"""Accountable human review dossiers; no source promotion or publication authority."""

import hmac
import json
from datetime import datetime, timezone
from typing import Literal

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from .auth import authenticate
from .db import LoginSession, User, digest, now, uid
from .public_sources import SHA256, PublicSourceError, PublicSourceStore
from .source_review_models import SourceReviewEvent, SourceReviewHead

CATEGORIES = ("rights", "source_identity", "extraction", "legal")
MAX_EVENTS = 1000
HISTORY_LIMIT = 50
LIMITATIONS = [
    "Bu kayıt kuruma özeldir. İnceleme kaynak paketini değiştirmez ve araştırmaya açmaz.",
    "İnceleme dosyası imzasızdır; bağımsız graf yayımlama incelemesi ve kullanım kapsamı kontrolü gerekir.",
    "Kanıt referanslarının erişilebilirliği ve gerçekliği insan tarafından doğrulanmalıdır.",
    "Kabul kararı kaynağın güncel hukuk olduğunu veya her somut olaya uygulanacağını göstermez.",
]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class EvidenceReference(StrictInput):
    reference: str = Field(min_length=1, max_length=1000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("reference")
    @classmethod
    def printable(cls, value):
        if any(ord(char) < 32 for char in value):
            raise ValueError("Kanıt referansı kontrol karakteri içeremez")
        return value


class MutationInput(StrictInput):
    expected_revision: StrictInt = Field(ge=0, le=MAX_EVENTS)
    rationale: str = Field(min_length=3, max_length=4000)


class AssignmentInput(MutationInput):
    action: Literal["claim", "release"]


class AssessmentInput(MutationInput):
    category: Literal["rights", "source_identity", "extraction", "legal"]
    decision: Literal["accepted", "needs_changes", "rejected"]
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=10)
    passage_ids: list[str] = Field(default_factory=list, max_length=100)
    permitted_uses: list[Literal["storage", "local_processing", "internal_display", "indexing",
                                 "local_inference", "export"]] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def required_support(self):
        if self.decision == "accepted" and not self.evidence_refs:
            raise ValueError("Kabul kararı en az bir kanıt referansı gerektirir")
        if self.category == "extraction" and self.decision == "accepted" and not self.passage_ids:
            raise ValueError("Metin çıkarımı incelemesi en az bir kaynak pasajı gerektirir")
        if self.category == "rights" and self.decision == "accepted" and not self.permitted_uses:
            raise ValueError("Haklar kabulü için izin verilen kullanımları belirtin")
        if self.category != "rights" and self.permitted_uses:
            raise ValueError("Kullanım kapsamı yalnızca haklar incelemesinde belirtilebilir")
        if len(self.passage_ids) != len(set(self.passage_ids)) or len(self.permitted_uses) != len(set(self.permitted_uses)):
            raise ValueError("Pasajlar ve izin verilen kullanımlar tekrarlanamaz")
        for passage_id in self.passage_ids:
            if not 1 <= len(passage_id) <= 80:
                raise ValueError("Geçersiz pasaj kimliği")
        if len({(item.reference, item.sha256) for item in self.evidence_refs}) != len(self.evidence_refs):
            raise ValueError("Kanıt referansları tekrarlanamaz")
        return self


def _authorize(request, expected=None):
    user = authenticate(request)
    if user.role not in {"admin", "curator"}:
        raise HTTPException(403, "Kaynak incelemesi için küratör yetkisi gerekiyor")
    if expected is not None and (user.id != expected.id or user.firm_id != expected.firm_id):
        raise HTTPException(401, "Oturum veya kurum değişti; yeniden açın")
    return user


def _lock_identity(session, request, expected):
    """Hold account/session locks through commit; revocation cannot race a committed write."""
    current = session.scalar(select(User).where(User.id == expected.id).with_for_update()
                             .execution_options(populate_existing=True))
    token = request.cookies.get("la_session", "")
    login = session.scalar(select(LoginSession).where(LoginSession.token_hash == digest(token)).with_for_update()
                           .execution_options(populate_existing=True)) if token else None
    if (not current or not current.active or current.firm_id != expected.firm_id or not login
            or login.user_id != expected.id
            or datetime.fromisoformat(login.expires_at) <= datetime.now(timezone.utc)):
        raise HTTPException(401, "Oturum veya kurum değişti; yeniden açın")
    if current.role not in {"admin", "curator"}:
        raise HTTPException(403, "Kaynak incelemesi için küratör yetkisi gerekiyor")
    if not hmac.compare_digest(login.csrf, request.headers.get("x-csrf-token", "")):
        raise HTTPException(403, "CSRF doğrulaması başarısız")
    return current


