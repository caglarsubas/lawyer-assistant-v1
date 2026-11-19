"""Passive CI case diagnostics over invented test IDs and private in-memory state."""

import hashlib
import importlib.util
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def diagnostic(monkeypatch):
    source = Path(__file__).resolve().parents[2] / "scripts" / "ci_case_diagnostics.py"
    spec = importlib.util.spec_from_file_location("disposable_ci_case_diagnostics", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Never change the actual worker environment or the active CI collector.
    monkeypatch.setattr(module, "os", SimpleNamespace(environ={"GITHUB_ACTIONS": "true"}))
    return module


def messages(capsys, *, progress=False):
    output = capsys.readouterr()
    assert not output.err
    lines = [line for line in output.out.splitlines() if line]
    if progress:
        assert lines.pop(0) == "."
    assert all(line.startswith("CI_CASE ") for line in lines)
    return [json.loads(line.removeprefix("CI_CASE ")) for line in lines]


@pytest.mark.parametrize("environment", [{}, {"GITHUB_ACTIONS": "false"},
    {"GITHUB_ACTIONS": "True"}, {"GITHUB_ACTIONS": "true", "PYTEST_XDIST_WORKER": "gw0"}])
def test_case_diagnostics_require_the_real_ci_master_only(diagnostic, capsys, environment):
    diagnostic.os.environ = environment
    diagnostic.pytest_runtest_logstart("tests/test_safe.py::test_case", None)
    diagnostic._ci_case_end("tests/test_safe.py::test_case")
    assert messages(capsys) == [] and diagnostic._ci_active == {}


def test_case_start_end_hash_parameters_and_preserve_exact_case_identity(diagnostic, capsys, monkeypatch):
    secret = "SYNTHETIC-private-api-key-and-client-name-never-log"
    nodeid = "backend/tests/test_safe.py::test_case[" + secret + "]"
    clock = iter([12.0, 13.25])
    monkeypatch.setattr(diagnostic, "_ci_clock", lambda: next(clock))
    print(".", end="")
    diagnostic.pytest_runtest_logstart(nodeid, None)
    assert len(diagnostic._ci_active) == 1
    assert all(secret not in str(value) for value in diagnostic._ci_active.values())
    diagnostic._ci_case_end(nodeid)
    rows = messages(capsys, progress=True)
    key = hashlib.sha256(nodeid.encode()).hexdigest()
    assert rows == [
        {"event": "start", "node_sha256": key, "file": "tests/test_safe.py"},
        {"event": "end", "node_sha256": key, "file": "tests/test_safe.py", "elapsed_seconds": 1.25},
    ]
    assert secret not in json.dumps(rows) and "test_case[" not in json.dumps(rows)
    assert diagnostic._ci_active == {}


def test_teardown_report_closes_the_case_without_changing_the_test_verdict(diagnostic, capsys):
    nodeid = "tests/test_safe.py::test_case"
    report = SimpleNamespace(nodeid=nodeid, when="call", duration=0.25, outcome="passed", longrepr=None)
    diagnostic.pytest_runtest_logstart(nodeid, None)
    before = vars(report).copy()
    diagnostic.pytest_runtest_logreport(report)
    assert vars(report) == before and len(diagnostic._ci_active) == 1
    report.when = "teardown"
    before = vars(report).copy()
    diagnostic.pytest_runtest_logreport(report)
    assert vars(report) == before and diagnostic._ci_active == {}
    assert [row["event"] for row in messages(capsys)] == ["start", "end"]


@pytest.mark.parametrize("nodeid", [
    "/Users/private/test_secret.py::test_case",
    "../tests/test_safe.py::test_case",
    "tests/../../test_secret.py::test_case",
    "tests/test_\u0130.py::test_case",
    "tests/" + "x" * 240 + ".py::test_case",
    "tests/test_safe.py\n::test_case",
    "tests/test_safe.py::test_case[\ud800]",
    None,
])
def test_malformed_paths_are_ignored_without_exposing_text(diagnostic, capsys, nodeid):
    diagnostic.pytest_runtest_logstart(nodeid, None)
    diagnostic._ci_case_end(nodeid)
    assert messages(capsys) == [] and diagnostic._ci_active == {}


def test_two_case_cache_overflow_is_bounded_and_only_warns_once(diagnostic, capsys):
    ids = ["tests/test_safe.py::test_" + str(index) for index in range(5)]
    for nodeid in ids:
        diagnostic.pytest_runtest_logstart(nodeid, None)
    assert len(diagnostic._ci_active) == 2
    rows = messages(capsys)
    assert [row["event"] for row in rows] == ["start", "start", "warning"]
    assert rows[-1] == {"event": "warning", "code": "active_inventory_unverifiable", "active_limit": 2}
    for nodeid in ids:
        diagnostic._ci_case_end(nodeid)
    assert len(messages(capsys)) == 2 and diagnostic._ci_active == {}


def test_clock_binding_does_not_use_mutated_global_time_attributes(diagnostic, capsys, monkeypatch):
    original_clock = diagnostic._ci_clock
    touched = []

    def forbidden():
        touched.append(True)
        raise AssertionError("Diagnostic used a globally mocked clock")

    with monkeypatch.context() as patch:
        patch.setattr(time, "perf_counter", forbidden)
        patch.setattr(time, "monotonic", forbidden)
        diagnostic.pytest_runtest_logstart("tests/test_safe.py::test_case", None)
        diagnostic._ci_case_end("tests/test_safe.py::test_case")
    assert diagnostic._ci_clock is original_clock and not touched
    assert [row["event"] for row in messages(capsys)] == ["start", "end"]


def test_diagnostic_output_failure_does_not_change_the_test_verdict(diagnostic, monkeypatch):
    def broken(*args, **kwargs):
        raise BrokenPipeError("SYNTHETIC output unavailable")

    monkeypatch.setattr(diagnostic, "print", broken, raising=False)
    diagnostic.pytest_runtest_logstart("tests/test_safe.py::test_case", None)
    diagnostic._ci_case_end("tests/test_safe.py::test_case")
    assert diagnostic._ci_active == {}


def test_case_identifier_input_is_bounded_before_hashing(diagnostic, capsys):
    prefix = "tests/test_safe.py::test_case["
    allowed = prefix + "x" * (65536 - len(prefix))
    diagnostic.pytest_runtest_logstart(allowed + "x", None)
    diagnostic._ci_case_end(allowed + "x")
    assert messages(capsys) == [] and diagnostic._ci_active == {}
    diagnostic.pytest_runtest_logstart(allowed, None)
    diagnostic._ci_case_end(allowed)
    rows = messages(capsys)
    assert len(rows) == 2 and all(row["node_sha256"] == hashlib.sha256(allowed.encode()).hexdigest() for row in rows)
    assert len(json.dumps(rows)) < 500


def test_duplicate_start_keeps_the_first_clock_and_emits_no_second_start(diagnostic, capsys, monkeypatch):
    nodeid = "tests/test_safe.py::test_case[SYNTHETIC-private-duplicate]"
    clock = iter([5.0, 8.0])
    monkeypatch.setattr(diagnostic, "_ci_clock", lambda: next(clock))
    diagnostic.pytest_runtest_logstart(nodeid, None)
    diagnostic.pytest_runtest_logstart(nodeid, None)
    diagnostic._ci_case_end(nodeid)
    diagnostic._ci_case_end(nodeid)
    rows = messages(capsys)
    assert [row["event"] for row in rows] == ["start", "warning", "end"]
    assert rows[-1]["elapsed_seconds"] == 3.0 and diagnostic._ci_active == {}
    assert "SYNTHETIC-private-duplicate" not in json.dumps(rows)
