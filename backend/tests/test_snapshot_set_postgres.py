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


def relationship_request(fixture, *, reverse=False):
    app, sources, _, _ = fixture
    client = sources[0][1]
    identifiers = [item[3] for item in sources]
    if reverse:
        identifiers.reverse()
    left, right = identifiers
    store = sources[0][2]
    packages = [store.verified_package(ident) for ident in identifiers]
    params = {'other_source_id': right, 'passage_id': packages[0].locators.passages[0].id,
              'other_passage_id': packages[1].locators.passages[0].id}
    evidence = client.get(f'/api/v1/public-sources/{left}/comparison', params=params)
    assert evidence.status_code == 200, evidence.text
    base = f'/api/v1/public-sources/{left}/relationship?other_source_id={right}'
    state = client.get(base).json()
    body = {'expected_revision': state['revision'],
            'expected_source_revisions': {key: value['revision'] for key, value in state['source_reviews'].items()},
            'classification': 'unresolved', 'rationale': 'Synthetic PostgreSQL race; no legal opinion',
            'identities': [], 'evidence_refs': [],
            'comparison': {'passage_id': params['passage_id'], 'other_passage_id': params['other_passage_id'],
                           'offset': 0, 'other_offset': 0, 'evidence_sha256': evidence.json()['evidence_sha256']}}
    return client, base, body


def test_selection_export_rejects_pair_changed_during_read(postgres_sources, monkeypatch):
    from app import source_selection
    client, base, body = relationship_request(postgres_sources)
    assert client.post(base, json=body).status_code == 200
    entered, resume = Event(), Event()
    original = source_selection._identity_conflicts

    def pause(pairs):
        entered.set()
        assert resume.wait(5)
        return original(pairs)

    monkeypatch.setattr(source_selection, '_identity_conflicts', pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, '/api/v1/public-sources/selection-review/export',
                             json={'source_ids': list(body['expected_source_revisions'])})
        try:
            assert entered.wait(5)
            replacement = {**body, 'expected_revision': 1, 'rationale': 'New synthetic PostgreSQL opinion'}
            assert client.post(base, json=replacement).status_code == 200
        finally:
            resume.set()
        result = future.result(timeout=10)
    assert result.status_code == 409 and 'evidence_json' not in result.json()
    assert client.get(base).json()['revision'] == 2


def test_relationship_opposite_pair_writers_keep_one_revision(postgres_sources):
    forward = relationship_request(postgres_sources)
    reverse = relationship_request(postgres_sources, reverse=True)
    barrier = Barrier(2)
    def write(args):
        client, base, body = args
        barrier.wait(timeout=5)
        return client.post(base, json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(write, [forward, reverse]))
    assert sorted(response.status_code for response in responses) == [200, 409]
    state = forward[0].get(forward[1]).json()
    assert state['revision'] == 1 and len(state['history']) == 1


def test_relationship_waits_for_source_revision_then_rejects_old_pin(postgres_sources):
    app, sources, _, _ = postgres_sources
    client, base, body = relationship_request(postgres_sources)
    source_id = sources[1][3]
    with app.state.store.session() as blocker:
        head = blocker.scalar(select(SourceReviewHead).where(SourceReviewHead.source_id == source_id).with_for_update())
        with observe_identity_lock(app.state.store.engine, statement_fragment='FROM source_review_heads') as (attempted, pids):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(client.post, base, json=body)
                assert attempted.wait(timeout=5)
                # The second source wait can have a different PID from the first
                # head query only if the implementation changes connection use.
                wait_until_blocked(app.state.store.engine, pids[-1])
                head.revision += 1  # Deliberately inconsistent synthetic source ledger.
                blocker.commit()
                response = future.result(timeout=10)
    assert response.status_code == 409
    from app.source_review_models import SourceRelationshipHead
    with app.state.store.session() as session:
        assert session.scalar(select(SourceRelationshipHead)) is None


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


def _decision_proposal(postgres_sources):
    from app.jurisprudence_candidates import find_occurrences
    _, sources, _, _ = postgres_sources
    _, client, store, identifier, base = sources[0]
    package = store.verified_package(identifier)
    passage = package.locators.passages[0]
    occurrence = find_occurrences(package, passage.id)["items"][0]
    return client, base + "/decision-mappings", {"expected_revision": 0, "expected_source_review_revision": 5,
        "passage_id": passage.id, "candidate_id": occurrence["id"], "rationale": "Synthetic PostgreSQL occurrence"}


