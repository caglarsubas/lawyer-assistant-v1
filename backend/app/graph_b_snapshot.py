"""Current private Graph B snapshots for trusted local publication preparation.

No HTTP identities, schema initialization, signatures, authorization or graph writes.
Use readonly_store and discard dependent output if context exit fails. PostgreSQL
holds account/source/identity/review locks; SQLite demo uses final revalidation.
"""
from contextlib import contextmanager
from typing import Literal

from fastapi import HTTPException
from pydantic import Field, StrictInt, model_validator
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from . import decision_equivalence as eq
from . import graph_b_review as review
from . import source_reviews as sources
from .decision_equivalence_models import DecisionEquivalenceHead
from .decision_identity_models import DecisionIdentityHead, DecisionIdentityReservation
from .decision_mapping_models import DecisionMappingHead
from .graph_b_review_models import GraphBReviewHead
from .graph_release import _load_serving
from .release_preparation import canonical, digest
from .release_snapshot import REQUIRED_USES, SnapshotError, _operator, _package
from .source_review_models import SourceReviewHead

VERSION = "signed-graph-b-snapshot-v1"
MAX_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


class SnapshotRequest(sources.StrictInput):
    schema_version: Literal["signed-graph-b-selection-v1"]
    decision_source_ids: list[eq.SOURCE_ID] = Field(min_length=2, max_length=2)
    register_source_id: eq.SOURCE_ID
    reviewer_id: str = Field(min_length=1, max_length=64)
    expected_review_revision: StrictInt = Field(ge=1, le=review.MAX_EVENTS)
    expected_equivalence_revision: StrictInt = Field(ge=1, le=eq.MAX_EVENTS)
    pins: eq.Pins

    @model_validator(mode="after")
    def exact_selection(self):
        decisions, _ = eq.context_ids(*self.decision_source_ids, self.register_source_id)
        selected = {*decisions, self.register_source_id}
        if (self.decision_source_ids != decisions or set(self.pins.source_revisions) != selected
                or set(self.pins.mapping_revisions) != selected or set(self.pins.identity_revisions) != set(decisions)
                or any(value < 1 for value in self.pins.source_revisions.values())
                or any(self.pins.mapping_revisions[key] < 1 or self.pins.identity_revisions[key] < 1 for key in decisions)):
            raise ValueError("Sorted exact sources and positive current decision revisions are required")
        return self


def invalid():
    return SnapshotError("Current independently signed Graph B publication snapshot could not be verified")


def _row(session, model, firm, field, value, shared):
    row = session.scalar(select(model).where(model.firm_id == firm, getattr(model, field) == value)
                         .with_for_update(read=shared).execution_options(populate_existing=True))
    if row is None:
        raise invalid()
    return row


