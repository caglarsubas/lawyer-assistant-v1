"""Real PostgreSQL snapshot races against explicitly disposable test storage.

The opt-in URL must name the dedicated ``lawyer_snapshot_test`` database on
loopback or the CI ``postgres`` service. Each test creates a randomly named child
database and drops only that exact database. Existing databases and public tables
are never cleared. No application configuration or credentials are loaded.
"""

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from threading import Barrier, Event, Lock
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import event, select, text, update
from sqlalchemy.engine import make_url
from test_provision_mappings import review
from test_public_sources import source as source_fixture
from test_source_reviews import another_client, assign

from app.config import Settings
from app.db import User
from app.main import create_app
from app.provision_mapping_models import ProvisionMappingHead
from app.release_snapshot import SnapshotError, readonly_store
from app.release_snapshot_set import SnapshotSetRequest, SourceSelection, locked_snapshot_set
from app.source_review_models import SourceReviewHead


@pytest.fixture
def postgres_database():
    value = os.environ.get("LA_TEST_POSTGRES_URL")
    if not value:
        pytest.skip("Set LA_TEST_POSTGRES_URL for an isolated PostgreSQL race run")
    try:
        supplied = make_url(value)
        valid = (supplied.drivername in {"postgresql", "postgresql+psycopg"}
                 and supplied.database == "lawyer_snapshot_test"
                 and supplied.host in {"localhost", "127.0.0.1", "::1", "postgres"}
                 and not supplied.query and supplied.username and supplied.password
                 and (supplied.port is None or 1 <= supplied.port <= 65535))
    except (ValueError, TypeError):
        valid = False
    if not valid:
        pytest.fail("PostgreSQL race tests require the dedicated local test database URL", pytrace=False)
    database = "lawyer_snapshot_test_" + uuid4().hex
    assert re.fullmatch(r"lawyer_snapshot_test_[0-9a-f]{32}", database)
    arguments = {"host": supplied.host, "port": supplied.port or 5432, "user": supplied.username,
                 "password": supplied.password, "dbname": supplied.database, "connect_timeout": 5,
                 "options": "-c statement_timeout=15000 -c lock_timeout=5000"}
    created = False
    try:
        with psycopg.connect(**arguments, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
            created = True
        yield supplied.set(drivername="postgresql+psycopg", database=database)
    finally:
        if created:
            with psycopg.connect(**arguments, autocommit=True) as admin:
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))


@pytest.fixture
def postgres_sources(postgres_database, tmp_path):
    from test_release_snapshot_set import make_source_set

    # model_construct deliberately bypasses all environment/dotenv configuration.
    settings = Settings.model_construct(
        demo_mode=True, cookie_secure=False, data_dir=tmp_path / "workspace",
        database_url=postgres_database.render_as_string(hide_password=False),
        public_source_dir=tmp_path / "public-only")
    app = create_app(settings)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/auth/login", json={"username": "demo", "password": "demo-local-only"})
            assert response.status_code == 200
            client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
            workspace = (app, client, client.get("/api/v1/matters").json()[0]["id"])
            sources = make_source_set(workspace, source_fixture.__wrapped__(tmp_path), count=2)
            with app.state.store.session() as session:
                operator = session.scalar(select(User.id).where(User.username == "demo"))
            request = SnapshotSetRequest(schema_version="legal-review-source-selection-v1", sources=[
                SourceSelection(source_id=item[3], expected_source_review_revision=5, expected_mapping_revision=2)
                for item in sources])
            yield app, sources, operator, request
    finally:
        app.state.store.engine.dispose()


@contextmanager
def source_set(fixture, *, request=None, reader=None):
    app, sources, operator, original_request = fixture
    if reader is None:
        with readonly_store(app.state.settings) as current:
            with source_set(fixture, request=request, reader=current) as snapshot:
                yield snapshot
        return
    with locked_snapshot_set(reader, sources[0][2], operator_id=operator,
                             request=request or original_request) as snapshot:
        yield snapshot


