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

    def test_both_shards_cover_each_test_exactly_once(self):
        tests = runner.collect()
        manifest = json.loads(runner.MANIFEST.read_text())
        a, b = [{test.id() for test in runner.plan(tests, manifest, n)} for n in (1, 2)]
        self.assertTrue(runner.ARM_AFFINITY <= b)
        self.assertTrue(runner.X86_AFFINITY <= a)
        self.assertFalse(a & b)
        self.assertEqual(a | b, {test.id() for test in tests})

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
