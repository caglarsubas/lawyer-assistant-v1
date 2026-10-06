"""Synthetic, offline admission and cancellation with event-controlled dependencies."""

import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event

import pytest
from sqlalchemy import func, select
from test_workspace import workspace as workspace_fixture

from app.db import Audit, Membership, Record, User
from app.research import run_research
from app.research_jobs import (
    JobStopped,
    QueueUnavailable,
    ResearchJobs,
    coordinator_lease,
    ensure_active,
    finish_run,
    recover_runs,
    request_stop,
    submission,
)


@pytest.fixture
def workspace(tmp_path):
    yield from workspace_fixture.__wrapped__(tmp_path)

def wait_for(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    pytest.fail("Synthetic job did not reach the expected state")


def state(app, ident):
    with app.state.store.session() as session:
        return app.state.store.view(session.get(Record, ident))


def seed_run(app, matter, **values):
    store = app.state.store
    with store.session() as session:
        user = session.scalar(select(User).where(User.username == "demo"))
        record = store.add(session, "research", user, {
            **submission(300), "question": "SYNTHETIC ödeme", **values,
        }, matter)
        session.commit()
        return record.id


def products(app, matter):
    with app.state.store.session() as session:
        return session.scalar(select(func.count()).select_from(Record).where(
            Record.kind == "product", Record.matter_id == matter))


def light_graph(monkeypatch, app):
    def locate(*args, **kwargs):
        return {"snapshot": {"mode": "synthetic"}, "paths": []}
    monkeypatch.setattr(app.state.graph, "tool", locate)


def test_five_workers_ten_admissions_and_physical_queued_removal():
    started, release = Barrier(6), Event()
    executed, finished = [], []

    def work(ident):
        executed.append(ident)
        if len(executed) <= 5:
            started.wait(timeout=5)
            assert release.wait(5)

    pool = ResearchJobs(work, lambda ident: None, finished.append)
    try:
        ids = []
        for _ in range(10):
            with pool.reserve() as ident:
                ids.append(ident)
                pool.submit(ident)
        started.wait(timeout=5)
        assert set(executed) == set(ids[:5])
        with pytest.raises(QueueUnavailable), pool.reserve():
            pass
        # Replacements stay bounded even under repeated queued cancellations.
        queued = ids[5]
        for _ in range(30):
            pool.cancel(queued)
            pool.cancel(queued)
            assert finished.count(queued) == 1
            with pool.reserve() as ident:
                queued = ident
                pool.submit(ident)
            assert len(pool._queue) == 5
            with pytest.raises(QueueUnavailable), pool.reserve():
                pass
        release.set()
        wait_for(lambda: len(executed) == 10)
    finally:
        release.set()
        pool.close()
    assert len(set(executed)) == 10
    assert len(pool._jobs) == 0


def test_outcome_failure_disables_admission_without_logging_payload(caplog):
    done = Event()

    def finish(ident):
        done.set()
        raise ValueError("SYNTHETIC PRIVATE PAYLOAD")

    pool = ResearchJobs(lambda ident: None, lambda ident: None, finish, workers=1)
    try:
        with pool.reserve() as ident:
            pool.submit(ident)
        assert done.wait(5)
        wait_for(lambda: pool._closed)
        with pytest.raises(QueueUnavailable), pool.reserve():
            pass
    finally:
        pool.close()
    assert "SYNTHETIC PRIVATE PAYLOAD" not in caplog.text
    assert "admission disabled" in caplog.text


def test_reservations_release_on_error_and_reject_after_close():
    pool = ResearchJobs(lambda ident: None, lambda ident: None, lambda ident: None, workers=1, capacity=1)
    with pytest.raises(ValueError), pool.reserve():
        raise ValueError("synthetic transaction failure")
    with pool.reserve() as ident:
        pool.close()
        with pytest.raises(QueueUnavailable):
            pool.submit(ident)
    assert not pool._jobs


def test_rejected_api_submission_has_no_record_or_audit(workspace):
    app, client, matter = workspace
    store = app.state.store

    def counts():
        with store.session() as session:
            return (session.scalar(select(func.count()).select_from(Record)),
                    session.scalar(select(func.count()).select_from(Audit)))

    before = counts()
    with ExitStack() as stack:
        for _ in range(10):
            stack.enter_context(app.state.research_jobs.reserve())
        assert client.post(f"/api/v1/matters/{matter}/research", json={"question": "SYNTHETIC capacity"}).status_code == 429
        assert client.post("/api/v1/matters/foreign/research", json={"question": "SYNTHETIC capacity"}).status_code == 404
    assert counts() == before


def test_submission_shutdown_race_is_interrupted_not_orphaned(workspace, monkeypatch):
    app, client, matter = workspace

    def closed(ident):
        raise QueueUnavailable()

    monkeypatch.setattr(app.state.research_jobs, "submit", closed)
    response = client.post(f"/api/v1/matters/{matter}/research", json={"question": "SYNTHETIC race"})
    assert response.status_code == 503
    with app.state.store.session() as session:
        runs = session.scalars(select(Record).where(Record.kind == "research")).all()
        assert len(runs) == 1
        assert app.state.store.decode(runs[0])["status"] == "interrupted"
    assert not app.state.research_jobs._jobs


@pytest.mark.parametrize("action", ["cancel", "archive", "expire", "revoke", "shutdown"])
def test_inflight_provider_must_exit_before_stop_acknowledgement(workspace, monkeypatch, action):
    app, client, matter = workspace
    light_graph(monkeypatch, app)
    entered, release = Event(), Event()

    class Provider:
        configured = True
        transport_mode = "local"

        def generate(self, *args):
            entered.set()
            assert release.wait(10)
            return '{"summary":"", "claims":[]}'

    app.state.provider = Provider()
    base = f"/api/v1/matters/{matter}"
    run = client.post(base + "/research", json={"question": "SYNTHETIC ödeme"})
    assert run.status_code == 202, run.text
    ident = run.json()["id"]
    try:
        assert entered.wait(5)
        assert state(app, ident)["status"] == "running"
        if action == "cancel":
            for _ in range(2):
                cancelled = client.post(base + f"/research/{ident}/cancel")
                assert cancelled.status_code == 200
                assert cancelled.json()["status"] == "cancelling"
        elif action == "archive":
            revision = client.get(base).json()["revision"]
            archived = client.post(base + "/archive", json={"reason": "Synthetic archive", "expected_revision": revision})
            assert archived.status_code == 200, archived.text
            assert state(app, ident)["status"] == "cancelling"
        elif action == "shutdown":
            request_stop(app.state.store, ident, "service_shutdown")
        else:
            with app.state.store.session() as session:
                if action == "expire":
                    record = session.get(Record, ident)
                    app.state.store.update(record, {**app.state.store.decode(record), "deadline_at": "2000-01-01T00:00:00+00:00"})
                else:
                    member = session.scalar(select(Membership).where(Membership.matter_id == matter))
                    session.delete(member)
                session.commit()
        assert ident in app.state.research_jobs._jobs
        assert products(app, matter) == 0
        assert "finished_at" not in state(app, ident)
    finally:
        release.set()
    expected = {"expire": "timed_out", "revoke": "failed", "shutdown": "interrupted"}.get(action, "cancelled")
    wait_for(lambda: state(app, ident)["status"] == expected)
    wait_for(lambda: ident not in app.state.research_jobs._jobs)
    assert products(app, matter) == 0
    assert state(app, ident)["finished_at"]


def test_queued_cancel_frees_slot_without_entering_worker(workspace, monkeypatch):
    app, client, matter = workspace
    started, release = Barrier(6), Event()
    executed = []

    def work(ident):
        executed.append(ident)
        started.wait(timeout=5)
        assert release.wait(10)

    monkeypatch.setattr(app.state.research_jobs, "_work", work)
    base = f"/api/v1/matters/{matter}"
    try:
        running = [client.post(base + "/research", json={"question": "SYNTHETIC running"}).json()["id"] for _ in range(5)]
        started.wait(timeout=5)
        queued = client.post(base + "/research", json={"question": "SYNTHETIC queued"}).json()["id"]
        response = client.post(base + f"/research/{queued}/cancel")
        assert response.json()["status"] == "cancelled"
        assert queued not in executed
        assert queued not in app.state.research_jobs._jobs
        assert set(app.state.research_jobs._jobs) == set(running)
    finally:
        release.set()


@pytest.mark.parametrize("where", ["evidence", "graph", "search", "provider"])
def test_stage_failure_terminalizes_and_does_not_expose_error(workspace, monkeypatch, where):
    app, _, matter = workspace
    light_graph(monkeypatch, app)

    def fail(*args, **kwargs):
        raise RuntimeError("SYNTHETIC PRIVATE VALUE")

    if where == "evidence":
        monkeypatch.setattr("app.research.select_passages", fail)
    elif where == "graph":
        monkeypatch.setattr(app.state.graph, "tool", fail)
    elif where == "search":
        monkeypatch.setattr(app.state.search, "search", fail)
    else:
        app.state.provider = type("Provider", (), {"configured": True, "generate": fail})()
    ident = seed_run(app, matter)
    run_research(app, ident)
    assert state(app, ident)["status"] == "failed"
    assert "PRIVATE VALUE" not in str(state(app, ident))
    assert products(app, matter) == 0


def test_expired_queue_never_enters_retrieval(workspace, monkeypatch):
    app, _, matter = workspace

    def forbidden(*args, **kwargs):
        pytest.fail("Expired job entered retrieval")

    monkeypatch.setattr(app.state.graph, "tool", forbidden)
    ident = seed_run(app, matter, deadline_at="2000-01-01T00:00:00+00:00")
    run_research(app, ident)
    assert state(app, ident)["status"] == "timed_out"
    assert products(app, matter) == 0


def test_wrong_matter_cancel_has_no_effect(workspace):
    app, client, matter = workspace
    ident = seed_run(app, matter)
    other = client.post("/api/v1/matters", json={"title": "Synthetic other", "domain": "contracts"}).json()["id"]
    assert client.post(f"/api/v1/matters/{other}/research/{ident}/cancel").status_code == 404
    assert state(app, ident)["status"] == "queued"


def test_shutdown_waits_for_worker_and_persists_intent_first():
    entered, release, stopped, finished = Event(), Event(), Event(), Event()

    def work(ident):
        entered.set()
        assert release.wait(5)
        assert stopped.is_set()

    pool = ResearchJobs(work, lambda ident: stopped.set(), lambda ident: finished.set(), workers=1)
    with pool.reserve() as ident:
        pool.submit(ident)
    assert entered.wait(5)
    with ThreadPoolExecutor(1) as executor:
        closing = executor.submit(pool.close)
        try:
            assert stopped.wait(5)
            assert not closing.done()
            assert not finished.is_set()
        finally:
            release.set()
        closing.result(timeout=5)
    assert finished.is_set()
    assert all(not thread.is_alive() for thread in pool._threads)


def test_restart_marks_only_unfinished_jobs_and_lease_is_exclusive(workspace):
    app, _, matter = workspace
    with pytest.raises(RuntimeError, match="coordinator"), coordinator_lease(app.state.store):
        pass
    ids = {status: seed_run(app, matter, status=status) for status in
           ["queued", "running", "cancelling", "completed", "failed", "cancelled", "timed_out"]}
    # No worker owns the synthetic rows; production calls recovery only under its startup lease.
    recover_runs(app.state.store)
    for previous, ident in ids.items():
        expected = "interrupted" if previous in {"queued", "running", "cancelling"} else previous
        assert state(app, ident)["status"] == expected
    completed = ids["completed"]
    before = state(app, completed)
    request_stop(app.state.store, completed)
    finish_run(app.state.store, completed)
    assert state(app, completed) == before


def test_deadline_includes_queue_time_and_requires_timezone():
    before = datetime.now(timezone.utc)
    captured = submission(30)
    deadline = datetime.fromisoformat(captured["deadline_at"])
    assert before + timedelta(seconds=30) <= deadline <= datetime.now(timezone.utc) + timedelta(seconds=30)
    with pytest.raises(ValueError, match="timezone"):
        ensure_active({"status": "queued", "deadline_at": "2000-01-01T00:00:00"})
    with pytest.raises(JobStopped) as stopped:
        ensure_active({"status": "cancelling", "deadline_at": "2000-01-01T00:00:00+00:00"})
    assert stopped.value.outcome == "cancelled"


def test_sqlite_cancel_between_read_and_write_rolls_back_product(workspace, monkeypatch):
    app, _, matter = workspace
    light_graph(monkeypatch, app)
    ident = seed_run(app, matter)
    original = app.state.store.add

    def add(session, kind, *args, **kwargs):
        if kind == "product":
            request_stop(app.state.store, ident)
        return original(session, kind, *args, **kwargs)

    monkeypatch.setattr(app.state.store, "add", add)
    run_research(app, ident)
    assert state(app, ident)["status"] == "cancelled"
    assert products(app, matter) == 0


def test_shutdown_persistence_failure_joins_workers_and_reports_recovery(caplog):
    def stop(ident):
        raise RuntimeError("SYNTHETIC PRIVATE SHUTDOWN ERROR")

    pool = ResearchJobs(lambda ident: None, stop, lambda ident: None, workers=1)
    with pool.reserve():
        with pytest.raises(RuntimeError, match="restart recovery"):
            pool.close()
    assert all(not thread.is_alive() for thread in pool._threads)
    assert "PRIVATE SHUTDOWN" not in caplog.text


def test_second_startup_cannot_recover_live_records(workspace):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app, _, matter = workspace
    ids = {status: seed_run(app, matter, status=status) for status in
           ["queued", "running", "cancelling", "completed"]}
    # A second startup must fail before it can rewrite the original worker's state.
    with pytest.raises(RuntimeError, match="coordinator"), TestClient(create_app(app.state.settings)):
        pass
    assert state(app, ids["running"])["status"] == "running"
