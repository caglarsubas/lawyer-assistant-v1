"""Operator CLI: stop a stack for an encrypted cold backup, or restore a fresh one."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("api", "postgres", "opensearch", "fuseki")
COMPOSE = ["docker", "compose", "--project-directory", str(ROOT), "-f", str(ROOT / "compose.yaml")]


def run(command: list[str], *, capture: bool = True, timeout: int = 120) -> str:
    # Never print resolved Compose configuration or container environment values.
    result = subprocess.run(command, check=True, text=True, capture_output=capture, timeout=timeout)
    return result.stdout.strip() if capture else ""


def inventory() -> tuple[dict[str, str], dict[str, str]]:
    containers = {}
    images = {}
    for service in SERVICES:
        found = run([*COMPOSE, "ps", "--all", "--quiet", service]).splitlines()
        if len(found) != 1:
            raise ValueError(f"Exactly one existing {service} container is required")
        containers[service] = found[0]
        images[service] = run(["docker", "inspect", "--format", "{{.Image}}", found[0]])
    return containers, images


def helper(containers: dict, images: dict, action: str, key_file: Path, archive: Path) -> list[str]:
    command = ["docker", "run", "--rm", "--network", "none", "--read-only", "--user", "0:0",
               "--security-opt", "no-new-privileges:true", "--cap-drop", "ALL",
               "--cap-add", "DAC_OVERRIDE", "--tmpfs", "/tmp:size=64m,mode=1777",
               "--env", "LA_ARCHIVE_IMAGES=" + json.dumps(images, sort_keys=True)]
    if action == "restore":
        command += ["--cap-add", "CHOWN", "--cap-add", "FOWNER"]
    for container in containers.values():
        command += ["--volumes-from", f"{container}:{'ro' if action == 'backup' else 'rw'}"]
    key_target = "backup-recipients" if action == "backup" else "backup-identity"
    command += ["--mount", f"type=bind,src={key_file},dst=/run/secrets/{key_target},readonly"]
    if action == "restore":
        command += ["--mount", f"type=bind,src={archive},dst=/backup/archive.age,readonly"]
    command += ["--entrypoint", "python", images["api"], "/app/deploy/volume_archive.py", action]
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("archive", type=Path)
    parser.add_argument("--recipients-file", type=Path)
    parser.add_argument("--identity-file", type=Path)
    parser.add_argument("--stop-services", action="store_true", help="Acknowledge backup downtime")
    parser.add_argument("--fresh-target", action="store_true", help="Restore only into new empty volumes")
    args = parser.parse_args()
    original_running = []
    partial = None
    try:
        archive = args.archive.expanduser().resolve()
        key_file = args.recipients_file if args.action == "backup" else args.identity_file
        if key_file is None or not key_file.expanduser().is_file():
            raise ValueError("Supply an existing age recipients/identity file; no keys are generated")
        key_file = key_file.expanduser().resolve()
        if "," in str(key_file) or "," in str(archive):
            raise ValueError("Docker bind mount paths cannot contain commas")
        if args.action == "backup" and not args.stop_services:
            raise ValueError("Cold backup needs --stop-services and causes temporary downtime")
        if args.action == "restore" and (not args.fresh_target or not archive.is_file()):
            raise ValueError("Restore needs an existing archive and --fresh-target")
        containers, images = inventory()
        if args.action == "backup":
            if archive.exists():
                raise ValueError("Refusing to overwrite an existing backup")
            archive.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            candidate_partial = archive.with_name(archive.name + ".partial")
            # Exclusive creation prevents accidental replacement of a prior partial backup.
            fd = os.open(candidate_partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            partial = candidate_partial
            with os.fdopen(fd, "wb") as output:
                original_running = run([*COMPOSE, "--profile", "research", "--profile", "native-provider", "ps", "--quiet",
                                        "--status", "running"]).splitlines()
                if original_running:
                    run(["docker", "stop", "--time", "60", *original_running])
                # Stop offline publishers too; the five volumes form one cold point.
                result = subprocess.run(helper(containers, images, "backup", key_file, archive),
                                        stdout=output, timeout=7200, check=False)
                if result.returncode:
                    raise RuntimeError("Encrypted backup helper failed")
                output.flush()
                os.fsync(output.fileno())
            os.link(partial, archive)  # Fail if another operator created the destination.
            partial.unlink()
            partial = None
            print(f"Encrypted cold backup saved: {archive}")
        else:
            running = run([*COMPOSE, "--profile", "research", "--profile", "native-provider", "ps", "--quiet", "--status", "running"])
            if running:
                raise ValueError("Restore target must be stopped; this command never stops a live target")
            subprocess.run(helper(containers, images, "restore", key_file, archive),
                           check=True, timeout=7200)
            print("Restored into empty volumes. Services remain stopped. Verify keys before starting.")
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        # subprocess exceptions include argv; never include the helper command or any environment.
        detail = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
        print(f"Backup operation failed: {detail}", file=sys.stderr)
        return 1
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)
        if original_running:
            try:
                run(["docker", "start", *original_running])
            except subprocess.SubprocessError:
                print("Previously running containers need manual restart; do not assume recovery.", file=sys.stderr)
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
