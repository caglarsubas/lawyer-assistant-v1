"""Invented local host admission only; no receipt/provider/runtime integration."""

import copy
import gc
import json
import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from host_reconciliation_authority import (  # noqa: E402
    MAX_BODY,
    PATH,
    HostBinding,
    HostReconciliationAuthority,
    _AuthorizationSnapshot,
)

from app.db import Base, Employee, EmployeeRole, FirmRole, LoginSession, User, digest  # noqa: E402
from app.firm_rbac import FirmAuthorization  # noqa: E402

PRINCIPAL, RECORD = "1" * 32, "2" * 32
COOKIE, CSRF = "invented-local-session", "invented-local-csrf"
ORIGIN = "https://isolated.invalid"


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


class TrackedGuards:
    def __init__(self, engine):
        self.real = FirmAuthorization(engine)
        self.active = self.entered = self.released = 0

    @contextmanager
    def guard(self, firm_id, *, exclusive=False):
        with self.real.guard(firm_id, exclusive=exclusive):
            self.active += 1
            self.entered += 1
            try:
                yield
            finally:
                self.active -= 1
                self.released += 1


@pytest.fixture
def host(tmp_path):
    now = [int(datetime.now(timezone.utc).timestamp())]
    engine = create_engine("sqlite:///" + str(tmp_path / "invented-host.sqlite"))
    Base.metadata.create_all(engine)
    store = SimpleNamespace(session=sessionmaker(engine, expire_on_commit=False))
    with store.session() as session:
        session.add(User(id=PRINCIPAL, username="invented", name="Invented reviewer", firm_id="invented-firm",
                         role="lawyer", password_hash="not-a-login-credential", active=True))
        session.flush()
        session.add(Employee(user_id=PRINCIPAL, firm_id="invented-firm", revision=1))
        session.add(FirmRole(id="invented-role", firm_id="invented-firm", name="Invented qualification role",
                             permissions=json.dumps(["firm.manage", "source.curate"]), revision=1))
        session.flush()
        session.add(EmployeeRole(user_id=PRINCIPAL, role_id="invented-role"))
        session.add(LoginSession(token_hash=digest(COOKIE), user_id=PRINCIPAL, csrf=CSRF,
                                 expires_at=utc(now[0] + 600)))
        session.commit()
    guards = TrackedGuards(engine)
    app = SimpleNamespace(state=SimpleNamespace(store=store, settings=SimpleNamespace(origins=(ORIGIN,)),
                                               firm_authorization=guards))
    binding = HostBinding(record_id=RECORD, firm_id="invented-firm", principal_id=PRINCIPAL,
        scope_sha256="a" * 64, source_sha256="b" * 64, permission_sha256="c" * 64,
        enrollment_sha256="d" * 64, trust_registry_sha256="e" * 64,
        issued_at=now[0] - 1, expires_at=now[0] + 300)
    f = SimpleNamespace(app=app, store=store, guards=guards, now=now, binding=binding, calls=[])

    def resolve(record_id, firm_id, principal_id):
        assert guards.active == 1
        f.calls.append((record_id, firm_id, principal_id))
        return f.binding

    f.resolve = resolve
    f.gate = HostReconciliationAuthority(app, resolve, clock=lambda: now[0])
    f.scope = {"type": "http", "method": "POST", "path": PATH, "raw_path": PATH.encode(),
               "query_string": b"", "headers": [(b"origin", ORIGIN.encode()),
               (b"cookie", b"la_session=" + COOKIE.encode()), (b"x-csrf-token", CSRF.encode())]}
    f.body = json.dumps({"record_id": RECORD}).encode()

    def mutate(model, ident, **changes):
        with store.session() as session:
            row = session.get(model, ident)
            for name, value in changes.items():
                setattr(row, name, value)
            session.commit()

    f.mutate = mutate
    try:
        yield f
    finally:
        assert guards.active == 0 and guards.entered == guards.released
        engine.dispose()


def denied(call):
    with pytest.raises(HTTPException) as held:
        call()
    assert held.value.status_code == 403 and held.value.detail == "Host admission withheld"


def test_valid_private_grant_rechecks_without_renewal_or_credential_result(host):
    f = host
    grant = f.gate.authorize(f.scope, f.body)
    assert type(grant) is _AuthorizationSnapshot
    assert grant._expires_at == f.now[0] + 60
    assert f.gate.recheck(grant, f.scope) is grant
    assert f.calls == [(RECORD, "invented-firm", PRINCIPAL)] * 4
    assert f.guards.entered == f.guards.released == 2
    assert repr(grant) == "_AuthorizationSnapshot()"
    assert all(value not in repr(grant) for value in (COOKIE, CSRF, PRINCIPAL, RECORD, digest(COOKIE)))
    with pytest.raises(TypeError):
        json.dumps(grant)
    with pytest.raises(FrozenInstanceError):
        grant._expires_at += 1
    f.now[0] = grant._expires_at
    denied(lambda: f.gate.recheck(grant, f.scope))


