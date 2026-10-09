"""Revision-bound administration of same-firm employees and supported action roles."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from .auth import authenticate, hash_password
from .content_scope import invalidate_scope, remove_queued, scoped_records, scoped_users
from .db import Audit, Employee, EmployeeRole, FirmRole, Record, User, now
from .firm_rbac import CATALOG, initialize_firm, permissions_for, require_permission, validate_permissions


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RoleInput(StrictInput):
    name: str = Field(min_length=1, max_length=100)
    permissions: list[str] = Field(max_length=len(CATALOG))

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Geçerli bir ad girin")
        return value.strip()


class RoleEdit(RoleInput):
    revision: int = Field(ge=1)


class EmployeeInput(StrictInput):
    username: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=16, max_length=200)
    professional_role: str = Field(pattern="^(lawyer|curator)$", default="lawyer")
    role_ids: list[str] = Field(max_length=20)
    manager_id: str | None = Field(default=None, max_length=64)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value):
        if value != value.strip() or any(c.isspace() or ord(c) < 32 for c in value):
            raise ValueError("Geçerli bir kullanıcı adı girin")
        return value

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        return RoleInput.clean_name(value)


class EmployeeEdit(StrictInput):
    name: str = Field(min_length=1, max_length=100)
    role_ids: list[str] = Field(max_length=20)
    manager_id: str | None = Field(default=None, max_length=64)
    active: bool
    revision: int = Field(ge=1)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        return RoleInput.clean_name(value)


def _audit(store, session, actor, action, target, before, after):
    change = store.add(session, "firm_change", actor,
                       {"action": action, "target_id": target, "before": before, "after": after,
                        "recorded_at": now()})
    session.add(Audit(actor_id=actor.id, action=action, object_id=change.id))


def _role_view(role):
    return {"id": role.id, "name": role.name, "permissions": sorted(validate_permissions(json.loads(role.permissions))),
            "revision": role.revision, "starter": role.starter}


def _employee_view(session, user):
    employee = session.get(Employee, user.id)
    return {"id": user.id, "name": user.name, "username": user.username, "professional_role": user.role,
            "active": user.active, "manager_id": employee.manager_id, "revision": employee.revision,
            "role_ids": list(session.scalars(select(EmployeeRole.role_id).where(EmployeeRole.user_id == user.id))),
            "permissions": sorted(permissions_for(session, user))}


def _admit(session, user):
    # The request holds the exclusive firm advisory lock until the response is built.
    users = session.scalars(select(User).where(User.firm_id == user.firm_id).order_by(User.id)
                            .with_for_update().execution_options(populate_existing=True)).all()
    require_permission(session, user, "firm.manage")
    initialize_firm(session, user.firm_id)
    return users


def _roles(session, firm_id, ids):
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Yinelenen rol")
    roles = session.scalars(select(FirmRole).where(FirmRole.id.in_(ids), FirmRole.firm_id == firm_id)).all()
    if len(roles) != len(ids):
        raise HTTPException(404, "Rol bulunamadı")
    for role in roles:
        validate_permissions(json.loads(role.permissions))
    return roles


def _manager(session, firm_id, user_id, manager_id):
    cursor, seen = manager_id, {user_id}
    while cursor:
        if cursor in seen:
            raise HTTPException(422, "Organizasyon döngüsü veya kişinin kendisine bağlılığı kabul edilemez")
        seen.add(cursor)
        manager = session.get(User, cursor)
        if not manager or manager.firm_id != firm_id or not manager.active:
            raise HTTPException(404, "Aktif yönetici bulunamadı")
        employee = session.get(Employee, cursor)
        cursor = employee.manager_id if employee else None


def _retain_administrator(session, users):
    if not any(user.active and "firm.manage" in permissions_for(session, user) for user in users):
        raise HTTPException(409, "En az bir aktif büro yöneticisi korunmalı")


def firm_admin_router():
    router = APIRouter(prefix="/api/v1/firm-admin", tags=["firm-administration"])

    @router.get("")
    def overview(request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            users = _admit(session, user)
            roles = session.scalars(select(FirmRole).where(FirmRole.firm_id == user.firm_id)
                                    .order_by(FirmRole.name, FirmRole.id)).all()
            result = {"permissions": [{"id": key, "label": value} for key, value in CATALOG.items()],
                      "roles": [_role_view(role) for role in roles],
                      "employees": [_employee_view(session, item) for item in users],
                      "content_access": "explicit_assignments_only", "hierarchy_grants_access": False}
            session.commit()
            return result

    @router.post("/roles", status_code=201)
    def create_role(body: RoleInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            _admit(session, user)
            roles = session.scalars(select(FirmRole).where(FirmRole.firm_id == user.firm_id)).all()
            if len(roles) >= 50 or any(role.name.casefold() == body.name.casefold() for role in roles):
                raise HTTPException(409, "Rol adı kullanılıyor veya rol sınırına ulaşıldı")
            role = FirmRole(firm_id=user.firm_id, name=body.name,
                            permissions=json.dumps(sorted(validate_permissions(body.permissions))))
            session.add(role)
            session.flush()
            result = _role_view(role)
            _audit(store, session, user, "firm_role_created", role.id, None, result)
            session.commit()
            return result

    @router.put("/roles/{role_id}")
    def edit_role(role_id: str, body: RoleEdit, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            users = _admit(session, user)
            role = _roles(session, user.firm_id, [role_id])[0]
            if role.starter:
                raise HTTPException(409, "Başlangıç rolü değiştirilemez; özel rol oluşturun")
            if role.revision != body.revision:
                raise HTTPException(409, "Rol değişti; yenileyin")
            if session.scalar(select(FirmRole.id).where(FirmRole.firm_id == user.firm_id,
                                                       FirmRole.name == body.name, FirmRole.id != role.id)):
                raise HTTPException(409, "Rol adı kullanılıyor")
            before = _role_view(role)
            role.name, role.permissions = body.name, json.dumps(sorted(validate_permissions(body.permissions)))
            role.revision += 1
            session.flush()
            _retain_administrator(session, users)
            affected = list(session.scalars(select(EmployeeRole.user_id).where(EmployeeRole.role_id == role.id)))
            stopped = invalidate_scope(store, session, user.firm_id, affected)
            for employee in session.scalars(select(Employee).where(Employee.user_id.in_(affected))):
                employee.revision += 1
            result = _role_view(role)
            _audit(store, session, user, "firm_role_updated", role.id, before, result)
            session.commit()
            remove_queued(request.app, stopped)
            return result

    @router.post("/employees", status_code=201)
    def create_employee(body: EmployeeInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            users = _admit(session, user)
            if len(users) >= 500:
                raise HTTPException(409, "Çalışan sınırına ulaşıldı")
            if session.scalar(select(User.id).where(User.username == body.username)):
                raise HTTPException(409, "Kullanıcı adı kullanılamıyor; mevcut parola değiştirilmedi")
            roles = _roles(session, user.firm_id, body.role_ids)
            target = User(username=body.username, name=body.name, firm_id=user.firm_id,
                          role=body.professional_role, password_hash=hash_password(body.password))
            session.add(target)
            try:
                session.flush()
            except IntegrityError:
                raise HTTPException(409, "Kullanıcı adı kullanılamıyor") from None
            _manager(session, user.firm_id, target.id, body.manager_id)
            session.add(Employee(user_id=target.id, firm_id=user.firm_id, manager_id=body.manager_id))
            session.flush()
            session.add_all([EmployeeRole(user_id=target.id, role_id=role.id) for role in roles])
            session.flush()
            result = _employee_view(session, target)
            _audit(store, session, user, "firm_employee_created", target.id, None, result)
            try:
                session.commit()
            except IntegrityError:
                raise HTTPException(409, "Kullanıcı adı kullanılamıyor") from None
            return result

    @router.put("/employees/{user_id}")
    def edit_employee(user_id: str, body: EmployeeEdit, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            users = _admit(session, user)
            target = next((item for item in users if item.id == user_id), None)
            if not target:
                raise HTTPException(404, "Çalışan bulunamadı")
            employee = session.get(Employee, user_id)
            if employee.revision != body.revision:
                raise HTTPException(409, "Çalışan değişti; yenileyin")
            roles = _roles(session, user.firm_id, body.role_ids)
            _manager(session, user.firm_id, user_id, body.manager_id)
            if not body.active:
                if session.scalar(select(Employee.user_id).where(Employee.manager_id == user_id)):
                    raise HTTPException(409, "Önce bağlı çalışanların yöneticisini değiştirin")
                # Preserve the offline administrator's no-stranded-matter guarantee.
                for matter in session.scalars(scoped_records(target, ("matter", "archived_matter"))):
                    if not any(person.id != user_id for person in scoped_users(session, matter.id, user.firm_id)):
                        raise HTTPException(409, "Son aktif dosya üyesi devre dışı bırakılamaz")
            before = _employee_view(session, target)
            target.name, target.active = body.name, body.active
            employee.manager_id, employee.revision = body.manager_id, employee.revision + 1
            session.execute(delete(EmployeeRole).where(EmployeeRole.user_id == user_id))
            session.add_all([EmployeeRole(user_id=user_id, role_id=role.id) for role in roles])
            session.flush()
            _retain_administrator(session, users)
            stopped = invalidate_scope(store, session, user.firm_id, [user_id])
            result = _employee_view(session, target)
            _audit(store, session, user, "firm_employee_updated", user_id, before, result)
            session.commit()
            remove_queued(request.app, stopped)
            return result

    @router.get("/changes")
    def changes(request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            require_permission(session, user, "firm.manage")
            rows = session.scalars(select(Record).where(Record.kind.in_(["firm_change", "access_change"]), Record.firm_id == user.firm_id)
                                   .order_by(Record.created_at.desc(), Record.id).limit(100)).all()
            return {"items": [{**store.view(row), "actor_id": row.owner_id} for row in rows], "limit": 100}

    return router
