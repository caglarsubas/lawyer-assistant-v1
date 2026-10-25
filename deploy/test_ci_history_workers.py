import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_ci_history_workers import commands, run  # noqa: E402


class HistoryWorkerContracts(unittest.TestCase):
    def test_discovery_and_two_worker_budget_are_closed(self):
        node = ["npm", "test", "--", "--shard=2/2", "--maxWorkers=1", "--reporter=default", "--reporter=json", "--outputFile=/tmp/invented.json"]
        contract = ["bash", "scripts/run_ci_contracts.sh", "backend/.venv/bin/python", "-m", "unittest", "discover", "-s", "deploy", "-p", "test_*.py"]
        self.assertEqual(commands([*node, ":::", *contract]), (node, contract))
        for invalid in ([*node[:4], "--maxWorkers=2", *node[5:], ":::", *contract], [*node, ":::", *contract[:-1], "subset.py"]):
            with self.assertRaises(ValueError):
                commands(invalid)

    def test_real_children_overlap_and_complete_once(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            program = "from pathlib import Path;import sys,time;p=Path(sys.argv[1]);p.write_text('started');end=time.monotonic()+2\nwhile not Path(sys.argv[2]).exists():\n if time.monotonic()>end:raise SystemExit(7)\n time.sleep(.01)\np.write_text('complete')"
            a = [sys.executable, "-c", program, str(root / "a"), str(root / "b")]
            b = [sys.executable, "-c", program, str(root / "b"), str(root / "a")]
            self.assertEqual(run(a, b, node_cwd=root, contract_cwd=root), 0)
            self.assertEqual((root / "a").read_text(), "complete")
            self.assertEqual((root / "b").read_text(), "complete")

    def test_failed_worker_status_is_preserved_and_peer_is_reaped(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            peer = [sys.executable, "-c", "import os,time;from pathlib import Path;Path('pid').write_text(str(os.getpid()));time.sleep(20)"]
            failure = [sys.executable, "-c", "import time;from pathlib import Path\nwhile not Path('pid').exists():time.sleep(.01)\nraise SystemExit(17)"]
            self.assertEqual(run(peer, failure, node_cwd=root, contract_cwd=root), 17)
            import os
            with self.assertRaises(ProcessLookupError):
                os.kill(int((root / "pid").read_text()), 0)


if __name__ == "__main__":
    unittest.main()