def test_decision_mapping_competing_writers_keep_one_revision(postgres_sources):
    client, base, body = _decision_proposal(postgres_sources)
    barrier = Barrier(2)
    def write(_):
        barrier.wait(timeout=5)
        return client.post(base, json=body)
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(write, range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    state = client.get(base).json()
    assert state["revision"] == 1 and len(state["history"]) == 1


def test_decision_writer_rechecks_source_revision_after_lock_wait(postgres_sources):
    app, sources, _, _ = postgres_sources
    client, base, body = _decision_proposal(postgres_sources)
    identifier = sources[0][3]
    with app.state.store.session() as blocker:
        head = blocker.scalar(select(SourceReviewHead).where(SourceReviewHead.source_id == identifier).with_for_update())
        with observe_identity_lock(app.state.store.engine, statement_fragment="FROM source_review_heads") as (attempted, pids):
            with ThreadPoolExecutor(1) as pool:
                future = pool.submit(client.post, base, json=body)
                assert attempted.wait(timeout=5)
                wait_until_blocked(app.state.store.engine, pids[-1])
                assert not future.done()
                head.revision += 1  # Deliberately inconsistent synthetic ledger: fail closed after the lock wait.
                blocker.commit()
                response = future.result(timeout=10)
    assert response.status_code == 409
    from app.decision_mapping_models import DecisionMappingHead
    with app.state.store.session() as session:
        assert session.scalar(select(DecisionMappingHead)) is None


def test_decision_dossier_waits_for_source_then_withholds_stale_pin(postgres_sources):
    app, sources, _, _ = postgres_sources
    client, base, _ = _decision_proposal(postgres_sources)
    identifier = sources[0][3]
    with app.state.store.session() as blocker:
        head = blocker.scalar(select(SourceReviewHead).where(SourceReviewHead.source_id == identifier).with_for_update())
        with observe_identity_lock(app.state.store.engine, statement_fragment="FROM source_review_heads") as (attempted, pids):
            with ThreadPoolExecutor(1) as pool:
                future = pool.submit(client.post, base + "/dossier", json={
                    "expected_revision": 0, "expected_source_review_revision": 5})
                assert attempted.wait(timeout=5)
                wait_until_blocked(app.state.store.engine, pids[-1])
                assert not future.done()
                head.revision += 1  # Deliberately inconsistent synthetic ledger; no response after the wait.
                blocker.commit()
                response = future.result(timeout=10)
    assert response.status_code == 409 and "evidence_json" not in response.json()


@pytest.fixture
def postgres_decision(postgres_sources, tmp_path):
    from test_decision_identities import mapped
    from test_decision_mappings import mapping as mapping_fixture
    from test_jurisprudence_candidates import incoming
    app, sources, _, _ = postgres_sources
    root = tmp_path / "synthetic-decision"
    root.mkdir()
    package = source_fixture.__wrapped__(root)
    result = mapping_fixture.__wrapped__((app, sources[0][1], None), incoming.__wrapped__(package))
    mapped(result)
    return result


def test_canonical_identity_competing_reviews_keep_one_approval(postgres_decision):
    from test_decision_identities import propose_identity, review_identity
    assert propose_identity(postgres_decision).status_code == 200
    peer = another_client(postgres_decision[0], username="canonical-peer")
    barrier = Barrier(2)
    def write(_):
        barrier.wait(timeout=5)
        return review_identity(postgres_decision, peer)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(write, range(2)))
    assert sorted(response.status_code for response in results) == [200, 409]
    state = peer.get(postgres_decision[4] + "/decision-identities").json()
    assert state["revision"] == 2 and state["staged_handoff_ready"] and len(state["history"]) == 2


def test_canonical_identity_source_wait_revalidates_before_proposal(postgres_decision):
    from test_decision_identities import propose_identity
    app = postgres_decision[0]
    with app.state.store.session() as blocker:
        head = blocker.scalar(select(SourceReviewHead).where(SourceReviewHead.source_id == postgres_decision[3]).with_for_update())
        with observe_identity_lock(app.state.store.engine, statement_fragment="FROM source_review_heads") as (attempted, pids):
            with ThreadPoolExecutor(1) as pool:
                future = pool.submit(propose_identity, postgres_decision)
                assert attempted.wait(5)
                assert wait_until_blocked(app.state.store.engine, pids[-1])
                head.revision += 1  # Corrupt synthetic ledger cannot become an identity proposal.
                blocker.commit()
                assert future.result(timeout=10).status_code == 409


