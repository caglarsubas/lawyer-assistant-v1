"""Protect complete evidence tests and the existing two-worker ceiling."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import ci_recipient_affinity as affinity  # noqa: E402


def test_exact_source_and_complete_inventory_are_required(tmp_path):
    value = affinity.contract()
    assert len(value["test_ids"]) == 10
    for mode in ("source", "missing", "duplicate", "unknown"):
        changed = json.loads(affinity.MANIFEST.read_bytes())
        if mode == "source":
            changed["source_sha256"] = "0" * 64
        elif mode == "missing":
            changed["test_ids"].pop()
        elif mode == "duplicate":
            changed["test_ids"][-1] = changed["test_ids"][0]
        else:
            changed["path_from_request"] = "untrusted"
        p = tmp_path / "manifest.json"
        p.write_text(json.dumps(changed))
        with pytest.raises(ValueError):
            affinity.contract(p)


def test_only_new_fixture_is_grouped_and_legacy_tests_remain_individual_scopes():
    ids = affinity.contract()["test_ids"]
    scheduler = object.__new__(affinity.RecipientScheduling)
    assert len({scheduler._split_scope(n) for n in ids}) == 1
    others = ["tests/test_existing.py::Example::test_one", "tests/test_existing.py::Example::test_two"]
    assert [scheduler._split_scope(n) for n in others] == others
    affinity.validate_collection([*others, *ids], ids)
    for rows in (ids[:-1], [*ids, ids[0]], [*ids[:-1], affinity.PREFIX + "test_unregistered"]):
        with pytest.raises(ValueError):
            affinity.validate_collection(rows, ids)


def test_only_complete_once_single_worker_execution_can_publish_receipt():
    value = affinity.contract()
    for mode in ("valid", "skipped", "duplicate", "xfail", "split_worker", "unknown_worker"):
        plugin = affinity.Affinity(value)
        for i, nodeid in enumerate(value["test_ids"]):
            report = SimpleNamespace(when="call", nodeid=nodeid,
                passed=not (mode == "skipped" and i == 0), wasxfail=(mode == "xfail" and i == 0),
                worker_id=None if mode == "unknown_worker" else "gw1" if mode == "split_worker" and i == 0 else "gw0")
            plugin.pytest_runtest_logreport(report)
            if mode == "duplicate" and i == 0:
                plugin.pytest_runtest_logreport(report)
        config = SimpleNamespace(getoption=lambda _: False)
        session = SimpleNamespace(config=config, exitstatus=0)
        plugin.pytest_sessionfinish(session, 0)
        lines = []
        plugin.pytest_terminal_summary(SimpleNamespace(config=config, write_line=lines.append), session.exitstatus)
        if mode == "valid":
            assert session.exitstatus == 0 and json.loads(lines[0])["test_ids"] == value["test_ids"]
        else:
            assert session.exitstatus == pytest.ExitCode.TESTS_FAILED and not lines
