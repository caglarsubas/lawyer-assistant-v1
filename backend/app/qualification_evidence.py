"""Bounded offline byte verification for R01; hashes never authenticate legal evidence.

No credentials, settings, database or network are accessed. Descriptor-relative traversal
and repeated captures detect ordinary path replacement and concurrent modification; this
is an integrity check, not a snapshot filesystem or protection against a privileged host.
"""

import hashlib
import os
import re
import stat
from contextlib import contextmanager
from pathlib import Path

from .research_qualification import ResearchDossier

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_FILES = 2000
CHUNK_BYTES = 64 * 1024
FIXED_FILENAMES = frozenset({
    "source-catalog.json", "asset-catalog.json", "analysis-fixture.json", "scenario-fixture.json",
    "research-dossier.json", "sample.json", "raw.bin", "extraction.json", "reference.json",
})
FAILURE = "qualification_evidence_invalid"


class EvidenceVerificationError(ValueError):
    """One fixed diagnostic; never include file contents, paths or submitted identifiers."""


def _invalid():
    raise EvidenceVerificationError(FAILURE)


def _identity(info):
    return info.st_dev, info.st_ino


def _stable(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid, info.st_gid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def _directory_chain(directory):
    """Pin every ancestor with a descriptor; never resolve symlinks before opening."""
    if not isinstance(directory, Path):
        _invalid()
    raw = os.fspath(directory)
    if len(raw) > 4096 or "\x00" in raw or ".." in directory.parts:
        _invalid()
    path = directory if directory.is_absolute() else Path.cwd() / directory
    if len(path.parts) > 128 or path.anchor != "/":
        _invalid()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    descriptors = []
    names = []
    try:
        descriptors.append(os.open("/", flags))
        for name in path.parts[1:]:
            if name in {"", ".", ".."}:
                _invalid()
            descriptors.append(os.open(name, flags, dir_fd=descriptors[-1]))
            names.append(name)
        _check_chain(descriptors, names)
        yield descriptors, names
        _check_chain(descriptors, names)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _check_chain(descriptors, names):
    for descriptor in descriptors:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            _invalid()
    for parent, name, child in zip(descriptors, names, descriptors[1:]):
        linked = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISDIR(linked.st_mode) or _identity(linked) != _identity(os.fstat(child)):
            _invalid()


def _inventory(directory_fd, specifications):
    count = 0
    found = set()
    # scandir streams entries: an unexpected or excessive inventory is rejected
    # immediately rather than loading an unbounded list of attacker-controlled names.
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            count += 1
            if count > MAX_FILES or count > len(specifications) or entry.name not in specifications:
                _invalid()
            found.add(entry.name)
    if found != set(specifications):
        _invalid()


def _read_file(directory_fd, name, limit, remaining, retain_bytes):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    descriptor = os.open(name, flags, dir_fd=directory_fd)
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size < 0 or before.st_size > min(limit, remaining)):
            _invalid()
        digest = hashlib.sha256()
        chunks = [] if retain_bytes else None
        consumed = 0
        # Read exactly the captured size, never one byte beyond the remaining budget.
        # Size/metadata changes and a second complete capture detect ordinary growth.
        while consumed < before.st_size:
            chunk = os.read(descriptor, min(CHUNK_BYTES, before.st_size - consumed))
            if not chunk:
                _invalid()
            consumed += len(chunk)
            if consumed > limit or consumed > remaining:
                _invalid()
            digest.update(chunk)
            if chunks is not None:
                chunks.append(chunk)
        after = os.fstat(descriptor)
        linked = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if _stable(before) != _stable(after) or _stable(after) != _stable(linked):
            _invalid()
        return (b"".join(chunks) if chunks is not None else None,
                digest.digest(), _stable(after), consumed)
    finally:
        os.close(descriptor)


def _capture(directory_fd, specifications, total_limit, retain_bytes):
    before = os.fstat(directory_fd)
    _inventory(directory_fd, specifications)
    content, metadata = {}, {}
    consumed = 0
    for name, limit in sorted(specifications.items()):
        raw, digest, stable, size = _read_file(directory_fd, name, limit, total_limit - consumed, retain_bytes)
        consumed += size
        if retain_bytes:
            content[name] = raw
        metadata[name] = (digest, stable, size)
    _inventory(directory_fd, specifications)
    after = os.fstat(directory_fd)
    if _stable(before) != _stable(after):
        _invalid()
    return content, metadata, _stable(after)


