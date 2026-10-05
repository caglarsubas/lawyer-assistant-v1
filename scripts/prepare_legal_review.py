#!/usr/bin/env python3
"""Prepare or revalidate confidential legal-graph review packets, entirely locally.

Never signs, publishes, activates, changes credentials or mutates review records.
Run only on the trusted deployment host with an existing source-review owner's ID.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import load_settings  # noqa: E402
from app.public_sources import PublicSourceStore  # noqa: E402

HASH = re.compile(r"^[a-f0-9]{64}$")
MAX_JSON = 2 * 1024 * 1024
MAX_FILE = 32 * 1024 * 1024
MAX_PACKET = 96 * 1024 * 1024
MAX_FILES = 256
MAX_EVIDENCE = 128
MAX_EVIDENCE_FILE = 8 * 1024 * 1024
MAX_EVIDENCE_TOTAL = 32 * 1024 * 1024
RESERVED = {"manifest.json", "manifest.sha256", "manifest.hmac"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def parse_json(raw):
    def invalid(value):
        raise ValueError("Invalid JSON number")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=invalid)


def checked_path(value):
    path = Path(os.path.abspath(Path(value).expanduser()))
    for parent in (*reversed(path.parents), path):
        if parent.is_symlink():
            raise ValueError("Symbolic links are prohibited")
    return path


def read_file(value, limit):
    path = checked_path(value)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit or info.st_nlink != 1:
            raise ValueError("Input must be a bounded regular non-linked file")
        raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("Input exceeded its byte budget")
        return raw


def evidence_files(directory):
    root = checked_path(directory)
    if not root.is_dir():
        raise ValueError("Evidence directory is required")
    evidence, total = {}, 0
    for path in root.iterdir():
        if len(evidence) >= MAX_EVIDENCE or not re.fullmatch(r"[a-f0-9]{64}\.bin", path.name):
            raise ValueError("Evidence inventory is invalid or exceeds its bound")
        raw = read_file(path, MAX_EVIDENCE_FILE)
        total += len(raw)
        if total > MAX_EVIDENCE_TOTAL or digest(raw) != path.stem:
            raise ValueError("Evidence byte budget or digest mismatch")
        evidence[path.stem] = raw
    return evidence


def _relative(name):
    if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,239}", name)
            or len(name.split("/")) > 4
            or Path(name).is_absolute() or any(part in {"", ".", ".."} for part in name.split("/"))):
        raise ValueError("Unsafe packet-relative path")
    return name


def _inventory(files):
    if len(files) > MAX_FILES or sum(len(raw) for raw in files.values()) > MAX_PACKET:
        raise ValueError("Review packet exceeds its budget")
    for name, raw in files.items():
        _relative(name)
        if type(raw) is not bytes or len(raw) > MAX_FILE or name in RESERVED:
            raise ValueError("Invalid review packet content")
    return {name: {"sha256": digest(raw), "bytes": len(raw)} for name, raw in sorted(files.items())}


def sealed_files(files, store):
    manifest = canonical({"schema_version": "legal-review-packet-v1", "confidentiality": "firm_confidential",
                          "signed": False, "publication_eligible": False, "files": _inventory(files)})
    return {**files, "manifest.json": manifest, "manifest.sha256": (digest(manifest) + "\n").encode(),
            "manifest.hmac": (store.preparation_mac(manifest) + "\n").encode()}


def read_packet(directory, store):
    root = checked_path(directory)
    if not root.is_dir():
        raise ValueError("Packet directory is missing")
    raw = read_file(root / "manifest.json", MAX_JSON)
    expected_mac = read_file(root / "manifest.hmac", 65).decode().strip()
    if not HASH.fullmatch(expected_mac) or not hmac.compare_digest(expected_mac, store.preparation_mac(raw)):
        raise ValueError("Packet integrity seal does not match this deployment")
    if read_file(root / "manifest.sha256", 65).decode().strip() != digest(raw):
        raise ValueError("Packet inventory digest mismatch")
    manifest = parse_json(raw)
    if (set(manifest) != {"schema_version", "confidentiality", "signed", "publication_eligible", "files"}
            or manifest["schema_version"] != "legal-review-packet-v1"
            or manifest["confidentiality"] != "firm_confidential" or manifest["signed"] is not False
            or manifest["publication_eligible"] is not False or not isinstance(manifest["files"], dict)
            or len(manifest["files"]) > MAX_FILES):
        raise ValueError("Unsupported review packet")
    expected = set(manifest["files"]) | RESERVED
    actual, directories = set(), set()
    for name in expected:
        _relative(name)
        directories.update(str(parent) for parent in Path(name).parents if str(parent) != ".")
    # Bound every filesystem entry, not just manifest files; do not follow symlinks.
    entries = [iter(root.iterdir())]
    count = 0
    while entries:
        try:
            path = next(entries[-1])
        except StopIteration:
            entries.pop()
            continue
        count += 1
        if count > MAX_FILES * 3 or path.is_symlink():
            raise ValueError("Unsafe review packet inventory")
        relative = str(path.relative_to(root))
        if path.is_dir():
            if relative not in directories:
                raise ValueError("Undeclared review packet directory")
            entries.append(iter(path.iterdir()))
        else:
            actual.add(relative)
    if actual != expected:
        raise ValueError("Missing or extra review packet files")
    files = {name: read_file(root / name, MAX_FILE) for name in manifest["files"]}
    if manifest["files"] != _inventory(files):
        raise ValueError("Review packet bytes changed")
    if canonical(manifest) != raw:
        raise ValueError("Noncanonical review packet inventory")
    return files, digest(raw)


def atomic_packet(output, files):
    destination = checked_path(output)
    if destination.exists() or not destination.parent.is_dir():
        raise ValueError("Output must be new and its parent must already exist")
    # An exclusive sibling reservation prevents cooperating processes replacing a
    # same-name destination; a malicious host root remains outside this boundary.
    reservation = destination.parent / ("." + destination.name + ".preparation-lock")
    fd = os.open(reservation, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    stage = None
    try:
        if destination.exists():
            raise ValueError("Output already exists")
        stage = Path(tempfile.mkdtemp(prefix=".legal-review-", dir=destination.parent))
        os.chmod(stage, 0o700)
        for name, raw in files.items():
            _relative(name)
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            for parent in path.parents:
                if parent == stage:
                    break
                os.chmod(parent, 0o700)
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        if destination.exists():
            raise ValueError("Output was created during preparation")
        for directory in [p for p in stage.rglob("*") if p.is_dir()] + [stage]:
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        result = stage.stat()
        _rename_exclusive(stage, destination)
        stage = None
        return (result.st_dev, result.st_ino)
    finally:
        if stage is not None:
            shutil.rmtree(stage)
        reservation.unlink()


def _rename_exclusive(source, destination):
    """Atomically rename without replacing a concurrently created destination."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        operation = libc.renamex_np
        operation.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = operation(os.fsencode(source), os.fsencode(destination), 4)  # RENAME_EXCL
    elif sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        operation = libc.renameat2
        operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = operation(-100, os.fsencode(source), -100, os.fsencode(destination), 1)  # NOREPLACE
    else:
        raise ValueError("Atomic no-replace preparation is unsupported on this host")
    if result != 0:
        raise OSError(ctypes.get_errno(), "Atomic review packet publication failed")


