"""Invented trials and distinct fixture accounts; no legal/model qualification."""

import copy
import json
import time
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_analysis_reviews import review_request
from test_analysis_suggestions import patch, prepare
from test_analysis_workbench import workbench as workbench_fixture

from app import analysis_comparisons as comparisons
from app.auth import hash_password
from app.db import Membership, Record, User, digest
from app.evidence_prompt import canonical
from app.research_jobs import QueueUnavailable


@pytest.fixture
def workbench(tmp_path):
    yield from workbench_fixture.__wrapped__(tmp_path)


def login(client, username='demo'):
    response = client.post('/api/v1/auth/login', json={
        'username': username, 'password': 'demo-local-only' if username == 'demo' else 'SYNTHETIC-review-only'})
    assert response.status_code == 200, response.text
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']


def register(workbench, monkeypatch, *, reviewed=True, mock=None, feedback=False):
    app, client, base, *_ = workbench
    record, _ = prepare(workbench, monkeypatch)
    reviewers = []
    with app.state.store.session() as session:
        owner = session.scalar(select(User).where(User.username == 'demo'))
        for index in range(2):
            user = User(username=f'SYNTHETIC-reviewer-{index}', name=f'SYNTHETIC reviewer {index}',
                        firm_id=owner.firm_id, role='lawyer', password_hash=hash_password('SYNTHETIC-review-only'))
            session.add(user)
            session.flush()
            session.add(Membership(matter_id=base.rsplit('/', 1)[1], user_id=user.id))
            reviewers.append(user.id)
        session.commit()
    if reviewed:
        reviews = base + '/analyses/' + record['id'] + '/reviews'
        body, _ = review_request(client, reviews, record, decision='changes_requested')
        if feedback:
            body['findings'][0]['target_id'] = 'application:a1'
        assert client.post(reviews, json=body).status_code == 201
    calls = []

    def suggest(content, **options):
        calls.append((copy.deepcopy(content), options))
        if mock:
            return mock(content, options)
        output = patch() if options['repair'] else {
            'application_updates': [{'id': 'a1', 'rationale': 'SYNTHETIC changed interpretation; still incomplete'}]}
        if feedback:
            output['feedback_responses'] = [{'finding_id': 'finding:0', 'outcome': 'proposed_change',
                'text': 'SYNTHETIC proposed edits, not resolved finding',
                'edited_targets': ['application:a1', 'conclusion'] if options['repair'] else ['application:a1'],
                'evidence_ids': ['synthetic-clause']}]
        return json.dumps(output)

    monkeypatch.setattr(app.state.provider, 'suggest_analysis', suggest)
    endpoint = base + '/analyses/' + record['id'] + '/comparisons'
    body = {'request_id': uuid4().hex, 'expected_revision': record['revision'], 'version_id': record['latest_version_id'],
            'context_sha256': client.get(endpoint + '/registration-context').json()['context_sha256'],
            'title': 'SYNTHETIC same-input comparison', 'question': 'SYNTHETIC capture behavior only',
            'rubric_text': 'SYNTHETIC — inspect sources, roles, conditions, chronology, counterevidence and certainty.',
            'split_family_sha256': 'a' * 64, 'sample_kind': 'synthetic', 'reviewer_ids': reviewers}
    if feedback:
        body['review_feedback'] = {'review_id': client.get(endpoint + '/registration-context').json()['source_review_id'],
                                   'finding_indices': [0]}
    result = client.post(endpoint, json=body)
    assert result.status_code == 201, result.text
    return record, endpoint, result.json(), body, calls


def completed(client, endpoint, ident):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        response = client.get(endpoint + '/' + ident)
        assert response.status_code == 200, response.text
        value = response.json()
        # A public-source job can briefly withhold its capture while its
        # post-commit admission is pending. Empty arms are not completion.
        if len(value['arms']) == 2 and all(item['status'] not in {'not_started', 'queued', 'running', 'cancelling'}
                                         for item in value['arms'].values()):
            return value
        time.sleep(.01)
    pytest.fail('Synthetic comparison did not finish')


