"""Closed CI commands, exact source identity and bounded serial-worker cleanup."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_ci_history_review_pair as pair  # noqa: E402


def profile():
    return json.loads(pair.PROFILE.read_text())


def test_closed_pair_matches_its_frozen_sources_and_exact_commands():
    assert pair.validate(pair.COMMANDS, profile()) == profile()["source_sha256"]


@pytest.mark.parametrize("change", ["executor", "arguments", "workers", "deadline", "source", "counts"])
def test_unknown_commands_or_expanded_budgets_cannot_launch_workers(change):
    commands = [list(x) for x in pair.COMMANDS]
    value = profile()
    if change == "executor":
        commands[0][0] = "arbitrary-python"
    elif change == "arguments":
        commands[1].append("--ignore=tests")
    elif change == "workers":
        value["active_workers"] = 3
    elif change == "deadline":
        value["seconds"] = 51
    elif change == "source":
        value["source_sha256"][pair.FILES[0]] = "f" * 64
    else:
        value["counts"] = [44, 8]
    with pytest.raises(ValueError):
        pair.validate(commands, value)


def fake_workers(monkeypatch, mode):
    rows = []
    class Process:
        def __init__(self, command, **kw):
            self.index, self.returncode, self.terminated = len(rows), None, False
            assert command[:-1] == list(pair.COMMANDS[self.index])
            rows.append(self)
        def communicate(self, timeout):
            assert 0 < timeout <= 50
            if mode == "timeout":
                raise subprocess.TimeoutExpired("closed", timeout)
            self.returncode = 1 if mode == "failure" and self.index == 0 else 0
            return (f"{[45, 8][self.index]} passed in 0.01s\n".encode(), None)
        def poll(self):
            return self.returncode
        def terminate(self):
            self.terminated = True
            self.returncode = -15
        def kill(self):
            self.returncode = -9
        def wait(self, timeout):
            return self.returncode
    monkeypatch.setattr(pair.subprocess, "Popen", Process)
    return rows


def test_success_requires_both_complete_children_and_no_extra_worker(tmp_path, monkeypatch, capsys):
    rows = fake_workers(monkeypatch, "success")
    assert pair.run(pair.COMMANDS, tmp_path, profile()) == 0
    lines = capsys.readouterr().out.splitlines()
    receipt = json.loads(lines[-1])
    assert len(rows) == 2 and receipt["tests_run"] == 53 and receipt["clean_exits"] == [0, 0]
    assert receipt["source_sha256"] == profile()["source_sha256"]


def test_child_failure_never_emits_a_qualified_pair(tmp_path, monkeypatch, capsys):
    rows = fake_workers(monkeypatch, "failure")
    with pytest.raises(ValueError):
        pair.run(pair.COMMANDS, tmp_path, profile())
    assert len(rows) == 2 and "history_review_pair" not in capsys.readouterr().out


def test_deadline_terminates_both_children_without_retry(tmp_path, monkeypatch):
    rows = fake_workers(monkeypatch, "timeout")
    with pytest.raises(subprocess.TimeoutExpired):
        pair.run(pair.COMMANDS, tmp_path, profile())
    assert len(rows) == 2 and all(p.terminated and p.returncode == -15 for p in rows)


@pytest.mark.parametrize("change", ["parent", "profile", "lane", "workers", "worker_child", "role"])
def test_serial_adapter_rejects_standalone_or_extra_worker_context(monkeypatch, change):
    import os
    from types import SimpleNamespace

    from scripts import ci_serial_history_cohorts as adapter
    monkeypatch.setenv("CI_HISTORY_PAIR_PARENT", str(os.getppid()))
    monkeypatch.setenv("CI_HISTORY_PAIR_PROFILE", pair.identity(profile()))
    values = {"numprocesses": None, "authority_cohort_lane": "history", "ci_serial_role": "cohort"}
    config = SimpleNamespace(getoption=lambda key, default=None: values.get(key, default))
    if change == "parent":
        monkeypatch.delenv("CI_HISTORY_PAIR_PARENT")
    elif change == "profile":
        monkeypatch.setenv("CI_HISTORY_PAIR_PROFILE", "f" * 64)
    elif change == "lane":
        values["authority_cohort_lane"] = "review"
    elif change == "workers":
        values["numprocesses"] = 2
    elif change == "worker_child":
        config.workerinput = {}
    else:
        values["ci_serial_role"] = "unknown"
    with pytest.raises(pytest.UsageError):
        adapter.pytest_configure(config)


@pytest.mark.parametrize("name", ["PYTEST_ADDOPTS", "PYTEST_PLUGINS"])
def test_environment_cannot_inject_additional_workers_or_plugins(monkeypatch, name):
    monkeypatch.setenv(name, "unapproved")
    with pytest.raises(ValueError):
        pair.validate(pair.COMMANDS, profile())
