"""Opt-in real OpenSearch drill. The generated internal Docker project is required.

All sources, reviewers, signatures and private ledgers are synthetic test fixtures.
No real-law qualification or existing deployment access is performed.
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from test_release_set_authorization import change_second, guard_set
from test_set_authorization_postgres import postgres_authorized_set as postgres_authorized_set_fixture
from test_snapshot_set_postgres import observe_identity_lock, wait_until_blocked
from test_snapshot_set_postgres import postgres_database as postgres_database_fixture

from app.graph_release import RuntimeGraphRelease, _load_serving
from app.search import PublicSearchService
from app.search_index import IndexBuildError, IndexTransport, build_index

postgres_authorized_set = postgres_authorized_set_fixture
postgres_database = postgres_database_fixture
MARKER = "lawyer-search-index-drill-v2"
URL = "http://opensearch:9200"
pytestmark = pytest.mark.skipif(os.environ.get("LA_SEARCH_INDEX_DRILL") != MARKER,
                                reason="Opt-in disposable OpenSearch qualification only")


def test_real_index_build_rebuild_failure_and_revocation(postgres_authorized_set, tmp_path, monkeypatch):
    fixture = postgres_authorized_set
    assert fixture["app"].state.store.engine.dialect.name == "postgresql"
    serving = _load_serving()
    root = tmp_path / "runtime"

    def authorize(info, action):
        return guard_set(fixture, info=info, action=action)

    serving.install(root, fixture["info"]["bundle_path"].parent, fixture["public_key"], authorization_guard=authorize)
    serving.activate(root, fixture["info"]["release_id"], fixture["public_key"], expected_current=None, authorization_guard=authorize)
    runtime = RuntimeGraphRelease(root, fixture["public_key"], authorize)
    release = runtime.require_current()["release_id"]
    began = time.monotonic()
    first = build_index(runtime, URL, release)
    build_seconds = round(time.monotonic() - began, 3)
    with runtime.current_guard():
        expected = list(runtime.iter_search_documents())
    assert first["document_count"] == len(expected) and len(expected) >= 4
    authority = expected[0]["authority_id"]
    search = PublicSearchService(URL, first["index"], release, runtime)
    initial = search.search("term absent from source", as_of="2011-06-01", authority_id=authority)
    assert initial["hits"] and initial["coverage"]["rejected_hits"] == 0
    assert all(row["text"] in {item["text"] for item in expected} and row["source_url"] is None for row in initial["hits"])
    assert not search.search("term", as_of="2013-01-01", authority_id=authority)["hits"]
    assert search.search("Birinci", as_of="2011-06-01")["hits"]

    # A build paused after index creation cannot displace or masquerade as the
    # existing sealed index. Query the actual old index while its rebuild runs.
    ready, proceed = Event(), Event()
    original = IndexTransport.request
    rebuilding = []

    def hold(self, method, suffix="", **kwargs):
        if suffix == "/_bulk":
            rebuilding.append(self.index)
            ready.set()
            if not proceed.wait(30):
                raise TimeoutError("Synthetic rebuild barrier")
        return original(self, method, suffix, **kwargs)

    with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=1) as pool:
        patch.setattr(IndexTransport, "request", hold)
        future = pool.submit(build_index, runtime, URL, release)
        try:
            assert ready.wait(30)
            def query():
                start = time.monotonic()
                result = search.search("term", as_of="2011-06-01", authority_id=authority)
                assert result["coverage"]["status"] == "available"
                assert result["hits"] == initial["hits"]
                return round(time.monotonic() - start, 3)

            with ThreadPoolExecutor(max_workers=5) as readers:
                futures = [readers.submit(query) for _ in range(5)]
                query_seconds = [item.result(timeout=25) for item in futures]
            assert not future.done()  # All five complete while rebuild still holds its guard.
            incomplete = PublicSearchService(URL, rebuilding[0], release, runtime).search("Birinci")
            assert incomplete["coverage"]["status"] == "unavailable" and not incomplete["hits"]
        finally:
            proceed.set()
        second = future.result(timeout=60)
    assert second["index"] != first["index"] and second["documents_sha256"] == first["documents_sha256"]
    assert search.search("term", as_of="2011-06-01", authority_id=authority)["hits"] == initial["hits"]

    sealed = IndexTransport(URL, first["index"], time.monotonic() + 30)
    with pytest.raises(ValueError):
        sealed.request("POST", "/_doc/forbidden", body={"text": "must not enter"})
    sealed.request("PUT", "/_settings", body={"index.blocks.write": False})
    assert search.search("Birinci")["coverage"]["status"] == "unavailable"
    sealed.request("PUT", "/_settings", body={"index.blocks.write": True})

    # Cause an actual per-item 409 despite HTTP 200: repeat the first create in
    # the new build's bulk body. Keep its partial index; never alter either ready index.
    def duplicate(self, method, suffix="", **kwargs):
        if suffix == "/_bulk":
            raw = kwargs["ndjson"]
            kwargs["ndjson"] = raw + b"\n".join(raw.splitlines()[:2]) + b"\n"
        return original(self, method, suffix, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(IndexTransport, "request", duplicate)
        with pytest.raises(IndexBuildError) as failed:
            build_index(runtime, URL, release)
    assert failed.value.stage == "write"
    partial = PublicSearchService(URL, failed.value.index, release, runtime).search("Birinci")
    assert partial["coverage"]["status"] == "unavailable"
    assert search.search("term", as_of="2011-06-01", authority_id=authority)["hits"] == initial["hits"]

    # A writer remains excluded through the whole build. Observe PostgreSQL's
    # actual wait, then release the build and wait for the revocation to commit.
    # Searches after that commit must reject all three completed generations.
    ready.clear()
    proceed.clear()
    with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=2) as pool:
        patch.setattr(IndexTransport, "request", hold)
        future = pool.submit(build_index, runtime, URL, release)
        try:
            assert ready.wait(30)
            with observe_identity_lock(fixture["app"].state.store.engine) as observed:
                start = time.monotonic()
                writer = pool.submit(change_second, fixture, "rights")
                assert observed[0].wait(5)
                assert wait_until_blocked(fixture["app"].state.store.engine, observed[1][0])
                assert not writer.done()
                proceed.set()
                third = future.result(timeout=30)
                writer.result(timeout=10)
                revocation_seconds = round(time.monotonic() - start, 3)
        finally:
            proceed.set()
    with monkeypatch.context() as patch:
        patch.setattr(PublicSearchService, "_read_json", lambda *args: pytest.fail("Revoked release contacted OpenSearch"))
        assert search.search("Birinci")["coverage"]["status"] == "unavailable"
        for built in (second, third):
            assert not PublicSearchService(URL, built["index"], release, runtime).search("Birinci")["hits"]
        patch.setattr(IndexTransport, "request", lambda *args, **kwargs: pytest.fail("Revoked build contacted OpenSearch"))
        with pytest.raises(IndexBuildError) as revoked:
            build_index(runtime, URL, release)
        assert revoked.value.stage == "authorization"
    report = {"status": "passed", "synthetic_only": True, "release_id": release,
              "document_count": first["document_count"], "documents_sha256": first["documents_sha256"],
              "first_build_seconds": build_seconds, "indexes_built": 3,
              "private_ledger": "postgresql", "concurrent_searches": 5, "search_seconds_during_rebuild": query_seconds,
              "revocation_wait_and_commit_seconds": revocation_seconds, "partial_indexes_retained_until_cleanup": 1,
              "checks": {name: True for name in ("exact_signed_passages", "historical_interval_filter", "lexical_query",
                  "five_searches_during_locked_rebuild", "revocation_wait_observed_in_postgres", "building_index_denied", "same_inventory_new_index", "write_block_enforced",
                  "writable_index_denied", "real_bulk_item_error_denied", "old_index_preserved_on_failure",
                  "second_source_revocation_blocks_all_indexes_and_rebuild")}}
    print("SEARCH_INDEX_DRILL_REPORT=" + json.dumps(report, sort_keys=True))
