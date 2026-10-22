"""Operator CLI: stop a stack for an encrypted cold backup, or restore a fresh one."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from restart_preflight import MAX_CONTAINERS, plan_restarts

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("api", "postgres", "opensearch", "fuseki")
COMPOSE = ["docker", "compose", "--project-directory", str(ROOT), "-f", str(ROOT / "compose.yaml")]
VOLUME_TARGETS = {"api": ("/data", "/public-sources"), "postgres": ("/var/lib/postgresql/data",),
                  "opensearch": ("/usr/share/opensearch/data",), "fuseki": ("/fuseki",)}


def compose_command(project_name=None, compose_files=(), env_file=None):
    """Allow an explicit isolated target without mutating ambient Compose settings."""
    command = ["docker", "compose", "--project-directory", str(ROOT)]
    if project_name is not None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", project_name):
            raise ValueError("Invalid Compose project name")
        command += ["--project-name", project_name]
    if env_file is not None:
        # /dev/null is useful for a fully specified, credential-free drill file.
        path = Path(env_file).expanduser().resolve(strict=True)
        command += ["--env-file", str(path)]
    for supplied in compose_files or (ROOT / "compose.yaml",):
        path = Path(supplied).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError("Compose configuration must be a file")
        command += ["-f", str(path)]
    return command


def run(command: list[str], *, capture: bool = True, timeout: int = 120) -> str:
    # Never print resolved Compose configuration or container environment values.
    result = subprocess.run(command, check=True, text=True, capture_output=capture, timeout=timeout)
    return result.stdout.strip() if capture else ""


def inventory(compose=COMPOSE) -> tuple[dict[str, str], dict[str, str]]:
    containers = {}
    images = {}
    for service in SERVICES:
        found = run([*compose, "ps", "--all", "--quiet", service]).splitlines()
        if len(found) != 1:
            raise ValueError(f"Exactly one existing {service} container is required")
        containers[service] = found[0]
        images[service] = run(["docker", "inspect", "--format", "{{.Image}}", found[0]])
    return containers, images


def restart_plan(container_ids: list[str]) -> list[list[str]]:
    """Check startup dependencies and every explicit shared-network endpoint."""
    if not container_ids:
        return []
    if len(container_ids) > MAX_CONTAINERS or len(set(container_ids)) != len(container_ids):
        raise ValueError("Running-container restart set contains duplicates")
    # Retrieve only allowlisted fields, never a raw inspect or environment dump.
    metadata = run(["docker", "inspect", "--format",
                    '{"id":{{json .Id}},"role":{{json (index .Config.Labels "com.docker.compose.service")}},'
                    '"running":{{json .State.Running}},"networks":{{json .NetworkSettings.Networks}}}',
                    *container_ids])
    return plan_restarts(container_ids, metadata)


def volume_mounts(containers: dict, *, writable: bool) -> list[str]:
    """Select exactly five named volumes, even when their service mounts are read-only.

    Docker's --volumes-from :rw preserves an inherited read-only mount. Explicit
    named mounts are necessary for restoring graphs/public sources. Unrelated
    host binds (including trust/configuration) must never enter the helper.
    """
    args, seen = [], set()
    for service, targets in VOLUME_TARGETS.items():
        mounts = json.loads(run(["docker", "inspect", "--format", "{{json .Mounts}}", containers[service]]))
        for target in targets:
            selected = [mount for mount in mounts if mount.get("Destination") == target]
            if len(selected) != 1 or selected[0].get("Type") != "volume":
                raise ValueError("Backup requires the five expected named volumes")
            name = selected[0].get("Name", "")
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name) or name in seen:
                raise ValueError("Backup requires five distinct named volumes")
            seen.add(name)
            args += ["--mount", f"type=volume,src={name},dst={target}" + ("" if writable else ",readonly")]
    return args


def helper(containers: dict, images: dict, action: str, key_file: Path, archive: Path) -> list[str]:
    command = ["docker", "run", "--rm", "--network", "none", "--read-only", "--user", "0:0",
               "--security-opt", "no-new-privileges:true", "--cap-drop", "ALL",
               "--cap-add", "DAC_OVERRIDE", "--tmpfs", "/tmp:size=64m,mode=1777",
               "--env", "LA_ARCHIVE_IMAGES=" + json.dumps(images, sort_keys=True)]
    if action == "restore":
        # Without FSETID Linux can silently strip a directory's S_ISGID when
        # its numeric group is not in the helper's supplementary groups.
        command += ["--cap-add", "CHOWN", "--cap-add", "FOWNER", "--cap-add", "FSETID"]
    command += volume_mounts(containers, writable=action == "restore")
    key_target = "backup-recipients" if action == "backup" else "backup-identity"
    command += ["--mount", f"type=bind,src={key_file},dst=/run/secrets/{key_target},readonly"]
    if action == "restore":
        command += ["--mount", f"type=bind,src={archive},dst=/backup/archive.age,readonly"]
    command += ["--entrypoint", "python", images["api"], "/app/deploy/volume_archive.py", action]
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("archive", type=Path, nargs="?")
    parser.add_argument("--preflight-only", action="store_true",
                        help="Read-only restart-order check; no archive, keys or downtime")
    parser.add_argument("--recipients-file", type=Path)
    parser.add_argument("--identity-file", type=Path)
    parser.add_argument("--stop-services", action="store_true", help="Acknowledge backup downtime")
    parser.add_argument("--fresh-target", action="store_true", help="Restore only into new empty volumes")
    parser.add_argument("--project-name", help="Explicit Compose project; use with the matching configuration")
    parser.add_argument("--compose-file", action="append", type=Path, default=[],
                        help="Compose file, repeat for overrides (default: repository compose.yaml)")
    parser.add_argument("--env-file", type=Path, help="Explicit Compose env file; /dev/null disables .env loading")
    args = parser.parse_args()
    original_running = []
    restart_groups = []
    partial = None
    try:
        compose = compose_command(args.project_name, args.compose_file, args.env_file)
        if args.preflight_only:
            if (args.action != "backup" or args.archive is not None or args.stop_services or args.fresh_target
                    or args.recipients_file is not None or args.identity_file is not None):
                raise ValueError("Preflight-only accepts no archive, keys, downtime or restore options")
            running = run([*compose, "--profile", "*", "ps", "--quiet", "--status", "running"]).splitlines()
            groups = restart_plan(running)
            print(json.dumps({"schema": "backup-restart-preflight-v1", "restart_order_verified": True,
                              "running_containers": len(running), "restart_groups": len(groups),
                              "backup_qualified": False, "changes_performed": False}))
            return 0
        if args.archive is None:
            raise ValueError("Supply an archive path or use --preflight-only")
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
        containers, images = inventory(compose)
        if args.action == "backup":
            if archive.exists():
                raise ValueError("Refusing to overwrite an existing backup")
            archive.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            candidate_partial = archive.with_name(archive.name + ".partial")
            # Exclusive creation prevents accidental replacement of a prior partial backup.
            fd = os.open(candidate_partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            partial = candidate_partial
            with os.fdopen(fd, "wb") as output:
                running = run([*compose, "--profile", "*", "ps", "--quiet",
                               "--status", "running"]).splitlines()
                if running:
                    restart_groups = restart_plan(running)
                    original_running = running
                    # Respect each container's configured StopTimeout (API: 240s).
                    # A 60s override can terminate cooperative workers prematurely.
                    run(["docker", "stop", *original_running], timeout=600)
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
            running = run([*compose, "--profile", "*", "ps", "--quiet", "--status", "running"])
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
                for group in restart_groups:
                    run(["docker", "start", *group])
            except subprocess.SubprocessError:
                print("Previously running containers need manual restart; do not assume recovery.", file=sys.stderr)
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
