"""Reject missing coverage and unmeasured capacity without changing legal tests."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import ci_metadata_capacity as capacity  # noqa: E402


def test_original_cases_are_disjoint_and_fit_all_six_measured_increments():
    contract = capacity.load_contract()
    value = json.loads(capacity.MANIFEST.read_bytes())
    rows = [n for ids in contract.lanes.values() for n in ids]
    assert len(rows) == len(set(rows)) == 44
    assert sorted(rows) == list(contract.ids)
    assert [sum(n.startswith(p.removeprefix("backend/") + "::") for n in rows)
            for p in capacity.SOURCES] == [32, 12]
    for lane, ids in contract.lanes.items():
        assert capacity.estimated_increment(ids, value["case_cost_ms"]) <= capacity.BUDGETS[lane]


@pytest.mark.parametrize("change", ["source", "missing", "overlap", "cost", "budget", "bool_cost", "provenance", "unknown", "duplicate_key"])
def test_changed_sources_coverage_or_measured_capacity_cannot_be_admitted(tmp_path, change):
    value = json.loads(capacity.MANIFEST.read_bytes())
    if change == "source":
        value["source_sha256"][capacity.SOURCES[0]] = "f" * 64
    elif change == "missing":
        value["test_ids"].pop()
    elif change == "overlap":
        value["lanes"]["review"][0] = value["lanes"]["frontend"][0]
        value["lanes"]["review"].sort()
    elif change == "cost":
        for n in value["lanes"]["review"]:
            value["case_cost_ms"][n] = 60000
    elif change == "budget":
        value["lane_increment_budget_ms"]["review"] += 1
    elif change == "bool_cost":
        value["case_cost_ms"][value["test_ids"][0]] = True
    elif change == "provenance":
        value["qualification_status"] = "qualified"
    elif change == "unknown":
        value["lanes"]["extra_worker"] = []
    path = tmp_path / "manifest.json"
    raw = json.dumps(value)
    if change == "duplicate_key":
        raw = '{"schema":"unexpected",' + raw[1:]
    path.write_text(raw)
    with pytest.raises((ValueError, TypeError)):
        capacity.load_contract(path)


def test_collection_preserves_other_tests_and_refuses_missing_duplicate_or_invented_cases():
    contract = capacity.load_contract()
    other = "tests/test_other.py::test_retained"
    for ids in (list(contract.ids[:-1]), [*contract.ids, contract.ids[0]],
                [*contract.ids[:-1], "tests/test_analysis_cohorts.py::test_undeclared"]):
        with pytest.raises(ValueError):
            capacity.select(contract, "review", ids)
    with pytest.raises(ValueError):
        capacity.select(contract, "unknown", list(contract.ids))
    assert capacity.select(contract, "review", [other, *contract.ids]) == [other, *contract.lanes["review"]]


def test_worker_inventory_cannot_drop_a_selected_case():
    contract = capacity.load_contract()
    plugin = capacity.Partition(contract, "review")
    plugin.pytest_xdist_node_collection_finished(list(contract.lanes["review"]))
    with pytest.raises(pytest.UsageError):
        plugin.pytest_xdist_node_collection_finished(list(contract.lanes["review"][:-1]))


def test_skip_or_repeated_execution_cannot_publish_an_exact_execution_receipt():
    contract = capacity.load_contract()
    for mode in ("skipped", "duplicate", "xfail"):
        plugin = capacity.Partition(contract, "review")
        for i, nodeid in enumerate(contract.lanes["review"]):
            report = SimpleNamespace(when="call", passed=not (i == 0 and mode == "skipped"),
                                     wasxfail=(i == 0 and mode == "xfail"), nodeid=nodeid)
            plugin.pytest_runtest_logreport(report)
            if i == 0 and mode == "duplicate":
                plugin.pytest_runtest_logreport(report)
        session = SimpleNamespace(config=SimpleNamespace(getoption=lambda _: False), exitstatus=0)
        plugin.pytest_sessionfinish(session, 0)
        lines = []
        plugin.pytest_terminal_summary(SimpleNamespace(config=session.config, write_line=lines.append), session.exitstatus)
        assert session.exitstatus == pytest.ExitCode.TESTS_FAILED and lines == []


def test_manifest_size_is_bounded_before_parsing(tmp_path):
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * 65537)
    with pytest.raises(ValueError, match="exceeds"):
        capacity.load_contract(path)
