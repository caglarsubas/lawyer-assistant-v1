"""Reviewed cross-source claims and retained institutional identity evidence, never merging."""
import re
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field, StrictInt, ValidationError, field_validator, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from . import decision_identities as identities
from . import source_reviews as reviews
from .db import now, uid
from .decision_equivalence_models import DecisionEquivalenceEvent, DecisionEquivalenceHead
from .release_preparation import canonical, digest
from .source_reviews import StrictInput

VERSION = "decision-equivalence-review-v1"
MAX_EVENTS = 50
MAX_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_LEDGER_BYTES = 2 * 1024 * 1024
SOURCE_ID = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SOURCE_REVISION = Annotated[StrictInt, Field(ge=0, le=1000)]
IDENTITY_REVISION = Annotated[StrictInt, Field(ge=0, le=identities.MAX_EVENTS)]


class Proof(StrictInput):
    source_id: SOURCE_ID
    passage_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Claims(StrictInput):
    relation: Literal["same_decision", "different_decision", "undetermined"]
    canonical_decision_id: str | None = Field(pattern="^" + identities.ID % "decision" + "$")
    institution_id: str = Field(pattern="^" + identities.ID % "institution" + "$")
    registered_name: str = Field(min_length=3, max_length=300)
    register_record_id: str = Field(min_length=3, max_length=300)
    evidence: list[Proof] = Field(min_length=3, max_length=30)

    @field_validator("registered_name", "register_record_id")
    @classmethod
    def printable(cls, value):
        if value != value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Sicil kaydı ve kurum adı açık, kontrol karaktersiz olmalı")
        return value

    @field_validator("evidence")
    @classmethod
    def unique(cls, value):
        if len({(p.source_id, p.passage_id) for p in value}) != len(value):
            raise ValueError("Aynı pasaj birden fazla dayanak olarak eklenemez")
        return value

    @model_validator(mode="after")
    def explicit_anchor(self):
        if (self.relation == "same_decision") != (self.canonical_decision_id is not None):
            raise ValueError("Aynı karar için açık kanonik aday seçin; farklı veya belirsiz kararlar için null kullanın")
        return self


class Pins(StrictInput):
    source_revisions: dict[SOURCE_ID, SOURCE_REVISION] = Field(min_length=3, max_length=3)
    mapping_revisions: dict[SOURCE_ID, SOURCE_REVISION] = Field(min_length=3, max_length=3)
    identity_revisions: dict[SOURCE_ID, IDENTITY_REVISION] = Field(min_length=2, max_length=2)


class Mutation(StrictInput):
    expected_revision: StrictInt = Field(ge=0, le=MAX_EVENTS)
    pins: Pins
    rationale: str = Field(min_length=3, max_length=4000)


class ProposalInput(Mutation):
    claims: Claims


class ReviewInput(Mutation):
    decision: Literal["accepted", "needs_changes", "rejected"]
    evidence: list[Proof] = Field(min_length=3, max_length=30)

    @field_validator("evidence")
    @classmethod
    def unique(cls, value):
        return Claims.unique(value)


def _error():
    return HTTPException(409, "Eşdeğerlik kaydı, tam dayanaklar veya güncel revizyonlar doğrulanamadı")


def context_ids(source_id, peer_source_id, register_source_id):
    if (any(type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None
            for value in (source_id, peer_source_id, register_source_id))
            or len({source_id, peer_source_id, register_source_id}) != 3):
        raise ValueError("Two distinct exact decision sources and a register source are required")
    decision_ids = sorted([source_id, peer_source_id])
    return decision_ids, digest(canonical([decision_ids, register_source_id, VERSION]))


def context(request, source_id, peer_source_id, register_source_id, user):
    try:
        decision_ids, key = context_ids(source_id, peer_source_id, register_source_id)
    except ValueError:
        raise HTTPException(422, "İki karar kaynağı ve sicil kaynağı ayrı olmalı") from None
    packages = {key: reviews._package(request, key, user) for key in sorted([*decision_ids, register_source_id])}
    return packages, decision_ids, key


