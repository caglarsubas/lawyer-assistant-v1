import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_roadmap_sanity import audit_snapshot, validate_catalog
from roadmap_backlog import project
from roadmap_delivery import readiness
from roadmap_progress import distribution

COMMIT = "1" * 40
PINS = {"docs/ROADMAP.md": "0" * 64}


class RoadmapSanityTests(unittest.TestCase):
    def setUp(self):
        items = [
            {
                "id": ident, "title": ident, "status": status, "milestone": "M",
                "source_path": "docs/ROADMAP.md", "dependencies": dependencies,
                "scope": scope, "remaining_gate": "Representative target evaluation.",
                "code": ["backend/app/example.py"], "tests": ["backend/tests/test_example.py"],
                "evidence": [],
            }
            for ident, status, dependencies, scope in [
                ("M-1", "waiting", [], "partial"),
                ("M-2", "done", ["M-1"], "synthetic"),
            ]
        ]
        milestones = [{
            "id": "M", "title": "Milestone", "status": "partial", "dependencies": [],
            "legal_qualified": False, "task_ids": ["M-1", "M-2"],
            "remaining_gate": "Representative target evaluation.",
        }]
        self.catalog = {
            "schema": "lawyer-assistant-roadmap-sanity-v1",
            "reviewed_source": COMMIT, "source_pins": PINS,
            "items": items, "milestones": milestones,
            "engineering_completion_dependencies": {"M-2": {"M-1": "Synthetic feature can be exercised first."}},
        }
        self.paths = {"docs/ROADMAP.md", "backend/app/example.py", "backend/tests/test_example.py"}

        reserves = [
            {"kind": "job", "name": "unit", "cap": 180, "seconds": 135, "margin": 45, "required_margin": 30},
            {"kind": "step", "name": "setup", "cap": 120, "seconds": 89, "margin": 31, "required_margin": 30},
            {"kind": "step", "name": "short", "cap": 60, "seconds": 45, "margin": 15, "required_margin": 15},
        ]
        self.catalog["ci_reserve_profile"] = copy.deepcopy(reserves)
        run = {"state": "completed", "conclusion": "success",
               "successful_jobs": 1, "observed_jobs": 1, "total_jobs": 1}
        self.snapshot = {
            "schema": "lawyer-assistant-roadmap-snapshot-v1",
            "source_commit": COMMIT, "source_clean": True, "source_pins": PINS.copy(),
            "items": copy.deepcopy(items), "milestones": copy.deepcopy(milestones),
            "progress": {"after": distribution(items), "current_merge_verified": True, "current_source": COMMIT},
            "backlog": project(items), "readiness": readiness(milestones),
            "delivery": {
                "progress": {"after": {"done": 1, "open": 0, "blocked_waiting": 0}, "verified": True,
                             "current_source": COMMIT},
                "records": [{"id": "ENG-PR-1", "status": "done", "number": 1, "merge_commit": COMMIT,
                             "referenced_items": ["M-1"]}],
            },
            "receipt": {
                "source_commit": COMMIT, "remote_main": COMMIT, "pr": {"number": 1, "merge_commit": COMMIT},
                "pr_ci": {**run, "id": 11}, "main_ci": {**run, "id": 22},
                "PR_CI_reserves": reserves, "main_CI_reserves": copy.deepcopy(reserves),
            },
            "next_engineering_item_id": "M-1",
        }

    def test_accepts_scoped_work_and_preserves_independent_readiness(self):
        validate_catalog(self.catalog, self.paths)
        result = audit_snapshot(self.catalog, self.snapshot)
        self.assertEqual(result["checklist"]["counts"]["done"], 1)
        self.assertEqual(result["milestones"]["counts"]["ready"], 0)
        self.assertEqual(result["ci"]["main"]["minimum_step_reserve_at_30_second_floor"], 31)
        self.assertIn("Engineering focus M-1 has 1 linked completed PRs and remains unfinished", result["warnings"])

    def test_rejects_omitted_milestone_children(self):
        self.catalog["milestones"][0]["task_ids"].pop()
        with self.assertRaisesRegex(ValueError, "Checklist coverage"):
            validate_catalog(self.catalog, self.paths)

    def test_rejects_ready_milestone_with_open_items(self):
        self.catalog["milestones"][0]["status"] = "done"
        with self.assertRaisesRegex(ValueError, "unfinished checklist"):
            validate_catalog(self.catalog, self.paths)

    def test_rejects_unmapped_and_undocumented_delivery(self):
        item = self.catalog["items"][1]
        tests = item["tests"]
        item["tests"] = []
        with self.assertRaisesRegex(ValueError, "scoped code and test evidence"):
            validate_catalog(self.catalog, self.paths)
        item["tests"] = tests
        self.catalog["engineering_completion_dependencies"].clear()
        with self.assertRaisesRegex(ValueError, "scoped explanation"):
            validate_catalog(self.catalog, self.paths)

    def test_rejects_dependency_cycles(self):
        self.catalog["items"][0]["dependencies"] = ["M-2"]
        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            validate_catalog(self.catalog, self.paths)

    def test_rejects_catalog_drift_and_false_rollup(self):
        self.snapshot["items"][0]["status"] = "done"
        with self.assertRaisesRegex(ValueError, "Audit drift"):
            audit_snapshot(self.catalog, self.snapshot)
        self.snapshot["items"][0]["status"] = "waiting"
        self.snapshot["progress"]["after"]["counts"]["done"] = 2
        with self.assertRaisesRegex(ValueError, "checklist count"):
            audit_snapshot(self.catalog, self.snapshot)

    def test_rejects_missing_reserve_even_with_successful_ci(self):
        self.snapshot["receipt"]["main_CI_reserves"].pop()
        with self.assertRaisesRegex(ValueError, "Reserve profile differs"):
            audit_snapshot(self.catalog, self.snapshot)

    def test_rejects_mismatched_pin_and_independent_main_reserve_failure(self):
        self.snapshot["source_pins"]["docs/ROADMAP.md"] = "2" * 64
        with self.assertRaisesRegex(ValueError, "source pins differ"):
            audit_snapshot(self.catalog, self.snapshot)
        self.snapshot["source_pins"] = PINS.copy()
        self.snapshot["receipt"]["main_CI_reserves"][1].update(seconds=91, margin=29)
        with self.assertRaisesRegex(ValueError, "declared floor breached"):
            audit_snapshot(self.catalog, self.snapshot)
