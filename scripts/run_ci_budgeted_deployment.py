"""CI-only measured overlay; retain the frozen driver and every original test."""

import hashlib
import json
import re
from pathlib import Path

import run_ci_deployment_shard as driver

PROFILE = driver.ROOT / ".github/fixtures/authenticated_reserve_overlay.json"
ORIGINAL_PLAN = driver.plan
ORIGINAL_DRIVER = Path(driver.__file__)
COUNTS = {"1": 385, "3": 90, "10": 11}
BUDGETS = {"1": 10000, "10": 6000}


def assignments(tests, manifest, profile=None):
    value = json.loads(PROFILE.read_text()) if profile is None else profile
    keys = {"schema", "manifest_sha256", "driver_sha256", "observed_head", "observed_run",
            "retained_log_sha256", "original_counts", "worker_increment_budget_ms", "assignments"}
    if (not isinstance(value, dict) or set(value) != keys
            or value["schema"] != "ci-authenticated-reserve-overlay-v1"
            or value["manifest_sha256"] != hashlib.sha256(driver.MANIFEST.read_bytes()).hexdigest()
            or value["driver_sha256"] != hashlib.sha256(ORIGINAL_DRIVER.read_bytes()).hexdigest()
            or value["original_counts"] != COUNTS or value["worker_increment_budget_ms"] != BUDGETS
            or not isinstance(value["observed_head"], str) or not re.fullmatch(r"[0-9a-f]{40}", value["observed_head"])
            or type(value["observed_run"]) is not int or value["observed_run"] <= 0
            or not isinstance(value["retained_log_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["retained_log_sha256"])
            or not isinstance(value["assignments"], list) or len(value["assignments"]) != 6):
        raise ValueError("Closed source-bound measured CI overlay required")
    original = {lane: ORIGINAL_PLAN(tests, manifest, int(lane)) for lane in COUNTS}
    if any(len(original[lane]) != count for lane, count in COUNTS.items()):
        raise ValueError("Original deployment identities and counts required")
    source = {test.id() for test in original["3"]}
    moved, costs = {}, {}
    for row in value["assignments"]:
        if (not isinstance(row, dict) or set(row) != {"test_id", "shard", "observed_case_ms"}
                or not isinstance(row["test_id"], str) or row["test_id"] not in source or row["test_id"] in moved
                or type(row["shard"]) is not int or row["shard"] not in (1, 10)
                or type(row["observed_case_ms"]) is not int or row["observed_case_ms"] <= 0):
            raise ValueError("Six unique original authenticated identities required")
        moved[row["test_id"]], costs[row["test_id"]] = row["shard"], row["observed_case_ms"]
    for lane, count in ((1, 4), (10, 2)):
        selected = sorted([test.id() for test in original[str(lane)]] + [ident for ident in moved if moved[ident] == lane])
        if (sum(n == lane for n in moved.values()) != count
                or any(sum(costs.get(ident, 0) for ident in selected[i::2]) > BUDGETS[str(lane)] for i in (0, 1))):
            raise ValueError("Existing destination worker reserves must cover measured increments")
    return original, moved


def plan(tests, manifest, selected):
    if selected not in (1, 3, 10):
        return ORIGINAL_PLAN(tests, manifest, selected)
    original, moved = assignments(tests, manifest)
    ids = {test.id() for test in original[str(selected)] if test.id() not in moved}
    ids.update(ident for ident, lane in moved.items() if lane == selected)
    return [test for test in tests if test.id() in ids]


def main():
    # The unchanged parallel implementation launches this same overlay in both
    # children. Its exact-ID, actual-execution and receipt verification remains.
    driver.plan = plan
    driver.__file__ = __file__
    return driver.main()


if __name__ == "__main__":
    raise SystemExit(main())