def observation(view):
    return {'request_id': uuid4().hex, 'execution_sha256': view['execution_sha256'],
            'expected_previous_id': view['previous_observation_id'], 'note': 'SYNTHETIC independent-account declaration only',
            'arms': [{'arm': arm, 'assessment': {
                'comparison_sha256': item['comparison']['comparison_sha256'], 'review_seconds': None,
                'observations': [{'dimension': key, 'outcome': 'not_assessed', 'note': 'SYNTHETIC not real adjudication',
                                  'target_ids': ['conclusion'], 'source_refs': []} for key in item['comparison']['dimensions']],
                'finding_dispositions': [{'finding_index': finding['finding_index'], 'outcome': 'unresolved',
                    'note': 'SYNTHETIC unresolved original finding', 'target_ids': [finding['target_id']], 'source_refs': []}
                    for finding in item['comparison']['findings']]}}
                for arm, item in view['arms'].items()]}


def effort(view):
    return {'request_id': uuid4().hex, 'execution_sha256': view['execution_sha256'],
            'expected_previous_id': view['previous_effort_id'], 'note': 'SYNTHETIC active effort declaration only',
            'shared_setup_included': True, 'verification_and_correction_included': True,
            'arms': [{'arm': arm, 'preparation_seconds': 20, 'verification_seconds': 30, 'correction_seconds': 10}
                     for arm in comparisons.ARMS]}


def run(client, endpoint, view):
    response = client.post(endpoint + '/' + view['id'] + '/run')
    assert response.status_code == 202, response.text
    return completed(client, endpoint, view['id'])


def test_registration_precedes_runs_exact_pair_and_no_live_adoption(workbench, monkeypatch):
    app, client, base, *_ = workbench
    record, endpoint, registered, request, calls = register(workbench, monkeypatch)
    assert not calls and registered['can_run'] and not registered['capture_complete']
    assert all(item['status'] == 'not_started' for item in registered['arms'].values())
    with app.state.store.session() as session:
        frozen = session.get(Record, registered['id']).payload
    assert client.post(endpoint, json=request).json()['id'] == registered['id']
    changed = {**request, 'rubric_text': 'SYNTHETIC changed rubric'}
    assert client.post(endpoint, json=changed).status_code == 409
    view = run(client, endpoint, registered)
    assert len(calls) == 3 and calls[0][0] == calls[1][0]
    assert calls[0][1]['repair'] is False and calls[1][1]['repair'] is False and calls[2][1]['repair'] is True
    assert all(item['job']['created_at'] >= registered['protocol']['registered_at'] for item in view['arms'].values())
    assert [len(view['arms'][arm]['job']['iterations']) for arm in comparisons.ARMS] == [1, 2]
    assert all(item['provider_round_trip_seconds'] >= 0 and item['gpu_compute_seconds'] is None for item in view['arms'].values())
    assert not view['capture_complete'] and not view['can_observe'] and not view['qualification_granted']
    for item in view['arms'].values():
        job = item['job']
        assert digest(canonical(job['source_content'])) == view['protocol']['task_input_sha256']
        assert job['comparison_ref']['protocol_sha256'] == view['protocol']['protocol_sha256']
        suggestions = base + '/analyses/' + record['id'] + '/suggestions'
        assert not client.get(suggestions + '/' + job['id']).json()['can_adopt']
        assert client.post(suggestions + '/' + job['id'] + '/adopt', json={
            'expected_revision': record['revision'], 'candidate_sha256': job['candidate_sha256'],
            'change_note': 'SYNTHETIC prohibited experimental adoption'}).status_code == 409
    assert client.get(base + '/analyses').json()[0]['version'] == 1
    assert client.post(endpoint + '/' + view['id'] + '/run').status_code == 202 and len(calls) == 3
    with app.state.store.session() as session:
        assert session.get(Record, registered['id']).payload == frozen
        assert 'SYNTHETIC same-input' not in frozen
    assert 'SYNTHETIC-NOT-A-REAL-KEY' not in json.dumps(view)


