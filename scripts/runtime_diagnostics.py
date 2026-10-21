#!/usr/bin/env python3
"""Allowlisted runtime posture; never print inspect/configuration/error payloads."""

import argparse
import json
import re
import subprocess
import sys

ROLES = {"api", "extractor", "postgres", "web", "scanner", "fuseki", "opensearch", "provider-relay", "gateway"}
SECRET_NAMES = {"LA_DATABASE_URL", "LA_ENCRYPTION_KEY", "LA_BOOTSTRAP_PASSWORD", "LA_GRAPH_PASSWORD",
                "LA_EXTRACTION_TOKEN", "LA_GATEWAY_TOKEN", "LLM_PROVIDER_API_KEY", "POSTGRES_PASSWORD"}


def safe_projection(containers):
    result = []
    for container in containers:
        role = container["Config"]["Labels"]["com.docker.compose.service"]
        if role not in ROLES:
            raise ValueError("Unsupported service")
        env = dict(item.split("=", 1) for item in container["Config"].get("Env", []))
        health = container["State"].get("Health", {}).get("Status", "unknown")
        result.append({"service": role, "running": container["State"]["Running"] is True,
                       "health": health if health in {"healthy", "unhealthy", "starting"} else "unknown",
                       "literal_secret_environment_present": any(env.get(k) for k in SECRET_NAMES),
                       "mounted_secret_settings": sum(bool(env.get(k + "_FILE")) for k in SECRET_NAMES),
                       "read_only_root": container["HostConfig"].get("ReadonlyRootfs") is True})
    if len(result) != len({r["service"] for r in result}):
        raise ValueError("Ambiguous service")
    return {"schema": "runtime-posture-v1", "services": sorted(result, key=lambda r: r["service"])}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid runtime diagnostic arguments; use --help.\n")


def main():
    parser = Parser(description=__doc__)
    parser.add_argument("--project", default="lawyer-assistant-v1")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", args.project):
        raise ValueError("Invalid project")
    ids = subprocess.run(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + args.project],
                         capture_output=True, text=True, check=True, timeout=20).stdout.split()
    if not ids or len(ids) > 16:
        raise ValueError("Unsupported inventory")
    raw = subprocess.run(["docker", "inspect", *ids], capture_output=True, check=True, timeout=20).stdout
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError("Oversized inventory")
    print(json.dumps(safe_projection(json.loads(raw)), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        sys.exit("Runtime diagnostics unavailable; no raw diagnostic output emitted.")