def wait_until_blocked(engine, pid, *, timeout=4):
    """Observe a real database lock wait, rather than infer one from a sleep."""
    deadline = time.monotonic() + timeout
    with engine.connect() as connection:
        while time.monotonic() < deadline:
            blockers = connection.scalar(text("SELECT pg_blocking_pids(:pid)"), {"pid": pid})
            if blockers:
                return blockers
            time.sleep(0.01)
    pytest.fail("Expected database lock wait was not observed")


@contextmanager
def observe_identity_lock(engine, *, statement_fragment=None):
    attempted, pids = Event(), []

    def before_query(connection, cursor, statement, parameters, context, executemany):
        matches = (statement_fragment in statement if statement_fragment is not None
                   else "FROM users" in statement and "FOR UPDATE" in statement)
        if matches:
            pids.append(connection.connection.driver_connection.info.backend_pid)
            attempted.set()

    event.listen(engine, "before_cursor_execute", before_query)
    try:
        yield attempted, pids
    finally:
        event.remove(engine, "before_cursor_execute", before_query)


def mapping_writer(fixture):
    mapping = fixture[1][0]
    identifier = mapping[1].get(mapping[4] + "/provision-mappings").json()["items"][0]["id"]
    return review(mapping, identifier, revision=2, decision="rejected")


@pytest.mark.parametrize("workers", [2, 5])
def test_reversed_concurrent_sets_are_identical_without_deadlock(postgres_sources, workers):
    _, _, _, request = postgres_sources
    barrier, guard, results = Barrier(workers), Lock(), []

    def run(index):
        selection = request.model_copy(update={"sources": list(reversed(request.sources)) if index % 2 else request.sources})
        with readonly_store(postgres_sources[0].state.settings) as reader:
            barrier.wait(timeout=5)
            with source_set(postgres_sources, request=selection, reader=reader) as snapshot:
                assert snapshot["summary"]["consistency_mode"] == "postgresql_transaction_locks"
                assert snapshot["summary"]["publication_eligible"] is False
                with guard:
                    results.append(snapshot["binding"])

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run, index) for index in range(workers)]
        for future in futures:
            future.result(timeout=20)
    assert len(results) == workers
    assert all(binding == results[0] for binding in results)
    assert [item["source_id"] for item in results[0]["sources"]] == sorted(item.source_id for item in request.sources)


def test_mapping_writer_waits_for_whole_set_then_invalidates_old_selection(postgres_sources):
    app = postgres_sources[0]
    with ThreadPoolExecutor(max_workers=1) as pool:
        with source_set(postgres_sources), observe_identity_lock(app.state.store.engine) as observed:
            future = pool.submit(mapping_writer, postgres_sources)
            attempted, pids = observed
            assert attempted.wait(5)
            assert wait_until_blocked(app.state.store.engine, pids[0])
            assert not future.done()
        assert future.result(timeout=10).status_code == 200
    with pytest.raises(SnapshotError), source_set(postgres_sources):
        pytest.fail("A changed mapping must invalidate the whole old selection")


def test_different_admin_release_waits_for_source_head_not_operator(postgres_sources):
    app, sources, operator, _ = postgres_sources
    # The fixture already owns the application lifespan; this is a second login, not a second API.
    with closing(another_client(app, username="reassigning-admin", role="admin")) as other:
        with app.state.store.session() as session:
            assert session.scalar(select(User.id).where(User.username == "reassigning-admin")) != operator
        with ThreadPoolExecutor(max_workers=1) as pool:
            with source_set(postgres_sources), observe_identity_lock(
                    app.state.store.engine, statement_fragment="UPDATE source_review_heads") as observed:
                future = pool.submit(assign, other, sources[0][4] + "/review", 5, "release",
                                     "Synthetic administrative reassignment race")
                assert observed[0].wait(5)
                assert wait_until_blocked(app.state.store.engine, observed[1][0])
                assert not future.done()
            response = future.result(timeout=10)
            assert response.status_code == 200
            assert response.json()["assigned_to"] is None
    with pytest.raises(SnapshotError), source_set(postgres_sources):
        pytest.fail("The released source must invalidate the whole old selection")


