#!/usr/bin/env python3
"""Offline firm administration. Passwords are read only from a hidden terminal prompt."""

import argparse
import getpass
import json
import sys
import warnings
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.auth import hash_password
from app.content_scope import (
    configuration,
    has_case_scope,
    scoped_records,
    scoped_users,
)
from app.db import Audit, CaseResponsibility, LoginSession, Membership, Record, User
from app.firm_rbac import (
    FirmAuthorization,
    initialize_firm,
    permissions_for,
)


class AdministrationError(Exception):
    """Safe operator-facing error without credentials or matter contents."""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unrecognized values, which might be an
        # accidentally supplied password. Never repeat command-line input.
        self.exit(2, "Invalid administration arguments; use --help.\n")


def user_summary(user):
    return {"id": user.id, "name": user.name, "role": user.role, "active": user.active}


def operate(store, operator_id, command, *, user_id=None, matter_id=None,
            username=None, name=None, role="lawyer", password=None):
    if command not in {"list", "create", "grant", "revoke", "deactivate"}:
        raise AdministrationError("Unsupported operation")
    with store.session() as lookup:
        identity = lookup.get(User, operator_id)
        if not identity or not identity.active:
            raise AdministrationError("An existing active administrator ID is required")
        firm_id = identity.firm_id
    with FirmAuthorization(store.engine).guard(firm_id, exclusive=True), store.session() as session, session.begin():
        operator = session.get(User, operator_id)
        if not operator or not operator.active or "firm.manage" not in permissions_for(session, operator):
            raise AdministrationError("An existing active administrator ID is required")
        # One stable lock order serializes this CLI's firm-level access changes.
        users = session.scalars(select(User).where(User.firm_id == operator.firm_id)
                                .order_by(User.id).with_for_update()
                                .execution_options(populate_existing=True)).all()
        operator = next((user for user in users if user.id == operator_id), None)
        if not operator or not operator.active or "firm.manage" not in permissions_for(session, operator):
            raise AdministrationError("Administrator access changed; operation denied")

        def audit(action, target_id, matter=None):
            session.add(Audit(actor_id=operator.id, action=action, object_id=target_id, matter_id=matter))

        if command == "list":
            audit("operator_users_listed", operator.id)
            return [user_summary(user) for user in users]
        if command == "create":
            if (not isinstance(username, str) or not 1 <= len(username) <= 100
                    or username != username.strip() or any(c.isspace() or ord(c) < 32 for c in username)
                    or not isinstance(name, str) or not name.strip() or len(name) > 100
                    or any(ord(c) < 32 for c in name) or role not in {"admin", "lawyer", "curator"}):
                raise AdministrationError("Supply a valid username, display name and role")
            if not isinstance(password, str) or not 16 <= len(password) <= 200:
                raise AdministrationError("A new password must contain 16–200 characters")
            if session.scalar(select(User.id).where(User.username == username)):
                raise AdministrationError("Username already exists; existing credentials were not changed")
            target = User(username=username, name=name, firm_id=operator.firm_id, role=role,
                          active=True, password_hash=hash_password(password))
            session.add(target)
            session.flush()
            initialize_firm(session, operator.firm_id)
            audit("operator_user_created", target.id)
            return {"changed": True, "user": user_summary(target)}

        target = next((user for user in users if user.id == user_id), None)
        if target is None:
            raise AdministrationError("Target user is not in the operator's firm")

        def active_others(matter, admin_only=False):
            return sum(person.id != target.id and (not admin_only or person.role == "admin")
                       for person in scoped_users(session, matter, operator.firm_id))

        if command in {"grant", "revoke"}:
            matter = session.scalar(select(Record).where(Record.id == matter_id, Record.kind == "matter",
                                                         Record.firm_id == operator.firm_id).with_for_update())
            if matter is None or not has_case_scope(session, matter.id, operator):
                raise AdministrationError("Operator must already be a member of the same-firm matter")
            membership = session.get(Membership, (matter.id, target.id))
            if command == "grant":
                if not target.active:
                    raise AdministrationError("Cannot grant matter access to an inactive user")
                if membership is not None:
                    return {"changed": False}
                session.add(Membership(matter_id=matter.id, user_id=target.id))
                audit("operator_member_granted", target.id, matter.id)
            else:
                if membership is None:
                    return {"changed": False}
                if target.active and not active_others(matter.id):
                    raise AdministrationError("Cannot remove the last active matter member")
                session.delete(membership)
                session.execute(delete(CaseResponsibility).where(CaseResponsibility.matter_id == matter.id,
                                                                 CaseResponsibility.user_id == target.id))
                audit("operator_member_revoked", target.id, matter.id)
            configuration(session, matter).revision += 1
            session.execute(delete(LoginSession).where(LoginSession.user_id == target.id))
            return {"changed": True}

        if target.id == operator.id:
            raise AdministrationError("Self-deactivation is prohibited")
        if target.active:
            matters = session.scalars(scoped_records(target, ("matter", "archived_matter"))
                                     .order_by(Record.id).with_for_update(of=Record)).all()
            if any(not active_others(matter.id) for matter in matters):
                raise AdministrationError("Cannot deactivate the last active member of a matter")
            if target.role == "admin" and any(matter.kind == "archived_matter"
                                              and not active_others(matter.id, admin_only=True)
                                              for matter in matters):
                raise AdministrationError("Cannot deactivate the last active administrator member of an archived matter")
        target.active = False
        session.execute(delete(LoginSession).where(LoginSession.user_id == target.id))
        audit("operator_user_deactivated", target.id)
        return {"changed": True, "user": user_summary(target), "sessions_revoked": True}


