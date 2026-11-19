"""Passive CI-master case diagnostics; never alter test coverage or verdicts."""

import hashlib
import json
import os
import re
from time import perf_counter

_ci_clock = perf_counter  # Bind the real clock before any test changes time attributes.
_ci_active = {}
_ci_overflowed = False
_CI_CASE_FILE = re.compile(r"tests/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.py\Z")


def _ci_case_identity(nodeid):
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("PYTEST_XDIST_WORKER")
            or not isinstance(nodeid, str) or len(nodeid) > 65536):
        return None
    file = nodeid.split("::", 1)[0].removeprefix("backend/")
    if len(file) > 240 or _CI_CASE_FILE.fullmatch(file) is None:
        return None
    try:
        return hashlib.sha256(nodeid.encode("utf-8")).hexdigest(), file
    except UnicodeError:
        return None


def _ci_case_print(event, **value):
    try:
        print("\nCI_CASE " + json.dumps({"event": event, **value}, sort_keys=True, allow_nan=False), flush=True)
    except (OSError, TypeError, ValueError):
        pass  # Passive diagnostics never change the test verdict.


def pytest_runtest_logstart(nodeid, location):
    global _ci_overflowed
    identity = _ci_case_identity(nodeid)
    if identity is None:
        return
    key, file = identity
    if key in _ci_active or len(_ci_active) >= 2:
        if not _ci_overflowed:
            _ci_overflowed = True
            _ci_case_print("warning", code="active_inventory_unverifiable", active_limit=2)
        return
    _ci_active[key] = (_ci_clock(), file)
    _ci_case_print("start", node_sha256=key, file=file)


def _ci_case_end(nodeid):
    identity = _ci_case_identity(nodeid)
    if identity is None:
        return
    key, _file = identity
    previous = _ci_active.pop(key, None)
    if previous is not None:
        started, file = previous
        elapsed = round(max(0.0, min(86400.0, _ci_clock() - started)), 3)
        _ci_case_print("end", node_sha256=key, file=file, elapsed_seconds=elapsed)




def pytest_runtest_logreport(report):
    if report.when == "teardown":
        _ci_case_end(report.nodeid)