def _remove_own_output(output, identity):
    """Discard only this invocation's artifact if the final live check fails."""
    path = checked_path(output)
    if identity is not None and path.exists():
        current = path.stat()
        if (current.st_dev, current.st_ino) == identity:
            shutil.rmtree(path)


def prepare(settings, *, operator_id, source_id, expected_source_review_revision, expected_mapping_revision,
            registry, resolutions, evidence_dir, output, ontology_root=ROOT / "ontology"):
    from app.release_preparation import compile_review
    from app.release_snapshot import locked_snapshot, readonly_store

    registry_data = parse_json(read_file(registry, MAX_JSON))
    resolution_data = parse_json(read_file(resolutions, MAX_JSON))
    evidence = evidence_files(evidence_dir)
    with readonly_store(settings) as store:
        with locked_snapshot(store, PublicSourceStore(settings.public_source_dir), operator_id=operator_id,
                             source_id=source_id, expected_source_review_revision=expected_source_review_revision,
                             expected_mapping_revision=expected_mapping_revision) as snapshot:
            files, summary = compile_review(snapshot, registry_data, resolution_data, evidence, Path(ontology_root))
            packet = sealed_files(files, store)
            # Finish the snapshot's final integrity/generation check before writing.
        # A second locked check prevents publishing a packet from a stale first read.
        created = None
        try:
            with locked_snapshot(store, PublicSourceStore(settings.public_source_dir), operator_id=operator_id,
                                 source_id=source_id, expected_source_review_revision=expected_source_review_revision,
                                 expected_mapping_revision=expected_mapping_revision) as current:
                if current["binding"] != snapshot["binding"]:
                    raise ValueError("Source review changed before packet output")
                created = atomic_packet(output, packet)
                written, written_digest = read_packet(output, store)
                if written != files or written_digest != digest(packet["manifest.json"]):
                    raise ValueError("Review packet changed during atomic output")
        except BaseException:
            _remove_own_output(output, created)
            raise
    return {**summary, "packet_sha256": digest(packet["manifest.json"]), "current_at_validation": True}


