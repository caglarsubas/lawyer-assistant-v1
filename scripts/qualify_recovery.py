"""Opt-in synthetic encrypted recovery drill; never targets an existing Compose project.

Requires preloaded API/Fuseki images built from the checkout and the pinned database
images. No provider, client data, host port, live .env or external network is used.
"""

import argparse
import base64
import hashlib
import json
import os
import platform
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))
sys.path.insert(0, str(ROOT / "scripts"))
from manage_backup import SERVICES, compose_command, inventory, volume_mounts  # noqa: E402
from recovery_fixture import code_fingerprint  # noqa: E402

POSTGRES = "postgres:16.10-bookworm@sha256:38471f330eb885e04de130b768d6db4e10469e2311879c7e5c699f6d2d8a1c74"
OPENSEARCH = "opensearchproject/opensearch:2.19.3@sha256:e96cc6ae1500a073d973c0906f30f7cf4d9c461f32f855f9242a2da933660cdd"
MARKER = "lawyer-recovery-drill-v1"


def command(argv, *, timeout=300, expected=0):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    if (expected == 0 and result.returncode != 0) or (expected != 0 and result.returncode == 0):
        # Captured output/argv can contain disposable credentials; keep them out of reports.
        raise RuntimeError("Recovery command returned an unexpected exit status")
    return result.stdout.strip()


def compose_definition(images, encryption_key, password):
    restricted = {"restart": "no", "networks": ["isolated"], "cap_drop": ["ALL"],
                  "security_opt": ["no-new-privileges:true"], "pids_limit": 256, "cpus": "2.0"}
    services = {name: {**restricted, "image": images[name], "pull_policy": "never"} for name in SERVICES}
    services["api"].update({
        "read_only": True, "tmpfs": ["/tmp:size=256m,mode=1777"], "mem_limit": "1g",
        "stop_grace_period": "240s",
        "environment": {"LA_RECOVERY_DRILL": MARKER, "LA_DEMO_MODE": "true", "LA_COOKIE_SECURE": "false",
                        "LA_DATA_DIR": "/data", "LA_PUBLIC_SOURCE_DIR": "/public-sources",
                        "LA_DATABASE_URL": f"postgresql+psycopg://lawyer:{password}@postgres:5432/lawyer_recovery_drill",
                        "LA_ENCRYPTION_KEY": encryption_key},
        "volumes": ["documents:/data", "public_sources:/public-sources", "graphs:/graph-releases:ro"],
        "depends_on": {"postgres": {"condition": "service_healthy"}},
        "healthcheck": {"test": ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"],
                        "interval": "2s", "timeout": "5s", "retries": 30},
    })
    services["postgres"].update({
        "cap_add": ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID"], "mem_limit": "1g",
        "environment": {"POSTGRES_DB": "lawyer_recovery_drill", "POSTGRES_USER": "lawyer",
                        "POSTGRES_PASSWORD": password, "POSTGRES_INITDB_ARGS": "--auth-host=scram-sha-256 --auth-local=scram-sha-256"},
        "volumes": ["postgres:/var/lib/postgresql/data"],
        "healthcheck": {"test": ["CMD", "pg_isready", "-U", "lawyer", "-d", "lawyer_recovery_drill"],
                        "interval": "2s", "timeout": "3s", "retries": 30},
    })
    services["opensearch"].update({
        "mem_limit": "1536m", "environment": {"discovery.type": "single-node", "DISABLE_INSTALL_DEMO_CONFIG": "true",
                                                "DISABLE_SECURITY_PLUGIN": "true", "OPENSEARCH_JAVA_OPTS": "-Xms512m -Xmx512m"},
        "volumes": ["opensearch:/usr/share/opensearch/data"],
        "healthcheck": {"test": ["CMD", "curl", "--fail", "--silent", "http://localhost:9200/_cluster/health?wait_for_status=yellow&timeout=2s"],
                        "interval": "3s", "timeout": "5s", "retries": 40},
    })
    services["fuseki"].update({
        "read_only": True, "mem_limit": "1g", "tmpfs": ["/tmp:size=512m,mode=1777"],
        "volumes": ["graphs:/fuseki:ro"],
        "healthcheck": {"test": ["CMD", "curl", "--fail", "--silent", "http://localhost:3030/structural/query?query=ASK%7B%7D"],
                        "interval": "2s", "timeout": "3s", "retries": 30},
    })
    return {"services": services, "networks": {"isolated": {"internal": True}},
            "volumes": {name: {} for name in ("documents", "postgres", "opensearch", "graphs", "public_sources")}}


