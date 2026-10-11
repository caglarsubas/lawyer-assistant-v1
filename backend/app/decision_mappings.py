"""Accountable, encrypted decision occurrence reviews; never graph publication."""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, StrictInt, ValidationError, field_validator, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from . import source_reviews as reviews
from .db import now, uid
from .decision_mapping_models import DecisionMappingEvent, DecisionMappingHead
from .jurisprudence_candidates import find_occurrences
from .provision_mappings import _source_review as _base_source_review
from .provision_mappings import _span
from .source_review_models import SourceReviewHead
from .source_reviews import EvidenceReference, StrictInput

MAX_EVENTS = 1000
MAX_MAPPINGS = 200
HISTORY_LIMIT = 50
KINDS = Literal["application_number", "case_number", "decision_number", "decision_date", "publication_date",
                "instrument_number_reference", "article_number_reference"]
DECISIONS = Literal["accepted", "needs_changes", "rejected"]
LIMITATIONS = [
    "Karar eşlemeleri şifreli ve büroya özel insan incelemeleridir; kaynak veya graf değiştirilmez.",
    "İnsan tarafından girilen referanslar kanonik kimlik kaydı değildir; bağımsız çözümleme gerekir.",
    "Atıf, uygulama, bağlayıcılık, kesinleşme ve hukuki etki farklıdır; son üçü bu iş akışında çözümlenmez.",
    "Kaynak incelemesindeki her değişiklik kabul edilmiş eşlemeleri yeniden incelemeye açar.",
]


class MutationInput(StrictInput):
    expected_revision: StrictInt = Field(ge=0, le=1000)
    expected_source_review_revision: StrictInt = Field(ge=0, le=1000)
    rationale: str = Field(min_length=3, max_length=4000)


class ProposalInput(MutationInput):
    passage_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")


class Resolution(StrictInput):
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(gt=0)
    occurrence_role: Literal["own_decision", "cited_authority", "editorial", "unknown"]
    proceeding_ref: str | None = Field(min_length=3, max_length=300)
    decision_ref: str | None = Field(min_length=3, max_length=300)
    institution_ref: str | None = Field(min_length=3, max_length=300)
    target_ref: str | None = Field(min_length=3, max_length=300)
    target_version_ref: str | None = Field(min_length=3, max_length=300)
    event_role: Literal["decision", "publication", "unknown"]
    event_date: str | None
    authority_treatment: Literal["cites", "quotes", "applies", "distinguishes", "unknown"]

    @field_validator("proceeding_ref", "decision_ref", "institution_ref", "target_ref", "target_version_ref")
    @classmethod
    def printable(cls, value):
        if value is not None and (not value.strip() or any(ord(char) < 32 for char in value)):
            raise ValueError("Referans boş veya kontrol karakterli olamaz")
        return value

    @field_validator("event_date")
    @classmethod
    def canonical_date(cls, value):
        if value is not None and date.fromisoformat(value).isoformat() != value:
            raise ValueError("Tarih YYYY-MM-DD biçiminde veya bilinmiyorsa null olmalıdır")
        return value

    @model_validator(mode="after")
    def interval(self):
        if self.end <= self.start or self.end - self.start > 20000:
            raise ValueError("Geçersiz dayanak aralığı")
        if self.occurrence_role == "own_decision" and not all((self.proceeding_ref, self.decision_ref, self.institution_ref)):
            raise ValueError("Belgenin kendi kararı için yargılama, karar ve kurum ayrı referanslar gerektirir")
        if (self.target_version_ref and not self.target_ref) or (self.event_date and self.event_role == "unknown"):
            raise ValueError("Sürüm veya tarih rolü eksik")
        if self.authority_treatment != "unknown" and (self.occurrence_role != "cited_authority" or not self.target_ref):
            raise ValueError("Atıf işlemi için atıf rolü ve hedef referansı gerekir")
        return self


def _candidate(package, passage_id, candidate_id, lookup=None):
    try:
        if lookup is None:
            lookup = {}
        if passage_id not in lookup:
            lookup[passage_id] = {item["id"]: item for item in find_occurrences(package, passage_id)["items"]}
        return lookup[passage_id][candidate_id]
    except (KeyError, ValueError):
        raise HTTPException(422, "Anma adayı bu kaynak ve pasaja ait değil") from None


