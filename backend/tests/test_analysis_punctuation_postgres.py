"""Real PostgreSQL retention locks and atomic history over disposable saved sources.

Only the dedicated opt-in test database is admitted. The shared fixture creates
and drops a unique child database for each test, never application data.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event, local

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_analysis_original_source import synthetic_pdf
from test_analysis_punctuation import retained_source as retained_fixture
from test_analysis_punctuation_audit import _readonly
from test_analysis_reviews import review_request
from test_snapshot_set_postgres import observe_identity_lock, wait_until_blocked
from test_snapshot_set_postgres import postgres_database as database_fixture

from app import analysis_punctuation as punctuation
from app.config import Settings
from app.db import Audit, Record, User, digest
from app.runtime import create_app


@pytest.fixture
def postgres_database():
    yield from database_fixture.__wrapped__()


@pytest.fixture
def postgres_saved_source(postgres_database, tmp_path):
    # model_construct deliberately bypasses the environment and dotenv loader.
    app = create_app(Settings.model_construct(
        demo_mode=True, cookie_secure=False, data_dir=tmp_path,
        database_url=postgres_database.render_as_string(hide_password=False),
        public_source_dir=tmp_path / "public-only"))
    try:
        with TestClient(app) as client:
            login = client.post("/api/v1/auth/login", json={"username": "demo", "password": "demo-local-only"})
            assert login.status_code == 200
            client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            matter = client.get("/api/v1/matters").json()[0]["id"]
            base = f"/api/v1/matters/{matter}"
            original = synthetic_pdf()
            uploaded = client.post(base + "/documents", files={"file": ("synthetic.pdf", original, "application/pdf")})
            assert uploaded.status_code == 201
            document = client.get(base + "/documents/" + uploaded.json()["id"]).json()
            assert document["sha256"] == digest(original) and document["page_count"] == 2
            [passage] = [item for item in document["passages"] if item["locator"] == "Sayfa 2"]
            payload = {
                "title": "SYNTHETIC PostgreSQL source retention",
                "issue": "SYNTHETIC private saved-source punctuation qualification.",
                "evidence": [{"evidence_id": passage["id"], "passage_sha256": passage["text_sha256"],
                              "document_revision": document["revision"], "start": 10, "end": len(passage["text"])}],
                "conclusion": {"text": "SYNTHETIC review-only draft.", "next_step": "Inspect the original."},
            }
            created = client.post(base + "/analyses", json=payload)
            assert created.status_code == 201
            analysis = created.json()
            scope = base + f"/analyses/{analysis['id']}"
            body, context = review_request(client, scope + "/reviews", analysis, decision="changes_requested")
            review = client.post(scope + "/reviews", json=body)
            assert review.status_code == 201
            headers = {"X-Analysis-Content-SHA256": context["content_sha256"],
                       "X-Quote-SHA256": context["sources"][0]["quote_sha256"]}
            link = scope + f"/versions/{analysis['latest_version_id']}/evidence/{passage['id']}/original/"
            yield app, client, matter, document, analysis, payload, link, headers, original
    finally:
        app.state.store.engine.dispose()


@pytest.fixture
def retained_source(postgres_saved_source):
    return retained_fixture.__wrapped__(postgres_saved_source)


def _protected(case):
    app, client = case["app"], case["client"]
    with app.state.store.session() as session:
        before = {row.id: (row.revision, row.payload) for row in session.scalars(select(Record).where(
            ~Record.kind.in_((punctuation.KIND, punctuation.RUN_KIND)),
        ))}
    original = (app.state.settings.data_dir / "documents" / (case["document"]["id"] + ".enc")).read_bytes()
    reviews = client.get(f"/api/v1/matters/{case['matter']}/analyses/{case['analysis']['id']}/reviews",
                         params={"version_id": case["pins"]["version_id"]}).json()
    assert len(reviews) == 1, "Preservation must include a real saved review, not an empty list"
    return before, original, reviews


def _retained_rows_and_audits(case):
    with case["app"].state.store.session() as session:
        rows = session.scalars(select(Record).where(Record.kind.in_((punctuation.KIND, punctuation.RUN_KIND)))).all()
        audits = session.scalars(select(Audit).where(Audit.action.in_(
            ("analysis_punctuation_capture_retained", "analysis_punctuation_retained"),
        ))).all()
        return rows, audits


@pytest.mark.parametrize("with_event", [True, False])
def test_duplicate_captures_wait_on_real_matter_lock_and_preserve_exact_history(retained_source, monkeypatch,
                                                                             with_event):
    case = retained_source
    before = _protected(case)
    capture = dict(case["capture"])
    if not with_event:
        capture["events"] = []
        capture["run_sha256"] = punctuation.capture_run_sha256(capture)
    entered, resume = Event(), Event()
    calls = local()
    original = punctuation._original

    def pause_inside_first_transaction(*args):
        count = getattr(calls, "count", 0) + 1
        calls.count = count
        result = original(*args)
        if count == 2 and not entered.is_set():
            entered.set()
            assert resume.wait(timeout=10)
        return result

    monkeypatch.setattr(punctuation, "_original", pause_inside_first_transaction)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(case["retain"], capture)
        assert entered.wait(timeout=5)
        with observe_identity_lock(case["app"].state.store.engine, statement_fragment="FOR UPDATE") as observed:
            second = pool.submit(case["retain"], capture)
            try:
                assert observed[0].wait(timeout=5)
                assert wait_until_blocked(case["app"].state.store.engine, observed[1][-1])
                assert not first.done() and not second.done()
            finally:
                resume.set()
            left, right = first.result(timeout=10), second.result(timeout=10)
    assert left == right and len(left) == int(with_event)
    rows, audits = _retained_rows_and_audits(case)
    assert len(rows) == len(audits) == 1 + int(with_event)
    assert all(row.revision == 1 for row in rows)
    row_payloads = {row.id: row.payload for row in rows}
    assert case["retain"](capture) == left
    assert {row.id: row.payload for row in _retained_rows_and_audits(case)[0]} == row_payloads
    assert _protected(case) == before
    viewed = case["client"].get(case["url"], headers=case["headers"])
    assert viewed.status_code == 200 and viewed.headers["cache-control"] == "no-store"
    assert viewed.json()["items"] == left and len(viewed.json()["runs"]) == 1


def test_write_permission_revoked_while_waiting_for_matter_lock_refuses_retention(retained_source):
    case = retained_source
    store = case["app"].state.store
    before = _protected(case)
    with store.session() as blocker:
        blocker.scalar(select(Record).where(Record.id == case["matter"]).with_for_update())
        with observe_identity_lock(store.engine, statement_fragment="FOR UPDATE") as observed:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(case["retain"])
                try:
                    assert observed[0].wait(timeout=5)
                    assert wait_until_blocked(store.engine, observed[1][-1])
                    with store.session() as update:
                        _readonly(update, update.scalar(select(User).where(User.username == "demo")))
                        update.commit()
                finally:
                    blocker.rollback()
                with pytest.raises(HTTPException) as refused:
                    future.result(timeout=10)
    assert refused.value.status_code == 403
    assert _retained_rows_and_audits(case) == ([], [])
    assert _protected(case) == before


def test_post_flush_failure_rolls_back_capture_events_and_audits_then_allows_fresh_retry(retained_source, monkeypatch):
    case = retained_source
    store = case["app"].state.store
    before = _protected(case)
    add = store.add

    def fail_after_event_flush(session, kind, user, data, *args, **kwargs):
        record = add(session, kind, user, data, *args, **kwargs)
        if kind == punctuation.KIND:
            raise RuntimeError("SYNTHETIC interruption after capture and observation flush")
        return record

    with monkeypatch.context() as injected:
        injected.setattr(store, "add", fail_after_event_flush)
        with pytest.raises(RuntimeError, match="SYNTHETIC interruption"):
            case["retain"]()
    assert _retained_rows_and_audits(case) == ([], [])
    assert _protected(case) == before
    [saved] = case["retain"]()
    assert case["retain"]() == [saved]
    rows, audits = _retained_rows_and_audits(case)
    assert len(rows) == len(audits) == 2
    assert _protected(case) == before


def test_served_capture_and_exact_raster_reopen_through_an_independent_postgres_store(retained_source, monkeypatch):
    from app import analysis_punctuation_capture as coordinator

    case = retained_source
    app, client = case["app"], case["client"]
    before = _protected(case)
    app.state.settings.extraction_url = "http://127.0.0.1:8002"
    app.state.settings.extraction_token = "SYNTHETIC-disposable-worker-token-at-least32"
    calls = []

    class DisposableWorker:
        def __init__(self, origin, token):
            assert origin == app.state.settings.extraction_url and token == app.state.settings.extraction_token

        def execute_capture(self, content, page):
            assert content == case["original"] and page == 2
            calls.append(digest(content))
            return case["capture"]

    monkeypatch.setattr(coordinator, "PunctuationClient", DisposableWorker)
    captured = client.post(case["url"], headers=case["headers"])
    assert captured.status_code == 200 and captured.headers["cache-control"] == "no-store"
    assert calls == [digest(case["original"])]
    history = client.get(case["url"], headers=case["headers"]).json()
    [saved] = history["items"]
    assert saved["canonical_usable"] is False and saved["scope"] == "source_page_context"
    detail_url = case["url"] + "/" + saved["id"]
    assert client.get(detail_url, headers=case["headers"]).json() == saved
    raster = client.get(detail_url + "/raster", headers=case["headers"])
    assert raster.status_code == 200 and raster.content == case["capture"]["png"]
    assert raster.headers["cache-control"] == "no-store"
    assert raster.headers["x-source-raster-sha256"] == digest(raster.content) == saved["raster_sha256"]
    assert raster.headers["x-source-sha256"] == case["document"]["sha256"]
    assert _protected(case) == before

    # Release the single API coordinator before a real application restart.
    # The fixture's ExitStack teardown is idempotent after this explicit stop.
    client.__exit__(None, None, None)
    reopened = create_app(app.state.settings)
    try:
        with TestClient(reopened) as other:
            login = other.post("/api/v1/auth/login", json={"username": "demo", "password": "demo-local-only"})
            assert login.status_code == 200
            assert other.get(case["url"], headers=case["headers"]).json() == history
            assert other.get(detail_url, headers=case["headers"]).json() == saved
            assert other.get(detail_url + "/raster", headers=case["headers"]).content == raster.content
            restarted_case = {**case, "app": reopened, "client": other}
            assert _protected(restarted_case) == before
    finally:
        store = getattr(reopened.state, "store", None)
        if store is not None:
            store.engine.dispose()
