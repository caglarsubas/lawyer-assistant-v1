from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import bootstrap, check_password, create_session, hash_password
from app.db import Base, LoginSession, User, digest


@pytest.fixture
def store():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield SimpleNamespace(session=sessionmaker(engine, expire_on_commit=False))
    engine.dispose()


def settings(password):
    return SimpleNamespace(demo_mode=False, bootstrap_username="admin", bootstrap_password=password)


@pytest.mark.parametrize("password", ["admin", "", "a-different-long-password"])
@pytest.mark.parametrize("active", [True, False])
def test_existing_account_and_sessions_survive_bootstrap_config_changes(store, password, active):
    original_hash = hash_password("saved-account-password")
    with store.session() as session:
        user = User(username="admin", name="Existing user", firm_id="existing-firm",
                    role="lawyer", active=active, password_hash=original_hash)
        session.add(user)
        session.commit()
        user_id = user.id
        token, csrf = create_session(session, user, 8)
        expires_at = session.get(LoginSession, digest(token)).expires_at

    bootstrap(store, settings(password))

    with store.session() as session:
        user = session.get(User, user_id)
        assert user.password_hash == original_hash
        assert (user.name, user.firm_id, user.role, user.active) == (
            "Existing user", "existing-firm", "lawyer", active,
        )
        login = session.get(LoginSession, digest(token))
        assert (login.user_id, login.csrf, login.expires_at) == (user_id, csrf, expires_at)
        assert len(session.scalars(select(User)).all()) == 1


@pytest.mark.parametrize("password", ["", "admin", "x" * 15])
def test_new_deployment_still_rejects_missing_or_short_password(store, password):
    with pytest.raises(ValueError):
        bootstrap(store, settings(password))
    with store.session() as session:
        assert session.scalar(select(User)) is None


def test_new_account_is_created_with_a_hashed_valid_password(store):
    password = "synthetic-new-admin-password"
    bootstrap(store, settings(password))
    with store.session() as session:
        user = session.scalar(select(User).where(User.username == "admin"))
        assert check_password(password, user.password_hash)
        assert user.password_hash != password
        assert (user.firm_id, user.role, user.active) == ("org-lawyer", "admin", True)
