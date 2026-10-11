"""Firm-private, evidence-bound human opinions on one exact source pair."""

import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field, StrictInt, ValidationError, field_validator, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from . import source_reviews as reviews
from .db import digest, now, uid
from .public_sources import SHA256
from .source_comparison import SourceComparisonUnavailable, compare_sources
from .source_review_models import SourceRelationshipEvent, SourceRelationshipHead
from .source_reviews import EvidenceReference, ReviewEffort, StrictInput

MAX_EVENTS = 200
HISTORY_LIMIT = 50
LIMITATIONS = [
    "Kuruma özel insan görüşüdür; kaynakları veya kimlikleri birleştirmez, graf yayımlamaz.",
    "Her kaynak incelemesi değişikliği bu ilişkinin yeniden incelenmesini gerektirir.",
    "Karşılaştırma tek başına hukuki eşdeğerlik, güncel hukuk veya bağımsız çalışma örneklerini kanıtlamaz.",
    "Referansların gerçekliği ve kimlik/sürüm kararı bağımsız yayımlama ve çalışma incelemesi gerektirir.",
]


class ComparisonInput(StrictInput):
    passage_id: str = Field(min_length=1, max_length=80)
    other_passage_id: str = Field(min_length=1, max_length=80)
    offset: StrictInt = Field(ge=0, le=20000)
    other_offset: StrictInt = Field(ge=0, le=20000)
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class IdentityInput(StrictInput):
    source_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    work_ref: str = Field(min_length=3, max_length=300)
    version_ref: str = Field(min_length=3, max_length=300)

    @field_validator("work_ref", "version_ref")
    @classmethod
    def printable(cls, value):
        if any(ord(char) < 32 for char in value):
            raise ValueError("Kimlik referansları kontrol karakteri içeremez")
        return value


class RelationshipInput(StrictInput):
    expected_revision: StrictInt = Field(ge=0, le=MAX_EVENTS)
    expected_source_revisions: dict[str, StrictInt]
    classification: Literal["same_work_same_version", "same_work_different_version", "different_work", "unresolved"]
    rationale: str = Field(min_length=3, max_length=4000)
    identities: list[IdentityInput] = Field(default_factory=list, max_length=2)
    comparison: ComparisonInput
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=10)
    effort: ReviewEffort | None = None

    @model_validator(mode="after")
    def support(self):
        pins = self.expected_source_revisions
        if len(pins) != 2 or any(not SHA256.fullmatch(key) or not 0 <= rev <= 1000 for key, rev in pins.items()):
            raise ValueError("İki tam kaynak inceleme sürümü gereklidir")
        if len({(item.reference, item.sha256) for item in self.evidence_refs}) != len(self.evidence_refs):
            raise ValueError("Kanıt referansları tekrarlanamaz")
        if self.classification == "unresolved":
            if self.identities:
                raise ValueError("Çözümlenmemiş ilişki kesin kimlik içeremez")
            return self
        if len(self.identities) != 2 or {item.source_id for item in self.identities} != set(pins):
            raise ValueError("Her iki kaynak için açık eser ve sürüm referansı gereklidir")
        a, b = self.identities
        same_work, same_version = a.work_ref == b.work_ref, a.version_ref == b.version_ref
        valid = {"same_work_same_version": same_work and same_version,
                 "same_work_different_version": same_work and not same_version,
                 "different_work": not same_work}
        if not valid[self.classification]:
            raise ValueError("Kimlik referansları ilişki sınıflandırmasıyla tutarlı olmalıdır")
        if not any(item.sha256 != self.comparison.evidence_sha256 for item in self.evidence_refs):
            raise ValueError("Karşılaştırmadan ayrı en az bir insan inceleme dayanağı gereklidir")
        return self


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _error():
    return HTTPException(409, "Kaynak ilişki kaydı veya dayanakları doğrulanamadı; yeniden açın")