def test_distinct_authenticated_observations_and_full_effort_complete_capture_not_qualification(workbench, monkeypatch):
    _, client, base, *_ = workbench
    _, endpoint, registered, _, calls = register(workbench, monkeypatch)
    view = run(client, endpoint, registered)
    detail = endpoint + '/' + view['id']
    assert client.post(detail + '/observations', json=observation(view)).status_code == 409
    for index in range(2):
        login(client, f'SYNTHETIC-reviewer-{index}')
        context = client.get(detail).json()
        assert context['can_observe'] and not context['can_run'] and not context['can_record_effort']
        assert client.post(detail + '/run').status_code == 403
        body = observation(context)
        result = client.post(detail + '/observations', json=body)
        assert result.status_code == 201, result.text
        assert result.json()['reviewer_id'] == context['protocol']['reviewer_ids'][index]
        assert result.json()['comparison_snapshots']['single_pass'] == context['arms']['single_pass']['comparison']
        assert client.post(detail + '/observations', json=body).json()['id'] == result.json()['id']
        altered = copy.deepcopy(body)
        altered['note'] += ' changed'
        assert client.post(detail + '/observations', json=altered).status_code == 409
        assert client.post(detail + '/effort', json=effort(context)).status_code == 409
    login(client)
    view = client.get(detail).json()
    assert view['current_reviewer_count'] == 2 and not view['effort_accounted'] and not view['capture_complete']
    body = effort(view)
    result = client.post(detail + '/effort', json=body)
    assert result.status_code == 201, result.text
    assert client.post(detail + '/effort', json=body).json()['id'] == result.json()['id']
    view = client.get(detail).json()
    assert view['capture_complete'] and view['effort_accounted'] and not view['benefit_established']
    assert not view['qualification_granted'] and view['sample_kind'] == 'synthetic'
    assert all(item['arms'][0]['assessment']['review_seconds'] is None for item in view['observations'])
    assert len(calls) == 3 and client.get(base + '/analyses').json()[0]['review']['effective_state'] == 'changes_requested'


@pytest.mark.parametrize('mutation', ['real_demo', 'same_reviewer', 'operator_reviewer', 'revision', 'version', 'extra', 'bool_revision'])
def test_invalid_registration_is_rejected_without_calls(workbench, monkeypatch, mutation):
    app, client, *_ = workbench
    _, endpoint, _, body, calls = register(workbench, monkeypatch)
    body['request_id'] = uuid4().hex
    if mutation == 'real_demo':
        body['sample_kind'] = 'real'
    elif mutation == 'same_reviewer':
        body['reviewer_ids'][1] = body['reviewer_ids'][0]
    elif mutation == 'operator_reviewer':
        with app.state.store.session() as session:
            body['reviewer_ids'][0] = session.scalar(select(User).where(User.username == 'demo')).id
    elif mutation == 'revision':
        body['expected_revision'] += 1
    elif mutation == 'version':
        body['version_id'] = 'SYNTHETIC-unknown-version'
    elif mutation == 'extra':
        body['external_provider'] = 'unapproved'
    else:
        body['expected_revision'] = True
    assert client.post(endpoint, json=body).status_code in {404, 409, 422} and not calls


@pytest.mark.parametrize('mutation', ['nonce', 'arm_mode', 'protocol_digest', 'feedback'])
def test_frozen_arm_cannot_be_forged_or_repeated_under_new_nonce(workbench, monkeypatch, mutation):
    _, client, base, *_ = workbench
    record, _, view, _, calls = register(workbench, monkeypatch)
    plan = view['protocol']
    spec = plan['arms']['single_pass']
    body = {'expected_revision': record['revision'], 'version_id': record['latest_version_id'],
            'request_id': spec['request_id'], 'mode': spec['mode'],
            'comparison_ref': {'id': view['id'], 'protocol_sha256': plan['protocol_sha256'], 'arm': 'single_pass'}}
    if mutation == 'nonce':
        body['request_id'] = uuid4().hex
    elif mutation == 'arm_mode':
        body['mode'] = 'repair'
    elif mutation == 'protocol_digest':
        body['comparison_ref']['protocol_sha256'] = 'b' * 64
    else:
        body['review_feedback'] = {'review_id': plan['source_review_id'], 'finding_indices': [0]}
    endpoint = base + '/analyses/' + record['id'] + '/suggestions'
    assert client.post(endpoint, json=body).status_code == 409 and not calls


