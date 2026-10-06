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

from app.config import Settings
from app.db import Record
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
