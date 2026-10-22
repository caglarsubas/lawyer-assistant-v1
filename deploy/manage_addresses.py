"""Freeze existing Docker endpoints at their current addresses, without recreation.

Plan first; apply only a separately inspected, hash-bound owner-only plan during
exclusive Docker maintenance. No images, volumes, secrets or subnets are changed.
An interrupted operation stays stopped and can resume toward the same pinned plan;
it never guesses a dynamic rollback order.
"""

import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from restart_preflight import MAX_CONTAINERS, MAX_METADATA_BYTES, ROLES, _unique, plan_restarts

SCHEMA = "existing-address-plan-v1"
IDENT = re.compile(r"[0-9a-f]{64}")
NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}")


def run(argv, timeout=120):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError("Address maintenance command failed; inspect the private checkpoint")
    return result.stdout.strip()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def private_write(path, value):
    """Never overwrite a plan; atomically checkpoint through an exclusive sibling."""
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def checkpoint(path, value):
    temp = path.with_suffix(".next")
    private_write(temp, value)
    os.replace(temp, path)


def capture(project):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", project):
        raise ValueError("Invalid maintenance project")
    ids = run(["docker", "ps", "--all", "--quiet", "--no-trunc", "--filter",
               "label=com.docker.compose.project=" + project]).splitlines()
    if not ids or len(ids) > MAX_CONTAINERS or any(not IDENT.fullmatch(i) for i in ids):
        raise ValueError("Cannot verify bounded project ownership")
    result = []
    for ident in sorted(ids):
        raw = run(["docker", "inspect", "--format",
                   '{"id":{{json .Id}},"role":{{json (index .Config.Labels "com.docker.compose.service")}},'
                   '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
                   '"running":{{json .State.Running}},"networks":{{json .NetworkSettings.Networks}}}', ident])
        if len(raw.encode()) > MAX_METADATA_BYTES:
            raise ValueError("Endpoint metadata exceeds its bound")
        node = json.loads(raw, object_pairs_hook=_unique)
        # Configuration may contain credentials: hash in memory, never retain or
        # print it. Mount array ordering is not semantically significant.
        posture = json.loads(run(["docker", "inspect", "--format",
                                  '{"image":{{json .Image}},"config":{{json .Config}},'
                                  '"host":{{json .HostConfig}},"mounts":{{json .Mounts}}}', ident]))
        posture["mounts"].sort(key=lambda item: item["Destination"])
        node["posture"] = digest(posture)
        result.append(node)
    return result


def networks_for(nodes):
    ids = sorted({e["NetworkID"] for n in nodes for e in n["networks"].values()})
    if not ids or len(ids) > 32 or any(not IDENT.fullmatch(i) for i in ids):
        raise ValueError("Cannot verify bounded network ownership")
    raw = run(["docker", "network", "inspect", "--format",
               '{"id":{{json .Id}},"name":{{json .Name}},"driver":{{json .Driver}},'
               '"internal":{{json .Internal}},"ipam":{{json .IPAM.Config}},'
               '"project":{{json (index .Labels "com.docker.compose.project")}},'
               '"key":{{json (index .Labels "com.docker.compose.network")}},'
               '"members":{{json .Containers}}}', *ids])
    if len(raw.encode()) > MAX_METADATA_BYTES:
        raise ValueError("Network metadata exceeds its bound")
    return [json.loads(line, object_pairs_hook=_unique) for line in raw.splitlines()]


