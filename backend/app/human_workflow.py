"""Manual human work: fresh case scope, independent recipients and attributed history."""
import re
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, exists, or_, select
from sqlalchemy.orm.exc import StaleDataError

from .auth import authenticate, require_matter
from .content_scope import case_scope, scoped_users
from .db import Audit, CaseResponsibility, LoginSession, Membership, Record, User, WorkParticipant, now
from .firm_rbac import permissions_for, require_permission

ISTANBUL = ZoneInfo("Europe/Istanbul")
Kind = Literal["deadline", "milestone", "task", "opinion"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class WorkInput(Strict):
    kind: Kind
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20000)
    due_local: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
    assignee_ids: list[str] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_content(self):
        if len(set(self.assignee_ids)) != len(self.assignee_ids) or any(not i or len(i) > 64 for i in self.assignee_ids):
            raise ValueError("Geçersiz veya yinelenen çalışan referansı")
        normalize_due(self.due_local)
        if self.kind == "opinion" and not self.description:
            raise ValueError("Görüş için soru ve bağlam gerekir")
        return self


class EditInput(WorkInput):
    revision: int = Field(ge=1)
    status: Literal["open", "completed", "cancelled"] = "open"
    reason: str = Field(min_length=1, max_length=2000)


class ProgressInput(Strict):
    revision: int = Field(ge=1)
    status: Literal["pending", "in_progress", "completed"]
    note: str = Field(min_length=1, max_length=4000)


class SubmissionInput(Strict):
    revision: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=50000)


class ReviewInput(Strict):
    revision: int = Field(ge=1)
    submission_id: str = Field(min_length=1, max_length=64)
    decision: Literal["accepted", "revision_requested"]
    note: str = Field(min_length=1, max_length=4000)


def normalize_due(value):
    # Browser wall time is always explicitly interpreted in Istanbul, never host TZ.
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", value):
            raise ValueError()
        wall = datetime.fromisoformat(value)
        first, second = wall.replace(tzinfo=ISTANBUL, fold=0), wall.replace(tzinfo=ISTANBUL, fold=1)
        if first.utcoffset() != second.utcoffset() or first.astimezone(timezone.utc).astimezone(ISTANBUL).replace(tzinfo=None) != wall:
            raise ValueError()
        return first.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError) as exc:
        raise ValueError("Geçerli ve tek anlamlı bir İstanbul tarihi/saatini girin") from exc


def supervisor_scope(matter_id, user_id, firm_id):
    return exists(select(1).select_from(CaseResponsibility).join(Membership,
        (Membership.matter_id == CaseResponsibility.matter_id) & (Membership.user_id == CaseResponsibility.user_id)).where(
        CaseResponsibility.matter_id == matter_id, CaseResponsibility.user_id == user_id,
        CaseResponsibility.firm_id == firm_id, CaseResponsibility.supervisor.is_(True)))


def is_supervisor(session, matter_id, user):
    return user.role in {"lawyer", "admin"} and bool(session.scalar(select(supervisor_scope(matter_id, user.id, user.firm_id))))


def require_supervisor(session, matter_id, user, *, review=False):
    require_permission(session, user, "matter.review" if review else "matter.write")
    if not is_supervisor(session, matter_id, user):
        raise HTTPException(403, "Bu dosya için açık gözetmen ataması gerekir")


def _matter(session, matter_id, user, lock=False):
    if lock:
        session.scalar(select(Record).where(Record.id == matter_id, Record.firm_id == user.firm_id).with_for_update())
    return require_matter(session, matter_id, user)


def _item(session, matter_id, ident, user, lock=False):
    _matter(session, matter_id, user, lock)
    query = select(Record).where(Record.id == ident, Record.kind == "human_work", Record.matter_id == matter_id,
                                  Record.firm_id == user.firm_id).execution_options(populate_existing=True)
    row = session.scalar(query.with_for_update() if lock else query)
    participant = session.get(WorkParticipant, (ident, user.id))
    if not row or not (is_supervisor(session, matter_id, user) or (participant and participant.active)):
        raise HTTPException(404, "Çalışma kaydı bulunamadı")
    return row


def eligible(session, matter_id, user, kind):
    return [person for person in scoped_users(session, matter_id, user.firm_id)
            if "matter.write" in permissions_for(session, person) and (kind != "opinion" or person.role in {"lawyer", "admin"})]


def _validate_recipients(session, matter_id, user, body):
    people = {person.id for person in eligible(session, matter_id, user, body.kind)}
    if not set(body.assignee_ids) <= people:
        raise HTTPException(422, "Çalışanlar aktif, işlem izinli ve dosyaya zaten yetkili olmalı")


