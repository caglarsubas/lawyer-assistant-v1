"""Customer tags and workspace navigation over the existing encrypted matter store.

Customer membership is descriptive, never an authorization grant. Workspaces retain
their matter identities, membership checks, documents, and lifecycle endpoints.
"""

from datetime import date, datetime, timezone
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select

from .auth import authenticate, require_matter
from .db import Audit, Membership, Record, User, now

Identifier = Annotated[str, Field(min_length=1, max_length=64)]
DateField = Literal["created_at", "updated_at", "relevant_date"]
PORTFOLIO_TIMEZONE = ZoneInfo("Europe/Istanbul")


class PortfolioInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class CustomerInput(PortfolioInput):
    name: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=4000)


class WorkspaceInput(PortfolioInput):
    title: str = Field(min_length=1, max_length=200)
    domain: Literal["contracts", "commercial", "employment"]
    objective: str = Field(default="", max_length=4000)
    represented_party: str = Field(default="", max_length=200)
    stage: str = Field(default="hazırlık", max_length=200)
    relevant_date: str | None = None
    customer_ids: list[Identifier] = Field(default_factory=list, max_length=100)

    @field_validator("relevant_date")
    @classmethod
    def canonical_relevant_date(cls, value):
        if value is not None:
            parse_date(value)
        return value


class WorkspaceCustomersInput(PortfolioInput):
    customer_ids: list[Identifier] = Field(max_length=100)
    revision: int = Field(ge=1)


class CommentInput(PortfolioInput):
    text: str = Field(min_length=1, max_length=10000)


def parse_date(value: date | str | None) -> date | None:
    if value is None:
        return None
    if type(value) is date:
        return value
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("Noncanonical date")
        return parsed
    except (TypeError, ValueError):
        raise HTTPException(422, "Date must be YYYY-MM-DD") from None


def _current_user(session, user):
    current = session.get(User, user.id, populate_existing=True)
    if not current or not current.active or current.firm_id != user.firm_id:
        raise HTTPException(401, "Oturum geçersiz")
    return current


def _workspace_records(session, user):
    _current_user(session, user)
    return session.scalars(
        select(Record)
        .join(Membership, Membership.matter_id == Record.id)
        .where(Record.kind == "matter", Record.firm_id == user.firm_id, Membership.user_id == user.id)
        .order_by(Record.created_at.desc(), Record.id)
    ).all()


def _customer_records(store, session, user, workspaces):
    linked_ids = {
        customer_id
        for workspace in workspaces
        for customer_id in store.decode(workspace).get("customer_ids", [])
    }
    return session.scalars(select(Record).where(
        Record.kind == "customer",
        Record.firm_id == user.firm_id,
        or_(Record.owner_id == user.id, Record.id.in_(linked_ids)),
    ).order_by(Record.created_at.desc(), Record.id)).all()


def validate_customer_ids(store, session, user, customer_ids):
    """Return distinct authorized IDs without revealing absent or inaccessible records."""
    ids = list(dict.fromkeys(customer_ids))
    if not ids:
        _current_user(session, user)
        return []
    workspaces = _workspace_records(session, user)
    allowed = {record.id for record in _customer_records(store, session, user, workspaces)}
    if any(customer_id not in allowed for customer_id in ids):
        raise HTTPException(404, "Müşteri bulunamadı")
    return ids


def workspace_view(store, session, user, workspace, *, customers=None, document_count=None):
    """Serialize an already authorized workspace without exposing foreign customer links."""
    data = store.view(workspace)
    ids = list(dict.fromkeys(data.get("customer_ids", [])))
    if customers is None:
        customers = {
            row.id: store.view(row)
            for row in session.scalars(select(Record).where(
                Record.kind == "customer", Record.firm_id == user.firm_id, Record.id.in_(ids)
            ))
        }
    tagged = [{"id": customer_id, "name": customers[customer_id]["name"]}
              for customer_id in ids if customer_id in customers]
    if document_count is None:
        document_count = session.scalar(select(func.count()).select_from(Record).where(
            Record.kind == "document", Record.matter_id == workspace.id, Record.firm_id == user.firm_id
        ))
    return {
        **data,
        "customer_ids": [customer["id"] for customer in tagged],
        "customers": tagged,
        "document_count": document_count,
        "updated_at": data.get("updated_at") or workspace.created_at,
    }


def list_workspaces(store, session, user, customer_ids: list[str] | None = None,
                    date_from: date | str | None = None, date_to: date | str | None = None,
                    date_field: str = "created_at") -> list[dict]:
    """Authorized portfolio snapshot shared by navigation and assistant summaries.

    Customer matching is OR. Date endpoints are inclusive calendar dates; absent
    relevant dates do not match a bounded relevant-date filter. Archived workspaces
    remain accessible only through the existing governance lifecycle endpoints.
    """
    if date_field not in {"created_at", "updated_at", "relevant_date"}:
        raise HTTPException(422, "Unsupported date field")
    start, end = parse_date(date_from), parse_date(date_to)
    if start and end and start > end:
        raise HTTPException(422, "Başlangıç tarihi bitiş tarihinden sonra olamaz")
    workspaces = _workspace_records(session, user)
    customers = {row.id: store.view(row) for row in _customer_records(store, session, user, workspaces)}
    counts = dict(session.execute(select(Record.matter_id, func.count()).where(
        Record.kind == "document", Record.firm_id == user.firm_id,
        Record.matter_id.in_([row.id for row in workspaces]),
    ).group_by(Record.matter_id)).all())
    wanted = set(customer_ids or [])
    result = []
    for workspace in workspaces:
        item = workspace_view(store, session, user, workspace, customers=customers,
                              document_count=counts.get(workspace.id, 0))
        if wanted and not wanted.intersection(item["customer_ids"]):
            continue
        if start or end:
            raw_date = item.get(date_field)
            if not raw_date:
                continue
            # Older records can contain unknown or noncanonical relevant dates.
            # They do not acquire a fabricated date when a filter is applied.
            try:
                if date_field == "relevant_date":
                    stamp = date.fromisoformat(raw_date)
                else:
                    instant = datetime.fromisoformat(raw_date)
                    if instant.tzinfo is None:
                        instant = instant.replace(tzinfo=timezone.utc)
                    stamp = instant.astimezone(PORTFOLIO_TIMEZONE).date()
            except (TypeError, ValueError):
                continue
            if (start and stamp < start) or (end and stamp > end):
                continue
        result.append(item)
    return result


