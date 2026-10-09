"""Synthetic authenticated human workflow and its distinct scope/action/review boundaries."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_content_scope import team
from test_firm_admin import PASSWORD, create_employee, login
from test_firm_admin import firm as firm_fixture

from app.db import Audit, CaseResponsibility, Membership, Record, WorkParticipant
from app.human_workflow import normalize_due


@pytest.fixture
def workflow(tmp_path):
    yield from firm_fixture.__wrapped__(tmp_path)


def setup(app, client):
    admin = client.get('/api/v1/auth/me').json()['user']['id']
    first, second = create_employee(client, 'first'), create_employee(client, 'second')
    case = client.get('/api/v1/matters').json()[0]
    team(client, case['id'], [{'user_id': admin, 'supervisor': True}, {'user_id': first['id']}, {'user_id': second['id']}])
    return admin, first, second, case['id']


def create(client, case, recipients, kind='opinion', **overrides):
    body = {'kind': kind, 'title': 'Synthetic legal question', 'description': 'Human question, facts and uncertainties',
            'due_local': '2026-10-10T00:30', 'assignee_ids': recipients, **overrides}
    response = client.post(f'/api/v1/workspaces/{case}/work', json=body)
    assert response.status_code == 201, response.text
    return response.json()


def path(case, item):
    return f'/api/v1/workspaces/{case}/work/{item["id"]}'


def response_for(item, user):
    return next(row for row in item['responses'] if row['user_id'] == user)


def submit(client, case, item, own, text='Human written reasoning'):
    result = client.post(path(case, item) + '/submissions', json={'revision': own['revision'], 'text': text})
    assert result.status_code == 200, result.text
    return result.json()


def review(client, case, item, recipient, decision='revision_requested'):
    current = client.get(path(case, item)).json()
    own = response_for(current, recipient)
    submission = [e for e in own['history'] if e['action'] == 'submitted'][-1]
    result = client.post(path(case, item) + f'/responses/{recipient}/review', json={
        'revision': own['revision'], 'submission_id': submission['id'], 'decision': decision, 'note': 'Human review reason',
    })
    assert result.status_code == 200, result.text
    return result.json()


def edit_body(item, **changes):
    return {**{key: item[key] for key in ('kind', 'title', 'description', 'due_local', 'assignee_ids', 'status')},
            'revision': item['revision'], 'reason': 'Recorded human change', **changes}


def test_distinct_accounts_revise_and_accept_independent_opinions_with_authorship(workflow):
    app, client = workflow
    admin, first, second, case = setup(app, client)
    item = create(client, case, [first['id'], second['id']])
    login(client, 'first', PASSWORD)
    view = client.get(path(case, item)).json()
    assert [r['user_id'] for r in view['responses']] == [first['id']]
    submitted = submit(client, case, item, view['responses'][0], 'First original human opinion')
    assert submitted['responses'][0]['history'][0]['actor_id'] == first['id']
    assert submitted['responses'][0]['history'][0]['authorship'] == 'human_account'
    login(client)
    revised = review(client, case, item, first['id'])
    assert response_for(revised, second['id'])['status'] == 'pending'
    login(client, 'first', PASSWORD)
    own = client.get(path(case, item)).json()['responses'][0]
    submit(client, case, item, own, 'First revised human opinion')
    login(client)
    review(client, case, item, first['id'], 'accepted')
    login(client, 'second', PASSWORD)
    own = client.get(path(case, item)).json()['responses'][0]
    submit(client, case, item, own, 'Second independent opinion')
    login(client)
    accepted = review(client, case, item, second['id'], 'accepted')
    first_history = response_for(accepted, first['id'])['history']
    assert [e['text'] for e in first_history if e['action'] == 'submitted'] == ['First original human opinion', 'First revised human opinion']
    assert [e['actor_id'] for e in first_history if e['action'] == 'reviewed'] == [admin, admin]
    closed = client.put(path(case, item), json=edit_body(accepted, status='completed'))
    assert closed.status_code == 200, closed.text
    assert len(closed.json()['history']) == 2
    with app.state.store.session() as session:
        assert 'First original human opinion' not in session.get(Record, response_for(accepted, first['id'])['id']).payload
        assert len(list(session.scalars(select(Audit).where(Audit.action == 'human_opinion_reviewed')))) == 3


@pytest.mark.parametrize('kind', ['deadline', 'milestone', 'task'])
def test_manual_dates_progress_and_personal_supervisory_queues(workflow, kind):
    app, client = workflow
    _, first, second, case = setup(app, client)
    item = create(client, case, [first['id']], kind, due_local='2020-01-01T01:00')
    assert item['due_at'] == '2019-12-31T22:00:00+00:00'
    assert item['time_zone'] == 'Europe/Istanbul' and item['overdue']
    login(client, 'second', PASSWORD)
    assert client.get('/api/v1/work').json()['items'] == []
    assert client.get(path(case, item)).status_code == 404  # Case membership is not work recipient scope.
    login(client, 'first', PASSWORD)
    queue = client.get('/api/v1/work?bucket=overdue').json()
    assert [i['id'] for i in queue['items']] == [item['id']]
    assert client.get('/api/v1/work?view=supervisory').json()['items'] == []
    own = client.get(path(case, item)).json()['responses'][0]
    result = client.post(path(case, item) + '/progress', json={'revision': own['revision'], 'status': 'completed', 'note': 'Completed by assigned human'})
    assert result.status_code == 200
    assert client.get('/api/v1/work?bucket=overdue').json()['items'] == []
    assert len(client.get('/api/v1/work?bucket=closed').json()['items']) == 1
    login(client)
    current = client.get(path(case, item)).json()
    assert client.put(path(case, item), json=edit_body(current, status='completed')).status_code == 200
    assert client.get('/api/v1/work?view=supervisory&bucket=overdue').json()['items'] == []
    assert len(client.get('/api/v1/work?view=supervisory&bucket=closed').json()['items']) == 1


def test_supervision_and_recipients_do_not_create_case_grants(workflow):
    app, client = workflow
    admin, first, _, case = setup(app, client)
    stranger = create_employee(client, 'unassigned')
    before = client.get(f'/api/v1/workspaces/{case}/work').json()
    invalid = {'kind': 'task', 'title': 'Private task', 'description': '', 'due_local': '2026-10-10T17:00', 'assignee_ids': [stranger['id']]}
    assert client.post(f'/api/v1/workspaces/{case}/work', json=invalid).status_code == 422
    with app.state.store.session() as session:
        assert not session.get(Membership, (case, stranger['id']))
        assert not session.get(WorkParticipant, ('unknown', stranger['id']))
    login(client, 'first', PASSWORD)
    invalid['assignee_ids'] = [first['id']]
    assert client.post(f'/api/v1/workspaces/{case}/work', json=invalid).status_code == 403
    login(client, 'unassigned', PASSWORD)
    assert client.get(f'/api/v1/workspaces/{case}/work').status_code == 404
    assert client.get('/api/v1/work?view=supervisory').json()['items'] == []
    login(client)
    assert client.get(f'/api/v1/workspaces/{case}/work').json() == before
    with app.state.store.session() as session:
        assert session.get(CaseResponsibility, (case, admin)).supervisor


def test_changed_question_and_recipient_edits_retain_history_and_require_new_opinion(workflow):
    app, client = workflow
    _, first, second, case = setup(app, client)
    item = create(client, case, [first['id']])
    login(client, 'first', PASSWORD)
    own = client.get(path(case, item)).json()['responses'][0]
    submit(client, case, item, own)
    login(client)
    accepted = review(client, case, item, first['id'], 'accepted')
    changed = client.put(path(case, item), json=edit_body(accepted, description='Changed facts and question')).json()
    assert changed['request_version'] == 2 and changed['responses'][0]['status'] == 'stale'
    assert client.put(path(case, item), json=edit_body(changed, status='completed')).status_code == 409
    login(client, 'first', PASSWORD)
    own = client.get(path(case, item)).json()['responses'][0]
    submit(client, case, item, own, 'New-version response')
    login(client)
    current = client.get(path(case, item)).json()
    replaced = client.put(path(case, item), json=edit_body(current, assignee_ids=[second['id']])).json()
    previous = response_for(replaced, first['id'])
    assert not previous['active'] and len(previous['history']) == 3
    login(client, 'first', PASSWORD)
    assert client.get(path(case, item)).status_code == 404
    assert client.get('/api/v1/work').json()['items'] == []
    login(client, 'second', PASSWORD)
    view = client.get(path(case, item)).json()
    assert len(view['responses']) == 1 and view['responses'][0]['history'] == []


def test_wrong_version_self_review_impersonation_and_extra_fields_fail_closed(workflow):
    app, client = workflow
    admin, first, _, case = setup(app, client)
    item = create(client, case, [admin, first['id']])
    own = response_for(item, admin)
    result = submit(client, case, item, own)
    self_result = response_for(result, admin)
    endpoint = path(case, item) + f'/responses/{admin}/review'
    body = {'revision': self_result['revision'], 'submission_id': self_result['history'][0]['id'], 'decision': 'accepted', 'note': 'Self approval denied'}
    assert client.post(endpoint, json=body).status_code == 403
    assert client.post(path(case, item) + '/submissions', json={'revision': 1, 'text': 'Pretend', 'author_id': first['id']}).status_code == 422
    assert client.post(path(case, item) + '/submissions', json={'revision': 1, 'text': 'Stale write'}).status_code == 409
    login(client, 'first', PASSWORD)
    assert client.post(path(case, item) + f'/responses/{admin}/review', json=body).status_code == 403
    assert client.post(path(case, item) + '/progress', json={'revision': 1, 'status': 'completed', 'note': 'Not an opinion submission'}).status_code == 422


def test_revoked_session_cannot_recover_work_or_prior_opinion_and_supervisor_can_cancel(workflow):
    app, client = workflow
    admin, first, _, case = setup(app, client)
    item = create(client, case, [first['id']])
    other = TestClient(app)
    try:
        login(other, 'first', PASSWORD)
        own = other.get(path(case, item)).json()['responses'][0]
        submit(other, case, item, own, 'Confidential human opinion')
        team(client, case, [{'user_id': admin, 'supervisor': True}])
        assert other.get('/api/v1/auth/me').status_code == 401
        login(other, 'first', PASSWORD)
        assert other.get('/api/v1/work').json()['items'] == []
        assert other.get(path(case, item)).status_code == 404
        current = client.get(path(case, item)).json()
        assert not current['responses'][0]['currently_eligible']
        response = current['responses'][0]
        submission = response['history'][0]
        assert client.post(path(case, item) + f'/responses/{first["id"]}/review', json={
            'revision': response['revision'], 'submission_id': submission['id'], 'decision': 'accepted', 'note': 'No current permission',
        }).status_code == 409
        assert client.put(path(case, item), json=edit_body(current, status='cancelled')).status_code == 200
    finally:
        other.close()


def test_archive_removes_queues_and_denies_work_actions(workflow):
    app, client = workflow
    _, first, _, case = setup(app, client)
    item = create(client, case, [first['id']], 'deadline')
    current = client.get('/api/v1/matters/' + case).json()
    result = client.post(f'/api/v1/matters/{case}/archive', json={'expected_revision': current['revision'], 'reason': 'Synthetic archive'})
    assert result.status_code == 200, result.text
    assert client.get('/api/v1/work?view=supervisory').json()['items'] == []
    assert client.get(path(case, item)).status_code == 404
    with app.state.store.session() as session:
        assert session.get(Record, item['id'])  # Retention is preserved, never automatic physical erasure.


def test_time_validation_duplicates_kind_mutation_and_early_completion(workflow):
    app, client = workflow
    _, first, _, case = setup(app, client)
    assert normalize_due('2026-10-10T00:30') == '2026-10-09T21:30:00+00:00'
    for value in ['2026-02-30T17:00', '2026-10-10T17:00Z', '2026-10-10', 'not-date']:
        with pytest.raises(ValueError):
            normalize_due(value)
    item = create(client, case, [first['id']], 'task')
    assert client.put(path(case, item), json=edit_body(item, status='completed')).status_code == 409
    assert client.put(path(case, item), json=edit_body(item, kind='deadline')).status_code == 422
    assert client.put(path(case, item), json=edit_body(item, assignee_ids=[first['id'], first['id']])).status_code == 422
    assert client.put(path(case, item), json=edit_body(item, revision=99)).status_code == 409
    assert client.get(path(case, item)).json()['revision'] == item['revision']
    assert client.get(path(case, item)).headers['cache-control'] == 'no-store'
    assert datetime.fromisoformat(item['history'][0]['recorded_at']).tzinfo == timezone.utc


def test_changed_task_instructions_require_fresh_progress_not_old_completion(workflow):
    app, client = workflow
    _, first, _, case = setup(app, client)
    item = create(client, case, [first['id']], 'task')
    login(client, 'first', PASSWORD)
    result = client.post(path(case, item) + '/progress', json={'revision': 1, 'status': 'completed', 'note': 'Original task complete'})
    assert result.status_code == 200
    login(client)
    current = client.get(path(case, item)).json()
    updated = client.put(path(case, item), json=edit_body(current, description='Additional evidence to inspect')).json()
    assert updated['responses'][0]['status'] == 'stale'
    assert client.put(path(case, item), json=edit_body(updated, status='completed')).status_code == 409
    login(client, 'first', PASSWORD)
    assert len(client.get('/api/v1/work?bucket=upcoming').json()['items']) == 1
    own = client.get(path(case, item)).json()['responses'][0]
    assert client.post(path(case, item) + '/progress', json={'revision': own['revision'], 'status': 'completed', 'note': 'Additional work completed'}).status_code == 200
    assert client.post(path(case, item) + '/progress', json={'revision': own['revision'], 'status': 'completed', 'note': 'Stale duplicate'}).status_code == 409


def test_removing_supervisor_flag_with_retained_case_access_closes_other_opinions(workflow):
    app, client = workflow
    admin, first, second, case = setup(app, client)
    item = create(client, case, [first['id']])
    team(client, case, [{'user_id': admin}, {'user_id': first['id']}, {'user_id': second['id'], 'supervisor': True}])
    assert client.get('/api/v1/matters/' + case).status_code == 200
    assert client.get('/api/v1/work?view=supervisory').json()['items'] == []
    assert client.get(path(case, item)).status_code == 404
    login(client, 'second', PASSWORD)
    assert client.get(path(case, item)).status_code == 200
    assert client.put(path(case, item), json=edit_body(item, title='Current appointed supervisor edits')).status_code == 200


def test_foreign_configuration_and_read_only_accounts_cannot_act_or_read_private_work(workflow):
    from app.auth import hash_password
    from app.db import User
    app, client = workflow
    admin, first, _, case = setup(app, client)
    reader = create_employee(client, 'reader', 'Salt okuma')
    create_employee(client, 'configuration', 'Büro yöneticisi (yapılandırma)')
    team(client, case, [{'user_id': admin, 'supervisor': True}, {'user_id': first['id']}, {'user_id': reader['id']}])
    item = create(client, case, [first['id']])
    invalid = {'kind': 'task', 'title': 'No action permission', 'description': '', 'due_local': '2026-10-10T17:00', 'assignee_ids': [reader['id']]}
    assert client.post(f'/api/v1/workspaces/{case}/work', json=invalid).status_code == 422
    login(client, 'reader', PASSWORD)
    assert client.get(path(case, item)).status_code == 404
    assert client.post(f'/api/v1/workspaces/{case}/work', json=invalid).status_code == 403
    login(client, 'configuration', PASSWORD)
    assert client.get('/api/v1/work').status_code == 403
    with app.state.store.session() as session:
        session.add(User(username='foreign', name='Foreign', firm_id='other-firm', role='admin', password_hash=hash_password(PASSWORD)))
        session.commit()
    login(client, 'foreign', PASSWORD)
    assert client.get('/api/v1/work?view=supervisory').json()['items'] == []
    assert client.get(path(case, item)).status_code == 404


def test_removing_work_recipient_invalidates_session_even_with_retained_case_scope(workflow):
    app, client = workflow
    _, first, second, case = setup(app, client)
    item = create(client, case, [first['id']])
    other = TestClient(app)
    try:
        login(other, 'first', PASSWORD)
        assert other.get(path(case, item)).status_code == 200
        assert client.put(path(case, item), json=edit_body(item, assignee_ids=[second['id']])).status_code == 200
        assert other.get('/api/v1/auth/me').status_code == 401
        login(other, 'first', PASSWORD)
        assert other.get('/api/v1/matters/' + case).status_code == 200
        assert other.get(path(case, item)).status_code == 404
        assert other.get('/api/v1/work').json()['items'] == []
    finally:
        other.close()
