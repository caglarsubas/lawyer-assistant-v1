"""Disposable Docker IP-allocation drill; no application data or backup keys.

Uses an explicitly selected immutable local image with Python. Creates only an
internal network and bounded, nonroot sleepers with no ports, mounts or secrets.
Does not run a backup, restore a volume or operate on the application project.
"""

import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
import traceback
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))
import manage_backup as backup  # noqa: E402

OWNER = "lawyer-assistant.restart-preflight-drill"


def run(command, *, check=True):
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if check and result.returncode:
        raise RuntimeError("Isolated Docker operation failed")
    return result


def inspect_network(ident):
    # Only inspect our own labelled network; never retrieve container environments.
    return json.loads(run(["docker", "network", "inspect", "--format",
                           '{"labels":{{json .Labels}},"ipam":{{json .IPAM.Config}},'
                           '"internal":{{json .Internal}},"driver":{{json .Driver}},'
                           '"containers":{{json .Containers}}}', ident]).stdout)


def inspect_node(ident):
    return json.loads(run(["docker", "inspect", "--format",
                           '{"owner":{{json (index .Config.Labels "' + OWNER + '")}},'
                           '"running":{{json .State.Running}},'
                           '"image":{{json .Image}},"mounts":{{json .Mounts}},'
                           '"bindings":{{json .HostConfig.PortBindings}},'
                           '"read_only":{{json .HostConfig.ReadonlyRootfs}},'
                           '"cap_drop":{{json .HostConfig.CapDrop}},'
                           '"security_options":{{json .HostConfig.SecurityOpt}},'
                           '"user":{{json .Config.User}},"privileged":{{json .HostConfig.Privileged}},'
                           '"memory":{{json .HostConfig.Memory}},"nano_cpus":{{json .HostConfig.NanoCpus}},'
                           '"pid_limit":{{json .HostConfig.PidsLimit}},'
                           '"networks":{{json .NetworkSettings.Networks}}}', ident]).stdout)


def unused_drill_subnet():
    """One calculated benchmark-range subnet; no retry grid or network pruning."""
    ids = run(["docker", "network", "ls", "--quiet"]).stdout.split()
    if len(ids) > 1024 or any(not re.fullmatch(r"[0-9a-f]{12,64}", ident) for ident in ids):
        raise RuntimeError("Cannot bound the Docker network inventory")
    allocated = []
    if ids:
        raw = run(["docker", "network", "inspect", "--format", "{{json .IPAM.Config}}", *ids]).stdout
        if len(raw.encode()) > 512 * 1024:
            raise RuntimeError("Docker network metadata exceeds the drill bound")
        lines = raw.splitlines()
        if len(lines) != len(ids):
            raise RuntimeError("Cannot verify the complete Docker network inventory")
        for line in lines:
            config = json.loads(line)
            if config is None:
                config = []
            if not isinstance(config, list):
                raise RuntimeError("Cannot verify Docker subnet metadata")
            for entry in config:
                if not isinstance(entry, dict) or not isinstance(entry.get("Subnet"), str):
                    raise RuntimeError("Cannot verify Docker subnet metadata")
                subnet = ipaddress.ip_network(entry["Subnet"])
                if subnet.version == 4:
                    allocated.append(subnet)
    candidates = list(ipaddress.ip_network("198.19.0.0/16").subnets(new_prefix=28))
    for candidate in reversed(candidates):
        if not any(candidate.overlaps(existing) for existing in allocated):
            return str(candidate)
    raise RuntimeError("No unused isolated drill subnet is available")


