#!/usr/bin/env python3
"""Collect allowlisted status observations from the local deployment."""

import argparse
import hashlib
import http.client
import json
import os
import re
import selectors
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

if __package__:
    from .runtime_diagnostics import ROLES, SECRET_NAMES
else:
    from runtime_diagnostics import ROLES, SECRET_NAMES

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (("web", "/", 200), ("health", "/api/v1/health", 200),
          ("anonymous_readiness", "/api/v1/readiness", 401),
          ("anonymous_matters", "/api/v1/matters", 401))
POSTURE_FIELDS = {"service", "running", "health", "literal_secret_environment_present",
                  "mounted_secret_settings", "read_only_root"}
DEFAULT_OUTPUT_LIMIT = 128 * 1024
GIT_BLOB_LIMIT = 4 * 1024 * 1024


def command(argv, *, stdin=None, timeout=12, limit=DEFAULT_OUTPUT_LIMIT, env=None):
    deadline = time.monotonic() + timeout
    with tempfile.TemporaryFile() as input_file:
        if stdin is not None:
            input_file.write(stdin)
            input_file.seek(0)
        process = subprocess.Popen(
            argv, stdin=input_file if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
        )
        try:
            output = bytearray()
            with selectors.DefaultSelector() as ready:
                ready.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not ready.select(remaining):
                        raise subprocess.TimeoutExpired(argv, timeout)
                    chunk = os.read(process.stdout.fileno(), min(65536, limit + 1 - len(output)))
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > limit:
                        raise ValueError("Observation exceeds output budget")
            code = process.wait(timeout=max(0, deadline - time.monotonic()))
            if code:
                raise subprocess.CalledProcessError(code, argv)
            return bytes(output)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)
            process.stdout.close()


def local_route(port, path):
    """Request a status code over fixed loopback without sending credentials."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("GET", path)
        return connection.getresponse().status
    except (OSError, http.client.HTTPException):
        return None
    finally:
        connection.close()


def docker_environment(ambient=None):
    env = dict(os.environ if ambient is None else ambient)
    context = env.pop("DOCKER_CONTEXT", "")
    endpoint = env.pop("DOCKER_HOST", "")
    if context or not endpoint:
        # Docker gives DOCKER_CONTEXT precedence over DOCKER_HOST.
        argv = ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]
        if context:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", context):
                return None
            argv.extend(["--", context])
        endpoint = command(argv, env=env, timeout=4, limit=4096).decode("utf-8").strip()
    url = urlsplit(endpoint)
    if (not endpoint.startswith("unix:///") or url.scheme != "unix" or url.netloc or url.query or url.fragment
            or not url.path.startswith("/") or any(ord(char) < 32 for char in endpoint)
            or not Path(url.path).is_socket()):
        return None
    # A fixed Unix socket keeps every Docker command, including the posture
    # helper, on the same host as the loopback routes.
    return {**env, "DOCKER_HOST": endpoint}


def service_id(project, service, env):
    ids = command(["docker", "ps", "-q", "--filter", f"label=com.docker.compose.project={project}",
                   "--filter", f"label=com.docker.compose.service={service}"],
                  env=env, timeout=5, limit=4096).decode("ascii").split()
    if len(ids) != 1 or not re.fullmatch(r"[a-f0-9]{12,64}", ids[0]):
        return None
    return ids[0]


def pinned_source(commit):
    paths = command(["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", commit, "--", "backend/app"],
                    timeout=5).decode("ascii").splitlines()
    paths = [path for path in paths if path.endswith(".py")]
    if not paths or len(paths) > 512 or any(not re.fullmatch(r"backend/app/[a-zA-Z0-9_/]+\.py", p) for p in paths):
        raise ValueError("Unexpected application source inventory")
    requests = "".join(f"{commit}:{path}\n" for path in paths).encode("ascii")
    raw = command(["git", "-C", str(ROOT), "cat-file", "--batch"], stdin=requests,
                  timeout=6, limit=GIT_BLOB_LIMIT)
    cursor, hashes = 0, {}
    for path in paths:
        header_end = raw.find(b"\n", cursor)
        header = re.fullmatch(rb"[a-f0-9]{40,64} blob ([0-9]+)", raw[cursor:header_end])
        if header_end < 0 or header is None:
            raise ValueError("Invalid commit blob response")
        start = header_end + 1
        end = start + int(header[1])
        if raw[end:end + 1] != b"\n":
            raise ValueError("Incomplete commit blob response")
        hashes[path] = hashlib.sha256(raw[start:end]).hexdigest()
        cursor = end + 1
    if cursor != len(raw):
        raise ValueError("Unexpected commit blob response")
    return hashes


def code_identity(project, commit, env):
    api = service_id(project, "api", env)
    if api is None:
        return {"status": "unavailable"}
    hashes = pinned_source(commit)
    code = """import hashlib, json, sys
from pathlib import Path

root = Path('/app')
result = {}
for name in json.load(sys.stdin):
    path = root / name
    result[name] = None
    if path.resolve() == path and path.is_file():
        with path.open('rb') as handle:
            content = handle.read(1024 * 1024 + 1)
        if len(content) <= 1024 * 1024:
            result[name] = hashlib.sha256(content).hexdigest()