def _package(request, source_id, user):
    if not SHA256.fullmatch(source_id):
        raise HTTPException(404, "Kaynak hazırlama kaydı bulunamadı")
    try:
        package = PublicSourceStore(request.app.state.settings.public_source_dir).verified_package(source_id)
    except (PublicSourceError, OSError):
        raise HTTPException(409, "Kaynak paketi yok veya bütünlük denetimi başarısız") from None
    _authorize(request, user)
    return package


def _binding(package):
    return {"source_id": package.detail["id"], "artifacts": package.detail["artifacts"]}


def _head(session, firm_id, source_id):
    return session.scalar(select(SourceReviewHead).where(
        SourceReviewHead.firm_id == firm_id, SourceReviewHead.source_id == source_id))


def _decode(store, record):
    try:
        data = store.decode(record)
        if not isinstance(data, dict):
            raise ValueError("Invalid review envelope")
        return data
    except (InvalidToken, ValueError, TypeError):
        raise HTTPException(409, "Kaynak inceleme kaydı bütünlük denetiminden geçmedi") from None


def _valid_reviewer(value):
    return (isinstance(value, dict) and set(value) == {"id", "name"}
            and isinstance(value["id"], str) and 1 <= len(value["id"]) <= 64
            and isinstance(value["name"], str) and 1 <= len(value["name"]) <= 100)


def _valid_event(value):
    if not isinstance(value, dict):
        return False
    fields = {"id", "revision", "event_type", "reviewer", "created_at", "rationale",
              "evidence_refs", "passage_ids", "permitted_uses"}
    action = value.get("event_type")
    if action == "assessment":
        fields |= {"category", "decision"}
    if (set(value) != fields or not isinstance(value["id"], str) or len(value["id"]) != 32
            or not _valid_reviewer(value["reviewer"]) or type(value["revision"]) is not int
            or not 1 <= value["revision"] <= MAX_EVENTS):
        return False
    try:
        timestamp = datetime.fromisoformat(value["created_at"])
        if timestamp.tzinfo is None:
            return False
        body = {"expected_revision": value["revision"] - 1, "rationale": value["rationale"]}
        if action == "assessment":
            body.update({key: value[key] for key in ("category", "decision", "evidence_refs", "passage_ids", "permitted_uses")})
            AssessmentInput.model_validate(body)
        else:
            AssignmentInput.model_validate({**body, "action": action})
            if value["evidence_refs"] != [] or value["passage_ids"] != [] or value["permitted_uses"] != []:
                return False
        return True
    except (TypeError, ValueError, ValidationError):
        return False


def _projection(store, head, package):
    if head is None:
        return {"source_binding": _binding(package), "assigned_to": None, "assessments": {}}
    if type(head.revision) is not int or not 1 <= head.revision <= MAX_EVENTS:
        raise HTTPException(409, "Geçersiz kaynak inceleme sürümü")
    data = _decode(store, head)
    if (data.get("source_binding") != _binding(package)
            or data.get("context") != {"firm_id": head.firm_id, "head_id": head.id, "revision": head.revision}):
        raise HTTPException(409, "İnceleme farklı bir kaynak paketine bağlı")
    assigned = data.get("assigned_to")
    assessments = data.get("assessments")
    if (set(data) != {"source_binding", "context", "assigned_to", "assessments"}
            or assigned is not None and not _valid_reviewer(assigned)
            or not isinstance(assessments, dict) or not set(assessments).issubset(CATEGORIES)):
        raise HTTPException(409, "Kaynak inceleme kaydı yapısı doğrulanamadı")
    for category, event in assessments.items():
        if (not _valid_event(event) or event.get("category") != category
                or event["event_type"] != "assessment" or event["revision"] > head.revision):
            raise HTTPException(409, "Kaynak inceleme kararı doğrulanamadı")
    return data


