"""Closed source-review placement, with execution receipts for every retained ID."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/tests/test_source_reviews.py"
MANIFEST = ROOT / "deploy/fixtures/source_review_partition.json"
PREFIX = "tests/test_source_reviews.py::"
LANES = ("candidate", "withdrawal", "publication")


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
        raise ValueError("Source-review manifest exceeds its budget")
    value = json.loads(raw)
    if (not isinstance(value, dict) or set(value) != {"schema", "source_path", "source_sha256", "test_ids", "lanes"}
            or value["schema"] != "source-review-ci-partition-v1"
            or value["source_path"] != "backend/tests/test_source_reviews.py"
            or value["source_sha256"] != hashlib.sha256(source.read_bytes()).hexdigest()):
        raise ValueError("Source-review source or manifest changed")
    ids, lanes = value["test_ids"], value["lanes"]
    if (not isinstance(ids, list) or len(ids) != 69
            or any(not isinstance(x, str) or not x.startswith(PREFIX) or len(x) > 1024 for x in ids)
            or ids != sorted(set(ids)) or not isinstance(lanes, dict) or set(lanes) != set(LANES)):
        raise ValueError("Source-review inventory is not closed")
    all_ids = []
    for rows in lanes.values():
        if not isinstance(rows, list) or len(rows) != 23 or rows != sorted(set(rows)):
            raise ValueError("Source-review lane is not closed")
        all_ids.extend(rows)
    if sorted(all_ids) != ids or len(set(all_ids)) != 69:
        raise ValueError("Every source-review identity must occur once")
    return Contract(value["source_sha256"], tuple(ids), {k: tuple(v) for k, v in lanes.items()})


def select(contract, lane, nodeids):
    if lane not in contract.lanes or len(nodeids) != len(set(nodeids)):
        raise ValueError("Unknown source-review lane or duplicate collection")
    if sorted(x for x in nodeids if x.startswith(contract.prefix)) != list(contract.ids):
        raise ValueError("Full source-review collection differs from its manifest")
    wanted = set(contract.lanes[lane])
    return [x for x in nodeids if not x.startswith(contract.prefix) or x in wanted]


class Partition:
    def __init__(self, contract, lane):
        if lane not in contract.lanes:
            raise ValueError("Unknown source-review lane")
        self.contract, self.lane = contract, lane
        self.passed, self.valid = {}, False

    @pytest.hookimpl(tryfirst=True)
    def pytest_collection_modifyitems(self, config, items):
        try:
            keep = set(select(self.contract, self.lane, [x.nodeid for x in items]))
        except ValueError as exc:
            raise pytest.UsageError(str(exc)) from None
        removed = [x for x in items if x.nodeid not in keep]
        items[:] = [x for x in items if x.nodeid in keep]
        config.hook.pytest_deselected(items=removed)

    @pytest.hookimpl(optionalhook=True)
    def pytest_xdist_node_collection_finished(self, ids):
        if (sorted(x for x in ids if x.startswith(self.contract.prefix)) != list(self.contract.lanes[self.lane])
                or len(ids) != len(set(ids))):
            raise pytest.UsageError("Worker source-review IDs differ from the manifest")

    def pytest_runtest_logreport(self, report):
        if (report.when == "call" and report.passed and not getattr(report, "wasxfail", False)
                and report.nodeid.startswith(self.contract.prefix)):
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
            terminalreporter.write_line(json.dumps({"source_review_partition": self.lane,
                "source_sha256": self.contract.source_sha256, "inventory_sha256": self.contract.inventory_sha256,
                "complete_count": 69, "selected_ids": sorted(self.passed)}))


def pytest_addoption(parser):
    parser.addoption("--source-review-lane", choices=LANES)


def pytest_configure(config):
    try:
        if (not hasattr(config, "workerinput") and not config.getoption("collectonly")
                and config.getoption("numprocesses", default=None) != 2):
            raise ValueError("Exactly two existing workers required")
        config.pluginmanager.register(Partition(load_contract(), config.getoption("source_review_lane")),
                                      "closed-source-review-partition")
    except (ValueError, OSError, KeyError, TypeError):
        raise pytest.UsageError("Closed source-review source, inventory and lane required") from None