def _pair(request, source_id, other_source_id, user):
    if source_id == other_source_id:
        raise HTTPException(422, "İki farklı kaynak paketi seçin")
    left = reviews._package(request, source_id, user)
    right = reviews._package(request, other_source_id, user)
    packages = sorted([left, right], key=lambda package: package.detail["id"])
    pair_id = digest(_canonical([package.detail["id"] for package in packages]))
    return left, right, packages, pair_id


def _source_states(store, session, packages, firm_id, *, lock=False):
    result = {}
    for package in packages:  # Canonical ordering prevents opposite-pair lock inversion.
        query = select(reviews.SourceReviewHead).where(
            reviews.SourceReviewHead.firm_id == firm_id,
            reviews.SourceReviewHead.source_id == package.detail["id"])
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        head = session.scalar(query)
        projection = reviews._projection(store, head, package)
        reviews._history(store, session, head)
        identity = projection["assessments"].get("source_identity")
        result[package.detail["id"]] = {"revision": head.revision if head else 0,
                                       "assigned_to": projection["assigned_to"],
                                       "identity_assessment": identity}
    return result


def _head(session, firm_id, pair_id):
    return session.scalar(select(SourceRelationshipHead).where(
        SourceRelationshipHead.firm_id == firm_id, SourceRelationshipHead.pair_id == pair_id))


def _comparison(left, right, selection):
    try:
        value = compare_sources(left, right, **selection.model_dump(exclude={"evidence_sha256"}))
    except SourceComparisonUnavailable:
        raise HTTPException(422, "Karşılaştırma pasajları veya pencereleri geçersiz") from None
    evidence_json = _canonical(value)
    if digest(evidence_json) != selection.evidence_sha256:
        raise _error()
    return {"evidence_json": evidence_json, "evidence_sha256": selection.evidence_sha256}


def _ledger(store, session, head, packages, pair_id):
    if head is None:
        return []
    if type(head.revision) is not int or not 1 <= head.revision <= MAX_EVENTS:
        raise _error()
    bindings = [reviews._binding(package) for package in packages]
    context = {"firm_id": head.firm_id, "head_id": head.id, "pair_id": pair_id, "revision": head.revision}
    projection = reviews._decode(store, head)
    if set(projection) != {"context", "bindings", "latest"} or projection["context"] != context or projection["bindings"] != bindings:
        raise _error()
    rows = list(session.scalars(select(SourceRelationshipEvent).where(
        SourceRelationshipEvent.head_id == head.id, SourceRelationshipEvent.firm_id == head.firm_id
    ).order_by(SourceRelationshipEvent.revision.desc()).limit(MAX_EVENTS + 1)))
    if [row.revision for row in rows] != list(range(head.revision, 0, -1)):
        raise _error()
    history = []
    by_id = {package.detail["id"]: package for package in packages}
    source_history = {}
    for ident, package in by_id.items():
        source_head = reviews._head(session, head.firm_id, ident)
        reviews._projection(store, source_head, package)
        pins, owner, assessment = {}, None, None
        for source_event in reversed(reviews._history(store, session, source_head)):
            if source_event["event_type"] == "claim":
                owner = source_event["reviewer"]
            elif source_event["event_type"] == "release":
                owner = None
            elif source_event["category"] == "source_identity":
                assessment = source_event
            pins[source_event["revision"]] = {"revision": source_event["revision"],
                                               "assigned_to": owner, "identity_assessment": assessment}
        source_history[ident] = pins
    for row in rows:
        data = reviews._decode(store, row)
        expected_context = {**context, "revision": row.revision, "event_id": row.id}
        if set(data) != {"context", "bindings", "event"} or data["context"] != expected_context or data["bindings"] != bindings:
            raise _error()
        event = data["event"]
        try:
            fields = {"id", "revision", "reviewer", "created_at", "input", "source_reviews", "comparison_evidence", "source_order"}
            if (type(event) is not dict or set(event) != fields or event["id"] != row.id
                    or event["revision"] != row.revision or event["created_at"] != row.created_at
                    or not reviews._valid_reviewer(event["reviewer"])
                    or datetime.fromisoformat(event["created_at"]).tzinfo is None
                    or sorted(event["source_order"]) != sorted(by_id)):
                raise ValueError()
            body = RelationshipInput.model_validate(event["input"])
            if body.expected_revision != row.revision - 1 or set(body.expected_source_revisions) != set(by_id):
                raise ValueError()
            for source_id, pin in event["source_reviews"].items():
                if (set(pin) != {"revision", "assigned_to", "identity_assessment"}
                        or body.expected_source_revisions[source_id] != pin["revision"]
                        or source_history[source_id].get(pin["revision"]) != pin
                        or not reviews._valid_reviewer(pin["assigned_to"])
                        or pin["assigned_to"]["id"] != event["reviewer"]["id"]):
                    raise ValueError()
                assessment = pin["identity_assessment"]
                if (assessment is not None and (not reviews._valid_event(assessment)
                        or assessment.get("category") != "source_identity" or assessment["revision"] > pin["revision"])):
                    raise ValueError()
                if body.classification != "unresolved" and (assessment is None or assessment["decision"] != "accepted"):
                    raise ValueError()
            if set(event["source_reviews"]) != set(by_id):
                raise ValueError()
            a, b = [by_id[ident] for ident in event["source_order"]]
            if event["comparison_evidence"] != _comparison(a, b, body.comparison):
                raise ValueError()
        except (KeyError, TypeError, ValueError, ValidationError, HTTPException):
            raise _error() from None
        history.append(event)
    if projection["latest"] != history[0]:
        raise _error()
    return history


