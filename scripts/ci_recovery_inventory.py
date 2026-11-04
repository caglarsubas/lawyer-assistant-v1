"""Closed placement of new inventory tests within existing measured capacity."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts.ci_source_reviews import Contract
from scripts.ci_source_reviews import Partition as BasePartition
from scripts.ci_source_reviews import select as select

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/tests/test_recovery_review_inventory.py"
MANIFEST = ROOT / "deploy/fixtures/recovery_review_inventory_partition.json"
PREFIX = "tests/test_recovery_review_inventory.py::"
COUNTS = {"postgres": 16, "capacity": 10}
LANES = tuple(COUNTS)


def load_contract(path=MANIFEST, source=SOURCE):
    raw = path.read_bytes()
    if len(raw) > 65536:
        raise ValueError("Inventory-review manifest exceeds its budget")
    value = json.loads(raw)
    if (not isinstance(value, dict) or set(value) != {"schema", "source_path", "source_sha256", "test_ids", "lanes"}
            or value["schema"] != "recovery-inventory-ci-partition-v1"
            or value["source_path"] != "backend/tests/test_recovery_review_inventory.py"
            or value["source_sha256"] != hashlib.sha256(source.read_bytes()).hexdigest()):
        raise ValueError("Inventory-review source or manifest changed")
    ids, lanes = value["test_ids"], value["lanes"]
    if (not isinstance(ids, list) or len(ids) != 26
            or any(not isinstance(x, str) or not x.startswith(PREFIX) or len(x) > 1024 for x in ids)
            or ids != sorted(set(ids)) or not isinstance(lanes, dict) or set(lanes) != set(COUNTS)):
        raise ValueError("Inventory-review inventory is not closed")
    all_ids = []
    for lane, count in COUNTS.items():
        rows = lanes[lane]
        if not isinstance(rows, list) or len(rows) != count or rows != sorted(set(rows)):
            raise ValueError("Inventory-review lane is not closed")
        all_ids.extend(rows)
    if sorted(all_ids) != ids or len(set(all_ids)) != 26:
        raise ValueError("Every recovery-inventory identity must occur once")
    return Contract(value["source_sha256"], tuple(ids), {k: tuple(v) for k, v in lanes.items()})


class Partition(BasePartition):
    def pytest_terminal_summary(self, terminalreporter, exitstatus):
        if self.valid and exitstatus == 0 and not hasattr(terminalreporter.config, "workerinput"):
            terminalreporter.write_line(json.dumps({"recovery_inventory_partition": self.lane,
                "source_sha256": self.contract.source_sha256, "inventory_sha256": self.contract.inventory_sha256,
                "complete_count": 26, "selected_ids": sorted(self.passed)}))


def pytest_addoption(parser):
    parser.addoption("--recovery-inventory-lane", choices=tuple(COUNTS))


def pytest_configure(config):
    try:
        if (not hasattr(config, "workerinput") and not config.getoption("collectonly")
                and config.getoption("numprocesses", default=None) != 2):
            raise ValueError("Exactly two existing workers required")
        config.pluginmanager.register(Partition(load_contract(), config.getoption("recovery_inventory_lane")),
                                      "closed-recovery-inventory-partition")
    except (ValueError, OSError, KeyError, TypeError):
        raise pytest.UsageError("Closed recovery-inventory source, inventory and lane required") from None
