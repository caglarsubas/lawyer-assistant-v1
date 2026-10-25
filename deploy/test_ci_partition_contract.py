"""Prevent duplicate backend selections and accidental CI resource escalation."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class PartitionContract(unittest.TestCase):
    def test_every_explicit_group_is_disjoint_and_excluded_from_remainder(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        groups = re.findall(r"^ {2,6}(CI_[A-Z_]+): >-\n((?: +backend/tests/[^\n]+\n)+)", workflow, re.MULTILINE)
        self.assertTrue(groups)
        self.assertEqual(len(groups), len({key for key, _ in groups}))
        seen = set()
        for key, body in groups:
            files = body.split()
            self.assertTrue(files, key)
            self.assertEqual(len(files), len(set(files)), key)
            self.assertFalse(seen.intersection(files), key)
            for path in files:
                self.assertTrue(path.startswith("backend/tests/test_") and path.endswith(".py"), path)
                self.assertTrue((ROOT / path).is_file(), path)
            seen.update(files)
        remainder = workflow.split("- name: Test backend\n", 1)[1].split("\n      - name:", 1)[0]
        variables = {key: variable for variable, key in re.findall(r'read -r -a (\w+) <<< "\$(CI_[A-Z_]+)"', remainder)}
        self.assertEqual(set(variables), {key for key, _ in groups})
        loop = next(line for line in remainder.splitlines() if "for path in " in line)
        for variable in variables.values():
            self.assertIn('"${' + variable + '[@]}"', loop)
        self.assertIn('ignore_args+=("--ignore=$path")', remainder)
        self.assertIn('pytest backend/tests "${ignore_args[@]}"', remainder)

    def test_graph_lane_is_bounded_and_existing_deadlines_are_preserved(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text().split("\njobs:\n", 1)[1]
        blocks = {name: body for name, body in re.findall(r"^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:\n|\Z)", workflow, re.MULTILINE | re.DOTALL)}
        caps = {"backend-and-contracts": 20, "postgres-snapshot-concurrency": 5, "frontend": 5, "frontend-history": 5,
                "final-release-authorization": 6, "retained-release-withdrawal": 3,
                "graph-candidate-contracts": 3, "source-publication-contracts": 3, "graph-runtime-contracts": 6}
        self.assertEqual(set(blocks), set(caps))
        for name, cap in caps.items():
            self.assertEqual(int(re.search(r"^    timeout-minutes: (\d+)$", blocks[name], re.MULTILINE)[1]), cap)
        graph = blocks["graph-runtime-contracts"]
        self.assertIn("runs-on: ubuntu-24.04-arm", graph)
        self.assertIn('"${graph_runtime_tests[@]}" -n 2 --dist worksteal --max-worker-restart=0 --maxfail=1', graph)
        self.assertEqual(graph.count("CI_GRAPH_RUNTIME_TESTS"), 1)

    def test_frontend_shards_keep_isolation_workers_and_complete_discovery(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        package = (ROOT / "frontend/package.json").read_text()
        self.assertEqual(workflow.count("npm test -- --shard=1/2"), 1)
        self.assertEqual(workflow.count("npm test -- --shard=2/2"), 1)
        self.assertEqual(workflow.count("node scripts/verify_frontend_shards.mjs"), 3)
        self.assertEqual(workflow.count("- run: npm run build"), 1)
        self.assertIn('"test": "vitest run --pool=threads --maxWorkers=2"', package)
        self.assertIn("npm test -- --shard=2/2 --maxWorkers=1", workflow)
        self.assertIn("python scripts/run_ci_history_workers.py", workflow)
        self.assertNotIn("--no-isolate", workflow + package)
        self.assertNotIn("--passWithNoTests", workflow + package)


if __name__ == "__main__":
    unittest.main()