def _check_file_bindings(directory_fd, metadata):
    for name, (_, captured_stat, _) in metadata.items():
        if _stable(os.stat(name, dir_fd=directory_fd, follow_symlinks=False)) != captured_stat:
            _invalid()


def read_exact_directory(directory: Path, specifications: dict[str, int], total_limit: int) -> dict[str, bytes]:
    """Read one exact, immutable-during-inspection inventory without following symlinks.

    Only the fixed packet filenames and lowercase SHA-256 ``.bin`` filenames are
    admitted. Limits apply to each full capture; the second capture retains only hashes
    and metadata. Returned bytes are private input, never an automatically safe report.
    """
    try:
        if (type(specifications) is not dict or len(specifications) > MAX_FILES
                or type(total_limit) is not int or not 0 < total_limit <= MAX_TOTAL_BYTES):
            _invalid()
        for name, limit in specifications.items():
            if (type(name) is not str or (name not in FIXED_FILENAMES
                                         and re.fullmatch(r"[0-9a-f]{64}\.bin", name) is None)
                    or type(limit) is not int or not 0 < limit <= MAX_FILE_BYTES):
                _invalid()
        # Copy to make caller mutation unable to change the admitted names or limits.
        specifications = dict(specifications)
        with _directory_chain(directory) as (first_chain, first_names):
            first_identities = [_identity(os.fstat(fd)) for fd in first_chain]
            content, first_metadata, first_directory = _capture(
                first_chain[-1], specifications, total_limit, True,
            )
            _check_chain(first_chain, first_names)
            # Reopen the full path with the same no-follow policy. A pinned old fd
            # alone would otherwise conceal that the supplied path now names a replacement.
            with _directory_chain(directory) as (second_chain, second_names):
                if [_identity(os.fstat(fd)) for fd in second_chain] != first_identities:
                    _invalid()
                _, second_metadata, second_directory = _capture(
                    second_chain[-1], specifications, total_limit, False,
                )
                if first_metadata != second_metadata or first_directory != second_directory:
                    _invalid()
                _check_file_bindings(second_chain[-1], second_metadata)
                _check_chain(second_chain, second_names)
            _check_file_bindings(first_chain[-1], first_metadata)
            _check_chain(first_chain, first_names)
        return content
    except (OSError, ValueError, TypeError, AttributeError, OverflowError, RuntimeError):
        raise EvidenceVerificationError(FAILURE) from None


def verify_research_evidence(dossier: ResearchDossier, directory: Path) -> dict:
    """Verify all declared bytes physically, while leaving metadata and approvals untrusted."""
    try:
        if not isinstance(dossier, ResearchDossier):
            _invalid()
        dossier = ResearchDossier.model_validate(dossier.model_dump(mode="python"))
        specifications = {f"{record.sha256}.bin": MAX_FILE_BYTES for record in dossier.evidence_records}
        content = read_exact_directory(directory, specifications, MAX_TOTAL_BYTES)
        for record in dossier.evidence_records:
            if hashlib.sha256(content[f"{record.sha256}.bin"]).hexdigest() != record.sha256:
                _invalid()
        return {
            "schema_version": "research-evidence-verification-v1",
            "status": "hashes_verified" if dossier.evidence_records else "no_records",
            "verified_file_count": len(content),
            "verified_bytes": sum(len(raw) for raw in content.values()),
            "declared_evidence_counts": {
                kind: sum(record.sample_kind == kind for record in dossier.evidence_records)
                for kind in ("real", "synthetic")
            },
            "declared_measurement_counts": {
                kind: sum(record.sample_kind == kind for record in dossier.measurements)
                for kind in ("real", "synthetic")
            },
            "source_authenticity_verified": False,
            "review_authenticated": False,
            "metadata_authenticated": False,
            "source_identity_deduplication": "not_evaluated",
            "sample_independence": "not_established",
            "runtime_authorization": "none",
            "production_qualified": False,
        }
    except (OSError, ValueError, TypeError, AttributeError, OverflowError, RuntimeError):
        raise EvidenceVerificationError(FAILURE) from None
