"""Opt-in real OpenSearch drill. The generated internal Docker project is required.

All sources, reviewers, signatures and private ledgers are synthetic test fixtures.
No real-law qualification or existing deployment access is performed.
"""

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from test_release_set_authorization import change_second, guard_set
from test_search_index import Release as SyntheticRelease
from test_search_index import source as synthetic_source
from test_set_authorization_postgres import postgres_authorized_set as postgres_authorized_set_fixture
from test_snapshot_set_postgres import observe_identity_lock, wait_until_blocked
from test_snapshot_set_postgres import postgres_database as postgres_database_fixture

from app.graph_release import RuntimeGraphRelease, _load_serving
from app.retrieval_benchmark import RetrievalBenchmark, capture_run, score_run
from app.search import PublicSearchService
from app.search_index import IndexBuildError, IndexTransport, build_index
from app.search_index_contract import document_id
from app.search_normalization import normalization_metadata

postgres_authorized_set = postgres_authorized_set_fixture
postgres_database = postgres_database_fixture
MARKER = "lawyer-search-index-drill-v5"
URL = "http://opensearch:9200"
pytestmark = pytest.mark.skipif(os.environ.get("LA_SEARCH_INDEX_DRILL") != MARKER,
                                reason="Opt-in disposable OpenSearch qualification only")


def benchmark_fixture(release, built, queries):
    return RetrievalBenchmark.model_validate({"schema_version": "retrieval-development-benchmark-v1",
        "dataset_id": "invented-opensearch-benchmark", "purpose": "development", "origin": "synthetic",
        "adjudication_status": "pending", "adjudication_evidence_sha256": None,
        "snapshot": {"release_id": release.info["release_id"], "serving_sha256": release.info["serving_sha256"],
            "activation_sequence": release.info["pointer"]["sequence"], "index": built["index"],
            "documents_sha256": built["documents_sha256"], "index_schema": built["schema"],
            "normalization": built["normalization"], "citation_profile": built["citation_profile"], "fusion": "rrf-k60-v1"},
        "queries": [{"id": f"synthetic-{position}", "query": query, "family_sha256": hashlib.sha256(str(position).encode()).hexdigest(),
            "practice": ("contracts", "commercial", "employment")[position % 3], "period": "unknown", "slices": ["citation"],
            "as_of": "2011-06-01", "corpus_coverage": "covered", "exact_target": None,
            "judgments": [{"authority_id": target, "relevance": 3, "adverse": False} for target in targets]}
            for position, (query, targets) in enumerate(queries)]})


