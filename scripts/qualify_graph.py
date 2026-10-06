"""Opt-in synthetic signed-graph lifecycle drill using disposable Docker resources.

No existing deployment, dotenv, provider or legal/private source is used. Images
must already exist; this command never builds/pulls them or exposes host ports.
"""

import argparse
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
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "deploy"))
from graph_drill_fixture import MARKER  # noqa: E402
from load_metrics import cgroup_peaks  # noqa: E402
from manage_backup import compose_command  # noqa: E402
from qualify_recovery import cleanup_project, command, fresh_project  # noqa: E402
from recovery_fixture import code_fingerprint  # noqa: E402

FUSEKI_FILES = {"deploy/fuseki/runtime.py": "/opt/fuseki/runtime.py",
                "deploy/fuseki/entrypoint.sh": "/usr/local/bin/fuseki-entrypoint",
                "deploy/fuseki/config.ttl": "/etc/fuseki/config.ttl",
                "scripts/graph_releases.py": "/opt/scripts/graph_releases.py"}


def fuseki_fingerprint(root):
    files = [root / path for path in FUSEKI_FILES]
    files += [path for path in (root / "ontology").rglob("*")
              if path.is_file() and path.suffix in {".py", ".json", ".ttl", ".nq", ".trig"}]
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}


def verify_images(images):
    actual = json.loads(command(["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--env", "LA_RECOVERY_DRILL=lawyer-recovery-drill-v1", "--entrypoint", "python", images["api"],
        "/app/scripts/recovery_fixture.py", "code"]))
    if actual != code_fingerprint(ROOT):
        raise ValueError("API image source differs from checkout")
    # Enumerate the image's ontology too: detecting added files matters as well as
    # changed/missing known files. No image helper can simply assert its own hash.
    script = ("import hashlib,json; from pathlib import Path; "
              f"files={FUSEKI_FILES!r}; "
              "files.update({p.relative_to('/opt').as_posix():str(p) for p in Path('/opt/ontology').rglob('*') "
              "if p.is_file() and p.suffix in {'.py','.json','.ttl','.nq','.trig'}}); "
              "print(json.dumps({name:hashlib.sha256(Path(path).read_bytes()).hexdigest() for name,path in files.items()}))")
    observed = json.loads(command(["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
                                   "--entrypoint", "python3", images["fuseki"], "-c", script]))
    if observed != fuseki_fingerprint(ROOT):
        raise ValueError("Fuseki runtime/ontology image differs from checkout")
    return {"api": actual, "fuseki": {"files": len(observed),
            "sha256": hashlib.sha256(json.dumps(observed, sort_keys=True).encode()).hexdigest()}}


def compose_definition(images):
    def mounts(readonly):
        return [{"type": "volume", "source": name, "target": target, "read_only": readonly,
                 "volume": {"nocopy": True}} for name, target in (("graphs", "/fuseki"), ("fixture", "/drill"))]

    restricted = {"restart": "no", "networks": ["isolated"], "cap_drop": ["ALL"],
                  "security_opt": ["no-new-privileges:true"], "pids_limit": 256, "cpus": "2.0",
                  "read_only": True, "mem_limit": "1g", "pull_policy": "never"}
    fixture = {**restricted, "image": images["api"], "profiles": ["fixture"], "user": "10002:10002",
               "entrypoint": ["python", "/app/scripts/graph_drill_fixture.py"],
               "tmpfs": ["/tmp:size=256m,mode=1777"], "volumes": mounts(False),
               "environment": {"LA_GRAPH_DRILL": MARKER}}
    return {"services": {
        "fixture": fixture,
        "bootstrap": {**fixture, "user": "0:0", "cap_add": ["CHOWN"], "command": ["bootstrap"]},
        "fuseki": {**restricted, "image": images["fuseki"], "volumes": mounts(True),
                   "tmpfs": ["/tmp:size=512m,mode=1777"],
                   "environment": {"LA_GRAPH_TRUSTED_REVIEW_KEY": "/drill/TEST-ONLY-public.pem"},
                   "healthcheck": {"test": ["CMD", "curl", "--fail", "--silent", "http://localhost:3030/structural/query?query=ASK%7B%7D"],
                                   "interval": "2s", "timeout": "3s", "retries": 60}}},
        "volumes": {"graphs": {}, "fixture": {}}, "networks": {"isolated": {"internal": True}}}