def test_graph_b_handoff_waits_for_source_then_withholds_stale_approval(postgres_decision):
    from test_decision_graph_handoff import download, evidence
    from test_decision_identities import proposal, propose_identity, review_identity
    from test_decision_mappings import review as decision_review
    from test_source_reviews import assess
    app, client, _, identifier, base, _, _ = postgres_decision
    assert assess(client, base + "/review", 5, "rights", permitted_uses=["local_processing", "internal_display", "export"]).status_code == 200
    item = client.get(base + "/decision-mappings").json()["items"][0]
    assert decision_review(postgres_decision, item["id"], 2, 6).status_code == 200
    identity = {**proposal(postgres_decision)["identity"], "identity_evidence": evidence(postgres_decision), "institution_evidence": evidence(postgres_decision)}
    assert propose_identity(postgres_decision, expected_mapping_revision=3, expected_source_review_revision=6, identity=identity).status_code == 200
    peer = another_client(app, username="stage-peer")
    assert review_identity(postgres_decision, peer, expected_mapping_revision=3, expected_source_review_revision=6, evidence_refs=evidence(postgres_decision)).status_code == 200
    with app.state.store.session() as blocker:
        head = blocker.scalar(select(SourceReviewHead).where(SourceReviewHead.source_id == identifier).with_for_update())
        with observe_identity_lock(app.state.store.engine, statement_fragment="FROM source_review_heads") as (attempted, pids):
            with ThreadPoolExecutor(1) as pool:
                future = pool.submit(download, postgres_decision, expected_mapping_revision=3)
                assert attempted.wait(5)
                assert wait_until_blocked(app.state.store.engine, pids[-1])
                head.revision += 1
                blocker.commit()
                result = future.result(timeout=10)
    assert result.status_code == 409 and "evidence_json" not in result.json()


@pytest.fixture
def postgres_equivalence(postgres_sources, tmp_path):
    from test_decision_equivalence import prepare
    from test_jurisprudence_candidates import incoming
    app, sources, _, _ = postgres_sources
    root = tmp_path / "synthetic-equivalence"
    root.mkdir()
    store, make = incoming.__wrapped__(source_fixture.__wrapped__(root))
    return prepare(app, sources[0][1], store, make)


def test_equivalence_competing_independent_reviews_keep_one_opinion(postgres_equivalence):
    from test_decision_equivalence import endpoint, opinion, propose
    assert propose(postgres_equivalence).status_code == 200
    barrier = Barrier(2)
    def write(_):
        barrier.wait(timeout=5)
        return opinion(postgres_equivalence)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(write, range(2)))
    assert sorted(response.status_code for response in results) == [200, 409]
    result = postgres_equivalence[2].get(endpoint(postgres_equivalence)).json()
    assert result["revision"] == 2 and result["same_decision_supported"]


def test_equivalence_waits_for_register_review_and_rechecks_pin(postgres_equivalence):
    from test_decision_equivalence import propose
    item = postgres_equivalence[0][2]
    app = item[0]
    with app.state.store.session() as blocker:
        head = blocker.scalar(select(SourceReviewHead).where(SourceReviewHead.source_id == item[3]).with_for_update())
        with observe_identity_lock(app.state.store.engine, statement_fragment="FROM source_review_heads") as (attempted, pids):
            with ThreadPoolExecutor(1) as pool:
                future = pool.submit(propose, postgres_equivalence)
                assert attempted.wait(5)
                assert wait_until_blocked(app.state.store.engine, pids[-1])
                head.revision += 1
                blocker.commit()
                assert future.result(timeout=10).status_code == 409


def test_equivalence_handoff_holds_register_lock_until_full_packet_finishes(postgres_equivalence, monkeypatch):
    from test_decision_equivalence import opinion, propose
    from test_decision_equivalence_handoff import decode, download
    from test_source_reviews import assess

    from app import decision_equivalence_handoff as handoff

    assert propose(postgres_equivalence).status_code == opinion(postgres_equivalence).status_code == 200
    item = postgres_equivalence[0][2]
    entered, resume = Event(), Event()
    compile_packet = handoff.compile_packet
    def pause(*args):
        result = compile_packet(*args)
        entered.set()
        assert resume.wait(5)
        return result
    monkeypatch.setattr(handoff, "compile_packet", pause)
    with ThreadPoolExecutor(2) as pool:
        packet = pool.submit(download, postgres_equivalence, postgres_equivalence[2])
        try:
            assert entered.wait(5)
            with observe_identity_lock(item[0].state.store.engine, statement_fragment="FROM source_review_heads") as (attempted, pids):
                writer = pool.submit(assess, item[1], item[4] + "/review", 6, "legal")
                assert attempted.wait(5)
                assert wait_until_blocked(item[0].state.store.engine, pids[-1])
                assert not writer.done()
                resume.set()
                data = decode(packet.result(timeout=10))
                assert data["pins"]["source_revisions"][item[3]] == 6
                assert writer.result(timeout=10).status_code == 200
        finally:
            resume.set()
    assert download(postgres_equivalence).status_code == 409


