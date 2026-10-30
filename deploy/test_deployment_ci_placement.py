"""Keep complete contract discovery exactly once within existing CI resources."""

import os
import re
import shutil
import subprocess
import tempfile
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
        for name, lane in (("frontend", 4), ("backend-and-contracts", 5), ("backend-and-contracts", 6)):
            self.assertIn("scripts/run_ci_deployment_shard.py --shard=" + str(lane), blocks[name])
        self.assertLess(blocks["backend-and-contracts"].index("--shard=3"), blocks["backend-and-contracts"].index("name: Test backend"))
        self.assertIn("--shard=8 --workers=2", blocks["frontend"])
        self.assertIn("--shard=1 --workers=2", blocks["backend-review-contracts"])
        self.assertIn("scripts/run_ci_deployment_shard.py --shard=7", blocks["backend-and-contracts"])
        self.assertNotIn("--shard=7", blocks["frontend"])
        self.assertIn("scripts/run_ci_deployment_shard.py --shard=2", blocks["frontend-history"])
        self.assertIn("actions/setup-python@v5", blocks["frontend"])
        self.assertIn('"$uv_path" sync --project backend --frozen --extra dev', blocks["frontend"])
        self.assertNotIn("name: Test confidential human review groups", blocks["backend-and-contracts"])
        self.assertEqual(workflow.count("name: Test confidential human review groups"), 1)
        self.assertIn("timeout-minutes: 3", blocks["backend-review-contracts"].split("name: Test confidential human review groups", 1)[1])
        self.assertLess(blocks["backend-review-contracts"].index("name: Test complete backend review"), blocks["backend-review-contracts"].index("name: Test confidential human review groups"))
        self.assertIn('"${human_review_tests[@]}" -q -n 2 --dist worksteal --max-worker-restart=0 --maxfail=1', blocks["backend-review-contracts"])
        self.assertIn("actions/setup-python@v5", blocks["frontend-history"])
        self.assertIn('"$uv_path" sync --project backend --frozen --extra dev', blocks["frontend-history"])
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
        self.assertNotIn("name: Test workspace permission", final)
        self.assertIn('"${workspace_tests[@]}" -q -n 2 --dist worksteal --max-worker-restart=0 --maxfail=1', postgres)
        self.assertIn("timeout-minutes: 2", postgres.split("name: Test workspace permission", 1)[1])
        self.assertLess(postgres.index("name: Test real PostgreSQL review"), postgres.index("name: Test workspace permission"))
        self.assertEqual(workflow.count("name: Test workspace permission and proposal contracts"), 1)
        graph = blocks["graph-runtime-contracts"]
        self.assertNotIn("--shard=4", graph)
        self.assertIn("--shard=4 --workers=2", blocks["frontend"])
        self.assertNotIn("--shard=4", backend)
        self.assertLess(blocks["frontend"].index("--shard=8"), blocks["frontend"].index("--shard=4"))
        self.assertIn("timeout-minutes: 1", blocks["frontend"].split("name: Test manifest-bound reader lifecycle slice 4", 1)[1])
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
        self.assertNotIn("name: Test confidential human review groups", blocks["frontend"])
        self.assertIn("timeout-minutes: 1", blocks["frontend"].split("name: Test manifest-bound review headroom slice 8", 1)[1])
        self.assertNotIn("--shard=10", blocks["frontend-history"])
        self.assertNotIn("--shard=4", backend)
        self.assertNotIn("--shard=10", blocks["frontend"])
        self.assertLess(graph.index("name: Test complete graph assembly"), graph.index("--shard=10"))
        self.assertIn("--shard=10 --workers=2", graph)
        self.assertIn("timeout-minutes: 1", graph.split("name: Test manifest-bound review headroom slice 10", 1)[1])
        self.assertEqual(workflow.count("cache: pip"), 10)
        self.assertEqual(workflow.count("cache-dependency-path: |\n            backend/uv.lock\n            .github/scripts/install-uv.sh"), 10)
        self.assertEqual(workflow.count("timeout --kill-after=2s 20s bash .github/scripts/install-uv.sh"), 10)
        self.assertEqual(workflow.count("UV_HTTP_TIMEOUT=10 UV_HTTP_RETRIES=0 timeout --kill-after=2s 20s \"$uv_path\" sync --project backend --frozen --extra dev"), 10)
        self.assertNotIn("--shard=9", blocks["frontend-history"])
        self.assertIn("--shard=9 --workers=2", review)
        self.assertLess(review.index("--shard=1"), review.index("--shard=9"))
        self.assertNotIn("--shard=9", backend)
        self.assertIn("timeout-minutes: 1", review.split("name: Test manifest-bound review headroom slice 9", 1)[1])
        self.assertNotIn("name: Test registered local-model authority trials", backend)
        self.assertEqual(workflow.count("name: Test registered local-model authority trials"), 1)
        self.assertIn('"${model_trial_tests[@]}" -n 2 --dist worksteal --max-worker-restart=0 --maxfail=1', graph)
        self.assertIn("timeout-minutes: 2", graph.split("name: Test registered local-model authority trials", 1)[1])
        self.assertLess(review.index("--plan-only"), review.index("name: Test complete backend review"))
        self._bootstrap_rejections()

    def _bootstrap_rejections(self):
        script = ROOT / ".github/scripts/install-uv.sh"
        self.assertIn("--max-time 15 --retry 0", script.read_text())
        self.assertIn("sha256sum --check --status", script.read_text())
        for kind in ("unsupported_arch", "poisoned_cache", "symlink_cache"):
            with self.subTest(bootstrap=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                commands = root / "bin"
                commands.mkdir()
                uname = commands / "uname"
                uname.write_text("#!/bin/sh\nif [ \"$1\" = -s ]; then echo Linux; else echo " + ("unsupported" if kind == "unsupported_arch" else "aarch64") + "; fi\n")
                uname.chmod(0o700)
                cache = root / "pip/lawyer-ci-uv/0.8.15"
                cache.mkdir(parents=True)
                archive = cache / "uv-aarch64-unknown-linux-gnu-6ede0fefa7db7be3d5d9eda8784a8e43b1cf5410720eb3da60ab1d2f66678e82.tar.gz"
                outside = root / "untrusted"
                outside.write_bytes(b"wrong archive; never execute")
                if kind == "symlink_cache":
                    archive.symlink_to(outside)
                elif kind == "poisoned_cache":
                    if not shutil.which("sha256sum"):
                        continue  # Linux CI has coreutils; unsupported/link guards run everywhere.
                    archive.write_bytes(outside.read_bytes())
                env = {**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                       "PIP_CACHE_DIR": str(root / "pip"), "RUNNER_TEMP": str(root), "GITHUB_PATH": str(root / "export")}
                result = subprocess.run(["bash", str(script)], env=env, capture_output=True, timeout=3)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((root / "export").exists())
                self.assertEqual(outside.read_bytes(), b"wrong archive; never execute")
                self.assertFalse(list(root.glob("lawyer-uv.*")))

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