def _verified_event(store, row, head, binding):
    payload = _decode(store, row)
    event = payload.get("event")
    if (payload.get("context") != {"firm_id": head.firm_id, "head_id": head.id,
                                  "revision": row.revision, "event_id": row.id}
            or payload.get("source_binding") != binding or not _valid_event(event)
            or event.get("id") != row.id or event.get("revision") != row.revision
            or event.get("created_at") != row.created_at):
        raise HTTPException(409, "İnceleme geçmişi kaynak ve kurum bağıyla eşleşmiyor")
    return event


def _history(store, session, head):
    if head is None:
        return []
    rows = session.scalars(select(SourceReviewEvent).where(
        SourceReviewEvent.head_id == head.id, SourceReviewEvent.firm_id == head.firm_id,
    ).order_by(SourceReviewEvent.revision.desc()).limit(MAX_EVENTS + 1))
    projection = _decode(store, head)
    binding = projection["source_binding"]
    history = [_verified_event(store, row, head, binding) for row in rows]
    expected = list(range(head.revision, 0, -1))
    if [event["revision"] for event in history] != expected:
        raise HTTPException(409, "İnceleme geçmişinde eksik veya tutarsız olay var")
    # Rebuild the bounded ledger projection. A previous acceptance or assignment
    # cannot replace a later rejection/release, including beyond displayed history.
    assigned = None
    assessments = {}
    for event in reversed(history):
        action = event["event_type"]
        if action == "claim":
            if assigned is not None:
                raise HTTPException(409, "İnceleme atama geçmişi tutarsız")
            assigned = event["reviewer"]
        elif action == "release":
            if assigned is None:
                raise HTTPException(409, "İnceleme atama geçmişi tutarsız")
            assigned = None
        else:
            if assigned is None or event["reviewer"]["id"] != assigned["id"]:
                raise HTTPException(409, "İnceleme kararı atama geçmişiyle eşleşmiyor")
            assessments[event["category"]] = event
    if projection["assigned_to"] != assigned or projection["assessments"] != assessments:
        raise HTTPException(409, "Güncel inceleme kararı değişmez geçmişinin son durumuyla eşleşmiyor")
    return history[:HISTORY_LIMIT]


def _state(package, revision, projection, history):
    assessments = [projection["assessments"][key] for key in CATEGORIES if key in projection["assessments"]]
    return {"source": package.detail, "revision": revision, "assigned_to": projection["assigned_to"],
            "assessments": assessments, "history": history, "history_truncated": revision > len(history),
            "handoff_ready": len(assessments) == len(CATEGORIES) and all(
                item["decision"] == "accepted" for item in assessments),
            "publication_eligible": False, "limitations": LIMITATIONS}


def _event(user, revision, body):
    event = {"id": uid(), "revision": revision, "reviewer": {"id": user.id, "name": user.name},
             "created_at": now(), "rationale": body.rationale,
             "event_type": body.action if isinstance(body, AssignmentInput) else "assessment",
             "evidence_refs": [], "passage_ids": [], "permitted_uses": []}
    if isinstance(body, AssessmentInput):
        event.update(body.model_dump(exclude={"expected_revision", "rationale"}))
    return event


def _transition(projection, event, user):
    assigned = projection["assigned_to"]
    action = event["event_type"]
    if action == "claim":
        if assigned is not None:
            raise HTTPException(409, "Kaynak başka bir incelemeye atanmış; güncel kaydı açın")
        projection["assigned_to"] = event["reviewer"]
    elif action == "release":
        if assigned is None:
            raise HTTPException(409, "Kaynak incelemesi zaten atanmamış")
        if assigned["id"] != user.id and user.role != "admin":
            raise HTTPException(403, "Atamayı yalnızca incelemeci veya gerekçe belirten yönetici kaldırabilir")
        projection["assigned_to"] = None
    else:
        if assigned is None or assigned["id"] != user.id:
            raise HTTPException(409, "Karar vermeden önce kaynak incelemesini üstlenin")
        projection["assessments"][event["category"]] = event


