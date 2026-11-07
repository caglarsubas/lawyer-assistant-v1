"""Unregistered host admission qualification; no receipt IO or execution authority.

The constructor's app and resolver are trusted host wiring. The resolver MUST
authorize the selected record for the supplied firm/principal and freshly check
scope, source, permission, enrollment and trust-registry validity/revocation.
Its immutable metadata is an exact comparison binding, not proof of provenance.
This gate neither implements recipient reconciliation nor bridges legacy planners.
"""

import json
import math
import re
import time
import weakref
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

from app.auth import authenticate
from app.db import Employee, EmployeeRole, FirmRole, LoginSession, User, digest
from app.firm_rbac import permissions_for

PATH = "/api/v1/firm-admin/retention/reconcile"
SCHEMA = "isolated-host-reconciliation-binding-v1"
MAX_BODY, MAX_HEADERS, MAX_HEADER_BYTES, MAX_LIFETIME = 1024, 64, 16384, 60
REQUIRED = frozenset({"firm.manage", "source.curate"})


def _deny():
    raise HTTPException(403, "Host admission withheld") from None


def _token(value, length):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is not None


def _label(value):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value) is not None


def _stamp(value):
    return type(value) is int and 0 <= value < 2**53


@dataclass(frozen=True, kw_only=True)
class HostBinding:
    """Resolver-owned current authorization metadata; never client claims."""

    record_id: str
    firm_id: str
    principal_id: str
    scope_sha256: str
    source_sha256: str
    permission_sha256: str
    enrollment_sha256: str
    trust_registry_sha256: str
    issued_at: int
    expires_at: int
    revision: int = 1
    schema: str = SCHEMA
    action: str = "reconcile"

    def __post_init__(self):
        if (type(self.schema) is not str or self.schema != SCHEMA or type(self.action) is not str
                or self.action != "reconcile" or not _token(self.record_id, 32)
                or not _label(self.firm_id) or not _token(self.principal_id, 32)
                or type(self.revision) is not int or not 1 <= self.revision < 2**53
                or any(not _token(getattr(self, name), 64) for name in (
                    "scope_sha256", "source_sha256", "permission_sha256", "enrollment_sha256", "trust_registry_sha256"))
                or not _stamp(self.issued_at) or not _stamp(self.expires_at)
                or self.issued_at >= self.expires_at):
            raise ValueError("Host binding rejected")


@dataclass(frozen=True)
class _Actor:
    principal_id: str
    firm_id: str
    session_sha256: str = field(repr=False)
    session_version_sha256: str = field(repr=False)
    session_expires_at: int
    roles_sha256: str = field(repr=False)


@dataclass(frozen=True, eq=False)
class _AuthorizationSnapshot:
    """Process-local admission only. No serialization or public response API."""

    _nonce: object = field(repr=False)
    _actor: _Actor = field(repr=False)
    _binding: HostBinding = field(repr=False)
    _issued_at: int = field(repr=False)
    _expires_at: int = field(repr=False)


