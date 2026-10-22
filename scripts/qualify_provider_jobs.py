"""Opt-in real-provider jobs with disposable documents/database and no host ports."""

import argparse
import base64
import json
import os
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "deploy"), str(ROOT / "backend")]
from load_metrics import cgroup_peaks  # noqa: E402
from manage_backup import compose_command  # noqa: E402
from provider_job_checks import WORKLOADS  # noqa: E402
from provider_job_fixture import MARKER, PROFILE_FIELDS  # noqa: E402
from qualify_load import ResourceSampler, compose_definition  # noqa: E402
from qualify_recovery import POSTGRES, cleanup_project, command, fresh_project  # noqa: E402
from recovery_fixture import code_fingerprint  # noqa: E402
from restart_preflight_drill import unused_drill_subnet  # noqa: E402


def definition(images, key, password, token, subnet, profile_file, key_file, network, *, workload="short-txt-v1", context_limit=8192):
    if workload not in WORKLOADS or type(context_limit) is not int or not 3072 <= context_limit <= 16384:
        raise ValueError("Invalid declared workload")
    result = compose_definition(images, key, password, token, subnet)
    api = result["services"]["api"]
    api["command"][1] = "provider_job_fixture:create_app"
    api["environment"]["LA_LOAD_REAL_PROVIDER"] = MARKER
    if workload == "quote-volume-v1":
        api["environment"]["LA_QUOTE_VOLUME_CANDIDATE"] = MARKER
    api["volumes"] += [
        {"type": "bind", "source": str(profile_file), "target": "/run/secrets/provider-profile.json", "read_only": True},
        {"type": "bind", "source": str(key_file), "target": "/run/secrets/provider-key", "read_only": True}]
    api["networks"]["provider"] = {"ipv4_address": "172.30.240.14"}
    result["networks"]["provider"] = {"external": True, "name": network}
    driver = {"quote-selection-v1": "quote_selection_driver.py",
              "quote-volume-v1": "quote_volume_driver.py"}.get(workload, "provider_job_driver.py")
    result["services"]["driver"]["command"] = ["python", "/app/scripts/" + driver]
    result["services"]["driver"]["environment"].update(
        LA_REAL_JOB_WORKLOAD=workload, LA_REAL_JOB_CONTEXT_UNITS=str(context_limit))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-image", required=True)
    parser.add_argument("--provider-profile", required=True, type=Path)
    parser.add_argument("--provider-key-file", required=True, type=Path)
    parser.add_argument("--provider-network", required=True)
    parser.add_argument("--relay-container", required=True)
    parser.add_argument("--workload", choices=WORKLOADS, default="short-txt-v1")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute-real-provider", required=True, action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    with args.output.open("x") as stream:
        stream.write('{"status":"incomplete"}\n')
    report = {"schema": MARKER, "status": "failed", "synthetic_documents_only": True, "workload_profile": args.workload,
              "started_at": datetime.now(timezone.utc).isoformat(),
              "not_qualified": ["private case review", "reviewed public-corpus research", "production or sustained capacity",
                                "GPU parallelism", "tunnel retention or disconnected operation",
                                "malware scanning", "production isolated extraction service", "OCR or visual fidelity"]}
    stage = "preflight"
    try:
        for path, maximum in ((args.provider_profile, 16384), (args.provider_key_file, 4096)):
            if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077 or path.stat().st_size > maximum:
                raise ValueError("Protected fixture input required")
        profile = json.loads(args.provider_profile.read_text())
        if set(profile) != PROFILE_FIELDS or profile["provider_base_url"] != "http://172.30.240.2:8083/v1":
            raise ValueError("Expected configured relay profile")
        relay = json.loads(command(["docker", "inspect", args.relay_container]))[0]
        labels = relay["Config"]["Labels"]
        if (labels.get("com.docker.compose.project") != "lawyer-assistant-v1"
                or labels.get("com.docker.compose.service") != "provider-relay"
                or relay["State"]["Health"]["Status"] != "healthy"):
            raise ValueError("Owned healthy relay required")
        network = json.loads(command(["docker", "network", "inspect", args.provider_network]))[0]
        members = set(network["Containers"])
        if (network["Internal"] is not True or network["IPAM"]["Config"][0]["Subnet"] != "172.30.240.0/28"
                or len(members) != 2 or relay["Id"] not in members
                or any(e["IPv4Address"].split("/")[0] == "172.30.240.14" for e in network["Containers"].values())):
            raise ValueError("Expected dedicated provider network without fixture endpoint")
        images = {name: command(["docker", "image", "inspect", "--format", "{{.Id}}", reference])
                  for name, reference in {"api": args.api_image, "postgres": POSTGRES}.items()}
        actual = json.loads(command(["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--env", "LA_RECOVERY_DRILL=lawyer-recovery-drill-v1", "--entrypoint", "python", images["api"],
            "/app/scripts/recovery_fixture.py", "code"]))
        if actual != code_fingerprint(ROOT):
            raise ValueError("Fixture image source differs from checkout")
        report.update(images=images, api_source=actual, relay_image=relay["Image"],
                      context_units=profile["provider_context_limit"], model=profile["provider_model"])
        hardware = '{"cpus":{{.NCPU}},"memory_bytes":{{.MemTotal}},"os":{{json .OSType}},"architecture":{{json .Architecture}}}'
        report["docker_host"] = json.loads(command(["docker", "info", "--format", hardware]))
        with tempfile.TemporaryDirectory(prefix="lawyer-provider-jobs-") as directory:
            path = Path(directory) / "compose.json"
            value = definition(images, base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(), secrets.token_hex(24),
                secrets.token_hex(32), unused_drill_subnet(), args.provider_profile.resolve(), args.provider_key_file.resolve(), args.provider_network,
                workload=args.workload, context_limit=profile["provider_context_limit"])
            path.write_text(json.dumps(value))
            project = "lawyer-provider-jobs-" + secrets.token_hex(6)
            fresh_project(project)
            compose = compose_command(project, [path], Path("/dev/null"))
            report["cleanup"] = {"complete": False, "remaining_project": project}
            sampler = None
            try:
                stage = "startup"
                command([*compose, "up", "-d", "--wait", "--wait-timeout", "120", "api", "postgres"], timeout=150)
                containers = {name: command([*compose, "ps", "--quiet", name]) for name in ("api", "postgres")}
                containers["provider-relay"] = relay["Id"]
                sampler = ResourceSampler(containers)
                sampler.thread.start()
                stage = "jobs"
                result = subprocess.run([*compose, "run", "--rm", "--no-deps", "driver"], capture_output=True, text=True, timeout=240)
                report["workload"] = json.loads(result.stdout)
                if result.returncode != 0 or report["workload"]["status"] != "passed":
                    raise ValueError("Declared job waves failed")
                stage = "resources"
                report["resources"] = sampler.finish()
                sampler = None
                if not report["resources"]["valid"]:
                    raise ValueError("Resource sampling incomplete")
                for name, ident in containers.items():
                    state = json.loads(command(["docker", "inspect", "--format", "{{json .State}}", ident]))
                    if not state["Running"] or state["OOMKilled"] or state["Restarting"]:
                        raise ValueError("Measured service failed")
                    fields = ["memory.peak", "memory.max", "pids.peak", "pids.max", "cpu.stat"]
                    report["resources"]["services"][name]["kernel"] = cgroup_peaks(command(
                        ["docker", "exec", ident, "cat", *["/sys/fs/cgroup/" + f for f in fields]]))
                report["status"] = "passed"
            finally:
                if sampler is not None:
                    report["resources"] = sampler.finish()
                cleanup_project(compose)
                current = json.loads(command(["docker", "network", "inspect", args.provider_network]))[0]
                if set(current["Containers"]) != members:
                    raise ValueError("Provider network membership changed")
                report["cleanup"] = {"complete": True, "original_provider_members_restored": True}
    except Exception:
        report.update(status="failed", failure_stage=stage)
    if report.get("cleanup", {}).get("complete") is not True:
        report["status"] = "failed"
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "failure_stage": report.get("failure_stage")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
