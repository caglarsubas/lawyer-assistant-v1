"""Exact, reviewable source-to-provision mapping with no publication side effects."""

import json
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field, StrictInt, ValidationError, field_validator, model_serializer, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from . import source_reviews as reviews
from .db import now, uid
from .provision_candidates import CandidateLookup, candidate_for_id, find_candidates, span_details
from .provision_mapping_models import ProvisionMappingEvent, ProvisionMappingHead
from .source_review_models import SourceReviewHead
from .source_reviews import EvidenceReference, StrictInput

MAX_EVENTS = 1000
MAX_MAPPINGS = 200
HISTORY_LIMIT = 50
KINDS = Literal["article", "temporary_article", "additional_article"]
DECISIONS = Literal["accepted", "needs_changes", "rejected"]
LIMITATIONS = [
    "Eşlemeler kuruma özel inceleme kayıtlarıdır; kaynak paketini veya yayımlanmış grafı değiştirmez.",
    "Madde sınırları ve kimlik referansları insan incelemesi gerektirir; güncel hukuk veya uygulanabilirlik varsayılmaz.",
    "İnceleme dosyası imzasızdır; bağımsız yayımlama incelemesi ve kullanım kapsamı kontrolü gerekir.",
    "Kaynak incelemesinin her değişikliği kabul edilmiş eşlemelerin yeniden incelenmesini gerektirir.",
]


class MutationInput(StrictInput):
    expected_revision: StrictInt = Field(ge=0, le=1000)
    expected_source_review_revision: StrictInt = Field(ge=0, le=1000)
    rationale: str = Field(min_length=3, max_length=4000)


class ProposalInput(MutationInput):
    candidate_id: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(gt=0)
    kind: KINDS
    label: str = Field(min_length=1, max_length=200)

    @field_validator("label")
    @classmethod
    def printable(cls, value):
        if any(ord(char) < 32 for char in value):
            raise ValueError("Madde etiketi kontrol karakteri içeremez")
        return value


class OpenEndedValidity(StrictInput):
    checked_through: str
    evidence_start: StrictInt = Field(ge=0)
    evidence_end: StrictInt = Field(gt=0)

    @field_validator("checked_through")
    @classmethod
    def canonical_date(cls, value):
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("Denetim tarihi YYYY-MM-DD biçiminde olmalıdır")
        return value

    @model_validator(mode="after")
    def evidence_span(self):
        if self.evidence_end <= self.evidence_start or self.evidence_end - self.evidence_start > 20000:
            raise ValueError("Geçersiz yürürlük dayanağı metin aralığı")
        return self


class Resolution(StrictInput):
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(gt=0)
    instrument_ref: str = Field(min_length=3, max_length=300)
    provision_ref: str = Field(min_length=3, max_length=300)
    provision_version_ref: str = Field(min_length=3, max_length=300)
    text_role: Literal["operative_text", "amendment_text", "transitional_text", "quoted_text", "unknown"]
    valid_from: str | None
    valid_until: str | None
    open_ended_validity: OpenEndedValidity | None = None

    @field_validator("open_ended_validity")
    @classmethod
    def explicit_review(cls, value):
        if value is None:
            raise ValueError("Açık uçlu yürürlük incelemesi nesne olmalı veya alan bulunmamalıdır")
        return value

    @model_serializer(mode="wrap")
    def preserve_legacy_resolution(self, handler):
        result = handler(self)
        # Immutable events and sealed preparation inputs retain their exact old
        # shape. Do not remove the existing, meaningful null date fields.
        if "open_ended_validity" not in self.model_fields_set:
            result.pop("open_ended_validity", None)
        return result

    @field_validator("instrument_ref", "provision_ref", "provision_version_ref")
    @classmethod
    def printable(cls, value):
        if any(ord(char) < 32 for char in value):
            raise ValueError("Referans kontrol karakteri içeremez")
        return value

    @field_validator("valid_from", "valid_until")
    @classmethod
    def canonical_date(cls, value):
        if value is not None and date.fromisoformat(value).isoformat() != value:
            raise ValueError("Tarih YYYY-MM-DD biçiminde veya bilinmiyorsa null olmalıdır")
        return value

    @model_validator(mode="after")
    def interval(self):
        if self.end <= self.start or self.end - self.start > 20000:
            raise ValueError("Geçersiz madde metni aralığı")
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValueError("Geçerlilik tarihleri ters olamaz")
        if self.open_ended_validity is not None:
            if (self.valid_from is None or self.valid_until is not None
                    or self.open_ended_validity.checked_through < self.valid_from):
                raise ValueError("Açık uçlu yürürlük için başlangıç bilinmeli ve denetim başlangıçtan önce olmamalıdır")
        return self


