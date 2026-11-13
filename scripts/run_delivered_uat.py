#!/usr/bin/env python3
"""Run the disposable acceptance suites and retain per-case results."""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_PATHS = ("tests/quality", "tests/uat")
BROWSER_SUITE = "tests/uat/browser/workbench.test.mjs"
JOURNEY_NUMBERS = {f"{number:02d}" for number in range(1, 9)}


def junit_cases(path):
    result = []
    for case in ET.parse(path).getroot().iter("testcase"):
        failed = case.find("failure") is not None or case.find("error") is not None
        skip = case.find("skipped")
        expected = skip is not None and skip.get("type") in {"pytest.xfail", "todo"}
        outcome = "known_failure" if expected else "fail" if failed else "not_passed" if skip is not None else "pass"
        result.append({"id": case.get("classname", "") + "::" + case.get("name", ""),
                       "result": outcome, "seconds": float(case.get("time", "0"))})
    return result


def collection_ids(stdout):
    ids = []
    journeys = []
    for line in stdout.splitlines():
        if not line.startswith(("tests/quality/", "tests/uat/")):
            continue
        path, separator, name = line.partition("::")
        if not separator or not path.endswith(".py") or not name:
            raise ValueError("Invalid pytest collection")
        parts = name.split("::")
        ids.append(".".join([path.removesuffix(".py").replace("/", "."), *parts[:-1]]) + "::" + parts[-1])
        if path == "tests/uat/test_delivered_workflows.py":
            match = re.fullmatch(r"test_buat_(\d{2})_[a-z0-9_]+", name)
            if not match:
                raise ValueError("Invalid backend acceptance case")
            journeys.append(match[1])
    if len(set(ids)) != len(ids) or len(journeys) != len(JOURNEY_NUMBERS) or set(journeys) != JOURNEY_NUMBERS:
        raise ValueError("Incomplete or ambiguous pytest collection")
    return ids


def browser_ids(path):
    # The scenarios in this suite are literal, top-level calls. Require each
    # declaration to have a unique name before comparing against Node's JUnit.
    source = path.read_text(encoding="utf-8")
    names = re.findall(r"^scenario\('([^'\n]+)'\s*,", source, flags=re.MULTILINE)
    if len(names) != 10 or len(set(names)) != 10 or len(re.findall(r"^scenario\(", source, flags=re.MULTILINE)) != 10:
        raise ValueError("Incomplete or ambiguous browser scenario inventory")
    return names


def result_inventory(path, expected, *, browser=False):
    cases = junit_cases(path)
    found = [case["id"].partition("::")[2] if browser else case["id"] for case in cases]
    return cases, bool(expected) and Counter(found) == Counter(expected)


def test_environment(ambient):
    env = {key: value for key, value in ambient.items()
           if not key.startswith(("LA_", "LLM_PROVIDER_", "PYTEST_")) and key != "PYTHONHOME"}
    env["PYTHONPATH"] = os.pathsep.join(str(ROOT / path) for path in ("backend", "backend/tests", "."))
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"  # xdist is loaded explicitly below
    return env


def stop_group(process):
    def signal_group(signum):
        try:
            os.killpg(process.pid, signum)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # macOS can report EPERM for signal 0 while a group is exiting.
            # Retry while its leader is still present.
            if signum == 0:
                return process.poll() is None
            raise

    if signal_group(signal.SIGTERM):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            process.poll()
            if not signal_group(0):
                break
            time.sleep(0.05)
        else:
            signal_group(signal.SIGKILL)
    process.wait(timeout=2)