def make_plan(project, nodes, networks):
    """Conservative IPv4-only bridge plan; unsupported topology is never guessed."""
    ids = [n["id"] for n in nodes]
    if (not ids or len(ids) > MAX_CONTAINERS or len(set(ids)) != len(ids)
            or any(not IDENT.fullmatch(i) for i in ids)
            or any(n["project"] != project or n["running"] is not True or n["role"] not in ROLES for n in nodes)
            or len({n["role"] for n in nodes}) != len(nodes)):
        raise ValueError("Maintenance requires unique, running, owned service containers")
    by_id = {n["id"]: n for n in networks}
    if (len(by_id) != len(networks) or not networks or len({n["key"] for n in networks}) != len(networks)
            or len({n["name"] for n in networks}) != len(networks)):
        raise ValueError("Ambiguous maintenance networks")
    endpoints, projected, reservations = [], [], set()
    for node in nodes:
        target = {k: node[k] for k in ("id", "role", "running")}
        target["networks"] = {}
        if not node["networks"] or len(node["networks"]) > 32:
            raise ValueError("Cannot verify service attachments")
        for name, e in sorted(node["networks"].items()):
            network = by_id.get(e["NetworkID"])
            if (not network or network["name"] != name or network["driver"] != "bridge"
                    or network["project"] != project or not NAME.fullmatch(network["key"] or "")
                    or set(network["members"] or {}) - set(ids)):
                raise ValueError("Maintenance requires exclusively owned bridge networks")
            ipam = e.get("IPAMConfig") or {}
            aliases = e.get("Aliases") or []
            if (e.get("GlobalIPv6Address") or e.get("IPv6Gateway") or e.get("Links") or e.get("DriverOpts")
                    or set(ipam) - {"IPv4Address", "IPv6Address", "LinkLocalIPs"}
                    or ipam.get("IPv6Address") or ipam.get("LinkLocalIPs")
                    or not isinstance(aliases, list) or len(aliases) > 32
                    or any(not isinstance(a, str) or not NAME.fullmatch(a) for a in aliases)
                    or type(e.get("GwPriority", 0)) is not int or e.get("GwPriority", 0) != 0):
                raise ValueError("Unsupported endpoint options; manual network review required")
            address = ipaddress.ip_address(e["IPAddress"])
            configs = network["ipam"]
            if (address.version != 4 or address.is_unspecified or address.is_multicast or address.is_loopback
                    or len(configs) != 1 or address not in ipaddress.ip_network(configs[0]["Subnet"])
                    or str(address) in {configs[0].get("Gateway"), str(ipaddress.ip_network(configs[0]["Subnet"]).network_address),
                                       str(ipaddress.ip_network(configs[0]["Subnet"]).broadcast_address)}
                    or ipam.get("IPv4Address", str(address)) != str(address)
                    or (network["id"], str(address)) in reservations):
                raise ValueError("Cannot establish unique existing endpoint addresses")
            reservations.add((network["id"], str(address)))
            endpoint = {"container": node["id"], "network": network["id"], "name": name,
                        "key": network["key"], "address": str(address), "aliases": sorted(set(aliases)),
                        "was_static": bool(ipam.get("IPv4Address")), "mac": e.get("MacAddress", "")}
            endpoints.append(endpoint)
            target["networks"][name] = {**e, "IPAMConfig": {"IPv4Address": str(address)}}
        projected.append(target)
    if set(by_id) != {e["network"] for e in endpoints}:
        raise ValueError("Maintenance network set differs from service attachments")
    groups = plan_restarts(ids, "\n".join(json.dumps(n) for n in projected))
    return {"schema": SCHEMA, "project": project, "nodes": nodes, "networks": networks,
            "endpoints": endpoints, "groups": groups}


def validate(plan):
    if (set(plan) != {"schema", "project", "nodes", "networks", "endpoints", "groups"}
            or plan["schema"] != SCHEMA or make_plan(plan["project"], plan["nodes"], plan["networks"]) != plan):
        raise ValueError("Maintenance plan is invalid")


def compose_lock(plan):
    """Per-host override only. Use with separately verified full configuration."""
    services = {n["role"]: {"networks": {}} for n in plan["nodes"]}
    roles = {n["id"]: n["role"] for n in plan["nodes"]}
    for e in plan["endpoints"]:
        services[roles[e["container"]]]["networks"][e["key"]] = {
            "ipv4_address": e["address"], "aliases": e["aliases"]}
    return {"services": services, "networks": {n["key"]: {"name": n["name"]} for n in plan["networks"]}}


def wait_healthy(group):
    deadline = time.monotonic() + 150
    while True:
        states = run(["docker", "inspect", "--format",
                      '{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}', *group]).splitlines()
        if len(states) == len(group) and all(s in {"true healthy", "true none"} for s in states):
            return
        if time.monotonic() >= deadline:
            raise ValueError("Startup health not qualified; retain the maintenance checkpoint")
        time.sleep(2)


def verify_resume_endpoints(plan, actual):
    """Accept only the original endpoint, its pinned successor, or a disconnect."""
    original = {n["id"]: n for n in plan["nodes"]}
    for node in actual:
        allowed = original[node["id"]]["networks"]
        if set(node["networks"]) - set(allowed):
            raise ValueError("Unexpected maintenance attachment")
        for name, endpoint in node["networks"].items():
            before = allowed[name]
            wanted = {"IPv4Address": before["IPAddress"]}
            if (endpoint["NetworkID"] != before["NetworkID"]
                    or set(endpoint.get("Aliases") or []) != set(before.get("Aliases") or [])
                    or endpoint.get("IPAMConfig") not in (before.get("IPAMConfig"), wanted)
                    or endpoint.get("IPAddress") not in ("", before["IPAddress"])
                    or any(endpoint.get(k) != before.get(k) for k in ("DriverOpts", "Links", "GwPriority"))
                    or endpoint.get("GlobalIPv6Address")):
                raise ValueError("Maintenance endpoint changed outside the reviewed plan")


