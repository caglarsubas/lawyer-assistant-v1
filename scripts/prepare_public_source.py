#!/usr/bin/env python3
"""Scan and transcribe one registered acquisition in two disposable offline workers."""

import argparse
import json
import math
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

from app.public_sources import _json, _validate  # noqa: E402
from app.qualification_evidence import read_exact_directory  # noqa: E402
from app.registered_source_preparation import (  # noqa: E402
    ACQUISITION_FILES,
    ADAPTER_VERSION,
    PREPARATION_FILES,
    PreparationError,
    encode,
    sha,
    validate_acquisition,
)
from app.source_gateway import rename_new  # noqa: E402

IMAGE = "lawyer-assistant-public-preparation:0.1.0"
SCANNER_IMAGE = "lawyer-assistant-scanner:1.4.6"
PROXIES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
           "http_proxy", "https_proxy", "all_proxy", "no_proxy")
# Constant code, never user/source interpolation. Existing scanner admission is reused.
SCAN_CODE = '''
import hashlib, json, subprocess, sys, time
sys.path.insert(0, "/opt/scanner")
from control import verify
started = time.monotonic()
before = verify("/var/lib/clamav")
result = subprocess.run([
    "clamscan", "--database=/var/lib/clamav", "--official-db-only=yes",
    "--max-filesize=20M", "--max-scansize=100M", "--max-recursion=12", "--max-files=5000",
    "--max-scantime=0", "--alert-exceeds-max=yes", "--alert-encrypted=yes",
    "--alert-broken=yes", "--bytecode-unsigned=no", "--no-summary", "/input/raw.html"
], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
if result.returncode != 0 or verify("/var/lib/clamav") != before:
    sys.exit(1)
raw = open("/input/raw.html", "rb").read(1048577)
if not 0 < len(raw) <= 1048576:
    sys.exit(1)
print(json.dumps({"schema_version": "registered-source-scan-v1", "clean": True,
    "raw_sha256": hashlib.sha256(raw).hexdigest(), "databases": before,
    "elapsed_seconds": time.monotonic() - started}))
'''


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid preparation arguments; use --help.\n")


def run(command, *, timeout=15):
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        raise PreparationError("Offline worker could not complete") from None
    if result.returncode or len(result.stdout) > 64 * 1024:
        raise PreparationError("Offline worker rejected the operation")
    return result.stdout


def image_id(tag):
    value = run(["docker", "image", "inspect", "--format", "{{.Id}}", tag]).decode().strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise PreparationError("Existing immutable worker image required")
    return value


def worker_command(name, image, mounts, *, scanner=False):
    # No application networks, ports, credentials, socket or private volumes.
    command = ["docker", "run", "--rm", "--name", name, "--pull", "never", "--network", "none",
               "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
               "--user", f"{os.getuid() or 10001}:{os.getgid() or 10001}",
               "--memory", "3g" if scanner else "256m", "--memory-swap", "3g" if scanner else "256m",
               "--cpus", "1", "--pids-limit", "64" if scanner else "32", "--log-driver", "none",
               "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m", "--entrypoint", "/usr/bin/env"]
    for key in PROXIES:
        command += ["--env", key + "="]
    for source, target, readonly in mounts:
        command += ["--mount", f"type=bind,src={source},dst={target}" + (",readonly" if readonly else "")]
    command += [image, "-i", "PATH=/app/backend/.venv/bin:/usr/sbin:/usr/bin:/bin",
                "PYTHONDONTWRITEBYTECODE=1", "PYTHONUNBUFFERED=1", "LANG=C.UTF-8", "TZ=UTC", "LC_ALL=C"]
    if scanner:
        return command + ["LA_SCANNER_MAX_SIGNATURE_AGE_DAYS=7", "python3", "-c", SCAN_CODE]
    return command + ["/app/backend/.venv/bin/python", "-m", "app.registered_source_preparation",
                      "/input", "/output"]


