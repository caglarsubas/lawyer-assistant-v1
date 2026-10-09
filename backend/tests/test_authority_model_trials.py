"""Invented authorities, fixture accounts and mocked inference
no legal approval."""
import copy
import json
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session
from test_analysis_authorities import mutate, payload
from test_analysis_comparisons import completed, effort, login
from test_authority_proposals import output, prepare
from test_authority_proposals import workbench as workbench_fixture
from test_authority_revalidations import ready, saved

from app import authority_model_trials as trials
from app.auth import hash_password
from app.db import Membership, User

workbench = workbench_fixture


def register(workbench, monkeypatch, *, renewal=False):
    app, client, base, *_ = workbench
    if renewal:
        path, _, permit, reader, _ = ready(workbench, monkeypatch)
        renewed, _ = saved(client, path)
        record = renewed['analysis']
        dep = record['authority_dependencies'][0]
        selection = {'kind': 'admitted_renewal', **{key: dep[key] for key in ('context_id', 'review_id', 'review_sha256')},
            'renewal_id': renewed['id'], 'renewal_sha256': record['authority_revalidations'][-1]['sha256'],
            'findings': [{'source_index': 0, 'dimension': 'history'}]}
    else:
        _, spec, record, _, permit, _, reader = prepare(workbench, monkeypatch)
        selection = {'kind': 'original_review', **spec['authority_feedback']}
    reviewers = []
    with app.state.store.session() as session:
        for index in range(2):
            user = User(username=f'SYNTHETIC-model-reviewer-{index}', name=f'SYNTHETIC model reviewer {index}',
                firm_id='demo-firm', role='lawyer', password_hash=hash_password('SYNTHETIC-review-only'))
            session.add(user)
            session.flush()
            session.add(Membership(matter_id=base.split('/')[-1], user_id=user.id))
            reviewers.append(user.id)
        session.commit()
    calls = []
    def suggest(content, **options):
        calls.append((copy.deepcopy(content), copy.deepcopy(options)))
        if options['repair']:
            result = output(outcome='unresolved')
            result.pop('conclusion_update')
            result['authority_responses'][0]['edited_targets'] = []
            return json.dumps(result)
        return json.dumps(output(text='SYNTHETIC trial-only candidate'))
    monkeypatch.setattr(app.state.provider, 'suggest_analysis', suggest)
    path = base + '/analyses/' + record['id'] + '/authority-model-trials'
    preview = client.post(path + '/registration-context', json={'selection': selection})
    assert preview.status_code == 200, preview.text
    context = preview.json()
    body = {'request_id': uuid4().hex, 'expected_revision': record['revision'], 'version_id': record['latest_version_id'],
        'context_sha256': context['context_sha256'], 'selection': selection, 'title': 'SYNTHETIC public model trial',
        'question': 'SYNTHETIC fixed source comparison', 'rubric_text': 'SYNTHETIC review exact passages and adverse gaps',
        'split_family_sha256': 'a' * 64, 'sample_kind': 'synthetic', 'reviewer_ids': reviewers}
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return path, response.json(), body, calls, permit, reader, record


def run(client, path, value):
    response = client.post(path + '/' + value['id'] + '/run', json={})
    assert response.status_code == 202, response.text
    return completed(client, path, value['id'])


def observation(value, *, outcome='unresolved'):
    basis = value['protocol']['authority_basis']
    return {'request_id': uuid4().hex, 'execution_sha256': value['execution_sha256'],
        'expected_previous_id': value['previous_observation_id'], 'note': 'SYNTHETIC account observation only',
        'arms': [{'arm': arm, 'assessment': {'comparison_sha256': item['comparison']['comparison_sha256'],
            'observations': [{'dimension': dimension, 'outcome': outcome, 'note': 'SYNTHETIC semantic uncertainty',
                'target_refs': [], 'private_source_refs': [], 'public_source_indices': []}
                for dimension in value['protocol']['dimensions']],
            'judgments': [{'source_index': index, 'dimension': dimension, 'outcome': 'unresolved',
                'note': 'SYNTHETIC unqualified finding', 'target_refs': [], 'private_source_refs': [], 'public_source_indices': []}
                for index, source in enumerate(basis['assessment']['sources']) for dimension in basis['authority_dimensions']],
            'adverse_scope': {'status': 'not_searched', 'inspected_source_indices': [], 'limitations': 'SYNTHETIC no corpus recall claim'},
            'note': 'SYNTHETIC separate source-linked assessment', 'review_seconds': None}} for arm, item in value['arms'].items()]}