def _state(packages, pair_id, revision, sources, history, user):
    latest = history[0] if history else None
    stale = latest is not None and latest["source_reviews"] != sources
    identity_ready = all(value["identity_assessment"] is not None and
                         value["identity_assessment"]["decision"] == "accepted" for value in sources.values())
    return {"schema_version": "source-relationship-state-v1", "pair_id": pair_id,
            "source_ids": [package.detail["id"] for package in packages], "revision": revision,
            "source_reviews": sources, "latest": latest, "history": history[:HISTORY_LIMIT],
            "history_truncated": len(history) > HISTORY_LIMIT, "stale": stale,
            "can_record": all(value["assigned_to"] is not None and value["assigned_to"]["id"] == user.id for value in sources.values()),
            "identity_reviews_ready": identity_ready,
            "resolved_for_handoff": bool(latest and not stale and identity_ready and latest["input"]["classification"] != "unresolved"),
            "confidentiality": "firm_confidential", "signed": False, "publication_eligible": False,
            "independent_originals_verified": False, "current_law_verified": False, "limitations": LIMITATIONS}


def _read(request, source_id, other_source_id, user):
    _, _, packages, pair_id = _pair(request, source_id, other_source_id, user)
    store = request.app.state.store
    with store.session() as session:
        sources = _source_states(store, session, packages, user.firm_id)
        head = _head(session, user.firm_id, pair_id)
        history = _ledger(store, session, head, packages, pair_id)
        result = _state(packages, pair_id, head.revision if head else 0, sources, history, user)
    with store.session() as session:
        if _source_states(store, session, packages, user.firm_id) != sources:
            raise _error()
    reviews._authorize(request, user)
    return result


