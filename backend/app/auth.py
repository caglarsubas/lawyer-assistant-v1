import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import select

from .content_scope import has_case_scope
from .db import LoginSession, Record, User, digest
from .firm_rbac import permissions_for, require_permission, route_permissions


def hash_password(password):
    salt = secrets.token_hex(16)
    return salt + ":" + hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()


def check_password(password, stored):
    salt, expected = stored.split(":")
    actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(actual, expected)


def user_view(user):
    return {"id": user.id, "name": user.name, "role": user.role, "firm_id": user.firm_id,
            "permissions": sorted(getattr(user, "action_permissions", []))}


def hold_firm_guard(request, firm_id):
    if getattr(request.state, "firm_guard", None):
        if request.state.guard_firm_id != firm_id:
            raise HTTPException(401, "Oturum veya kurum değişti")
        return
    guard = request.app.state.firm_authorization.guard(
        firm_id, exclusive=(request.url.path.startswith("/api/v1/firm-admin")
            or (request.method not in {"GET", "HEAD", "OPTIONS"} and (
                request.url.path in {"/api/v1/customers", "/api/v1/workspaces", "/api/v1/matters"}
                or (request.url.path.startswith("/api/v1/workspaces/") and request.url.path.endswith("/customers")))))
    )
    guard.__enter__()
    request.state.firm_guard = guard
    request.state.guard_firm_id = firm_id


def authenticate(request: Request):
    token = request.cookies.get("la_session", "")
    with request.app.state.store.session() as session:
        login = session.get(LoginSession, digest(token)) if token else None
        if not login or datetime.fromisoformat(login.expires_at) <= datetime.now(timezone.utc):
            raise HTTPException(401, "Oturum açmanız gerekiyor")
        user = session.get(User, login.user_id)
        if not user or not user.active:
            raise HTTPException(401, "Oturum geçersiz")
        if not getattr(request.state, "firm_guard", None):
            hold_firm_guard(request, user.firm_id)
            # Account/session may have changed while admission waited for an update.
            session.expire_all()
            login = session.get(LoginSession, digest(token))
            user = session.get(User, login.user_id) if login else None
            if not user or not user.active or datetime.fromisoformat(login.expires_at) <= datetime.now(timezone.utc):
                raise HTTPException(401, "Oturum geçersiz")
        hold_firm_guard(request, user.firm_id)
        user.action_permissions = permissions_for(session, user)
        if not route_permissions(request.url.path, request.method) <= user.action_permissions:
            raise HTTPException(403, "Bu işlem için rol izniniz yok")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin not in request.app.state.settings.origins:
                raise HTTPException(403, "Origin denied")
            if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), login.csrf):
                raise HTTPException(403, "CSRF doğrulaması başarısız")
        request.state.csrf = login.csrf
        return user


def require_matter(session, matter_id, user):
    current = session.get(User, user.id, populate_existing=True)
    if not current or not current.active or current.firm_id != user.firm_id:
        raise HTTPException(401, "Oturum geçersiz")
    matter = session.get(Record, matter_id)
    if not matter or matter.kind != "matter" or matter.firm_id != user.firm_id or not has_case_scope(session, matter_id, user):
        raise HTTPException(404, "Dosya bulunamadı")
    require_permission(session, current, "matter.read")
    return matter


def require_child(session, record_id, kind, matter_id, user):
    require_matter(session, matter_id, user)
    rec = session.get(Record, record_id)
    if not rec or rec.kind != kind or rec.matter_id != matter_id or rec.firm_id != user.firm_id:
        raise HTTPException(404, "Kayıt bulunamadı")
    return rec


def bootstrap(store, settings):
    username = "demo" if settings.demo_mode else settings.bootstrap_username
    password = "demo-local-only" if settings.demo_mode else settings.bootstrap_password
    if not username:
        raise ValueError("Configure LA_BOOTSTRAP_USERNAME and LA_BOOTSTRAP_PASSWORD")
    with store.session() as session:
        # Bootstrap credentials only create an account; existing identity and
        # authentication state must survive later configuration edits.
        if session.scalar(select(User.id).where(User.username == username)):
            return
        if not password:
            raise ValueError("Configure LA_BOOTSTRAP_USERNAME and LA_BOOTSTRAP_PASSWORD")
        if not settings.demo_mode and len(password) < 16:
            raise ValueError("Bootstrap password must contain at least 16 characters")
        session.add(
            User(
                username=username,
                name="Demo Avukat" if settings.demo_mode else username,
                firm_id="demo-firm" if settings.demo_mode else "org-lawyer",
                role="admin",
                password_hash=hash_password(password),
            )
        )
        session.commit()


def create_session(session, user, hours):
    token = secrets.token_urlsafe(32)
    login = LoginSession(
        token_hash=digest(token),
        user_id=user.id,
        csrf=secrets.token_urlsafe(32),
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(),
    )
    session.add(login)
    session.commit()
    return token, login.csrf