def validate_open_ended_validity(resolution, package, recorded_at):
    """Verify an explicit temporal review, never infer it from a missing end."""
    support = resolution.open_ended_validity
    if support is None:
        return
    recorded = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
    if (recorded.tzinfo is None
            or date.fromisoformat(support.checked_through) > recorded.astimezone(timezone.utc).date()):
        raise ValueError("Yürürlük denetim tarihi inceleme olayının UTC tarihinden sonra olamaz")
    details = span_details(package, support.evidence_start, support.evidence_end)
    if not details["span"]["text"].strip() or not details["non_whitespace_covered"]:
        raise ValueError("Açık uçlu yürürlük dayanağı doğrulanmış pasajlarla tam kapsanmalıdır")


class ReviewInput(MutationInput):
    decision: DECISIONS
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=10)
    resolution: Resolution | None

    @model_validator(mode="after")
    def evidence(self):
        if self.decision == "accepted" and (not self.evidence_refs or self.resolution is None):
            raise ValueError("Kabul için madde çözümlemesi ve kanıt referansı gerekir")
        if self.decision != "accepted" and self.resolution is not None:
            raise ValueError("Yalnızca kabul edilen eşleme kimlik çözümlemesi içerebilir")
        if len({(item.reference, item.sha256) for item in self.evidence_refs}) != len(self.evidence_refs):
            raise ValueError("Kanıt referansları tekrarlanamaz")
        return self


def _error():
    return HTTPException(409, "Madde eşleme kaydı bütünlük denetiminden geçmedi")


def _source_review(store, session, package, firm_id, *, lock=False):
    query = select(SourceReviewHead).where(
        SourceReviewHead.firm_id == firm_id, SourceReviewHead.source_id == package.detail["id"])
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    head = session.scalar(query)
    projection = reviews._projection(store, head, package)
    reviews._history(store, session, head)
    assessments = projection["assessments"]
    ready = (set(assessments) == set(reviews.CATEGORIES)
             and all(item["decision"] == "accepted" for item in assessments.values())
             and {"local_processing", "internal_display"}.issubset(assessments["rights"]["permitted_uses"]))
    return {"revision": head.revision if head else 0, "assigned_to": projection["assigned_to"], "ready": ready}


def _head(session, firm_id, source_id):
    return session.scalar(select(ProvisionMappingHead).where(
        ProvisionMappingHead.firm_id == firm_id, ProvisionMappingHead.source_id == source_id))


def _span(package, start, end):
    try:
        result = span_details(package, start, end)
        if not result["span"]["text"].strip():
            raise ValueError("Empty provision text")
        return {key: result[key] for key in ("span", "passage_ids", "non_whitespace_covered")}
    except ValueError:
        raise HTTPException(422, "Madde aralığı doğrulanmış metin içinde ve en çok 20.000 karakter olmalıdır") from None


def _candidate(package, candidate_id, kind, label, span=None, lookup=None):
    if candidate_id is None:
        return
    try:
        candidate = lookup.get(candidate_id) if lookup is not None else candidate_for_id(package, candidate_id)
    except ValueError:
        raise HTTPException(422, "Madde adayı bu kaynak paketine ait değil") from None
    if candidate["kind"] != kind or candidate["label"] != label:
        raise HTTPException(422, "Aday türü ve etiketi kaynakla eşleşmelidir")
    if span and not (span["start"] <= candidate["heading"]["start"] < candidate["heading"]["end"] <= span["end"]):
        raise HTTPException(422, "Önerilen metin aralığı aday başlığını içermelidir")


