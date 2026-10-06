"""Bounded, consistent private review snapshots; never release preparation.

The set does not reconcile canonical identities, combine graphs or grant rights.
Its caller must use ``readonly_store`` for the no-write local operator boundary
and discard dependent output when context exit raises. PostgreSQL holds account
and ledger locks in one transaction. Explicit SQLite demo storage has optimistic
revalidation only; it does not provide PostgreSQL's lock guarantee.
"""

import hashlib
import re
from contextlib import contextmanager
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy.exc import SQLAlchemyError

from .release_snapshot import SnapshotError, _canonical, _copy, _load, _operator, _package

MAX_SOURCES = 8
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_MAPPINGS = 400


class SourceSelection(BaseModel):
    """One exact, current source revision pair supplied by the local operator."""

    model_config = ConfigDict(extra="forbid", strict=True, revalidate_instances="always")

    source_id: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    expected_source_review_revision: int = Field(ge=1, le=1000)
    expected_mapping_revision: int = Field(ge=1, le=1000)

    @field_validator("source_id")
    @classmethod
    def exact_source_id(cls, value):
        if re.fullmatch(r"[a-f0-9]{64}", value) is None:
            raise ValueError("An exact source identifier is required")
        return value


class SnapshotSetRequest(BaseModel):
    """An explicit source set, not a query or authorization to acquire sources."""

    model_config = ConfigDict(extra="forbid", strict=True, revalidate_instances="always")

    schema_version: Literal["legal-review-source-selection-v1"]
    sources: list[SourceSelection] = Field(min_length=2, max_length=MAX_SOURCES)

    @model_validator(mode="after")
    def unique_sources(self):
        if len({source.source_id for source in self.sources}) != len(self.sources):
            raise ValueError("Source selections must be unique")
        return self


def _selection(operator_id, request):
    # A validated model can still have been mutated by its caller. Validate an
    # independent copy before opening the session or reading any source bytes.
    if type(operator_id) is not str or not 1 <= len(operator_id) <= 64 or type(request) is not SnapshotSetRequest:
        raise SnapshotError("Supply an exact operator and bounded source selection")
    try:
        request = SnapshotSetRequest.model_validate(request.model_dump(mode="python", warnings=False))
        return tuple(sorted(request.sources, key=lambda item: item.source_id))
    except (ValidationError, ValueError, TypeError, AttributeError):
        raise SnapshotError("Supply an exact operator and bounded source selection") from None


def _identity(operator):
    return operator.id, operator.firm_id, operator.role


def _package_bytes(package):
    return {name: bytes(raw) for name, raw in package.artifacts.items()}


def _snapshot_fingerprint(snapshot):
    """Bind returned metadata too, without retaining another copy of raw bytes."""
    if type(snapshot) is not dict or set(snapshot) != {"package", "state", "source_review", "binding"}:
        raise SnapshotError("Returned snapshot content changed during inspection")
    package = snapshot["package"]
    payload = {key: snapshot[key] for key in ("state", "source_review", "binding")}
    payload["package"] = {
        "detail": package.detail, "metadata": package.metadata.model_dump(),
        "locators": package.locators.model_dump(), "text": package.text,
        "artifacts": {name: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
                      for name, raw in package.artifacts.items()},
    }
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _result_fingerprint(value):
    try:
        if type(value) is not dict or set(value) != {"snapshots", "binding", "summary"}:
            raise ValueError()
        return hashlib.sha256(_canonical({"binding": value["binding"], "summary": value["summary"],
                                         "snapshots": [_snapshot_fingerprint(item)
                                                       for item in value["snapshots"]]})).hexdigest()
    except (TypeError, ValueError, KeyError, AttributeError, RecursionError):
        raise SnapshotError("Returned snapshot content changed during inspection") from None


def _budget(artifact_bytes, mapping_count):
    if artifact_bytes > MAX_ARTIFACT_BYTES:
        raise SnapshotError("The source set exceeds the total artifact byte limit")
    if mapping_count > MAX_MAPPINGS:
        raise SnapshotError("The source set exceeds the total mapping limit")