def capture(store, session, packages, decision_ids, firm_id, *, lock=False):
    captured, events = {}, {}
    # Every path takes source locks in the same order, including register sources.
    for key, package in packages.items():
        captured[key] = identities.capture(store, session, package, firm_id, lock=lock)
        if key in decision_ids:
            events[key] = identities.ledger(store, session, identities._head(session, firm_id, key), package, captured[key])
    result = {"sources": captured, "identities": events}
    if len(canonical(result)) > MAX_CAPTURE_BYTES:
        raise HTTPException(409, "Tam kaynak ve kimlik geçmişleri 4 MiB sınırını aşıyor; kısmi inceleme verilmedi")
    return result


def current_pins(captured):
    return {"source_revisions": {key: value["state"]["source_review_revision"] for key, value in captured["sources"].items()},
            "mapping_revisions": {key: value["state"]["revision"] for key, value in captured["sources"].items()},
            "identity_revisions": {key: len(value) for key, value in captured["identities"].items()}}


def _source_at(value, revision, mapping_revision):
    source = [e for e in value["source_history"] if e["revision"] <= revision]
    mappings = [e for e in value["mapping_history"] if e["revision"] <= mapping_revision]
    if ([e["revision"] for e in source] != list(range(revision, 0, -1))
            or [e["revision"] for e in mappings] != list(range(mapping_revision, 0, -1))):
        raise _error()
    assessments = {}
    for event in source:
        if event["event_type"] == "assessment":
            assessments.setdefault(event["category"], event)
    if (set(assessments) != set(reviews.CATEGORIES) or any(e["decision"] != "accepted" for e in assessments.values())
            or not {"local_processing", "internal_display"}.issubset(assessments["rights"]["permitted_uses"])):
        raise _error()
    return {"source_history": source, "mapping_history": mappings,
            "reviewed_passage_ids": assessments["extraction"]["passage_ids"],
            "export_allowed": "export" in assessments["rights"]["permitted_uses"]}


def resolve_proofs(proofs, packages, snapshot):
    result = []
    for proof in proofs:
        value = Proof.model_validate(proof)
        package = packages.get(value.source_id)
        passage = next((p for p in package.locators.passages if p.id == value.passage_id), None) if package else None
        if (passage is None or passage.text_sha256 != value.sha256
                or passage.id not in snapshot["sources"][value.source_id]["reviewed_passage_ids"]):
            raise HTTPException(409, "Dayanaklar seçili üç kaynağın çıkarımı kabul edilmiş tam pasajları ve SHA256'ları olmalı")
        result.append((value.source_id, passage))
    if {key for key, _ in result} != set(packages):
        raise HTTPException(409, "Her iki karar ve sicil kaynağından ayrı fiziksel dayanak gerekir")
    return result


def _identity_proofs(proposal, event, packages, snapshot):
    refs = proposal["identity"]["identity_evidence"] + proposal["identity"]["institution_evidence"] + event["evidence_refs"]
    lookup = {f"source:{key}:passage:{p.id}": (key, p) for key, package in packages.items() for p in package.locators.passages}
    for ref in refs:
        found = lookup.get(ref["reference"])
        if (found is None or found[1].text_sha256 != ref["sha256"]
                or found[1].id not in snapshot["sources"][found[0]]["reviewed_passage_ids"]):
            raise HTTPException(409, "Kanonik kimliğin eski metin veya harici dayanaklarını seçili fiziksel pasajlara yeniden bağlayın")


def snapshot(packages, captured, decision_ids, pins):
    pins = Pins.model_validate(pins).model_dump()
    if (set(pins["source_revisions"]) != set(packages) or set(pins["mapping_revisions"]) != set(packages)
            or set(pins["identity_revisions"]) != set(decision_ids)):
        raise _error()
    result = {"sources": {}, "identities": {}}
    contributors = set()
    for key, package in packages.items():
        value = captured["sources"][key]
        result["sources"][key] = _source_at(value, pins["source_revisions"][key], pins["mapping_revisions"][key])
        source = result["sources"][key]
        contributors.update(e["reviewer"]["id"] for e in source["source_history"] + source["mapping_history"])
        if key in decision_ids:
            revision = pins["identity_revisions"][key]
            events = captured["identities"][key][:revision]
            if not events or len(events) != revision or events[-1]["decision"] != "accepted":
                raise _error()
            proposal = events[-1]["proposal"]
            if (proposal["source_review_revision"] != pins["source_revisions"][key]
                    or proposal["mapping_revision"] != pins["mapping_revisions"][key]):
                raise _error()
            identities._bound(package, value, proposal["mapping_revision"], proposal["source_review_revision"])
            result["identities"][key] = events
            contributors.update(e["actor"]["id"] for e in events)
    for events in result["identities"].values():
        _identity_proofs(events[-1]["proposal"], events[-1], packages, result)
    result["contributors"] = sorted(contributors)
    result["source_bindings"] = {key: reviews._binding(package) for key, package in packages.items()}
    return result


