#!/usr/bin/env python3
"""Explicit public update staging or fully offline, verified signature-package import."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "lawyer-assistant-scanner:1.4.6"
FILES = ("main.cvd", "daily.cvd", "bytecode.cvd")


def run(arguments, *, timeout=300):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError("Signature staging or verification failed; no package was published")
    return result.stdout


def publish(source, destination, image, days):
    source, destination = Path(source).resolve(), Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination must be a new directory; never overwrite a mounted signature release")
    if not source.is_dir() or any((source / name).is_symlink() or not (source / name).is_file()
                                  for name in FILES):
        raise ValueError("Source must contain three regular official CVD files")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".signatures-", dir=destination.parent) as temporary:
        staged = Path(temporary)
        staged.chmod(0o755)
        for name in FILES:
            if (source / name).stat().st_size > 300 * 1024 * 1024:
                raise ValueError("Signature file exceeds the admitted limit")
            shutil.copyfile(source / name, staged / name)
            (staged / name).chmod(0o644)
        output = run([
            "docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--memory", "3g", "--pids-limit", "64",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m", "--mount",
            f"type=bind,src={staged},dst=/approved,readonly",
            "--env", f"LA_SCANNER_MAX_SIGNATURE_AGE_DAYS={days}", image, "verify", "/approved",
        ])
        manifest = json.loads(output)
        manifest.update({"image": image, "maximum_daily_age_days": days,
                         "admission": "official CVD signatures verified in a disconnected container"})
        (staged / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (staged / "manifest.json").chmod(0o644)
        # Atomic publication to a new path. Recreate the scanner to mount this release.
        os.rename(staged, destination)
    return manifest


def fetch(destination, image, days):
    # This one-shot update container is outside all application networks. It receives no
    # application environment, secrets, documents or Docker socket.
    with tempfile.TemporaryDirectory(prefix="lawyer-signature-download-") as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        incoming = root / "incoming"
        incoming.mkdir(mode=0o777)
        incoming.chmod(0o777)
        config = root / "freshclam.conf"
        config.write_text(
            "DatabaseDirectory /staging\nDatabaseOwner clamav\nDatabaseMirror database.clamav.net\n"
            "DNSDatabaseInfo current.cvd.clamav.net\nScriptedUpdates no\nBytecode yes\n"
            "TestDatabases yes\nConnectTimeout 20\nReceiveTimeout 60\nMaxAttempts 2\n"
        )
        config.chmod(0o644)
        run([
            "docker", "run", "--rm", "--user", "1000:1000", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--memory", "3g", "--pids-limit", "64",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m", "--mount",
            f"type=bind,src={incoming},dst=/staging", "--mount",
            f"type=bind,src={config},dst=/etc/clamav/staging.conf,readonly", "--entrypoint", "freshclam",
            image, "--config-file=/etc/clamav/staging.conf", "--stdout", "--foreground",
        ], timeout=600)
        return publish(incoming, destination, image, days)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("fetch", "import"))
    parser.add_argument("--source", type=Path, help="Offline package directory containing official CVD files")
    parser.add_argument("--destination", type=Path, default=ROOT / ".data/clamav-signatures")
    parser.add_argument("--image", default=IMAGE, help="Locally built, evaluated scanner image")
    parser.add_argument("--max-age-days", type=int, default=7, choices=range(1, 15))
    args = parser.parse_args()
    try:
        if args.operation == "fetch":
            manifest = fetch(args.destination, args.image, args.max_age_days)
        elif args.source:
            manifest = publish(args.source, args.destination, args.image, args.max_age_days)
        else:
            parser.error("import requires --source")
        print(json.dumps({"status": "verified", "destination": str(args.destination),
                          "databases": manifest["databases"]}, indent=2))
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Signature provisioning stopped: {error}\n")


if __name__ == "__main__":
    main()