def test_real_literal_citations_remain_distinct_unresolved_and_source_backed(tmp_path):
    (tmp_path / "publication.lock").touch()
    texts = {"esas_a": "Esas Sayısı: 2099/0007", "esas_b": "E. 2099 / 0007", "karar": "Karar No: 2099/0007",
             "short_number": "E. 2099/7", "application": "Başvuru Numarası: 2099/0007",
             "law": "999999 sayılı Kanun", "unlabeled": "2099/0007, m. 7", "expired": "E. 2099/0007"}
    rows = []
    for ident, text in texts.items():
        row = {**synthetic_source("urn:test:assertion:" + ident), "text": text,
               "passage_id": "urn:test:passage:" + ident, "authority_id": "urn:test:authority:" + ident,
               "source_sha256": hashlib.sha256(text.encode()).hexdigest(), "title": "SENTETİK"}
        if ident == "expired":
            row.update(valid_from="1999-01-01", valid_to="2001-01-01")
        rows.append(row)
    release = SyntheticRelease(tmp_path, rows)
    built = build_index(release, URL, release.info["release_id"])
    search = PublicSearchService(URL, built["index"], release.info["release_id"], release)
    cases = [("E. 2099/0007", {"esas_a", "esas_b"}), ("Esas No: 2099 / 0007", {"esas_a", "esas_b"}),
             ("K. 2099/0007", {"karar"}), ("B. No: 2099/0007", {"application"}),
             ("E. 2099/7", {"short_number"}), ("Kanun No: 999999", {"law"}),
             ("E. 2099/0007, K. 2099/0007", {"esas_a", "esas_b", "karar"})]
    for query, expected in cases:
        result = search.search(query, as_of="2011-01-01")
        assert result["coverage"]["status"] == "available"
        matches = {hit["passage_id"].rsplit(":", 1)[-1]: hit for hit in result["hits"] if "literal_citation" in hit["channels"]}
        assert set(matches) == expected
        for ident, hit in matches.items():
            assert hit["text"] == texts[ident] and hit["literal_citations"]["resolution"] == "unresolved"
            assert hit["literal_citations"]["occurrences"]
            assert "citation_keys" not in hit
            for occurrence in hit["literal_citations"]["occurrences"]:
                assert hit[occurrence["field"]][occurrence["start"]:occurrence["end"]] == occurrence["literal"]
    plain = search.search("2099/0007", as_of="2011-01-01")
    assert plain["coverage"]["channels"]["literal_citation"] == "not_requested"
    release.info = {**release.info, "serving_sha256": "f" * 64, "pointer": {"sequence": 1}}
    benchmark = benchmark_fixture(release, built, [
        ("Kanun No: 999999", ["urn:test:authority:law"]),
        ("E. 2099/0007", ["urn:test:authority:esas_a", "urn:test:authority:esas_b"]),
        ("B. No: 2099/0007", ["urn:test:authority:application"])])
    captured = capture_run(benchmark, search)
    scored = score_run(benchmark, captured)
    assert len(captured.observations) == 9 and all(row.status == "available" for row in captured.observations)
    assert scored["production_qualified"] is False and scored["runtime_authorization"] == "none"
    assert all(scored["profiles"][profile]["recall_at_20"]["value"] == 1.0 for profile in ("lexical", "turkish", "all"))
    print("\nRETRIEVAL_BENCHMARK_DRILL_REPORT=" + json.dumps({
        "status": "passed", "synthetic_only": True, "projection": "explicit_fixture_only",
        "queries": scored["queries"], "observations": len(captured.observations),
        "benchmark_sha256": scored["benchmark_sha256"], "paired": scored["paired"],
        "metrics": {profile: {metric: values[metric] for metric in ("recall_at_20", "ndcg_at_10", "adverse_recall_at_20", "exact_target_hit_at_20")}
                    for profile, values in scored["profiles"].items()},
        "checks": {name: True for name in ("same_index_and_snapshot", "all_query_profile_cells",
            "real_opensearch_profiles", "complete_cohort_denominators", "non_authorizing_report")}}, sort_keys=True))
    # A privileged index writer can forge derived keys, but cannot cause the
    # reader to claim a citation occurrence absent from verified source text.
    transport = IndexTransport(URL, built["index"], time.monotonic() + 30)
    transport.request("PUT", "/_settings", body={"index.blocks.write": False})
    transport.request("POST", "/_update/" + document_id(rows[0]), body={"doc": {"citation_keys": ["esas:2099:9999"]}})
    transport.request("POST", "/_refresh")
    transport.request("PUT", "/_settings", body={"index.blocks.write": True})
    poisoned = search.search("E. 2099/9999", as_of="2011-01-01")
    assert poisoned["coverage"]["rejected_hits"] >= 1
    assert not any("literal_citation" in hit["channels"] for hit in poisoned["hits"])
    print("\nCITATION_RETRIEVAL_DRILL_REPORT=" + json.dumps({
        "status": "passed", "synthetic_only": True, "projection": "explicit_fixture_only",
        "index_schema": built["schema"], "citation_profile": built["citation_profile"],
        "document_count": len(rows), "targeted_cases_passed": len(cases),
        "checks": {name: True for name in ("typed_role_separation", "leading_zeros_preserved", "unresolved_collisions",
            "original_literal_spans", "historical_prefilters", "unlabeled_numbers_not_resolved",
            "no_pairing_inference", "forged_keyword_rejected_against_source")}}, sort_keys=True))