def run(argv, directory, name, environment, *, timeout):
    start = time.monotonic()
    try:
        with (directory / f"{name}.log").open("w") as log:
            process = subprocess.Popen(argv, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except BaseException:
                stop_group(process)
                raise
        status = "completed"
    except subprocess.TimeoutExpired:
        code, status = None, "timeout"
    except OSError:
        code, status = None, "unavailable"
    return {"name": name, "execution": status, "exit_code": code, "seconds": round(time.monotonic() - start, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory for this observation")
    parser.add_argument("--python", type=Path, default=ROOT / "backend/.venv/bin/python")
    parser.add_argument("--browser", action="store_true", help="Build frontend and run isolated Chromium fixtures")
    parser.add_argument("--observe-runtime", action="store_true", help="Add unauthenticated read-only local deployment observations")
    args = parser.parse_args()
    os.umask(0o077)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    environment = test_environment(os.environ)
    # Keep the venv launcher path so Python finds pyvenv.cfg.
    python = str(args.python.absolute())
    pytest = [python, "-m", "pytest", "-c", "backend/pyproject.toml", "--rootdir=.", "-p", "xdist.plugin",
              *API_PATHS]
    api_xml = output / "api-quality.xml"
    browser_xml = output / "browser.xml"
    api_expected, browser_expected, cases = [], [], []
    collection = run([*pytest, "--collect-only", "-q", "--disable-warnings"],
                     output, "api-collection", environment, timeout=30)
    phases = [collection]
    if collection["exit_code"] == 0:
        try:
            api_expected = collection_ids((output / "api-collection.log").read_text(encoding="utf-8"))
        except ValueError:
            collection["execution"] = "invalid_inventory"
    if api_expected:
        phases.append(run([*pytest, "-n", "2", "--max-worker-restart=0", "--dist", "load", "-q", "-rA",
                           f"--junitxml={api_xml}"], output, "api-quality", environment, timeout=90))
    else:
        phases.append({"name": "api-quality", "execution": "blocked", "exit_code": None, "seconds": 0})
    if args.browser:
        try:
            browser_expected = browser_ids(ROOT / BROWSER_SUITE)
        except (OSError, ValueError):
            phases.append({"name": "browser-inventory", "execution": "invalid_inventory", "exit_code": None,
                           "seconds": 0})
        if browser_expected:
            build = run(["npm", "--prefix", "frontend", "run", "build"],
                        output, "frontend-build", environment, timeout=90)
            phases.append(build)
        if browser_expected and build["exit_code"] == 0:
            phases.append(run(["node", "--test", "--test-concurrency=1", "--test-reporter=junit",
                               f"--test-reporter-destination={browser_xml}", BROWSER_SUITE],
                              output, "browser", environment, timeout=300))
        else:
            phases.append({"name": "browser", "execution": "blocked", "exit_code": None, "seconds": 0})
    else:
        phases.append({"name": "browser", "execution": "not_requested", "exit_code": None, "seconds": 0})
    if args.observe_runtime:
        phases.append(run([python, "scripts/observe_uat_runtime.py", "--compare-backend-code"],
                          output, "runtime", environment, timeout=90))

    def read_results(path, expected, *, browser=False):
        try:
            observed, complete = result_inventory(path, expected, browser=browser)
            cases.extend(observed)
        except (OSError, ValueError, ET.ParseError):
            complete = False
        if not complete:
            phases.append({"name": path.name, "execution": "invalid_result", "exit_code": None, "seconds": 0})
        return complete

    api_complete = read_results(api_xml, api_expected) if api_expected else False
    browser_complete = read_results(browser_xml, browser_expected, browser=True) if browser_expected else False
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=5).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True, timeout=5))
    failures = any(case["result"] != "pass" for case in cases)
    complete = all(phase["exit_code"] == 0 and phase["execution"] == "completed"
                   for phase in phases if phase["execution"] != "not_requested")
    report = {"schema": "delivered-workflow-uat-run-v1", "observed_at": datetime.now(timezone.utc).isoformat(),
              "source_commit": source, "source_worktree_dirty": dirty, "test_workers": 2, "phases": phases, "cases": cases,
              "counts": {key: sum(case["result"] == key for case in cases)
                         for key in ("pass", "fail", "known_failure", "not_passed")},
              "inventory": {"api_expected": len(api_expected), "api_complete": api_complete,
                            "browser_expected": len(browser_expected), "browser_complete": browser_complete},
              "selected_checks_passed": complete and api_complete and (browser_complete or not args.browser) and not failures,
              "browser_coverage": "fixture_backed" if browser_complete else "incomplete" if args.browser else "not_observed",
              "production_uat": "not_qualified", "human_legal_review": "not_granted"}
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"result_file": str(output / "results.json"), "counts": report["counts"],
                      "selected_checks_passed": report["selected_checks_passed"], "production_uat": "not_qualified"}))
    return 0 if report["selected_checks_passed"] else 1


def interrupted(_signum, _frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