@pytest.mark.parametrize('dependency', ['source_review', 'fact', 'provider', 'recipe', 'reviewer', 'protocol'])
def test_changed_dependencies_stale_capture_and_block_calls_or_annotations(workbench, monkeypatch, dependency):
    app, client, base, _, fact, *_ = workbench
    _, endpoint, view, _, calls = register(workbench, monkeypatch)
    if dependency == 'source_review':
        with app.state.store.session() as session:
            row = session.get(Record, view['protocol']['source_review_id'])
            data = app.state.store.decode(row)
            data['findings'][0]['text'] += ' SYNTHETIC substituted'
            app.state.store.update(row, data)
            session.commit()
    elif dependency == 'fact':
        assert client.patch(base + '/facts/' + fact['id'], json={
            'text': 'SYNTHETIC changed fact', 'status': 'alleged', 'reason': 'SYNTHETIC correction'}).status_code == 200
    elif dependency == 'provider':
        app.state.settings.provider_model = 'SYNTHETIC-other-model'
    elif dependency == 'recipe':
        monkeypatch.setattr(comparisons, 'RECIPE', 'SYNTHETIC changed comparison recipe')
    elif dependency == 'reviewer':
        with app.state.store.session() as session:
            session.delete(session.get(Membership, (base.rsplit('/', 1)[1], view['protocol']['reviewer_ids'][0])))
            session.commit()
    else:
        with app.state.store.session() as session:
            row = session.get(Record, view['id'])
            data = app.state.store.decode(row)
            data['rubric_text'] += ' SYNTHETIC replaced'
            app.state.store.update(row, data)
            session.commit()
    result = client.get(endpoint + '/' + view['id'])
    if dependency == 'protocol':
        assert result.status_code == 409
    else:
        assert result.status_code == 200 and result.json()['freshness']['status'] == 'stale'
        assert not result.json()['can_run'] and not result.json()['capture_complete']
    assert client.post(endpoint + '/' + view['id'] + '/run').status_code == 409 and not calls


def test_partial_admission_retained_and_retry_only_starts_missing_arm(workbench, monkeypatch):
    app, client, *_ = workbench
    _, endpoint, view, _, calls = register(workbench, monkeypatch)
    reserve = app.state.research_jobs.reserve
    count = 0

    def admission():
        nonlocal count
        count += 1
        if count == 2:
            raise QueueUnavailable()
        return reserve()

    monkeypatch.setattr(app.state.research_jobs, 'reserve', admission)
    assert client.post(endpoint + '/' + view['id'] + '/run').status_code == 429
    partial = client.get(endpoint + '/' + view['id']).json()
    ident = partial['arms']['single_pass']['job']['id']
    assert partial['arms']['bounded_correction']['status'] == 'not_started' and not partial['capture_complete']
    complete = run(client, endpoint, view)
    assert complete['arms']['single_pass']['job']['id'] == ident and len(calls) == 3


def test_cancelled_pair_is_not_silently_retried_and_failed_cost_stays_unknown(workbench, monkeypatch):
    _, client, base, *_ = workbench
    entered, release = Event(), Event()

    def blocked(_content, _options):
        entered.set()
        assert release.wait(5)
        return json.dumps(patch())

    record, endpoint, view, _, calls = register(workbench, monkeypatch, mock=blocked)
    try:
        result = client.post(endpoint + '/' + view['id'] + '/run')
        assert result.status_code == 202 and entered.wait(5)
        context = client.get(endpoint + '/' + view['id']).json()
        for item in context['arms'].values():
            assert client.post(base + '/analyses/' + record['id'] + '/suggestions/' + item['job']['id'] + '/cancel').status_code == 200
    finally:
        release.set()
    done = completed(client, endpoint, view['id'])
    assert all(item['status'] == 'cancelled' and item['provider_round_trip_seconds'] is None for item in done['arms'].values())
    call_count = len(calls)
    assert 1 <= call_count <= 2
    assert client.post(endpoint + '/' + view['id'] + '/run').status_code == 202 and len(calls) == call_count
    assert not done['can_run'] and not done['capture_complete']


@pytest.mark.parametrize('missing', ['preparation_seconds', 'verification_seconds', 'correction_seconds', 'shared_setup_included'])
def test_missing_or_unaccounted_effort_does_not_mean_zero_or_complete(workbench, monkeypatch, missing):
    _, client, *_ = workbench
    _, endpoint, registered, _, _ = register(workbench, monkeypatch)
    view = run(client, endpoint, registered)
    body = effort(view)
    if missing == 'shared_setup_included':
        body[missing] = False
    else:
        body['arms'][0][missing] = None
    result = client.post(endpoint + '/' + view['id'] + '/effort', json=body)
    assert result.status_code == 201, result.text
    current = client.get(endpoint + '/' + view['id']).json()
    assert not current['effort_accounted'] and not current['capture_complete']


