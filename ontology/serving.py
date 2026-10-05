"""Verified immutable serving artifacts and atomic offline release selection.

The signed source bundle is authoritative. Canonical N-Quads are reconstructed on
validation; runtime TDB2 indexes are disposable derivatives, never release truth.
No function here contacts a service, generates a review key, or modifies a live DB.
"""
from __future__ import annotations

import ctypes
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from rdflib import RDF, Graph, Literal, URIRef
from rdflib.compare import to_canonical_graph

_spec = importlib.util.spec_from_file_location("lawyer_source_releases", Path(__file__).with_name("releases.py"))
_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_release)
canonical, file_hash, validate_bundle = _release.canonical, _release.file_hash, _release.validate_bundle
FAMILIES = ("structure", "jurisprudence")
HASH = re.compile(r"[a-f0-9]{64}\Z")
SERVING_NS = "urn:la:serving:"
FORMAT = 1


class TransitionOutcomeUnknown(ValueError):
    """A filesystem commit succeeded before a later transition check failed."""


def _require_guard(authorization_guard):
    if authorization_guard is None:
        raise ValueError("Release transition requires a live authorization guard")
    if not callable(authorization_guard):
        raise TypeError("Release authorization guard must be callable")


def _rename_exclusive(source: Path, destination: Path) -> None:
    """Publish a directory atomically without replacing even an empty directory."""
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
        raise ValueError("Atomic no-replace release publication is unsupported on this host")
    if result != 0:
        raise OSError(ctypes.get_errno(), "Atomic no-replace release publication failed")


def release_id(value: str) -> str:
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise ValueError("Release ID must be a full lowercase SHA-256 digest")
    return value


def safe_file(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(p in {"..", "."} for p in path.parts):
        raise ValueError("Unsafe release-relative path")
    candidate = root
    if root.is_symlink():
        raise ValueError("Release roots cannot be symlinks")
    for part in path.parts:
        candidate /= part
        if candidate.is_symlink():
            raise ValueError("Release paths cannot contain symlinks")
    if not candidate.is_file():
        raise ValueError("Release path must be a regular file")
    return candidate


def _files(root: Path) -> set[str]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Release must be a real directory")
    result = set()
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("Release contains a symlink or special file")
        if path.is_file():
            result.add(str(path.relative_to(root)))
    return result


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write(path: Path, raw: bytes) -> None:
    with path.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def _sync_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    for directory in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        _sync_directory(directory)
    _sync_directory(root)


def _public_release_modes(root: Path) -> None:
    # The API (UID 10001) and Fuseki/publisher (UID 10002) deliberately differ.
    # Only validated public data reaches these directories; runtime mounts are RO.
    for path in root.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o444)
    root.chmod(0o755)


