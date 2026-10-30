"""Closed, source-bound CI placement without dropping or renaming cohort tests."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/tests/test_authority_model_cohorts.py"
MANIFEST = ROOT / "deploy/fixtures/authority_cohort_partition.json"
PREFIX = "tests/test_authority_model_cohorts.py::"
COUNTS = {"review": 16, "database": 1, "history": 2}


@dataclass(frozen=True)
class Contract:
    source_sha256: str
    ids: tuple[str, ...]
    lanes: dict[str, tuple[str, ...]]

    @property
    def prefix(self):
        return self.ids[0].split("::", 1)[0] + "::"

    @property
    def inventory_sha256(self):
        return hashlib.sha256(json.dumps(self.ids, separators=(",", ":")).encode()).hexdigest()


def load_contract(path=MANIFEST, source=SOURCE):
    raw = path.read_bytes()
    if len(raw) > 65536:
        raise ValueError("Cohort manifest exceeds its closed budget")
    value = json.loads(raw)
    if (not isinstance(value, dict) or set(value) != {"schema", "source_path", "source_sha256", "test_ids", "lanes"}
            or value["schema"] != "authority-cohort-ci-partition-v1"
            or value["source_path"] != "backend/tests/test_authority_model_cohorts.py"
            or value["source_sha256"] != hashlib.sha256(source.read_bytes()).hexdigest()):
        raise ValueError("Cohort source or manifest changed")
    ids, lanes = value["test_ids"], value["lanes"]
    if (not isinstance(ids, list) or len(ids) != 19
            or any(not isinstance(x, str) or not x.startswith(PREFIX) or len(x) > 1024 for x in ids)
            or ids != sorted(set(ids)) or not isinstance(lanes, dict) or set(lanes) != set(COUNTS)):
        raise ValueError("Cohort inventory is not closed")
    selected = []
    for lane, count in COUNTS.items():
        rows = lanes[lane]
        if not isinstance(rows, list) or len(rows) != count or rows != sorted(set(rows)):
            raise ValueError("Cohort lane is not closed")
        selected.extend(rows)
    if sorted(selected) != ids or len(set(selected)) != 19:
        raise ValueError("Cohort lanes must partition every identity once")
    return Contract(value["source_sha256"], tuple(ids), {k: tuple(v) for k, v in lanes.items()})


def select(contract, lane, nodeids):
    if lane not in contract.lanes or len(nodeids) != len(set(nodeids)):
        raise ValueError("Unknown lane or duplicate collection")
    actual = sorted(x for x in nodeids if x.startswith(contract.prefix))
    if actual != list(contract.ids):
        raise ValueError("Full cohort collection differs from its frozen inventory")
    wanted = set(contract.lanes[lane])
    retained = [x for x in nodeids if not x.startswith(contract.prefix) or x in wanted]
    if lane != "review":
        # Worksteal initially halves the queue between the existing two workers.
        # Start one expensive case in each half instead of recreating a serial tail.
        cohort = list(contract.lanes[lane])
        other = [x for x in retained if not x.startswith(contract.prefix)]
        if len(cohort) == 1:
            return [cohort[0], *other]
        middle = len(retained) // 2
        return [cohort[0], *other[:middle - 1], cohort[1], *other[middle - 1:]]
    return retained


class Partition:
    def __init__(self, contract, lane):
        if lane not in contract.lanes:
            raise ValueError("Unknown cohort lane")
        self.contract, self.lane = contract, lane
        self.passed = {}
        self.valid = False

    @pytest.hookimpl(tryfirst=True)
    def pytest_collection_modifyitems(self, config, items):
        try:
            ordered = select(self.contract, self.lane, [x.nodeid for x in items])
        except ValueError as exc:
            raise pytest.UsageError(str(exc)) from None
        keep = set(ordered)
        removed = [x for x in items if x.nodeid not in keep]
        by_id = {x.nodeid: x for x in items}
        items[:] = [by_id[x] for x in ordered]
        config.hook.pytest_deselected(items=removed)

    @pytest.hookimpl(optionalhook=True)
    def pytest_xdist_node_collection_finished(self, ids):
        actual = sorted(x for x in ids if x.startswith(self.contract.prefix))
        if actual != list(self.contract.lanes[self.lane]) or len(ids) != len(set(ids)):
            raise pytest.UsageError("Worker cohort selection differs from its exact lane")
        if self.lane != "review":
            positions = [ids.index(x) for x in self.contract.lanes[self.lane]]
            expected = [0] if len(positions) == 1 else [0, len(ids) // 2]
            if positions != expected:
                raise pytest.UsageError("Expensive cases must occupy separate initial worker halves")

    def pytest_runtest_logreport(self, report):
        if (report.when == "call" and report.passed and not getattr(report, "wasxfail", False)
                and report.nodeid.startswith(self.contract.prefix)):
            self.passed[report.nodeid] = self.passed.get(report.nodeid, 0) + 1

    def pytest_sessionfinish(self, session, exitstatus):
        if hasattr(session.config, "workerinput"):
            return
        expected = set(self.contract.lanes[self.lane])
        self.valid = exitstatus == 0 and set(self.passed) == expected and all(x == 1 for x in self.passed.values())
        if exitstatus == 0 and not self.valid:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter, exitstatus):
        if self.valid and exitstatus == 0 and not hasattr(terminalreporter.config, "workerinput"):
            terminalreporter.write_line(json.dumps({"authority_cohort_partition": self.lane,
                "source_sha256": self.contract.source_sha256, "inventory_sha256": self.contract.inventory_sha256,
                "complete_count": len(self.contract.ids), "selected_ids": sorted(self.passed)}))


def pytest_addoption(parser):
    parser.addoption("--authority-cohort-lane", choices=tuple(COUNTS))


def pytest_configure(config):
    try:
        if not hasattr(config, "workerinput") and config.getoption("numprocesses", default=None) != 2:
            raise ValueError("Exactly two existing workers required")
        lane = config.getoption("authority_cohort_lane")
        config.pluginmanager.register(Partition(load_contract(), lane), "closed-authority-cohort-partition")
    except (ValueError, OSError, KeyError, TypeError):
        raise pytest.UsageError("Closed authority cohort source, inventory and lane required") from None