def probe(compose, action, *, timeout=180):
    return json.loads(command([*compose, "run", "--rm", "--no-deps", "-T", "fixture", action], timeout=timeout))


def container_state(ident):
    return json.loads(command(["docker", "inspect", "--format", "{{json .State}}", ident]))


def runtime_resources(ident):
    state = container_state(ident)
    if not state["Running"] or state["OOMKilled"] or state["Restarting"]:
        raise ValueError("Graph runtime stopped or exhausted memory")
    fields = ["memory.peak", "memory.max", "pids.peak", "pids.max", "cpu.stat"]
    return cgroup_peaks(command(["docker", "exec", ident, "cat", *["/sys/fs/cgroup/" + field for field in fields]]))


def require_failed_start(state, logs):
    if (state["Running"] or state["ExitCode"] != 1 or state["OOMKilled"] or state["Restarting"]
            or "Fuseki serving release startup failed: Serving payload differs from signed source graph" not in logs
            or '"event": "verified_release_loaded"' in logs or '"event": "no_active_release"' in logs):
        raise ValueError("Corruption did not cause the expected fail-closed startup")


def wait_exit(ident, seconds=150):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        state = container_state(ident)
        if not state["Running"]:
            return state
        time.sleep(.5)
    raise TimeoutError("Fixture process did not exit within its budget")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-image", required=True)
    parser.add_argument("--fuseki-image", required=True)
    parser.add_argument("--output", required=True, type=Path, help="New payload-free JSON report")
    args = parser.parse_args()
    os.umask(0o077)
    with args.output.open("x") as stream:
        stream.write('{"status":"incomplete"}\n')
    report = {"schema_version": MARKER, "status": "failed", "synthetic_only": True,
              "started_at": datetime.now(timezone.utc).isoformat(), "checks": {}, "startups": {},
              "not_qualified": ["real legal/rights/private publication authorization", "legal assertion applicability",
                                "production corpus or sustained load", "OpenSearch reindex or inference overlap",
                                "encrypted populated graph restore", "power-loss durability or production RTO"]}
    stage = "preflight"
    try:
        images = {name: command(["docker", "image", "inspect", "--format", "{{.Id}}", reference])
                  for name, reference in {"api": args.api_image, "fuseki": args.fuseki_image}.items()}
        report.update(images=images, source=verify_images(images),
                      checkout_commit=command(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
                      checkout_dirty=bool(command(["git", "-C", str(ROOT), "status", "--porcelain"])))
        hardware = '{"cpus":{{.NCPU}},"memory_bytes":{{.MemTotal}},"os":{{json .OSType}},"architecture":{{json .Architecture}},"server_version":{{json .ServerVersion}}}'
        report["host"] = {"system": platform.system(), "architecture": platform.machine(),
                          "docker": json.loads(command(["docker", "info", "--format", hardware]))}
        with tempfile.TemporaryDirectory(prefix="lawyer-graph-") as directory:
            config = Path(directory) / "compose.json"
            definition = compose_definition(images)
            config.write_text(json.dumps(definition))
            report["resource_limits"] = {name: {key: service[key] for key in ("cpus", "mem_limit", "pids_limit")}
                                         for name, service in definition["services"].items()}
            project = "lawyer-graph-" + secrets.token_hex(6)
            compose = compose_command(project, [config], Path("/dev/null"))
            fresh_project(project)
            report["cleanup"] = {"complete": False, "remaining_project": project}

            def start(label, variant):
                began = time.monotonic()
                command([*compose, "up", "-d", "--force-recreate", "--wait", "--wait-timeout", "150", "fuseki"], timeout=180)
                seconds = round(time.monotonic() - began, 3)
                verified = probe(compose, "verify-" + variant)
                ident = command([*compose, "ps", "--quiet", "fuseki"])
                kernel = runtime_resources(ident)
                report["startups"][label] = {"compose_ready_seconds": seconds, "verified": verified, "kernel": kernel}
                return verified

            try:
                stage = "seed"
                command([*compose, "run", "--rm", "--no-deps", "-T", "bootstrap"])
                report["fixture"] = probe(compose, "seed", timeout=300)
                stage = "initial_start"
                original = start("initial_a", "a")
                stage = "install_while_querying"
                report["checks"]["install_overlap"] = probe(compose, "overlap")
                report["checks"]["live_activation_denied"] = probe(compose, "deny-live-activate")
                stage = "interrupted_import"
                interrupted = command([*compose, "run", "-d", "--no-deps", "fixture", "interrupted-install"])
                deadline = time.monotonic() + 90
                while not probe(compose, "ready")["ready"]:
                    if not container_state(interrupted)["Running"] or time.monotonic() >= deadline:
                        raise ValueError("Interrupted import never reached its partial-copy barrier")
                    time.sleep(.5)
                command(["docker", "kill", "--signal", "KILL", interrupted])
                stopped = wait_exit(interrupted, 10)
                if stopped["ExitCode"] != 137 or stopped["OOMKilled"]:
                    raise ValueError("Importer was not killed at the intended barrier")
                report["checks"]["interrupted_install"] = probe(compose, "recover-install")
                report["runtime_after_imports"] = runtime_resources(command([*compose, "ps", "--quiet", "fuseki"]))
                stage = "reindex_a"
                if start("recreated_a", "a") != original:
                    raise ValueError("Rebuilt indexes differ from the original immutable release")
                report["checks"]["fresh_tdb2_rebuild_matches"] = True
                stage = "activate_b"
                command([*compose, "stop", "fuseki"])
                pointer_b = probe(compose, "activate-b")
                if pointer_b["sequence"] != 2:
                    raise ValueError("Activation did not advance sequence")
                report["checks"]["activated_b"] = pointer_b
                start("activated_b", "b")
                stage = "corrupt_active"
                command([*compose, "stop", "fuseki"])
                probe(compose, "corrupt-b")
                command([*compose, "up", "-d", "--force-recreate", "fuseki"])
                ident = command([*compose, "ps", "--all", "--quiet", "fuseki"])
                failed = wait_exit(ident)
                # Fetch both Docker log streams, retaining neither in the report.
                # These contain invented data only.
                logged = subprocess.run(["docker", "logs", ident], capture_output=True, text=True, timeout=10, check=True)
                require_failed_start(failed, logged.stdout + logged.stderr)
                report["checks"]["corrupt_active_fails_closed_without_fallback"] = True
                stage = "rollback"
                pointer_a = probe(compose, "rollback-a")
                if pointer_a["sequence"] != 3 or pointer_a["release_id"] != original["release_id"]:
                    raise ValueError("Rollback did not restore A with a new sequence")
                report["checks"]["rolled_back_a"] = pointer_a
                if start("rollback_a", "a") != original:
                    raise ValueError("Rollback served different content")
                stage = "reject_unsafe_transitions"
                command([*compose, "stop", "fuseki"])
                report["checks"]["stale_sequence_denied"] = probe(compose, "deny-stale-sequence")
                report["checks"]["corrupt_rollback_target_denied"] = probe(compose, "deny-corrupt-rollback")
                if start("final_a", "a") != original:
                    raise ValueError("Rejected transition changed serving data")
                report["status"] = "passed"
            finally:
                try:
                    cleanup_project(compose)
                    report["cleanup"] = {"complete": True}
                except (RuntimeError, ValueError, OSError, subprocess.SubprocessError):
                    report.update(status="failed", cleanup={"complete": False, "remaining_project": project})
    except Exception as error:
        report.update(status="failed", failure_stage=stage, failure_type=type(error).__name__)
    finally:
        if report.get("cleanup", {}).get("complete") is not True:
            report["status"] = "failed"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Synthetic graph drill {report['status']}: {args.output}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
