"""Retain exact acceptance scope, honest outcomes and owned process cleanup."""

import os
import signal
import sys
from unittest.mock import Mock

import pytest

from scripts import run_delivered_uat as runner


def test_junit_keeps_failed_known_failed_and_skipped_cases_separate(tmp_path):
    path = tmp_path / "results.xml"
    path.write_text('''<testsuites><testsuite>
    <testcase classname="flow" name="pass" time="1.5"/>
    <testcase classname="flow" name="broken"><failure>Broken</failure></testcase>
    <testcase classname="flow" name="known"><skipped type="pytest.xfail">Known failure</skipped></testcase>
    <testcase classname="flow" name="todo"><skipped type="todo" message="Known"/><failure>Known</failure></testcase>
    <testcase classname="flow" name="skip"><skipped message="TODO"/></testcase>
    <testcase classname="flow" name="error"><error>Unavailable</error></testcase>
    </testsuite></testsuites>''')
    cases = runner.junit_cases(path)
    assert [case["result"] for case in cases] == ["pass", "fail", "known_failure", "known_failure", "not_passed", "fail"]
    assert cases[0]["seconds"] == 1.5


def test_missing_command_retains_an_unavailable_phase(tmp_path):
    result = runner.run([str(tmp_path / "missing-executable")], tmp_path, "synthetic", {}, timeout=1)
    assert result["execution"] == "unavailable" and result["exit_code"] is None


def test_ambient_pytest_filter_and_plugins_cannot_shrink_acceptance_scope():
    env = runner.test_environment({
        "PATH": "/test", "PYTEST_ADDOPTS": "-k unrelated", "PYTEST_PLUGINS": "unknown", "PYTHONHOME": "/elsewhere",
        "PYTHONPATH": "/user", "LA_TEST_SETTING": "synthetic", "LLM_PROVIDER_TEST_SETTING": "synthetic",
    })
    assert set(env) == {"PATH", "PYTHONPATH", "PYTEST_DISABLE_PLUGIN_AUTOLOAD"}
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert "/user" not in env["PYTHONPATH"]


def test_exact_junit_inventory_requires_all_eight_acceptance_journeys(tmp_path):
    source = "tests/uat/test_delivered_workflows.py"
    collections = [f"{source}::test_buat_{number:02d}_synthetic" for number in range(1, 9)]
    quality = "tests/quality/test_uat_runner.py::Quality::test_one"
    expected = runner.collection_ids("\n".join([quality, *collections]))
    assert expected[0] == "tests.quality.test_uat_runner.Quality::test_one"
    with pytest.raises(ValueError, match="Incomplete"):
        runner.collection_ids("\n".join([quality, *collections[:-1]]))
    with pytest.raises(ValueError, match="ambiguous"):
        runner.collection_ids("\n".join([quality, *collections, collections[0]]))
    path = tmp_path / "report.xml"

    def results(ids):
        rows = [f'<testcase classname="{ident.split("::")[0]}" name="{ident.split("::")[1]}"/>' for ident in ids]
        path.write_text("<testsuite>" + "".join(rows) + "</testsuite>")
        return runner.result_inventory(path, expected)[1]

    assert results(reversed(expected))
    assert not results(expected[:-1])
    assert not results([*expected[:-1], expected[0]])


def test_browser_inventory_must_match_source_and_junit(tmp_path):
    expected = runner.browser_ids(runner.ROOT / runner.BROWSER_SUITE)
    assert len(expected) == 10 and any("deep link" in item for item in expected)
    path = tmp_path / "missing.mjs"
    path.write_text("scenario('only one scenario', () => {});")
    with pytest.raises(ValueError, match="Incomplete"):
        runner.browser_ids(path)
    path.write_text('<testsuite><testcase name="only one scenario" classname="test"/></testsuite>')
    assert not runner.result_inventory(path, expected, browser=True)[1]


def test_interrupt_reaps_owned_process_group(monkeypatch, tmp_path):
    process = Mock(pid=56789)
    process.wait.side_effect = [KeyboardInterrupt(), 0]
    start = Mock(return_value=process)
    monkeypatch.setattr(runner.subprocess, "Popen", start)
    # The group has already exited when the cleanup signal is sent.
    signals = Mock(side_effect=ProcessLookupError)
    monkeypatch.setattr(runner.os, "killpg", signals)
    with pytest.raises(KeyboardInterrupt):
        runner.run(["synthetic"], tmp_path, "interrupted", {}, timeout=1)
    assert start.call_args.kwargs["start_new_session"]
    signals.assert_called_once_with(56789, signal.SIGTERM)
    assert process.wait.call_count == 2


def test_timeout_terminates_its_process_and_keeps_outcome(tmp_path):
    child = [sys.executable, "-c", "import time; time.sleep(30)"]
    result = runner.run(child, tmp_path, "timed-out", os.environ, timeout=0.1)
    assert result["execution"] == "timeout" and result["exit_code"] is None
    assert result["seconds"] < 5