def validate(settings, directory, *, operator_id, ontology_root=ROOT / "ontology"):
    from app.release_preparation import compile_review
    from app.release_snapshot import locked_snapshot, readonly_store

    with readonly_store(settings) as store:
        files, packet_digest = read_packet(directory, store)
        binding = parse_json(files["binding.json"])
        registry = parse_json(files["registry.json"])
        resolutions = parse_json(files["resolutions.json"])
        evidence = {Path(name).stem: raw for name, raw in files.items() if name.startswith("private-evidence/")}
        if binding["operator_id"] != operator_id:
            raise ValueError("Packet is bound to a different source-review owner")
        with locked_snapshot(store, PublicSourceStore(settings.public_source_dir), operator_id=operator_id,
                             source_id=binding["source_id"],
                             expected_source_review_revision=binding["source_review_revision"],
                             expected_mapping_revision=binding["mapping_revision"]) as snapshot:
            rebuilt, summary = compile_review(snapshot, registry, resolutions, evidence, Path(ontology_root))
            if files != rebuilt:
                raise ValueError("Packet differs from current source, reviews, identities or ontology")
            final_files, final_digest = read_packet(directory, store)
            if final_digest != packet_digest or final_files != files:
                raise ValueError("Packet changed during validation")
    return {**summary, "packet_sha256": packet_digest, "current_at_validation": True}


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid review preparation arguments; use --help.\n")


def parser():
    result = SafeParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    preparing = commands.add_parser("prepare")
    checking = commands.add_parser("validate")
    for command in (preparing, checking):
        command.add_argument("--operator-id", required=True)
    for name in ("source-id", "registry", "resolutions", "evidence-dir", "output"):
        preparing.add_argument("--" + name, required=True, type=str if name == "source-id" else Path)
    for name in ("expected-source-review-revision", "expected-mapping-revision"):
        preparing.add_argument("--" + name, required=True, type=int)
    checking.add_argument("directory", type=Path)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        settings = load_settings()
        values = vars(args).copy()
        operation = values.pop("command")
        result = prepare(settings, **values) if operation == "prepare" else validate(settings, **values)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print("Review preparation stopped: invalid input, unavailable store, changed review or integrity failure. "
              "No publication was performed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
