"""Keep the new shared fixture on one worker; preserve atomic legacy scopes."""

import hashlib
import json
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import pytest
from xdist.scheduler.loadscope import LoadScopeScheduling

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "backend/tests/test_recipient_observation_readiness.py"
PREFIX = "tests/test_recipient_observation_readiness.py::"
MANIFEST = ROOT / "deploy/fixtures/recipient_ci_affinity.json"


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate affinity field")
        value[key] = item
    return value


def contract(path=MANIFEST, root=ROOT):
    raw = path.read_bytes()
    if len(raw) > 16384:
        raise ValueError("Affinity manifest exceeds its bound")
    value = json.loads(raw, object_pairs_hook=unique)
    if (type(value) is not dict or set(value) != {"schema", "source_path", "source_sha256", "test_ids"}
            or value["schema"] != "recipient-ci-affinity-v1" or value["source_path"] != SOURCE
            or value["source_sha256"] != hashlib.sha256((root / SOURCE).read_bytes()).hexdigest()):
        raise ValueError("Exact recipient source required")
    ids = value["test_ids"]
    if (type(ids) is not list or len(ids) != 10 or any(type(n) is not str or not n.startswith(PREFIX) for n in ids)
            or ids != sorted(set(ids))):
        raise ValueError("Complete recipient inventory required")
    return value


def validate_collection(ids, expected):
    if len(ids) != len(set(ids)) or sorted(n for n in ids if n.startswith(PREFIX)) != expected:
        raise ValueError("Recipient collection must remain complete and unique")


class RecipientScheduling(LoadScopeScheduling):
    def _split_scope(self, nodeid):
        return PREFIX.removesuffix("::") if nodeid.startswith(PREFIX) else nodeid


class Affinity:
    def __init__(self, value):
        self.value, self.passed, self.workers, self.valid = value, Counter(), set(), False

    def pytest_collection_modifyitems(self, items):
        validate_collection([n.nodeid for n in items], self.value["test_ids"])

    @pytest.hookimpl(optionalhook=True)
    def pytest_xdist_node_collection_finished(self, ids):
        validate_collection(ids, self.value["test_ids"])

    @pytest.hookimpl(optionalhook=True, tryfirst=True)
    def pytest_xdist_make_scheduler(self, config, log):
        return RecipientScheduling(config, log)

    def pytest_runtest_logreport(self, report):
        if report.when == "call" and report.nodeid.startswith(PREFIX):
            if report.passed and not getattr(report, "wasxfail", False):
                self.passed[report.nodeid] += 1
                self.workers.add(getattr(report, "worker_id", None))

    def pytest_sessionfinish(self, session, exitstatus):
        if hasattr(session.config, "workerinput") or session.config.getoption("collectonly"):
            return
        self.valid = (exitstatus == 0 and set(self.passed) == set(self.value["test_ids"])
                      and set(self.passed.values()) == {1} and len(self.workers) == 1
                      and self.workers <= {"gw0", "gw1"})
        if exitstatus == 0 and not self.valid:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter, exitstatus):
        if self.valid and exitstatus == 0 and not hasattr(terminalreporter.config, "workerinput"):
            terminalreporter.write_line(json.dumps({"recipient_fixture_affinity": 1,
                "source_sha256": self.value["source_sha256"], "test_ids": sorted(self.passed),
                "worker_id": next(iter(self.workers)), "legacy_scopes": "individual_test_ids"}))


def pytest_configure(config):
    try:
        if (version("pytest-xdist") != "3.8.0" or not hasattr(config, "workerinput")
                and (config.getoption("numprocesses", default=None) != 2 or config.getoption("dist") != "load"
                     or config.getoption("maxschedchunk") != 1)):
            raise ValueError("Pinned version and existing two-worker interface required")
        config.pluginmanager.register(Affinity(contract()), "recipient-only-fixture-affinity")
    except (ValueError, OSError, TypeError, KeyError):
        raise pytest.UsageError("Exact recipient fixture and pinned two-worker scheduling required") from None
