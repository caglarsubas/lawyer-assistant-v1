"""Opt-in five-job application baseline using only disposable Docker resources."""

import argparse
import base64
import json
import os
import platform
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "deploy"))
from load_fixture import MARKER  # noqa: E402
from load_metrics import cgroup_peaks, resource_sample  # noqa: E402
from manage_backup import compose_command  # noqa: E402
from qualify_recovery import POSTGRES, cleanup_project, command, fresh_project  # noqa: E402
from qualify_recovery import compose_definition as recovery_definition  # noqa: E402
from recovery_fixture import code_fingerprint  # noqa: E402


def compose_definition(images, key, password, token):
    definition = recovery_definition({**images, "fuseki": images["api"], "opensearch": images["api"]}, key, password)
    services = definition["services"]
    del services["fuseki"], services["opensearch"]
    environment = {"LA_LOAD_DRILL": MARKER, "LA_LOAD_CONTROL_TOKEN": token,
                   "LA_DATABASE_URL": f"postgresql+psycopg://lawyer:{password}@postgres:5432/lawyer_load_drill",
                   "LA_ENCRYPTION_KEY": key}
    services["api"].update({"environment": environment, "volumes": ["documents:/data"],
        "command": ["uvicorn", "load_fixture:create_app", "--app-dir", "/app/scripts", "--factory",
                    "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]})
    services["postgres"]["environment"]["POSTGRES_DB"] = "lawyer_load_drill"
    services["postgres"]["healthcheck"]["test"][-1] = "lawyer_load_drill"
    services["driver"] = {"image": images["api"], "pull_policy": "never", "profiles": ["driver"],
        "command": ["python", "/app/scripts/load_driver.py"], "restart": "no", "networks": ["isolated"],
        "environment": {name: value for name, value in environment.items() if name != "LA_ENCRYPTION_KEY"},
        "read_only": True, "tmpfs": ["/tmp:size=64m,mode=1777"], "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"], "cpus": "1.0", "mem_limit": "768m", "pids_limit": 128}
    definition["volumes"] = {"documents": {}, "postgres": {}}
    return definition


class ResourceSampler:
    """Docker CLI RSS-like/cache-adjusted samples, not a continuous peak profiler."""

    def __init__(self, containers):
        self.containers = containers
        self.names = {command(["docker", "inspect", "--format", "{{.Name}}", ident]).lstrip("/"): service
                      for service, ident in containers.items()}
        self.peaks = {service: {"samples": 0, "sampled_peak_memory_bytes": 0, "sampled_peak_cpu_percent": 0,
                               "sampled_peak_pids": 0} for service in containers}
        self.errors = 0
        self.stop = Event()
        self.thread = Thread(target=self.sample, daemon=True)

    def sample(self):
        while not self.stop.is_set():
            try:
                output = command(["docker", "stats", "--no-stream", "--format", "{{json .}}", *self.containers.values()], timeout=10)
                observed = set()
                for line in output.splitlines():
                    row = json.loads(line)
                    service = self.names[row["Name"]]
                    if service in observed:
                        raise ValueError("Duplicate sample")
                    observed.add(service)
                    parsed = resource_sample(row)
                    peak = self.peaks[service]
                    peak["samples"] += 1
                    peak["sampled_peak_memory_bytes"] = max(peak["sampled_peak_memory_bytes"], parsed["memory_bytes"])
                    peak["sampled_peak_cpu_percent"] = max(peak["sampled_peak_cpu_percent"], parsed["cpu_percent"])
                    peak["sampled_peak_pids"] = max(peak["sampled_peak_pids"], parsed["pids"])
                    peak["memory_limit_bytes"] = parsed["memory_limit_bytes"]
                if observed != set(self.containers):
                    raise ValueError("Incomplete sample")
            except Exception:
                # Any unexpected schema/transport failure invalidates the measurement;
                # a dead sampler must not turn earlier good samples into a pass.
                self.errors += 1
            self.stop.wait(1)

    def finish(self):
        self.stop.set()
        self.thread.join(timeout=15)
        return {"services": self.peaks, "sampling_errors": self.errors,
                "valid": not self.thread.is_alive() and self.errors == 0 and all(row["samples"] >= 2 for row in self.peaks.values()),
                "method": "docker stats --no-stream plus 1s pause; sampled peaks may miss short bursts; driver excluded"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-image", required=True, help="Prebuilt current source; never auto-pulled")
    parser.add_argument("--output", required=True, type=Path, help="New payload-free JSON report")
    args = parser.parse_args()
    os.umask(0o077)
    with args.output.open("x") as stream:
        stream.write('{"status":"incomplete"}\n')
    report = {"schema_version": MARKER, "status": "failed", "synthetic_only": True,
              "started_at": datetime.now(timezone.utc).isoformat(),
              "not_qualified": ["real model latency or throughput", "reviewed public corpus retrieval", "public source ingestion",
                                "malware or OCR qualification", "production capacity or latency SLOs", "sustained soak or stress ceiling"]}
    stage = "preflight"
    try:
        images = {name: command(["docker", "image", "inspect", "--format", "{{.Id}}", reference])
                  for name, reference in {"api": args.api_image, "postgres": POSTGRES}.items()}
        expected = code_fingerprint(ROOT)
        actual = json.loads(command(["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--env", "LA_RECOVERY_DRILL=lawyer-recovery-drill-v1", "--entrypoint", "python", images["api"],
            "/app/scripts/recovery_fixture.py", "code"]))
        if actual != expected:
            raise ValueError("API image source differs from checkout")
        report.update(images=images, api_source=actual, checkout_commit=command(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
                      checkout_dirty=bool(command(["git", "-C", str(ROOT), "status", "--porcelain"])))
        hardware = '{"cpus":{{.NCPU}},"memory_bytes":{{.MemTotal}},"os":{{json .OSType}},"architecture":{{json .Architecture}},"server_version":{{json .ServerVersion}}}'
        report["host"] = {"system": platform.system(), "architecture": platform.machine(),
                          "docker": json.loads(command(["docker", "info", "--format", hardware]))}
        with tempfile.TemporaryDirectory(prefix="lawyer-load-") as directory:
            config = Path(directory) / "compose.json"
            definition = compose_definition(images, base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
                                            secrets.token_hex(24), secrets.token_hex(32))
            config.write_text(json.dumps(definition))
            report["resource_limits"] = {name: {key: service[key] for key in ("cpus", "mem_limit", "pids_limit")}
                                         for name, service in definition["services"].items()}
            project = "lawyer-load-" + secrets.token_hex(6)
            compose = compose_command(project, [config], Path("/dev/null"))
            fresh_project(project)
            report["cleanup"] = {"complete": False, "remaining_project": project}
            sampler = None
            try:
                stage = "startup"
                command([*compose, "up", "-d", "--wait", "--wait-timeout", "120", "api", "postgres"], timeout=150)
                containers = {name: command([*compose, "ps", "--quiet", name]) for name in ("api", "postgres")}
                sampler = ResourceSampler(containers)
                sampler.thread.start()
                stage = "workload"
                process = subprocess.run([*compose, "run", "--rm", "--no-deps", "driver"], capture_output=True, text=True, timeout=240)
                result = json.loads(process.stdout)
                report["workload"] = result
                if process.returncode != 0 or result.get("status") != "passed":
                    raise ValueError("Synthetic workload failed")
                stage = "resource_verification"
                report["resources"] = sampler.finish()
                sampler = None
                if not report["resources"]["valid"]:
                    raise ValueError("Resource sampling incomplete")
                for service, ident in containers.items():
                    state = json.loads(command(["docker", "inspect", "--format", "{{json .State}}", ident]))
                    if not state["Running"] or state["OOMKilled"] or state["Restarting"]:
                        raise ValueError("A measured service stopped or exhausted memory")
                    fields = ["memory.peak", "memory.max", "pids.peak", "pids.max", "cpu.stat"]
                    report["resources"]["services"][service]["kernel"] = cgroup_peaks(command(
                        ["docker", "exec", ident, "cat", *["/sys/fs/cgroup/" + field for field in fields]]))
                report["services_running_without_oom"] = True
                report["status"] = "passed"
            finally:
                if sampler is not None:
                    report["resources"] = sampler.finish()
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
    print(f"Synthetic five-job drill {report['status']}: {args.output}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