@pytest.mark.parametrize("change", [
    {"method": "GET"}, {"path": PATH + "/"}, {"raw_path": b"/wrong"},
    {"query_string": b"record_id=other"}, {"query_string": ""}, {"type": "websocket"},
    {"headers": [(b"x", b"a")] * 65}, {"headers": [(b"x", b"a" * 16385)]},
    {"headers": [(b"bad header", b"x")]}, {"headers": [(b"x", b"\r\n")]},
])
def test_invalid_transport_precedes_lookup(host, change):
    denied(lambda: host.gate.authorize({**host.scope, **change}, host.body))
    assert not host.calls


@pytest.mark.parametrize("name", [b"cookie", b"origin", b"x-csrf-token"])
def test_duplicate_or_missing_security_headers(host, name):
    headers = host.scope["headers"]
    original = next(pair for pair in headers if pair[0] == name)
    for replacement in ([*headers, (name.upper(), original[1])], [pair for pair in headers if pair[0] != name]):
        denied(lambda: host.gate.authorize({**host.scope, "headers": replacement}, host.body))
    assert not host.calls


@pytest.mark.parametrize("name,value", [
    (b"origin", b""), (b"origin", b"https://foreign.invalid"), (b"x-csrf-token", b"wrong"),
    (b"cookie", b"la_session=wrong"),
    (b"cookie", ("la_session=" + COOKIE + "; la_session=" + COOKIE).encode()),
    (b"cookie", ("la_session=" + COOKIE + "; la_session").encode()),
])
def test_invalid_browser_context_does_not_resolve(host, name, value):
    headers = [(key, value if key == name else old) for key, old in host.scope["headers"]]
    denied(lambda: host.gate.authorize({**host.scope, "headers": headers}, host.body))
    assert not host.calls


@pytest.mark.parametrize("body", [
    b"", b"invalid", b"[]", b"null", b"true", b"{\"record_id\":true}", b"{\"record_id\":1}",
    b"{\"record_id\":\"other\"}", b"{\"record_id\":NaN}", b"\xff", b" " * (MAX_BODY + 1),
    ("{\"record_id\":\"" + RECORD + "\",\"record_id\":\"" + RECORD + "\"}").encode(),
    ("{\"record_id\":\"" + RECORD + "\",\"path\":\"forbidden\"}").encode(),
    {"record_id": RECORD},
])
def test_bad_payload_releases_authenticated_guard_before_lookup(host, body):
    denied(lambda: host.gate.authorize(host.scope, body))
    assert not host.calls and host.guards.entered == host.guards.released == 1


def test_authentication_precedes_payload_parsing_and_lookup(host, monkeypatch):
    def forbidden(body):
        pytest.fail("Unauthenticated payload was parsed")
    monkeypatch.setattr(host.gate, "_record", forbidden)
    scope = {**host.scope, "headers": [(key, b"wrong" if key == b"x-csrf-token" else value)
                                      for key, value in host.scope["headers"]]}
    denied(lambda: host.gate.authorize(scope, b"invalid"))
    assert not host.calls and host.guards.entered == host.guards.released == 1


def test_forged_scope_app_and_guard_are_ignored(host):
    class CallerGuard:
        def __exit__(self, *args):
            pytest.fail("Caller guard released")
    caller_state = {"firm_guard": CallerGuard(), "guard_firm_id": "forged"}
    scope = {**host.scope, "app": object(), "state": caller_state}
    grant = host.gate.authorize(scope, host.body)
    assert host.gate.recheck(grant, scope) is grant
    assert scope["state"] is caller_state and caller_state["guard_firm_id"] == "forged"


@pytest.mark.parametrize("model,ident,changes", [
    (User, PRINCIPAL, {"active": False}), (User, PRINCIPAL, {"firm_id": "foreign"}),
    (Employee, PRINCIPAL, {"firm_id": "foreign"}),
    (FirmRole, "invented-role", {"permissions": json.dumps(["firm.manage"])}),
    (FirmRole, "invented-role", {"permissions": json.dumps(["source.curate"])}),
])
def test_wrong_account_or_permissions_withheld_before_lookup(host, model, ident, changes):
    host.mutate(model, ident, **changes)
    denied(lambda: host.gate.authorize(host.scope, host.body))
    assert not host.calls


@pytest.mark.parametrize("field,value", [
    ("record_id", "3" * 32), ("principal_id", "3" * 32), ("firm_id", "foreign"),
])
def test_wrong_trusted_record_actor_or_firm_withheld(host, field, value):
    host.binding = replace(host.binding, **{field: value})
    denied(lambda: host.gate.authorize(host.scope, host.body))
    assert len(host.calls) == 1


@pytest.mark.parametrize("field,value", [
    ("schema", "other"), ("action", "retain"), ("revision", True), ("issued_at", True),
    ("expires_at", 1.5), ("scope_sha256", "invalid"), ("trust_registry_sha256", 123),
])
def test_binding_rejects_wrong_schema_action_and_strict_types(host, field, value):
    with pytest.raises(ValueError, match="Host binding rejected"):
        replace(host.binding, **{field: value})


