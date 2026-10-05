#!/usr/bin/env python3
"""Offline signed graph-release preparation, installation and stopped-service CAS activation.

Default operational commands target this Compose project's existing Fuseki volume.
--root targets a deliberately supplied offline filesystem for imports/rehearsals.
No command creates trust keys, signs legal review, starts services or accesses law websites.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lawyer_graph_serving", ROOT / "ontology" / "serving.py")
serving = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(serving)
COMPOSE = ["docker", "compose", "--project-directory", str(ROOT), "-f", str(ROOT / "compose.yaml")]


def run(command: list[str], timeout: int = 120) -> str:
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
    return result.stdout.strip()


def _path(value: Path) -> Path:
    if value.is_symlink():
        raise ValueError("Operator inputs cannot be symlinks")
    path = value.expanduser().resolve(strict=True)
    if "," in str(path):
        raise ValueError("Docker bind mount paths cannot contain commas")
    return path


def compose_target() -> tuple[str, str]:
    found = run([*COMPOSE, "ps", "--all", "--quiet", "fuseki"]).splitlines()
    if len(found) != 1:
        raise ValueError("Exactly one existing Compose Fuseki container is required")
    mounts = json.loads(run(["docker", "inspect", "--format", "{{json .Mounts}}", found[0]]))
    candidates = [m for m in mounts if m["Destination"] == "/fuseki" and m["Type"] == "volume"]
    if len(candidates) != 1:
        raise ValueError("Fuseki must have one named volume at /fuseki")
    image = run(["docker", "inspect", "--format", "{{.Image}}", found[0]])
    return candidates[0]["Name"], image


def require_stopped() -> None:
    for service in ("api", "fuseki"):
        containers = run([*COMPOSE, "ps", "--all", "--quiet", service]).splitlines()
        if len(containers) != 1:
            raise ValueError("Exactly one existing api and fuseki container is required")
        if run(["docker", "inspect", "--format", "{{.State.Running}}", containers[0]]) != "false":
            raise ValueError("Stop api and fuseki before activation or rollback; they are not stopped automatically")


def compose_operation(args: argparse.Namespace) -> dict:
    if args.command in {"activate", "rollback"}:
        require_stopped()
    if args.command in {"install", "activate", "rollback"}:
        # Live freshness requires the private PostgreSQL ledger. The dedicated
        # internal-network coordinator receives no inference/provider credentials.
        command = [*COMPOSE, "--profile", "publication", "run", "--rm", "--no-deps", "-T"]
        child = ["--root", "/graph-publication", args.command]
        if args.command == "install":
            prepared = _path(args.prepared)
            serving.validate_prepared(prepared, _path(args.trusted_review_key))
            command += ["--volume", f"{prepared}:/import:ro"]
            child.append("/import")
        key = _path(args.trusted_review_key)
        command += ["--volume", f"{key}:/run/review-key.pem:ro"]
        child += ["--trusted-review-key", "/run/review-key.pem"]
        if args.command == "activate":
            child.append(args.release_id)
        if args.command in {"activate", "rollback"}:
            child += ["--expected-current", args.expected_current, "--expected-sequence", str(args.expected_sequence)]
        return json.loads(run([*command, "publisher", *child], timeout=600))
    volume, image = compose_target()
    command = ["docker", "run", "--rm", "--network", "none", "--read-only", "--user", "10002:10002",
               "--security-opt", "no-new-privileges:true", "--cap-drop", "ALL",
               "--tmpfs", "/tmp:size=128m,mode=1777", "--mount",
               f"type=volume,src={volume},dst=/fuseki" + (",readonly" if args.command == "status" else ""),
               "--entrypoint", "python3"]
    child = ["/opt/scripts/graph_releases.py", "--root", "/fuseki", args.command]
    if args.command == "install":
        prepared = _path(args.prepared)
        serving.validate_prepared(prepared, _path(args.trusted_review_key))
        command += ["--mount", f"type=bind,src={prepared},dst=/import,readonly"]
        child += ["/import"]
    if args.trusted_review_key is not None:
        key = _path(args.trusted_review_key)
        command += ["--mount", f"type=bind,src={key},dst=/run/review-key.pem,readonly"]
        child += ["--trusted-review-key", "/run/review-key.pem"]
    if args.command == "activate":
        child.append(args.release_id)
    if args.command in {"activate", "rollback"}:
        child += ["--expected-current", args.expected_current, "--expected-sequence", str(args.expected_sequence)]
    return json.loads(run([*command, image, *child], timeout=600))


@contextmanager
def live_authorization(trusted_key):
    # Do not import application/private-store dependencies for pure public
    # validation or the network-none Fuseki initialization/status commands.
    sys.path.insert(0, str(ROOT / "backend"))
    from app.config import load_settings
    from app.public_sources import PublicSourceStore
    from app.release_authorization import ReleaseAuthorization
    from app.release_snapshot import readonly_store
    settings = load_settings()
    with readonly_store(settings) as store:
        yield ReleaseAuthorization(store, PublicSourceStore(settings.public_source_dir),
                                   settings.data_dir / "release-authorizations", trusted_key,
                                   ROOT / "ontology", settings.data_dir / "publication-epoch").guard


def local_operation(args: argparse.Namespace) -> dict:
    root = args.root
    if args.command == "initialize":
        serving.initialize(root)
        return {"initialized": True, "active": serving.read_pointer(root)}
    if args.command == "install":
        with live_authorization(args.trusted_review_key) as guard:
            return serving.install(root, args.prepared, args.trusted_review_key, authorization_guard=guard)
    if args.command == "activate":
        current = None if args.expected_current == "none" else args.expected_current
        with live_authorization(args.trusted_review_key) as guard:
            return serving.activate(root, args.release_id, args.trusted_review_key,
                                    expected_current=current, expected_sequence=args.expected_sequence,
                                    authorization_guard=guard)
    if args.command == "rollback":
        with live_authorization(args.trusted_review_key) as guard:
            return serving.rollback(root, args.trusted_review_key, expected_current=args.expected_current,
                                    expected_sequence=args.expected_sequence, authorization_guard=guard)
    if args.command == "status":
        pointer = serving.read_pointer(root)
        receipt = serving.load_active(root, args.trusted_review_key) if args.trusted_review_key else None
        releases = root / "releases"
        if releases.is_symlink():
            raise ValueError("Release directory cannot be a symlink")
        installed = sorted(p.name for p in releases.iterdir()
                           if p.is_dir() and not p.is_symlink() and serving.HASH.fullmatch(p.name)) if releases.exists() else []
        return {"active": pointer, "installed": installed, "signature_verified": receipt is not None,
                "authorization_checked": False,
                "status": "signature_only" if receipt else "no_active_release" if pointer is None else "trust_not_checked"}
    raise ValueError("Unsupported release operation")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--root", type=Path, help="Offline filesystem root; omit for Compose named volume")
    commands = result.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Validate signed bundle and produce immutable canonical N-Quads")
    prepare.add_argument("bundle", type=Path)
    prepare.add_argument("--output", required=True, type=Path)
    prepare.add_argument("--trusted-review-key", required=True, type=Path)
    for name in ("initialize", "install", "status", "activate", "rollback"):
        command = commands.add_parser(name)
        command.add_argument("--trusted-review-key", type=Path, required=name in {"install", "activate", "rollback"})
        if name == "install":
            command.add_argument("prepared", type=Path)
        if name == "activate":
            command.add_argument("release_id")
        if name in {"activate", "rollback"}:
            command.add_argument("--expected-current", required=True, help="Full current release ID, or none for first activation")
            command.add_argument("--expected-sequence", required=True, type=int, help="Current monotonic pointer sequence, or 0")
    return result


def main() -> int:
    try:
        args = parser().parse_args()
        if args.command == "prepare":
            result = serving.prepare(args.bundle, args.trusted_review_key, args.output)
        elif args.root is None:
            result = compose_operation(args)
        else:
            result = local_operation(args)
        print(json.dumps(result, indent=2, default=str))
        return 0
    except (Exception, KeyboardInterrupt):
        # Never echo private DB errors, authorization contents or host paths.
        print("Graph release operation stopped. Check current reviews, private authorization, "
              "trust, service locks and pointer. A pointer transition may have committed; "
              "reconcile status before retrying.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