def _capture(store, source_store, session, operator_id, request, trusted_key, ontology_root, shared):
    # All accounts precede all source locks. Explicit IDs avoid deriving a lock
    # target from an untrusted or stale projection; both are checked below.
    members = {key: _operator(session, key, shared=shared) for key in sorted({operator_id, request.reviewer_id})}
    operator, reviewer = members[operator_id], members[request.reviewer_id]
    if operator.id == reviewer.id or operator.firm_id != reviewer.firm_id:
        raise invalid()
    decisions, context = eq.context_ids(*request.decision_source_ids, request.register_source_id)
    packages, heads, reservation_ids = {}, {}, set()
    total = 0
    for key in sorted([*decisions, request.register_source_id]):
        packages[key] = package = _package(source_store, key)
        total += sum(len(raw) for raw in package.artifacts.values())
        if total > MAX_ARTIFACT_BYTES:
            raise invalid()
        row = _row(session, SourceReviewHead, operator.firm_id, "source_id", key, shared)
        heads[key] = {"source_review": row.id}
        if key in decisions:
            for name, model in (("mapping", DecisionMappingHead), ("identity", DecisionIdentityHead)):
                own_head = _row(session, model, operator.firm_id, "source_id", key, shared)
                heads[key][name] = own_head.id
                if name == "identity":
                    proposal = sources._decode(store, own_head)["event"]["proposal"]
                    reservation_ids.update((proposal["identity"]["decision_id"], proposal["identity"]["proceeding_id"],
                                            proposal["version_id"]))
    equivalence_head = _row(session, DecisionEquivalenceHead, operator.firm_id, "context_id", context, shared)
    signed_head = _row(session, GraphBReviewHead, operator.firm_id, "context_id", context, shared)
    # Reservation payloads are checked by the identity ledger; lock them too so
    # direct concurrent registry maintenance cannot change accepted identities.
    reservations = list(session.scalars(select(DecisionIdentityReservation).where(
        DecisionIdentityReservation.firm_id == operator.firm_id,
        DecisionIdentityReservation.canonical_id.in_(sorted(reservation_ids))).order_by(DecisionIdentityReservation.canonical_id)
        .with_for_update(read=shared).execution_options(populate_existing=True)))
    if not 1 <= len(reservations) <= 6 or {row.canonical_id for row in reservations} != reservation_ids:
        raise invalid()
    _, _, _, captured, equivalence, events = review.context_from_packages(
        store, session, packages, decisions, context, operator.firm_id)
    if (len(events) != request.expected_review_revision or len(equivalence) != request.expected_equivalence_revision
            or eq.current_pins(captured) != request.pins.model_dump()):
        raise invalid()
    event = events[-1]
    body = event["envelope"]["body"]
    key_raw, _, key_sha = review.configured_key_path(trusted_key)
    ontology_sha = _load_serving()._release.ontology_digest(ontology_root)
    if body["decision"] != "approve" or body["operator_id"] != operator.id or body["reviewer_id"] != reviewer.id:
        raise invalid()
    review.current_check(body, session, packages, captured, decisions, equivalence, context, key_sha, ontology_sha)
    for source in captured["sources"].values():
        rights = next(event for event in source["source_history"] if event.get("category") == "rights")
        if rights["decision"] != "accepted" or not REQUIRED_USES.issubset(rights["permitted_uses"]):
            raise invalid()
    bound, _ = review.assessed(packages, captured, decisions, equivalence, len(equivalence), body["pins"])
    private = {"captured": captured, "equivalence_history": equivalence, "signed_review_history": events}
    private_bytes = canonical(private)
    if len(private_bytes) > MAX_BYTES:
        raise invalid()
    binding = {"schema_version": VERSION, "firm_id": operator.firm_id, "operator_id": operator.id,
        "reviewer_id": reviewer.id, "context_id": context, "selection": request.model_dump(), "heads": heads,
        "equivalence_head_id": equivalence_head.id, "signed_review_head_id": signed_head.id,
        "source_artifacts": {key: package.detail["artifacts"] for key, package in packages.items()},
        "snapshot_sha256": digest(private_bytes), "signed_review_sha256": digest(canonical(event["envelope"])),
        "ontology_sha256": ontology_sha, "review_key_sha256": key_sha, "publication_eligible": False}
    return {"binding": binding, "packages": packages, "decisions": decisions, "bound": bound,
        **private, "members": {key: {"id": actor.id, "firm_id": actor.firm_id, "role": actor.role} for key, actor in members.items()},
        "key_bytes": key_raw,
        "reservations": [{"id": row.id, "canonical_id": row.canonical_id, "payload": row.payload} for row in reservations]}


def _fingerprint(snapshot):
    # Includes original bytes, metadata and every returned field. Caller changes
    # cannot become an implicit override of the reconstructed evidence.
    packages = {key: {"detail": package.detail, "metadata": package.metadata.model_dump(mode="json"),
        "locators": package.locators.model_dump(mode="json"),
        "artifacts": {name: digest(raw) for name, raw in package.artifacts.items()}}
        for key, package in snapshot["packages"].items()}
    return digest(canonical({**{key: value for key, value in snapshot.items() if key not in {"packages", "key_bytes"}},
                             "packages": packages, "key_sha256": digest(snapshot["key_bytes"])}))


@contextmanager
def locked_graph_b_snapshot(store, source_store, *, operator_id, request, trusted_key, ontology_root, shared=False):
    """Transport-independent conjunctive gate; never itself publication permission."""
    try:
        if (type(operator_id) is not str or not 1 <= len(operator_id) <= 64 or type(shared) is not bool
                or type(request) is not SnapshotRequest):
            raise invalid()
        request = SnapshotRequest.model_validate(request.model_dump())
        with store.session() as session:
            snapshot = _capture(store, source_store, session, operator_id, request, trusted_key, ontology_root, shared)
            fingerprint = _fingerprint(snapshot)
            yield snapshot
            if _fingerprint(snapshot) != fingerprint:
                raise invalid()
            # Expunge cached rows before reading all projections and roles anew.
            session.expire_all()
            final = _capture(store, source_store, session, operator_id, request, trusted_key, ontology_root, shared)
            if _fingerprint(final) != fingerprint:
                raise invalid()
            # No commit. readonly_store independently prohibits all writes.
    except (HTTPException, ValueError, TypeError, KeyError, AttributeError, OSError, SQLAlchemyError):
        raise invalid() from None