def _capture(store, source_store, session, operator, selections, *, shared=False):
    snapshots, originals, fingerprints = [], [], []
    artifact_bytes, mapping_count = 0, 0
    for source in selections:
        package = _package(source_store, source.source_id)
        artifact_bytes += sum(len(raw) for raw in package.artifacts.values())
        _budget(artifact_bytes, mapping_count)
        snapshot = _load(store, session, package, operator,
                         source.expected_source_review_revision, source.expected_mapping_revision, shared=shared)
        mapping_count += len(snapshot["state"]["items"])
        _budget(artifact_bytes, mapping_count)
        snapshots.append(snapshot)
        originals.append(_package_bytes(package))
        fingerprints.append(_snapshot_fingerprint(snapshot))
    return snapshots, originals, fingerprints, artifact_bytes, mapping_count


def _revalidate(store, source_store, session, operator_id, identity, selections, originals, fingerprints, *, shared=False):
    operator = _operator(session, operator_id, shared=shared)
    if _identity(operator) != identity:
        raise SnapshotError("The operator identity or role changed during inspection")
    artifact_bytes, mapping_count = 0, 0
    for source, original, fingerprint in zip(selections, originals, fingerprints, strict=True):
        package = _package(source_store, source.source_id)
        if package.artifacts != original:
            raise SnapshotError("A source package changed during inspection")
        artifact_bytes += sum(len(raw) for raw in package.artifacts.values())
        _budget(artifact_bytes, mapping_count)
        current = _load(store, session, package, operator,
                        source.expected_source_review_revision, source.expected_mapping_revision, shared=shared)
        mapping_count += len(current["state"]["items"])
        _budget(artifact_bytes, mapping_count)
        if _snapshot_fingerprint(current) != fingerprint:
            raise SnapshotError("Review state changed during inspection")
    # The final package or ledger read may itself have crossed an account change
    # in explicit SQLite demo mode, where FOR UPDATE does not acquire row locks.
    if _identity(_operator(session, operator_id, shared=shared)) != identity:
        raise SnapshotError("The operator identity or role changed during inspection")


@contextmanager
def locked_snapshot_set(store, source_store, *, operator_id, request: SnapshotSetRequest, shared=False):
    """Hold all selected current reviews through one bounded caller operation.

    Acquisition order is account, then source-review and mapping heads for each
    source ID in ascending order. All locks remain in one transaction until exit.
    Runtime read authorization may request shared row locks; ordinary preparation
    keeps exclusive locks. Shared callers may not mutate rows or upgrade locks.
    The returned set and its hash are private inspection material, not a prepared
    packet, legal signature or publication authorization. No rows are written.
    """
    if type(shared) is not bool:
        raise SnapshotError("Invalid snapshot lock mode")
    selections = _selection(operator_id, request)
    backend = store.engine.dialect.name
    if backend not in {"postgresql", "sqlite"}:
        raise SnapshotError("Snapshot sets require PostgreSQL or explicit SQLite demo storage")
    mode = "postgresql_transaction_locks" if backend == "postgresql" else "sqlite_demo_optimistic_revalidation"
    try:
        with store.session() as session:
            operator = _operator(session, operator_id, shared=shared)
            identity = _identity(operator)
            snapshots, originals, fingerprints, artifact_bytes, mapping_count = _capture(
                store, source_store, session, operator, selections, shared=shared)
            _revalidate(store, source_store, session, operator_id, identity, selections, originals, fingerprints, shared=shared)
            binding = {
                "schema_version": "legal-review-snapshot-set-v1", "firm_id": identity[1],
                "operator_id": identity[0], "sources": [_copy(item["binding"]) for item in snapshots],
                "publication_eligible": False,
            }
            summary = {
                "schema_version": "legal-review-snapshot-set-summary-v1", "source_count": len(selections),
                "mapping_count": mapping_count, "artifact_bytes": artifact_bytes,
                "binding_sha256": hashlib.sha256(_canonical(binding)).hexdigest(), "consistency_mode": mode,
                "signed": False, "publication_eligible": False, "confidentiality": "firm_confidential",
            }
            value = {"snapshots": snapshots, "binding": binding, "summary": summary}
            retained = _result_fingerprint(value)
            yield value
            if _result_fingerprint(value) != retained:
                raise SnapshotError("Returned snapshot content changed during inspection")
            _revalidate(store, source_store, session, operator_id, identity, selections, originals, fingerprints, shared=shared)
            if _result_fingerprint(value) != retained:
                raise SnapshotError("Returned snapshot content changed during inspection")
            # Session close rolls back; no commit, review event, audit or mutation.
    except HTTPException:
        raise SnapshotError("Review ledger integrity validation failed") from None
    except SQLAlchemyError:
        raise SnapshotError("Existing review storage is unavailable or changed concurrently") from None