def test_comparison_is_authorized_before_private_joins(workbench, monkeypatch):
    app, client, base, *_ = workbench
    record, endpoint, view, _, _ = register(workbench, monkeypatch)
    other = client.post('/api/v1/matters', json={'title': 'SYNTHETIC unrelated', 'domain': 'contracts'}).json()['id']
    foreign = f'/api/v1/matters/{other}/analyses/{record["id"]}/comparisons'
    assert client.get(foreign + '/' + view['id']).status_code == 404
    assert client.post(foreign + '/' + view['id'] + '/run').status_code == 404
    with app.state.store.session() as session:
        owner = session.scalar(select(User).where(User.username == 'demo'))
        session.delete(session.get(Membership, (base.rsplit('/', 1)[1], owner.id)))
        session.commit()
    assert client.get(endpoint + '/' + view['id']).status_code == 404
    assert client.post(endpoint + '/' + view['id'] + '/run').status_code == 404


@pytest.mark.parametrize('dependency', ['provider', 'source_review'])
def test_registration_preview_cannot_silently_bind_changed_context(workbench, monkeypatch, dependency):
    app, client, *_ = workbench
    _, endpoint, view, body, calls = register(workbench, monkeypatch)
    body['request_id'] = uuid4().hex
    if dependency == 'provider':
        app.state.settings.provider_model = 'SYNTHETIC changed after preview'
    else:
        with app.state.store.session() as session:
            row = session.get(Record, view['protocol']['source_review_id'])
            data = app.state.store.decode(row)
            data['findings'][0]['text'] += ' SYNTHETIC changed after preview'
            app.state.store.update(row, data)
            session.commit()
    assert client.post(endpoint, json=body).status_code == 409 and not calls
    assert len(client.get(endpoint).json()) == 1


@pytest.mark.parametrize('damage', ['missing_finish', 'before_registration', 'backwards', 'empty_passes', 'negative_provider_time'])
def test_missing_or_inconsistent_execution_evidence_never_completes_capture(workbench, monkeypatch, damage):
    app, client, *_ = workbench
    _, endpoint, registered, _, calls = register(workbench, monkeypatch)
    view = run(client, endpoint, registered)
    with app.state.store.session() as session:
        row = session.get(Record, view['arms']['single_pass']['job']['id'])
        data = app.state.store.decode(row)
        if damage == 'missing_finish':
            data['finished_at'] = None
        elif damage == 'before_registration':
            row.created_at = '1920-01-01T00:00:00+00:00'
        elif damage == 'backwards':
            data['finished_at'] = '1920-01-01T00:00:00+00:00'
        elif damage == 'empty_passes':
            data['iterations'] = []
        else:
            data['iterations'][0]['provider_seconds'] = -1
        app.state.store.update(row, data)
        session.commit()
    current = client.get(endpoint + '/' + view['id']).json()
    assert current['freshness']['status'] == 'stale' and not current['capture_complete']
    assert not current['can_record_effort'] and not current['can_observe'] and len(calls) == 3


@pytest.mark.parametrize('damage', ['execution', 'comparison', 'head', 'boolean_time'])
def test_observation_is_bound_to_exact_completed_pair_and_own_head(workbench, monkeypatch, damage):
    _, client, *_ = workbench
    _, endpoint, registered, _, _ = register(workbench, monkeypatch)
    view = run(client, endpoint, registered)
    login(client, 'SYNTHETIC-reviewer-0')
    detail = endpoint + '/' + view['id']
    body = observation(client.get(detail).json())
    if damage == 'execution':
        body['execution_sha256'] = 'b' * 64
    elif damage == 'comparison':
        body['arms'][0]['assessment']['comparison_sha256'] = 'b' * 64
    elif damage == 'head':
        body['expected_previous_id'] = 'SYNTHETIC foreign head'
    else:
        body['arms'][0]['assessment']['review_seconds'] = True
    assert client.post(detail + '/observations', json=body).status_code in {409, 422}
    assert client.get(detail).json()['observations'] == []


