"""One no-write transaction for bounded Graph A/B preparation dependencies.

Current private projections only: no public assembly, component permission,
legal qualification or serving authority. Callers must discard dependent output
if exit fails. The original family-specific reconstruction stays authoritative.
"""
from contextlib import contextmanager
from typing import Literal

from fastapi import HTTPException
from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from . import graph_b_snapshot as b_family
from . import release_snapshot_set as a_family
from .decision_equivalence import context_ids
from .decision_equivalence_models import DecisionEquivalenceHead
from .decision_identity_models import DecisionIdentityHead, DecisionIdentityReservation
from .decision_mapping_models import DecisionMappingHead
from .graph_b_review_models import GraphBReviewHead
from .provision_mapping_models import ProvisionMappingHead
from .release_preparation import canonical, digest
from .release_snapshot import SnapshotError, _operator
from .source_review_models import SourceReviewHead
from .source_reviews import StrictInput

MAX_BYTES = 64 * 1024 * 1024
MAX_PRIVATE_BYTES = 32 * 1024 * 1024


class MixedGraphRequest(StrictInput):
    schema_version: Literal["legal-mixed-graph-selection-v1"]
    structure: a_family.SnapshotSetRequest
    jurisprudence: list[b_family.SnapshotRequest] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def distinct_contexts(self):
        contexts = [context_ids(*item.decision_source_ids, item.register_source_id)[1]
                    for item in self.jurisprudence]
        a_sources = {item.source_id for item in self.structure.sources}
        b_sources = {key for item in self.jurisprudence for key in [*item.decision_source_ids, item.register_source_id]}
        decisions = {key for item in self.jurisprudence for key in item.decision_source_ids}
        registers = {item.register_source_id for item in self.jurisprudence}
        if len(set(contexts)) != len(contexts) or a_sources & b_sources or decisions & registers:
            raise ValueError("Distinct decision contexts and disjoint source families are required")
        return self


def invalid():
    return SnapshotError("Current mixed legal-graph preparation dependencies could not be verified")


def _contexts(request):
    return sorted((context_ids(*item.decision_source_ids, item.register_source_id)[1], item)
                  for item in request.jurisprudence)


def _lock_plan(store, session, operator_id, request, shared):
    # Pre-acquire the complete plan before family reconstruction. Reacquisition
    # by existing helpers stays in this SAME session/mode; no upgrades or nested
    # sessions. Every account precedes every source, then contexts/reservations.
    members = {key: _operator(session, key, shared=shared) for key in sorted(
        {operator_id, *(item.reviewer_id for item in request.jurisprudence)})}
    operator = members[operator_id]
    if any(actor.firm_id != operator.firm_id for actor in members.values()):
        raise invalid()
    a_sources = {item.source_id for item in request.structure.sources}
    decisions = {key for item in request.jurisprudence for key in item.decision_source_ids}
    registers = {item.register_source_id for item in request.jurisprudence}
    # A source cannot be a decision in one context and a register in another.
    if decisions & registers:
        raise invalid()
    reservations = set()
    for source in sorted(a_sources | decisions | registers):
        b_family._row(session, SourceReviewHead, operator.firm_id, "source_id", source, shared)
        if source in a_sources:
            b_family._row(session, ProvisionMappingHead, operator.firm_id, "source_id", source, shared)
        if source in decisions:
            b_family._row(session, DecisionMappingHead, operator.firm_id, "source_id", source, shared)
            head = b_family._row(session, DecisionIdentityHead, operator.firm_id, "source_id", source, shared)
            proposal = b_family.sources._decode(store, head)["event"]["proposal"]
            reservations.update((proposal["identity"]["decision_id"], proposal["identity"]["proceeding_id"], proposal["version_id"]))
    for context, _ in _contexts(request):
        b_family._row(session, DecisionEquivalenceHead, operator.firm_id, "context_id", context, shared)
        b_family._row(session, GraphBReviewHead, operator.firm_id, "context_id", context, shared)
    rows = list(session.scalars(select(DecisionIdentityReservation).where(
        DecisionIdentityReservation.firm_id == operator.firm_id,
        DecisionIdentityReservation.canonical_id.in_(sorted(reservations)))
        .order_by(DecisionIdentityReservation.canonical_id).with_for_update(read=shared)
        .execution_options(populate_existing=True)))
    if not reservations or {row.canonical_id for row in rows} != reservations:
        raise invalid()
    return operator