def _validate_resolution(resolution, candidate, package):
    details = _span(package, resolution.start, resolution.end)
    if not (resolution.start <= candidate["start"] < candidate["end"] <= resolution.end
            and details["non_whitespace_covered"]):
        raise HTTPException(422, "Dayanak aralığı anmayı ve doğrulanmış metni kapsamalıdır")
    if resolution.occurrence_role == "own_decision" and candidate["kind"].endswith("_reference"):
        raise HTTPException(422, "Norm anması belgenin kendi karar kimliği olamaz")
    expected_role = {"decision_date": "decision", "publication_date": "publication"}.get(candidate["kind"])
    if resolution.event_role != "unknown" and resolution.event_role != expected_role:
        raise HTTPException(422, "Tarih rolü anma türüyle uyuşmuyor")
    if resolution.event_date is not None and (expected_role is None or resolution.event_date != candidate["parsed_value"]):
        raise HTTPException(422, "Tarih seçili anmanın geçerli takvim değeriyle uyuşmuyor")
    return details


class ReviewInput(MutationInput):
    decision: DECISIONS
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=10)
    resolution: Resolution | None

    @model_validator(mode="after")
    def evidence(self):
        if self.decision == "accepted" and (not self.evidence_refs or self.resolution is None):
            raise ValueError("Kabul için karar çözümlemesi ve kanıt referansı gerekir")
        if self.decision != "accepted" and self.resolution is not None:
            raise ValueError("Yalnızca kabul edilen eşleme kimlik çözümlemesi içerebilir")
        if len({(item.reference, item.sha256) for item in self.evidence_refs}) != len(self.evidence_refs):
            raise ValueError("Kanıt referansları tekrarlanamaz")
        return self


def _error():
    return HTTPException(409, "Karar eşleme kaydı bütünlük denetiminden geçmedi")


def _source_review(store, session, package, firm_id, *, lock=False):
    result = _base_source_review(store, session, package, firm_id, lock=lock)
    head = session.scalar(select(SourceReviewHead).where(
        SourceReviewHead.firm_id == firm_id, SourceReviewHead.source_id == package.detail["id"]))
    assessments = reviews._projection(store, head, package)["assessments"]
    rights = assessments.get("rights", {})
    result["export_allowed"] = rights.get("decision") == "accepted" and {
        "local_processing", "internal_display", "export"}.issubset(rights.get("permitted_uses", []))
    result["reviewed_passage_ids"] = sorted(assessments.get("extraction", {}).get("passage_ids", []))
    return result


def _head(session, firm_id, source_id):
    return session.scalar(select(DecisionMappingHead).where(
        DecisionMappingHead.firm_id == firm_id, DecisionMappingHead.source_id == source_id))


def _valid_snapshot(snapshot, package, lookup=None):
    fields = {"passage_id", "candidate", "status", "resolution", "reviewed_source_revision"}
    if not isinstance(snapshot, dict) or set(snapshot) != fields:
        return False
    try:
        candidate = snapshot["candidate"]
        if candidate != _candidate(package, snapshot["passage_id"], candidate["id"], lookup):
            return False
        if snapshot["status"] == "machine_proposed":
            return snapshot["resolution"] is None and snapshot["reviewed_source_revision"] is None
        if snapshot["status"] not in {"accepted", "needs_changes", "rejected"}:
            return False
        if type(snapshot["reviewed_source_revision"]) is not int or not 1 <= snapshot["reviewed_source_revision"] <= 1000:
            return False
        if snapshot["status"] == "accepted":
            _validate_resolution(Resolution.model_validate(snapshot["resolution"]), candidate, package)
            return True
        return snapshot["resolution"] is None
    except (HTTPException, ValidationError, TypeError, ValueError, KeyError):
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
            ReviewInput.model_validate({**body, "decision": event["decision"], "evidence_refs": event["evidence_refs"],
                                                "resolution": event["snapshot"]["resolution"]})
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
    rows = session.scalars(select(DecisionMappingEvent).where(
        DecisionMappingEvent.head_id == head.id, DecisionMappingEvent.firm_id == head.firm_id,
    ).order_by(DecisionMappingEvent.revision.desc()).limit(MAX_EVENTS + 1))
    events = [_event_header(store, row, head, package) for row in rows]
    if [item["revision"] for item in events] != list(range(head.revision, 0, -1)):
        raise _error()
    latest = {}
    for event in events:
        latest.setdefault(event["mapping_id"], event)
    if latest != projection["mappings"]:
        raise _error()
    lookup = {}
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
            "assigned_to": source_review["assigned_to"], "source_review_ready": source_review["ready"], "export_allowed": source_review["export_allowed"], "items": items,
            "history": history, "history_truncated": revision > len(history),
            "handoff_ready": bool(items) and source_review["ready"] and all(
                item["status"] == "accepted" and not item["stale"] for item in items),
            "publication_eligible": False, "limitations": LIMITATIONS}


