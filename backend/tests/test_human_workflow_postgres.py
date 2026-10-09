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