def test_signed_graph_b_competing_acceptances_keep_one_complete_event(postgres_equivalence, tmp_path):
    import json

    from test_graph_b_review import accept, path, prepare, request_body
    fixture = prepare(postgres_equivalence, tmp_path)
    body = json.loads(request_body(postgres_equivalence, fixture).json()["body_json"])
    barrier = Barrier(2)
    def write(_):
        barrier.wait(timeout=5)
        return accept(postgres_equivalence, fixture, body)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(write, range(2)))
    assert sorted(response.status_code for response in results) == [200, 409]
    state = fixture[1].get(path(postgres_equivalence)).json()
    assert state["signed_review_current"] and state["revision"] == len(state["history"]) == 1


def test_signed_graph_b_accept_waits_for_register_and_rejects_changed_pin(postgres_equivalence, tmp_path):
    import json

    from test_graph_b_review import accept, prepare, request_body
    fixture = prepare(postgres_equivalence, tmp_path)
    body = json.loads(request_body(postgres_equivalence, fixture).json()["body_json"])
    item = postgres_equivalence[0][2]
    with fixture[0].state.store.session() as blocker:
        head = blocker.scalar(select(SourceReviewHead).where(SourceReviewHead.source_id == item[3]).with_for_update())
        with observe_identity_lock(fixture[0].state.store.engine, statement_fragment="FROM source_review_heads") as (attempted, pids):
            with ThreadPoolExecutor(1) as pool:
                future = pool.submit(accept, postgres_equivalence, fixture, body)
                assert attempted.wait(5)
                assert wait_until_blocked(fixture[0].state.store.engine, pids[-1])
                head.revision += 1
                blocker.commit()
                assert future.result(timeout=10).status_code == 409
    from app.graph_b_review_models import GraphBReviewEvent
    with fixture[0].state.store.session() as session:
        assert session.scalar(select(GraphBReviewEvent)) is None


def test_graph_b_signing_inputs_hold_register_lock_through_conversion(postgres_equivalence, tmp_path, monkeypatch):
    from test_graph_b_review import accept, prepare
    from test_graph_b_signing import download
    from test_source_reviews import assess

    from app import graph_b_review
    fixture = prepare(postgres_equivalence, tmp_path)
    assert accept(postgres_equivalence, fixture).status_code == 200
    item = postgres_equivalence[0][2]
    entered, resume = Event(), Event()
    original = graph_b_review.compile_inputs
    def pause(*args):
        result = original(*args)
        entered.set()
        assert resume.wait(5)
        return result
    monkeypatch.setattr(graph_b_review, "compile_inputs", pause)
    with ThreadPoolExecutor(2) as pool:
        packet = pool.submit(download, postgres_equivalence, fixture)
        try:
            assert entered.wait(5)
            with observe_identity_lock(fixture[0].state.store.engine, statement_fragment="FROM source_review_heads") as (attempted, pids):
                writer = pool.submit(assess, item[1], item[4] + "/review", 6, "legal")
                assert attempted.wait(5)
                assert wait_until_blocked(fixture[0].state.store.engine, pids[-1])
                assert not writer.done()
                resume.set()
                assert packet.result(timeout=10).status_code == 200
                assert writer.result(timeout=10).status_code == 200
        finally:
            resume.set()
    assert download(postgres_equivalence, fixture).status_code == 409


@pytest.fixture
def postgres_graph_b_snapshot(postgres_sources, tmp_path):
    from test_graph_b_snapshot import prepare
    from test_jurisprudence_candidates import incoming
    app, sources, _, _ = postgres_sources
    root = tmp_path / "synthetic-signed-publication"
    root.mkdir()
    return prepare((app, sources[0][1], None), incoming.__wrapped__(source_fixture.__wrapped__(root)), tmp_path)


