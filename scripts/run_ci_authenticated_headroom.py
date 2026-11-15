"""Move measured contract work out of the authenticated qualification step."""

import hashlib
import json

import run_ci_retained_deployment as retained

driver = retained.driver
PROFILE = driver.ROOT / ".github/fixtures/authenticated_headroom_workload.json"
SOURCE_PATHS = ("scripts/run_ci_deployment_shard.py", "scripts/run_ci_retained_deployment.py",
                "scripts/run_ci_budgeted_deployment.py", "scripts/run_ci_history_workers.py")
CASE_BUDGET_MS = {3: 80000, 9: 24500}


def worker_loads(ids, costs):
    """Match the frozen executor's alternating allocation on sorted identities."""
    return tuple(sum(costs[ident] for ident in ids[index::2]) for index in (0, 1))


def allocations(tests, manifest, profile=None):
    value = json.loads(PROFILE.read_text()) if profile is None else profile
    if (not isinstance(value, dict)
            or set(value) != {"schema", "manifest_sha256", "source_sha256", "observations", "transferred_ids", "case_ms"}
            or value["schema"] != "ci-authenticated-headroom-v1"
            or value["manifest_sha256"] != hashlib.sha256(driver.MANIFEST.read_bytes()).hexdigest()
            or value["source_sha256"] != {
                name: hashlib.sha256((driver.ROOT / name).read_bytes()).hexdigest() for name in SOURCE_PATHS
            }):
        raise ValueError("Current closed manifest and frozen executors required")

    observed = value["observations"]
    if (not isinstance(observed, dict) or set(observed) != {"head", "run", "attempt", "logs_sha256"}
            or not retained.digest_ok(observed["head"], 40)
            or any(type(observed[key]) is not int or observed[key] <= 0 for key in ("run", "attempt"))
            or not isinstance(observed["logs_sha256"], dict)
            or set(observed["logs_sha256"]) != {"3", "9"}
            or not all(retained.digest_ok(digest) for digest in observed["logs_sha256"].values())):
        raise ValueError("Source-bound timing evidence for both steps required")

    before = {lane: [test.id() for test in retained.plan(tests, manifest, lane)] for lane in CASE_BUDGET_MS}
    costs, moved = value["case_ms"], value["transferred_ids"]
    if (not isinstance(costs, dict) or set(costs) != set(before[3] + before[9])
            or any(type(cost) is not int or cost < 0 for cost in costs.values())):
        raise ValueError("Complete measured source and destination case costs required")
    if (not isinstance(moved, list) or not moved or any(not isinstance(ident, str) for ident in moved)
            or moved != sorted(set(moved)) or not set(moved) <= set(before[3])
            or any(costs[ident] <= 0 for ident in moved)):
        raise ValueError("Unique measured transfers from the authenticated step required")

    selected = {3: sorted(set(before[3]) - set(moved)), 9: sorted(before[9] + moved)}
    for lane, ids in selected.items():
        if len(ids) < 2 or max(worker_loads(ids, costs)) > CASE_BUDGET_MS[lane]:
            raise ValueError("Both workers must fit the measured case budgets")
    by_id = {test.id(): test for test in tests}
    return {lane: [by_id[ident] for ident in ids] for lane, ids in selected.items()}


def plan(tests, manifest, shard):
    if shard not in CASE_BUDGET_MS:
        return retained.plan(tests, manifest, shard)
    return allocations(tests, manifest)[shard]


def main():
    # Keep the existing process lifecycle and exact execution receipt checks.
    driver.plan = plan
    driver.__file__ = __file__
    return driver.main()


if __name__ == "__main__":
    raise SystemExit(main())