@pytest.mark.parametrize('renewal', [False, True])
def test_frozen_original_or_renewed_inputs_no_adoption_and_permanent_receipts(workbench, monkeypatch, renewal):
    app, client, base, *_ = workbench
    path, registered, body, calls, _, _, record = register(workbench, monkeypatch, renewal=renewal)
    assert not calls and registered['can_run'] and not registered['capture_complete']
    frozen = payload(app, registered['id'])
    version = payload(app, record['latest_version_id'])
    assert client.post(path, json=body).json()['id'] == registered['id']
    assert client.post(path, json={**body, 'rubric_text': 'SYNTHETIC changed rubric'}).status_code == 409
    result = run(client, path, registered)
    assert len(calls) == 2 and calls[0][0] == calls[1][0]
    assert calls[0][1]['authority_feedback'] == calls[1][1]['authority_feedback']
    assert result['protocol']['authority_basis']['input_ref']['kind'] == body['selection']['kind']
    assert all(item['provider_round_trip_seconds'] >= 0 for item in result['arms'].values())
    for arm, item in result['arms'].items():
        job = item['job']
        assert job['created_at'] >= result['protocol']['registered_at']
        assert job['authority_feedback'] == result['protocol']['authority_feedback']
        suggestions = base + '/analyses/' + record['id'] + '/suggestions'
        assert not client.get(suggestions + '/' + job['id']).json()['can_adopt']
        assert client.post(suggestions + '/' + job['id'] + '/adopt', json={'expected_revision': record['revision'],
            'candidate_sha256': job['candidate_sha256'], 'change_note': 'SYNTHETIC cannot adopt trial'}).status_code == 409
    assert client.post(path + '/' + result['id'] + '/run', json={}).status_code == 202 and len(calls) == 2
    assert payload(app, registered['id']) == frozen and payload(app, record['latest_version_id']) == version
    assert 'SYNTHETIC-NOT-A-REAL-KEY' not in json.dumps(result)


def test_two_accounts_unknown_effort_and_disagreement_without_approval(workbench, monkeypatch):
    _, client, *_ = workbench
    path, value, _, _, *_ = register(workbench, monkeypatch)
    value = run(client, path, value)
    detail = path + '/' + value['id']
    assert client.post(detail + '/observations', json=observation(value)).status_code == 409
    for index in range(2):
        login(client, f'SYNTHETIC-model-reviewer-{index}')
        current = client.get(detail).json()
        assert current['can_observe'] and not current['can_run']
        body = observation(current, outcome='unresolved' if index == 0 else 'not_assessed')
        response = client.post(detail + '/observations', json=body)
        assert response.status_code == 201, response.text
        assert client.post(detail + '/observations', json=body).json()['id'] == response.json()['id']
        assert client.post(detail + '/observations', json={**body, 'note': 'SYNTHETIC changed nonce'}).status_code == 409
    login(client)
    current = client.get(detail).json()
    assert current['current_reviewer_count'] == 2 and current['disagreement'] and not current['capture_complete']
    body = {**effort(current), 'active_phases_nonoverlapping': True}
    assert client.post(detail + '/effort', json=body).status_code == 201
    current = client.get(detail).json()
    assert current['capture_complete'] and not current['qualification_granted'] and not current['benefit_established']
    response = client.get(detail + '/export')
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    body = {**effort(current), 'active_phases_nonoverlapping': True}
    body['arms'][0]['verification_seconds'] = None
    assert client.post(detail + '/effort', json=body).status_code == 201
    assert not client.get(detail).json()['capture_complete']