def _payload(bundle: Path, result: dict, family: str) -> tuple[bytes, dict]:
    ident = release_id(result["bundle_sha256"])
    iri = f"urn:la:release:{ident}:{family}"
    manifest_raw = safe_file(bundle, "manifest.json").read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != ident:
        raise ValueError("Source manifest changed after signature validation")
    manifest = json.loads(manifest_raw)

    def read_verified(relative: str) -> tuple[str, bytes]:
        path = safe_file(bundle, relative)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest["files"][relative]:
            raise ValueError("Source graph changed after bundle validation")
        return path.as_uri(), raw

    inputs = {}
    for name in FAMILIES:
        uri, raw = read_verified(f"inputs/{name}.ttl")
        inputs[name] = Graph().parse(data=raw, format="turtle", publicID=uri)
    assertions = {subject for graph in inputs.values() for subject in graph.subjects(RDF.type, _release.LA.Assertion)}
    schema_paths = [*sorted(path for path in manifest["files"]
                           if path.startswith("ontology/modules/") and path.endswith(".ttl")), "ontology/domains.ttl"]
    # Every file is read and checked against the signed manifest even on a warm
    # parse. Reuse only ontology syntax, never the source assertions or payload.
    graph = _release._validation.parse_ontology_graph([read_verified(path) for path in schema_paths])
    for name, source in inputs.items():
        for triple in source:
            # Shared resource/evidence context is required for cross-family links;
            # assertion subjects remain confined to their signed family input.
            if name == family or triple[0] not in assertions:
                graph.add(triple)
    graph = to_canonical_graph(graph)
    # NT serialization escapes embedded newlines and quotes; canonical bnodes make
    # the payload stable across parses. Sorting also removes parser iteration order.
    triples = sorted(line for line in graph.serialize(format="nt").splitlines() if line.strip())
    data = [line[:-1].rstrip() + f" <{iri}> ." for line in triples]
    subject = URIRef(f"urn:la:release:{ident}").n3()
    meta_iri = f"urn:la:release:{ident}:metadata"
    metadata = {
        "bundleSha256": Literal(ident),
        "ontologySha256": Literal(manifest["ontology_sha256"]),
        "reviewKeySha256": Literal(result["review"]["key_sha256"]),
        "family": Literal(family),
        "graph": URIRef(iri),
    }
    for predicate, obj in metadata.items():
        data.append(f"{subject} <{SERVING_NS}{predicate}> {obj.n3()} <{meta_iri}> .")
    raw = ("\n".join(sorted(data)) + "\n").encode("utf-8")
    return raw, {"graph_iri": iri, "file": f"{family}.nq", "sha256": hashlib.sha256(raw).hexdigest(),
                 "triple_count": len(triples)}


def expected_serving(bundle: Path, trusted_key: Path) -> tuple[dict, dict[str, bytes]]:
    _files(bundle)
    result = validate_bundle(bundle, trusted_key)
    if result["legal_publication_eligible"] is not True or result["review"]["verified"] is not True:
        raise ValueError("Serving publication requires an independently trusted signed legal review")
    manifest_raw = safe_file(bundle, "manifest.json").read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != result["bundle_sha256"]:
        raise ValueError("Source manifest changed after signature validation")
    manifest = json.loads(manifest_raw)
    payloads, graphs = {}, {}
    for family in FAMILIES:
        payloads[family], graphs[family] = _payload(bundle, result, family)
    ident = result["bundle_sha256"]
    return {"format_version": FORMAT, "release_id": ident, "bundle_sha256": ident,
            "ontology_sha256": manifest["ontology_sha256"], "review": result["review"],
            "graphs": graphs, "metadata_graph_iri": f"urn:la:release:{ident}:metadata",
            "runtime_mutation": False, "serving_format": "canonical-nquads-v1"}, payloads


def validate_prepared(root: Path, trusted_key: Path) -> dict:
    actual = _files(root)
    raw = safe_file(root, "serving.json").read_bytes()
    if len(raw) > 65536:
        raise ValueError("Serving marker exceeds size limit")
    expected, payloads = expected_serving(root / "bundle", trusted_key)
    if raw != canonical(expected):
        raise ValueError("Serving marker differs from independently verified source bundle")
    wanted = {"serving.json", *(f"{family}.nq" for family in FAMILIES)}
    wanted |= {"bundle/" + relative for relative in _files(root / "bundle")}
    if actual != wanted:
        raise ValueError("Serving release contains missing or undeclared files")
    for family, data in payloads.items():
        if file_hash(safe_file(root, f"{family}.nq")) != hashlib.sha256(data).hexdigest():
            raise ValueError("Serving payload differs from signed source graph")
    return {**expected, "serving_sha256": hashlib.sha256(raw).hexdigest(), "bundle_path": root / "bundle"}


