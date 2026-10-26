"""Source-manifest-bound disjoint deployment tests; one sequential worker per lane."""

import argparse
import hashlib
import json
import re
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "deploy/fixtures/deployment_test_manifest.json"

def flatten(suite):
    result = []
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            result.extend(flatten(test))
        elif isinstance(test, unittest.TestCase):
            result.append(test)
        else:
            raise ValueError("Closed deployment discovery required")
    return result


def collect():
    sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend"), str(ROOT / "deploy")]
    tests = flatten(unittest.defaultTestLoader.discover(str(ROOT / "deploy"), pattern="test_*.py"))
    ids = [test.id() for test in tests]
    if not ids or len(ids) != len(set(ids)) or any(isinstance(test, unittest.loader._FailedTest) for test in tests):
        raise ValueError("Complete unique deployment discovery required")
    return sorted(tests, key=lambda test: test.id())


NAMESPACE_WORKLOAD = ROOT / "deploy/fixtures/reader_namespace_ci_workload.json"
NAMESPACE_BUDGET_MS = {"1": 12000, "3": 20000, "4": 12000, "5": 12000, "6": 6000, "7": 14000}


def namespace_assignments(ids, profile=None):
    value = json.loads(NAMESPACE_WORKLOAD.read_text()) if profile is None else profile
    expected = [ident for ident in ids if ident.startswith("test_reader_namespace.ReaderNamespaceContracts.")]
    source = json.loads((ROOT / "deploy/fixtures/reader_namespace_first_report.json").read_text())["candidate"]["source"]
    for name, expected_sha in source.items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
            raise ValueError("Current qualified namespace source required before execution")
    source_sha = hashlib.sha256(json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if (not isinstance(value, dict) or set(value) != {"schema", "qualification_source_sha256", "observed_head", "observed_run", "retained_log_sha256", "lane_case_budget_ms", "assignments", "graph_rebalance"}
            or value["schema"] != "reader-namespace-ci-workload-v1" or value["qualification_source_sha256"] != source_sha
            or not re.fullmatch(r"[0-9a-f]{40}", value["observed_head"]) or type(value["observed_run"]) is not int or value["observed_run"] <= 0
            or not re.fullmatch(r"[0-9a-f]{64}", value["retained_log_sha256"]) or value["lane_case_budget_ms"] != NAMESPACE_BUDGET_MS
            or not isinstance(value["assignments"], list) or len(value["assignments"]) != len(expected)):
        raise ValueError("Source-bound namespace work profile required")
    result, sums = {}, dict.fromkeys(NAMESPACE_BUDGET_MS, 0)
    for row in value["assignments"]:
        if (not isinstance(row, dict) or set(row) != {"test_id", "shard", "observed_case_ms"}
                or row["test_id"] in result or row["test_id"] not in expected or type(row["shard"]) is not int
                or str(row["shard"]) not in sums or type(row["observed_case_ms"]) is not int or row["observed_case_ms"] <= 0):
            raise ValueError("Closed unique namespace assignments required")
        result[row["test_id"]] = row["shard"]
        sums[str(row["shard"])] += row["observed_case_ms"]
    if sorted(result) != expected or any(sums[n] > budget for n, budget in NAMESPACE_BUDGET_MS.items()):
        raise ValueError("Complete namespace assignments within measured budgets required")
    change = value["graph_rebalance"]
    lifecycle_ids = sorted((ident for ident in ids if ident.startswith("test_reader_lifecycle.ReaderLifecycleContracts.")),
                           key=lambda ident: hashlib.sha256(ident.encode()).digest())
    if (not isinstance(change, dict) or set(change) != {"observed_head", "observed_run", "retained_log_sha256", "moved"}
            or not re.fullmatch(r"[0-9a-f]{40}", change["observed_head"]) or type(change["observed_run"]) is not int or change["observed_run"] <= 0
            or not re.fullmatch(r"[0-9a-f]{64}", change["retained_log_sha256"]) or not isinstance(change["moved"], list) or len(change["moved"]) != 7):
        raise ValueError("Exact retained graph rebalance required")
    moved, cost = set(), 0
    for row in change["moved"]:
        if (not isinstance(row, dict) or set(row) != {"test_id", "observed_case_ms"}
                or row["test_id"] in moved or row["test_id"] not in lifecycle_ids[12:]
                or type(row["observed_case_ms"]) is not int or row["observed_case_ms"] <= 0):
            raise ValueError("Unique graph-runtime cases required")
        moved.add(row["test_id"])
        cost += row["observed_case_ms"]
        result[row["test_id"]] = 7
    if cost > 25000:
        raise ValueError("Bounded PostgreSQL case increment required")
    return result


def shard(test_id, lifecycle_ids, namespace):
    if test_id.startswith("test_reader_namespace.ReaderNamespaceContracts."):
        return namespace[test_id]  # A source-bound measured budget; no extra worker.
    if test_id.startswith("test_reader_lifecycle.ReaderLifecycleContracts."):
        if test_id in namespace:
            return namespace[test_id]
        # Measured 65s group is disjointly distributed over existing reserves.
        rank = sorted(lifecycle_ids, key=lambda ident: hashlib.sha256(ident.encode()).digest()).index(test_id)
        return 5 if rank < 4 else 6 if rank < 12 else 4
    if test_id.startswith(("test_staged_reader.StagedReaderContracts.", "test_authenticated_operator_review.AuthenticatedOperatorContracts.")):
        return 3  # Keep the complete original authenticated groups together.
    key = int.from_bytes(hashlib.sha256(test_id.encode()).digest()[:4], "big")
    # Existing ordinary and retained frozen-case assignments stay unchanged.
    return (1 if key % 5 < 2 else 2) if re.search(r"\.test_case_[A-Z][0-9]{2}_", test_id) else key % 2 + 1


def digest(ids):
    return hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()


def plan(tests, manifest, selected):
    ids = [test.id() for test in tests]
    if (selected not in {1, 2, 3, 4, 5, 6, 7} or manifest != {"schema": "complete-deployment-test-manifest-v1", "test_ids": ids}
            or ids != sorted(set(ids)) or not ids):
        raise ValueError("Source-bound complete test manifest required")
    lifecycle_ids = [ident for ident in ids if ident.startswith("test_reader_lifecycle.ReaderLifecycleContracts.")]
    namespace = namespace_assignments(ids)
    sets = [{ident for ident in ids if shard(ident, lifecycle_ids, namespace) == lane} for lane in (1, 2, 3, 4, 5, 6, 7)]
    if not all(sets) or any(a & b for n, a in enumerate(sets) for b in sets[n + 1:]) or set.union(*sets) != set(ids):
        raise ValueError("Complete disjoint shards required")
    return [test for test in tests if test.id() in sets[selected - 1]]


class ExecutedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executed_ids = []
        self.case_seconds = {}

    def startTest(self, test):
        self.executed_ids.append(test.id())
        self.case_started = time.monotonic()
        print(json.dumps({"contract_started": test.id()}), flush=True)
        super().startTest(test)

    def stopTest(self, test):
        elapsed = round(time.monotonic() - self.case_started, 3)
        self.case_seconds[test.id()] = elapsed
        print(json.dumps({"contract_completed": test.id(), "seconds": elapsed}), flush=True)
        super().stopTest(test)


def verify(result, expected):
    if not result.wasSuccessful() or result.testsRun != len(expected) or result.executed_ids != expected or not expected:
        raise ValueError("Assigned deployment tests did not execute completely")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, choices=(1, 2, 3, 4, 5, 6, 7), required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    tests = collect()
    raw = MANIFEST.read_bytes()
    selected = plan(tests, json.loads(raw), args.shard)
    expected = [test.id() for test in selected]
    result = unittest.TextTestRunner(resultclass=ExecutedResult).run(unittest.TestSuite(selected))
    report = {"schema": "deployment-shard-result-v1", "shard": args.shard, "total_shards": 7,
              "manifest_sha256": hashlib.sha256(raw).hexdigest(), "complete_suite_sha256": digest([test.id() for test in tests]),
              "selected_ids": expected, "executed_ids": result.executed_ids, "tests_run": result.testsRun,
              "case_seconds": result.case_seconds,
              "complete_count": len(tests), "success": result.wasSuccessful()}
    with args.report.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    verify(result, expected)
    print(json.dumps({"deployment_shard": args.shard, "tests_run": result.testsRun, "complete_count": len(tests), "manifest_sha256": report["manifest_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