print(json.dumps(result))
"""
    remote = json.loads(command(["docker", "exec", "-i", api, "python", "-c", code],
                                stdin=json.dumps(list(hashes)).encode("ascii"), env=env, timeout=10))
    if (not isinstance(remote, dict) or set(remote) != set(hashes)
            or any(value is not None and (not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value))
                   for value in remote.values())):
        raise ValueError("Invalid application source observation")
    different = [path for path, expected in hashes.items() if remote[path] != expected]
    return {"status": "matches" if not different else "differs", "compared_files": len(hashes),
            "matching_files": len(hashes) - len(different), "different_or_absent_files": different,
            "scope": "backend Python source blobs in the reported commit"}


def deployment_posture(project, env):
    raw = command([sys.executable, str(ROOT / "scripts/runtime_diagnostics.py"), "--project", project],
                  env=env, timeout=16)
    posture = json.loads(raw)
    if (not isinstance(posture, dict) or set(posture) != {"schema", "services"}
            or posture["schema"] != "runtime-posture-v1" or not isinstance(posture["services"], list)
            or not 1 <= len(posture["services"]) <= len(ROLES)):
        raise ValueError("Invalid runtime posture")
    seen = set()
    for row in posture["services"]:
        if (not isinstance(row, dict) or set(row) != POSTURE_FIELDS or row["service"] not in ROLES
                or row["service"] in seen or row["health"] not in {"healthy", "unhealthy", "starting", "unknown"}
                or type(row["mounted_secret_settings"]) is not int or not 0 <= row["mounted_secret_settings"] <= len(SECRET_NAMES)
                or any(type(row[key]) is not bool for key in ("running", "read_only_root",
                                                             "literal_secret_environment_present"))):
            raise ValueError("Invalid runtime posture")
        seen.add(row["service"])
    return posture


def scanner_readiness(project, env):
    scanner = service_id(project, "scanner", env)
    if scanner is None:
        return {"status": "unavailable"}
    code = ("import json,sys\nsys.path.insert(0,'/opt/scanner')\n"
            "from scanner import probe_scanner\nfrom control import age_limit\n"
            "r=probe_scanner('127.0.0.1',timeout_seconds=3,max_signature_age_days=age_limit())\n"
            "print(json.dumps({'status':r['status'],'issues':r['issues']}))\n")
    value = json.loads(command(["docker", "exec", scanner, "python3", "-c", code], env=env, timeout=7))
    if (not isinstance(value, dict) or set(value) != {"status", "issues"}
            or not isinstance(value["issues"], list) or len(value["issues"]) > 1
            or any(not isinstance(issue, dict) for issue in value["issues"])):
        raise ValueError("Invalid scanner observation")
    codes = [issue.get("code") for issue in value["issues"]]
    expected = {"ready": [], "blocked": ["scanner_not_ready"], "unavailable": ["scanner_unavailable"]}
    if value["status"] not in expected or codes != expected[value["status"]]:
        raise ValueError("Invalid scanner observation")
    return {"status": value["status"], "issue_codes": codes}


def safe_observation(operation, fallback):
    try:
        return operation()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return fallback


def observe(project="lawyer-assistant-v1", port=8081, *, compare_code=False):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", project) or type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Invalid observation target")
    commit = command(["git", "-C", str(ROOT), "rev-parse", "HEAD"], timeout=5, limit=256).decode("ascii").strip()
    if not re.fullmatch(r"[a-f0-9]{40,64}", commit):
        raise ValueError("Invalid commit identity")
    docker = safe_observation(docker_environment, None)
    posture = {"status": "unavailable", "services": []}
    scanner = {"status": "unavailable"}
    identity = {"status": "unavailable" if compare_code else "not_observed"}
    if docker is not None:
        posture = safe_observation(lambda: deployment_posture(project, docker), posture)
        scanner = safe_observation(lambda: scanner_readiness(project, docker), scanner)
        if compare_code:
            identity = safe_observation(lambda: code_identity(project, commit, docker), identity)
    routes = []
    for ident, path, expected in ROUTES:
        observed = local_route(port, path)
        routes.append({"id": ident, "expected_http": expected, "observed_http": observed,
                       "result": "pass" if observed == expected else "blocked" if observed is None else "fail"})
    return {"schema": "delivered-uat-runtime-v1", "observed_at": datetime.now(timezone.utc).isoformat(),
            "source_commit": commit, "local_docker_socket": docker is not None,
            "read_only": True, "authenticated_workflows": "not_observed", "legal_acceptance": "not_granted",
            "posture": posture, "routes": routes, "backend_source": identity, "scanner": scanner}


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, "Invalid runtime observation arguments. Use --help.\n")


def main():
    parser = Parser(description=__doc__)
    parser.add_argument("--project", default="lawyer-assistant-v1")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--compare-backend-code", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(observe(args.project, args.port, compare_code=args.compare_backend_code), indent=2))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        sys.exit("Read-only observation unavailable. No raw diagnostic output emitted.")


if __name__ == "__main__":
    main()
