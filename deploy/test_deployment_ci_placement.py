"""Keep complete contract discovery exactly once within existing CI resources."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DeploymentPlacementContract(unittest.TestCase):
    def test_full_deployment_discovery_is_not_duplicated_or_left_in_backend_tail(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        command = "-m unittest discover -s deploy -p 'test_*.py'"
        self.assertEqual(workflow.count(command), 0)
        blocks = dict(re.findall(r"^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:\n|\Z)", workflow.split("\njobs:\n", 1)[1], re.MULTILINE | re.DOTALL))
        self.assertNotIn(command, blocks["backend-and-contracts"])
        self.assertEqual(workflow.count("scripts/run_ci_deployment_shard.py"), 11)
        self.assertIn("scripts/run_ci_deployment_shard.py --shard=3", blocks["backend-and-contracts"])
        for name, lane in (("backend-review-contracts", 4), ("backend-and-contracts", 5), ("backend-and-contracts", 6)):
            self.assertIn("scripts/run_ci_deployment_shard.py --shard=" + str(lane), blocks[name])
        self.assertLess(blocks["backend-and-contracts"].index("--shard=3"), blocks["backend-and-contracts"].index("name: Test backend"))
        self.assertIn("--shard=8 --workers=2", blocks["frontend"])
        self.assertIn("--shard=1 --workers=2", blocks["backend-review-contracts"])
        self.assertIn("scripts/run_ci_deployment_shard.py --shard=7", blocks["backend-and-contracts"])
        self.assertNotIn("--shard=7", blocks["frontend"])
        self.assertIn("scripts/run_ci_deployment_shard.py --shard=2", blocks["frontend-history"])
        self.assertIn("actions/setup-python@v5", blocks["frontend"])
        self.assertIn("uv sync --project backend --frozen --extra dev", blocks["frontend"])
        self.assertNotIn("name: Test confidential human review groups", blocks["backend-and-contracts"])
        self.assertEqual(workflow.count("name: Test confidential human review groups"), 1)
        self.assertIn("timeout-minutes: 3", blocks["frontend"].split("name: Test confidential human review groups", 1)[1])
        self.assertLess(blocks["frontend"].index("name: Verify executed frontend shard"), blocks["frontend"].index("name: Test confidential human review groups"))
        self.assertIn('"${human_review_tests[@]}" -q -n 2 --dist worksteal --max-worker-restart=0 --maxfail=1', blocks["frontend"])
        self.assertIn("actions/setup-python@v5", blocks["frontend-history"])
        self.assertIn("uv sync --project backend --frozen --extra dev", blocks["frontend-history"])
        self.assertIn("timeout-minutes: 5", blocks["frontend-history"])
        self.assertIn("runs-on: ubuntu-24.04-arm", blocks["frontend-history"])
        self.assertIn("runs-on: ubuntu-latest", blocks["frontend"])
        self.assertIn("timeout-minutes: 18", blocks["backend-and-contracts"])
        self.assertEqual(workflow.count("--workers=2"), 9)
        self.assertIn("--shard=3 --workers=2", blocks["backend-and-contracts"])
        backend = blocks["backend-and-contracts"]
        for lane in (5, 6, 7):
            self.assertIn("--shard=" + str(lane) + " --workers=2", backend)
            self.assertLess(backend.index("--shard=" + str(lane)), backend.index("name: Test backend"))
        for name in ("graph-candidate-contracts", "retained-release-withdrawal", "postgres-snapshot-concurrency"):
            self.assertNotIn("scripts/run_ci_deployment_shard.py", blocks[name])
        stages = re.findall(r"      - name: Test manifest-bound [^\n]+\n        timeout-minutes: (\d+)\n        run: [^\n]+--shard=(\d+)[^\n]+", backend)
        self.assertEqual(stages, [("2", "3"), ("1", "5"), ("1", "6"), ("1", "7")])
        final = blocks["final-release-authorization"]
        self.assertNotIn("--shard=6", final)
        postgres = blocks["postgres-snapshot-concurrency"]
        self.assertNotIn("name: Test workspace permission", backend)
        self.assertNotIn("name: Test workspace permission", postgres)
        self.assertIn('"${workspace_tests[@]}" -q -n 2 --dist worksteal --max-worker-restart=0 --maxfail=1', final)
        self.assertIn("timeout-minutes: 2", final.split("name: Test workspace permission", 1)[1])
        self.assertLess(final.index("name: Test whole-release permission"), final.index("name: Test workspace permission"))
        self.assertEqual(workflow.count("name: Test workspace permission and proposal contracts"), 1)
        graph = blocks["graph-runtime-contracts"]
        self.assertNotIn("--shard=4", graph)
        self.assertIn("--shard=4 --workers=2", blocks["backend-review-contracts"])
        self.assertLess(blocks["backend-review-contracts"].index("--shard=1"), blocks["backend-review-contracts"].index("--shard=4"))
        self.assertIn("timeout-minutes: 1", blocks["backend-review-contracts"].split("name: Test manifest-bound reader lifecycle slice 4", 1)[1])
        group = re.search(r"  CI_GRAPH_RUNTIME_TESTS: >-\n((?:    [^\n]+\n)+)", workflow)[1]
        self.assertEqual(group.count("backend/tests/test_open_validity_publication.py"), 1)
        self.assertNotIn("backend/tests/test_graph_b_snapshot.py", group)
        self.assertEqual(workflow.count("backend/tests/test_graph_b_snapshot.py"), 0)
        self.assertIn('"${graph_runtime_tests[@]}"', blocks["backend-and-contracts"])
        final_group = re.search(r"  CI_BACKEND_REVIEW_TESTS: >-\n((?:    [^\n]+\n)+)", workflow)[1]
        self.assertNotIn("backend/tests/test_set_publication_cli.py", final_group)
        self.assertEqual(final_group.count("backend/tests/test_private_inventory_receipts.py"), 1)
        self.assertEqual(workflow.count("backend/tests/test_private_inventory_receipts.py"), 1)
        self.assertIn('"${backend_review_tests[@]}"', blocks["backend-and-contracts"])
        candidate_group = re.search(r"  CI_GRAPH_CANDIDATE_TESTS: >-\n((?:    [^\n]+\n)+)", workflow)[1]
        self.assertEqual(candidate_group.count("backend/tests/test_staged_receipt_adapter.py"), 1)
        self.assertEqual(workflow.count("backend/tests/test_staged_receipt_adapter.py"), 1)
        review = blocks["backend-review-contracts"]
        self.assertLess(review.index("name: Test complete backend review"), review.index("name: Test complete manifest-bound assignment 1"))
        self.assertLess(blocks["frontend"].index("name: Test confidential human review groups"), blocks["frontend"].index("--shard=8"))
        self.assertIn("timeout-minutes: 1", blocks["frontend"].split("name: Test manifest-bound review headroom slice 8", 1)[1])
        self.assertNotIn("--shard=10", blocks["frontend-history"])
        self.assertNotIn("--shard=4", blocks["frontend"])
        self.assertNotIn("--shard=10", blocks["frontend"])
        self.assertLess(graph.index("name: Test complete graph assembly"), graph.index("--shard=10"))
        self.assertIn("--shard=10 --workers=2", graph)
        self.assertIn("timeout-minutes: 1", graph.split("name: Test manifest-bound review headroom slice 10", 1)[1])
        self.assertEqual(workflow.count("cache: pip"), 10)
        self.assertEqual(workflow.count("cache-dependency-path: backend/uv.lock"), 10)
        self.assertEqual(workflow.count("timeout --kill-after=2s 20s python -m pip install --disable-pip-version-check --no-input --retries 0 --timeout 10 uv==0.8.15"), 10)
        self.assertEqual(workflow.count("UV_HTTP_TIMEOUT=10 UV_HTTP_RETRIES=0 timeout --kill-after=2s 20s uv sync --project backend --frozen --extra dev"), 10)
        self.assertNotIn("--shard=9", backend)
        self.assertIn("--shard=9 --workers=2", blocks["frontend-history"])
        self.assertLess(blocks["frontend-history"].index("name: Verify executed frontend shard"), blocks["frontend-history"].index("--shard=9"))
        self.assertIn("timeout-minutes: 1", blocks["frontend-history"].split("name: Test manifest-bound review headroom slice 9", 1)[1])
        self.assertNotIn("name: Test registered local-model authority trials", backend)
        self.assertEqual(workflow.count("name: Test registered local-model authority trials"), 1)
        self.assertIn('"${model_trial_tests[@]}" -n 2 --dist worksteal --max-worker-restart=0 --maxfail=1', graph)
        self.assertIn("timeout-minutes: 2", graph.split("name: Test registered local-model authority trials", 1)[1])
        self.assertLess(review.index("--plan-only"), review.index("name: Test complete backend review"))

    def test_bounded_scratch_preserves_full_command_exit_and_cleanup(self):
        script = (ROOT / "scripts/run_ci_contracts.sh").read_text()
        self.assertIn('size=1024m,mode=1777,nosuid,nodev', script)
        self.assertIn('TMPDIR="$scratch" "$@"', script)
        self.assertIn('trap cleanup EXIT', script)
        self.assertIn('umount "$scratch"', script)
        self.assertIn('exit "$status"', script)
        self.assertNotIn('|| true', script)
        self.assertNotIn('retry', script)


if __name__ == "__main__":
    unittest.main()
