"""Measured CI history overlay without rewriting frozen qualification drivers."""

import hashlib
import json
import re

import run_ci_budgeted_deployment as prior

driver = prior.driver
PROFILE = driver.ROOT / ".github/fixtures/retained_history_overlay.json"
COUNTS = {"2": 425, "3": 84, "10": 13}
INCREMENTS = {"3": 17000, "10": 14000}
BUDGETS = {"3": 80000, "10": 38000}
RETAINED_FAMILIES = ("test_anchored_operator_review.AnchoredReviewContracts.test_case_",
                     "test_history_backup.HistoryBackupContracts.test_case_",
                     "test_restore_authorization.RestoreAuthorizationContracts.test_case_",
                     "test_restore_lifecycle.RestoreLifecycleContracts.test_case_",
                     "test_enrollment_revocation.EnrollmentRevocationContracts.test_case_",
                     "test_withdrawal_backup.WithdrawalBackupContracts.test_case_")
SOURCES = ("scripts/run_ci_deployment_shard.py", "scripts/run_ci_budgeted_deployment.py", "scripts/run_ci_history_workers.py")


def digest_ok(value, length=64):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(length) + r"}", value) is not None


def profile(value=None):
    value = json.loads(PROFILE.read_text()) if value is None else value
    fields = {"schema", "manifest_sha256", "source_sha256", "observed_history_head", "observed_history_run",
              "retained_history_log_sha256", "observed_target_head", "observed_target_run", "retained_target_log_sha256",
              "original_counts", "original_history_ids_sha256", "worker_increment_budget_ms", "worker_budget_ms",
              "baseline_case_ms", "assignments"}
    if (not isinstance(value, dict) or set(value) != fields or value["schema"] != "ci-retained-history-overlay-v1"
            or value["manifest_sha256"] != hashlib.sha256(driver.MANIFEST.read_bytes()).hexdigest()
            or value["source_sha256"] != {n: hashlib.sha256((driver.ROOT / n).read_bytes()).hexdigest() for n in SOURCES}
            or value["original_counts"] != COUNTS or value["worker_increment_budget_ms"] != INCREMENTS
            or value["worker_budget_ms"] != BUDGETS or not digest_ok(value["original_history_ids_sha256"])
            or any(not digest_ok(value[k], 40) for k in ("observed_history_head", "observed_target_head"))
            or any(type(value[k]) is not int or value[k] <= 0 for k in ("observed_history_run", "observed_target_run"))
            or not digest_ok(value["retained_history_log_sha256"])
            or not isinstance(value["retained_target_log_sha256"], dict)
            or set(value["retained_target_log_sha256"]) != {"backend-and-contracts", "graph-runtime-contracts"}
            or any(not digest_ok(x) for x in value["retained_target_log_sha256"].values())
            or not isinstance(value["baseline_case_ms"], dict) or not isinstance(value["assignments"], list)
            or len(value["assignments"]) != 6):
        raise ValueError("Source-bound retained history profile required")
    return value


def assignments(tests, manifest, value=None):
    value = profile(value)
    original = {n: prior.plan(tests, manifest, int(n)) for n in COUNTS}
    if any(len(original[n]) != count for n, count in COUNTS.items()):
        raise ValueError("Exact original retained partitions required")
    ids = {n: [test.id() for test in rows] for n, rows in original.items()}
    if driver.digest(ids["2"]) != value["original_history_ids_sha256"]:
        raise ValueError("Original history identity commitment required")
    costs = dict(value["baseline_case_ms"])
    if (set(costs) != set(ids["3"] + ids["10"])
            or any(type(x) is not int or x < 0 for x in costs.values())):
        raise ValueError("Complete measured destination costs required")
    moved = {}
    for row in value["assignments"]:
        if (not isinstance(row, dict) or set(row) != {"test_id", "shard", "observed_case_ms"}
                or not isinstance(row["test_id"], str) or row["test_id"] not in ids["2"] or row["test_id"] in moved
                or type(row["shard"]) is not int or row["shard"] not in (3, 10)
                or type(row["observed_case_ms"]) is not int or row["observed_case_ms"] <= 0):
            raise ValueError("Six unique measured history identities required")
        if row["shard"] == 3 and row["test_id"].startswith(RETAINED_FAMILIES):
            raise ValueError("Retained history family must stay in its compatible assignment")
        moved[row["test_id"]], costs[row["test_id"]] = row["shard"], row["observed_case_ms"]
    for lane in ("3", "10"):
        selected = sorted(ids[lane] + [ident for ident, target in moved.items() if str(target) == lane])
        old_peak = max(sum(costs[x] for x in ids[lane][i::2]) for i in (0, 1))
        peak = max(sum(costs[x] for x in selected[i::2]) for i in (0, 1))
        if (sum(str(n) == lane for n in moved.values()) != 3 or peak > BUDGETS[lane]
                or peak - old_peak > INCREMENTS[lane]):
            raise ValueError("Both retained destination workers must fit measured reserves")
    return original, moved


def plan(tests, manifest, selected):
    if selected not in (2, 3, 10):
        return prior.plan(tests, manifest, selected)
    original, moved = assignments(tests, manifest)
    ids = {test.id() for test in original[str(selected)] if test.id() not in moved}
    ids.update(ident for ident, lane in moved.items() if lane == selected)
    return [test for test in tests if test.id() in ids]


def main():
    driver.plan = plan
    driver.__file__ = __file__
    return driver.main()


if __name__ == "__main__":
    raise SystemExit(main())