class HostReconciliationAuthority:
    """Isolated, reconcile-only admission; deliberately not a SessionAuthority.

    Grants last at most 60 seconds, never outlive session/binding validity and
    cannot be renewed by recheck. Callers must recheck before any later separately
    reviewed integration. This does not establish an atomic cross-store snapshot,
    cancellation deadline, custody, retention permission or production readiness.
    No request-supplied app, state, paths, keys or resolver is used.
    """

    def __init__(self, app, resolver, *, clock=None):
        if not callable(resolver) or (clock is not None and not callable(clock)):
            raise ValueError("Host wiring rejected")
        self._app, self._resolver = app, resolver
        self._clock = clock if clock is not None else lambda: int(time.time())
        self._issued = weakref.WeakValueDictionary()

    def _now(self):
        value = self._clock()
        if not _stamp(value):
            _deny()
        return value

    @contextmanager
    def _request(self, scope):
        request = None
        try:
            if (type(scope) is not dict or scope.get("type") != "http" or scope.get("method") != "POST"
                    or scope.get("path") != PATH or scope.get("query_string") != b""
                    or scope.get("raw_path", PATH.encode()) != PATH.encode()):
                _deny()
            headers = scope.get("headers")
            if type(headers) not in (list, tuple) or len(headers) > MAX_HEADERS:
                _deny()
            if any(type(pair) not in (list, tuple) or len(pair) != 2
                   or any(type(part) is not bytes for part in pair) for pair in headers):
                _deny()
            headers = [(name.lower(), value) for name, value in headers]
            if (sum(len(k) + len(v) for k, v in headers) > MAX_HEADER_BYTES
                    or any(not re.fullmatch(rb"[!#$%&'*+.^_`|~0-9a-z-]+", k)
                           or any(c < 32 or c == 127 for c in v) for k, v in headers)):
                _deny()
            for name in (b"cookie", b"origin", b"x-csrf-token"):
                if sum(key == name for key, _ in headers) != 1:
                    _deny()
            origin = next(v for k, v in headers if k == b"origin").decode("ascii")
            if not origin or origin not in self._app.state.settings.origins:
                _deny()
            cookie = next(v for k, v in headers if k == b"cookie").decode("ascii")
            cookies = [part.strip().partition("=") for part in cookie.split(";")]
            selected = [value for name, sep, value in cookies if name == "la_session" and sep]
            if sum(name == "la_session" for name, _, _ in cookies) != 1 or len(selected) != 1 or not selected[0]:
                _deny()
            # Build all security-relevant scope fields locally. Caller app/state
            # and any caller-held firm guard must never enter this Request.
            request = Request({"type": "http", "http_version": "1.1", "method": "POST", "scheme": "https",
                               "path": PATH, "raw_path": PATH.encode(), "root_path": "", "query_string": b"",
                               "headers": headers, "app": self._app, "state": {}})
            yield request
        except Exception:  # noqa: BLE001 - withhold arbitrary trusted-resolver diagnostics at admission
            _deny()
        finally:
            if request is not None:
                guard = request.scope["state"].get("firm_guard")
                if guard is not None:
                    guard.__exit__(None, None, None)

    def _actor(self, request):
        user = authenticate(request)
        if not REQUIRED <= user.action_permissions:
            _deny()
        session_hash = digest(request.cookies.get("la_session", ""))
        with self._app.state.store.session() as session:
            login = session.get(LoginSession, session_hash)
            current = session.get(User, user.id)
            employee = session.get(Employee, user.id)
            if (not login or login.user_id != user.id or not current or not current.active
                    or current.firm_id != user.firm_id or not employee or employee.firm_id != user.firm_id
                    or not _token(user.id, 32) or not _label(user.firm_id)):
                _deny()
            permissions = permissions_for(session, current)
            if not REQUIRED <= permissions:
                _deny()
            roles = session.execute(select(EmployeeRole.role_id, FirmRole.firm_id, FirmRole.revision, FirmRole.permissions)
                .outerjoin(FirmRole, EmployeeRole.role_id == FirmRole.id)
                .where(EmployeeRole.user_id == user.id).order_by(EmployeeRole.role_id)).all()
            if not roles or len(roles) > 32 or any(row[1] != user.firm_id or row[2] is None for row in roles):
                _deny()
            expiry = datetime.fromisoformat(login.expires_at)
            if expiry.tzinfo is None or expiry.utcoffset() != timedelta(0):
                _deny()
            expires_at = math.floor(expiry.timestamp())
            if self._now() >= expires_at:
                _deny()
            version = digest(json.dumps([login.user_id, login.csrf, login.expires_at], separators=(",", ":")))
            role_version = digest(json.dumps([current.role, employee.revision, sorted(permissions),
                                               [list(row) for row in roles]], separators=(",", ":")))
        return _Actor(user.id, user.firm_id, session_hash, version, expires_at, role_version)

    @staticmethod
    def _record(body):
        if type(body) is not bytes or not 0 < len(body) <= MAX_BODY:
            _deny()

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    _deny()
                result[key] = value
            return result

        value = json.loads(body, object_pairs_hook=unique, parse_constant=lambda _: _deny())
        if type(value) is not dict or set(value) != {"record_id"} or not _token(value["record_id"], 32):
            _deny()
        return value["record_id"]

    def _binding(self, record_id, actor):
        binding = self._resolver(record_id, actor.firm_id, actor.principal_id)
        if type(binding) is not HostBinding:
            _deny()
        binding.__post_init__()
        if (binding.record_id != record_id or binding.firm_id != actor.firm_id
                or binding.principal_id != actor.principal_id or not binding.issued_at <= self._now() < binding.expires_at):
            _deny()
        return binding

    def authorize(self, scope, body):
        """Authenticate before JSON decoding/selected-record resolution."""
        with self._request(scope) as request:
            actor = self._actor(request)
            record_id = self._record(body)
            binding = self._binding(record_id, actor)
            if (self._actor(request) != actor or self._binding(record_id, actor) != binding
                    or self._actor(request) != actor):
                _deny()
            now = self._now()
            expiry = min(now + MAX_LIFETIME, actor.session_expires_at, binding.expires_at)
            if now < binding.issued_at or now >= expiry:
                _deny()
            snapshot = _AuthorizationSnapshot(object(), actor, binding, now, expiry)
            self._issued[snapshot._nonce] = snapshot
            return snapshot

    def recheck(self, snapshot, scope):
        """Fresh authentication and trusted resolution; return the same grant."""
        if (type(snapshot) is not _AuthorizationSnapshot
                or type(getattr(snapshot, "_nonce", None)) is not object
                or self._issued.get(snapshot._nonce) is not snapshot
                or not snapshot._issued_at <= self._now() < snapshot._expires_at):
            _deny()
        with self._request(scope) as request:
            actor = self._actor(request)
            if actor != snapshot._actor:
                _deny()
            binding = self._binding(snapshot._binding.record_id, actor)
            if (binding != snapshot._binding or self._actor(request) != actor
                    or self._binding(binding.record_id, actor) != binding or self._actor(request) != actor):
                _deny()
            if not snapshot._issued_at <= self._now() < snapshot._expires_at:
                _deny()
            return snapshot
