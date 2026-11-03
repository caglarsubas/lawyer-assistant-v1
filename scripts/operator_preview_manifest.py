"""Stdlib-only inspection of a public preview export before executing its source."""

import os
import stat
import sys
import time
from pathlib import Path

from controller_stage_manifest import digest, directory, hex_digest, read, strict

SCHEMA = "operator-preview-package-v1"
MANIFEST = "operator-preview-manifest.json"
ASSETS = {"operator_inspection_preview.py", "operator_inspection_preview.html"}
HOST_SCRIPTS = {
    "controller_stage_manifest", "copy_recovery_disposition", "disposition_journal_reconciliation",
    "disposition_receipt_reobservation", "disposition_reconciliation_receipt", "journal_backup_readiness",
    "journal_copy_reconciliation", "journal_materialization", "operator_checksum_handoff",
    "operator_enrollment_evidence", "operator_inventory_handoff", "operator_recovery_inventory",
    "operator_review_auth", "planning_journal_reconciliation", "private_inventory_receipts",
    "receipt_provisioning_readiness", "receipt_recovery_inventory", "receipt_recovery_planning",
    "receipt_stage_manifest",
}
TOOLS = {"operator_preview_manifest", "operator_preview_binding", "build_operator_preview"}
MAX_FILES, MAX_BYTES, SECONDS = 512, 8 * 1024**2, 20


def host_paths(root):
    """Closed code inventory; no configuration, state, tests or account fixtures."""
    root = Path(root)
    return {"scripts/" + name + ".py" for name in HOST_SCRIPTS | TOOLS} | {
        p.relative_to(root).as_posix() for p in (root / "backend/app").rglob("*.py")
    } | {"backend/pyproject.toml", "backend/uv.lock"}


def host_read(path, owner, readonly):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != owner or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) not in {0o600, 0o644} or not 0 <= before.st_size <= 1024**2
                or readonly and not os.fstatvfs(stream.fileno()).f_flag & os.ST_RDONLY):
            raise ValueError("Protected host source required")
        raw = stream.read(1024**2 + 1)
        def identity(value):
            return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_nlink,
                    value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if (len(raw) != before.st_size or identity(before) != identity(os.fstat(stream.fileno()))
                or identity(before) != identity(path.lstat())):
            raise ValueError("Host source changed during inspection")
        return raw


def files(root, names, *, readonly, host=False):
    if not 1 <= len(names) <= MAX_FILES:
        raise ValueError("Preview inventory budget exceeded")
    owner, total, values = os.getuid(), 0, {}
    started = time.monotonic()
    for name in sorted(names):
        path = root / name
        # Refuse symlinked ancestors as well as final symlinks and hardlinks.
        if path.absolute() != path.resolve():
            raise ValueError("Exact preview source namespace required")
        raw = (host_read if host else read)(path, owner, readonly)
        total += len(raw)
        if total > MAX_BYTES or time.monotonic() - started > SECONDS:
            raise ValueError("Preview verification budget exceeded")
        values[name] = raw
    return values


def inspect_package(root, approved_manifest_sha256, *, require_readonly=True):
    """The approval pin is a trusted caller input, never taken from this export."""
    if type(require_readonly) is not bool:
        raise ValueError("Explicit preview policy required")
    root = directory(root, os.getuid(), require_readonly)
    if {p.name for p in root.iterdir()} != ASSETS | {MANIFEST}:
        raise ValueError("Closed preview export required")
    raw = read(root / MANIFEST, os.getuid(), require_readonly)
    if digest(raw) != hex_digest(approved_manifest_sha256):
        raise ValueError("Independent preview approval differs")
    value = strict(raw)
    if (not isinstance(value, dict) or set(value) != {"schema", "version", "stage_only", "production_activation",
            "private_material_included", "compatible_application_host_required", "python", "asset_sha256", "host_sha256"}
            or value["schema"] != SCHEMA or type(value["version"]) is not int or value["version"] != 1
            or value["stage_only"] is not True or value["production_activation"] is not False
            or value["private_material_included"] is not False or value["compatible_application_host_required"] is not True
            or value["python"] != ">=3.12" or not isinstance(value["asset_sha256"], dict)
            or set(value["asset_sha256"]) != ASSETS or not isinstance(value["host_sha256"], dict)
            or not 22 <= len(value["host_sha256"]) <= MAX_FILES):
        raise ValueError("Public source-only preview manifest required")
    assets = files(root, ASSETS, readonly=require_readonly)
    if any(digest(body) != hex_digest(value["asset_sha256"][name]) for name, body in assets.items()):
        raise ValueError("Preview asset differs")
    for expected in value["host_sha256"].values():
        hex_digest(expected)
    return value, assets


def inspect_host(root, manifest, *, require_readonly=True):
    """Requires already loaded trusted host modules; never adds an import path."""
    root = directory(root, os.getuid(), require_readonly)
    names = host_paths(root)
    if names != set(manifest["host_sha256"]):
        raise ValueError("Compatible closed host inventory required")
    bodies = files(root, names, readonly=require_readonly, host=True)
    if any(digest(raw) != manifest["host_sha256"][name] for name, raw in bodies.items()):
        raise ValueError("Pinned host source differs")
    required = HOST_SCRIPTS | {"app", "app.auth", "app.db", "app.firm_rbac"}
    if not required <= set(sys.modules):
        raise ValueError("Trusted host must already be loaded")
    for name, module in tuple(sys.modules.items()):
        if name not in HOST_SCRIPTS | TOOLS and name != "app" and not name.startswith("app."):
            continue
        path = root / ("scripts/" + name + ".py" if name in HOST_SCRIPTS | TOOLS else
                       "backend/" + name.replace(".", "/") + ("/__init__.py" if hasattr(module, "__path__") else ".py"))
        if (path.relative_to(root).as_posix() not in bodies or getattr(module, "__file__", None) != str(path)
                or getattr(getattr(module, "__spec__", None), "origin", None) != str(path)):
            raise ValueError("Loaded host module namespace differs")
    return {"host_files_checked": len(bodies), "host_bytes_checked": sum(map(len, bodies.values())),
            "kernel_readonly": require_readonly, "production_activation": False}