def cleanup(name):
    try:
        run(["docker", "rm", "--force", name])
    except PreparationError:
        deadline = time.monotonic() + 3
        while run(["docker", "container", "ls", "--all", "--quiet", "--filter", f"name=^{name}$"]).strip():
            if time.monotonic() >= deadline:
                raise PreparationError("Offline worker cleanup could not be confirmed") from None
            time.sleep(0.1)


def execute(image, mounts, *, scanner=False):
    name = "lawyer-public-preparation-" + uuid.uuid4().hex
    try:
        return run(worker_command(name, image, mounts, scanner=scanner), timeout=180 if scanner else 45)
    finally:
        cleanup(name)


def safe_directory(path):
    path = Path(path).absolute()
    if (".." in path.parts or any(part.is_symlink() for part in (path, *path.parents))
            or not path.is_dir() or any("," in part or "\n" in part or "\r" in part for part in path.parts)):
        raise PreparationError("A regular dedicated directory is required")
    return path


def validate_scan(scan, digest):
    if (not isinstance(scan, dict) or set(scan) != {
            "schema_version", "clean", "raw_sha256", "databases", "elapsed_seconds"}
            or scan["schema_version"] != "registered-source-scan-v1" or scan["clean"] is not True
            or scan["raw_sha256"] != digest or type(scan["elapsed_seconds"]) not in (int, float)
            or not math.isfinite(scan["elapsed_seconds"]) or not 0 <= scan["elapsed_seconds"] <= 180):
        raise PreparationError("Scan receipt does not match the captured input")
    database = scan["databases"]
    if (not isinstance(database, dict) or set(database) != {"schema_version", "engine", "databases"}
            or type(database["schema_version"]) is not int or database["schema_version"] != 1
            or database["engine"] != "ClamAV 1.4.6" or not isinstance(database["databases"], list)
            or len(database["databases"]) != 3):
        raise PreparationError("Incomplete scanner signature receipt")
    names, now = set(), time.time()
    for record in database["databases"]:
        if (not isinstance(record, dict) or set(record) != {
                "file", "sha256", "bytes", "version", "signatures", "build_time"}
                or not isinstance(record["file"], str) or record["file"] in names
                or record["file"] not in {"main.cvd", "daily.cvd", "bytecode.cvd"}
                or not isinstance(record["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None
                or any(type(record[key]) is not int or record[key] <= 0 for key in (
                    "bytes", "version", "signatures", "build_time"))
                or not 512 < record["bytes"] <= 300 * 1024 * 1024 or record["build_time"] > now + 300
                or (record["file"] == "daily.cvd" and now - record["build_time"] > 7 * 86400)):
            raise PreparationError("Invalid or stale scanner signature receipt")
        names.add(record["file"])


def prepare_in_containers(acquisition, signatures, destination):
    acquisition, signatures = safe_directory(acquisition), safe_directory(signatures)
    destination = Path(destination).absolute()
    safe_directory(destination.parent)
    if (destination.exists() or destination.is_symlink() or ".." in destination.parts
            or any(char in destination.name for char in ",\n\r")):
        raise PreparationError("Output must be a new directory")
    # Capture original input with exact inventory/no-follow/regular-file/recapture checks.
    files = read_exact_directory(acquisition, ACQUISITION_FILES, sum(ACQUISITION_FILES.values()))
    manifest = validate_acquisition(files)
    for name in ("main.cvd", "daily.cvd", "bytecode.cvd"):
        path = signatures / name
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            raise PreparationError("Official scanner databases required")
    parser_image, scanner_image = image_id(IMAGE), image_id(SCANNER_IMAGE)
    with tempfile.TemporaryDirectory(prefix=".public-preparation-", dir=destination.parent) as temporary:
        root = Path(temporary)
        incoming, outgoing = root / "input", root / "output"
        incoming.mkdir(mode=0o700)
        outgoing.mkdir(mode=0o700)
        for name, raw in files.items():
            (incoming / name).write_bytes(raw)
            (incoming / name).chmod(0o400)
        if os.getuid() == 0:
            # Keep workers unprivileged when the operator is root. Change only
            # our disposable snapshot/output, never the acquisition or CVD release.
            for path in [incoming, outgoing, *incoming.iterdir()]:
                os.chown(path, 10001, os.getgid() or 10001)
        scan = _json(execute(scanner_image, [(incoming, "/input", True),
                      (signatures, "/var/lib/clamav", True)], scanner=True))
        validate_scan(scan, manifest["raw_sha256"])
        if read_exact_directory(incoming, ACQUISITION_FILES, sum(ACQUISITION_FILES.values())) != files:
            raise PreparationError("Captured source changed after scanning")
        execute(parser_image, [(incoming, "/input", True), (outgoing, "/output", False)])
        artifacts = read_exact_directory(outgoing, PREPARATION_FILES, sum(PREPARATION_FILES.values()))
        report = _json(artifacts["preparation.json"])
        if (not isinstance(report, dict)
                or artifacts["raw.bin"] != files["raw.html"] or artifacts["acquisition.json"] != files["acquisition.json"]
                or report.get("raw_sha256") != manifest["raw_sha256"]
                or report.get("text_sha256") != sha(artifacts["text.txt"])
                or report.get("adapter_version") != ADAPTER_VERSION or report.get("current_consolidation") is not False
                or report.get("extraction_fidelity_verified") is not False
                or report.get("source_identity_verified") is not False or report.get("sensitivity_reviewed") is not False
                or report.get("rights_status") != "rights_pending" or report.get("review_status") != "legal_review_pending"):
            raise PreparationError("Prepared output does not match the captured source")
        metadata, locators, _ = _validate({name: artifacts[name] for name in (
            "raw.bin", "text.txt", "source.json", "locators.json")})
        if any(metadata[key] != manifest[key] for key in (
            "title", "source_url", "source_version_id", "acquired_at", "domain", "raw_media_type")):
            raise PreparationError("Prepared source metadata changed")
        if (any(metadata[key] is not None for key in ("published_on", "effective_from", "effective_until"))
                or type(report.get("passage_count")) is not int
                or report.get("passage_count") != len(locators.passages)
                or report.get("schema_version") != "registered-source-preparation-v1"
                or report.get("representation") != "enacted_text"
                or report.get("publication_status") != "prepared_for_staging"):
            raise PreparationError("Prepared review states or counts changed")
        if read_exact_directory(acquisition, ACQUISITION_FILES, sum(ACQUISITION_FILES.values())) != files:
            raise PreparationError("Original acquisition changed during preparation")
        admission = {"schema_version": "registered-source-admission-v1", "registry_id": manifest["registry_id"],
                     "raw_sha256": manifest["raw_sha256"], "parser_image_id": parser_image,
                     "scanner_image_id": scanner_image, "scan": scan,
                     "artifact_sha256": {name: sha(raw) for name, raw in artifacts.items()},
                     "network": "none", "signature_max_age_days": 7,
                     "rights_approved": False, "legal_approved": False, "published": False}
        (outgoing / "admission.json").write_bytes(encode(admission))
        for path in outgoing.iterdir():
            path.chmod(0o400)
        rename_new(outgoing, destination)
    return {"status": "prepared_for_staging", "registry_id": manifest["registry_id"],
            "raw_sha256": manifest["raw_sha256"], "passage_count": len(locators.passages),
            "current_consolidation": False, "rights_approved": False, "legal_approved": False}


def main(argv=None):
    cli = SafeParser(description=__doc__, allow_abbrev=False)
    cli.add_argument("acquisition", type=Path)
    cli.add_argument("output", type=Path)
    cli.add_argument("--signatures", required=True, type=Path)
    args = cli.parse_args(argv)
    try:
        result = prepare_in_containers(args.acquisition, args.signatures, args.output)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        cli.exit(1, "Public preparation stopped: admission, integrity or offline worker failure.\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