def _valid_snapshot(snapshot, package, lookup=None):
    fields = {"candidate_id", "kind", "label", "span", "passage_ids", "non_whitespace_covered", "status",
              "resolution", "reviewed_source_revision"}
    if not isinstance(snapshot, dict) or set(snapshot) != fields or not isinstance(snapshot["span"], dict):
        return False
    try:
        span = snapshot["span"]
        proposal = ProposalInput.model_validate({"expected_revision": 0, "expected_source_review_revision": 0,
                                               "rationale": "Integrity validation", "candidate_id": snapshot["candidate_id"],
                                               "kind": snapshot["kind"], "label": snapshot["label"],
                                               "start": span.get("start"), "end": span.get("end")})
        details = _span(package, proposal.start, proposal.end)
        if any(snapshot[key] != value for key, value in details.items()):
            return False
        _candidate(package, proposal.candidate_id, proposal.kind, proposal.label, span, lookup)
        if snapshot["status"] == "machine_proposed":
            return snapshot["resolution"] is None and snapshot["reviewed_source_revision"] is None
        if snapshot["status"] not in {"accepted", "needs_changes", "rejected"}:
            return False
        if type(snapshot["reviewed_source_revision"]) is not int or not 1 <= snapshot["reviewed_source_revision"] <= 1000:
            return False
        if snapshot["status"] == "accepted":
            resolution = Resolution.model_validate(snapshot["resolution"])
            return (resolution.start == span["start"] and resolution.end == span["end"]
                    and snapshot["non_whitespace_covered"] is True)
        return snapshot["resolution"] is None
    except (HTTPException, ValidationError, TypeError, ValueError):
        return False


def _event_header(store, row, head, package):
    payload = reviews._decode(store, row)
    event = payload.get("event")
    context = {"firm_id": head.firm_id, "head_id": head.id, "revision": row.revision, "event_id": row.id}
    fields = {"id", "revision", "mapping_id", "event_type", "reviewer", "created_at", "rationale", "decision",
              "evidence_refs", "source_review_revision", "snapshot"}
    if (set(payload) != {"context", "source_binding", "event"} or payload.get("context") != context
            or payload.get("source_binding") != reviews._binding(package) or not isinstance(event, dict)
            or set(event) != fields or event.get("id") != row.id or event.get("revision") != row.revision
            or event.get("created_at") != row.created_at or not reviews._valid_reviewer(event.get("reviewer"))
            or not isinstance(event.get("mapping_id"), str) or len(event["mapping_id"]) != 32
            or type(event["revision"]) is not int or not 1 <= event["revision"] <= MAX_EVENTS
            or type(event["source_review_revision"]) is not int or not 1 <= event["source_review_revision"] <= 1000):
        raise _error()
    return event


def _verified_event(event, package, lookup=None):
    if not _valid_snapshot(event["snapshot"], package, lookup):
        raise _error()
    try:
        if datetime.fromisoformat(event["created_at"]).tzinfo is None:
            raise ValueError("Missing timezone")
        body = {"expected_revision": event["revision"] - 1,
                "expected_source_review_revision": event["source_review_revision"], "rationale": event["rationale"]}
        if event["event_type"] == "propose":
            MutationInput.model_validate(body)
            if (event["decision"] is not None or event["evidence_refs"] != []
                    or event["snapshot"]["status"] != "machine_proposed"):
                raise ValueError("Invalid proposal event")
        elif event["event_type"] == "review":
            review = ReviewInput.model_validate({**body, "decision": event["decision"], "evidence_refs": event["evidence_refs"],
                                                "resolution": event["snapshot"]["resolution"]})
            if review.resolution is not None:
                validate_open_ended_validity(review.resolution, package, event["created_at"])
            if (event["snapshot"]["status"] != event["decision"]
                    or event["snapshot"]["reviewed_source_revision"] != event["source_review_revision"]):
                raise ValueError("Unbound decision")
        else:
            raise ValueError("Unknown event")
    except (TypeError, ValueError, ValidationError):
        raise _error() from None
    return event


