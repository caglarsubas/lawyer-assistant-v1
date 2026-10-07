"""Development metrics/receipts are measurable; synthetic scores grant no approval."""

import copy
import importlib.util
import json
import math
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_search_index import INDEX, RELEASE
from test_search_index import case as index_case_fixture

from app import retrieval_benchmark as benchmark_module
from app.qualification_scoring import digest
from app.retrieval_benchmark import RetrievalBenchmark, capture_run, query_metrics, score_run
from app.search import PublicSearchService
from app.search_index import build_index

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_retrieval_benchmark_fixture import fixture_inputs  # noqa: E402

SPEC = importlib.util.spec_from_file_location("benchmark_cli_tests", ROOT / "scripts/benchmark_retrieval.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)
case = index_case_fixture


def mutable_fixture():
    benchmark, run = fixture_inputs()
    return benchmark.model_dump(mode="json"), run.model_dump(mode="json")


def repin(benchmark, run):
    run["benchmark_sha256"] = digest(RetrievalBenchmark.model_validate(benchmark).model_dump(mode="json"))


def test_known_rankings_use_graded_ndcg_and_independent_adverse_denominators():
    benchmark, run = fixture_inputs()
    scores = query_metrics(benchmark.queries[0], run.observations[0])
    assert scores["recall_at_20"] == 0.5 and scores["adverse_recall_at_20"] == 0.0
    assert scores["ndcg_at_10"] == pytest.approx((7 / math.log2(3)) / (7 + 3 / math.log2(3)))
    report = score_run(benchmark, run)
    assert report["profiles"]["turkish"]["recall_at_20"] == {"value": 1.0, "queries": 3}
    assert report["profiles"]["lexical"]["exact_target_hit_at_20"] == {"value": 1.0, "queries": 1}
    assert report["paired"][0]["metrics"]["recall_at_20"]["interval_95"] == [0.5, 0.5]
    assert report["origin"] == "synthetic" and report["production_qualified"] is False
    assert report["runtime_authorization"] == "none"
    assert report["profiles"]["all"]["by_practice"]["employment"]["queries"] == 1
    assert report["profiles"]["all"]["by_slice"]["citation"]["queries"] == 1


@pytest.mark.parametrize("status", ["partial", "unavailable", "not_run"])
def test_failed_and_unexecuted_queries_are_misses_and_never_vanish_from_aggregate(status):
    benchmark, run = mutable_fixture()
    row = run["observations"][1]
    row.update(status=status, authority_ids=[], returned_passages=0, elapsed_seconds=0.0)
    report = score_run(benchmark, run)
    assert report["profiles"]["turkish"]["recall_at_20"] == {"value": 2 / 3, "queries": 3}
    assert report["profiles"]["turkish"]["statuses"][status] == 1
    paired = report["paired"][0]["metrics"]["recall_at_20"]
    assert paired["paired_queries"] == 2 and paired["excluded_queries"] == 1


def test_unknown_coverage_and_empty_gold_are_unmeasured_while_unjudged_hits_are_counted():
    benchmark, run = mutable_fixture()
    benchmark["queries"][0]["corpus_coverage"] = "unknown"
    benchmark["queries"][1].update(judgments=[], exact_target=None)
    run["observations"][7]["authority_ids"].append("urn:test:unjudged")
    run["observations"][7]["returned_passages"] += 1
    repin(benchmark, run)
    report = score_run(benchmark, run)
    assert report["profiles"]["turkish"]["recall_at_20"]["queries"] == 1
    assert report["profiles"]["turkish"]["unjudged_authorities"] == 3
    assert report["profiles"]["turkish"]["exact_target_hit_at_20"]["value"] is None


def test_correlated_queries_share_one_bootstrap_block_and_tiny_cohorts_have_no_interval():
    benchmark, run = mutable_fixture()
    for query in benchmark["queries"]:
        query["family_sha256"] = "f" * 64
    repin(benchmark, run)
    first = score_run(benchmark, run)
    assert first == score_run(benchmark, run)
    result = first["paired"][0]["metrics"]["recall_at_20"]
    assert result["paired_queries"] == 3 and result["independent_families_declared"] == 1
    assert result["interval_95"] is None


@pytest.mark.parametrize("mutation", ["missing_cell", "duplicate_cell", "unknown_query", "snapshot", "benchmark_hash",
                                       "duplicate_authority", "too_many_hits", "negative_time", "nan", "unavailable_hits"])
def test_invalid_or_mixed_run_is_rejected(mutation):
    benchmark, run = mutable_fixture()
    if mutation == "missing_cell":
        run["observations"].pop()
    elif mutation == "duplicate_cell":
        run["observations"].append(copy.deepcopy(run["observations"][0]))
    elif mutation == "unknown_query":
        run["observations"][0]["query_id"] = "unknown-query"
    elif mutation == "snapshot":
        run["snapshot"]["documents_sha256"] = "e" * 64
    elif mutation == "benchmark_hash":
        run["benchmark_sha256"] = "0" * 64
    elif mutation == "duplicate_authority":
        run["observations"][0]["authority_ids"] *= 2
    elif mutation == "too_many_hits":
        run["observations"][0]["returned_passages"] = 21
    elif mutation == "negative_time":
        run["observations"][0]["elapsed_seconds"] = -1.0
    elif mutation == "nan":
        run["observations"][0]["elapsed_seconds"] = math.nan
    else:
        run["observations"][0]["status"] = "unavailable"
    with pytest.raises(ValueError):
        score_run(benchmark, run)


@pytest.mark.parametrize("mutation", ["index_release", "unicode", "duplicate_query", "duplicate_text", "unjudged_target",
                                       "duplicate_judgment", "adverse_zero", "unreviewed_evidence", "bad_date", "private_period"])
def test_invalid_benchmark_relationships_rejected(mutation):
    benchmark, _ = mutable_fixture()
    if mutation == "index_release":
        benchmark["snapshot"]["release_id"] = "0" * 64
    elif mutation == "unicode":
        benchmark["snapshot"]["normalization"]["unicode_version"] = "unknown"
    elif mutation == "duplicate_query":
        benchmark["queries"].append(copy.deepcopy(benchmark["queries"][0]))
    elif mutation == "duplicate_text":
        benchmark["queries"][1]["query"] = benchmark["queries"][0]["query"]
    elif mutation == "unjudged_target":
        benchmark["queries"][0]["exact_target"] = "urn:test:missing"
    elif mutation == "duplicate_judgment":
        benchmark["queries"][0]["judgments"].append(copy.deepcopy(benchmark["queries"][0]["judgments"][0]))
    elif mutation == "adverse_zero":
        benchmark["queries"][0]["judgments"][2]["adverse"] = True
    elif mutation == "unreviewed_evidence":
        benchmark["adjudication_status"] = "adjudicated"
    elif mutation == "bad_date":
        benchmark["queries"][0]["as_of"] = "2011-02-30"
    else:
        benchmark["queries"][0]["period"] = "PRIVATE-CUSTOMER"
    with pytest.raises(ValueError):
        RetrievalBenchmark.model_validate(benchmark)


def ready_benchmark(release, built):
    benchmark, _ = mutable_fixture()
    release.info = {**release.info, "serving_sha256": "c" * 64, "pointer": {"sequence": 1}}
    benchmark["snapshot"].update(index=built["index"], release_id=RELEASE,
        documents_sha256=built["documents_sha256"], normalization=built["normalization"])
    return RetrievalBenchmark.model_validate(benchmark)


def test_capture_uses_every_profile_with_original_projection_and_no_repeated_authority_credit(case):
    release, server = case
    release.rows.append({**release.rows[0], "assertion_id": "urn:test:assertion:second"})
    built = build_index(release, "http://opensearch:9200", RELEASE)
    benchmark = ready_benchmark(release, built)
    search = PublicSearchService("http://opensearch:9200", INDEX, RELEASE, release)
    server.calls.clear()
    captured = capture_run(benchmark, search)
    assert len(captured.observations) == 9
    assert all(row.authority_ids == [release.rows[0]["authority_id"]] and row.returned_passages == 2 for row in captured.observations)
    assert [row.profile for row in captured.observations] == ["lexical", "turkish", "all", "turkish", "all", "lexical", "all", "lexical", "turkish"]
    assert "query" not in captured.model_dump(mode="json")
    report = score_run(benchmark, captured)
    assert report["profiles"]["all"]["returned_unique_authorities"] == 3
    assert report["profiles"]["all"]["returned_passages"] == 6


def test_capture_total_budget_retains_all_not_run_cells_without_search_traffic(case, monkeypatch):
    release, server = case
    built = build_index(release, "http://opensearch:9200", RELEASE)
    benchmark = ready_benchmark(release, built)
    search = PublicSearchService("http://opensearch:9200", INDEX, RELEASE, release)
    counter = iter(range(100))
    started = time.monotonic()
    monkeypatch.setattr(benchmark_module, "time", SimpleNamespace(monotonic=lambda: started + next(counter) * 1000))
    server.calls.clear()
    captured = capture_run(benchmark, search, seconds=1)
    assert len(captured.observations) == 9 and all(row.status == "not_run" for row in captured.observations)
    assert all(not call.url.path.endswith("/_search") for call in server.calls)
    assert score_run(benchmark, captured)["profiles"]["all"]["recall_at_20"]["value"] == 0.0


@pytest.mark.parametrize("change", ["revocation", "receipt", "activation"])
def test_capture_discards_all_measurements_on_permission_or_snapshot_changes(case, monkeypatch, change):
    release, server = case
    built = build_index(release, "http://opensearch:9200", RELEASE)
    benchmark = ready_benchmark(release, built)
    search = PublicSearchService("http://opensearch:9200", INDEX, RELEASE, release)
    original = search.search
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if change == "revocation":
            release.active = False
        elif change == "receipt":
            server.mapping["_meta"]["documents_sha256"] = "e" * 64
        else:
            release.info["pointer"]["sequence"] += 1
        return result
    monkeypatch.setattr(search, "search", changed)
    with pytest.raises(ValueError):
        capture_run(benchmark, search)


def input_files(tmp_path):
    benchmark, run = mutable_fixture()
    benchmark["queries"][0]["query"] = "PRIVATE-QUERY-MARKER"
    repin(benchmark, run)
    paths = tmp_path / "benchmark.json", tmp_path / "run.json"
    for path, content in zip(paths, (benchmark, run), strict=True):
        path.write_text(json.dumps(content))
    return paths


def test_cli_report_contains_aggregates_and_digests_without_queries_ids_or_paths(tmp_path, capsys):
    benchmark, run = input_files(tmp_path)
    assert cli.main([str(benchmark), "--run", str(run)]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["production_qualified"] is False
    for private in ("PRIVATE-QUERY-MARKER", "urn:test:positive", str(tmp_path), "synthetic-0"):
        assert private not in captured.out
    assert report["input_files"]["benchmark"]["bytes"] == benchmark.stat().st_size


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "directory", "oversized", "malformed"])
def test_cli_rejects_unsafe_or_malformed_files_without_echoing_private_data(tmp_path, capsys, kind):
    benchmark, run = input_files(tmp_path)
    if kind == "hardlink":
        os.link(benchmark, tmp_path / "linked")
    elif kind == "malformed":
        benchmark.write_text('{"PRIVATE-QUERY-MARKER":NaN}')
    else:
        benchmark.unlink()
        if kind == "symlink":
            benchmark.symlink_to(run)
        elif kind == "fifo":
            os.mkfifo(benchmark)
        elif kind == "directory":
            benchmark.mkdir()
        else:
            with benchmark.open("wb") as stream:
                stream.truncate(cli.MAX_COMPONENT_BYTES + 1)
    assert cli.main([str(benchmark), "--run", str(run)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "PRIVATE-QUERY-MARKER" not in captured.err and str(tmp_path) not in captured.err


def test_cli_recaptures_input_changes_before_reporting(tmp_path, capsys, monkeypatch):
    benchmark, run = input_files(tmp_path)
    original = cli.score_run
    def changed(*args):
        result = original(*args)
        run.write_bytes(run.read_bytes() + b"\n")
        return result
    monkeypatch.setattr(cli, "score_run", changed)
    assert cli.main([str(benchmark), "--run", str(run)]) == 2
    assert capsys.readouterr().out == ""


def test_cli_schemas_require_no_files_or_configuration(capsys):
    assert cli.main(["--schemas"]) == 0
    assert json.loads(capsys.readouterr().out)["runtime_authorization"] == "none"
    assert cli.main(["--unknown"]) == 2
    assert capsys.readouterr().out == ""
