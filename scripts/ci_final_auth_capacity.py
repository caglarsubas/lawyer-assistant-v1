"""Closed routing of unchanged authorization tests; fixed two-worker scheduling."""

import hashlib
import importlib.metadata
import json
import re
from pathlib import Path

import pytest

from scripts.ci_source_reviews import Contract, select
from scripts.ci_source_reviews import Partition as BasePartition
from scripts.controller_stage_manifest import strict

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "deploy/fixtures/final_auth_ci_capacity.json"
SOURCE = "backend/tests/test_final_release_authorization.py"
PREFIX = "tests/test_final_release_authorization.py::"
MOVED = tuple(PREFIX + n for n in ("test_acceptance_interruption_discards_only_owned_new_permission",
                                  "test_guard_rejects_unheld_or_fabricated_transition"))


def load_contract(path=MANIFEST, root=ROOT):
    raw = path.read_bytes()
    if len(raw) > 16384:
        raise ValueError("Closed authorization manifest exceeds its bound")
    v = strict(raw)
    fields = {"schema", "source_path", "source_sha256", "lock_sha256", "xdist_version", "test_ids", "lanes",
              "observed_head", "observed_run", "retained_log_sha256", "moved_case_cpu_upper_ms", "worker_positions"}
    if (type(v) is not dict or set(v) != fields or v["schema"] != "final-auth-capacity-v1"
            or v["source_path"] != SOURCE
            or v["source_sha256"] != hashlib.sha256((root / SOURCE).read_bytes()).hexdigest()
            or v["lock_sha256"] != hashlib.sha256((root / "backend/uv.lock").read_bytes()).hexdigest()
            or v["xdist_version"] != "3.8.0" or importlib.metadata.version("pytest-xdist") != v["xdist_version"]
            or v["observed_head"] != "6122e965023d81394e2cfa416c21cada330cffda" or v["observed_run"] != 42005341497
            or type(v["retained_log_sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", v["retained_log_sha256"])
            or v["worker_positions"] != [0, 2] or v["moved_case_cpu_upper_ms"] != dict.fromkeys(MOVED, 12000)):
        raise ValueError("Exact source, scheduler and retained timing evidence required")
    ids, lanes = v["test_ids"], v["lanes"]
    if (type(ids) is not list or len(ids) != 10 or any(type(n) is not str or not n.startswith(PREFIX) for n in ids)
            or ids != sorted(set(ids)) or type(lanes) is not dict or set(lanes) != {"graph", "final"}
            or lanes["graph"] != list(MOVED) or lanes["final"] != sorted(set(ids) - set(MOVED))
            or len(lanes["final"]) != 8 or not set(MOVED) <= set(ids)):
        raise ValueError("All original authorization cases must occur once")
    return Contract(v["source_sha256"], tuple(ids), {k: tuple(ns) for k, ns in lanes.items()})


def balanced(contract, lane, ids):
    kept = select(contract, lane, ids)
    if lane == "graph":
        others = [n for n in kept if n not in MOVED]
        if len(others) < 2:
            raise ValueError("Two nonempty initial worker batches required")
        kept = [MOVED[0], others[0], MOVED[1], *others[1:]]
    return kept


class Partition(BasePartition):
    def __init__(self, contract, lane):
        super().__init__(contract, lane)
        self.workers = {}

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, config, items):
        ids = balanced(self.contract, self.lane, [n.nodeid for n in items])
        lookup = {n.nodeid: n for n in items}
        removed = [n for n in items if n.nodeid not in set(ids)]
        items[:] = [lookup[n] for n in ids]
        config.hook.pytest_deselected(items=removed)

    @pytest.hookimpl(optionalhook=True)
    def pytest_xdist_node_collection_finished(self, ids):
        super().pytest_xdist_node_collection_finished(ids)
        if self.lane == "graph" and (len(ids) < 4 or [ids[0], ids[2]] != list(MOVED)):
            raise pytest.UsageError("Moved cases must start in separate initial batches")

    def pytest_runtest_logreport(self, report):
        super().pytest_runtest_logreport(report)
        if report.when == "call" and report.passed and report.nodeid in self.contract.lanes[self.lane]:
            self.workers[report.nodeid] = getattr(report, "worker_id", None)

    def pytest_sessionfinish(self, session, exitstatus):
        super().pytest_sessionfinish(session, exitstatus)
        if hasattr(session.config, "workerinput") or session.config.getoption("collectonly"):
            return
        if self.valid and (set(self.workers) != set(self.contract.lanes[self.lane])
                           or any(n not in {"gw0", "gw1"} for n in self.workers.values())
                           or self.lane == "graph" and len(set(self.workers.values())) != 2):
            self.valid = False
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter, exitstatus):
        if self.valid and exitstatus == 0 and not hasattr(terminalreporter.config, "workerinput"):
            terminalreporter.write_line(json.dumps({"final_auth_capacity_partition": self.lane,
                "source_sha256": self.contract.source_sha256, "inventory_sha256": self.contract.inventory_sha256,
                "complete_count": 10, "selected_ids": sorted(self.passed), "worker_ids": self.workers}))


def pytest_addoption(parser):
    parser.addoption("--final-auth-capacity-lane", choices=("graph", "final"))


def pytest_configure(config):
    try:
        if (not hasattr(config, "workerinput") and not config.getoption("collectonly")
                and (config.getoption("numprocesses", default=None) != 2 or config.getoption("dist") != "load"
                     or config.getoption("maxschedchunk") != 1)):
            raise ValueError("Only the locked two-worker scheduler may execute")
        config.pluginmanager.register(Partition(load_contract(), config.getoption("final_auth_capacity_lane")),
                                      "closed-final-authorization-capacity")
    except (ValueError, OSError, KeyError, TypeError):
        raise pytest.UsageError("Closed authorization source, complete collection and fixed scheduler required") from None
