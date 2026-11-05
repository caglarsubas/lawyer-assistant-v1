"""Closed placement of the twenty unchanged, mocked model-trial cases."""

import hashlib
import json
import re
from pathlib import Path

import pytest

from scripts.ci_source_reviews import Contract, select  # noqa: F401
from scripts.ci_source_reviews import Partition as BasePartition
from scripts.controller_stage_manifest import strict

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "deploy/fixtures/model_trial_ci_capacity.json"
SOURCE = "backend/tests/test_authority_model_trials.py"
PREFIX = "tests/test_authority_model_trials.py::"
COUNTS = {"frontend": 8, "history": 12}


def load_contract(path=MANIFEST, root=ROOT):
    raw = path.read_bytes()
    if len(raw) > 16384:
        raise ValueError("Closed model-trial manifest exceeds its bound")
    value = strict(raw)
    fields = {"schema", "source_path", "source_sha256", "test_ids", "lanes", "observed_head", "observed_run", "retained_log_sha256"}
    if (type(value) is not dict or set(value) != fields or value["schema"] != "model-trial-capacity-v1"
            or value["source_path"] != SOURCE or value["source_sha256"] != hashlib.sha256((root / SOURCE).read_bytes()).hexdigest()
            or value["observed_head"] != "04c38dcb60648656e63c22f0b82cae258b62d973" or value["observed_run"] != 42035472783
            or type(value["retained_log_sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", value["retained_log_sha256"])):
        raise ValueError("Exact model-trial source and retained measurement required")
    ids, lanes = value["test_ids"], value["lanes"]
    if (type(ids) is not list or len(ids) != 20 or ids != sorted(set(ids))
            or any(type(n) is not str or not n.startswith(PREFIX) or len(n) > 1024 for n in ids)
            or type(lanes) is not dict or set(lanes) != set(COUNTS)):
        raise ValueError("Complete original model-trial identities required")
    combined = []
    for lane, count in COUNTS.items():
        rows = lanes[lane]
        if type(rows) is not list or len(rows) != count or rows != sorted(set(rows)):
            raise ValueError("Closed model-trial lane required")
        combined += rows
    if sorted(combined) != ids or len(set(combined)) != 20:
        raise ValueError("Every unchanged model-trial identity must execute once")
    return Contract(value["source_sha256"], tuple(ids), {k: tuple(ns) for k, ns in lanes.items()})


class Partition(BasePartition):
    def pytest_terminal_summary(self, terminalreporter, exitstatus):
        if self.valid and exitstatus == 0 and not hasattr(terminalreporter.config, "workerinput"):
            terminalreporter.write_line(json.dumps({"model_trial_capacity_partition": self.lane,
                "source_sha256": self.contract.source_sha256, "inventory_sha256": self.contract.inventory_sha256,
                "complete_count": 20, "selected_ids": sorted(self.passed)}))


def pytest_addoption(parser):
    parser.addoption("--model-trial-capacity-lane", choices=tuple(COUNTS))


def pytest_configure(config):
    try:
        if (not hasattr(config, "workerinput") and not config.getoption("collectonly")
                and config.getoption("numprocesses", default=None) != 2):
            raise ValueError("Only the existing two-worker ceiling may execute")
        config.pluginmanager.register(Partition(load_contract(), config.getoption("model_trial_capacity_lane")),
                                      "closed-model-trial-capacity")
    except (ValueError, OSError, TypeError, KeyError):
        raise pytest.UsageError("Exact source, complete collection and closed model-trial lane required") from None