@pytest.mark.parametrize("field", [
    "scope_sha256", "source_sha256", "permission_sha256", "enrollment_sha256", "trust_registry_sha256", "revision",
])
def test_changed_binding_is_not_silently_reauthorized(host, field):
    grant = host.gate.authorize(host.scope, host.body)
    host.binding = replace(host.binding, **{field: 2 if field == "revision" else "f" * 64})
    denied(lambda: host.gate.recheck(grant, host.scope))


@pytest.mark.parametrize("mutation", ["role_revision", "employee_revision", "permissions", "session", "expiry", "csrf"])
def test_changed_roles_or_session_rejected_on_recheck(host, mutation):
    grant = host.gate.authorize(host.scope, host.body)
    if mutation == "role_revision":
        host.mutate(FirmRole, "invented-role", revision=2)
    elif mutation == "employee_revision":
        host.mutate(Employee, PRINCIPAL, revision=2)
    elif mutation == "permissions":
        host.mutate(FirmRole, "invented-role", permissions=json.dumps(["firm.manage", "source.curate", "system.read"]))
    elif mutation == "session":
        with host.store.session() as session:
            session.delete(session.get(LoginSession, digest(COOKIE)))
            session.commit()
    else:
        host.mutate(LoginSession, digest(COOKIE), **({"expires_at": utc(host.now[0] - 1)} if mutation == "expiry"
                                                    else {"csrf": "changed"}))
    before = len(host.calls)
    denied(lambda: host.gate.recheck(grant, host.scope))
    assert len(host.calls) == before


@pytest.mark.parametrize("mutation", ["session", "role", "binding", "binding_expiry"])
@pytest.mark.parametrize("during_recheck", [False, True])
def test_change_during_resolver_work_is_withheld(host, mutation, during_recheck):
    grant = host.gate.authorize(host.scope, host.body) if during_recheck else None
    changed = False

    def resolver(*args):
        nonlocal changed
        value = host.resolve(*args)
        if not changed:
            changed = True
            if mutation == "session":
                host.mutate(LoginSession, digest(COOKIE), expires_at=utc(host.now[0] - 1))
            elif mutation == "role":
                host.mutate(FirmRole, "invented-role", revision=2)
            elif mutation == "binding":
                host.binding = replace(host.binding, trust_registry_sha256="f" * 64)
            else:
                host.now[0] = host.binding.expires_at
        return value

    host.gate._resolver = resolver
    denied(lambda: host.gate.recheck(grant, host.scope) if during_recheck else host.gate.authorize(host.scope, host.body))


def test_expiry_is_exact_bounded_and_never_renewed(host):
    host.binding = replace(host.binding, expires_at=host.now[0] + 20)
    host.mutate(LoginSession, digest(COOKIE), expires_at=utc(host.now[0] + 10))
    grant = host.gate.authorize(host.scope, host.body)
    assert grant._expires_at == host.now[0] + 10
    host.now[0] += 9
    assert host.gate.recheck(grant, host.scope) is grant
    assert grant._expires_at == host.now[0] + 1
    host.now[0] += 1
    denied(lambda: host.gate.recheck(grant, host.scope))


def test_binding_must_be_current_and_session_expiry_utc(host):
    host.binding = replace(host.binding, issued_at=host.now[0] + 1)
    denied(lambda: host.gate.authorize(host.scope, host.body))
    host.binding = replace(host.binding, issued_at=host.now[0] - 2, expires_at=host.now[0])
    denied(lambda: host.gate.authorize(host.scope, host.body))
    host.binding = replace(host.binding, expires_at=host.now[0] + 10)
    host.mutate(LoginSession, digest(COOKIE), expires_at=datetime.fromtimestamp(host.now[0] + 600).isoformat())
    denied(lambda: host.gate.authorize(host.scope, host.body))


def test_forged_copied_replaced_foreign_and_expired_grants_fail(host):
    grant = host.gate.authorize(host.scope, host.body)
    forged = [object(), object.__new__(_AuthorizationSnapshot), copy.copy(grant), copy.deepcopy(grant),
              replace(grant), replace(grant, _expires_at=grant._expires_at + 60),
              replace(grant, _binding=replace(host.binding, record_id="3" * 32))]
    before = len(host.calls)
    for other in forged:
        denied(lambda: host.gate.recheck(other, host.scope))
    foreign = HostReconciliationAuthority(host.app, host.resolve, clock=lambda: host.now[0])
    denied(lambda: foreign.recheck(grant, host.scope))
    assert len(host.calls) == before


def test_resolver_failure_is_sanitized_and_releases_guard(host):
    def fail(*args):
        assert host.guards.active == 1
        raise RuntimeError("invented-private-diagnostic-must-not-escape")
    host.gate._resolver = fail
    denied(lambda: host.gate.authorize(host.scope, host.body))
    assert host.guards.entered == host.guards.released == 1


def test_unreferenced_grant_is_not_retained_by_authority(host):
    grant = host.gate.authorize(host.scope, host.body)
    assert len(host.gate._issued) == 1
    del grant
    gc.collect()
    assert len(host.gate._issued) == 0
