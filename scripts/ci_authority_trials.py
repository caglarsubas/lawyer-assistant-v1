"""Closed, source-bound placement of unchanged trial and graph boundary tests."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/tests/test_authority_trials.py"
MANIFEST = ROOT / "deploy/fixtures/authority_trial_partition.json"
SOURCES = {"backend/tests/test_authority_trials.py": 37, "backend/tests/test_graph.py": 58}
COUNTS = {"final": 28, "candidate": 12, "publication": 8, "analysis": 6, "graph": 2, "history": 39}
PRIORITY = ("tests/test_graph.py::test_two_hop_expansion_stops_before_third_hop",)


@dataclass(frozen=True)
class Contract:
    source_sha256: dict[str, str]
    ids: tuple[str, ...]
    lanes: dict[str, tuple[str, ...]]

    def includes(self, nodeid):
        return any(nodeid.startswith(path.removeprefix("backend/") + "::") for path in SOURCES)

    @property
    def inventory_sha256(self):
        return hashlib.sha256(json.dumps(self.ids, separators=(",", ":")).encode()).hexdigest()


def load_contract(path=MANIFEST, source=SOURCE):
    raw = path.read_bytes()
    if len(raw) > 65536:
        raise ValueError("Backend capacity manifest exceeds its budget")
    value = json.loads(raw)
    hashes = {p: hashlib.sha256((source if p == "backend/tests/test_authority_trials.py"
                                else ROOT / p).read_bytes()).hexdigest() for p in SOURCES}
    if (not isinstance(value, dict) or set(value) != {"schema", "sources", "test_ids", "lanes", "priority_ids"}
            or value["schema"] != "backend-capacity-ci-partition-v2" or value["sources"] != hashes
            or value["priority_ids"] != list(PRIORITY)):
        raise ValueError("Backend capacity sources or manifest changed")
    ids, lanes = value["test_ids"], value["lanes"]
    if (not isinstance(ids, list) or len(ids) != 95
            or any(not isinstance(x, str) or len(x) > 1024 for x in ids)
            or ids != sorted(set(ids)) or not set(PRIORITY) <= set(ids)
            or not isinstance(lanes, dict) or set(lanes) != set(COUNTS)):
        raise ValueError("Backend capacity inventory is not closed")
    for p, count in SOURCES.items():
        if sum(n.startswith(p.removeprefix("backend/") + "::") for n in ids) != count:
            raise ValueError("Backend capacity source inventory differs")
    combined = []
    for lane, count in COUNTS.items():
        rows = lanes[lane]
        if not isinstance(rows, list) or len(rows) != count or rows != sorted(set(rows)):
            raise ValueError("Backend capacity lane is not closed")
        combined.extend(rows)
    if sorted(combined) != ids or len(set(combined)) != 95:
        raise ValueError("Every backend capacity identity must occur once")
    return Contract(hashes, tuple(ids), {k: tuple(v) for k, v in lanes.items()})


def select(contract, lane, nodeids):
    if lane not in contract.lanes or len(nodeids) != len(set(nodeids)):
        raise ValueError("Unknown backend capacity lane or duplicate collection")
    if sorted(x for x in nodeids if contract.includes(x)) != list(contract.ids):
        raise ValueError("Full backend capacity collection differs from its manifest")
    wanted = set(contract.lanes[lane])
    kept = [x for x in nodeids if not contract.includes(x) or x in wanted]
    # The measured indivisible13-second case starts before short queued work.
    # All other identities keep their original relative ordering.
    return [x for x in PRIORITY if x in wanted] + [x for x in kept if x not in PRIORITY]


class Partition:
    def __init__(self, contract, lane):
        if lane not in contract.lanes:
            raise ValueError("Unknown backend capacity lane")
        self.contract, self.lane = contract, lane
        self.passed, self.valid = {}, False

    @pytest.hookimpl(tryfirst=True)
    def pytest_collection_modifyitems(self, config, items):
        try:
            selected = select(self.contract, self.lane, [x.nodeid for x in items])
        except ValueError as exc:
            raise pytest.UsageError(str(exc)) from None
        by_id = {x.nodeid: x for x in items}
        removed = [x for x in items if x.nodeid not in set(selected)]
        items[:] = [by_id[n] for n in selected]
        config.hook.pytest_deselected(items=removed)

    @pytest.hookimpl(optionalhook=True)
    def pytest_xdist_node_collection_finished(self, ids):
        if (sorted(x for x in ids if self.contract.includes(x)) != list(self.contract.lanes[self.lane])
                or len(ids) != len(set(ids))):
            raise pytest.UsageError("Worker backend capacity IDs differ")

    def pytest_runtest_logreport(self, report):
        if (report.when == "call" and report.passed and not getattr(report, "wasxfail", False)
                and self.contract.includes(report.nodeid)):
            self.passed[report.nodeid] = self.passed.get(report.nodeid, 0) + 1

    def pytest_sessionfinish(self, session, exitstatus):
        if hasattr(session.config, "workerinput") or session.config.getoption("collectonly"):
            return
        self.valid = (exitstatus == 0 and set(self.passed) == set(self.contract.lanes[self.lane])
                      and all(n == 1 for n in self.passed.values()))
        if exitstatus == 0 and not self.valid:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter, exitstatus):
        if self.valid and exitstatus == 0 and not hasattr(terminalreporter.config, "workerinput"):
            terminalreporter.write_line(json.dumps({"backend_capacity_partition": self.lane,
                "source_sha256": self.contract.source_sha256,
                "inventory_sha256": self.contract.inventory_sha256,
                "complete_count": 95,
                "selected_ids_sha256": sorted(hashlib.sha256(n.encode()).hexdigest() for n in self.passed)}))


def pytest_addoption(parser):
    parser.addoption("--authority-trial-lane", choices=tuple(COUNTS))


def pytest_configure(config):
    try:
        if (not hasattr(config, "workerinput") and not config.getoption("collectonly")
                and config.getoption("numprocesses", default=None) != 2):
            raise ValueError("Exactly two existing workers required")
        config.pluginmanager.register(Partition(load_contract(), config.getoption("authority_trial_lane")),
                                      "closed-backend-capacity-partition")
    except (ValueError, OSError, KeyError, TypeError):
        raise pytest.UsageError("Closed backend capacity sources, inventory and lane required") from None
