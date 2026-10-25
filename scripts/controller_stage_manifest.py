"""Stdlib-only inspection BEFORE importing an independently approved stage."""

import ast
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

SCHEMA = "lawyer-guarded-controller-stage-v1"
PACKAGE = "lawyer_provider_stage"
MODULES = {"__init__", "trust", "adapters", "contract", "strict_json", "pin_schema", "hook", "route",
           "artifact_store", "sealed_volume", "control", "controller", "manifest", "readiness"}
METADATA = {"stage-manifest.json", "route-stage-manifest.json"}
MAX_FILE, MAX_TOTAL = 1024**2, 8 * 1024**2


def reject():
    raise ValueError("Portable controller stage rejected")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def hex_digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        reject()
    return value


def strict(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                reject()
            value[key] = item
        return value
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: reject())
    except (ValueError, UnicodeError, RecursionError):
        reject()


def directory(path, owner, readonly):
    path = Path(path).absolute()
    info = path.lstat()
    if (path != path.resolve() or not stat.S_ISDIR(info.st_mode) or info.st_uid != owner
            or stat.S_IMODE(info.st_mode) != 0o755):
        reject()
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        if readonly and not os.fstatvfs(fd).f_flag & os.ST_RDONLY:
            reject()
    finally:
        os.close(fd)
    return path


def read(path, owner, readonly):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != owner or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o644 or not 0 < before.st_size <= MAX_FILE
                or (readonly and not os.fstatvfs(stream.fileno()).f_flag & os.ST_RDONLY)):
            reject()
        raw = stream.read(MAX_FILE + 1)
        after = os.fstat(stream.fileno())
        def fields(value):
            return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_nlink,
                    value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if len(raw) != before.st_size or fields(before) != fields(after) or fields(after) != fields(Path(path).lstat()):
            reject()
        return raw


def inspect_stage(root, approved_manifest_sha256, *, expected_owner=None, require_readonly=True):
    """The approved hash/owner are trusted caller inputs, never read from the stage."""
    owner = os.getuid() if expected_owner is None else expected_owner
    if type(owner) is not int or owner < 0 or type(require_readonly) is not bool:
        reject()
    approved_manifest_sha256 = hex_digest(approved_manifest_sha256)
    root = directory(root, owner, require_readonly)
    if {p.name for p in root.iterdir()} != {PACKAGE, "guarded-stage-manifest.json", *METADATA}:
        reject()
    raw = read(root / "guarded-stage-manifest.json", owner, require_readonly)
    if digest(raw) != approved_manifest_sha256:
        reject()
    value = strict(raw)
    fields = {"schema", "version", "package_name", "stage_only", "production_activation", "private_material_included",
              "backend_transport", "application_or_engine_imports", "imports_rewritten_only_for_portability",
              "required_dependencies", "source_sha256", "package_sha256", "metadata_sha256"}
    if (not isinstance(value, dict) or set(value) != fields or value["schema"] != SCHEMA
            or type(value["version"]) is not int or value["version"] != 1 or value["package_name"] != PACKAGE
            or value["stage_only"] is not True or value["production_activation"] is not False
            or value["private_material_included"] is not False or value["application_or_engine_imports"] is not False
            or value["imports_rewritten_only_for_portability"] is not True
            or value["backend_transport"] != "explicit_httpx_mock_only"
            or value["required_dependencies"] != ["cryptography>=44,<47", "httpx==0.28.1"]
            or not isinstance(value["source_sha256"], dict) or not 10 <= len(value["source_sha256"]) <= 32
            or not isinstance(value["package_sha256"], dict) or set(value["package_sha256"]) != {n + ".py" for n in MODULES}
            or not isinstance(value["metadata_sha256"], dict) or set(value["metadata_sha256"]) != METADATA):
        reject()
    for name, expected in value["source_sha256"].items():
        if not re.fullmatch(r"(?:scripts/[a-z_]+\.py|deploy/fixtures/provider_(?:engine_source|stage_policy)\.json)", name):
            reject()
        hex_digest(expected)
    package = directory(root / PACKAGE, owner, require_readonly)
    if {p.name for p in package.iterdir()} != set(value["package_sha256"]):
        reject()
    total = len(raw)
    for name, expected in value["metadata_sha256"].items():
        body = read(root / name, owner, require_readonly)
        if digest(body) != hex_digest(expected):
            reject()
        total += len(body)
    for name, expected in value["package_sha256"].items():
        body = read(package / name, owner, require_readonly)
        if digest(body) != hex_digest(expected):
            reject()
        total += len(body)
        tree = ast.parse(body)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    if node.level != 1 or (node.module is not None and node.module.split(".")[0] not in MODULES):
                        reject()
                    if node.module is None and any(n.name not in MODULES for n in node.names):
                        reject()
                elif node.module.split(".")[0] not in sys.stdlib_module_names | {"cryptography", "httpx"}:
                    reject()
            elif isinstance(node, ast.Import):
                if any(n.name.split(".")[0] not in sys.stdlib_module_names | {"cryptography", "httpx"} for n in node.names):
                    reject()
    if total > MAX_TOTAL:
        reject()
    return {"manifest_sha256": approved_manifest_sha256, "modules": len(MODULES), "bytes_checked": total,
            "application_or_engine_imports": False, "kernel_readonly": require_readonly,
            "stage_only": True, "production_activation": False}