def validate_claims(claims, packages, decision_ids, bound):
    claims = Claims.model_validate(claims)
    values = [bound["identities"][key][-1]["proposal"]["identity"] for key in decision_ids]
    if any(value["institution_id"] != claims.institution_id for value in values):
        raise HTTPException(409, "Aynı tarihsel kurum kimliği gerekir; farklı kurum kimlikleri bu incelemede birleştirilemez")
    if claims.relation == "same_decision" and values[0]["proceeding_id"] != values[1]["proceeding_id"]:
        raise HTTPException(409, "Aynı karar iddiası için aynı yargılama kimliği gerekir; numara veya ad benzerliği yeterli değil")
    if claims.canonical_decision_id is not None and claims.canonical_decision_id not in {value["decision_id"] for value in values}:
        raise HTTPException(409, "Kanonik aday iki incelenmiş karar kimliğinden biri olmalı; yeni kimlik üretilemez")
    resolve_proofs([proof.model_dump() for proof in claims.evidence], packages, bound)


def decision_summary(events):
    return {key: ({**{name: value[-1]["proposal"]["identity"][name] for name in ("decision_id", "proceeding_id", "institution_id")},
                   "version_id": value[-1]["proposal"]["version_id"]} if value else None) for key, value in events.items()}


def _head(session, firm_id, key):
    return session.scalar(select(DecisionEquivalenceHead).where(
        DecisionEquivalenceHead.firm_id == firm_id, DecisionEquivalenceHead.context_id == key).execution_options(populate_existing=True))


def ledger(store, session, head, packages, decision_ids, captured):
    if head is None:
        return []
    if type(head.revision) is not int or not 1 <= head.revision <= MAX_EVENTS:
        raise _error()
    rows = list(session.scalars(select(DecisionEquivalenceEvent).where(
        DecisionEquivalenceEvent.firm_id == head.firm_id, DecisionEquivalenceEvent.head_id == head.id,
    ).order_by(DecisionEquivalenceEvent.revision).limit(MAX_EVENTS + 1)))
    if ([row.revision for row in rows] != list(range(1, head.revision + 1))
            or sum(len(row.payload) for row in rows) > MAX_LEDGER_BYTES):
        raise _error()
    events, latest, snapshots = [], None, {}
    try:
        for row in rows:
            data = reviews._decode(store, row)
            event = data["event"]
            ctx = {"firm_id": head.firm_id, "head_id": head.id, "context_id": head.context_id, "revision": row.revision, "event_id": row.id}
            if (set(data) != {"context", "event"} or data["context"] != ctx
                    or set(event) != {"id", "revision", "action", "actor", "created_at", "rationale", "decision", "evidence", "proposal"}
                    or event["id"] != row.id or event["revision"] != row.revision or event["created_at"] != row.created_at
                    or not reviews._valid_reviewer(event["actor"]) or datetime.fromisoformat(event["created_at"]).tzinfo is None):
                raise _error()
            proposal = event["proposal"]
            body = {"expected_revision": row.revision - 1, "pins": proposal["pins"], "rationale": event["rationale"]}
            Mutation.model_validate(body)
            cache_key = canonical(proposal["pins"])
            if cache_key not in snapshots:
                snapshots[cache_key] = snapshot(packages, captured, decision_ids, proposal["pins"])
            bound = snapshots[cache_key]
            if (set(proposal) != {"claims", "pins", "snapshot_sha256", "contributors", "proposer", "decisions"}
                    or proposal["snapshot_sha256"] != digest(canonical(bound)) or proposal["contributors"] != bound["contributors"]
                    or proposal["decisions"] != decision_summary(bound["identities"])
                    or not reviews._valid_reviewer(proposal["proposer"])):
                raise _error()
            validate_claims(proposal["claims"], packages, decision_ids, bound)
            if event["action"] == "propose":
                ProposalInput.model_validate({**body, "claims": proposal["claims"]})
                if event["actor"] != proposal["proposer"] or event["decision"] is not None or event["evidence"] != []:
                    raise _error()
            elif event["action"] == "review":
                ReviewInput.model_validate({**body, "decision": event["decision"], "evidence": event["evidence"]})
                if (latest is None or latest["proposal"] != proposal
                        or event["actor"]["id"] in proposal["contributors"] + [proposal["proposer"]["id"]]):
                    raise _error()
                resolve_proofs(event["evidence"], packages, bound)
            else:
                raise _error()
            events.append(event)
            latest = event
        expected = {"context": {"firm_id": head.firm_id, "head_id": head.id, "context_id": head.context_id, "revision": head.revision}, "event": latest}
        if reviews._decode(store, head) != expected:
            raise _error()
    except (KeyError, TypeError, ValueError, ValidationError):
        raise _error() from None
    return events


