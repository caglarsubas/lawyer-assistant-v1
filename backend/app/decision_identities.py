"""Explicit canonical identity assertions; independent review, never publication."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, StrictInt, ValidationError, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from . import decision_mappings as mappings
from . import source_reviews as reviews
from .db import now, uid
from .decision_dossier import handoff_checks
from .decision_identity_models import DecisionIdentityEvent, DecisionIdentityHead, DecisionIdentityReservation
from .decision_mapping_models import DecisionMappingEvent
from .public_sources import PublicSourceError, PublicSourceStore
from .release_preparation import canonical, digest
from .source_review_models import SourceReviewHead
from .source_reviews import EvidenceReference, StrictInput

MAX_EVENTS = 100
ID = r"urn:tr-law:%s:[a-z0-9][a-z0-9.-]{0,119}"


class IdentityInput(StrictInput):
    institution_id: str = Field(pattern="^" + ID % "institution" + "$")
    proceeding_id: str = Field(pattern="^" + ID % "proceeding" + "$")
    decision_id: str = Field(pattern="^" + ID % "decision" + "$")
    identity_evidence: list[EvidenceReference] = Field(min_length=1, max_length=10)
    institution_evidence: list[EvidenceReference] = Field(min_length=1, max_length=10)

    @field_validator("identity_evidence", "institution_evidence")
    @classmethod
    def unique_evidence(cls, value):
        if len({(item.reference, item.sha256) for item in value}) != len(value):
            raise ValueError("Dayanaklar yinelenemez")
        return value


class Pins(StrictInput):
    expected_revision: StrictInt = Field(ge=0, le=MAX_EVENTS)
    expected_mapping_revision: StrictInt = Field(ge=1, le=1000)
    expected_source_review_revision: StrictInt = Field(ge=1, le=1000)
    rationale: str = Field(min_length=3, max_length=4000)


class ProposalInput(Pins):
    identity: IdentityInput


class ReviewInput(Pins):
    decision: Literal["accepted", "needs_changes", "rejected"]
    evidence_refs: list[EvidenceReference] = Field(min_length=1, max_length=10)

    @field_validator("evidence_refs")
    @classmethod
    def unique_evidence(cls, value):
        return IdentityInput.unique_evidence(value)


def _error():
    return HTTPException(409, "Kanonik kimlik incelemesi bütünlük veya güncellik denetiminden geçmedi")


def version_id(package, decision_id):
    return "urn:tr-law:decision-version:" + digest(canonical([
        decision_id, package.detail["id"], package.metadata.source_version_id,
        package.detail["artifacts"]["raw.bin"]["sha256"], package.detail["artifacts"]["text.txt"]["sha256"],
    ]))


def capture(store, session, package, firm_id, *, lock=False):
    """Verify complete source/mapping histories, not just UI display windows."""
    source_review = mappings._source_review(store, session, package, firm_id, lock=lock)
    source_head = session.scalar(select(SourceReviewHead).where(
        SourceReviewHead.firm_id == firm_id, SourceReviewHead.source_id == package.detail["id"]))
    source_history = reviews._history(store, session, source_head)
    head = mappings._head(session, firm_id, package.detail["id"])
    projection, _ = mappings._projection(store, session, head, package)
    history, lookup = [], {}
    if head:
        rows = session.scalars(select(DecisionMappingEvent).where(
            DecisionMappingEvent.head_id == head.id, DecisionMappingEvent.firm_id == firm_id,
        ).order_by(DecisionMappingEvent.revision.desc()).limit(mappings.MAX_EVENTS + 1))
        history = [mappings._verified_event(mappings._event_header(store, row, head, package), package, lookup) for row in rows]
    revision = head.revision if head else 0
    if [event["revision"] for event in history] != list(range(revision, 0, -1)):
        raise _error()
    return {"state": mappings._state(package, revision, source_review, projection, history),
            "source_history": source_history, "mapping_history": history, "source_review": source_review}


def _bound(package, captured, mapping_revision, source_revision):
    source = [event for event in captured["source_history"] if event["revision"] <= source_revision]
    events = [event for event in captured["mapping_history"] if event["revision"] <= mapping_revision]
    if ([event["revision"] for event in source] != list(range(source_revision, 0, -1))
            or [event["revision"] for event in events] != list(range(mapping_revision, 0, -1))):
        raise _error()
    latest, assessments = {}, {}
    for event in events:
        latest.setdefault(event["mapping_id"], event)
    for event in source:
        if event["event_type"] == "assessment":
            assessments.setdefault(event["category"], event)
    ready = (set(assessments) == set(reviews.CATEGORIES)
             and all(event["decision"] == "accepted" for event in assessments.values())
             and {"local_processing", "internal_display"}.issubset(assessments["rights"]["permitted_uses"]))
    items = [{"id": key, **event["snapshot"], "stale": event["snapshot"]["reviewed_source_revision"] != source_revision}
             for key, event in latest.items()]
    state = {"items": items, "source_review_ready": ready,
             "handoff_ready": ready and bool(items) and all(item["status"] == "accepted" and not item["stale"] for item in items)}
    checks = handoff_checks(state)
    own = [item for item in items if item["resolution"] and item["resolution"]["occurrence_role"] == "own_decision"]
    keys = {(item["resolution"]["decision_ref"], item["resolution"]["proceeding_ref"], item["resolution"]["institution_ref"]) for item in own}
    if (not checks["independent_review_ready"] or len(keys) != 1
            or not any(item["candidate"]["kind"] in {"application_number", "case_number", "decision_number"} for item in own)):
        raise HTTPException(409, "Tek kararın güncel kimlik/numara eşlemeleri ve kaynak incelemeleri gerekir; çoklu kararlar ayrıştırılmalıdır")
    for item in items:
        if item["resolution"]:
            details = mappings._validate_resolution(mappings.Resolution.model_validate(item["resolution"]), item["candidate"], package)
            if not set(details["passage_ids"]).issubset(assessments["extraction"]["passage_ids"]):
                raise _error()
    return {"mapping_revision": mapping_revision, "source_review_revision": source_revision,
            "snapshot_sha256": digest(canonical({"source_binding": reviews._binding(package), "source": source, "mappings": events})),
            "contributors": sorted({event["reviewer"]["id"] for event in source + events}),
            "own_mapping_ids": sorted(item["id"] for item in own),
            "local_references": dict(zip(("decision_ref", "proceeding_ref", "institution_ref"), next(iter(keys)), strict=True))}


def _head(session, firm_id, source_id):
    return session.scalar(select(DecisionIdentityHead).where(
        DecisionIdentityHead.firm_id == firm_id, DecisionIdentityHead.source_id == source_id))


def ledger(store, session, head, package, captured):
    if head is None:
        return []
    if type(head.revision) is not int or not 1 <= head.revision <= MAX_EVENTS:
        raise _error()
    rows = list(session.scalars(select(DecisionIdentityEvent).where(
        DecisionIdentityEvent.head_id == head.id, DecisionIdentityEvent.firm_id == head.firm_id,
    ).order_by(DecisionIdentityEvent.revision).limit(MAX_EVENTS + 1)))
    if [row.revision for row in rows] != list(range(1, head.revision + 1)):
        raise _error()
    events, current = [], None
    try:
        for row in rows:
            data = reviews._decode(store, row)
            event = data["event"]
            context = {"firm_id": head.firm_id, "head_id": head.id, "revision": row.revision, "event_id": row.id}
            if (set(data) != {"context", "source_binding", "event"} or data["context"] != context
                    or data["source_binding"] != reviews._binding(package)
                    or set(event) != {"id", "revision", "actor", "created_at", "rationale", "action", "decision", "evidence_refs", "proposal"}
                    or event["id"] != row.id or event["revision"] != row.revision or event["created_at"] != row.created_at
                    or not reviews._valid_reviewer(event["actor"]) or datetime.fromisoformat(event["created_at"]).tzinfo is None):
                raise _error()
            proposal = event["proposal"]
            identity = IdentityInput.model_validate(proposal["identity"])
            pins = {"expected_revision": row.revision - 1, "expected_mapping_revision": proposal["mapping_revision"],
                    "expected_source_review_revision": proposal["source_review_revision"], "rationale": event["rationale"]}
            Pins.model_validate(pins)
            bound = _bound(package, captured, proposal["mapping_revision"], proposal["source_review_revision"])
            if (set(proposal) != set(bound) | {"identity", "version_id", "proposer"}
                    or any(proposal[key] != value for key, value in bound.items())
                    or proposal["version_id"] != version_id(package, identity.decision_id)
                    or not reviews._valid_reviewer(proposal["proposer"])):
                raise _error()
            if event["action"] == "propose":
                ProposalInput.model_validate({**pins, "identity": proposal["identity"]})
                if event["actor"] != proposal["proposer"] or event["decision"] is not None or event["evidence_refs"] != []:
                    raise _error()
            elif event["action"] == "review":
                ReviewInput.model_validate({**pins, "decision": event["decision"], "evidence_refs": event["evidence_refs"]})
                if current is None or proposal != current["proposal"] or event["actor"]["id"] in proposal["contributors"] + [proposal["proposer"]["id"]]:
                    raise _error()
                if event["decision"] == "accepted":
                    _reservations(store, session, head.firm_id, head.source_id, proposal, create=False)
            else:
                raise _error()
            events.append(event)
            current = event
        projection = reviews._decode(store, head)
        if projection != {"context": {"firm_id": head.firm_id, "head_id": head.id, "revision": head.revision},
                          "source_binding": reviews._binding(package), "event": current}:
            raise _error()
    except (KeyError, TypeError, ValueError, ValidationError):
        raise _error() from None
    return events


def view(package, captured, events, user):
    latest = events[-1] if events else None
    proposal = latest["proposal"] if latest else None
    stale = bool(proposal and (proposal["mapping_revision"] != captured["state"]["revision"]
                              or proposal["source_review_revision"] != captured["state"]["source_review_revision"]))
    accepted = bool(latest and latest["decision"] == "accepted" and not stale)
    return {"schema_version": "decision-identity-review-v1", "source": package.detail, "revision": len(events),
            "mapping_revision": captured["state"]["revision"], "source_review_revision": captured["state"]["source_review_revision"],
            "source_review_ready": captured["state"]["source_review_ready"], "export_allowed": captured["state"]["export_allowed"],
            "assigned_to": captured["state"]["assigned_to"], "current": latest, "history": list(reversed(events)), "stale": stale,
            "can_independently_review": bool(proposal and user.id not in proposal["contributors"] + [proposal["proposer"]["id"]] and not stale),
            "canonical_identity_reviewed": accepted, "staged_handoff_ready": accepted,
            "global_registry_qualified": False, "legal_effect_verified": False, "publication_eligible": False}


def _reservations(store, session, firm_id, source_id, proposal, *, create):
    identity = proposal["identity"]
    # No cross-source equivalence or ID recycling; reuse needs a future explicit review.
    values = {identity["proceeding_id"]: {"institution_id": identity["institution_id"]},
              identity["decision_id"]: {"source_id": source_id, "proceeding_id": identity["proceeding_id"], "institution_id": identity["institution_id"]},
              proposal["version_id"]: {"source_id": source_id, "decision_id": identity["decision_id"]}}
    for identifier, value in values.items():
        row = session.scalar(select(DecisionIdentityReservation).where(
            DecisionIdentityReservation.firm_id == firm_id, DecisionIdentityReservation.canonical_id == identifier))
        payload = {"firm_id": firm_id, "canonical_id": identifier, "binding": value}
        if row and reviews._decode(store, row) != payload:
            raise HTTPException(409, "Kimlik başka kaynak veya kurum ilişkisine ayrılmış; açık eşdeğerlik incelemesi gerekir")
        if row is None and not create:
            raise _error()
        if row is None:
            session.add(DecisionIdentityReservation(id=uid(), firm_id=firm_id, canonical_id=identifier, payload=store.encode(payload)))


def verify_package(request, source_id, package):
    try:
        refreshed = PublicSourceStore(request.app.state.settings.public_source_dir).verified_package(source_id)
        if refreshed.artifacts != package.artifacts:
            raise _error()
    except (PublicSourceError, OSError):
        raise _error() from None


def mutate(request, source_id, body, user):
    package = reviews._package(request, source_id, user)
    store = request.app.state.store
    try:
        with store.session() as session:
            current = reviews._lock_identity(session, request, user)
            role = current.role
            captured = capture(store, session, package, current.firm_id, lock=True)
            head = _head(session, current.firm_id, source_id)
            events = ledger(store, session, head, package, captured)
            if (body.expected_revision != len(events) or body.expected_mapping_revision != captured["state"]["revision"]
                    or body.expected_source_review_revision != captured["state"]["source_review_revision"] or len(events) >= MAX_EVENTS):
                raise _error()
            bound = _bound(package, captured, body.expected_mapping_revision, body.expected_source_review_revision)
            if isinstance(body, ProposalInput):
                owner = captured["state"]["assigned_to"]
                if not owner or owner["id"] != current.id:
                    raise HTTPException(409, "Kimlik önerisi için kaynak inceleme sorumlusu olmalısınız")
                proposal = {**bound, "identity": body.identity.model_dump(), "version_id": version_id(package, body.identity.decision_id),
                            "proposer": {"id": current.id, "name": current.name}}
                action, decision, evidence = "propose", None, []
            else:
                if not events or events[-1]["proposal"] != {**events[-1]["proposal"], **bound}:
                    raise _error()
                proposal = events[-1]["proposal"]
                if current.id in proposal["contributors"] + [proposal["proposer"]["id"]]:
                    raise HTTPException(403, "Öneren veya dayanak incelemelerine katılan kişi bağımsız inceleme yapamaz")
                action, decision, evidence = "review", body.decision, [item.model_dump() for item in body.evidence_refs]
                if decision == "accepted":
                    _reservations(store, session, current.firm_id, source_id, proposal, create=True)
            revision, head_id = len(events) + 1, head.id if head else uid()
            event = {"id": uid(), "revision": revision, "actor": {"id": current.id, "name": current.name},
                     "created_at": now(), "rationale": body.rationale, "action": action, "decision": decision,
                     "evidence_refs": evidence, "proposal": proposal}
            context = {"firm_id": current.firm_id, "head_id": head_id, "revision": revision}
            payload = store.encode({"context": context, "source_binding": reviews._binding(package), "event": event})
            if head is None:
                head = DecisionIdentityHead(id=head_id, firm_id=current.firm_id, source_id=source_id, revision=revision, payload=payload)
                session.add(head)
                session.flush()
            else:
                changed = session.execute(update(DecisionIdentityHead).where(
                    DecisionIdentityHead.id == head.id, DecisionIdentityHead.firm_id == current.firm_id,
                    DecisionIdentityHead.revision == body.expected_revision).values(revision=revision, payload=payload)
                    .execution_options(synchronize_session=False))
                if changed.rowcount != 1:
                    raise _error()
            session.add(DecisionIdentityEvent(id=event["id"], head_id=head_id, firm_id=current.firm_id,
                                             revision=revision, created_at=event["created_at"],
                                             payload=store.encode({"context": {**context, "event_id": event["id"]},
                                                                   "source_binding": reviews._binding(package), "event": event})))
            verify_package(request, source_id, package)
            if (reviews._lock_identity(session, request, user).role != role
                    or capture(store, session, package, current.firm_id, lock=True) != captured):
                raise _error()
            session.commit()
            return view(package, captured, [*events, event], current)
    except IntegrityError:
        raise _error() from None
    except OperationalError:
        raise _error() from None


def decision_identities_router():
    router = APIRouter(prefix="/api/v1/public-sources", tags=["decision-identity"])

    def authorize(request: Request):
        return reviews._authorize(request)

    @router.get("/{source_id}/decision-identities")
    def read(source_id: str, request: Request, user=Depends(authorize)):
        package = reviews._package(request, source_id, user)
        store = request.app.state.store
        with store.session() as session:
            captured = capture(store, session, package, user.firm_id)
            events = ledger(store, session, _head(session, user.firm_id, source_id), package, captured)
            result = view(package, captured, events, user)
        with store.session() as session:
            if capture(store, session, package, user.firm_id) != captured:
                raise _error()
            if ledger(store, session, _head(session, user.firm_id, source_id), package, captured) != events:
                raise _error()
        verify_package(request, source_id, package)
        reviews._authorize(request, user)
        return result

    @router.post("/{source_id}/decision-identities")
    def propose(source_id: str, body: ProposalInput, request: Request, user=Depends(authorize)):
        return mutate(request, source_id, body, user)

    @router.post("/{source_id}/decision-identities/review")
    def review(source_id: str, body: ReviewInput, request: Request, user=Depends(authorize)):
        return mutate(request, source_id, body, user)

    return router