def _mutate(request, source_id, other_source_id, body, user):
    left, right, packages, pair_id = _pair(request, source_id, other_source_id, user)
    if set(body.expected_source_revisions) != {package.detail["id"] for package in packages}:
        raise HTTPException(422, "İnceleme sürümleri seçili iki kaynağa ait olmalıdır")
    evidence = _comparison(left, right, body.comparison)
    store = request.app.state.store
    try:
        with store.session() as session:
            current = reviews._lock_identity(session, request, user)
            authorized_role = current.role
            sources = _source_states(store, session, packages, user.firm_id, lock=True)
            if body.expected_source_revisions != {key: value["revision"] for key, value in sources.items()}:
                raise _error()
            if not all(value["assigned_to"] and value["assigned_to"]["id"] == current.id for value in sources.values()):
                raise HTTPException(409, "Karar kaydetmeden önce iki kaynak incelemesini de üstlenin")
            if body.classification != "unresolved" and not all(value["identity_assessment"] and
                    value["identity_assessment"]["decision"] == "accepted" for value in sources.values()):
                raise HTTPException(409, "Çözümleme için iki kaynak kimliği incelemesi de kabul edilmiş olmalıdır")
            head = _head(session, current.firm_id, pair_id)
            revision = head.revision if head else 0
            if revision != body.expected_revision or revision >= MAX_EVENTS:
                raise _error()
            history = _ledger(store, session, head, packages, pair_id)
            event = {"id": uid(), "revision": revision + 1, "reviewer": {"id": current.id, "name": current.name},
                     "created_at": now(), "input": body.model_dump(), "source_reviews": sources,
                     "source_order": [source_id, other_source_id], "comparison_evidence": evidence}
            head_id = head.id if head else uid()
            bindings = [reviews._binding(package) for package in packages]
            context = {"firm_id": current.firm_id, "head_id": head_id, "pair_id": pair_id, "revision": revision + 1}
            projection = {"context": context, "bindings": bindings, "latest": event}
            if head is None:
                head = SourceRelationshipHead(id=head_id, firm_id=current.firm_id, pair_id=pair_id,
                                              revision=1, payload=store.encode(projection))
                session.add(head)
                session.flush()
            else:
                changed = session.execute(update(SourceRelationshipHead).where(
                    SourceRelationshipHead.id == head.id, SourceRelationshipHead.firm_id == current.firm_id,
                    SourceRelationshipHead.revision == revision).values(
                    revision=revision + 1, payload=store.encode(projection)).execution_options(synchronize_session=False))
                if changed.rowcount != 1:
                    raise _error()
            session.add(SourceRelationshipEvent(id=event["id"], head_id=head_id, firm_id=current.firm_id,
                                               revision=revision + 1, created_at=event["created_at"], payload=store.encode({
                                                   "context": {**context, "event_id": event["id"]}, "bindings": bindings, "event": event})))
            if reviews._lock_identity(session, request, user).role != authorized_role:
                raise HTTPException(403, "İnceleme yetkisi değişti")
            if _source_states(store, session, packages, current.firm_id, lock=True) != sources:
                raise _error()
            reviews._authorize(request, user)
            session.commit()
            return _state(packages, pair_id, revision + 1, sources, [event, *history], user)
    except IntegrityError:
        raise _error() from None
    except OperationalError as exc:
        if getattr(exc.orig, "sqlite_errorcode", None) in {5, 6, 517}:
            raise _error() from None
        raise HTTPException(503, "Kaynak ilişki deposuna şu anda erişilemiyor") from None


def source_relationships_router():
    router = APIRouter(prefix="/api/v1/public-sources", tags=["source-relationship"])

    def authorize(request: Request):
        return reviews._authorize(request)

    @router.get("/{source_id}/relationship")
    def read(source_id: str, request: Request, other_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"), user=Depends(authorize)):
        return _read(request, source_id, other_source_id, user)

    @router.post("/{source_id}/relationship")
    def record(source_id: str, body: RelationshipInput, request: Request,
               other_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"), user=Depends(authorize)):
        return _mutate(request, source_id, other_source_id, body, user)

    @router.get("/{source_id}/relationship/export")
    def export(source_id: str, request: Request, other_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"), user=Depends(authorize)):
        state = _read(request, source_id, other_source_id, user)
        payload = _canonical({"schema_version": "source-relationship-dossier-v1", "exported_at": now(), "review": state})
        reviews._authorize(request, user)
        return Response(payload, media_type="application/json", headers={
            "Content-Disposition": f'attachment; filename="source-relationship-{state["pair_id"]}.json"',
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    return router