def prepare(bundle: Path, trusted_key: Path, output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise ValueError("Immutable prepared release already exists")
    marker, payloads = expected_serving(bundle, trusted_key)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".preparing-", dir=output.parent))
    try:
        shutil.copytree(bundle, stage / "bundle", symlinks=False)
        for family, data in payloads.items():
            _write(stage / f"{family}.nq", data)
        _write(stage / "serving.json", canonical(marker))
        validate_prepared(stage, trusted_key)
        _public_release_modes(stage)
        _sync_tree(stage)
        _rename_exclusive(stage, output)
        _sync_directory(output.parent)
        return validate_prepared(output, trusted_key)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def initialize(root: Path) -> None:
    if root.is_symlink():
        raise ValueError("Publication root cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    # The operator initializes the shared graph GID; the private publisher must
    # not need ownership merely to reuse already-correct group permissions.
    if stat.S_IMODE(root.stat().st_mode) != 0o2775:
        root.chmod(0o2775)
    releases = root / "releases"
    if releases.is_symlink():
        raise ValueError("Release directory cannot be a symlink")
    releases.mkdir(exist_ok=True)
    if stat.S_IMODE(releases.stat().st_mode) != 0o2775:
        releases.chmod(0o2775)
    for name in ("publication.lock", ".install.lock"):
        descriptor = _lock_descriptor(root, name, create=True)
        try:
            if stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o644:
                os.fchmod(descriptor, 0o644)
        finally:
            os.close(descriptor)
    _sync_directory(root)


def _lock_descriptor(root: Path, name: str, *, create: bool = False) -> int:
    path = root / name
    if not create or path.exists() or path.is_symlink():
        safe_file(root, name)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_CREAT if create else 0), 0o644)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValueError("Release lock must be a regular file")
    return descriptor