def view(packages, decision_ids, key, captured, events, user, anchor_id):
    pins = current_pins(captured)
    latest = events[-1] if events else None
    stale = bool(latest and latest["proposal"]["pins"] != pins)
    try:
        bound = snapshot(packages, captured, decision_ids, pins)
        export_allowed = all(value["export_allowed"] for value in bound["sources"].values())
        ready = True
    except HTTPException:
        ready, export_allowed = False, False
    contributors = latest["proposal"]["contributors"] + [latest["proposal"]["proposer"]["id"]] if latest else []
    owner = captured["sources"][anchor_id]["state"]["assigned_to"]
    accepted = bool(latest and latest["decision"] == "accepted" and not stale and ready)
    return {"schema_version": VERSION, "confidentiality": "firm_confidential", "firm_id": user.firm_id,
            "context_id": key, "decision_source_ids": decision_ids, "register_source_id": next(key for key in packages if key not in decision_ids),
            "sources": {key: package.detail for key, package in packages.items()}, "revision": len(events), "pins": pins,
            "decisions": decision_summary(captured["identities"]),
            "current": latest, "history": list(reversed(events)), "history_complete": True, "stale": stale, "inputs_ready": ready,
            "export_allowed": export_allowed,
            "can_propose": bool(owner and owner["id"] == user.id and ready),
            "can_independently_review": bool(latest and not stale and ready and user.id not in contributors),
            "review_accepted": accepted, "same_decision_supported": bool(accepted and latest["proposal"]["claims"]["relation"] == "same_decision"),
            "identity_reservations_changed": False, "global_registry_qualified": False, "legal_effect_verified": False,
            "institutional_competence_verified": False, "publication_eligible": False}


def verify(request, packages, user):
    for key, package in packages.items():
        identities.verify_package(request, key, package)
    reviews._authorize(request, user)


def read(request, source_id, peer_source_id, register_source_id, user):
    packages, decision_ids, key = context(request, source_id, peer_source_id, register_source_id, user)
    store = request.app.state.store
    with store.session() as session:
        captured = capture(store, session, packages, decision_ids, user.firm_id)
        events = ledger(store, session, _head(session, user.firm_id, key), packages, decision_ids, captured)
        result = view(packages, decision_ids, key, captured, events, user, source_id)
    with store.session() as session:
        if (capture(store, session, packages, decision_ids, user.firm_id) != captured
                or ledger(store, session, _head(session, user.firm_id, key), packages, decision_ids, captured) != events):
            raise _error()
    verify(request, packages, user)
    return result


