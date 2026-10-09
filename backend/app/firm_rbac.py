"""Firm action permissions. Content membership and reviewer eligibility remain separate."""

import json
import threading
from contextlib import contextmanager
from functools import wraps

from fastapi import HTTPException
from sqlalchemy import select, text

from .db import Employee, EmployeeRole, FirmRole, Record, User, digest

CATALOG = {
    "firm.manage": "Çalışan, organizasyon ve rol yapılandırmasını yönet",
    "portfolio.read": "Yetkili müvekkilleri ve portföyü görüntüle",
    "portfolio.create": "Müvekkil ve çalışma alanı oluştur",
    "matter.read": "Açıkça yetkili çalışma alanı içeriğini görüntüle",
    "matter.write": "Yetkili alanda belge, yorum ve analiz oluştur/düzenle",
    "matter.review": "Yetkili alanda insan incelemesi kaydet",
    "matter.export": "Yetkili alandan çıktı al",
    "matter.lifecycle": "Yetkili alanın saklama ve arşiv işlemlerini yönet",
    "source.curate": "Kaynak hazırlama ve inceleme iş akışını kullan",
    "source.assign": "Başka incelemecinin kaynak atamasını kaldır",
    "playbook.manage": "Kurum rehberlerini düzenle",
    "system.read": "Sistem, kapsam ve genel hukuk haritasını görüntüle",
}
LAWYER = frozenset({"portfolio.read", "portfolio.create", "matter.read", "matter.write",
                    "matter.review", "matter.export", "system.read"})
CURATOR = LAWYER | {"source.curate", "playbook.manage"}
LEGACY = {"lawyer": LAWYER, "curator": CURATOR, "admin": frozenset(CATALOG),
          "reader": frozenset({"portfolio.read", "matter.read", "matter.export", "system.read"})}
STARTERS = {"Avukat": LAWYER, "Küratör": CURATOR,
            "Büro yöneticisi (yapılandırma)": frozenset({"firm.manage", "system.read"}),
            "Mevcut yönetici": LEGACY["admin"], "Salt okuma": LEGACY["reader"]}
DEPENDENCIES = {"matter.write": {"matter.read"}, "matter.review": {"matter.read", "matter.write"},
                "matter.export": {"matter.read"}, "matter.lifecycle": {"matter.read", "matter.write"},
                "portfolio.create": {"portfolio.read", "matter.read", "matter.write"},
                "source.assign": {"source.curate"}}


def validate_permissions(values):
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        raise HTTPException(422, "Geçersiz izin listesi")
    permissions = frozenset(values)
    if len(values) != len(permissions) or not permissions <= CATALOG.keys():
        raise HTTPException(422, "Desteklenmeyen veya yinelenen izin")
    if any(not required <= permissions for item, required in DEPENDENCIES.items() if item in permissions):
        raise HTTPException(422, "İzin için gerekli görüntüleme/düzenleme izinlerini de seçin")
    return permissions


def permissions_for(session, user):
    employee = session.get(Employee, user.id, populate_existing=True)
    if employee is None:
        # Compatibility for pre-migration accounts; migration creates an explicit
        # Employee even for users with no roles, so an empty assignment denies.
        return LEGACY.get(user.role, frozenset()) if user.active else frozenset()
    if employee.firm_id != user.firm_id or not user.active:
        return frozenset()
    roles = session.execute(select(EmployeeRole.role_id, FirmRole.firm_id, FirmRole.permissions)
                            .outerjoin(FirmRole, EmployeeRole.role_id == FirmRole.id)
                            .where(EmployeeRole.user_id == user.id)).all()
    permissions = set()
    for _, firm, encoded in roles:
        if firm != user.firm_id:
            return frozenset()
        try:
            permissions.update(validate_permissions(json.loads(encoded)))
        except (HTTPException, TypeError, ValueError):
            return frozenset()
    return frozenset(permissions)


def require_permission(session, user, permission):
    current = session.get(User, user.id, populate_existing=True)
    if not current or not current.active or current.firm_id != user.firm_id:
        raise HTTPException(401, "Oturum geçersiz")
    if permission not in permissions_for(session, current):
        raise HTTPException(403, "Bu işlem için rol izniniz yok")
    return current


def route_permissions(path, method):
    """Additional action gates; existing scoped authorization still runs in handlers."""
    parts = path.removeprefix("/api/v1/").strip("/").split("/")
    root = parts[0]
    read = method in {"GET", "HEAD", "OPTIONS"}
    if root in {"auth", "health", "bootstrap"}:
        return set()
    if root == "firm-admin":
        return {"firm.manage"}
    if root == "customers":
        return {"portfolio.read" if read else "portfolio.create"}
    if root == "assistant":
        return {"system.read"}
    if root == "public-sources":
        return {"source.curate"}
    if root == "playbooks":
        return {"portfolio.read" if read else "playbook.manage"}
    if root in {"matters", "workspaces", "governance"}:
        required = {"matter.read"}
        if not read:
            required.add("portfolio.create" if len(parts) == 1 else "matter.write")
        if any(part in {"export", "exports"} for part in parts):
            required.add("matter.export")
        if not read and any(part in {"reviews", "review", "observations", "adjudications"} for part in parts):
            required.add("matter.review")
        if (root == "governance" and not read) or any(part in {
            "legal-holds", "retention-policy", "erasure-plan", "restore"
        } for part in parts):
            required.add("matter.lifecycle")
        return required
    if root in {"graphs", "coverage", "status", "readiness", "intake"}:
        return {"system.read"}
    raise HTTPException(403, "Bu API işlemi izin kataloğunda tanımlı değil")


