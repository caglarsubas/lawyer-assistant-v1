"""Offline administration tests use only a temporary synthetic database."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.auth import check_password, hash_password
from app.db import Audit, LoginSession, Membership, Record, Store, User

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "manage_users.py"
SPEC = importlib.util.spec_from_file_location("manage_users", SCRIPT)
admin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(admin)
PASSWORD = "synthetic-password-only-12345"


@pytest.fixture
def workspace(tmp_path):
    store = Store(SimpleNamespace(data_dir=tmp_path, demo_mode=True,
                                  encryption_key=Fernet.generate_key().decode(),
                                  database_url=f"sqlite:///{tmp_path / 'test.db'}"))
    with store.session() as session:
        for identity, firm, role, active in (
            ("admin-a", "firm-a", "admin", True), ("lawyer-a", "firm-a", "lawyer", True),
            ("inactive-a", "firm-a", "lawyer", False), ("admin-b", "firm-b", "admin", True),
        ):
            session.add(User(id=identity, username=identity, name=identity, firm_id=firm, role=role,
                             active=active, password_hash=hash_password(PASSWORD)))
        session.flush()
        operator = session.get(User, "admin-a")
        for matter, owner, members in (
            ("shared", operator, ["admin-a", "lawyer-a"]),
            ("admin-only", operator, ["admin-a"]),
            ("lawyer-only", session.get(User, "lawyer-a"), ["lawyer-a"]),
            ("foreign", session.get(User, "admin-b"), ["admin-b"]),
        ):
            store.add(session, "matter", owner, {"title": "synthetic private matter"}, record_id=matter)
            for user in members:
                session.add(Membership(matter_id=matter, user_id=user))
        session.commit()
    yield store
    store.engine.dispose()


def test_list_is_same_firm_minimal_metadata(workspace):
    result = admin.operate(workspace, "admin-a", "list")
    assert {item["id"] for item in result} == {"admin-a", "lawyer-a", "inactive-a"}
    assert all(set(item) == {"id", "name", "role", "active"} for item in result)
    assert "password" not in json.dumps(result) and "synthetic private matter" not in json.dumps(result)


@pytest.mark.parametrize("operator", ["lawyer-a", "inactive-a", "missing"])
def test_only_existing_active_admin_can_operate(workspace, operator):
    with pytest.raises(admin.AdministrationError):
        admin.operate(workspace, operator, "list")


def test_create_uses_operator_firm_and_hashes_password_without_granting_matters(workspace):
    result = admin.operate(workspace, "admin-a", "create", username="new-lawyer", name="Synthetic Lawyer",
                           password=PASSWORD)
    assert PASSWORD not in json.dumps(result)
    with workspace.session() as session:
        user = session.get(User, result["user"]["id"])
        assert user.firm_id == "firm-a" and user.role == "lawyer"
        assert check_password(PASSWORD, user.password_hash)
        assert session.scalar(select(Membership).where(Membership.user_id == user.id)) is None
        audit = session.scalar(select(Audit).where(Audit.action == "operator_user_created"))
        assert audit.actor_id == "admin-a" and audit.object_id == user.id


def test_create_never_resets_existing_credentials_or_cross_firm_accounts(workspace):
    with workspace.session() as session:
        original = session.get(User, "admin-b").password_hash
    with pytest.raises(admin.AdministrationError, match="already exists"):
        admin.operate(workspace, "admin-a", "create", username="admin-b", name="Replacement",
                      password="different-synthetic-password")
    with workspace.session() as session:
        user = session.get(User, "admin-b")
        assert user.password_hash == original and user.name == "admin-b"


@pytest.mark.parametrize("command", ["grant", "revoke"])
@pytest.mark.parametrize("matter", ["lawyer-only", "foreign", "missing"])
def test_admin_role_does_not_bypass_explicit_matter_membership(workspace, command, matter):
    with pytest.raises(admin.AdministrationError, match="already be a member"):
        admin.operate(workspace, "admin-a", command, user_id="lawyer-a", matter_id=matter)


@pytest.mark.parametrize("command", ["grant", "revoke", "deactivate"])
def test_cross_firm_user_mutations_are_denied(workspace, command):
    with pytest.raises(admin.AdministrationError):
        admin.operate(workspace, "admin-a", command, user_id="admin-b", matter_id="shared")


def test_explicit_grant_and_revoke_are_idempotent_and_audited(workspace):
    values = {"user_id": "lawyer-a", "matter_id": "admin-only"}
    assert admin.operate(workspace, "admin-a", "grant", **values)["changed"]
    assert not admin.operate(workspace, "admin-a", "grant", **values)["changed"]
    assert admin.operate(workspace, "admin-a", "revoke", **values)["changed"]
    assert not admin.operate(workspace, "admin-a", "revoke", **values)["changed"]
    with workspace.session() as session:
        rows = session.scalars(select(Audit).where(Audit.matter_id == "admin-only")).all()
        assert {row.action for row in rows} == {"operator_member_granted", "operator_member_revoked"}
        assert all(row.object_id == "lawyer-a" for row in rows)


def test_last_active_member_and_self_deactivation_are_protected(workspace):
    with pytest.raises(admin.AdministrationError, match="last active"):
        admin.operate(workspace, "admin-a", "revoke", user_id="admin-a", matter_id="admin-only")
    with pytest.raises(admin.AdministrationError, match="last active"):
        admin.operate(workspace, "admin-a", "deactivate", user_id="lawyer-a")
    with pytest.raises(admin.AdministrationError, match="Self-deactivation"):
        admin.operate(workspace, "admin-a", "deactivate", user_id="admin-a")
    with workspace.session() as session:
        assert session.get(User, "lawyer-a").active


def test_inactive_users_do_not_count_as_a_remaining_active_member(workspace):
    with workspace.session() as session:
        session.add(Membership(matter_id="admin-only", user_id="inactive-a"))
        session.commit()
    with pytest.raises(admin.AdministrationError, match="last active"):
        admin.operate(workspace, "admin-a", "revoke", user_id="admin-a", matter_id="admin-only")
    with pytest.raises(admin.AdministrationError, match="inactive"):
        admin.operate(workspace, "admin-a", "grant", user_id="inactive-a", matter_id="shared")


def test_deactivation_revokes_all_target_sessions_without_changing_password(workspace):
    result = admin.operate(workspace, "admin-a", "create", username="new-lawyer", name="Synthetic Lawyer",
                           password=PASSWORD)
    target_id = result["user"]["id"]
    admin.operate(workspace, "admin-a", "grant", user_id=target_id, matter_id="shared")
    with workspace.session() as session:
        old_hash = session.get(User, target_id).password_hash
        session.add(LoginSession(token_hash="synthetic-target-session", user_id=target_id,
                                 csrf="synthetic", expires_at="2099-01-01T00:00:00+00:00"))
        session.add(LoginSession(token_hash="synthetic-other-session", user_id="admin-a",
                                 csrf="synthetic", expires_at="2099-01-01T00:00:00+00:00"))
        session.commit()
    assert admin.operate(workspace, "admin-a", "deactivate", user_id=target_id)["sessions_revoked"]
    with workspace.session() as session:
        target = session.get(User, target_id)
        assert not target.active and target.password_hash == old_hash
        assert session.get(LoginSession, "synthetic-target-session") is None
        assert session.get(LoginSession, "synthetic-other-session") is not None


def test_archived_matter_last_active_member_is_still_protected(workspace):
    with workspace.session() as session:
        session.get(Record, "lawyer-only").kind = "archived_matter"
        session.commit()
    with pytest.raises(admin.AdministrationError, match="last active member"):
        admin.operate(workspace, "admin-a", "deactivate", user_id="lawyer-a")


def test_archived_matter_keeps_an_active_admin_who_can_restore_it(workspace):
    with workspace.session() as session:
        session.get(User, "lawyer-a").role = "admin"
        session.get(Record, "lawyer-only").kind = "archived_matter"
        session.add(Membership(matter_id="lawyer-only", user_id="inactive-a"))
        session.get(User, "inactive-a").active = True
        session.commit()
    with pytest.raises(admin.AdministrationError, match="administrator member"):
        admin.operate(workspace, "admin-a", "deactivate", user_id="lawyer-a")
    with workspace.session() as session:
        assert session.get(User, "lawyer-a").active


def test_curator_can_be_created_without_becoming_a_firm_admin(workspace):
    result = admin.operate(workspace, "admin-a", "create", username="new-curator", name="Synthetic Curator",
                           role="curator", password=PASSWORD)
    assert result["user"]["role"] == "curator"
    with pytest.raises(admin.AdministrationError):
        admin.operate(workspace, result["user"]["id"], "list")


def test_help_does_not_load_settings_or_open_storage(monkeypatch, capsys):
    from app import config

    monkeypatch.setattr(config, "load_settings", lambda: pytest.fail("Help must not read configuration"))
    with pytest.raises(SystemExit) as error:
        admin.main(["--help"])
    assert error.value.code == 0
    assert "--password" not in capsys.readouterr().out


def test_password_cannot_be_supplied_in_argv_or_echoed_by_argument_errors(capsys):
    with pytest.raises(SystemExit):
        admin.arguments(["--operator", "admin-a", "create", "--username", "fixture", "--name", "Fixture",
                         "--password", "must-not-be-an-option"])
    assert "must-not-be-an-option" not in capsys.readouterr().err


def test_create_refuses_nonterminal_password_input_before_storage(monkeypatch):
    from app import config

    monkeypatch.setattr(admin.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(config, "load_settings", lambda: pytest.fail("No storage access before prompt safety"))
    assert admin.main(["--operator", "admin-a", "create", "--username", "fixture", "--name", "Fixture"]) == 2