def arguments(argv=None):
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument("--operator", required=True, help="Existing active administrator ID")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List minimal user metadata in the operator's firm")
    create = commands.add_parser("create", help="Create a new account; never reset an existing account")
    create.add_argument("--username", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--role", choices=["lawyer", "curator", "admin"], default="lawyer")
    for command in ("grant", "revoke"):
        sub = commands.add_parser(command, help=f"{command.title()} one explicit matter membership")
        sub.add_argument("--user", dest="user_id", required=True)
        sub.add_argument("--matter", dest="matter_id", required=True)
    deactivate = commands.add_parser("deactivate", help="Deactivate an account and revoke its sessions")
    deactivate.add_argument("--user", dest="user_id", required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = arguments(argv)  # --help exits before configuration or storage is read.
    store = None
    try:
        password = None
        if args.command == "create":
            if not sys.stdin.isatty() or not sys.stderr.isatty():
                raise AdministrationError("Account creation requires a terminal with hidden password input")
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                password = getpass.getpass("New user's password: ")
                if password != getpass.getpass("Confirm new user's password: "):
                    raise AdministrationError("Passwords did not match; nothing changed")
        from app.config import load_settings
        settings = load_settings()
        database_url = settings.database_url
        if database_url == "sqlite:///./.data/workspace.db":
            database_url = f"sqlite:///{settings.data_dir / 'workspace.db'}"
        url = make_url(database_url)
        if url.get_backend_name() == "sqlite":
            if not settings.demo_mode or not url.database or not Path(url.database).is_file():
                raise AdministrationError("SQLite administration requires an existing explicit demo database")
        elif url.get_backend_name() != "postgresql":
            raise AdministrationError("Configured production database must be PostgreSQL")
        # Existing schema only: no bootstrap, create_all, encryption-key file or credential reset.
        engine = create_engine(database_url, pool_pre_ping=True)
        store = SimpleNamespace(engine=engine, session=sessionmaker(engine, expire_on_commit=False))
        values = vars(args).copy()
        operator = values.pop("operator")
        command = values.pop("command")
        result = operate(store, operator, command, password=password, **values)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except AdministrationError as error:
        print(str(error), file=sys.stderr)
    except (Exception, KeyboardInterrupt):
        # Database exceptions can contain SQL parameters; never print their payloads.
        print("Administration failed; no credentials are printed. Check the local configuration and access.",
              file=sys.stderr)
    finally:
        if store is not None:
            store.engine.dispose()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
