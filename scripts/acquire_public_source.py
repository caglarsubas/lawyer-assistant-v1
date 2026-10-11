#!/usr/bin/env python3
"""Acquire one registered public HTML source in an isolated, disposable staging container."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.source_gateway import (  # noqa: E402
    MAX_BYTES,
    REGISTRY,
    REGISTRY_VERSION,
    WORKER_ERROR_CODES,
    AcquisitionError,
    registered,
    rename_new,
    validate_acquisition_metadata,
)

IMAGE = "lawyer-assistant-public-acquisition:0.1.0"


def _run(command, *, timeout=15):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        raise AcquisitionError("Disposable staging process could not complete") from None
    if result.returncode:
        try:
            diagnostic = json.loads(result.stderr)
        except (TypeError, ValueError):
            diagnostic = None
        if (isinstance(diagnostic, dict) and set(diagnostic) == {"error"}
                and isinstance(diagnostic["error"], str) and diagnostic["error"] in WORKER_ERROR_CODES):
            raise AcquisitionError("Registered source acquisition failed: " + diagnostic["error"])
        raise AcquisitionError("Disposable staging process was rejected")
    return result.stdout


def _command(source_id, directory, name, image):
    command = [
        "docker", "run", "--rm", "--name", name, "--pull", "never", "--network", "bridge",
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
        "--user", f"{os.getuid() or 10001}:{os.getgid() or 10001}", "--memory", "128m",
        "--memory-swap", "128m", "--cpus", "1", "--pids-limit", "32", "--log-driver", "none",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m", "--mount",
        f"type=bind,src={directory},dst=/staging", "--entrypoint", "/usr/bin/env",
    ]
    # Docker client proxy defaults are explicitly cleared, including credentials
    # they could contain. env -i also removes all image environment at exec.
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        command.extend(["--env", f"{key}="])
    return command + [image, "-i", "PATH=/app/backend/.venv/bin:/usr/bin:/bin",
                      "PYTHONDONTWRITEBYTECODE=1", "PYTHONUNBUFFERED=1",
                      "/app/backend/.venv/bin/python", "-m", "app.source_gateway", source_id,
                      "/staging/acquired", "--connected-staging"]


def _validate_package(source_id, directory):
    registered(source_id)
    if directory.is_symlink() or not directory.is_dir():
        raise AcquisitionError("Staged output is missing")
    if {item.name for item in directory.iterdir()} != {"raw.html", "acquisition.json"}:
        raise AcquisitionError("Staged output has unexpected artifacts")
    for name, limit in (("raw.html", MAX_BYTES), ("acquisition.json", 64 * 1024)):
        path = directory / name
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
            raise AcquisitionError("Staged artifact is invalid")
    raw = (directory / "raw.html").read_bytes()
    try:
        manifest = json.loads((directory / "acquisition.json").read_text())
    except (ValueError, UnicodeError):
        raise AcquisitionError("Staged manifest is invalid") from None
    if not isinstance(manifest, dict) or manifest.get("registry_id") != source_id:
        raise AcquisitionError("Staged provenance does not match the registered acquisition")
    try:
        return validate_acquisition_metadata(raw, manifest, required_registry_version=REGISTRY_VERSION)
    except AcquisitionError:
        raise AcquisitionError("Staged provenance does not match the registered acquisition") from None


def _cleanup(name):
    try:
        _run(["docker", "rm", "--force", name])
    except AcquisitionError:
        # An auto-removed successful worker is already absent. Confirm that with
        # a successful listing rather than treating arbitrary Docker errors as OK.
        deadline = time.monotonic() + 3
        while _run(["docker", "container", "ls", "--all", "--quiet", "--filter", f"name=^{name}$"]).strip():
            if time.monotonic() >= deadline:
                raise AcquisitionError("Disposable staging cleanup could not be confirmed") from None
            time.sleep(0.1)


def acquire_in_container(source_id, destination, *, connected_staging=False):
    registered(source_id)
    if connected_staging is not True:
        raise AcquisitionError("Explicit connected staging opt-in is required")
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise AcquisitionError("Output must be a new directory under an existing parent")
    image = _run(["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE]).strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise AcquisitionError("An existing immutable local acquisition image is required")
    with tempfile.TemporaryDirectory(prefix=".registered-staging-", dir=destination.parent) as temporary:
        directory = Path(temporary)
        # Only a newly created, empty public staging directory enters the worker.
        # No workspace, .env, Docker socket, application volume or secret is mounted.
        if os.getuid() == 0:
            directory.chmod(0o777)
        name = "lawyer-public-staging-" + uuid.uuid4().hex
        try:
            _run(_command(source_id, directory, name, image), timeout=45)
        finally:
            # --rm handles normal completion; force removal also covers a timed-out
            # Docker client, which by itself does not terminate its container.
            _cleanup(name)
        staged = directory / "acquired"
        manifest = _validate_package(source_id, staged)
        rename_new(staged, destination)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("source_id", choices=tuple(REGISTRY))
    parser.add_argument("output", type=Path)
    parser.add_argument("--connected-staging", action="store_true", required=True)
    args = parser.parse_args()
    try:
        manifest = acquire_in_container(args.source_id, args.output, connected_staging=args.connected_staging)
    except AcquisitionError as error:
        parser.exit(1, f"Registered acquisition stopped: {error}.\n")
    except OSError:
        parser.exit(1, "Registered acquisition stopped: local filesystem operation failed.\n")
    print(json.dumps({"status": "quarantined", "registry_id": manifest["registry_id"],
                      "raw_sha256": manifest["raw_sha256"], "byte_count": manifest["byte_count"],
                      "current_consolidation": False}))


if __name__ == "__main__":
    main()