def test_queued_writer_commits_before_snapshot_and_stale_set_never_yields(postgres_sources):
    app, _, operator, _ = postgres_sources
    with readonly_store(app.state.settings) as reader, ThreadPoolExecutor(max_workers=2) as pool:
        with app.state.store.session() as blocker:
            blocker.scalar(select(User).where(User.id == operator).with_for_update())
            with observe_identity_lock(app.state.store.engine) as writer_observed:
                writer = pool.submit(mapping_writer, postgres_sources)
                assert writer_observed[0].wait(5)
                wait_until_blocked(app.state.store.engine, writer_observed[1][0])

                def queued_snapshot():
                    with pytest.raises(SnapshotError), source_set(postgres_sources, reader=reader):
                        pytest.fail("The queued snapshot must see the writer's committed revision")

                with observe_identity_lock(reader.engine) as reader_observed:
                    snapshot = pool.submit(queued_snapshot)
                    assert reader_observed[0].wait(5)
                    wait_until_blocked(app.state.store.engine, reader_observed[1][0])
                    blocker.commit()
                    assert writer.result(timeout=10).status_code == 200
                    snapshot.result(timeout=10)


def test_real_lock_timeout_fails_safely_and_does_not_hold_locks(postgres_sources):
    app, _, operator, _ = postgres_sources
    with app.state.store.session() as blocker:
        blocker.scalar(select(User).where(User.id == operator).with_for_update())
        started = time.monotonic()
        with pytest.raises(SnapshotError) as failure, source_set(postgres_sources):
            pytest.fail("An unavailable identity lock must not yield a snapshot")
        assert time.monotonic() - started < 15
        assert "unavailable" in str(failure.value) or "concurrent" in str(failure.value)
        assert operator not in str(failure.value)
    with source_set(postgres_sources) as snapshot:
        assert snapshot["summary"]["source_count"] == 2


def test_partial_failure_releases_all_previously_acquired_locks(postgres_sources):
    app, _, operator, request = postgres_sources
    selections = sorted(request.sources, key=lambda item: item.source_id)
    selections[-1] = selections[-1].model_copy(update={"expected_mapping_revision": 3})
    invalid = request.model_copy(update={"sources": selections})
    with pytest.raises(SnapshotError), source_set(postgres_sources, request=invalid):
        pytest.fail("A stale final source must invalidate the entire selection")
    # NOWAIT proves failed preparation did not retain any acquired ledger locks.
    with app.state.store.session() as session:
        session.scalar(select(User).where(User.id == operator).with_for_update(nowait=True))
        for model in (SourceReviewHead, ProvisionMappingHead):
            assert len(list(session.scalars(select(model).with_for_update(nowait=True)))) == 2
    with source_set(postgres_sources) as snapshot:
        assert snapshot["summary"]["source_count"] == 2


def test_committed_revocation_is_seen_after_waiting_for_operator(postgres_sources):
    app, _, operator, _ = postgres_sources
    with readonly_store(app.state.settings) as reader, ThreadPoolExecutor(max_workers=1) as pool:
        with app.state.store.session() as blocker:
            blocker.scalar(select(User).where(User.id == operator).with_for_update())
            blocker.execute(update(User).where(User.id == operator).values(active=False))

            def queued_snapshot():
                with pytest.raises(SnapshotError), source_set(postgres_sources, reader=reader):
                    pytest.fail("A revoked operator must not obtain a set")

            with observe_identity_lock(reader.engine) as observed:
                future = pool.submit(queued_snapshot)
                assert observed[0].wait(5)
                wait_until_blocked(app.state.store.engine, observed[1][0])
                blocker.commit()
                future.result(timeout=10)
