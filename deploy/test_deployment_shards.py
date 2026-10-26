import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

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
        a, b, c, d = [{test.id() for test in runner.plan(tests, manifest, n)} for n in (1, 2, 3, 4)]
        self.assertFalse(a & b or a & c or a & d or b & c or b & d or c & d)
        self.assertEqual(a | b | c | d, {test.id() for test in tests})
        self.assertEqual(c, {test.id() for test in tests if test.id().startswith("test_staged_reader.StagedReaderContracts.")})
        self.assertEqual(d, {test.id() for test in tests if test.id().startswith("test_reader_lifecycle.ReaderLifecycleContracts.")})
        lifecycle = json.loads((ROOT / "deploy/fixtures/reader_lifecycle_policy.json").read_text())
        self.assertEqual({"test_reader_lifecycle.ReaderLifecycleContracts.test_case_" + row["id"] for row in lifecycle["cases"]}, {ident for ident in d if ".test_case_" in ident})
        policy = json.loads((ROOT / "deploy/fixtures/staged_reader_policy.json").read_text())
        self.assertEqual({"test_staged_reader.StagedReaderContracts.test_case_" + row["id"] for row in policy["cases"]}, {ident for ident in c if ident.startswith("test_staged_reader.StagedReaderContracts.test_case_")})
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
                self.assertEqual({name for name in a if name.startswith(prefix)}, expected)
                self.assertFalse(expected & (b | c | d))
            else:
                self.assertEqual({name for name in a | b if name.startswith(prefix)}, expected)
                self.assertTrue(expected & a)
                self.assertTrue(expected & b)

    def test_omitted_or_duplicate_test_is_rejected_before_execution(self):
        tests = [unittest.FunctionTestCase(lambda: None), unittest.FunctionTestCase(lambda: None)]
        with self.assertRaises(ValueError):
            runner.plan(tests, {"schema": "complete-deployment-test-manifest-v1", "test_ids": []}, 1)

    def test_incomplete_or_different_execution_is_rejected(self):
        result = SimpleNamespace(wasSuccessful=lambda: True, testsRun=1, executed_ids=["wrong"])
        with self.assertRaises(ValueError):
            runner.verify(result, ["expected"])


if __name__ == "__main__":
    unittest.main()
