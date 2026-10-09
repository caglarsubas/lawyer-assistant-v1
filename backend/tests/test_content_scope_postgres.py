"""Real PostgreSQL firm locks, conflicting scope edits and publication admission."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_firm_admin import PASSWORD, create_employee, login
from test_portfolio import customer
from test_portfolio import workspace as create_workspace
from test_research_jobs_postgres import postgres_database as database_fixture
from test_research_jobs_postgres import workspace as workspace_fixture
from test_snapshot_set_postgres import observe_identity_lock, wait_until_blocked

from app.db import CustomerAssignment, Membership, Record, User
from app.research_jobs import checkpoint


@pytest.fixture
def postgres_database():
    yield from database_fixture.__wrapped__()


@pytest.fixture
def workspace(postgres_database, tmp_path):
    yield from workspace_fixture.__wrapped__(postgres_database, tmp_path)


def test_concurrent_scope_edits_preserve_one_revision_and_independent_grant(workspace):
    app, client, matter = workspace
    peer = create_employee(client)
    a = customer(client)
    endpoint = '/api/v1/firm-admin/customers/' + a['id'] + '/assignments'
    before = client.get(endpoint).json()
    barrier = Barrier(2)

    def edit(scope):
        barrier.wait(timeout=5)
        return client.put(endpoint, json={'revision': before['revision'], 'assignments': [
            *before['assignments'], {'user_id': peer['id'], 'scope': scope},
        ]})

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(edit, value) for value in ('details', 'all_cases')]
        results = [future.result(timeout=10) for future in futures]
    assert sorted(result.status_code for result in results) == [200, 409]
    after = client.get(endpoint).json()
    assert after['revision'] == before['revision'] + 1
    with app.state.store.session() as session:
        assert session.get(CustomerAssignment, (a['id'], peer['id'])).scope in {'details', 'all_cases'}
        assert session.get(Membership, (matter, client.get('/api/v1/auth/me').json()['user']['id']))
        changes = list(session.scalars(select(Record).where(Record.kind == 'access_change')))
        assert sum(app.state.store.decode(row)['action'] == 'client_assignments_changed' for row in changes) == 1


def test_scope_revocation_waits_for_admitted_read_then_denies_new_reads_and_checkpoints(workspace, monkeypatch):
    app, client, _ = workspace
    peer = create_employee(client)
    a = customer(client)
    case = create_workspace(client, customer_ids=[a['id']])
    endpoint = '/api/v1/firm-admin/customers/' + a['id'] + '/assignments'
    before = client.get(endpoint).json()
    granted = client.put(endpoint, json={'revision': before['revision'], 'assignments': [
        *before['assignments'], {'user_id': peer['id'], 'scope': 'all_cases'},
    ]})
    assert granted.status_code == 200
    other = TestClient(app)
    try:
        login(other, 'peer', PASSWORD)
        assert other.get('/api/v1/workspaces/' + case['id']).status_code == 200
        with app.state.store.session() as session:
            owner = session.get(User, peer['id'])
            run = app.state.store.add(session, 'research', owner, {'status': 'running', 'phase': 'model'}, matter_id=case['id'])
            session.commit()
            run_id = run.id
        from app import portfolio
        entered, release = Event(), Event()
        original = portfolio.workspace_view

        def slow_response(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[3].id == case['id'] and not entered.is_set():
                entered.set()
                assert release.wait(10)
            return result

        monkeypatch.setattr(portfolio, 'workspace_view', slow_response)
        with ThreadPoolExecutor(2) as pool:
            active_read = pool.submit(other.get, '/api/v1/workspaces/' + case['id'])
            assert entered.wait(5)
            with observe_identity_lock(app.state.store.engine, statement_fragment='SELECT pg_advisory_lock(') as observed:
                future = pool.submit(client.put, endpoint, json={
                    'revision': granted.json()['revision'], 'assignments': before['assignments'],
                })
                try:
                    assert observed[0].wait(5)
                    assert wait_until_blocked(app.state.store.engine, observed[1][-1])
                    assert not future.done()
                finally:
                    release.set()
                assert active_read.result(timeout=10).status_code == 200
                response = future.result(timeout=10)
        assert response.status_code == 200, response.text
        assert other.get('/api/v1/auth/me').status_code == 401
        login(other, 'peer', PASSWORD)
        assert other.get('/api/v1/workspaces/' + case['id']).status_code == 404
        with pytest.raises(HTTPException):
            checkpoint(app, run_id, 'publishing')
        with app.state.store.session() as session:
            state = app.state.store.decode(session.get(Record, run_id))
            assert state['status'] == 'cancelling' and state['stop_reason'] == 'access_revoked'
    finally:
        other.close()
