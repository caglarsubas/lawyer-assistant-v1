"""Bounded real PostgreSQL work-version and response-admission races."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_firm_admin import PASSWORD, login
from test_human_workflow import create, edit_body, path
from test_research_jobs_postgres import postgres_database as database_fixture
from test_research_jobs_postgres import workspace as workspace_fixture
from test_snapshot_set_postgres import observe_identity_lock, wait_until_blocked

from app import human_workflow
from app.auth import hash_password
from app.db import CaseResponsibility, Membership, Record, User


@pytest.fixture
def postgres_database():
    yield from database_fixture.__wrapped__()


@pytest.fixture
def workspace(postgres_database, tmp_path):
    yield from workspace_fixture.__wrapped__(postgres_database, tmp_path)


def test_competing_opinion_reviews_preserve_one_decision_and_revision(workspace, monkeypatch):
    app, client, case = workspace
    admin = client.get('/api/v1/auth/me').json()['user']['id']
    with app.state.store.session() as session:
        session.add(CaseResponsibility(matter_id=case, user_id=admin, firm_id='demo-firm', supervisor=True))
        peer = User(username='synthetic-reviewee', name='Synthetic reviewee', firm_id='demo-firm', role='lawyer', password_hash=hash_password(PASSWORD))
        session.add(peer)
        session.flush()
        peer_id = peer.id
        session.add(Membership(matter_id=case, user_id=peer_id))
        session.commit()
    item = create(client, case, [peer_id])
    login(client, 'synthetic-reviewee', PASSWORD)
    submission = client.post(path(case, item) + '/submissions', json={'revision': 1, 'text': 'Synthetic independent opinion'})
    assert submission.status_code == 200
    own = submission.json()['responses'][0]
    login(client)
    entered, release = Event(), Event()
    audit = human_workflow._audit

    def pause(*args):
        if args[-1] == 'human_opinion_reviewed' and not entered.is_set():
            entered.set()
            assert release.wait(10)
        return audit(*args)

    monkeypatch.setattr(human_workflow, '_audit', pause)
    payload = {'revision': own['revision'], 'submission_id': own['history'][0]['id'], 'decision': 'accepted', 'note': 'Synthetic independent review'}
    endpoint = path(case, item) + f'/responses/{peer_id}/review'
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(client.post, endpoint, json=payload)
        try:
            assert entered.wait(5)
            with observe_identity_lock(app.state.store.engine, statement_fragment='FOR UPDATE') as observed:
                second = pool.submit(client.post, endpoint, json=payload)
                assert observed[0].wait(5)
                assert wait_until_blocked(app.state.store.engine, observed[1][-1])
                assert not second.done()
        finally:
            release.set()
        assert first.result(timeout=10).status_code == 200
        assert second.result(timeout=10).status_code == 409
    current = client.get(path(case, item)).json()['responses'][0]
    assert current['revision'] == 3 and len(current['history']) == 2 and current['status'] == 'accepted'


def test_competing_independent_source_reviews_serialize_exact_head(workspace, monkeypatch):
    from uuid import uuid4

    from test_analysis_workbench import build_workbench
    from test_authority_adjudications import reviewer
    from test_source_analysis_reviews import freeze, review_request, setup

    from app import source_analysis_reviews

    workbench = build_workbench(workspace)
    app, client, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    reviewer(workbench)
    review_path, body = review_request(client, endpoint, context['id'])
    entered, release = Event(), Event()
    audit = source_analysis_reviews._audit

    def pause(*args):
        if args[2] == 'source_analysis_review_recorded' and not entered.is_set():
            entered.set()
            assert release.wait(10)
        return audit(*args)

    monkeypatch.setattr(source_analysis_reviews, '_audit', pause)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(client.post, review_path, json=body)
        try:
            assert entered.wait(5)
            with observe_identity_lock(app.state.store.engine, statement_fragment='FOR UPDATE') as observed:
                second = pool.submit(client.post, review_path, json={**body, 'request_id': uuid4().hex})
                assert observed[0].wait(5)
                assert wait_until_blocked(app.state.store.engine, observed[1][-1])
                assert not second.done()
        finally:
            release.set()
        assert first.result(timeout=10).status_code == 201
        assert second.result(timeout=10).status_code == 409
    assert len(client.get(review_path).json()) == 1
    current = client.get(endpoint + '/' + context['id']).json()
    assert current['review']['snapshot']['sequence'] == 1


def test_source_renewal_waits_for_parent_review_and_rejects_changed_parent_head(workspace, monkeypatch):
    from uuid import uuid4

    from test_analysis_workbench import build_workbench
    from test_authority_adjudications import reviewer
    from test_source_analysis_reviews import freeze, review_request, setup
    from test_source_context_renewals import renewal_spec

    from app import source_analysis_reviews

    workbench = build_workbench(workspace)
    app, client, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    parent, _ = freeze(client, endpoint, spec)
    renewal, _ = renewal_spec(client, endpoint, spec, parent['id'])
    preview = client.post(endpoint + '/preview', json=renewal).json()
    reviewer(workbench)
    review_path, body = review_request(client, endpoint, parent['id'])
    entered, release = Event(), Event()
    audit = source_analysis_reviews._audit

    def pause(*args):
        if args[2] == 'source_analysis_review_recorded' and not entered.is_set():
            entered.set()
            assert release.wait(10)
        return audit(*args)

    monkeypatch.setattr(source_analysis_reviews, '_audit', pause)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(client.post, review_path, json=body)
        try:
            assert entered.wait(5)
            with observe_identity_lock(app.state.store.engine, statement_fragment='FOR UPDATE') as observed:
                second = pool.submit(client.post, endpoint, json={**renewal,
                    'expected_preview_sha256': preview['preview_sha256'], 'request_id': uuid4().hex})
                assert observed[0].wait(5)
                assert wait_until_blocked(app.state.store.engine, observed[1][-1])
                assert not second.done()
        finally:
            release.set()
        assert first.result(timeout=10).status_code == 201
        assert second.result(timeout=10).status_code == 409
    assert len(client.get(endpoint).json()) == 1


def test_recipient_removal_waits_for_admitted_opinion_body_with_case_scope_retained(workspace, monkeypatch):
    app, client, case = workspace
    admin = client.get('/api/v1/auth/me').json()['user']['id']
    with app.state.store.session() as session:
        peer = User(username='synthetic-peer', name='Synthetic peer', firm_id='demo-firm', role='lawyer', password_hash=hash_password(PASSWORD))
        session.add(peer)
        session.flush()
        peer_id = peer.id
        session.add(Membership(matter_id=case, user_id=peer_id))
        session.add(CaseResponsibility(matter_id=case, user_id=admin, firm_id='demo-firm', supervisor=True))
        session.commit()
    item = create(client, case, [peer_id])
    other = TestClient(app)
    entered, release = Event(), Event()
    original = human_workflow._view

    def pause(*args, **kwargs):
        value = original(*args, **kwargs)
        if kwargs.get('detail') and args[3].id == peer_id and not entered.is_set():
            entered.set()
            assert release.wait(10)
        return value

    try:
        login(other, 'synthetic-peer', PASSWORD)
        monkeypatch.setattr(human_workflow, '_view', pause)
        edit_path = path(case, item)
        with ThreadPoolExecutor(2) as pool:
            active = pool.submit(other.get, path(case, item))
            assert entered.wait(5)
            with observe_identity_lock(app.state.store.engine, statement_fragment='SELECT pg_advisory_lock(') as observed:
                future = pool.submit(client.put, edit_path, json=edit_body(item, assignee_ids=[admin]))
                try:
                    assert observed[0].wait(5)
                    assert wait_until_blocked(app.state.store.engine, observed[1][-1])
                    assert not future.done()
                finally:
                    release.set()
                assert active.result(timeout=10).status_code == 200
                assert future.result(timeout=10).status_code == 200
        assert other.get('/api/v1/auth/me').status_code == 401
        login(other, 'synthetic-peer', PASSWORD)
        assert other.get('/api/v1/work').json()['items'] == []
        assert other.get(path(case, item)).status_code == 404
        assert other.get('/api/v1/matters/' + case).status_code == 200
        with app.state.store.session() as session:
            assert session.scalar(select(Record).where(Record.id == item['id']))
    finally:
        other.close()


@pytest.mark.parametrize("observation", ["readiness", "navigation", "lineage"])
def test_source_readiness_waits_for_independent_review_and_observes_exact_new_head(workspace, monkeypatch, observation):
    from test_analysis_workbench import build_workbench
    from test_authority_adjudications import reviewer
    from test_source_analysis_reviews import freeze, record, review_request, setup

    from app import source_analysis_reviews

    workbench = build_workbench(workspace)
    app, client, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    reviewer(workbench)
    selected_review = None
    if observation == 'lineage':
        initial_path, initial_body = review_request(client, endpoint, context['id'])
        selected_review = record(client, initial_path, initial_body)['review']['id']
    review_path, body = review_request(client, endpoint, context['id'])
    entered, release = Event(), Event()
    audit = source_analysis_reviews._audit

    def pause(*args):
        if args[2] == 'source_analysis_review_recorded' and not entered.is_set():
            entered.set()
            assert release.wait(10)
        return audit(*args)

    monkeypatch.setattr(source_analysis_reviews, '_audit', pause)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(client.post, review_path, json=body)
        try:
            assert entered.wait(5)
            with observe_identity_lock(app.state.store.engine, statement_fragment='FOR UPDATE') as observed:
                route = '/readiness' if observation == 'readiness' else '/' + context['id'] + (
                    '/reviews/' + selected_review + '/navigation-context' if observation == 'lineage' else '/navigation-context')
                second = pool.submit(client.get, endpoint + route)
                assert observed[0].wait(5)
                assert wait_until_blocked(app.state.store.engine, observed[1][-1])
                assert not second.done()
        finally:
            release.set()
        saved = first.result(timeout=10)
        observed = second.result(timeout=10)
        assert saved.status_code == 201 and observed.status_code == 200
    item = observed.json()['items'][0] if observation == 'readiness' else observed.json()
    if observation == 'lineage':
        assert item['selected_review']['id'] == selected_review
        assert item['current_head']['id'] == saved.json()['review']['id']
        assert item['head_relationship'] == 'different_from_head'
        assert item['source_verification'] == 'not_checked' and 'PRIVATE REVIEW NOTE' not in observed.text
        return
    assert item['historical_review']['id'] == saved.json()['review']['id']
    assert item['historical_review']['state'] == 'reviewed_conditional'
    assert item['source_verification'] == 'not_checked' and item['legal_readiness'] == 'not_established'
    if observation == 'readiness':
        assert item['state'] in {'pending', 'inspection_required'}
    else:
        assert item['context_id'] == context['id'] and item['version_relation'] == 'same'
        assert 'PRIVATE REVIEW NOTE' not in observed.text


def test_source_readiness_holds_private_basis_until_concurrent_version_edit_finishes(workspace, monkeypatch):
    import copy

    from test_analysis_workbench import build_workbench
    from test_source_analysis_reviews import freeze, setup

    from app import source_review_readiness

    workbench = build_workbench(workspace)
    app, client, base, payload, *_ = workbench
    endpoint, spec, analysis, *_ = setup(workbench, monkeypatch)
    frozen, _ = freeze(client, endpoint, spec)
    entered, release = Event(), Event()
    original = source_review_readiness._item

    def pause(*args):
        value = original(*args)
        if not entered.is_set():
            entered.set()
            assert release.wait(10)
        return value

    monkeypatch.setattr(source_review_readiness, '_item', pause)
    changed = copy.deepcopy(payload)
    changed['rules'][0]['text'] = 'TEST ONLY later private version'
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(client.get, endpoint + '/readiness')
        try:
            assert entered.wait(5)
            with observe_identity_lock(app.state.store.engine, statement_fragment='FOR UPDATE') as observed:
                second = pool.submit(client.post, base + '/analyses/' + analysis['id'] + '/versions',
                    json={**changed, 'expected_revision': analysis['revision'], 'change_note': 'TEST ONLY concurrent private change'})
                assert observed[0].wait(5)
                assert wait_until_blocked(app.state.store.engine, observed[1][-1])
                assert not second.done()
        finally:
            release.set()
        observation = first.result(timeout=10)
        saved = second.result(timeout=10)
        assert observation.status_code == 200 and saved.status_code == 201
    assert observation.json()['items'][0]['state'] == 'awaiting_review'
    after = client.get(endpoint + '/readiness').json()['items'][0]
    assert after['id'] == frozen['id'] and after['state'] == 'needs_renewal'
    assert 'analysis_version_changed' in after['private_observation']['reasons']


def test_portfolio_source_queue_opposite_windows_wait_without_matter_lock_deadlock(workspace, monkeypatch):
    from test_analysis_workbench import build_workbench
    from test_portfolio_source_reviews import ENDPOINT, other_case
    from test_source_analysis_reviews import freeze, setup

    from app import portfolio_source_reviews

    bench = build_workbench(workspace)
    app, client, *_ = bench
    endpoint, spec, *_ = setup(bench, monkeypatch)
    first, _ = freeze(client, endpoint, spec)
    other, _, _, _, _, _, second = other_case(bench, monkeypatch)
    third, _ = freeze(client, endpoint, spec)
    entered, release = Event(), Event()
    original = portfolio_source_reviews._route

    def pause(*args):
        result = original(*args)
        if not entered.is_set():
            entered.set()
            assert release.wait(10)
        return result

    monkeypatch.setattr(portfolio_source_reviews, '_route', pause)
    with ThreadPoolExecutor(2) as pool:
        forward = pool.submit(client.get, ENDPOINT, params={'window': 2})
        try:
            assert entered.wait(5)
            with observe_identity_lock(app.state.store.engine, statement_fragment='FOR UPDATE') as observed:
                reverse = pool.submit(client.get, ENDPOINT, params={'window': 2, 'offset': 1})
                assert observed[0].wait(5)
                assert wait_until_blocked(app.state.store.engine, observed[1][-1])
                assert not reverse.done()
        finally:
            release.set()
        a, b = forward.result(timeout=10), reverse.result(timeout=10)
    assert a.status_code == b.status_code == 200, (a.text, b.text)
    assert a.json()['coverage']['locked_matter_count'] == b.json()['coverage']['locked_matter_count'] == 2
    assert {item['id'] for item in a.json()['items']} == {third['id'], second['id']}
    assert {item['id'] for item in b.json()['items']} == {second['id'], first['id']}
    assert {item['matter_id'] for item in a.json()['items']} == {workspace[2], other}


def test_portfolio_source_queue_new_unlocked_matter_record_requires_fresh_window(workspace, monkeypatch):
    from test_analysis_workbench import build_workbench
    from test_portfolio_source_reviews import ENDPOINT, other_case
    from test_source_analysis_reviews import freeze, setup

    from app import portfolio_source_reviews

    bench = build_workbench(workspace)
    app, client, *_ = bench
    endpoint, spec, *_ = setup(bench, monkeypatch)
    freeze(client, endpoint, spec)
    _, _, other_endpoint, other_spec, _, _, _ = other_case(bench, monkeypatch)
    freeze(client, endpoint, spec)  # Current window locks only the first matter.
    entered, release = Event(), Event()
    original = portfolio_source_reviews._route

    def pause(*args):
        result = original(*args)
        entered.set()
        assert release.wait(10)
        return result

    monkeypatch.setattr(portfolio_source_reviews, '_route', pause)
    with ThreadPoolExecutor(2) as pool:
        capture = pool.submit(client.get, ENDPOINT, params={'window': 1})
        try:
            assert entered.wait(5)
            added = freeze(client, other_endpoint, other_spec)[0]
        finally:
            release.set()
        response = capture.result(timeout=10)
    assert response.status_code == 409 and 'items' not in response.json()
    assert 'TEST ONLY' not in response.text
    monkeypatch.setattr(portfolio_source_reviews, '_route', original)
    latest = client.get(ENDPOINT, params={'window': 1}).json()
    assert latest['items'][0]['id'] == added['id']


def test_renewal_reconciliation_serializes_with_private_version_edit_without_replaying(workspace, monkeypatch):
    import copy

    from test_analysis_workbench import build_workbench
    from test_source_analysis_reviews import freeze, setup
    from test_source_context_renewals import reconciliation_receipt, renewal_spec

    from app import source_context_renewals

    workbench = build_workbench(workspace)
    app, client, base, payload, *_ = workbench
    endpoint, spec, analysis, *_ = setup(workbench, monkeypatch)
    parent, _ = freeze(client, endpoint, spec)
    value, _ = renewal_spec(client, endpoint, spec, parent['id'])
    child, sent = freeze(client, endpoint, value)
    receipt = reconciliation_receipt(sent, parent)
    entered, release = Event(), Event()
    original = source_context_renewals.comparison_from_parent

    def pause(*args):
        result = original(*args)
        if not entered.is_set():
            entered.set()
            assert release.wait(10)
        return result

    monkeypatch.setattr(source_context_renewals, 'comparison_from_parent', pause)
    changed = copy.deepcopy(payload)
    changed['rules'][0]['text'] = 'TEST ONLY concurrent new private version'
    body = {**changed, 'expected_revision': analysis['revision'], 'change_note': 'TEST ONLY explicit edit'}
    with ThreadPoolExecutor(2) as pool:
        reading = pool.submit(client.get, endpoint + '/renewal-reconciliation', params=receipt)
        try:
            assert entered.wait(5)
            with observe_identity_lock(app.state.store.engine, statement_fragment='FOR UPDATE') as observed:
                writing = pool.submit(client.post, base + '/analyses/' + analysis['id'] + '/versions', json=body)
                assert observed[0].wait(5)
                assert wait_until_blocked(app.state.store.engine, observed[1][-1])
                assert not writing.done()
        finally:
            release.set()
        observed = reading.result(timeout=10)
        edited = writing.result(timeout=10)
        assert observed.status_code == 200 and edited.status_code == 201
    result = observed.json()
    assert result['outcome'] == 'verified' and result['successor']['id'] == child['id']
    assert result['successor']['version_id'] == spec['version_id']
    assert edited.json()['latest_version_id'] != result['successor']['version_id']
    assert result['source_verification'] == 'not_checked' and not result['effects_replayed']
    assert len(client.get(endpoint).json()) == 2


def test_review_reconciliation_serializes_with_later_opposing_review_without_head_substitution(workspace, monkeypatch):
    from test_analysis_workbench import build_workbench
    from test_authority_adjudications import reviewer
    from test_source_analysis_reviews import freeze, record, review_request, setup
    from test_source_review_lineage import review_receipt

    from app import source_analysis_reviews

    workbench = build_workbench(workspace)
    app, client, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    reviewer(workbench)
    path, sent = review_request(client, endpoint, context['id'])
    selected = record(client, path, sent)
    receipt = review_receipt(sent, context)
    _, opposing = review_request(client, endpoint, context['id'], decision='changes_requested')
    entered, release = Event(), Event()
    original = source_analysis_reviews._validate_review

    def pause(*args):
        result = original(*args)
        if not entered.is_set():
            entered.set()
            assert release.wait(10)
        return result

    monkeypatch.setattr(source_analysis_reviews, '_validate_review', pause)
    target = path + '/reconciliation'
    with ThreadPoolExecutor(2) as pool:
        reading = pool.submit(client.get, target, params=receipt)
        try:
            assert entered.wait(5)
            with observe_identity_lock(app.state.store.engine, statement_fragment='FOR UPDATE') as observed:
                writing = pool.submit(client.post, path, json=opposing)
                assert observed[0].wait(5)
                assert wait_until_blocked(app.state.store.engine, observed[1][-1])
                assert not writing.done()
        finally:
            release.set()
        result = reading.result(timeout=10)
        later = writing.result(timeout=10)
    assert result.status_code == 200 and later.status_code == 201
    first = result.json()
    again = client.get(target, params=receipt).json()
    assert first['outcome'] == again['outcome'] == 'verified'
    assert first['review'] == again['review'] and first['review']['id'] == selected['review']['id']
    assert first['review']['id'] != later.json()['review']['id']
    assert first['current_head'] == again['current_head'] == 'not_checked'
    assert not again['effects_replayed']
