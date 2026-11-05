"""Preserve authorization coverage and prove the locked initial worker schedule."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from xdist.scheduler.load import LoadScheduling

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import ci_final_auth_capacity as capacity  # noqa: E402


def test_source_inventory_and_malformed_profiles_cannot_lose_authorization_cases(tmp_path):
    c = capacity.load_contract()
    assert len(c.ids) == 10 and len(c.lanes["final"]) == 8 and len(c.lanes["graph"]) == 2
    assert set(c.lanes["final"]).isdisjoint(c.lanes["graph"])
    assert set(c.lanes["final"]) | set(c.lanes["graph"]) == set(c.ids)
    for change in ("source", "missing", "overlap", "scheduler", "budget"):
        v = json.loads(capacity.MANIFEST.read_bytes())
        if change == "source":
            v["source_sha256"] = "f" * 64
        elif change == "missing":
            v["test_ids"].pop()
        elif change == "overlap":
            v["lanes"]["final"][0] = v["lanes"]["graph"][0]
        elif change == "scheduler":
            v["worker_positions"] = [0, 1]
        else:
            v["moved_case_cpu_upper_ms"][capacity.MOVED[0]] = 15001
        p = tmp_path / "profile.json"
        p.write_text(json.dumps(v))
        with pytest.raises(ValueError):
            capacity.load_contract(p)


def test_locked_scheduler_starts_moved_cases_on_different_workers_without_losing_other_cases():
    c = capacity.load_contract()
    others = ["tests/other.py::test_first", "tests/other.py::test_second"]
    ids = capacity.balanced(c, "graph", [*c.ids, *others])
    assert set(ids) == set(c.lanes["graph"]) | set(others) and len(ids) == 4

    class Node:
        def __init__(self):
            self.assigned = []
            self.gateway = SimpleNamespace(id="synthetic-node")
        def send_runtest_some(self, indices):
            self.assigned.extend(ids[i] for i in indices)
        def shutdown(self):
            pass

    nodes = [Node(), Node()]
    scheduler = LoadScheduling.__new__(LoadScheduling)
    scheduler.numnodes, scheduler.collection, scheduler.maxschedchunk = 2, None, 1
    scheduler.node2collection = dict.fromkeys(nodes, ids)
    scheduler.node2pending = {n: [] for n in nodes}
    scheduler.pending = []
    scheduler.schedule()
    assert capacity.MOVED[0] in nodes[0].assigned and capacity.MOVED[1] in nodes[1].assigned
    assert sorted(n for worker in nodes for n in worker.assigned) == sorted(ids)


def test_receipt_requires_complete_once_execution_and_distinct_real_worker_observations():
    c = capacity.load_contract()
    for mode in ("valid", "same_worker", "skip", "duplicate"):
        plugin = capacity.Partition(c, "graph")
        for i, nodeid in enumerate(c.lanes["graph"]):
            report = SimpleNamespace(when="call", passed=not (mode == "skip" and i == 0), nodeid=nodeid,
                                     worker_id="gw0" if mode == "same_worker" else "gw" + str(i))
            plugin.pytest_runtest_logreport(report)
            if mode == "duplicate" and i == 0:
                plugin.pytest_runtest_logreport(report)
        session = SimpleNamespace(config=SimpleNamespace(getoption=lambda _: False), exitstatus=0)
        plugin.pytest_sessionfinish(session, 0)
        lines = []
        plugin.pytest_terminal_summary(SimpleNamespace(config=session.config, write_line=lines.append), session.exitstatus)
        if mode == "valid":
            receipt = json.loads(lines[0])
            assert session.exitstatus == 0 and receipt["selected_ids"] == list(c.lanes["graph"])
            assert set(receipt["worker_ids"].values()) == {"gw0", "gw1"} and receipt["complete_count"] == 10
        else:
            assert session.exitstatus == pytest.ExitCode.TESTS_FAILED and lines == []