def _projection(store, session, head, package):
    if head is None:
        return {"source_binding": reviews._binding(package), "mappings": {}}, []
    projection = reviews._decode(store, head)
    if (type(head.revision) is not int or not 1 <= head.revision <= MAX_EVENTS
            or set(projection) != {"source_binding", "context", "mappings"}
            or projection.get("source_binding") != reviews._binding(package)
            or projection.get("context") != {"firm_id": head.firm_id, "head_id": head.id, "revision": head.revision}
            or not isinstance(projection.get("mappings"), dict)
            or not 1 <= len(projection["mappings"]) <= MAX_MAPPINGS):
        raise _error()
    # Bounded header replay proves that projections are the latest events, not
    # merely some earlier valid acceptance. Old rejections cannot be hidden by
    # truncating the displayed history or replacing a projection with old data.
    rows = session.scalars(select(ProvisionMappingEvent).where(
        ProvisionMappingEvent.head_id == head.id, ProvisionMappingEvent.firm_id == head.firm_id,
    ).order_by(ProvisionMappingEvent.revision.desc()).limit(MAX_EVENTS + 1))
    events = [_event_header(store, row, head, package) for row in rows]
    if [item["revision"] for item in events] != list(range(head.revision, 0, -1)):
        raise _error()
    latest = {}
    for event in events:
        latest.setdefault(event["mapping_id"], event)
    if latest != projection["mappings"]:
        raise _error()
    lookup = CandidateLookup(package)
    checked = {event["id"] for event in events[:HISTORY_LIMIT]}
    history = [_verified_event(event, package, lookup) for event in events[:HISTORY_LIMIT]]
    for event in latest.values():
        if event["id"] not in checked:
            _verified_event(event, package, lookup)
    return projection, history


def _state(package, revision, source_review, projection, history):
    items = []
    for identifier, event in projection["mappings"].items():
        snapshot = event["snapshot"]
        stale = snapshot["status"] == "accepted" and snapshot["reviewed_source_revision"] != source_review["revision"]
        items.append({"id": identifier, **snapshot, "stale": stale, "last_event": event})
    return {"source": package.detail, "revision": revision, "source_review_revision": source_review["revision"],
            "assigned_to": source_review["assigned_to"], "source_review_ready": source_review["ready"], "items": items,
            "history": history, "history_truncated": revision > len(history),
            "handoff_ready": bool(items) and source_review["ready"] and all(
                item["status"] == "accepted" and not item["stale"] for item in items),
            "publication_eligible": False, "limitations": LIMITATIONS}


def _transition(package, projection, body, mapping_id, source_review):
    mappings = projection["mappings"]
    if isinstance(body, ProposalInput):
        if len(mappings) >= MAX_MAPPINGS:
            raise HTTPException(409, "Kaynak başına madde eşleme sınırına ulaşıldı")
        details = _span(package, body.start, body.end)
        _candidate(package, body.candidate_id, body.kind, body.label, details["span"])
        for event in mappings.values():
            existing = event["snapshot"]
            if (existing["kind"], existing["label"], existing["span"]["start"], existing["span"]["end"]) == (
                    body.kind, body.label, body.start, body.end):
                raise HTTPException(409, "Aynı madde metni zaten eşleme listesinde")
        return {"candidate_id": body.candidate_id, "kind": body.kind, "label": body.label, **details,
                "status": "machine_proposed", "resolution": None, "reviewed_source_revision": None}
    if mapping_id not in mappings:
        raise HTTPException(404, "Madde eşlemesi bulunamadı")
    snapshot = {**mappings[mapping_id]["snapshot"], "status": body.decision,
                "resolution": None, "reviewed_source_revision": source_review["revision"]}
    if body.decision == "accepted":
        if not source_review["ready"]:
            raise HTTPException(409, "Dört kaynak incelemesi ve yerel işleme/gösterim izinleri kabul edilmelidir")
        details = _span(package, body.resolution.start, body.resolution.end)
        _candidate(package, snapshot["candidate_id"], snapshot["kind"], snapshot["label"], details["span"])
        if not details["non_whitespace_covered"]:
            raise HTTPException(422, "Kabul edilen metnin tüm içeriği doğrulanmış pasajlarla kapsanmalıdır")
        snapshot.update(**details, resolution=body.resolution.model_dump())
    return snapshot