def initialize_firm(session, firm_id):
    """Idempotent additive migration; never modifies memberships, credentials or records."""
    roles = session.scalars(select(FirmRole).where(FirmRole.firm_id == firm_id)).all()
    starters = {role.name: role for role in roles if role.starter}
    for name, permissions in STARTERS.items():
        if name not in starters:
            role = FirmRole(firm_id=firm_id, name=name, permissions=json.dumps(sorted(permissions)), starter=True)
            session.add(role)
            session.flush()
            starters[name] = role
    names = {"admin": "Mevcut yönetici", "curator": "Küratör", "lawyer": "Avukat", "reader": "Salt okuma"}
    for user in session.scalars(select(User).where(User.firm_id == firm_id).order_by(User.id)):
        if session.get(Employee, user.id) is not None:
            continue
        session.add(Employee(user_id=user.id, firm_id=firm_id))
        session.flush()
        if user.role in names:
            session.add(EmployeeRole(user_id=user.id, role_id=starters[names[user.role]].id))


class _ReadersWriter:
    """Demo-only in-process coordination; production uses shared PostgreSQL locks."""

    def __init__(self):
        self.condition = threading.Condition()
        self.readers = 0
        self.writer = False
        self.waiting = 0

    @contextmanager
    def guard(self, exclusive):
        with self.condition:
            if exclusive:
                self.waiting += 1
                try:
                    if not self.condition.wait_for(lambda: not self.writer and not self.readers, timeout=15):
                        raise HTTPException(503, "Yetki güncellemesi bekleniyor; tekrar deneyin")
                    self.writer = True
                finally:
                    self.waiting -= 1
            else:
                if not self.condition.wait_for(lambda: not self.writer and not self.waiting, timeout=15):
                    raise HTTPException(503, "Yetki güncellemesi bekleniyor; tekrar deneyin")
                self.readers += 1
        try:
            yield
        finally:
            with self.condition:
                if exclusive:
                    self.writer = False
                else:
                    self.readers -= 1
                self.condition.notify_all()


class FirmAuthorization:
    locks = {}
    mutex = threading.Lock()

    def __init__(self, engine):
        self.engine = engine

    @contextmanager
    def guard(self, firm_id, *, exclusive=False):
        if self.engine.dialect.name == "postgresql":
            key = int(digest("lawyer-firm-rbac-v1:" + firm_id)[:15], 16)
            suffix = "" if exclusive else "_shared"
            with self.engine.connect() as connection:
                connection.execute(text("SET LOCAL statement_timeout = '15000'"))
                try:
                    connection.execute(text(f"SELECT pg_advisory_lock{suffix}(:key)"), {"key": key})
                except Exception:
                    raise HTTPException(503, "Yetki güncellemesi sürüyor; tekrar deneyin") from None
                try:
                    yield
                finally:
                    connection.rollback()
                    try:
                        connection.execute(text(f"SELECT pg_advisory_unlock{suffix}(:key)"), {"key": key})
                        connection.commit()
                    except Exception:
                        # Never return a session-level lock to the connection pool.
                        connection.invalidate()
        else:
            with self.mutex:
                lock = self.locks.setdefault((str(self.engine.url), firm_id), _ReadersWriter())
            with lock.guard(exclusive):
                yield


class FirmGuardMiddleware:
    """Release admission only after the complete ASGI response, including file bodies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        try:
            await self.app(scope, receive, send)
        finally:
            if scope["type"] == "http":
                guard = scope.get("state", {}).get("firm_guard")
                if guard:
                    guard.__exit__(None, None, None)


def guard_job_write(function):
    """Serialize short publication/checkpoint writes; never hold locks during inference."""
    @wraps(function)
    def guarded(app, run_id, *args, **kwargs):
        store = app.state.store
        with store.session() as session:
            run = session.get(Record, run_id)
            if not run or run.kind != "research":
                raise HTTPException(404, "Araştırma bulunamadı")
            firm_id, owner_id, matter_id = run.firm_id, run.owner_id, run.matter_id
        authorization = getattr(app.state, "firm_authorization", None) or FirmAuthorization(store.engine)
        with authorization.guard(firm_id):
            with store.session() as session:
                owner = session.get(User, owner_id)
                if not owner or owner.firm_id != firm_id:
                    raise HTTPException(401, "Araştırma yetkisi değişti")
                require_permission(session, owner, "matter.write")
                from .auth import require_matter

                require_matter(session, matter_id, owner)
            return function(app, run_id, *args, **kwargs)
    return guarded