def _mutate(request, source_id, body, user):
    package = _package(request, source_id, user)
    if isinstance(body, AssessmentInput):
        available = {passage.id for passage in package.locators.passages}
        if not set(body.passage_ids).issubset(available):
            raise HTTPException(422, "Pasajlar bu kaynağın doğrulanmış metninden seçilmelidir")
    store = request.app.state.store
    try:
        with store.session() as session:
            head = _head(session, user.firm_id, source_id)
            revision = head.revision if head else 0
            if body.expected_revision != revision:
                raise HTTPException(409, "İnceleme değişti; güncel sürümü açıp yeniden deneyin")
            if revision >= MAX_EVENTS:
                raise HTTPException(409, "İnceleme olay sınırına ulaştı; kayıt saklama yöneticisine başvurun")
            projection = _projection(store, head, package)
            history = _history(store, session, head)
            current = _lock_identity(session, request, user)
            authorized_role = current.role
            event = _event(current, revision + 1, body)
            _transition(projection, event, current)
            head_id = head.id if head else uid()
            projection["context"] = {"firm_id": current.firm_id, "head_id": head_id, "revision": revision + 1}
            if head is None:
                head = SourceReviewHead(id=head_id, firm_id=current.firm_id, source_id=source_id,
                                        revision=1, payload=store.encode(projection))
                session.add(head)
                session.flush()
            else:
                changed = session.execute(update(SourceReviewHead).where(
                    SourceReviewHead.id == head.id, SourceReviewHead.firm_id == current.firm_id,
                    SourceReviewHead.revision == body.expected_revision,
                ).values(revision=revision + 1, payload=store.encode(projection))
                    .execution_options(synchronize_session=False))
                if changed.rowcount != 1:
                    raise HTTPException(409, "İnceleme eşzamanlı değişti; güncel sürümü açın")
            session.add(SourceReviewEvent(id=event["id"], head_id=head.id, firm_id=current.firm_id,
                                         revision=event["revision"], created_at=event["created_at"],
                                         payload=store.encode({"source_binding": _binding(package), "event": event,
                                                               "context": {**projection["context"], "event_id": event["id"]}})))
            result = _state(package, revision + 1, projection, [event, *history][:HISTORY_LIMIT])
            # Refresh role/session immediately before commit; held row locks protect the final boundary.
            if _lock_identity(session, request, user).role != authorized_role:
                raise HTTPException(403, "İnceleme sırasında yetkiniz değişti; güncel kaydı açın")
            session.commit()
            return result
    except IntegrityError:
        raise HTTPException(409, "İnceleme eşzamanlı değişti; güncel sürümü açın") from None
    except OperationalError as exc:
        if getattr(exc.orig, "sqlite_errorcode", None) in {5, 6, 517}:
            raise HTTPException(409, "İnceleme eşzamanlı değişti; güncel sürümü açın") from None
        raise HTTPException(503, "İnceleme deposuna şu anda erişilemiyor") from None


def source_reviews_router():
    router = APIRouter(prefix="/api/v1/public-sources", tags=["source-review"])

    def authorize(request: Request):
        return _authorize(request)

    def read(request, source_id, user):
        package = _package(request, source_id, user)
        store = request.app.state.store
        with store.session() as session:
            head = _head(session, user.firm_id, source_id)
            projection = _projection(store, head, package)
            result = _state(package, head.revision if head else 0, projection, _history(store, session, head))
        _authorize(request, user)
        return result

    @router.get("/{source_id}/review")
    def review(source_id: str, request: Request, user=Depends(authorize)):
        return read(request, source_id, user)

    @router.post("/{source_id}/review/assignment")
    def assignment(source_id: str, body: AssignmentInput, request: Request, user=Depends(authorize)):
        return _mutate(request, source_id, body, user)

    @router.post("/{source_id}/review/assessments")
    def assessment(source_id: str, body: AssessmentInput, request: Request, user=Depends(authorize)):
        return _mutate(request, source_id, body, user)

    @router.get("/{source_id}/review/export")
    def export(source_id: str, request: Request, user=Depends(authorize)):
        state = read(request, source_id, user)
        dossier = {"schema_version": "source-review-dossier-v1", "confidentiality": "firm_confidential",
                   "signed": False, "publication_eligible": False, "exported_at": now(), "review": state}
        payload = json.dumps(dossier, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        _authorize(request, user)
        return Response(payload, media_type="application/json", headers={
            "Content-Disposition": f'attachment; filename="source-review-{source_id}.json"',
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        })

    return router