def _mutate(request, source_id, body, user, mapping_id=None):
    package = reviews._package(request, source_id, user)
    store = request.app.state.store
    try:
        with store.session() as session:
            current = reviews._lock_identity(session, request, user)
            authorized_role = current.role
            source_review = _source_review(store, session, package, current.firm_id, lock=True)
            if body.expected_source_review_revision != source_review["revision"]:
                raise HTTPException(409, "Kaynak incelemesi değişti; güncel sürümü açın")
            if not source_review["assigned_to"] or source_review["assigned_to"]["id"] != current.id:
                raise HTTPException(409, "Eşleme yapmadan önce kaynak incelemesini üstlenin")
            head = _head(session, current.firm_id, source_id)
            revision = head.revision if head else 0
            if body.expected_revision != revision:
                raise HTTPException(409, "Madde eşlemeleri değişti; güncel sürümü açın")
            if revision >= MAX_EVENTS:
                raise HTTPException(409, "Eşleme olay sınırına ulaşıldı; kayıt saklama yöneticisine başvurun")
            projection, history = _projection(store, session, head, package)
            mapping_id = mapping_id if isinstance(body, ReviewInput) else uid()
            snapshot = _transition(package, projection, body, mapping_id, source_review)
            event = {"id": uid(), "revision": revision + 1, "mapping_id": mapping_id,
                     "event_type": "propose" if isinstance(body, ProposalInput) else "review",
                     "reviewer": {"id": current.id, "name": current.name}, "created_at": now(),
                     "rationale": body.rationale, "decision": body.decision if isinstance(body, ReviewInput) else None,
                     "evidence_refs": [item.model_dump() for item in body.evidence_refs] if isinstance(body, ReviewInput) else [],
                     "source_review_revision": source_review["revision"], "snapshot": snapshot}
            if isinstance(body, ReviewInput) and body.resolution is not None:
                try:
                    validate_open_ended_validity(body.resolution, package, event["created_at"])
                except ValueError:
                    raise HTTPException(422, "Açık uçlu yürürlük tarihi veya doğrulanmış dayanak aralığı geçersiz") from None
            projection["mappings"][mapping_id] = event
            head_id = head.id if head else uid()
            context = {"firm_id": current.firm_id, "head_id": head_id, "revision": revision + 1}
            projection["context"] = context
            if head is None:
                head = ProvisionMappingHead(id=head_id, firm_id=current.firm_id, source_id=source_id,
                                            revision=1, payload=store.encode(projection))
                session.add(head)
                session.flush()
            else:
                changed = session.execute(update(ProvisionMappingHead).where(
                    ProvisionMappingHead.id == head.id, ProvisionMappingHead.firm_id == current.firm_id,
                    ProvisionMappingHead.revision == body.expected_revision).values(
                    revision=revision + 1, payload=store.encode(projection)).execution_options(synchronize_session=False))
                if changed.rowcount != 1:
                    raise HTTPException(409, "Madde eşlemeleri eşzamanlı değişti; güncel sürümü açın")
            session.add(ProvisionMappingEvent(id=event["id"], head_id=head_id, firm_id=current.firm_id,
                                             revision=revision + 1, created_at=event["created_at"],
                                             payload=store.encode({"context": {**context, "event_id": event["id"]},
                                                                   "source_binding": reviews._binding(package), "event": event})))
            result = _state(package, revision + 1, source_review, projection, [event, *history][:HISTORY_LIMIT])
            if reviews._lock_identity(session, request, user).role != authorized_role:
                raise HTTPException(403, "Eşleme sırasında yetkiniz değişti; güncel kaydı açın")
            # SQLite has no row locks; this second check also protects explicit demo mode.
            if _source_review(store, session, package, current.firm_id, lock=True) != source_review:
                raise HTTPException(409, "Kaynak incelemesi eşzamanlı değişti; güncel sürümü açın")
            session.commit()
            return result
    except IntegrityError:
        raise HTTPException(409, "Madde eşlemeleri eşzamanlı değişti; güncel sürümü açın") from None
    except OperationalError as exc:
        if getattr(exc.orig, "sqlite_errorcode", None) in {5, 6, 517}:
            raise HTTPException(409, "Madde eşlemeleri eşzamanlı değişti; güncel sürümü açın") from None
        raise HTTPException(503, "Madde eşleme deposuna şu anda erişilemiyor") from None