def test_graph_b_local_snapshot_five_shared_readers_and_all_dependency_row_locks(postgres_graph_b_snapshot):
    from test_graph_b_snapshot import opened

    from app.decision_equivalence_models import DecisionEquivalenceHead
    from app.decision_identity_models import DecisionIdentityHead, DecisionIdentityReservation
    from app.decision_mapping_models import DecisionMappingHead
    from app.graph_b_review_models import GraphBReviewHead
    fixture = postgres_graph_b_snapshot
    entered = Barrier(5)
    with readonly_store(fixture["app"].state.settings) as reader:
        def read():
            with opened(fixture, reader, shared=True):
                entered.wait(timeout=10)
        with ThreadPoolExecutor(5) as pool:
            futures = [pool.submit(read) for _ in range(5)]
            for future in futures:
                future.result(timeout=20)
        with opened(fixture, reader, shared=True) as snapshot:
            binding = snapshot["binding"]
            targets = [(User, actor, "active") for actor in (binding["operator_id"], binding["reviewer_id"])]
            for heads in binding["heads"].values():
                targets.append((SourceReviewHead, heads["source_review"], "revision"))
                if "mapping" in heads:
                    targets += [(DecisionMappingHead, heads["mapping"], "revision"), (DecisionIdentityHead, heads["identity"], "revision")]
            targets += [(DecisionEquivalenceHead, binding["equivalence_head_id"], "revision"),
                        (GraphBReviewHead, binding["signed_review_head_id"], "revision")]
            targets += [(DecisionIdentityReservation, row["id"], "payload") for row in snapshot["reservations"]]
        def write(model, identifier, field):
            with fixture["app"].state.store.session() as session:
                session.execute(update(model).where(model.id == identifier).values({field: getattr(model, field)}))
                session.commit()
        # The application's connection pool is bounded to 15 connections. Probe
        # in batches so queued connection acquisition cannot mask a row-lock test.
        for offset in range(0, len(targets), 8):
            batch = targets[offset:offset + 8]
            with ThreadPoolExecutor(len(batch)) as pool:
                with opened(fixture, reader, shared=True), observe_identity_lock(fixture["app"].state.store.engine, statement_fragment="UPDATE ") as observed:
                    futures = [pool.submit(write, *target) for target in batch]
                    deadline = time.monotonic() + 4
                    while len(observed[1]) < len(batch) and time.monotonic() < deadline:
                        time.sleep(.01)
                    assert len(observed[1]) == len(batch)
                    assert all(wait_until_blocked(fixture["app"].state.store.engine, pid) for pid in observed[1])
                    assert not any(future.done() for future in futures)
                for future in futures:
                    future.result(timeout=10)



@pytest.mark.parametrize("change", ["register-rights", "negative-review"])
def test_graph_b_local_snapshot_blocks_review_writer_and_next_use_rejects(postgres_graph_b_snapshot, change):
    from datetime import datetime, timezone

    from test_graph_b_review import accept
    from test_graph_b_snapshot import opened
    from test_source_reviews import assess
    fixture = postgres_graph_b_snapshot
    if change == "negative-review":
        fixture["signed"][5].update(expected_review_revision=1, reviewed_at=datetime.now(timezone.utc).isoformat())
        def write():
            return accept(fixture["evidence"], fixture["signed"], decision="reject")
    else:
        item = fixture["evidence"][0][2]
        def write():
            return assess(item[1], item[4] + "/review", 6, "rights", decision="rejected")
    with readonly_store(fixture["app"].state.settings) as reader, ThreadPoolExecutor(1) as pool:
        with opened(fixture, reader, shared=True), observe_identity_lock(fixture["app"].state.store.engine, statement_fragment="FROM users") as observed:
            writer = pool.submit(write)
            assert observed[0].wait(5)
            assert wait_until_blocked(fixture["app"].state.store.engine, observed[1][-1])
            assert not writer.done()
        result = writer.result(timeout=10)
        assert result.status_code == 200, result.text
        with pytest.raises(SnapshotError), opened(fixture, reader, shared=True):
            pytest.fail("A later negative review or source revocation must invalidate old publication snapshots")


def test_graph_b_local_snapshot_cancels_bounded_lock_wait_without_partial_output(postgres_graph_b_snapshot):
    from test_graph_b_snapshot import opened
    fixture = postgres_graph_b_snapshot
    with fixture["app"].state.store.session() as blocker, readonly_store(fixture["app"].state.settings) as reader:
        blocker.scalar(select(SourceReviewHead).where(SourceReviewHead.source_id == fixture["request"].register_source_id).with_for_update())
        def read():
            with opened(fixture, reader):
                pytest.fail("Timed-out source selection must not yield any partial snapshot")
        with ThreadPoolExecutor(1) as pool:
            with observe_identity_lock(reader.engine, statement_fragment="FROM source_review_heads") as observed:
                future = pool.submit(read)
                assert observed[0].wait(5)
                assert wait_until_blocked(fixture["app"].state.store.engine, observed[1][-1])
                with pytest.raises(SnapshotError, match="could not be verified"):
                    future.result(timeout=8)
        blocker.rollback()
    with readonly_store(fixture["app"].state.settings) as reader, opened(fixture, reader):
        pass
