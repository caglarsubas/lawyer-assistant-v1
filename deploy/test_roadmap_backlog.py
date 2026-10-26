import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from roadmap_backlog import project  # noqa: E402


class RoadmapBacklogContracts(unittest.TestCase):
    def test_unstarted_and_waiting_work_exists_without_any_open_PR(self):
        rows = [{"id": name, "status": status} for name, status in (("done", "done"), ("active", "in_progress"),
                ("next", "planned"), ("review", "waiting"), ("later", "deferred"))]
        result = project(rows)
        self.assertEqual(result, {"total": 4, "catalog_total": 5, "counts": {"open": 2, "waiting": 1, "deferred": 1},
                                  "ids": ["active", "next", "review", "later"]})

    def test_projection_does_not_modify_parent_status_or_review_history(self):
        rows = [{"id": "review", "status": "waiting", "history": ["pending owner"]}]
        self.assertEqual(project(rows)["ids"], ["review"])
        self.assertEqual(rows, [{"id": "review", "status": "waiting", "history": ["pending owner"]}])

    def test_duplicate_or_unknown_status_cannot_inflate_or_hide_work(self):
        for rows in ([{"id": "x", "status": "planned"}] * 2, [{"id": "x", "status": "unknown"}]):
            with self.assertRaises(ValueError):
                project(rows)

    def test_empty_and_completed_catalogs_have_no_fabricated_backlog(self):
        for rows in ([], [{"id": "x", "status": "done"}]):
            self.assertEqual(project(rows)["total"], 0)
            self.assertEqual(project(rows)["ids"], [])