def mutate(request, source_id, peer_source_id, register_source_id, body, user):
    packages, decision_ids, key = context(request, source_id, peer_source_id, register_source_id, user)
    store = request.app.state.store
    try:
        with store.session() as session:
            current = reviews._lock_identity(session, request, user)
            role = current.role
            captured = capture(store, session, packages, decision_ids, current.firm_id, lock=True)
            head = _head(session, current.firm_id, key)
            events = ledger(store, session, head, packages, decision_ids, captured)
            if body.expected_revision != len(events) or body.pins.model_dump() != current_pins(captured) or len(events) >= MAX_EVENTS:
                raise _error()
            bound = snapshot(packages, captured, decision_ids, body.pins.model_dump())
            if isinstance(body, ProposalInput):
                owner = captured["sources"][source_id]["state"]["assigned_to"]
                if not owner or owner["id"] != current.id:
                    raise HTTPException(409, "Öneri için seçili karar kaynağının inceleme sorumlusu olmalısınız")
                validate_claims(body.claims, packages, decision_ids, bound)
                proposal = {"claims": body.claims.model_dump(), "pins": body.pins.model_dump(),
                            "decisions": decision_summary(bound["identities"]),
                            "snapshot_sha256": digest(canonical(bound)), "contributors": bound["contributors"],
                            "proposer": {"id": current.id, "name": current.name}}
                action, decision, evidence = "propose", None, []
            else:
                if not events or events[-1]["proposal"]["snapshot_sha256"] != digest(canonical(bound)):
                    raise _error()
                proposal = events[-1]["proposal"]
                if current.id in proposal["contributors"] + [proposal["proposer"]["id"]]:
                    raise HTTPException(403, "Öneren veya kaynak, eşleme ve kimlik geçmişlerine katılan hesap bağımsız inceleme yapamaz")
                evidence = [proof.model_dump() for proof in body.evidence]
                resolve_proofs(evidence, packages, bound)
                action, decision = "review", body.decision
            revision, head_id = len(events) + 1, head.id if head else uid()
            event = {"id": uid(), "revision": revision, "action": action, "actor": {"id": current.id, "name": current.name},
                     "created_at": now(), "rationale": body.rationale, "decision": decision, "evidence": evidence, "proposal": proposal}
            ctx = {"firm_id": current.firm_id, "head_id": head_id, "context_id": key, "revision": revision}
            payload = store.encode({"context": ctx, "event": event})
            if head is None:
                head = DecisionEquivalenceHead(id=head_id, firm_id=current.firm_id, context_id=key, revision=revision, payload=payload)
                session.add(head)
                session.flush()
            else:
                changed = session.execute(update(DecisionEquivalenceHead).where(
                    DecisionEquivalenceHead.id == head.id, DecisionEquivalenceHead.firm_id == current.firm_id,
                    DecisionEquivalenceHead.revision == body.expected_revision).values(revision=revision, payload=payload)
                    .execution_options(synchronize_session=False))
                if changed.rowcount != 1:
                    raise _error()
            session.add(DecisionEquivalenceEvent(id=event["id"], head_id=head_id, firm_id=current.firm_id,
                                                revision=revision, created_at=event["created_at"],
                                                payload=store.encode({"context": {**ctx, "event_id": event["id"]}, "event": event})))
            verify(request, packages, user)
            if (reviews._lock_identity(session, request, user).role != role
                    or capture(store, session, packages, decision_ids, current.firm_id, lock=True) != captured):
                raise _error()
            session.flush()
            if ledger(store, session, _head(session, current.firm_id, key), packages, decision_ids, captured) != [*events, event]:
                raise _error()
            session.commit()
            return view(packages, decision_ids, key, captured, [*events, event], current, source_id)
    except (IntegrityError, OperationalError):
        raise _error() from None


def decision_equivalence_router():
    router = APIRouter(prefix="/api/v1/public-sources", tags=["decision-equivalence"])
    def authorize(request: Request):
        return reviews._authorize(request)

    @router.get("/{source_id}/decision-equivalence")
    def get(source_id: str, request: Request, peer_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"),
            register_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"), user=Depends(authorize)):
        return read(request, source_id, peer_source_id, register_source_id, user)

    @router.post("/{source_id}/decision-equivalence")
    def propose(source_id: str, body: ProposalInput, request: Request, peer_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"),
                register_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"), user=Depends(authorize)):
        return mutate(request, source_id, peer_source_id, register_source_id, body, user)

    @router.post("/{source_id}/decision-equivalence/review")
    def review(source_id: str, body: ReviewInput, request: Request, peer_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"),
               register_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"), user=Depends(authorize)):
        return mutate(request, source_id, peer_source_id, register_source_id, body, user)

    from .decision_equivalence_handoff import HandoffInput, build_handoff

    @router.post("/{source_id}/decision-equivalence/graph-b-handoff")
    def handoff(source_id: str, body: HandoffInput, request: Request, peer_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"),
                register_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"), user=Depends(authorize)):
        return build_handoff(request, source_id, peer_source_id, register_source_id, body, user)
    return router
