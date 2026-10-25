"""Unregistered disposable adapter around the real local session/RBAC checks."""

from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import operator_enrollment_evidence as evidence
from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

from app.auth import authenticate
from app.db import Employee, EmployeeRole, FirmRole, LoginSession, Record, Store, User, digest
from app.firm_rbac import FirmAuthorization, permissions_for

PROFILE = "disposable-operator-review-v1"
REQUIRED = {"preparer": {"firm.manage"}, "reviewer": {"firm.manage", "source.curate"}}


def deny():
    raise HTTPException(403, "Operator session rejected")


class SessionAuthority:
    """No login/provisioning API. Accepts only an empty disposable SQLite store.

    Cookies are checked by app.auth.authenticate, including live account/RBAC,
    origin and CSRF checks. No production PostgreSQL or matter store is accepted.
    """

    def __init__(self, store, profile_root, *, firm_id, bindings, origins):
        if not isinstance(store, Store) or store.engine.dialect.name != "sqlite":
            deny()
        self.root = evidence.directory(profile_root)
        self.database = Path(store.engine.url.database).absolute()
        if self.database != self.root / "disposable-identities.sqlite":
            deny()
        marker = evidence.read(self.root / "disposable-profile.json")
        value = evidence.decode(marker)
        if (set(value) != {"schema", "profile_id", "production_activation"} or value["schema"] != PROFILE
                or value["production_activation"] is not False):
            deny()
        self.profile_id = evidence.token(value["profile_id"], 32)
        self.marker_sha = evidence.sha(marker)
        self.firm_id = evidence.label(firm_id)
        if not isinstance(bindings, dict) or not 2 <= len(bindings) <= 16 or set(bindings.values()) != set(REQUIRED):
            deny()
        for key in bindings:
            evidence.token(key, 32)
        self.bindings = MappingProxyType(dict(bindings))
        if not isinstance(origins, tuple) or not origins or len(origins) > 4:
            deny()
        self.store = store
        self.app = SimpleNamespace(state=SimpleNamespace(store=store, settings=SimpleNamespace(origins=origins),
                                                        firm_authorization=FirmAuthorization(store.engine)))
        info = self.database.lstat()
        self.file_identity = (info.st_dev, info.st_ino)
        self.validate_profile()

    def validate_profile(self):
        if evidence.sha(evidence.read(self.root / "disposable-profile.json")) != self.marker_sha:
            deny()
        # The account DB is intentionally mutable; pin its namespace and inode,
        # not its bytes. SQLite/IdP joint rollback is not qualified by this stage.
        import os
        import stat

        info = self.database.lstat()
        if (self.database != self.database.resolve() or (info.st_dev, info.st_ino) != self.file_identity
                or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600):
            deny()
        with self.store.session() as session:
            if session.scalar(select(Record.id).limit(1)) is not None:
                deny()  # Refuse a store containing even one private/application record.

    def eligible(self, user_id, kind):
        self.validate_profile()
        if kind not in REQUIRED or self.bindings.get(user_id) != kind:
            deny()
        with self.store.session() as session:
            user = session.get(User, user_id)
            employee = session.get(Employee, user_id)
            if not user or not user.active or user.firm_id != self.firm_id or not employee or employee.firm_id != self.firm_id:
                deny()
            permissions = permissions_for(session, user)
            if not REQUIRED[kind] <= permissions:
                deny()
            rows = session.execute(select(EmployeeRole.role_id, FirmRole.revision, FirmRole.permissions)
                                   .outerjoin(FirmRole, EmployeeRole.role_id == FirmRole.id)
                                   .where(EmployeeRole.user_id == user_id).order_by(EmployeeRole.role_id)).all()
            if not rows or len(rows) > 32 or any(row[1] is None for row in rows):
                deny()
            role_evidence = {"employee_revision": employee.revision, "permissions": sorted(permissions),
                             "roles": [list(row) for row in rows]}
        return {"user_id": user_id, "firm_id": self.firm_id, "kind": kind,
                "profile_id": self.profile_id, "role_sha256": evidence.sha(evidence.encode(role_evidence))}

    def snapshot(self, session_hash, user_id, kind, *, now):
        result = self.eligible(user_id, kind)
        with self.store.session() as session:
            login = session.get(LoginSession, evidence.token(session_hash))
            if not login or login.user_id != user_id:
                deny()
            expiry = datetime.fromisoformat(login.expires_at)
            if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc) or expiry.timestamp() <= now:
                deny()
            result.update(session_sha256=session_hash, expires_at=int(expiry.timestamp()))
        return result

    def resolve(self, scope, kind, *, now):
        scope["app"] = self.app
        request = Request(scope)
        user = authenticate(request)  # Real cookie, current session, origin, CSRF and permission checks.
        if kind is None:
            kind = self.bindings.get(user.id)
        actor = self.snapshot(digest(request.cookies.get("la_session", "")), user.id, kind, now=now)
        if actor["firm_id"] != user.firm_id:
            deny()
        return actor

    def recheck(self, actor, *, now):
        if self.snapshot(actor["session_sha256"], actor["user_id"], actor["kind"], now=now) != actor:
            deny()
        return actor