def test_final_guard_rolls_back_annotation_and_audit_when_basis_changes(workbench, monkeypatch):
    from app.db import Audit

    app, client, *_ = workbench
    _, endpoint, registered, _, _ = register(workbench, monkeypatch)
    view = run(client, endpoint, registered)
    audit = comparisons._audit

    def changed(*args, **kwargs):
        audit(*args, **kwargs)
        app.state.settings.provider_model = 'SYNTHETIC changed during effort commit'

    monkeypatch.setattr(comparisons, '_audit', changed)
    result = client.post(endpoint + '/' + view['id'] + '/effort', json=effort(view))
    assert result.status_code == 409, result.text
    assert client.get(endpoint + '/' + view['id']).json()['effort_history'] == []
    with app.state.store.session() as session:
        assert not session.scalars(select(Audit).where(Audit.action == 'analysis_comparison_effort')).all()


def test_bounded_history_and_export_reject_new_writes_without_losing_prior_records(workbench, monkeypatch):
    _, client, *_ = workbench
    _, endpoint, registered, _, _ = register(workbench, monkeypatch)
    view = run(client, endpoint, registered)
    detail = endpoint + '/' + view['id']
    monkeypatch.setattr(comparisons, 'CAPTURE_BYTES', 1)
    assert client.post(detail + '/effort', json=effort(view)).status_code == 409
    monkeypatch.setattr(comparisons, 'CAPTURE_BYTES', 8 * 1024 * 1024)
    assert client.get(detail).json()['effort_history'] == []
    monkeypatch.setattr(comparisons, 'MAX_EVENTS', 1)
    body = effort(view)
    first = client.post(detail + '/effort', json=body)
    assert first.status_code == 201, first.text
    assert client.post(detail + '/effort', json=body).json()['id'] == first.json()['id']
    view = client.get(detail).json()
    assert client.post(detail + '/effort', json=effort(view)).status_code == 409
    assert [item['id'] for item in client.get(detail).json()['effort_history']] == [first.json()['id']]
    assert client.post(detail + '/run', json={'mode': 'repair', 'budget_seconds': 1800}).status_code == 422


def test_selected_feedback_identical_for_both_arms_and_not_mixed_with_rubric(workbench, monkeypatch):
    _, client, *_ = workbench
    _, endpoint, registered, _, calls = register(workbench, monkeypatch, feedback=True)
    view = run(client, endpoint, registered)
    assert len(calls) == 3, {key: (item['status'], item['job'].get('error')) for key, item in view['arms'].items()}
    feedback = view['protocol']['review_feedback']
    assert all(item[1]['review_feedback'] == feedback for item in calls)
    assert all('rubric_text' not in item[0] and 'reviewer_ids' not in item[0] for item in calls)
    assert all(item['job']['review_feedback_sha256'] == view['protocol']['review_feedback_sha256'] for item in view['arms'].values())


def test_download_is_current_bounded_private_attachment_without_model_calls(workbench, monkeypatch):
    app, client, base, _, fact, *_ = workbench
    record, endpoint, registered, _, calls = register(workbench, monkeypatch)
    view = run(client, endpoint, registered)
    url = endpoint + '/' + view['id'] + '/export'
    response = client.get(url)
    assert response.status_code == 200 and response.json()['execution_sha256'] == view['execution_sha256']
    assert response.headers['content-disposition'] == f'attachment; filename="private-comparison-{view["id"]}.json"'
    assert response.headers['cache-control'] == 'no-store' and response.headers['x-content-type-options'] == 'nosniff'
    assert len(response.content) <= comparisons.CAPTURE_BYTES and len(calls) == 3
    assert client.patch(base + '/facts/' + fact['id'], json={
        'text': 'SYNTHETIC changed fact after view', 'status': 'alleged', 'reason': 'SYNTHETIC correction'}).status_code == 200
    stale = client.get(url)
    assert stale.status_code == 200 and stale.json()['freshness']['status'] == 'stale'
    assert not stale.json()['capture_complete'] and not stale.json()['qualification_granted']
    monkeypatch.setattr(comparisons, 'CAPTURE_BYTES', 1)
    assert client.get(url).status_code == 409 and len(calls) == 3
    other = client.post('/api/v1/matters', json={'title': 'SYNTHETIC unrelated', 'domain': 'contracts'}).json()['id']
    foreign = f'/api/v1/matters/{other}/analyses/{record["id"]}/comparisons/{view["id"]}/export'
    assert client.get(foreign).status_code == 404
    assert client.post('/api/v1/auth/logout').status_code == 200
    assert client.get(url).status_code == 401