def _audit(session, user, action, record_id, matter_id=None):
    session.add(Audit(actor_id=user.id, action=action, object_id=record_id, matter_id=matter_id))


def portfolio_router():
    router = APIRouter(prefix="/api/v1", tags=["portfolio"])

    @router.get("/customers")
    def customers(request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            workspaces = _workspace_records(session, user)
            links = [set(store.decode(row).get("customer_ids", [])) for row in workspaces]
            return [{**store.view(row), "workspace_count": sum(row.id in ids for ids in links)}
                    for row in _customer_records(store, session, user, workspaces)]

    @router.post("/customers", status_code=201)
    def create_customer(body: CustomerInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            _current_user(session, user)
            record = store.add(session, "customer", user, body.model_dump())
            _audit(session, user, "customer_created", record.id)
            session.commit()
            return {**store.view(record), "workspace_count": 0}

    @router.get("/workspaces")
    def workspaces(request: Request, customer_ids: str = Query(default="", max_length=6500),
                   date_from: str | None = None, date_to: str | None = None,
                   date_field: DateField = "created_at", user=Depends(authenticate)):
        ids = list(dict.fromkeys(part.strip() for part in customer_ids.split(",") if part.strip()))
        if len(ids) > 100 or any(len(value) > 64 for value in ids):
            raise HTTPException(422, "En fazla 100 geçerli müşteri kimliği seçin")
        store = request.app.state.store
        with store.session() as session:
            return list_workspaces(store, session, user, ids, date_from, date_to, date_field)

    @router.post("/workspaces", status_code=201)
    def create_workspace(body: WorkspaceInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            ids = validate_customer_ids(store, session, user, body.customer_ids)
            data = {**body.model_dump(), "customer_ids": ids, "status": "draft", "updated_at": now()}
            record = store.add(session, "matter", user, data)
            session.add(Membership(matter_id=record.id, user_id=user.id))
            _audit(session, user, "workspace_created", record.id, record.id)
            session.commit()
            return workspace_view(store, session, user, record)

    @router.get("/workspaces/{workspace_id}")
    def get_workspace(workspace_id: str, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            workspace = require_matter(session, workspace_id, user)
            result = workspace_view(store, session, user, workspace)
            children = session.scalars(select(Record).where(
                Record.matter_id == workspace_id, Record.firm_id == user.firm_id
            ).order_by(Record.created_at.desc(), Record.id)).all()
            for kind, key in (("document", "documents"), ("fact", "facts"),
                              ("product", "products"), ("research", "research_runs")):
                result[key] = [{key: value for key, value in store.view(row).items()
                                if key not in {"passages", "evidence", "original_path"}}
                               for row in children if row.kind == kind]
            result["comments"] = [store.view(row) for row in reversed(children)
                                  if row.kind == "workspace_comment"]
            return result

    @router.put("/workspaces/{workspace_id}/customers")
    def replace_customers(workspace_id: str, body: WorkspaceCustomersInput,
                          request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            workspace = require_matter(session, workspace_id, user)
            if workspace.revision != body.revision:
                raise HTTPException(409, "Çalışma alanı değişti; yenileyip tekrar deneyin")
            ids = validate_customer_ids(store, session, user, body.customer_ids)
            store.update(workspace, {**store.decode(workspace), "customer_ids": ids, "updated_at": now()})
            _audit(session, user, "workspace_customers_changed", workspace.id, workspace.id)
            session.commit()
            return workspace_view(store, session, user, workspace)

    @router.get("/workspaces/{workspace_id}/comments")
    def comments(workspace_id: str, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            require_matter(session, workspace_id, user)
            return [store.view(row) for row in session.scalars(select(Record).where(
                Record.kind == "workspace_comment", Record.matter_id == workspace_id,
                Record.firm_id == user.firm_id,
            ).order_by(Record.created_at, Record.id))]

    @router.post("/workspaces/{workspace_id}/comments", status_code=201)
    def add_comment(workspace_id: str, body: CommentInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            workspace = require_matter(session, workspace_id, user)
            record = store.add(session, "workspace_comment", user,
                               {"text": body.text, "author_name": user.name}, workspace_id)
            store.update(workspace, {**store.decode(workspace), "updated_at": now()})
            _audit(session, user, "workspace_comment_created", record.id, workspace_id)
            session.commit()
            return store.view(record)

    return router