def probe(containers, image, action):
    args = ["docker", "run", "--rm", "--network", "none", "--read-only", "--user", "0:0",
            "--cap-drop", "ALL", "--cap-add", "DAC_OVERRIDE", "--security-opt", "no-new-privileges:true",
            "--env", f"LA_RECOVERY_DRILL={MARKER}"]
    args += volume_mounts(containers, writable=action == "seed-volumes")
    return json.loads(command([*args, "--entrypoint", "python", image, "/app/scripts/recovery_fixture.py", action]))


def application_probe(compose, action):
    return json.loads(command([*compose, "exec", "-T", "api", "python", "/app/scripts/recovery_fixture.py", action]))


def fresh_project(name):
    # Reuse/cleanup is never inferred from a supplied name; both names are generated.
    for kind in ("container", "volume", "network"):
        args = ["docker", kind, "ls", "--quiet", "--filter", f"label=com.docker.compose.project={name}"]
        if kind == "container":
            args += ["--all"]
        if command(args):
            raise RuntimeError("Disposable project already exists")


def cleanup_project(compose):
    # --volumes affects only this generated project; no host directory is mounted.
    command([*compose, "down", "--volumes", "--remove-orphans", "--timeout", "30"], timeout=180)
    fresh_project(compose[compose.index("--project-name") + 1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-image", required=True, help="Prebuilt image from this checkout; never auto-pulled")
    parser.add_argument("--fuseki-image", default="lawyer-assistant-fuseki:5.3.0")
    parser.add_argument("--output", required=True, type=Path, help="New JSON report (no credentials or source payloads)")
    args = parser.parse_args()
    os.umask(0o077)
    # Exclusive output claim occurs before any Docker mutation.
    with args.output.open("x") as stream:
        stream.write('{"status":"incomplete"}\n')
    report = {"schema_version": MARKER, "status": "failed", "synthetic_only": True,
              "started_at": datetime.now(timezone.utc).isoformat(), "timings_seconds": {}, "checks": {},
              "scope": "encrypted five-volume cold restore; empty Fuseki corpus; fixture-only research without inference",
              "not_qualified": ["production RPO/RTO", "five-job throughput", "ingestion overlap", "populated graph rollback",
                                "real source rights or legal review", "real process crash or power-loss recovery"]}
    stage, projects = "preflight", []
    try:
        images = {name: command(["docker", "image", "inspect", "--format", "{{.Id}}", reference])
                  for name, reference in {"api": args.api_image, "postgres": POSTGRES,
                                          "opensearch": OPENSEARCH, "fuseki": args.fuseki_image}.items()}
        report["images"] = images
        stage = "verify_image_source"
        fingerprint = code_fingerprint(ROOT)
        actual = json.loads(command(["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
                                     "--env", f"LA_RECOVERY_DRILL={MARKER}", "--entrypoint", "python", images["api"],
                                     "/app/scripts/recovery_fixture.py", "code"]))
        if actual != fingerprint:
            raise ValueError("API image source differs from this checkout; rebuild before running the drill")
        report["api_source"] = fingerprint
        report["host_backup_tool_sha256"] = hashlib.sha256((ROOT / "deploy/manage_backup.py").read_bytes()).hexdigest()
        report["checkout_commit"] = command(["git", "-C", str(ROOT), "rev-parse", "HEAD"])
        report["checkout_dirty"] = bool(command(["git", "-C", str(ROOT), "status", "--porcelain"]))
        hardware = '{"cpus":{{.NCPU}},"memory_bytes":{{.MemTotal}},"os":{{json .OSType}},"architecture":{{json .Architecture}},"server_version":{{json .ServerVersion}}}'
        report["host"] = {"system": platform.system(), "architecture": platform.machine(),
                          "docker": json.loads(command(["docker", "info", "--format", hardware]))}
        with tempfile.TemporaryDirectory(prefix="lawyer-recovery-") as directory:
            work = Path(directory)
            config = work / "compose.json"
            definition = compose_definition(images, base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(), secrets.token_hex(24))
            config.write_text(json.dumps(definition))
            report["resource_limits"] = {name: {key: service[key] for key in ("cpus", "mem_limit", "pids_limit")}
                                         for name, service in definition["services"].items()}
            names = ["lawyer-recovery-" + secrets.token_hex(6) + suffix for suffix in ("-source", "-target")]
            source, target = [compose_command(name, [config], Path("/dev/null")) for name in names]
            for name in names:
                fresh_project(name)
            # Cleanup must run while configuration/secrets still exist.
            try:
                stage = "create_source"
                projects.append(source)
                command([*source, "up", "-d", "--wait", "--wait-timeout", "150"], timeout=180)
                stage = "seed_source"
                report["seed"] = application_probe(source, "seed")
                source_containers, _ = inventory(source)
                # Stop all owners before hashing or writing fixture epoch/sentinels.
                command([*source, "stop"], timeout=300)
                probe(source_containers, images["api"], "seed-volumes")
                before = probe(source_containers, images["api"], "inventory")
                if not before["epoch_exists"]:
                    raise ValueError("Missing source epoch fixture")
                report["volume_inventory"] = before["volumes"]
                key = work / "identity.txt"
                key.write_text(command(["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
                                        "--entrypoint", "age-keygen", images["api"]]))
                recipients = work / "recipients.txt"
                recipients.write_text(command(["docker", "run", "--rm", "--network", "none", "--read-only", "--user", "0:0",
                                               "--cap-drop", "ALL", "--cap-add", "DAC_OVERRIDE",
                                               "--mount", f"type=bind,src={key},dst=/key,readonly", "--entrypoint", "age-keygen", images["api"], "-y", "/key"]))
                archive = work / "backup.age"

                def transfer(action, project, path, *, expected=0):
                    flags = ["--recipients-file", str(recipients), "--stop-services"] if action == "backup" else ["--identity-file", str(key), "--fresh-target"]
                    return command([sys.executable, str(ROOT / "deploy/manage_backup.py"), action, str(path), *flags,
                                    "--project-name", project, "--compose-file", str(config), "--env-file", "/dev/null"], timeout=600, expected=expected)

                stage = "cold_backup"
                started = time.monotonic()
                transfer("backup", names[0], archive)
                report["timings_seconds"]["cold_backup"] = round(time.monotonic() - started, 3)
                report["archive"] = {"bytes": archive.stat().st_size, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
                stage = "create_target"
                projects.append(target)
                command([*target, "create"], timeout=120)
                target_containers, _ = inventory(target)
                probe(target_containers, images["api"], "empty")
                stage = "reject_truncated_archive"
                corrupt = work / "truncated.age"
                corrupt.write_bytes(archive.read_bytes()[:-32])
                transfer("restore", names[1], corrupt, expected=1)
                probe(target_containers, images["api"], "empty")
                report["checks"]["truncated_archive_rejected_without_writes"] = True
                stage = "restore"
                started = time.monotonic()
                transfer("restore", names[1], archive)
                report["timings_seconds"]["restore"] = round(time.monotonic() - started, 3)
                after = probe(target_containers, images["api"], "inventory")
                if after["volumes"] != before["volumes"] or after["epoch_exists"]:
                    raise ValueError("Restored bytes/metadata or publication invalidation differ")
                report["checks"]["five_volume_bytes_and_metadata_match_except_epoch"] = True
                stage = "reject_nonempty_target"
                transfer("restore", names[1], archive, expected=1)
                if probe(target_containers, images["api"], "inventory") != after:
                    raise ValueError("Rejected restore changed nonempty volumes")
                report["checks"]["nonempty_target_rejected_without_changes"] = True
                stage = "restored_startup"
                started = time.monotonic()
                command([*target, "up", "-d", "--wait", "--wait-timeout", "150"], timeout=180)
                report["timings_seconds"]["restored_startup"] = round(time.monotonic() - started, 3)
                stage = "verify_application"
                report["checks"].update(application_probe(target, "verify"))
                stage = "running_backup_restart"
                # A second backup tests the operator's downtime path. Deliberately
                # leave Fuseki stopped: backup must not start an idle service.
                command([*source, "up", "-d", "--wait", "--wait-timeout", "150", "api", "postgres", "opensearch"], timeout=180)
                transfer("backup", names[0], work / "running-backup.age")
                for service, container in source_containers.items():
                    running = command(["docker", "inspect", "--format", "{{.State.Running}}", container])
                    if running != ("false" if service == "fuseki" else "true"):
                        raise ValueError("Backup changed the previously running service set")
                command([*source, "up", "-d", "--wait", "--wait-timeout", "150", "api", "postgres", "opensearch"], timeout=180)
                report["checks"]["backup_restarts_only_previously_running_services"] = True
                report["status"] = "passed"
            finally:
                errors = []
                for project in reversed(projects):
                    try:
                        cleanup_project(project)
                    except (RuntimeError, OSError, subprocess.SubprocessError):
                        errors.append(project[project.index("--project-name") + 1])
                report["cleanup"] = {"complete": not errors, "remaining_projects": errors}
                if errors:
                    report["status"] = "failed"
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        report.update(status="failed", failure_stage=stage, failure_type=type(error).__name__)
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Synthetic recovery drill {report['status']}: {args.output}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
