"""One fresh SQL check retains independent action/scope grants and live revocation."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, update
from test_authorization_lookup import authority as authority_fixture
from test_authorization_lookup import managed

from app.auth import require_matter
from app.db import (
    CustomerAssignment,
    Employee,
    EmployeeRole,
    FirmRole,
    Membership,
    Record,
    User,
    WorkspaceCustomerLink,
)

authority = authority_fixture


@pytest.fixture
def matter(authority):
    session, user, counts = authority
    row = Record(id='synthetic-case', kind='matter', firm_id=user.firm_id, owner_id=user.id,
                 payload='opaque-not-decoded', created_at='2026-10-10T00:00:00+00:00')
    session.add(row)
    session.add(Membership(matter_id=row.id, user_id=user.id))
    session.commit()
    caller = SimpleNamespace(id=user.id, firm_id=user.firm_id)
    ident = row.id
    counts.clear()
    return session, caller, ident, counts


def denied(session, caller, ident, counts, status):
    counts.clear()
    with pytest.raises(HTTPException) as error:
        require_matter(session, ident, caller)
    assert error.value.status_code == status
    assert len(counts) == 1
    return error.value.detail


def client_grant(session, caller, ident, *, scope='all_cases'):
    session.add(Record(id='synthetic-client', kind='customer', firm_id=caller.firm_id,
                       owner_id=caller.id, payload='opaque'))
    session.add(WorkspaceCustomerLink(matter_id=ident, customer_id='synthetic-client', firm_id=caller.firm_id))
    session.add(CustomerAssignment(customer_id='synthetic-client', user_id=caller.id, firm_id=caller.firm_id,
                                   scope=scope, assigned_by=caller.id))
    session.flush()


def test_one_statement_per_call_refreshes_matter_and_direct_grant(matter):
    session, caller, ident, counts = matter
    first = require_matter(session, ident, caller)
    assert len(counts) == 1
    session.execute(update(Record).where(Record.id == ident).values(revision=2)
                    .execution_options(synchronize_session=False))
    counts.clear()
    assert require_matter(session, ident, caller) is first
    assert first.revision == 2 and len(counts) == 1
    # No expiration/commit/new session: a retained ORM identity cannot retain access.
    session.execute(delete(Membership))
    denied(session, caller, ident, counts, 404)


@pytest.mark.parametrize('change', ['scope', 'assignment', 'link', 'client_kind', 'client_firm',
                                  'assignment_firm', 'link_firm'])
def test_client_origin_is_fresh_and_independently_revocable(matter, change):
    session, caller, ident, counts = matter
    session.execute(delete(Membership))
    client_grant(session, caller, ident)
    counts.clear()
    assert require_matter(session, ident, caller).id == ident and len(counts) == 1
    if change == 'scope':
        session.execute(update(CustomerAssignment).values(scope='details'))
    elif change == 'assignment':
        session.execute(delete(CustomerAssignment))
    elif change == 'link':
        session.execute(delete(WorkspaceCustomerLink))
    elif change in {'client_kind', 'client_firm'}:
        session.execute(update(Record).where(Record.id == 'synthetic-client').values(
            **({'kind': 'matter'} if change == 'client_kind' else {'firm_id': 'foreign'})))
    else:
        model = CustomerAssignment if change == 'assignment_firm' else WorkspaceCustomerLink
        session.execute(update(model).values(firm_id='foreign'))
    denied(session, caller, ident, counts, 404)


def test_direct_and_client_grants_remain_independent(matter):
    session, caller, ident, counts = matter
    client_grant(session, caller, ident)
    session.execute(delete(Membership))
    assert require_matter(session, ident, caller).id == ident
    session.add(Membership(matter_id=ident, user_id=caller.id))
    session.execute(delete(CustomerAssignment))
    counts.clear()
    assert require_matter(session, ident, caller).id == ident and len(counts) == 1
    session.execute(delete(Membership))
    denied(session, caller, ident, counts, 404)


@pytest.mark.parametrize('change', ['inactive', 'deleted', 'moved_firm'])
def test_retained_caller_cannot_override_current_account_state(matter, change):
    session, caller, ident, counts = matter
    if change == 'deleted':
        session.execute(delete(User).execution_options(synchronize_session=False))
    else:
        session.execute(update(User).values(
            **({'active': False} if change == 'inactive' else {'firm_id': 'foreign'}))
            .execution_options(synchronize_session=False))
    denied(session, caller, ident, counts, 401)


def test_same_orm_user_identity_cannot_hide_firm_change_during_refresh(matter):
    session, caller, ident, counts = matter
    user = session.get(User, caller.id)
    assert user.firm_id == caller.firm_id
    session.execute(update(User).values(firm_id='foreign').execution_options(synchronize_session=False))
    denied(session, user, ident, counts, 401)


@pytest.mark.parametrize('change', ['missing', 'archived', 'wrong_kind', 'foreign', 'no_scope'])
def test_missing_and_unauthorized_matters_remain_indistinguishable(matter, change):
    session, caller, ident, counts = matter
    if change == 'missing':
        session.execute(delete(Record).where(Record.id == ident).execution_options(synchronize_session=False))
    elif change == 'no_scope':
        session.execute(delete(Membership))
    else:
        session.execute(update(Record).where(Record.id == ident).values(
            **({'firm_id': 'foreign'} if change == 'foreign' else
               {'kind': 'archived_matter' if change == 'archived' else 'document'}))
            .execution_options(synchronize_session=False))
    assert denied(session, caller, ident, counts, 404) == 'Dosya bulunamadı'


@pytest.mark.parametrize('change', ['removed', 'missing', 'malformed', 'unknown', 'foreign', 'employee_firm', 'empty'])
def test_current_role_rows_fail_closed_without_overriding_content_scope(matter, change):
    session, caller, ident, counts = matter
    user = session.get(User, caller.id)
    managed(session, user, None if change == 'empty' else ['matter.read'])
    if change != 'empty':
        assert require_matter(session, ident, caller).id == ident
    if change == 'employee_firm':
        session.execute(update(Employee).values(firm_id='foreign'))
    elif change == 'foreign':
        session.execute(update(FirmRole).values(firm_id='foreign'))
    elif change == 'missing':
        session.execute(delete(FirmRole))
    elif change != 'empty':
        session.execute(update(FirmRole).values(permissions={
            'removed': '["system.read"]', 'malformed': '{invalid', 'unknown': '["invented"]',
        }[change]))
    denied(session, caller, ident, counts, 403)
    session.execute(delete(Membership))
    denied(session, caller, ident, counts, 404)


def test_role_permission_without_content_grant_never_admits_a_matter(matter):
    session, caller, ident, counts = matter
    assert require_matter(session, ident, caller).id == ident  # Unmanaged legacy admin.
    session.execute(delete(Membership))
    client_grant(session, caller, ident, scope='details')
    denied(session, caller, ident, counts, 404)


def test_multiple_role_union_cannot_hide_one_malformed_role(matter):
    session, caller, ident, counts = matter
    managed(session, session.get(User, caller.id), ['system.read'])
    session.add(FirmRole(id='second', firm_id=caller.firm_id, name='Second', permissions='["matter.read"]'))
    session.add(EmployeeRole(user_id=caller.id, role_id='second'))
    session.flush()
    counts.clear()
    assert require_matter(session, ident, caller).id == ident and len(counts) == 1
    session.execute(update(FirmRole).where(FirmRole.id == 'synthetic-role').values(permissions='{invalid'))
    denied(session, caller, ident, counts, 403)