def provision_mappings_router():
    router = APIRouter(prefix="/api/v1/public-sources", tags=["provision-mapping"])

    def authorize(request: Request):
        return reviews._authorize(request)

    def read(request, source_id, user):
        package = reviews._package(request, source_id, user)
        store = request.app.state.store
        with store.session() as session:
            source_review = _source_review(store, session, package, user.firm_id)
            head = _head(session, user.firm_id, source_id)
            projection, history = _projection(store, session, head, package)
            result = _state(package, head.revision if head else 0, source_review, projection, history)
        # A fresh transaction avoids returning apparently current decisions from an old snapshot.
        with store.session() as session:
            if _source_review(store, session, package, user.firm_id) != source_review:
                raise HTTPException(409, "Kaynak incelemesi okuma sırasında değişti; güncel sürümü açın")
        reviews._authorize(request, user)
        return result

    @router.get("/{source_id}/provision-candidates")
    def candidates(source_id: str, request: Request, offset: int = Query(0, ge=0, le=500),
                   limit: int = Query(20, ge=1, le=20), user=Depends(authorize)):
        package = reviews._package(request, source_id, user)
        result = find_candidates(package, offset=offset, limit=limit)
        reviews._authorize(request, user)
        return result

    @router.get("/{source_id}/provision-mappings")
    def mappings(source_id: str, request: Request, user=Depends(authorize)):
        return read(request, source_id, user)

    @router.get("/{source_id}/provision-span")
    def span(source_id: str, request: Request, start: int = Query(..., ge=0),
             end: int = Query(..., gt=0), user=Depends(authorize)):
        package = reviews._package(request, source_id, user)
        result = {"source_id": source_id, "source_version_id": package.metadata.source_version_id,
                  "text_sha256": package.locators.text_sha256, **_span(package, start, end)}
        reviews._authorize(request, user)
        return result

    @router.post("/{source_id}/provision-mappings")
    def propose(source_id: str, body: ProposalInput, request: Request, user=Depends(authorize)):
        return _mutate(request, source_id, body, user)

    @router.post("/{source_id}/provision-mappings/{mapping_id}/review")
    def review(source_id: str, mapping_id: str, body: ReviewInput, request: Request, user=Depends(authorize)):
        return _mutate(request, source_id, body, user, mapping_id)

    @router.get("/{source_id}/provision-mappings/export")
    def export(source_id: str, request: Request, user=Depends(authorize)):
        state = read(request, source_id, user)
        payload = json.dumps({"schema_version": "provision-mapping-dossier-v1", "confidentiality": "firm_confidential",
                              "signed": False, "publication_eligible": False, "exported_at": now(), "mappings": state},
                             ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        reviews._authorize(request, user)
        return Response(payload, media_type="application/json", headers={
            "Content-Disposition": f'attachment; filename="provision-mappings-{source_id}.json"',
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    return router