def _event(user, action, **values):
    from .db import uid
    return {"id": uid(), "action": action, "actor_id": user.id, "actor_name": user.name, "recorded_at": now(), **values}


def _audit(session, user, row, action):
    session.add(Audit(actor_id=user.id, matter_id=row.matter_id, object_id=row.id, action=action))


def _commit(session):
    try:
        session.commit()
    except StaleDataError as exc:
        raise HTTPException(409, "Kayıt değişti; yeniden yükleyin") from exc


def _revision(row, expected):
    if row.revision != expected:
        raise HTTPException(409, "Kayıt değişti; yeniden yükleyin")


def _latest(data):
    return next((event for event in reversed(data["history"]) if event["action"] == "submitted"), None)


def _response_view(store, row, request_version):
    result = store.view(row)
    latest = next((e for e in reversed(result["history"]) if e["action"] in {"submitted", "progress"}), None)
    if latest and latest["request_version"] != request_version:
        result["status"] = "stale"
    return result


def _view(store, session, row, user, *, detail=False):
    data = store.view(row)
    supervisor = is_supervisor(session, row.matter_id, user)
    participants = session.scalars(select(WorkParticipant).where(WorkParticipant.work_id == row.id,
                                     WorkParticipant.firm_id == user.firm_id).order_by(WorkParticipant.user_id)).all()
    responses = []
    for person in participants:
        if not supervisor and person.user_id != user.id:
            continue
        response = session.get(Record, person.response_id)
        if not response or response.firm_id != user.firm_id or response.matter_id != row.matter_id or response.kind != "human_response":
            raise HTTPException(409, "Görüş kaydı doğrulanamadı")
        result = _response_view(store, response, data["request_version"])
        result.update(user_id=person.user_id, active=person.active)
        # Current availability is separate from the historical recipient identity.
        current = session.get(User, person.user_id, populate_existing=True)
        result["currently_eligible"] = bool(current and current.active and current.firm_id == user.firm_id
            and "matter.write" in permissions_for(session, current)
            and session.scalar(select(case_scope(row.matter_id, current.id, user.firm_id)))
            and (data["kind"] != "opinion" or current.role in {"lawyer", "admin"}))
        if not detail:
            result.pop("history", None)
        responses.append(result)
    if not detail:
        data.pop("history", None)
        data.pop("description", None)
    data.update(viewer_id=user.id, can_act="matter.write" in permissions_for(session, user), matter_id=row.matter_id, can_manage=supervisor and "matter.write" in permissions_for(session, user),
                can_review=supervisor and "matter.review" in permissions_for(session, user), responses=responses,
                overdue=data["status"] == "open" and datetime.fromisoformat(data["due_at"]) < datetime.now(timezone.utc))
    return data


def _assign(store, session, row, user, ids):
    existing = {p.user_id: p for p in session.scalars(select(WorkParticipant).where(WorkParticipant.work_id == row.id))}
    removed = {ident for ident, participant in existing.items() if participant.active and ident not in ids}
    session.execute(delete(LoginSession).where(LoginSession.user_id.in_(removed)))
    for ident, participant in existing.items():
        participant.active = ident in ids
    for ident in ids:
        if ident in existing:
            continue
        person = session.get(User, ident)
        response = store.add(session, "human_response", user, {"recipient_name": person.name, "status": "pending", "history": []}, row.matter_id)
        session.add(WorkParticipant(work_id=row.id, user_id=ident, response_id=response.id, matter_id=row.matter_id, firm_id=user.firm_id))
    session.flush()