@pytest.mark.parametrize('change', ['rights', 'source', 'private', 'model', 'reviewer', 'seal'])
def test_changes_close_run_observation_and_export_and_never_rewrite(workbench, monkeypatch, change):
    app, client, base, _, fact, *_ = workbench
    path, value, _, calls, permit, reader, _ = register(workbench, monkeypatch)
    old = payload(app, value['id'])
    detail = path + '/' + value['id']
    if change == 'rights':
        permit.active = False
    elif change == 'source':
        reader.info['pointer']['sequence'] += 1
    elif change == 'private':
        mutate(app, fact['id'], lambda data: data.update(text='SYNTHETIC changed fact'))
    elif change == 'model':
        app.state.settings.provider_model = 'SYNTHETIC changed model'
    elif change == 'reviewer':
        with app.state.store.session() as session:
            session.delete(session.get(Membership, (base.split('/')[-1], value['protocol']['reviewer_ids'][0])))
            session.commit()
    else:
        mutate(app, value['id'], lambda data: data.update(question='SYNTHETIC corrupted seal'))
    response = client.get(detail)
    if change == 'seal':
        assert response.status_code == 409
    else:
        assert response.json()['freshness']['status'] in {'withheld', 'stale'}
        if change in {'rights', 'source'}:
            assert response.json()['protocol'] is None and 'SYNTHETIC public model trial' not in response.text
    assert client.post(detail + '/run', json={}).status_code == 409 and not calls
    assert client.get(detail + '/export').status_code == 409
    if change != 'seal':
        assert payload(app, value['id']) == old


def test_supported_observations_need_complete_links_and_adverse_scope(workbench, monkeypatch):
    _, client, *_ = workbench
    path, value, *_ = register(workbench, monkeypatch)
    value = run(client, path, value)
    detail = path + '/' + value['id']
    login(client, 'SYNTHETIC-model-reviewer-0')
    value = client.get(detail).json()
    assert client.post(detail + '/observations', json=observation(value, outcome='supported')).status_code == 422
    body = observation(value)
    body['arms'][0]['assessment']['judgments'].pop()
    assert client.post(detail + '/observations', json=body).status_code == 422


def test_commit_then_late_guard_failure_is_permanently_pending_on_retry(workbench, monkeypatch):
    app, client, *_ = workbench
    path, value, body, calls, permit, *_ = register(workbench, monkeypatch)
    body['request_id'] = uuid4().hex
    original = app.state.store.add
    def late(session, kind, *args, **kwargs):
        result = original(session, kind, *args, **kwargs)
        if kind == trials.KIND:
            session.info['fail_authority_trial_after_commit'] = True
        return result
    commit = Session.commit
    def committed(session):
        commit(session)
        if session.info.pop('fail_authority_trial_after_commit', False):
            permit.fail_exit = True
    monkeypatch.setattr(Session, 'commit', committed)
    monkeypatch.setattr(app.state.store, 'add', late)
    response = client.post(path, json=body)
    assert response.status_code == 409, response.text
    assert response.json()['status'] == 'committed_needs_revalidation'
    permit.fail_exit = False
    assert client.post(path, json=body).json()['protocol'] is None
    ident = response.json()['id']
    assert client.get(path + '/' + ident).json()['protocol'] is None
    assert client.post(path + '/' + ident + '/run', json={}).status_code == 409 and not calls


def test_cancellation_and_inflight_revocation_do_not_publish_candidates(workbench, monkeypatch):
    app, client, *_ = workbench
    path, value, _, _, permit, *_ = register(workbench, monkeypatch)
    entered, release = Event(), Event()
    def blocked(*_a, **_k):
        entered.set()
        assert release.wait(5)
        return json.dumps(output(text='SYNTHETIC trial-only candidate'))
    monkeypatch.setattr(app.state.provider, 'suggest_analysis', blocked)
    try:
        response = client.post(path + '/' + value['id'] + '/run', json={})
        assert response.status_code == 202 and entered.wait(5)
        permit.active = False
        release.set()
        assert client.get(path + '/' + value['id']).json()['protocol'] is None
    finally:
        release.set()