def drill(image, directory):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("Supply an immutable, locally available trusted Python image ID")
    if run(["docker", "image", "inspect", "--format", "{{.Id}}", image]).stdout.strip() != image:
        raise ValueError("Cannot verify the local drill image")
    token = uuid.uuid4().hex[:12]
    project = "restart-check-" + token
    network = None
    nodes = []
    roles = {}

    def owned(ident, check_posture=True):
        data = inspect_node(ident)
        if data["owner"] != token:
            raise RuntimeError("Isolated container ownership could not be verified")
        if check_posture and (data["image"] != image or data["mounts"] or data["bindings"]
                              or data["read_only"] is not True or data["privileged"] is not False
                              or data["user"] != "10001:10001" or data["cap_drop"] != ["ALL"]
                              or data["security_options"] != ["no-new-privileges:true"]
                              or data["memory"] != 48 * 1024 * 1024
                              or data["nano_cpus"] != 250_000_000 or data["pid_limit"] != 32):
            raise RuntimeError("Isolated container posture could not be verified")
        return data

    def change(action, ids, *, check=True):
        if not set(ids) <= set(nodes) or not ids:
            raise RuntimeError("Refusing an operation outside the isolated drill")
        for ident in ids:
            owned(ident)
        return run(["docker", action, *ids], check=check)

    def node(role, address=None):
        args = ["docker", "create", "--pull=never", "--name", project + "-" + role,
                "--label", OWNER + "=" + token, "--label", "com.docker.compose.project=" + project,
                "--label", "com.docker.compose.service=" + role,
                "--label", "com.docker.compose.oneoff=False",
                # Compose getDefaultFilters requires this label's presence.
                "--label", "com.docker.compose.config-hash=" + token,
                "--network", network, "--read-only", "--user", "10001:10001",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                "--memory", "48m", "--cpus", "0.25", "--pids-limit", "32", "--stop-timeout", "1"]
        if address:
            args += ["--ip", address]
        args += ["--entrypoint", "python", image, "-c",
                 "import signal,sys,time;signal.signal(signal.SIGTERM,lambda *_:sys.exit(0));time.sleep(180)"]
        ident = run(args).stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{64}", ident):
            raise RuntimeError("Cannot verify isolated container identity")
        nodes.append(ident)
        roles[role] = ident
        change("start", [ident])
        return ident

    def address(ident):
        endpoints = owned(ident)["networks"]
        if len(endpoints) != 1:
            raise RuntimeError("Unexpected isolated network attachment")
        return next(iter(endpoints.values()))["IPAddress"]

    try:
        selected_subnet = unused_drill_subnet()
        network = run(["docker", "network", "create", "--driver", "bridge", "--internal", "--label", OWNER + "=" + token,
                       "--subnet", selected_subnet, project]).stdout.strip()
        net = inspect_network(network)
        if (net["labels"].get(OWNER) != token or len(net["ipam"]) != 1
                or net["internal"] is not True or net["driver"] != "bridge"):
            raise RuntimeError("Cannot verify isolated network ownership")
        subnet = ipaddress.ip_network(net["ipam"][0]["Subnet"])
        if subnet.version != 4 or subnet.num_addresses < 8 or str(subnet) != selected_subnet:
            raise RuntimeError("Isolated network lacks sufficient IPv4 addresses")
        fixed_ip = str(subnet.network_address + 2)
        fixed = node("postgres", fixed_ip)
        dynamic = node("opensearch")
        original = {ident: address(ident) for ident in [fixed, dynamic]}
        schedule = backup.restart_plan([dynamic, fixed])
        if schedule != [[fixed], [dynamic]]:
            raise RuntimeError("Reserved endpoint did not precede its dynamic allocator")

        # Observe the legacy dynamic-first hazard only inside our disposable set.
        change("stop", [fixed, dynamic])
        change("start", [dynamic])
        legacy = change("start", [fixed], check=False)
        collision = legacy.returncode != 0 and address(dynamic) == fixed_ip
        if legacy.returncode and not collision:
            raise RuntimeError("Legacy isolated start failed for an unclassified reason")
        change("stop", [fixed, dynamic])
        for group in schedule:
            change("start", group)
        if {ident: address(ident) for ident in [fixed, dynamic]} != original:
            raise RuntimeError("Qualified order did not preserve isolated endpoints")

        # Add a static web with a dynamic dependency on this same allocator.
        # Its required API-first order is cyclic with its reservation constraint.
        node("api", str(subnet.network_address + 4))
        node("web", str(subnet.network_address + 5))
        before = {ident: owned(ident) for ident in nodes}
        config = {"services": {role: {"image": image} for role in roles}}
        config_path = directory / "isolated-compose.json"
        config_path.write_text(json.dumps(config))
        compose = backup.compose_command(project, [config_path], "/dev/null")
        discovered = run([*compose, "--profile", "*", "ps", "--quiet", "--status", "running"]).stdout.split()
        if set(discovered) != set(nodes):
            raise RuntimeError("The isolated CLI did not discover its complete test set")
        command = [sys.executable, str(ROOT / "deploy/manage_backup.py"), "backup", "--preflight-only",
                   "--project-name", project, "--compose-file", str(config_path), "--env-file", "/dev/null"]
        check = run(command, check=False)
        if check.returncode != 1 or "Unsafe restart plan:" not in check.stderr or check.stdout.strip():
            raise RuntimeError("Cyclic isolated topology was not blocked by the read-only CLI")
        if before != {ident: owned(ident) for ident in nodes}:
            raise RuntimeError("Read-only preflight changed an isolated container")
        if not all(value["running"] for value in before.values()):
            raise RuntimeError("The blocked drill did not retain every running container")
        # Avoid claiming that metadata checks qualify data-service recovery.
        return {"schema": "backup-restart-native-drill-v1", "legacy_collision_observed": collision,
                "static_before_dynamic_verified": True, "exact_isolated_addresses_preserved": True,
                "cyclic_CLI_preflight_blocked_without_downtime": True, "isolated_containers": len(nodes),
                "host_ports": 0, "private_mounts": 0, "external_networks": 0,
                "application_project_mutations": 0, "backup_or_restore_executed": False,
                "real_data_service_recovery_qualified": False, "cleanup_verified": False}
    finally:
        for ident in reversed(nodes):
            owned(ident, check_posture=False)
            run(["docker", "rm", "--force", ident])
        if network is not None:
            net = inspect_network(network)
            if net["labels"].get(OWNER) != token or net["containers"]:
                raise RuntimeError("Cannot safely remove the isolated network")
            run(["docker", "network", "rm", network])
        if (run(["docker", "ps", "--all", "--quiet", "--filter", "label=" + OWNER + "=" + token]).stdout.strip()
                or run(["docker", "network", "ls", "--quiet", "--filter", "label=" + OWNER + "=" + token]).stdout.strip()):
            raise RuntimeError("Isolated cleanup could not be verified")


def main():
    import tempfile

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Trusted immutable cached Python image ID")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.report.exists():
        raise SystemExit("Refusing to overwrite an existing drill receipt")
    try:
        with tempfile.TemporaryDirectory(prefix="la-restart-drill-") as temp:
            result = drill(args.image, Path(temp))
        result["cleanup_verified"] = True
        with args.report.open("x") as report:
            json.dump(result, report, indent=2)
            report.write("\n")
        print(json.dumps(result))
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        frame = traceback.extract_tb(error.__traceback__)[-1]
        # No exception message, command, address, environment or key is retained.
        failure = {"schema": "backup-restart-native-drill-failure-v1", "qualified": False,
                   "error_type": type(error).__name__, "source_line": frame.lineno,
                   "application_project_mutations": 0, "cleanup_qualified": False}
        diagnostic = args.report.with_suffix(".failure.json")
        if not diagnostic.exists():
            with diagnostic.open("x") as report:
                json.dump(failure, report, indent=2)
                report.write("\n")
        raise SystemExit(f"Isolated restart drill failed at source line {frame.lineno}; "
                         "no application-project mutation was requested.") from None


if __name__ == "__main__":
    main()
