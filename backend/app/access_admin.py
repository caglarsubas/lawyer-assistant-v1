"""Firm-admin-only configuration using opaque references, without a content bypass."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select

from .auth import authenticate, require_matter
from .content_scope import (
    access_explanation,
    configuration,
    invalidate_scope,
    record_change,
    remove_queued,
    scoped_users,
)
from .db import CaseResponsibility, CustomerAssignment, Membership, Record, User, WorkspaceCustomerLink
from .firm_rbac import require_permission


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ClientGrant(StrictInput):
    user_id: str = Field(min_length=1, max_length=64)
    scope: Literal["details", "all_cases"]


class ClientEdit(StrictInput):
    revision: int = Field(ge=1)
    assignments: list[ClientGrant] = Field(max_length=500)


class CaseGrant(StrictInput):
    user_id: str = Field(min_length=1, max_length=64)
    supervisor: bool = False
    responsible: bool = False


class CaseEdit(StrictInput):
    revision: int = Field(ge=1)
    members: list[CaseGrant] = Field(max_length=500)


def _target(session, user, ident, kind):
    require_permission(session, user, "firm.manage")
    row = session.get(Record, ident, populate_existing=True)
    kinds = {"matter", "archived_matter"} if kind == "matter" else {kind}
    if not row or row.kind not in kinds or row.firm_id != user.firm_id:
        raise HTTPException(404, "Atama hedefi bulunamadı")
    return row


def _employees(session, user, assignments):
    ids = [item.user_id for item in assignments]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Yinelenen çalışan ataması")
    users = {row.id: row for row in session.scalars(select(User).where(
        User.id.in_(ids), User.firm_id == user.firm_id, User.active.is_(True)))}
    if len(users) != len(ids):
        raise HTTPException(404, "Aktif çalışan bulunamadı")
    return users


def _client_view(session, row):
    return {"target_id": row.id, "revision": configuration(session, row).revision,
            "assignments": [{"user_id": item.user_id, "scope": item.scope} for item in session.scalars(
                select(CustomerAssignment).where(CustomerAssignment.customer_id == row.id,
                                                  CustomerAssignment.firm_id == row.firm_id).order_by(CustomerAssignment.user_id))]}


def _case_view(session, row):
    members = []
    for ident in session.scalars(select(Membership.user_id).join(User, User.id == Membership.user_id).where(
        Membership.matter_id == row.id, User.firm_id == row.firm_id).order_by(Membership.user_id)):
        role = session.get(CaseResponsibility, (row.id, ident))
        members.append({"user_id": ident, "supervisor": bool(role and role.firm_id == row.firm_id and role.supervisor),
                        "responsible": bool(role and role.firm_id == row.firm_id and role.responsible)})
    return {"target_id": row.id, "revision": configuration(session, row).revision, "members": members,
            "client_grants_are_independent": True}


def _changed(before, after):
    old, new = ({item["user_id"]: item for item in values} for values in (before, after))
    return {ident for ident in old.keys() | new.keys() if old.get(ident) != new.get(ident)}


def access_router():
    router = APIRouter(prefix="/api/v1", tags=["explicit-assignments"])

    @router.get("/firm-admin/customers/{ident}/assignments")
    def client_assignments(ident: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            result = _client_view(session, _target(session, user, ident, "customer"))
            session.commit()
            return result

    @router.put("/firm-admin/customers/{ident}/assignments")
    def edit_client(ident: str, body: ClientEdit, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            row = _target(session, user, ident, "customer")
            version = configuration(session, row)
            if version.revision != body.revision:
                raise HTTPException(409, "Atamalar değişti; yeniden yükleyin")
            _employees(session, user, body.assignments)
            before = _client_view(session, row)
            linked = list(session.scalars(select(Record.id).join(WorkspaceCustomerLink, WorkspaceCustomerLink.matter_id == Record.id).where(
                WorkspaceCustomerLink.customer_id == ident, WorkspaceCustomerLink.firm_id == user.firm_id,
                Record.firm_id == user.firm_id, Record.kind.in_(["matter", "archived_matter"]))))
            session.execute(delete(CustomerAssignment).where(CustomerAssignment.customer_id == ident))
            session.add_all([CustomerAssignment(customer_id=ident, user_id=item.user_id, firm_id=user.firm_id,
                                               scope=item.scope, assigned_by=user.id) for item in body.assignments])
            version.revision += 1
            session.flush()
            result = _client_view(session, row)
            if any(not scoped_users(session, case, user.firm_id) for case in linked):
                raise HTTPException(409, "En az bir aktif dosya erişimi korunmalı")
            changed = _changed(before["assignments"], result["assignments"])
            stopped = invalidate_scope(store, session, user.firm_id, changed)
            record_change(store, session, user, ident, "client_assignments_changed", before, result)
            session.commit()
            remove_queued(request.app, stopped)
            return result

    @router.get("/firm-admin/workspaces/{ident}/team")
    def case_team(ident: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            result = _case_view(session, _target(session, user, ident, "matter"))
            session.commit()
            return result

    @router.put("/firm-admin/workspaces/{ident}/team")
    def edit_team(ident: str, body: CaseEdit, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            row = _target(session, user, ident, "matter")
            version = configuration(session, row)
            if version.revision != body.revision:
                raise HTTPException(409, "Ekip değişti; yeniden yükleyin")
            employees = _employees(session, user, body.members)
            if any((item.supervisor or item.responsible) and employees[item.user_id].role not in {"lawyer", "admin"}
                   for item in body.members):
                raise HTTPException(422, "Sorumlu veya gözetmen için avukat kimliği gerekir")
            before = _case_view(session, row)
            session.execute(delete(CaseResponsibility).where(CaseResponsibility.matter_id == ident))
            session.execute(delete(Membership).where(Membership.matter_id == ident))
            session.add_all([Membership(matter_id=ident, user_id=item.user_id) for item in body.members])
            session.add_all([CaseResponsibility(matter_id=ident, user_id=item.user_id, firm_id=user.firm_id,
                                               supervisor=item.supervisor, responsible=item.responsible) for item in body.members])
            session.flush()
            if not scoped_users(session, ident, user.firm_id):
                raise HTTPException(409, "En az bir aktif dosya erişimi korunmalı")
            version.revision += 1
            result = _case_view(session, row)
            changed = _changed(before["members"], result["members"])
            stopped = invalidate_scope(store, session, user.firm_id, changed)
            record_change(store, session, user, ident, "case_team_changed", before, result)
            session.commit()
            remove_queued(request.app, stopped)
            return result

    @router.get("/workspaces/{ident}/access")
    def explain(ident: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            matter = require_matter(session, ident, user)
            result = access_explanation(session, matter, user)
            people = scoped_users(session, ident, user.firm_id)
            roles = {item.user_id: item for item in session.scalars(select(CaseResponsibility).join(
                Membership, (Membership.matter_id == CaseResponsibility.matter_id) & (Membership.user_id == CaseResponsibility.user_id)).where(
                    CaseResponsibility.matter_id == matter.id, CaseResponsibility.firm_id == user.firm_id))}
            result["team"] = [{"user_id": person.id, "name": person.name,
                               "supervisor": bool(person.id in roles and roles[person.id].supervisor),
                               "responsible": bool(person.id in roles and roles[person.id].responsible)} for person in people]
            return result

    return router
