"""Offline signature admission and daemon startup. No downloader exists in this control path."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from scanner import probe_scanner

REQUIRED = ("main.cvd", "daily.cvd", "bytecode.cvd")


def age_limit():
    days = int(os.environ.get("LA_SCANNER_MAX_SIGNATURE_AGE_DAYS", "7"))
    if not 1 <= days <= 14:
        raise ValueError("Signature age policy must be between one and fourteen days")
    return days


def verify(directory):
    """Verify cryptographic signatures, count and date from signed CVD containers."""
    directory = Path(directory)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("An approved signature directory is required")
    if {entry.name for entry in directory.iterdir()} - {*REQUIRED, "manifest.json"}:
        raise ValueError("Only the three official CVD databases and manifest are admitted")
    records = []
    for name in REQUIRED:
        path = directory / name
        if path.is_symlink() or not path.is_file() or not 512 < path.stat().st_size <= 300 * 1024 * 1024:
            raise ValueError("A required official CVD database is absent or invalid")
        with path.open("rb") as source:
            fields = source.read(512).decode("ascii").strip().split(":")
        if (len(fields) != 9 or fields[0] != "ClamAV-VDB" or int(fields[3]) <= 0
                or int(fields[2]) <= 0):
            raise ValueError("CVD header or signature count is invalid")
        timestamp = int(fields[8])
        if timestamp > time.time() + 300:
            raise ValueError("CVD signature build time is in the future")
        if name == "daily.cvd" and time.time() - timestamp > age_limit() * 86400:
            raise ValueError("Daily signatures exceed the admitted age policy")
        result = subprocess.run(["sigtool", "--info", str(path)], capture_output=True, timeout=120, check=False)
        if result.returncode != 0 or b"Verification OK." not in result.stdout:
            raise ValueError("Official CVD cryptographic verification failed")
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        records.append({"file": name, "sha256": digest, "bytes": path.stat().st_size,
                        "version": int(fields[2]), "signatures": int(fields[3]),
                        "build_time": timestamp})
    return {"schema_version": 1, "engine": "ClamAV 1.4.6", "databases": records}


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "start"
    try:
        if command == "health":
            status = probe_scanner("127.0.0.1", timeout_seconds=3,
                                   max_signature_age_days=age_limit())
            if status["status"] != "ready":
                raise ValueError("Scanner unavailable or signatures outside policy")
        elif command == "verify" and len(sys.argv) == 3:
            print(json.dumps(verify(sys.argv[2]), indent=2))
        elif command == "start":
            verify("/var/lib/clamav")
            os.execv("/usr/sbin/clamd", ["clamd", "--config-file=/etc/clamav/clamd.conf"])
        else:
            raise ValueError("Unsupported scanner control operation")
    except (OSError, ValueError, subprocess.SubprocessError, UnicodeError):
        print("Scanner unavailable: verify approved databases, signature age and configuration.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