def test_rejected_repair_keeps_original_response_pass_without_adoption(workbench, monkeypatch):
    workbench[3]['applications'][0]['assessments'].pop()
    app, client, *_ = workbench
    path, value, *_ = register(workbench, monkeypatch)
    seen = []
    def suggest(_content, **options):
        seen.append(options['repair'])
        result = output(text='SYNTHETIC first trial edit')
        if options['repair']:
            result['conclusion_update']['text'] = 'SYNTHETIC rejected trial edit'
            result['application_updates'] = [{'id': 'a1', 'assessments': [
                {'condition_id': 'c1', 'status': 'not_met', 'premise_ids': ['p1']}]}]
            result['authority_responses'][0]['edited_targets'].append('application:a1')
        return json.dumps(result)
    monkeypatch.setattr(app.state.provider, 'suggest_analysis', suggest)
    value = run(client, path, value)
    assert seen == [False, False, True]
    repair = value['arms']['bounded_correction']['job']
    assert [item['outcome'] for item in repair['iterations']] == ['accepted_structural_patch', 'rejected_new_critical_checks']
    assert repair['authority_response_pass'] == 1
    assert repair['candidate']['conclusion']['text'] == 'SYNTHETIC first trial edit'
    assert not client.get(path.replace('/authority-model-trials', '/suggestions') + '/' + repair['id']).json()['can_adopt']


def test_observation_late_failure_stays_withheld_after_recovery(workbench, monkeypatch):
    app, client, *_ = workbench
    path, value, _, _, permit, *_ = register(workbench, monkeypatch)
    value = run(client, path, value)
    login(client, 'SYNTHETIC-model-reviewer-0')
    detail = path + '/' + value['id']
    value = client.get(detail).json()
    body = observation(value)
    original = app.state.store.add
    def late(session, kind, *args, **kwargs):
        row = original(session, kind, *args, **kwargs)
        if kind == trials.JUDGMENT:
            session.info['fail_authority_trial_after_commit'] = True
        return row
    commit = Session.commit
    def committed(session):
        commit(session)
        if session.info.pop('fail_authority_trial_after_commit', False):
            permit.fail_exit = True
    monkeypatch.setattr(Session, 'commit', committed)
    monkeypatch.setattr(app.state.store, 'add', late)
    result = client.post(detail + '/observations', json=body)
    assert result.status_code == 409 and result.json()['status'] == 'committed_needs_revalidation'
    permit.fail_exit = False
    assert client.get(detail).json()['protocol'] is None
    assert client.post(detail + '/observations', json=body).status_code == 409
    assert client.get(detail + '/export').status_code == 409


def test_export_guard_exit_discards_all_packet_bytes(workbench, monkeypatch):
    app, client, *_ = workbench
    path, value, _, _, permit, *_ = register(workbench, monkeypatch)
    original = trials.canonical
    def late(value):
        result = original(value)
        if isinstance(value, dict) and value.get('exported_at'):
            permit.fail_exit = True
        return result
    monkeypatch.setattr(trials, 'canonical', late)
    result = client.get(path + '/' + value['id'] + '/export')
    assert result.status_code == 409 and 'SYNTHETIC public model trial' not in result.text


@pytest.mark.parametrize('mutation', ['origin', 'nonce', 'override', 'supported', 'mixed'])
def test_invalid_registration_or_dispatch_never_calls_model(workbench, monkeypatch, mutation):
    _, client, *_ = workbench
    path, value, body, calls, *_ = register(workbench, monkeypatch)
    body = copy.deepcopy(body)
    if mutation == 'origin':
        body.update(request_id=uuid4().hex, sample_kind='real')
    elif mutation == 'nonce':
        body['question'] = 'SYNTHETIC changed same nonce'
    elif mutation == 'override':
        assert client.post(path + '/' + value['id'] + '/run', json={'mode': 'repair'}).status_code == 422
        return
    elif mutation == 'supported':
        body['selection']['findings'] *= 2
    else:
        body['review_feedback'] = {'review_id': 'SYNTHETIC fake private review', 'finding_indices': [0]}
    assert client.post(path, json=body).status_code in {409, 422}
    assert not calls
