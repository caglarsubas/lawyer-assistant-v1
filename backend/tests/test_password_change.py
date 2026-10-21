"""Synthetic self-service credentials only; never private cases or live inference."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from graph_b_test_seeds import cloned_empty_workspace, login
from sqlalchemy import delete, event, select
from sqlalchemy.exc import SQLAlchemyError

from app.auth import bootstrap, check_password, hash_password
from app.db import Audit, Base, LoginSession, User
from app.password_change import PasswordChange

OLD = "demo-local-only"
NEW = "  Türkçe yeni parola 2026  "
PATH = "/api/v1/auth/password"


@pytest.fixture
def account(tmp_path, synthetic_empty_source_workspace):
    with cloned_empty_workspace(synthetic_empty_source_workspace, tmp_path) as value:
        yield value


def body(**changes):
    return {"current_password": OLD, "new_password": NEW, "confirm_password": NEW, **changes}


def auth_state(app):
    with app.state.store.session() as session:
        return {"users": [tuple(row) for row in session.execute(select(User.__table__).order_by(User.id))],
                "sessions": [tuple(row) for row in session.execute(select(LoginSession.__table__).order_by(LoginSession.token_hash))]}


def private_state(app):
    with app.state.store.session() as session:
        return {table.name: sorted([tuple(row) for row in session.execute(select(table))], key=repr)
                for table in Base.metadata.sorted_tables if table.name not in {"users", "sessions", "audit"}}


def test_atomic_change_revokes_all_own_sessions_preserves_other_accounts_and_private_bytes(account):
    app, owner, matter = account
    store = app.state.store
    uploaded = owner.post(f"/api/v1/matters/{matter}/documents", files={
        "file": ("synthetic.txt", b"Synthetic original evidence stays unchanged.", "text/plain")})
    assert uploaded.status_code == 201
    with store.session() as session:
        user = session.scalar(select(User).where(User.username == "demo"))
        uid = user.id
        store.add(session, "review_fixture", user, {"status": "needs_review", "version": 3,
                  "history": [{"version": 1, "decision": "retained"}]}, matter)
        session.add(User(username="password-peer", name="Synthetic peer", firm_id=user.firm_id,
                         role="lawyer", password_hash=hash_password("synthetic-peer-password")))
        session.commit()
    sibling = login(app, "demo", OLD)
    peer = login(app, "password-peer", "synthetic-peer-password")
    try:
        before = private_state(app)
        auth_before = auth_state(app)
        original = {path.name: path.read_bytes() for path in (app.state.settings.data_dir / "documents").glob("*.enc")}
        with store.session() as session:
            audits_before = {row.id: tuple(row) for row in session.execute(select(Audit.__table__))}
        result = owner.post(PATH, json=body())
        assert result.status_code == 200
        assert result.json() == {"ok": True, "reauthentication_required": True}
        assert result.headers["cache-control"] == "no-store"
        cookie = result.headers["set-cookie"].lower()
        assert "max-age=0" in cookie and "httponly" in cookie and "samesite=strict" in cookie
        assert owner.get("/api/v1/auth/me").status_code == 401
        assert sibling.get("/api/v1/auth/me").status_code == 401
        assert peer.get("/api/v1/auth/me").status_code == 200
        assert private_state(app) == before
        assert {path.name: path.read_bytes() for path in (app.state.settings.data_dir / "documents").glob("*.enc")} == original
        with store.session() as session:
            assert not session.scalars(select(LoginSession).where(LoginSession.user_id == uid)).all()
            assert check_password(NEW, session.get(User, uid).password_hash)
            assert not check_password(NEW.strip(), session.get(User, uid).password_hash)
            audits_after = {row.id: tuple(row) for row in session.execute(select(Audit.__table__))}
            assert all(audits_after[key] == value for key, value in audits_before.items())
            added = session.scalars(select(Audit).where(Audit.id.not_in(audits_before))).all()
            assert [(row.actor_id, row.action, row.object_id, row.matter_id) for row in added] == [
                (uid, "password_changed", uid, None)]
        auth_after = auth_state(app)
        assert [row for row in auth_before["users"] if row[0] != uid] == [row for row in auth_after["users"] if row[0] != uid]
        # The only permitted user column change is the password hash.
        with store.session() as session:
            columns = list(User.__table__.columns.keys())
        assert {name: value for name, value in zip(columns, next(row for row in auth_before["users"] if row[0] == uid)) if name != "password_hash"} == {
            name: value for name, value in zip(columns, next(row for row in auth_after["users"] if row[0] == uid)) if name != "password_hash"}
        assert owner.post("/api/v1/auth/login", json={"username": "demo", "password": OLD}).status_code == 401
        assert owner.post("/api/v1/auth/login", json={"username": "demo", "password": NEW}).status_code == 200
        bootstrap(store, SimpleNamespace(demo_mode=False, bootstrap_username="demo", bootstrap_password=OLD))
        with store.session() as session:
            assert check_password(NEW, session.get(User, uid).password_hash)
    finally:
        sibling.close()
        peer.close()


@pytest.mark.parametrize("changes,status", [
    ({"current_password": "wrong-synthetic-password"}, 400),
    ({"confirm_password": "another-long-password"}, 400),
    ({"new_password": "short", "confirm_password": "short"}, 422),
    ({"new_password": " " * 16, "confirm_password": " " * 16}, 400),
    ({"new_password": "x" * 201}, 422),
    ({"current_password": "bad\npassword"}, 422),
    ({"current_password": 123456}, 422),
    ({"current_password": None}, 422),
    ({"user_id": "another-account"}, 422),
])
def test_invalid_change_retains_hash_and_sessions_without_secret_echo(account, changes, status):
    app, client, _ = account
    before = auth_state(app)
    result = client.post(PATH, json=body(**changes))
    assert result.status_code == status
    assert auth_state(app) == before
    assert OLD not in result.text and NEW not in result.text and "bad\\npassword" not in result.text
    assert client.get("/api/v1/auth/me").status_code == 200


def test_same_password_denied_and_secret_model_is_masked(account):
    app, client, _ = account
    first = client.post(PATH, json=body())
    assert first.status_code == 200
    login_result = client.post("/api/v1/auth/login", json={"username": "demo", "password": NEW})
    client.headers["X-CSRF-Token"] = login_result.json()["csrf_token"]
    before = auth_state(app)
    result = client.post(PATH, json=body(current_password=NEW))
    assert result.status_code == 400
    assert auth_state(app) == before
    model = PasswordChange(**body())
    assert OLD not in repr(model) and NEW not in model.model_dump_json()


def test_auth_origin_and_csrf_required(account):
    app, client, _ = account
    before = auth_state(app)
    assert client.post(PATH, json=body(), headers={"Origin": "https://attacker.invalid"}).status_code == 403
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post(PATH, json=body()).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    client.cookies.clear()
    assert client.post(PATH, json=body()).status_code == 401
    assert auth_state(app) == before


def test_current_password_attempt_limit_is_per_account_and_expires(account):
    app, client, _ = account
    before = auth_state(app)
    for _ in range(5):
        assert client.post(PATH, json=body(current_password="wrong")).status_code == 400
    assert client.post(PATH, json=body()).status_code == 429
    assert auth_state(app) == before
    with app.state.store.session() as session:
        session.add(User(username="unthrottled-peer", name="Synthetic", firm_id="demo-firm", role="lawyer",
                         password_hash=hash_password("synthetic-peer-password")))
        session.commit()
    peer = login(app, "unthrottled-peer", "synthetic-peer-password")
    try:
        assert peer.post(PATH, json=body(current_password="synthetic-peer-password")).status_code == 200
    finally:
        peer.close()
    with app.state.store.session() as session:
        old = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
        for row in session.scalars(select(Audit).where(Audit.action == "password_change_failed")):
            row.created_at = old
        session.commit()
    assert client.post(PATH, json=body()).status_code == 200


def test_transaction_failure_rolls_back_hash_and_revocations_without_driver_details(account):
    app, client, _ = account
    before = auth_state(app)
    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit"):
            raise SQLAlchemyError("synthetic-sensitive-driver-details")
    event.listen(app.state.store.engine, "before_cursor_execute", fail)
    try:
        response = client.post(PATH, json=body())
    finally:
        event.remove(app.state.store.engine, "before_cursor_execute", fail)
    assert response.status_code == 503
    assert "synthetic-sensitive-driver-details" not in response.text
    assert auth_state(app) == before
    assert client.get("/api/v1/auth/me").status_code == 200


def test_login_cannot_mint_old_password_session_after_waiting_for_change(account, monkeypatch):
    import app.main as main
    app, client, _ = account
    guard = main.hold_firm_guard
    def change_before_lock(request, firm_id):
        with app.state.store.session() as session:
            user = session.scalar(select(User).where(User.username == "demo"))
            user.password_hash = hash_password(NEW)
            session.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
            session.commit()
        guard(request, firm_id)
    monkeypatch.setattr(main, "hold_firm_guard", change_before_lock)
    result = client.post("/api/v1/auth/login", json={"username": "demo", "password": OLD})
    assert result.status_code == 401
    with app.state.store.session() as session:
        assert not session.scalars(select(LoginSession)).all()


def test_account_without_content_permissions_can_change_only_itself(account):
    app, _, _ = account
    with app.state.store.session() as session:
        session.add(User(username="no-content", name="Synthetic", firm_id="other-firm", role="none",
                         password_hash=hash_password("synthetic-old-password")))
        session.commit()
        original = session.scalar(select(User).where(User.username == "demo")).password_hash
    peer = login(app, "no-content", "synthetic-old-password")
    try:
        assert peer.get("/api/v1/matters").status_code == 403
        assert peer.post(PATH, json=body(current_password="synthetic-old-password")).status_code == 200
        with app.state.store.session() as session:
            assert session.scalar(select(User).where(User.username == "demo")).password_hash == original
    finally:
        peer.close()


def test_password_change_uses_exclusive_guard_and_waiting_old_session_is_rechecked(account, monkeypatch):
    from contextlib import contextmanager

    import app.auth as auth
    app, client, _ = account
    original = app.state.firm_authorization.guard
    observed = []
    @contextmanager
    def tracked(firm_id, exclusive=False):
        observed.append(exclusive)
        with original(firm_id, exclusive=exclusive):
            yield
    monkeypatch.setattr(app.state.firm_authorization, "guard", tracked)
    assert client.post(PATH, json=body(current_password="wrong")).status_code == 400
    assert observed == [True]
    guard = auth.hold_firm_guard
    def revoke_before_lock(request, firm_id):
        with app.state.store.session() as session:
            session.execute(delete(LoginSession))
            session.commit()
        guard(request, firm_id)
    monkeypatch.setattr(auth, "hold_firm_guard", revoke_before_lock)
    assert client.get("/api/v1/auth/me").status_code == 401