def _capture(store, source_store, session, operator_id, request, trusted_key, ontology_root, shared):
    operator = _lock_plan(store, session, operator_id, request, shared)
    selections = a_family._selection(operator_id, request.structure)
    snapshots, originals, fingerprints, byte_count, mapping_count = a_family._capture(
        store, source_store, session, operator, selections, shared=shared)
    a_family._revalidate(store, source_store, session, operator_id, a_family._identity(operator), selections,
        originals, fingerprints, shared=shared)
    binding = {"schema_version": "legal-review-snapshot-set-v1", "firm_id": operator.firm_id,
        "operator_id": operator.id, "sources": [item["binding"] for item in snapshots], "publication_eligible": False}
    mode = ("postgresql_transaction_locks" if store.engine.dialect.name == "postgresql"
            else "sqlite_demo_optimistic_revalidation")
    a_value = {"snapshots": snapshots, "binding": binding,
        "summary": {"schema_version": "legal-review-snapshot-set-summary-v1", "source_count": len(snapshots),
            "mapping_count": mapping_count, "artifact_bytes": byte_count, "binding_sha256": digest(canonical(binding)),
            "consistency_mode": mode, "signed": False, "publication_eligible": False, "confidentiality": "firm_confidential"}}
    packages = {item["package"].detail["id"]: item["package"] for item in snapshots}
    private_structure = {**{key: a_value[key] for key in ("binding", "summary")},
        "snapshots": [{key: item[key] for key in item if key != "package"} for item in snapshots]}
    b_values, private_bytes = [], len(canonical(private_structure))
    if private_bytes > MAX_PRIVATE_BYTES:
        raise invalid()
    for _, item in _contexts(request):
        value = b_family._capture(store, source_store, session, operator_id, item, trusted_key, ontology_root, shared)
        packages.update(value["packages"])
        private_bytes += len(canonical({key: value[key] for key in value if key not in {"packages", "key_bytes"}}))
        if (sum(len(raw) for package in packages.values() for raw in package.artifacts.values()) > MAX_BYTES
                or private_bytes > MAX_PRIVATE_BYTES):
            raise invalid()
        b_values.append(value)
    if len({value["binding"]["ontology_sha256"] for value in b_values}) != 1:
        raise invalid()
    return {"structure": a_value, "jurisprudence": b_values,
        "summary": {"schema_version": "legal-mixed-graph-snapshot-v1", "source_count": len(packages),
                    "context_count": len(b_values), "consistency_mode": mode, "publication_eligible": False,
                    "confidentiality": "firm_confidential"}}


def _fingerprint(value):
    if type(value) is not dict or set(value) != {"structure", "jurisprudence", "summary"}:
        raise invalid()
    return digest(canonical({"summary": value["summary"],
        "structure": a_family._result_fingerprint(value["structure"]),
        "jurisprudence": [b_family._fingerprint(item) for item in value["jurisprudence"]]}))


@contextmanager
def locked_mixed_snapshot(store, source_store, *, operator_id, request, trusted_key, ontology_root, shared=False):
    """All selected current A/B dependencies in one bounded no-write transaction.

    This is neither a complete-corpus declaration nor a permission verdict.
    PostgreSQL protects all dependency rows; SQLite demo only revalidates.
    """
    try:
        if (type(shared) is not bool or type(operator_id) is not str or not 1 <= len(operator_id) <= 64
                or type(request) is not MixedGraphRequest or store.engine.dialect.name not in {"postgresql", "sqlite"}):
            raise invalid()
        request = MixedGraphRequest.model_validate(request.model_dump())
        with store.session() as session:
            value = _capture(store, source_store, session, operator_id, request, trusted_key, ontology_root, shared)
            fingerprint = _fingerprint(value)
            yield value
            if _fingerprint(value) != fingerprint:
                raise invalid()
            session.expire_all()
            final = _capture(store, source_store, session, operator_id, request, trusted_key, ontology_root, shared)
            if _fingerprint(final) != fingerprint or _fingerprint(value) != fingerprint:
                raise invalid()
            # Context close rolls back. No rows, event, audit or graph is changed.
    except (HTTPException, ValueError, TypeError, KeyError, AttributeError, OSError, RecursionError, SQLAlchemyError):
        raise invalid() from None
