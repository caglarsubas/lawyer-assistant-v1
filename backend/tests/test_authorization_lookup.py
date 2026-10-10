"""Fresh authorization joins reduce SQL work without caching a grant or bypassing scope."""

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, delete, event, update
from sqlalchemy.orm import Session

from app.db import Base, Employee, EmployeeRole, FirmRole, User
from app.firm_rbac import permissions_for, require_permission


@pytest.fixture
def authority():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(id='synthetic-user', username='synthetic', name='Synthetic', firm_id='synthetic-firm',
                    role='admin', password_hash='not-a-login-credential', active=True)
        session.add(user)
        session.commit()
        counts = []

        def count(_conn, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().upper().startswith('SELECT'):
                counts.append(statement)
        event.listen(engine, 'before_cursor_execute', count)
        yield session, user, counts
    engine.dispose()


def managed(session, user, permissions=None):
    session.add(Employee(user_id=user.id, firm_id=user.firm_id))
    if permissions is not None:
        role = FirmRole(id='synthetic-role', firm_id=user.firm_id, name='Synthetic', permissions=json.dumps(permissions))
        session.add(role)
        session.add(EmployeeRole(user_id=user.id, role_id=role.id))
    session.commit()


def test_one_statement_per_call_refreshes_roles_and_user_without_caching(authority):
    session, user, counts = authority
    managed(session, user, ['matter.read', 'system.read'])
    # Pin a caller identity before the counter; expire_on_commit's lazy attribute
    # access is unrelated to the authorization statement itself.
    caller = SimpleNamespace(id=user.id, firm_id=user.firm_id)
    counts.clear()
    assert require_permission(session, caller, 'matter.read').id == user.id
    assert len(counts) == 1
    session.execute(update(FirmRole).values(permissions='["system.read"]'))
    session.commit()
    counts.clear()
    with pytest.raises(HTTPException) as error:
        require_permission(session, caller, 'matter.read')
    assert error.value.status_code == 403 and len(counts) == 1
    session.execute(update(User).values(active=False).execution_options(synchronize_session=False))
    session.commit()
    counts.clear()
    with pytest.raises(HTTPException) as error:
        require_permission(session, caller, 'system.read')
    assert error.value.status_code == 401 and len(counts) == 1


@pytest.mark.parametrize('case', ['unmanaged', 'empty_managed', 'multiple_roles', 'missing_role',
                                'foreign_role', 'malformed', 'unknown_permission', 'employee_firm'])
def test_join_preserves_exact_legacy_and_managed_permission_semantics(authority, case):
    session, user, _ = authority
    if case != 'unmanaged':
        managed(session, user, ['matter.read'] if case != 'empty_managed' else None)
    if case == 'multiple_roles':
        session.add(FirmRole(id='second', firm_id=user.firm_id, name='Second', permissions='["system.read"]'))
        session.add(EmployeeRole(user_id=user.id, role_id='second'))
    elif case == 'missing_role':
        session.execute(delete(FirmRole))
    elif case == 'foreign_role':
        session.execute(update(FirmRole).values(firm_id='other-firm'))
    elif case == 'malformed':
        session.execute(update(FirmRole).values(permissions='{invalid json'))
    elif case == 'unknown_permission':
        session.execute(update(FirmRole).values(permissions='["invented_permission"]'))
    elif case == 'employee_firm':
        session.execute(update(Employee).values(firm_id='other-firm'))
    session.commit()
    expected = permissions_for(session, user)
    for permission in ('matter.read', 'system.read', 'firm.manage'):
        if permission in expected:
            assert require_permission(session, user, permission).id == user.id
        else:
            with pytest.raises(HTTPException) as error:
                require_permission(session, user, permission)
            assert error.value.status_code == 403


@pytest.mark.parametrize('change', ['inactive', 'deleted', 'moved_firm'])
def test_retained_caller_does_not_override_current_account_state(authority, change):
    session, user, counts = authority
    caller = SimpleNamespace(id=user.id, firm_id=user.firm_id)
    if change == 'deleted':
        session.execute(delete(User).execution_options(synchronize_session=False))
    else:
        session.execute(update(User).values(**({'active': False} if change == 'inactive' else {'firm_id': 'other-firm'}))
                        .execution_options(synchronize_session=False))
    session.commit()
    counts.clear()
    with pytest.raises(HTTPException) as error:
        require_permission(session, caller, 'matter.read')
    assert error.value.status_code == 401 and len(counts) == 1


def test_same_orm_identity_cannot_hide_a_firm_change_during_refresh(authority):
    session, user, _ = authority
    _ = user.firm_id
    session.execute(update(User).values(firm_id='other-firm').execution_options(synchronize_session=False))
    with pytest.raises(HTTPException) as error:
        require_permission(session, user, 'matter.read')
    assert error.value.status_code == 401
