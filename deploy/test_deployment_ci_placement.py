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
        self.assertEqual(workflow.count("scripts/run_ci_deployment_shard.py"), 7)
        self.assertIn("scripts/run_ci_deployment_shard.py --shard=3", blocks["backend-and-contracts"])
        for name, lane in (("graph-runtime-contracts", 4), ("graph-candidate-contracts", 5), ("retained-release-withdrawal", 6)):
            self.assertIn("scripts/run_ci_deployment_shard.py --shard=" + str(lane), blocks[name])
        self.assertLess(blocks["backend-and-contracts"].index("--shard=3"), blocks["backend-and-contracts"].index("name: Test backend"))
        self.assertIn("scripts/run_ci_deployment_shard.py --shard=1", blocks["frontend"])
        self.assertIn("scripts/run_ci_deployment_shard.py --shard=7", blocks["postgres-snapshot-concurrency"])
        self.assertNotIn("--shard=7", blocks["frontend"])
        self.assertIn("scripts/run_ci_deployment_shard.py --shard=2", blocks["frontend-history"])
        self.assertIn("actions/setup-python@v5", blocks["frontend"])
        self.assertIn("uv sync --project backend --frozen --extra dev", blocks["frontend"])
        self.assertIn("actions/setup-python@v5", blocks["frontend-history"])
        self.assertIn("uv sync --project backend --frozen --extra dev", blocks["frontend-history"])
        self.assertIn("timeout-minutes: 5", blocks["frontend-history"])
        self.assertIn("runs-on: ubuntu-24.04-arm", blocks["frontend-history"])
        self.assertIn("runs-on: ubuntu-latest", blocks["frontend"])
        self.assertIn("timeout-minutes: 18", blocks["backend-and-contracts"])
        self.assertEqual(workflow.count("--workers=2"), 3)
        self.assertIn("--shard=3 --workers=2", blocks["backend-and-contracts"])
        self.assertIn("--shard=6 --workers=2", blocks["retained-release-withdrawal"])
        graph = blocks["graph-runtime-contracts"]
        self.assertIn("--shard=4 --workers=2", graph)
        self.assertLess(graph.index("name: Test complete graph assembly"), graph.index("name: Test manifest-bound reader lifecycle"))
        self.assertIn("timeout-minutes: 1", graph.split("name: Test manifest-bound reader lifecycle", 1)[1])
        group = re.search(r"  CI_GRAPH_RUNTIME_TESTS: >-\n((?:    [^\n]+\n)+)", workflow)[1]
        self.assertEqual(group.count("backend/tests/test_open_validity_publication.py"), 1)
        self.assertNotIn("backend/tests/test_graph_b_snapshot.py", group)
        self.assertEqual(workflow.count("backend/tests/test_graph_b_snapshot.py"), 0)
        self.assertIn('"${graph_runtime_tests[@]}"', blocks["backend-and-contracts"])
        final_group = re.search(r"  CI_FINAL_RELEASE_TESTS: >-\n((?:    [^\n]+\n)+)", workflow)[1]
        self.assertEqual(final_group.count("backend/tests/test_set_publication_cli.py"), 1)
        self.assertNotIn("--workers=2", blocks["frontend"])
        self.assertNotIn("--workers=2", blocks["frontend-history"])

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