def _transition(package, projection, body, mapping_id, source_review):
    mappings = projection["mappings"]
    if isinstance(body, ProposalInput):
        if len(mappings) >= MAX_MAPPINGS:
            raise HTTPException(409, "Kaynak başına karar eşleme sınırına ulaşıldı")
        candidate = _candidate(package, body.passage_id, body.candidate_id)
        if any(event["snapshot"]["candidate"]["id"] == candidate["id"] for event in mappings.values()):
            raise HTTPException(409, "Aynı anma zaten eşleme listesinde")
        return {"passage_id": body.passage_id, "candidate": candidate, "status": "machine_proposed",
                "resolution": None, "reviewed_source_revision": None}
    if mapping_id not in mappings:
        raise HTTPException(404, "Karar eşlemesi bulunamadı")
    snapshot = {**mappings[mapping_id]["snapshot"], "status": body.decision,
                "resolution": None, "reviewed_source_revision": source_review["revision"]}
    if body.decision == "accepted":
        if not source_review["ready"]:
            raise HTTPException(409, "Dört kaynak incelemesi ve yerel işleme/gösterim izinleri kabul edilmelidir")
        details = _validate_resolution(body.resolution, snapshot["candidate"], package)
        if not set(details["passage_ids"]).issubset(source_review["reviewed_passage_ids"]):
            raise HTTPException(409, "Dayanak pasajları metin çıkarımı incelemesinde onaylanmalıdır")
        snapshot["resolution"] = body.resolution.model_dump()
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
                raise HTTPException(409, "Karar eşlemeleri değişti; güncel sürümü açın")
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
            projection["mappings"][mapping_id] = event
            head_id = head.id if head else uid()
            context = {"firm_id": current.firm_id, "head_id": head_id, "revision": revision + 1}
            projection["context"] = context
            if head is None:
                head = DecisionMappingHead(id=head_id, firm_id=current.firm_id, source_id=source_id,
                                            revision=1, payload=store.encode(projection))
                session.add(head)
                session.flush()
            else:
                changed = session.execute(update(DecisionMappingHead).where(
                    DecisionMappingHead.id == head.id, DecisionMappingHead.firm_id == current.firm_id,
                    DecisionMappingHead.revision == body.expected_revision).values(
                    revision=revision + 1, payload=store.encode(projection)).execution_options(synchronize_session=False))
                if changed.rowcount != 1:
                    raise HTTPException(409, "Karar eşlemeleri eşzamanlı değişti; güncel sürümü açın")
            session.add(DecisionMappingEvent(id=event["id"], head_id=head_id, firm_id=current.firm_id,
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
        raise HTTPException(409, "Karar eşlemeleri eşzamanlı değişti; güncel sürümü açın") from None
    except OperationalError as exc:
        if getattr(exc.orig, "sqlite_errorcode", None) in {5, 6, 517}:
            raise HTTPException(409, "Karar eşlemeleri eşzamanlı değişti; güncel sürümü açın") from None
        raise HTTPException(503, "Karar eşleme deposuna şu anda erişilemiyor") from None


def decision_mappings_router():
    router = APIRouter(prefix="/api/v1/public-sources", tags=["decision-mapping"])

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

    @router.get("/{source_id}/decision-mappings")
    def mappings(source_id: str, request: Request, user=Depends(authorize)):
        return read(request, source_id, user)

    @router.post("/{source_id}/decision-mappings")
    def propose(source_id: str, body: ProposalInput, request: Request, user=Depends(authorize)):
        return _mutate(request, source_id, body, user)

    @router.post("/{source_id}/decision-mappings/{mapping_id}/review")
    def review(source_id: str, mapping_id: str, body: ReviewInput, request: Request, user=Depends(authorize)):
        return _mutate(request, source_id, body, user, mapping_id)

    from .decision_dossier import DossierInput, build_dossier

    @router.post("/{source_id}/decision-mappings/dossier")
    def dossier(source_id: str, body: DossierInput, request: Request, user=Depends(authorize)):
        from .public_sources import PublicSourceError
        try:
            result = build_dossier(request, source_id, body, user)
        except (PublicSourceError, OSError):
            raise HTTPException(409, "Kaynak bütünlüğü dışa aktarma sırasında doğrulanamadı") from None
        reviews._authorize(request, user)
        return result

    return router
