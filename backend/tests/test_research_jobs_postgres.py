"""Observe real row-lock ordering using only randomly named disposable databases."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient
from test_research_jobs import products, seed_run, state, wait_for
from test_snapshot_set_postgres import (
    observe_identity_lock,
    wait_until_blocked,
)
from test_snapshot_set_postgres import postgres_database as database_fixture

from app import analysis_reviews, analysis_suggestions, analysis_workbench
from app.config import Settings
from app.db import Record, User, digest
from app.main import create_app
from app.research import publish_product
from app.research_jobs import JobStopped, coordinator_lease, finish_run, request_stop


@pytest.fixture
def postgres_database():
    yield from database_fixture.__wrapped__()


@pytest.fixture
def workspace(postgres_database, tmp_path):
    app = create_app(Settings.model_construct(
        demo_mode=True, cookie_secure=False, data_dir=tmp_path,
        public_source_dir=tmp_path / 'public-only',
        database_url=postgres_database.render_as_string(hide_password=False)))
    with TestClient(app) as client:
        login = client.post('/api/v1/auth/login', json={'username': 'demo', 'password': 'demo-local-only'})
        assert login.status_code == 200
        client.headers['X-CSRF-Token'] = login.json()['csrf_token']
        yield app, client, client.get('/api/v1/matters').json()[0]['id']


def publish(app, matter, ident):
    with app.state.store.session() as session:
        revision = session.get(Record, matter).revision
    # Graph authorization has independent end-to-end tests. This slice exercises
    # the actual private publication transaction with a clearly synthetic product.
    return publish_product(app, ident, {'status': 'needs_review', 'title': 'SYNTHETIC'}, revision)


def test_analysis_revision_conflicts_preserve_one_immutable_history(workspace, monkeypatch):
    app, client, matter = workspace
    endpoint = f'/api/v1/matters/{matter}/analyses'
    payload = {'title': 'SYNTHETIC incomplete draft', 'issue': 'SYNTHETIC unresolved issue',
               'conclusion': {'text': 'SYNTHETIC provisional text', 'next_step': 'Collect evidence'}}
    created = client.post(endpoint, json=payload)
    assert created.status_code == 201, created.text
    original = created.json()
    versions = endpoint + '/' + original['id'] + '/versions'
    locked, release = Event(), Event()
    write = analysis_workbench._write_version

    def paused(*args, **kwargs):
        body = args[4]
        if body.change_note == 'SYNTHETIC first revision':
            locked.set()
            assert release.wait(10)
        return write(*args, **kwargs)

    monkeypatch.setattr(analysis_workbench, '_write_version', paused)
    first = {**payload, 'expected_revision': original['revision'], 'change_note': 'SYNTHETIC first revision'}
    second = {**first, 'title': 'SYNTHETIC competing revision', 'change_note': 'SYNTHETIC second revision'}
    with ThreadPoolExecutor(2) as pool:
        accepted = pool.submit(client.post, versions, json=first)
        try:
            assert locked.wait(5)
            with observe_identity_lock(app.state.store.engine, statement_fragment='FOR UPDATE') as observed:
                competing = pool.submit(client.post, versions, json=second)
                assert observed[0].wait(5)
                assert wait_until_blocked(app.state.store.engine, observed[1][-1])
                assert not competing.done()
        finally:
            release.set()
        assert accepted.result(timeout=5).status_code == 201
        assert competing.result(timeout=5).status_code == 409
    history = client.get(versions).json()
    assert [version['version'] for version in history] == [2, 1]
    assert history[1]['id'] == original['latest_version_id']
    assert history[1]['content']['title'] == payload['title']


@pytest.mark.parametrize('replay', [False, True])
def test_review_head_serializes_competing_decisions_and_identical_replays(workspace, monkeypatch, replay):
    from uuid import uuid4

    from sqlalchemy import func, select
    from test_analysis_reviews import review_request

    app, client, matter = workspace
    endpoint = f'/api/v1/matters/{matter}/analyses'
    response = client.post(endpoint, json={
        'title': 'SYNTHETIC review race', 'issue': 'SYNTHETIC incomplete issue',
        'conclusion': {'text': 'SYNTHETIC provisional text', 'next_step': 'Collect evidence'}})
    assert response.status_code == 201, response.text
    record = response.json()
    reviews = endpoint + '/' + record['id'] + '/reviews'
    body, _ = review_request(client, reviews, record)
    body['decision'] = 'changes_requested'
    body['criteria'][0].update(outcome='needs_change', note='SYNTHETIC missing sources')
    competing_body = body if replay else {**body, 'request_id': uuid4().hex}
    locked, release = Event(), Event()
    invalidate = analysis_reviews._invalidate

    def paused(*args, **kwargs):
        locked.set()
        assert release.wait(10)
        return invalidate(*args, **kwargs)

    monkeypatch.setattr(analysis_reviews, '_invalidate', paused)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(client.post, reviews, json=body)
        try:
            assert locked.wait(5)
            with observe_identity_lock(app.state.store.engine, statement_fragment='FOR UPDATE') as observed:
                second = pool.submit(client.post, reviews, json=competing_body)
                assert observed[0].wait(5)
                assert wait_until_blocked(app.state.store.engine, observed[1][-1])
                assert not second.done()
        finally:
            release.set()
        accepted, competing = first.result(timeout=5), second.result(timeout=5)
    assert accepted.status_code == 201, accepted.text
    assert competing.status_code == (201 if replay else 409), competing.text
    if replay:
        assert competing.json()['id'] == accepted.json()['id']
    with app.state.store.session() as session:
        for kind in (analysis_reviews.KIND, analysis_reviews.HEAD_KIND):
            assert session.scalar(select(func.count()).select_from(Record).where(
                Record.kind == kind, Record.matter_id == matter)) == 1
    history = client.get(endpoint + '/' + record['id'] + '/versions').json()
    assert len(history) == 1 and history[0]['id'] == record['latest_version_id']


def test_proposal_adoption_race_appends_exactly_one_immutable_version(workspace, monkeypatch):
    import json

    from sqlalchemy import select
    from test_analysis_suggestions import finished, prepare, start

    app, client, matter = workspace
    base = f'/api/v1/matters/{matter}'
    text = 'SYNTHETIC private clause — payment depends on delivery.'
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        document = app.state.store.add(session, 'document', user, {
            'name': 'SYNTHETIC.txt', 'status': 'extracted', 'sha256': digest(text),
            'passages': [{'id': 'pg-clause', 'text': text, 'locator': 'SYNTHETIC §1'}]}, matter)
        session.commit()
    payload = {'title': 'SYNTHETIC proposal race', 'issue': 'SYNTHETIC delivery issue',
               'evidence': [{'evidence_id': 'pg-clause', 'passage_sha256': digest(text),
                             'document_revision': document.revision, 'start': 0, 'end': len(text)}],
               'premises': [{'id': 'p1', 'kind': 'assumption', 'text': 'SYNTHETIC delivery assumption'}],
               'rules': [{'id': 'r1', 'kind': 'contract_clause', 'text': 'SYNTHETIC payment candidate',
                          'evidence_ids': ['pg-clause'], 'conditions': [{'id': 'c1', 'text': 'SYNTHETIC delivery'}]}],
               'applications': [{'id': 'a1', 'rule_id': 'r1', 'premise_ids': ['p1'],
                                 'rationale': 'SYNTHETIC original', 'assessments': [
                                     {'condition_id': 'c1', 'status': 'unknown', 'premise_ids': ['p1']}]}],
               'alternatives': [{'id': 'alt1', 'kind': 'search_gap', 'text': 'SYNTHETIC adverse gap'}],
               'conclusion': {'text': 'SYNTHETIC provisional', 'application_ids': ['a1'],
                              'alternative_ids': ['alt1'], 'next_step': 'SYNTHETIC inspect source'}}
    record, endpoint = prepare((app, client, base, payload), monkeypatch, incomplete=False)
    monkeypatch.setattr(app.state.provider, 'suggest_analysis', lambda *_a, **_k: json.dumps({
        'application_updates': [{'id': 'a1', 'rationale': 'SYNTHETIC proposed wording'}]}))
    queued, _ = start(client, endpoint, record)
    job = finished(client, endpoint, queued['id'])
    assert job['can_adopt']
    locked, release = Event(), Event()
    write = analysis_suggestions._write_version

    def paused(*args, **kwargs):
        if args[4].change_note == 'SYNTHETIC first adoption':
            locked.set()
            assert release.wait(10)
        return write(*args, **kwargs)

    monkeypatch.setattr(analysis_suggestions, '_write_version', paused)
    body = {'expected_revision': record['revision'], 'candidate_sha256': job['candidate_sha256'],
            'change_note': 'SYNTHETIC first adoption'}
    url = endpoint + '/' + job['id'] + '/adopt'
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(client.post, url, json=body)
        try:
            assert locked.wait(5)
            with observe_identity_lock(app.state.store.engine, statement_fragment='FOR UPDATE') as observed:
                second = pool.submit(client.post, url, json={**body, 'change_note': 'SYNTHETIC competing adoption'})
                assert observed[0].wait(5)
                assert wait_until_blocked(app.state.store.engine, observed[1][-1])
                assert not second.done()
        finally:
            release.set()
        accepted, rejected = first.result(timeout=5), second.result(timeout=5)
    assert accepted.status_code == 201, accepted.text
    assert rejected.status_code == 409, rejected.text
    history = client.get(base + '/analyses/' + record['id'] + '/versions').json()
    assert [item['version'] for item in history] == [2, 1]
    assert history[1]['content']['applications'] == record['applications']
    assert history[0]['content']['authorship'] == 'user_with_ai_assistance'
    assert history[0]['content']['status'] == 'needs_review'


def test_stop_commit_first_blocks_publication(workspace):
    app, _, matter = workspace
    ident = seed_run(app, matter, status='running')
    locked, release = Event(), Event()
    calls = []

    def authorize(session):
        calls.append(True)
        if len(calls) == 2:  # The stop helper has acquired the run row lock.
            locked.set()
            assert release.wait(10)

    with ThreadPoolExecutor(2) as pool:
        stop = pool.submit(request_stop, app.state.store, ident, authorize=authorize)
        try:
            assert locked.wait(5)
            # Publication first locks the matter, then waits on the stop's run lock.
            with observe_identity_lock(app.state.store.engine, statement_fragment='FOR UPDATE') as observed:
                output = pool.submit(publish, app, matter, ident)
                assert observed[0].wait(5)
                # The last observed row lock belongs to the research row, not the matter.
                wait_for(lambda: len(observed[1]) == 2)
                assert wait_until_blocked(app.state.store.engine, observed[1][-1])
                assert not output.done()
        finally:
            release.set()
        assert stop.result(timeout=5)['status'] == 'cancelling'
        with pytest.raises(JobStopped):
            output.result(timeout=5)
    finish_run(app.state.store, ident)
    assert state(app, ident)['status'] == 'cancelled'
    assert products(app, matter) == 0


def test_publication_commit_first_keeps_completed_result(workspace, monkeypatch):
    app, _, matter = workspace
    ident = seed_run(app, matter, status='running')
    locked, release = Event(), Event()
    original = app.state.store.add

    def add(session, kind, *args, **kwargs):
        if kind == 'product':
            locked.set()
            assert release.wait(10)
        return original(session, kind, *args, **kwargs)

    monkeypatch.setattr(app.state.store, 'add', add)
    with ThreadPoolExecutor(2) as pool:
        output = pool.submit(publish, app, matter, ident)
        try:
            assert locked.wait(5)
            with observe_identity_lock(app.state.store.engine, statement_fragment='FOR UPDATE') as observed:
                stop = pool.submit(request_stop, app.state.store, ident)
                assert observed[0].wait(5)
                assert wait_until_blocked(app.state.store.engine, observed[1][0])
                assert not stop.done()
        finally:
            release.set()
        product_id, _ = output.result(timeout=5)
        assert stop.result(timeout=5)['status'] == 'completed'
    assert state(app, ident)['product_id'] == product_id
    assert products(app, matter) == 1


def test_five_publishers_have_distinct_serial_versions(workspace):
    app, _, matter = workspace
    ids = [seed_run(app, matter, status='running') for _ in range(5)]
    ready = Barrier(5)

    def complete(ident):
        ready.wait(timeout=5)
        return publish(app, matter, ident)

    with ThreadPoolExecutor(5) as pool:
        futures = [pool.submit(complete, ident) for ident in ids]
        results = [future.result(timeout=10) for future in futures]
    with app.state.store.session() as session:
        versions = [app.state.store.decode(session.get(Record, ident))['version'] for ident, _ in results]
    assert sorted(versions) == [1, 2, 3, 4, 5]
    assert all(state(app, ident)['status'] == 'completed' for ident in ids)


def test_second_coordinator_cannot_recover_live_jobs(workspace):
    app, _, matter = workspace
    ident = seed_run(app, matter, status='running')
    before = state(app, ident)
    with pytest.raises(RuntimeError, match='coordinator'), coordinator_lease(app.state.store):
        pytest.fail('A second coordinator must not start recovery or admit jobs')
    assert state(app, ident) == before


def test_archive_waits_for_publication_and_hides_committed_result(workspace, monkeypatch):
    app, client, matter = workspace
    ident = seed_run(app, matter, status='running')
    locked, release = Event(), Event()
    original = app.state.store.add
    revision = client.get(f'/api/v1/matters/{matter}').json()['revision']

    def add(session, kind, *args, **kwargs):
        if kind == 'product':
            locked.set()
            assert release.wait(10)
        return original(session, kind, *args, **kwargs)

    monkeypatch.setattr(app.state.store, 'add', add)
    with ThreadPoolExecutor(2) as pool:
        output = pool.submit(publish, app, matter, ident)
        try:
            assert locked.wait(5)
            with observe_identity_lock(app.state.store.engine, statement_fragment='FOR UPDATE') as observed:
                archive = pool.submit(client.post, f'/api/v1/matters/{matter}/archive',
                                      json={'expected_revision': revision, 'reason': 'Synthetic archive race'})
                assert observed[0].wait(5)
                assert wait_until_blocked(app.state.store.engine, observed[1][0])
                assert not archive.done()
        finally:
            release.set()
        product_id, _ = output.result(timeout=5)
        result = archive.result(timeout=5)
        assert result.status_code == 200, result.text
    assert state(app, ident)['status'] == 'completed'
    assert client.get(f'/api/v1/matters/{matter}/products/{product_id}').status_code == 404


def test_lost_database_lease_fails_closed_without_reacquisition(workspace):
    from sqlalchemy import text

    from app.research_jobs import LEASE_KEY, QueueUnavailable

    app, _, matter = workspace
    app.state.research_owner()
    # Terminate only this disposable database's exact coordinator lock owner.
    with app.state.store.engine.connect() as connection:
        pid = connection.scalar(text(
            "SELECT pid FROM pg_locks WHERE locktype = 'advisory' AND database = "
            "(SELECT oid FROM pg_database WHERE datname = current_database()) "
            "AND classid = :upper AND objid = :lower AND objsubid = 1"),
            {"upper": LEASE_KEY >> 32, "lower": LEASE_KEY & 0xffffffff})
        assert pid
        assert connection.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
        connection.commit()
    with pytest.raises(QueueUnavailable), app.state.research_jobs.reserve():
        pass
    # A reconnected session must not silently obtain a new lease or publish.
    ident = seed_run(app, matter, status='running')
    with pytest.raises(RuntimeError, match='lease lost'):
        publish(app, matter, ident)
    assert products(app, matter) == 0
    with coordinator_lease(app.state.store) as verify:
        verify()
        with pytest.raises(RuntimeError, match='lease lost'):
            app.state.research_owner()
