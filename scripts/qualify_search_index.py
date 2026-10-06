"""Opt-in real OpenSearch index lifecycle test in a fresh internal Docker project."""

import argparse
import hashlib
import json
import os
import platform
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "deploy"))
from manage_backup import compose_command  # noqa: E402
from qualify_recovery import OPENSEARCH, POSTGRES, cleanup_project, command, fresh_project  # noqa: E402
from recovery_fixture import code_fingerprint  # noqa: E402

MARKER = "lawyer-search-index-drill-v2"


def tests_fingerprint(root):
    files = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted((root / "backend/tests").rglob("*.py"))}
    return {"files": len(files), "sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()}


def compose_definition(images, password):
    restricted = {"restart": "no", "networks": ["isolated"], "cap_drop": ["ALL"],
                  "security_opt": ["no-new-privileges:true"], "pids_limit": 256, "cpus": "2.0", "pull_policy": "never"}
    return {"services": {
        "postgres": {**restricted, "image": images["postgres"], "mem_limit": "512m",
            # Match production: vendor entrypoint owns the new volume, then drops UID.
            "cap_add": ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID"],
            "volumes": ["postgres:/var/lib/postgresql/data"],
            "environment": {"POSTGRES_DB": "lawyer_snapshot_test", "POSTGRES_USER": "snapshot_test",
                            "POSTGRES_PASSWORD": password,
                            "POSTGRES_INITDB_ARGS": "--auth-host=scram-sha-256 --auth-local=scram-sha-256"},
            "healthcheck": {"test": ["CMD-SHELL", "pg_isready -U snapshot_test -d lawyer_snapshot_test"],
                            "interval": "3s", "timeout": "3s", "retries": 30}},
        "opensearch": {**restricted, "image": images["opensearch"], "mem_limit": "1536m",
            "volumes": ["opensearch:/usr/share/opensearch/data"],
            "environment": {"discovery.type": "single-node", "DISABLE_INSTALL_DEMO_CONFIG": "true",
                            "DISABLE_SECURITY_PLUGIN": "true", "OPENSEARCH_JAVA_OPTS": "-Xms512m -Xmx512m"},
            "healthcheck": {"test": ["CMD", "curl", "--fail", "--silent", "http://localhost:9200/_cluster/health?wait_for_status=yellow&timeout=2s"],
                            "interval": "3s", "timeout": "5s", "retries": 40}},
        "driver": {**restricted, "image": images["test"], "profiles": ["driver"], "read_only": True,
            "mem_limit": "1g", "tmpfs": ["/tmp:size=256m,mode=1777"],
            "environment": {"LA_SEARCH_INDEX_DRILL": MARKER, "LA_PUBLIC_SOURCE_DIR": "/tmp/public-only",
                            "LA_TEST_POSTGRES_URL": f"postgresql+psycopg://snapshot_test:{password}@postgres:5432/lawyer_snapshot_test"},
            "command": ["python", "-m", "pytest", "tests/test_search_index_opensearch.py", "tests/test_snapshot_set_postgres.py",
                        "tests/test_set_authorization_postgres.py", "tests/test_research_jobs_postgres.py", "-q", "-s", "-p", "no:cacheprovider",
                        "--basetemp=/tmp/search-fixture", "--disable-warnings"]}},
        "volumes": {"opensearch": {}, "postgres": {}}, "networks": {"isolated": {"internal": True}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-image", required=True, help="Prebuilt current source + pinned development dependencies")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    with args.output.open("x") as stream:
        stream.write('{"status":"incomplete"}\n')
    report = {"schema_version": MARKER, "status": "failed", "synthetic_only": True,
              "started_at": datetime.now(timezone.utc).isoformat(),
              "not_qualified": ["real legal/source rights", "production capacity", "retrieval recall or adverse authority coverage",
                                "embedding/reranker quality", "five model jobs during reindexing", "representative PostgreSQL lock latency or production revocation SLA"]}
    stage = "preflight"
    try:
        images = {name: command(["docker", "image", "inspect", "--format", "{{.Id}}", value])
                  for name, value in {"test": args.test_image, "opensearch": OPENSEARCH, "postgres": POSTGRES}.items()}
        script = ("import sys,json,hashlib; from pathlib import Path; sys.path.insert(0,'/app/scripts'); "
                  "from recovery_fixture import code_fingerprint; root=Path('/app'); "
                  "files={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() "
                  "for p in sorted((root/'backend/tests').rglob('*.py'))}; "
                  "fingerprint={'files':len(files),'sha256':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()}; "
                  "print(json.dumps({'application':code_fingerprint(root),'tests':fingerprint}))")
        observed = json.loads(command(["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
                                       "--entrypoint", "python", images["test"], "-c", script]))
        if observed != {"application": code_fingerprint(ROOT), "tests": tests_fingerprint(ROOT)}:
            raise ValueError("Test image differs from checkout")
        report.update(images=images, source=observed, checkout_commit=command(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
                      checkout_dirty=bool(command(["git", "-C", str(ROOT), "status", "--porcelain"])),
                      host={"system": platform.system(), "architecture": platform.machine()})
        with tempfile.TemporaryDirectory(prefix="lawyer-search-") as directory:
            config = Path(directory) / "compose.json"
            definition = compose_definition(images, secrets.token_hex(24))
            config.write_text(json.dumps(definition))
            report["resource_limits"] = {name: {key: service[key] for key in ("cpus", "mem_limit", "pids_limit")}
                                         for name, service in definition["services"].items()}
            project = "lawyer-search-" + secrets.token_hex(6)
            compose = compose_command(project, [config], Path("/dev/null"))
            fresh_project(project)
            report["cleanup"] = {"complete": False, "remaining_project": project}
            try:
                stage = "database_startup"
                command([*compose, "up", "-d", "--wait", "--wait-timeout", "150", "postgres", "opensearch"], timeout=180)
                stage = "workload"
                result = subprocess.run([*compose, "run", "--rm", "--no-deps", "-T", "driver"],
                                        capture_output=True, text=True, timeout=240)
                lines = [line.removeprefix("SEARCH_INDEX_DRILL_REPORT=") for line in result.stdout.splitlines()
                         if line.startswith("SEARCH_INDEX_DRILL_REPORT=")]
                if result.returncode != 0 or len(lines) != 1:
                    raise ValueError("Isolated OpenSearch qualification did not pass")
                report["workload"] = json.loads(lines[0])
                if report["workload"].get("status") != "passed":
                    raise ValueError("Incomplete workload")
                report["status"] = "passed"
            finally:
                try:
                    cleanup_project(compose)
                    report["cleanup"] = {"complete": True}
                except Exception:
                    report["status"] = "failed"
    except Exception as error:
        report.update(status="failed", failure_stage=stage, failure_type=type(error).__name__)
    finally:
        if report.get("cleanup", {}).get("complete") is not True:
            report["status"] = "failed"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Synthetic search-index drill {report['status']}: {args.output}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
