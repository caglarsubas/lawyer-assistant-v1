"""Explicit scope, confidentiality and revocation using synthetic firm accounts."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from test_firm_admin import PASSWORD, create_employee, login
from test_firm_admin import firm as firm_fixture
from test_portfolio import customer, workspace

from app.content_scope import initialize_scope
from app.db import CaseResponsibility, CustomerAssignment, Membership, Record, ScopeMigration, User
from app.research_jobs import checkpoint


@pytest.fixture
def firm(tmp_path):
    yield from firm_fixture.__wrapped__(tmp_path)


def assignments(client, client_id, values):
    path = '/api/v1/firm-admin/customers/' + client_id + '/assignments'
    state = client.get(path)
    assert state.status_code == 200, state.text
    result = client.put(path, json={'revision': state.json()['revision'], 'assignments': values})
    assert result.status_code == 200, result.text
    return result.json()


def team(client, case_id, values):
    path = '/api/v1/firm-admin/workspaces/' + case_id + '/team'
    state = client.get(path)
    assert state.status_code == 200, state.text
    result = client.put(path, json={'revision': state.json()['revision'], 'members': values})
    assert result.status_code == 200, result.text
    # A changed grant invalidates the affected person's session, including the editor.
    login(client)
    return result.json()


def case_ids(client):
    response = client.get('/api/v1/workspaces')
    assert response.status_code == 200, response.text
    return {item['id'] for item in response.json()}


def test_details_only_never_grants_current_or_future_cases(firm):
    _, client = firm
    admin = client.get('/api/v1/auth/me').json()['user']['id']
    peer = create_employee(client)
    a = customer(client)
    case = workspace(client, customer_ids=[a['id']])
    assignments(client, a['id'], [{'user_id': admin, 'scope': 'details'}, {'user_id': peer['id'], 'scope': 'details'}])
    login(client)
    future = workspace(client, customer_ids=[a['id']])
    login(client, 'peer', PASSWORD)
    assert client.get('/api/v1/customers').json()[0]['workspace_count'] == 0
    assert case_ids(client) == set()
    for ident in (case['id'], future['id']):
        assert client.get('/api/v1/matters/' + ident).status_code == 404
        assert client.get('/api/v1/workspaces/' + ident + '/access').status_code == 404


def test_prospective_grants_multiclient_counts_and_independent_direct_origin(firm):
    app, client = firm
    admin = client.get('/api/v1/auth/me').json()['user']['id']
    peer = create_employee(client)
    a, b = customer(client), customer(client, 'Other related client')
    shared = workspace(client, customer_ids=[a['id'], b['id']])
    secret_b = workspace(client, title='Private B case', customer_ids=[b['id']])
    assignments(client, a['id'], [{'user_id': admin, 'scope': 'details'}, {'user_id': peer['id'], 'scope': 'all_cases'}])
    login(client)
    future = workspace(client, customer_ids=[a['id']])
    login(client, 'peer', PASSWORD)
    assert case_ids(client) == {shared['id'], future['id']}
    counts = {item['id']: item['workspace_count'] for item in client.get('/api/v1/customers').json()}
    assert counts == {a['id']: 2, b['id']: 1}
    assert client.get('/api/v1/matters/' + secret_b['id']).status_code == 404
    explanation = client.get('/api/v1/workspaces/' + shared['id'] + '/access').json()
    assert explanation['client_all_cases_origins'] == [a['id']] and not explanation['direct_case_grant']
    login(client)
    team(client, shared['id'], [{'user_id': admin}, {'user_id': peer['id'], 'responsible': True}])
    assignments(client, a['id'], [{'user_id': admin, 'scope': 'details'}])
    login(client, 'peer', PASSWORD)
    assert case_ids(client) == {shared['id']}
    explanation = client.get('/api/v1/workspaces/' + shared['id'] + '/access').json()
    assert explanation['direct_case_grant'] and explanation['responsible']
    assert explanation['client_all_cases_origins'] == []
    with app.state.store.session() as session:
        assert session.get(Membership, (shared['id'], peer['id']))


def test_multiple_supervisors_and_manager_cannot_assign_or_see_private_portfolio(firm):
    _, client = firm
    admin = client.get('/api/v1/auth/me').json()['user']['id']
    manager = create_employee(client, 'manager')
    a = create_employee(client, 'first', manager=manager['id'])
    b = create_employee(client, 'second')
    case = workspace(client, title='Confidential supervision')
    team(client, case['id'], [{'user_id': admin}, {'user_id': a['id'], 'supervisor': True},
                             {'user_id': b['id'], 'supervisor': True, 'responsible': True}])
    login(client, 'first', PASSWORD)
    view = client.get('/api/v1/workspaces/' + case['id'] + '/access').json()
    assert view['supervisor'] and sum(item['supervisor'] for item in view['team']) == 2
    assert client.put('/api/v1/firm-admin/workspaces/' + case['id'] + '/team', json={'revision': 2, 'members': []}).status_code == 403
    login(client, 'manager', PASSWORD)
    assert case_ids(client) == set()
    assert client.get('/api/v1/customers').json() == []
    assert client.get('/api/v1/workspaces/' + case['id'] + '/access').status_code == 404
    response = client.post('/api/v1/assistant/respond', json={'mode': 'weekly'})
    assert response.status_code == 200 and 'Confidential supervision' not in response.text


def test_configuration_admin_edits_opaque_references_without_content_bypass(firm):
    _, client = firm
    admin = client.get('/api/v1/auth/me').json()['user']['id']
    config = create_employee(client, 'config', 'Büro yöneticisi (yapılandırma)')
    a = customer(client, 'Never disclose this client')
    case = workspace(client, title='Never disclose this case', customer_ids=[a['id']])
    login(client, 'config', PASSWORD)
    for path in ('/firm-admin/customers/' + a['id'] + '/assignments', '/firm-admin/workspaces/' + case['id'] + '/team'):
        result = client.get('/api/v1' + path)
        assert result.status_code == 200
        assert 'Never disclose' not in result.text
    assignments(client, a['id'], [{'user_id': admin, 'scope': 'details'}, {'user_id': config['id'], 'scope': 'details'}])
    login(client, 'config', PASSWORD)
    assert client.get('/api/v1/customers').status_code == 403
    assert client.get('/api/v1/workspaces/' + case['id']).status_code == 403
    history = client.get('/api/v1/firm-admin/changes')
    assert history.status_code == 200 and 'Never disclose' not in history.text
    assert PASSWORD not in history.text


def test_revocation_relink_and_jobs_fail_closed_without_removing_direct_grant(firm):
    app, client = firm
    admin = client.get('/api/v1/auth/me').json()['user']['id']
    peer = create_employee(client)
    a = customer(client)
    case = workspace(client, customer_ids=[a['id']])
    assignments(client, a['id'], [{'user_id': admin, 'scope': 'details'}, {'user_id': peer['id'], 'scope': 'all_cases'}])
    login(client)
    peer_client = TestClient(app)
    try:
        login(peer_client, 'peer', PASSWORD)
        assert peer_client.get('/api/v1/workspaces/' + case['id']).status_code == 200
        with app.state.store.session() as session:
            owner = session.get(User, peer['id'])
            run = app.state.store.add(session, 'research', owner, {'status': 'running', 'phase': 'model'}, matter_id=case['id'])
            session.commit()
            run_id = run.id
        changed = client.put('/api/v1/workspaces/' + case['id'] + '/customers', json={
            'customer_ids': [], 'revision': case['revision'],
        })
        assert changed.status_code == 200, changed.text
        assert peer_client.get('/api/v1/auth/me').status_code == 401
        login(peer_client, 'peer', PASSWORD)
        assert case_ids(peer_client) == set()
        assert peer_client.get('/api/v1/matters/' + case['id']).status_code == 404
        with app.state.store.session() as session:
            state = app.state.store.decode(session.get(Record, run_id))
            assert state['status'] == 'cancelling' and state['stop_reason'] == 'access_revoked'
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            checkpoint(app, run_id, 'publishing')
        assert peer_client.get('/api/v1/workspaces').headers['cache-control'] == 'no-store'
    finally:
        peer_client.close()


def test_duplicate_foreign_inactive_and_stale_assignments_are_denied_atomically(firm):
    app, client = firm
    peer = create_employee(client)
    a = customer(client)
    path = '/api/v1/firm-admin/customers/' + a['id'] + '/assignments'
    before = client.get(path).json()
    with app.state.store.session() as session:
        session.add(User(id='foreign', username='foreign', name='Foreign', firm_id='foreign', role='lawyer', password_hash='unused'))
        session.get(User, peer['id']).active = False
        session.commit()
    for values, expected in (([{'user_id': 'foreign', 'scope': 'all_cases'}], 404),
                             ([{'user_id': peer['id'], 'scope': 'details'}], 404),
                             ([before['assignments'][0], before['assignments'][0]], 422)):
        result = client.put(path, json={'revision': before['revision'], 'assignments': values})
        assert result.status_code == expected
        assert client.get(path).json() == before
    assert client.put(path, json={'revision': before['revision'] + 1, 'assignments': []}).status_code == 409
    assert client.put(path, json={'revision': before['revision'], 'assignments': [{'user_id': 'foreign', 'scope': 'hierarchy'}]}).status_code == 422


def test_migration_only_preserves_details_and_does_not_resurrect_revocation(firm):
    app, client = firm
    a = customer(client)
    case = workspace(client, customer_ids=[a['id']])
    with app.state.store.session() as session:
        password = session.scalar(select(User.password_hash))
        memberships = {(item.matter_id, item.user_id) for item in session.scalars(select(Membership))}
        session.execute(delete(CustomerAssignment))
        session.execute(delete(ScopeMigration))
        initialize_scope(app.state.store, session, 'demo-firm')
        session.commit()
        grants = list(session.scalars(select(CustomerAssignment)))
        assert len(grants) == 1 and grants[0].scope == 'details'
        assert not list(session.scalars(select(CaseResponsibility)))
        assert memberships == {(item.matter_id, item.user_id) for item in session.scalars(select(Membership))}
        assert session.scalar(select(User.password_hash)) == password
        session.execute(delete(CustomerAssignment))
        initialize_scope(app.state.store, session, 'demo-firm')
        session.commit()
        assert not list(session.scalars(select(CustomerAssignment)))
    assert client.get('/api/v1/workspaces/' + case['id']).status_code == 200


def test_role_action_gate_hides_case_counts_even_with_client_scope(firm):
    from test_firm_admin import edit
    _, client = firm
    admin = client.get('/api/v1/auth/me').json()['user']['id']
    peer = create_employee(client)
    a = customer(client)
    workspace(client, title='Not allowed with details action', customer_ids=[a['id']])
    assignments(client, a['id'], [{'user_id': admin, 'scope': 'details'}, {'user_id': peer['id'], 'scope': 'all_cases'}])
    role = client.post('/api/v1/firm-admin/roles', json={'name': 'Client details only', 'permissions': ['portfolio.read', 'system.read']}).json()
    assert edit(client, peer, role_ids=[role['id']]).status_code == 200
    login(client, 'peer', PASSWORD)
    assert client.get('/api/v1/customers').json()[0]['workspace_count'] == 0
    assert client.get('/api/v1/workspaces').status_code == 403


def test_team_revocation_preserves_client_origin_and_rejects_last_scope_holder(firm):
    _, client = firm
    admin = client.get('/api/v1/auth/me').json()['user']['id']
    peer = create_employee(client)
    a = customer(client)
    case = workspace(client, customer_ids=[a['id']])
    assignments(client, a['id'], [{'user_id': admin, 'scope': 'details'}, {'user_id': peer['id'], 'scope': 'all_cases'}])
    team(client, case['id'], [{'user_id': admin}, {'user_id': peer['id'], 'supervisor': True}])
    team(client, case['id'], [{'user_id': admin}])
    login(client, 'peer', PASSWORD)
    explanation = client.get('/api/v1/workspaces/' + case['id'] + '/access').json()
    assert explanation['client_all_cases_origins'] == [a['id']]
    assert not explanation['direct_case_grant'] and not explanation['supervisor']
    login(client)
    team(client, case['id'], [])  # Client grant deliberately retains an active scope holder.
    path = '/api/v1/firm-admin/customers/' + a['id'] + '/assignments'
    current = client.get(path).json()
    assert client.put(path, json={'revision': current['revision'], 'assignments': [{'user_id': admin, 'scope': 'details'}]}).status_code == 409
    assert client.get(path).json() == current


def test_archived_case_team_remains_revocable_without_configuration_content_bypass(firm):
    app, client = firm
    admin = client.get('/api/v1/auth/me').json()['user']['id']
    peer = create_employee(client)
    case = workspace(client, title='Archived secret')
    team(client, case['id'], [{'user_id': admin}, {'user_id': peer['id'], 'supervisor': True}])
    with app.state.store.session() as session:
        record = session.get(Record, case['id'])
        record.kind = 'archived_matter'
        app.state.store.update(record, {**app.state.store.decode(record), 'status': 'archived'})
        session.commit()
    path = '/api/v1/firm-admin/workspaces/' + case['id'] + '/team'
    before = client.get(path)
    assert before.status_code == 200 and 'Archived secret' not in before.text
    result = client.put(path, json={'revision': before.json()['revision'], 'members': [{'user_id': admin}]})
    assert result.status_code == 200
    with app.state.store.session() as session:
        assert session.get(Membership, (case['id'], peer['id'])) is None
        assert session.get(CaseResponsibility, (case['id'], peer['id'])) is None