def workflow_router():
    router = APIRouter(prefix="/api/v1", tags=["human-workflow"])

    @router.get("/work")
    def queue(request: Request, view: Literal["personal", "supervisory"] = "personal",
              bucket: Literal["all", "upcoming", "overdue", "closed"] = "all",
              limit: int = Query(default=100, ge=1, le=500), user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            require_permission(session, user, "matter.read")
            recipient = exists(select(1).where(WorkParticipant.work_id == Record.id, WorkParticipant.user_id == user.id,
                                     WorkParticipant.firm_id == user.firm_id, WorkParticipant.active.is_(True)))
            routing = supervisor_scope(Record.matter_id, user.id, user.firm_id) if view == "supervisory" and user.role in {"lawyer", "admin"} else recipient
            if view == "supervisory" and user.role not in {"lawyer", "admin"}:
                return {"items": [], "truncated": False, "time_zone": "Europe/Istanbul"}
            # All authorization predicates precede joins, decryption, sorting and counts.
            matter = Record.__table__.alias("active_work_matter")
            query = select(Record).join(matter, matter.c.id == Record.matter_id).where(
                Record.kind == "human_work", Record.firm_id == user.firm_id,
                matter.c.kind == "matter", matter.c.firm_id == user.firm_id,
                case_scope(Record.matter_id, user.id, user.firm_id), routing).order_by(Record.created_at.desc(), Record.id)
            rows = session.scalars(query.limit(1001)).all()
            items = []
            for row in rows[:1000]:
                item = _view(store, session, row, user)
                own = next((r for r in item["responses"] if r["user_id"] == user.id and r["active"]), None)
                item["queue_status"] = own["status"] if view == "personal" and own and item["status"] == "open" else item["status"]
                closed = item["queue_status"] in {"completed", "cancelled", "accepted"}
                item["overdue"] = item["overdue"] and not closed
                if (bucket == "closed" and not closed) or (bucket == "overdue" and (closed or not item["overdue"])) or (bucket == "upcoming" and (closed or item["overdue"])):
                    continue
                title = session.get(Record, row.matter_id)
                item["matter_title"] = store.decode(title).get("title", "")
                items.append(item)
            items.sort(key=lambda value: (value["due_at"], value["id"]))
            return {"items": items[:limit], "truncated": len(items) > limit or len(rows) > 1000, "candidate_window": 1000, "time_zone": "Europe/Istanbul"}

    @router.get("/workspaces/{matter_id}/work")
    def case_work(matter_id: str, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            _matter(session, matter_id, user)
            supervising = is_supervisor(session, matter_id, user)
            own = exists(select(1).where(WorkParticipant.work_id == Record.id, WorkParticipant.user_id == user.id,
                               WorkParticipant.active.is_(True), WorkParticipant.firm_id == user.firm_id))
            rows = session.scalars(select(Record).where(Record.kind == "human_work", Record.matter_id == matter_id,
                Record.firm_id == user.firm_id, or_(supervising, own)).order_by(Record.created_at, Record.id)).all()
            result = {"items": [_view(store, session, row, user) for row in rows], "can_manage": supervising and "matter.write" in permissions_for(session, user),
                      "people": [], "time_zone": "Europe/Istanbul"}
            if result["can_manage"]:
                result["people"] = [{"id": p.id, "name": p.name, "can_opine": p.role in {"lawyer", "admin"}} for p in eligible(session, matter_id, user, "task")]
            return result

    @router.post("/workspaces/{matter_id}/work", status_code=201)
    def create(matter_id: str, body: WorkInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            _matter(session, matter_id, user, True)
            require_supervisor(session, matter_id, user)
            _validate_recipients(session, matter_id, user, body)
            data = {**body.model_dump(), "due_at": normalize_due(body.due_local), "time_zone": "Europe/Istanbul", "status": "open", "request_version": 1}
            data["history"] = [_event(user, "created", snapshot={**data})]
            row = store.add(session, "human_work", user, data, matter_id)
            _assign(store, session, row, user, body.assignee_ids)
            _audit(session, user, row, "human_work_created")
            _commit(session)
            return _view(store, session, row, user, detail=True)

    @router.get("/workspaces/{matter_id}/work/{ident}")
    def detail(matter_id: str, ident: str, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            return _view(store, session, _item(session, matter_id, ident, user), user, detail=True)

    @router.put("/workspaces/{matter_id}/work/{ident}")
    def edit(matter_id: str, ident: str, body: EditInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            row = _item(session, matter_id, ident, user, True)
            require_supervisor(session, matter_id, user)
            _revision(row, body.revision)
            data = store.decode(row)
            if body.kind != data["kind"]:
                raise HTTPException(422, "Kayıt türü değiştirilemez")
            # Closing/cancelling must remain possible after recipient access is revoked.
            if body.status == "open":
                _validate_recipients(session, matter_id, user, body)
            elif body.assignee_ids != data["assignee_ids"]:
                raise HTTPException(422, "Kapalı kayıtta alıcılar değiştirilemez")
            meaningful = any(getattr(body, key) != data[key] for key in ("title", "description", "due_local", "assignee_ids"))
            version = data["request_version"] + int(meaningful)
            if body.status == "completed":
                required = "accepted" if body.kind == "opinion" else "completed"
                for person in session.scalars(select(WorkParticipant).where(WorkParticipant.work_id == row.id, WorkParticipant.active.is_(True))):
                    state = _response_view(store, session.get(Record, person.response_id), version)
                    if state["status"] != required:
                        raise HTTPException(409, "Tüm etkin alıcıların çalışması tamamlanmalı")
            update = {**body.model_dump(exclude={"revision", "reason"}), "due_at": normalize_due(body.due_local), "time_zone": "Europe/Istanbul", "request_version": version}
            update["history"] = [*data["history"], _event(user, "updated", reason=body.reason, snapshot={**update})]
            store.update(row, update)
            _assign(store, session, row, user, body.assignee_ids)
            _audit(session, user, row, "human_work_updated")
            _commit(session)
            return _view(store, session, row, user, detail=True)

    def response_target(store, session, matter_id, ident, recipient, user, revision, *, reviewing=False):
        row = _item(session, matter_id, ident, user, True)
        data = store.decode(row)
        if data["status"] != "open":
            raise HTTPException(409, "Çalışma kapalı")
        person = session.get(WorkParticipant, (ident, recipient))
        if not person or not person.active or person.firm_id != user.firm_id:
            raise HTTPException(404, "Etkin alıcı bulunamadı")
        if reviewing:
            require_supervisor(session, matter_id, user, review=True)
        elif recipient != user.id:
            raise HTTPException(403, "Yalnızca kendi çalışmanızı gönderebilirsiniz")
        else:
            require_permission(session, user, "matter.write")
        response = session.scalar(select(Record).where(Record.id == person.response_id, Record.kind == "human_response",
            Record.firm_id == user.firm_id, Record.matter_id == matter_id).with_for_update())
        if not response:
            raise HTTPException(409, "Alıcı kaydı doğrulanamadı")
        _revision(response, revision)
        return row, data, response, store.decode(response)

    @router.post("/workspaces/{matter_id}/work/{ident}/progress")
    def progress(matter_id: str, ident: str, body: ProgressInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            row, data, response, state = response_target(store, session, matter_id, ident, user.id, user, body.revision)
            if data["kind"] == "opinion":
                raise HTTPException(422, "Görüşü ayrı gönderim formuyla kaydedin")
            store.update(response, {"recipient_name": state["recipient_name"], "status": body.status,
                "history": [*state["history"], _event(user, "progress", status=body.status, note=body.note, request_version=data["request_version"])]})
            _audit(session, user, row, "human_progress_recorded")
            _commit(session)
            return _view(store, session, row, user, detail=True)

    @router.post("/workspaces/{matter_id}/work/{ident}/submissions")
    def submit(matter_id: str, ident: str, body: SubmissionInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            row, data, response, state = response_target(store, session, matter_id, ident, user.id, user, body.revision)
            if data["kind"] != "opinion" or user.role not in {"lawyer", "admin"}:
                raise HTTPException(403, "Görüşü yalnızca atanan avukat kendi hesabıyla gönderebilir")
            if _response_view(store, response, data["request_version"])["status"] in {"submitted", "accepted"}:
                raise HTTPException(409, "Önce gözetmen incelemesi veya yeni soru sürümü gerekir")
            store.update(response, {"recipient_name": state["recipient_name"], "status": "submitted",
                "history": [*state["history"], _event(user, "submitted", text=body.text, request_version=data["request_version"], authorship="human_account") ]})
            _audit(session, user, row, "human_opinion_submitted")
            _commit(session)
            return _view(store, session, row, user, detail=True)

    @router.post("/workspaces/{matter_id}/work/{ident}/responses/{recipient}/review")
    def review(matter_id: str, ident: str, recipient: str, body: ReviewInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            row, data, response, state = response_target(store, session, matter_id, ident, recipient, user, body.revision, reviewing=True)
            if data["kind"] != "opinion" or recipient == user.id:
                raise HTTPException(403, "Kendi görüşünüzü inceleyemezsiniz")
            # A removed/deactivated recipient is retained as history but cannot be freshly reviewed.
            if recipient not in {p.id for p in eligible(session, matter_id, user, "opinion")}:
                raise HTTPException(409, "Alıcının güncel dosya erişimi/izni yok")
            latest = _latest(state)
            if not latest or latest["id"] != body.submission_id or latest["request_version"] != data["request_version"] or state["status"] != "submitted":
                raise HTTPException(409, "Gönderim veya soru sürümü değişti")
            store.update(response, {"recipient_name": state["recipient_name"], "status": body.decision,
                "history": [*state["history"], _event(user, "reviewed", submission_id=latest["id"], decision=body.decision, note=body.note, request_version=data["request_version"])]})
            _audit(session, user, row, "human_opinion_reviewed")
            _commit(session)
            return _view(store, session, row, user, detail=True)

    return router