@contextmanager
def publication_lock(root: Path, *, shared: bool = False):
    descriptor = _lock_descriptor(root, "publication.lock")
    try:
        try:
            fcntl.flock(descriptor, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Publication is locked; stop Fuseki before changing the active release") from exc
        yield descriptor
    finally:
        os.close(descriptor)


def read_pointer(root: Path) -> dict | None:
    if root.is_symlink():
        raise ValueError("Publication root cannot be a symlink")
    pointer = root / "active.json"
    if not pointer.exists() and not pointer.is_symlink():
        return None
    raw = safe_file(root, "active.json").read_bytes()
    if len(raw) > 4096:
        raise ValueError("Active pointer exceeds size limit")
    value = json.loads(raw)
    required = {"format_version", "release_id", "serving_sha256", "previous_release_id", "sequence"}
    if (not isinstance(value, dict) or set(value) != required or value["format_version"] != FORMAT
            or type(value["sequence"]) is not int or value["sequence"] < 1):
        raise ValueError("Invalid active release pointer")
    release_id(value["release_id"])
    release_id(value["serving_sha256"])
    if value["previous_release_id"] is not None:
        release_id(value["previous_release_id"])
    return value


def load_active(root: Path, trusted_key: Path | None) -> dict | None:
    pointer = read_pointer(root)
    if pointer is None:
        return None
    if trusted_key is None or not trusted_key.is_file():
        raise ValueError("Active release requires an operator-supplied trusted public review key")
    release_root = root / "releases" / pointer["release_id"]
    if (root / "releases").is_symlink():
        raise ValueError("Release directory cannot be a symlink")
    result = validate_prepared(release_root, trusted_key)
    if result["release_id"] != pointer["release_id"] or result["serving_sha256"] != pointer["serving_sha256"]:
        raise ValueError("Active pointer differs from verified serving release")
    if read_pointer(root) != pointer:
        raise ValueError("Active release changed during verification")
    return {**result, "pointer": pointer}


def install(root: Path, prepared: Path, trusted_key: Path, *, authorization_guard=None) -> dict:
    _require_guard(authorization_guard)
    verified = validate_prepared(prepared, trusted_key)
    initialize(root)
    # Install touches no active data and remains safe with live shared readers.
    # Its independent filesystem lock always precedes live authorization locks.
    descriptor = _lock_descriptor(root, ".install.lock")
    stage, committed = None, False
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        destination = root / "releases" / verified["release_id"]
        if destination.exists() or destination.is_symlink():
            result = validate_prepared(destination, trusted_key)
            if (result["release_id"] != verified["release_id"]
                    or result["serving_sha256"] != verified["serving_sha256"]):
                raise ValueError("Existing immutable release differs")
            # An existing installation does not confer continuing authorization.
            with authorization_guard(result, "install"):
                return result
        with authorization_guard(verified, "install"):
            stage = Path(tempfile.mkdtemp(prefix=".installing-", dir=root / "releases"))
            shutil.copytree(prepared, stage, dirs_exist_ok=True, symlinks=False)
            staged = validate_prepared(stage, trusted_key)
            if (staged["release_id"] != verified["release_id"]
                    or staged["serving_sha256"] != verified["serving_sha256"]):
                raise ValueError("Prepared release changed during installation")
            _public_release_modes(stage)
            _sync_tree(stage)
            _rename_exclusive(stage, destination)
            committed = True
            stage = None
            _sync_directory(destination.parent)
            return validate_prepared(destination, trusted_key)
    except BaseException:
        if committed:
            raise TransitionOutcomeUnknown("Release transition may have committed; reconcile pointer and installed inventory") from None
        raise
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
        os.close(descriptor)


def _check_current(root: Path, expected_current: str | None, expected_sequence: int) -> dict | None:
    if expected_current is not None:
        release_id(expected_current)
    if type(expected_sequence) is not int or expected_sequence < 0:
        raise ValueError("Expected release sequence must be a nonnegative integer")
    current = read_pointer(root)
    if ((current["release_id"] if current else None) != expected_current
            or (current["sequence"] if current else 0) != expected_sequence):
        raise ValueError("Active release changed: compare-and-swap failed")
    return current


def _activate_authorized(root: Path, ident: str, trusted_key: Path, *, current: dict | None,
                         authorization_guard, action: str) -> dict:
    """Caller holds publication EX and has checked the exact current pointer."""
    ident = release_id(ident)
    target = root / "releases" / ident
    if (root / "releases").is_symlink():
        raise ValueError("Release directory cannot be a symlink")
    result = validate_prepared(target, trusted_key)
    if result["release_id"] != ident:
        raise ValueError("Release directory does not match its signed identity")
    if current is not None and current["release_id"] == ident:
        raise ValueError("Requested release is already active")
    pointer = {"format_version": FORMAT, "release_id": ident, "serving_sha256": result["serving_sha256"],
               "previous_release_id": current["release_id"] if current else None,
               "sequence": current["sequence"] + 1 if current else 1}
    temporary = root / (".active-" + os.urandom(12).hex())
    committed = False
    try:
        with authorization_guard(result, action):
            # Catch non-cooperating pointer changes while authorization is read.
            if read_pointer(root) != current:
                raise ValueError("Active release changed: compare-and-swap failed")
            _write(temporary, canonical(pointer))
            temporary.chmod(0o444)
            os.replace(temporary, root / "active.json")
            committed = True
            _sync_directory(root)
        return pointer
    except BaseException:
        if committed:
            raise TransitionOutcomeUnknown("Release transition may have committed; reconcile pointer and installed inventory") from None
        raise
    finally:
        temporary.unlink(missing_ok=True)


def activate(root: Path, ident: str, trusted_key: Path, *, expected_current: str | None,
             expected_sequence: int = 0, authorization_guard=None) -> dict:
    _require_guard(authorization_guard)
    ident = release_id(ident)
    with publication_lock(root):
        current = _check_current(root, expected_current, expected_sequence)
        return _activate_authorized(root, ident, trusted_key, current=current,
                                    authorization_guard=authorization_guard, action="activate")


def rollback(root: Path, trusted_key: Path, *, expected_current: str, expected_sequence: int,
             authorization_guard=None) -> dict:
    _require_guard(authorization_guard)
    with publication_lock(root):
        current = _check_current(root, expected_current, expected_sequence)
        if current is None or current["previous_release_id"] is None:
            raise ValueError("No previous release is recorded for rollback")
        return _activate_authorized(root, current["previous_release_id"], trusted_key, current=current,
                                    authorization_guard=authorization_guard, action="rollback")
