"""Keep complete contract discovery exactly once within existing CI resources."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DeploymentPlacementContract(unittest.TestCase):
    def test_full_deployment_discovery_is_not_duplicated_or_left_in_backend_tail(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        command = "-m unittest discover -s deploy -p 'test_*.py'"
        self.assertEqual(workflow.count(command), 1)
        blocks = dict(re.findall(r"^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:\n|\Z)", workflow.split("\njobs:\n", 1)[1], re.MULTILINE | re.DOTALL))
        self.assertNotIn(command, blocks["backend-and-contracts"])
        self.assertNotIn(command, blocks["frontend-history"])
        self.assertIn("backend/.venv/bin/python " + command, blocks["frontend"])
        self.assertIn("actions/setup-python@v5", blocks["frontend"])
        self.assertIn("uv sync --project backend --frozen --extra dev", blocks["frontend"])
        self.assertIn("timeout-minutes: 5", blocks["frontend"])
        self.assertIn("timeout-minutes: 18", blocks["backend-and-contracts"])


if __name__ == "__main__":
    unittest.main()