def apply(plan, journal_path, *, resume=False):
    validate(plan)
    old = {n["id"]: n for n in plan["nodes"]}
    actual = capture(plan["project"])
    if not resume:
        if actual != plan["nodes"] or networks_for(actual) != plan["networks"]:
            raise ValueError("Maintenance snapshot changed; create a new plan")
        private_write(journal_path, {"plan_sha256": digest(plan), "phase": "stopping"})
    else:
        journal = json.loads(journal_path.read_text(), object_pairs_hook=_unique)
        if journal["plan_sha256"] != digest(plan) or journal["phase"] == "complete":
            raise ValueError("No incomplete maintenance checkpoint for this plan")
    if ({n["id"] for n in actual} != set(old)
            or any(n["posture"] != old[n["id"]]["posture"] for n in actual)):
        raise ValueError("Container identity or configuration changed; refusing maintenance")
    verify_resume_endpoints(plan, actual)
    # Stop consumers before their dependencies; respect existing graceful limits.
    # Resume also quiesces only this exact, already-authorized container set.
    for group in reversed(plan["groups"]):
        run(["docker", "stop", *group], timeout=600)
    stopped = capture(plan["project"])
    if any(n["running"] for n in stopped):
        raise ValueError("All authorized containers must be stopped")
    allowed = {n["id"]: {e["name"] for e in plan["endpoints"] if e["container"] == n["id"]} for n in stopped}
    if any(set(n["networks"]) - allowed[n["id"]] for n in stopped):
        raise ValueError("Unexpected network attachment; leave services stopped")
    # No external consumer may enter an owned network during the maintenance.
    for network in plan["networks"]:
        current = json.loads(run(["docker", "network", "inspect", "--format", "{{json .Containers}}", network["id"]])) or {}
        if set(current) - set(old):
            raise ValueError("Network ownership changed; leave services stopped")
    for e in plan["endpoints"]:
        checkpoint(journal_path, {"plan_sha256": digest(plan), "phase": "pinning", "endpoint": e})
        current = next(n for n in capture(plan["project"]) if n["id"] == e["container"])["networks"].get(e["name"])
        if current and (current.get("IPAMConfig") or {}).get("IPv4Address") == e["address"]:
            continue
        if current:
            run(["docker", "network", "disconnect", e["network"], e["container"]])
        args = ["docker", "network", "connect", "--ip", e["address"]]
        for alias in e["aliases"]:
            args += ["--alias", alias]
        run([*args, e["network"], e["container"]])
    checkpoint(journal_path, {"plan_sha256": digest(plan), "phase": "starting"})
    for group in plan["groups"]:
        run(["docker", "start", *group])
        wait_healthy(group)
    final = capture(plan["project"])
    if any(n["posture"] != old[n["id"]]["posture"] or not n["running"] for n in final):
        raise ValueError("Container posture verification failed")
    for e in plan["endpoints"]:
        actual = next(n for n in final if n["id"] == e["container"])["networks"][e["name"]]
        if (actual["IPAddress"] != e["address"] or (actual.get("IPAMConfig") or {}).get("IPv4Address") != e["address"]
                or set(actual.get("Aliases") or []) != set(e["aliases"])):
            raise ValueError("Endpoint preservation failed; inspect the private checkpoint")
    plan_restarts(list(old), "\n".join(json.dumps({k: n[k] for k in ("id", "role", "running", "networks")}) for n in final))
    checkpoint(journal_path, {"plan_sha256": digest(plan), "phase": "complete",
                              "same_containers_and_posture": True, "exact_addresses_and_aliases": True,
                              "restart_order_verified": True, "health_and_recovery_qualified": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "apply", "resume"])
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--stop-services", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.action == "plan":
            if args.expected_sha256 or args.stop_services:
                raise ValueError("Read-only planning accepts no apply options")
            nodes = capture(args.project_name)
            plan = make_plan(args.project_name, nodes, networks_for(nodes))
            private_write(args.plan, plan)
        else:
            if (not args.stop_services or not args.expected_sha256
                    or args.plan.is_symlink() or args.plan.stat().st_mode & 0o077
                    or args.plan.stat().st_size > MAX_METADATA_BYTES):
                raise ValueError("Apply requires a private bounded plan, hash and downtime acknowledgment")
            plan = json.loads(args.plan.read_text(), object_pairs_hook=_unique)
            if digest(plan) != args.expected_sha256 or plan["project"] != args.project_name:
                raise ValueError("Plan hash or project does not match")
            lock_path = args.plan.with_suffix(".maintenance-lock")
            # Serializes this plan's invocations. Other Docker operators must still
            # honor the documented exclusive maintenance window.
            descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "a") as mutex:
                fcntl.flock(mutex, fcntl.LOCK_EX | fcntl.LOCK_NB)
                apply(plan, args.plan.with_suffix(".journal.json"), resume=args.action == "resume")
            lock = args.plan.with_suffix(".compose-lock.json")
            if not lock.exists():
                private_write(lock, compose_lock(plan))
        print(json.dumps({"schema": SCHEMA, "plan_sha256": digest(plan), "services": len(plan["nodes"]),
                          "endpoints": len(plan["endpoints"]), "applied": args.action != "plan",
                          "health_and_recovery_qualified": False}))
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.SubprocessError):
        print("Address maintenance not qualified; inspect the private plan/checkpoint before proceeding.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