def test_real_turkish_fields_channels_and_exact_offsets(tmp_path):
    """Real index transport with an explicit fixture projection; no legal review.

    The separate lifecycle test below exercises actual signed-source projection
    and PostgreSQL private authorization, including source revocation.
    """
    (tmp_path / "publication.lock").touch()
    texts = {"uppercase": "İŞÇİ ücret talep eder.", "decomposed": "I\u0307S\u0327C\u0327I\u0307 beyanı.",
             "dotless": "IŞIK altında kayıt.", "apostrophe": "İŞÇİ’NİN beyanı.",
             "accent": "SÖZLEŞME ihlali.", "negative": "Sorumlu değildir; ödeme yapmadı.",
             "numbers": "E. 2020/00123 K. 2021/09 -1.250,50",
             "plain": "kar birikimi", "circumflex": "kâr oranı", "title": "Başka bir örnek.",
             "expired": "İŞÇİ tarihsel örnek."}
    rows = []
    for ident, text in texts.items():
        row = {**synthetic_source("urn:test:assertion:" + ident), "text": text,
               "passage_id": "urn:test:passage:" + ident, "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
               "title": "ÇALIŞMA" if ident == "title" else "SENTETİK"}
        if ident == "expired":
            row.update(valid_from="1999-01-01", valid_to="2001-01-01")
        rows.append(row)
    release = SyntheticRelease(tmp_path, rows)
    built = build_index(release, URL, release.info["release_id"])
    search = PublicSearchService(URL, built["index"], release.info["release_id"], release)
    cases = [("İŞÇİ", "uppercase", "lexical_original"), ("işçi", "uppercase", "lexical_normalized"),
             ("işçi", "decomposed", "lexical_normalized"), ("ışık", "dotless", "lexical_normalized"),
             ("işçi'nin", "apostrophe", "lexical_normalized"), ("sozlesme", "accent", "lexical_folded"),
             ("değildir", "negative", "lexical_normalized"), ("2020/00123", "numbers", "lexical_original"),
             ("-1.250,50", "numbers", "lexical_normalized"), ("calisma", "title", "lexical_folded")]
    for query, ident, channel in cases:
        result = search.search(query, as_of="2011-01-01")
        assert result["coverage"]["status"] == "available"
        candidates = {hit["passage_id"].rsplit(":", 1)[-1]: hit for hit in result["hits"]}
        assert ident in candidates and channel in candidates[ident]["channels"]
        assert "expired" not in candidates
        assert candidates[ident]["text"] == texts[ident]
        assert candidates[ident]["matches"]["spans"]
        assert all(hit["text"] == texts[key] for key, hit in candidates.items())
        for hit in candidates.values():
            for span in hit["matches"]["spans"]:
                assert hit[span["field"]][span["start"]:span["end"]]
        if ident == "decomposed":
            hit = candidates[ident]
            span = hit["matches"]["spans"][0]
            assert hit["text"][span["start"]:span["end"]] == "I\u0307S\u0327C\u0327I\u0307"
        if ident == "accent":
            assert candidates[ident]["channels"] == ["lexical_folded"]
    aliases = search.search("kar", as_of="2011-01-01")["hits"]
    assert {hit["text"] for hit in aliases} == {"kar birikimi", "kâr oranı"}
    assert len({hit["assertion_id"] for hit in aliases}) == 2
    print("\nTURKISH_RETRIEVAL_DRILL_REPORT=" + json.dumps({
        "status": "passed", "synthetic_only": True, "projection": "explicit_fixture_only",
        "normalization": normalization_metadata(), "index_schema": built["schema"],
        "document_count": len(rows), "targeted_cases_passed": len(cases),
        "checks": {name: True for name in ("independent_channels", "folded_only_discovery", "original_text_unchanged",
            "decomposed_exact_offsets", "negative_and_numeric_tokens", "title_matches", "historical_prefilters",
            "folded_collisions_do_not_merge_identities")}}, sort_keys=True))


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
    benchmark = benchmark_fixture(runtime, first, [("Birinci", sorted({row["authority_id"] for row in expected}))])
    captured = capture_run(benchmark, search)
    assert len(captured.observations) == 3 and all(row.status == "available" and row.authority_ids for row in captured.observations)
    assert score_run(benchmark, captured)["production_qualified"] is False

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
                  "signed_source_benchmark_capture",
                  "five_searches_during_locked_rebuild", "revocation_wait_observed_in_postgres", "building_index_denied", "same_inventory_new_index", "write_block_enforced",
                  "writable_index_denied", "real_bulk_item_error_denied", "old_index_preserved_on_failure",
                  "second_source_revocation_blocks_all_indexes_and_rebuild")}}
    print("\nSEARCH_INDEX_DRILL_REPORT=" + json.dumps(report, sort_keys=True))
