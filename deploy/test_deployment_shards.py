import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_ci_deployment_shard as runner  # noqa: E402


class DeploymentShardContracts(unittest.TestCase):
    def test_committed_manifest_matches_complete_unique_discovery(self):
        tests = runner.collect()
        self.assertEqual(json.loads(runner.MANIFEST.read_text()), {"schema": "complete-deployment-test-manifest-v1", "test_ids": [test.id() for test in tests]})

    def test_all_shards_cover_each_test_exactly_once(self):
        tests = runner.collect()
        manifest = json.loads(runner.MANIFEST.read_text())
        a, b, c, d, e, f, g = [{test.id() for test in runner.plan(tests, manifest, n)} for n in (1, 2, 3, 4, 5, 6, 7)]
        shards = (a, b, c, d, e, f, g)
        self.assertFalse(any(left & right for i, left in enumerate(shards) for right in shards[i + 1:]))
        self.assertEqual(a | b | c | d | e | f | g, {test.id() for test in tests})
        self.assertEqual({ident for ident in c | f if ident.startswith(("test_staged_reader.StagedReaderContracts.", "test_authenticated_operator_review.AuthenticatedOperatorContracts."))}, {test.id() for test in tests if test.id().startswith(("test_staged_reader.StagedReaderContracts.", "test_authenticated_operator_review.AuthenticatedOperatorContracts."))})
        self.assertEqual({ident for ident in d | e | f | g if ident.startswith("test_reader_lifecycle.")}, {test.id() for test in tests if test.id().startswith("test_reader_lifecycle.ReaderLifecycleContracts.")})
        self.assertEqual([sum(ident.startswith("test_reader_lifecycle.") for ident in lane) for lane in (d, e, f, g)], [5, 4, 8, 7])
        namespace_ids = {test.id() for test in tests if test.id().startswith("test_reader_namespace.ReaderNamespaceContracts.")}
        self.assertEqual(namespace_ids, {ident for ident in a | c | d | e | f | g if ident.startswith("test_reader_namespace.")})
        self.assertFalse(namespace_ids & b)
        namespace = json.loads((ROOT / "deploy/fixtures/reader_namespace_policy.json").read_text())
        self.assertEqual({"test_reader_namespace.ReaderNamespaceContracts.test_case_" + row["id"] for row in namespace["cases"]}, {ident for ident in namespace_ids if ".test_case_" in ident})
        lifecycle = json.loads((ROOT / "deploy/fixtures/reader_lifecycle_policy.json").read_text())
        self.assertEqual({"test_reader_lifecycle.ReaderLifecycleContracts.test_case_" + row["id"] for row in lifecycle["cases"]}, {ident for ident in d | e | f | g if ident.startswith("test_reader_lifecycle.ReaderLifecycleContracts.test_case_")})
        policy = json.loads((ROOT / "deploy/fixtures/staged_reader_policy.json").read_text())
        self.assertEqual({"test_staged_reader.StagedReaderContracts.test_case_" + row["id"] for row in policy["cases"]}, {ident for ident in c | f if ident.startswith("test_staged_reader.StagedReaderContracts.test_case_")})
        for module, cls, policy in [("test_authenticated_operator_review", "AuthenticatedOperatorContracts", "authenticated_operator_policy.json"),
                                    ("test_anchored_operator_review", "AnchoredReviewContracts", "anchored_review_policy.json"),
                                    ("test_history_backup", "HistoryBackupContracts", "history_backup_policy.json"),
                                    ("test_restore_authorization", "RestoreAuthorizationContracts", "restore_authorization_policy.json"),
                                    ("test_restore_lifecycle", "RestoreLifecycleContracts", "restore_lifecycle_policy.json"),
                                    ("test_enrollment_revocation", "EnrollmentRevocationContracts", "enrollment_revocation_policy.json"),
                                    ("test_withdrawal_backup", "WithdrawalBackupContracts", "withdrawal_backup_policy.json")]:
            prefix = module + "." + cls + ".test_case_"
            expected = {prefix + row["id"] for row in json.loads((ROOT / "deploy/fixtures" / policy).read_text())["cases"]}
            if module == "test_authenticated_operator_review":
                self.assertEqual({name for name in c if name.startswith(prefix)}, expected)
                self.assertFalse(expected & (a | b | d | e | f | g))
            else:
                self.assertEqual({name for name in a | b if name.startswith(prefix)}, expected)
                self.assertTrue(expected & a)
                self.assertTrue(expected & b)

    def test_namespace_work_profile_rejects_missing_duplicate_stale_over_budget_or_unknown_assignments(self):
        ids = [test.id() for test in runner.collect()]
        original = json.loads(runner.NAMESPACE_WORKLOAD.read_text())
        self.assertEqual(len(runner.namespace_assignments(ids)), 38)
        original_read = Path.read_bytes
        changed = ROOT / "scripts/reader_namespace.py"
        with patch.object(Path, "read_bytes", lambda path: b"changed" if path == changed else original_read(path)), self.assertRaises(ValueError):
            runner.namespace_assignments(ids, original)
        for kind in ("missing", "duplicate", "source", "budget", "lane", "graph_duplicate", "graph_cost", "backend_duplicate", "backend_cost", "unknown"):
            value = copy.deepcopy(original)
            if kind == "missing":
                value["assignments"].pop()
            elif kind == "duplicate":
                value["assignments"][1] = value["assignments"][0]
            elif kind == "source":
                value["qualification_source_sha256"] = "0" * 64
            elif kind == "budget":
                value["assignments"][0]["observed_case_ms"] = 1000000
            elif kind == "lane":
                value["assignments"][0]["shard"] = 2
            elif kind == "graph_duplicate":
                value["graph_rebalance"]["moved"][1] = value["graph_rebalance"]["moved"][0]
            elif kind == "graph_cost":
                value["graph_rebalance"]["moved"][0]["observed_case_ms"] = 1000000
            elif kind == "backend_duplicate":
                value["backend_rebalance"]["moved"][1] = value["backend_rebalance"]["moved"][0]
            elif kind == "backend_cost":
                value["backend_rebalance"]["moved"][0]["observed_case_ms"] = 1000000
            else:
                value["assignments"][0]["unexpected"] = True
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                runner.namespace_assignments(ids, value)

    def test_omitted_or_duplicate_test_is_rejected_before_execution(self):
        tests = [unittest.FunctionTestCase(lambda: None), unittest.FunctionTestCase(lambda: None)]
        with self.assertRaises(ValueError):
            runner.plan(tests, {"schema": "complete-deployment-test-manifest-v1", "test_ids": []}, 1)

    def test_parallel_receipts_reject_failure_missing_duplicate_or_stale_work(self):
        expected, complete, sha = ["a", "b", "c", "d"], ["a", "b", "c", "d", "e"], "0" * 64
        reports = [{"schema": "deployment-shard-result-v1", "shard": 3, "total_shards": 7,
                    "manifest_sha256": sha, "complete_suite_sha256": runner.digest(complete),
                    "selected_ids": expected[index::2], "executed_ids": expected[index::2],
                    "tests_run": 2, "case_seconds": dict.fromkeys(expected[index::2], .1),
                    "complete_count": 5, "success": True, "worker_index": index, "worker_count": 2} for index in (0, 1)]
        for lane in (1, 3, 4, 5, 6, 7):
            paired = copy.deepcopy(reports)
            for row in paired:
                row["shard"] = lane
            self.assertEqual(runner.merge_workers(paired, expected, complete, sha, lane), dict.fromkeys(expected, .1))
        for kind in ("failure", "missing", "duplicate", "stale", "wrong_worker", "count", "cost", "extra", "third_worker"):
            changed = copy.deepcopy(reports)
            if kind == "failure":
                changed[1]["success"] = False
            elif kind == "missing":
                changed[1]["executed_ids"].pop()
            elif kind == "duplicate":
                changed[1] = changed[0]
            elif kind == "stale":
                changed[1]["complete_suite_sha256"] = "1" * 64
            elif kind == "wrong_worker":
                changed[1]["worker_index"] = 0
            elif kind == "count":
                changed[1]["tests_run"] = 1
            elif kind == "cost":
                changed[1]["case_seconds"]["b"] = float("nan")
            elif kind == "extra":
                changed[1]["executed_ids"].append("e")
            else:
                changed.append(changed[0])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                runner.merge_workers(changed, expected, complete, sha, 3)

    def test_incomplete_or_different_execution_is_rejected(self):
        result = SimpleNamespace(wasSuccessful=lambda: True, testsRun=1, executed_ids=["wrong"])
        with self.assertRaises(ValueError):
            runner.verify(result, ["expected"])


if __name__ == "__main__":
    unittest.main()
