"""Keep all preview-package cases in a closed two-job partition."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts.ci_source_reviews import Contract, Partition
from scripts.controller_stage_manifest import strict

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "deploy/fixtures/preview_package_ci_capacity.json"
SOURCE = "backend/tests/test_operator_preview_package.py"
PREFIX = SOURCE.removeprefix("backend/") + "::"
LANES = ("graph", "review")


def load_contract(path=MANIFEST, root=ROOT):
    raw = path.read_bytes()
    if len(raw) > 16384:
        raise ValueError("Preview package inventory exceeds its bound")
    value = strict(raw)
    if (type(value) is not dict or set(value) != {"source_sha256", "test_ids", "lanes"}
            or value["source_sha256"] != hashlib.sha256((root / SOURCE).read_bytes()).hexdigest()):
        raise ValueError("Exact preview package source required")
    ids, lanes = value["test_ids"], value["lanes"]
    if (type(ids) is not list or len(ids) != 34 or any(type(n) is not str or not n.startswith(PREFIX) for n in ids)
            or ids != sorted(set(ids)) or type(lanes) is not dict or set(lanes) != set(LANES)
            or any(type(rows) is not list or len(rows) != 17 or any(type(n) is not str for n in rows)
                   or rows != sorted(set(rows)) for rows in lanes.values())
            or sorted(n for rows in lanes.values() for n in rows) != ids):
        raise ValueError("Both preview package lanes must partition every original case")
    return Contract(value["source_sha256"], tuple(ids), {k: tuple(v) for k, v in lanes.items()})


class PreviewPackagePartition(Partition):
    def pytest_terminal_summary(self, terminalreporter, exitstatus):
        if self.valid and exitstatus == 0 and not hasattr(terminalreporter.config, "workerinput"):
            terminalreporter.write_line(json.dumps({"preview_package_partition": self.lane,
                "source_sha256": self.contract.source_sha256, "inventory_sha256": self.contract.inventory_sha256,
                "complete_count": 34, "selected_ids": sorted(self.passed)}))


def pytest_addoption(parser):
    parser.addoption("--preview-package-lane", choices=LANES)


def pytest_configure(config):
    try:
        if (not hasattr(config, "workerinput") and not config.getoption("collectonly")
                and config.getoption("numprocesses", default=None) != 2):
            raise ValueError("Exactly two existing workers required")
        config.pluginmanager.register(PreviewPackagePartition(load_contract(), config.getoption("preview_package_lane")),
                                      "closed-preview-package-capacity")
    except (ValueError, OSError, TypeError, KeyError):
        raise pytest.UsageError("Closed preview package source and partition required") from None
