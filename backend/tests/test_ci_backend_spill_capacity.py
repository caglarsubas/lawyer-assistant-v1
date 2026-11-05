"""Keep every original backend spill case and refuse partial execution receipts."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import ci_backend_spill_capacity as capacity  # noqa: E402


def test_closed_source_and_complete_inventory_cannot_be_changed_or_omitted(tmp_path):
    c = capacity.load_contract()
    assert len(c.ids) == 99 and len(c.lanes) == 13
    assert len(c.lanes["backend"]) == 19 and c.lanes["review"] == c.lanes["final"] == ()
    assert set(c.lanes["analysis"]).isdisjoint(c.lanes["history"])
    rows = [n for values in c.lanes.values() for n in values]
    assert len(rows) == len(set(rows)) == 99 and set(rows) == set(c.ids)
    for mode in ("source", "missing", "overlap", "unknown"):
        v = json.loads(capacity.MANIFEST.read_bytes())
        if mode == "source":
            v["source_sha256"][capacity.SOURCES[0]] = "0" * 64
        elif mode == "missing":
            v["test_ids"].pop()
        elif mode == "overlap":
            v["lanes"]["analysis"][0] = v["lanes"]["history"][0]
            v["lanes"]["analysis"].sort()
        else:
            v["lanes"]["third_worker"] = []
        p = tmp_path / "profile.json"
        p.write_text(json.dumps(v))
        with pytest.raises(ValueError):
            capacity.load_contract(p)


def test_selection_keeps_other_cases_and_refuses_incomplete_duplicate_or_unknown_collection():
    c = capacity.load_contract()
    other = "tests/other.py::test_retained"
    assert capacity.select(c, "analysis", [other, *c.ids]) == [other, *c.lanes["analysis"]]
    for ids in (list(c.ids[:-1]), [*c.ids, c.ids[0]]):
        with pytest.raises(ValueError):
            capacity.select(c, "analysis", ids)
    with pytest.raises(ValueError):
        capacity.select(c, "unregistered", list(c.ids))


def test_only_complete_once_non_xfailed_execution_can_publish_a_receipt():
    c = capacity.load_contract()
    for mode in ("valid", "skipped", "duplicate", "xfail"):
        p = capacity.Partition(c, "analysis")
        for i, node in enumerate(c.lanes["analysis"]):
            r = SimpleNamespace(nodeid=node, when="call", passed=not (mode == "skipped" and i == 0),
                                wasxfail=(mode == "xfail" and i == 0))
            p.pytest_runtest_logreport(r)
            if mode == "duplicate" and i == 0:
                p.pytest_runtest_logreport(r)
        session = SimpleNamespace(config=SimpleNamespace(getoption=lambda _: False), exitstatus=0)
        p.pytest_sessionfinish(session, 0)
        lines = []
        p.pytest_terminal_summary(SimpleNamespace(config=session.config, write_line=lines.append), session.exitstatus)
        if mode == "valid":
            assert session.exitstatus == 0 and json.loads(lines[0])["selected_ids"] == list(c.lanes["analysis"])
        else:
            assert session.exitstatus == pytest.ExitCode.TESTS_FAILED and lines == []
