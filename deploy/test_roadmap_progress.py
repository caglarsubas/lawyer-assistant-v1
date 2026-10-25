import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from roadmap_progress import compare, distribution, project  # noqa: E402


class RoadmapProgressContracts(unittest.TestCase):
    def test_partition_and_explicit_deferred_denominator(self):
        items = [{"id": str(n), "status": s} for n, s in enumerate(("done", "in_progress", "planned", "waiting", "deferred"))]
        self.assertEqual(distribution(items), {"total": 5, "counts": {"done": 1, "open": 2, "blocked_waiting": 1, "deferred": 1}})

    def test_net_zero_keeps_individual_transitions(self):
        before = [{"id": "a", "status": "done"}, {"id": "b", "status": "waiting"}]
        after = [{"id": "a", "status": "waiting"}, {"id": "b", "status": "done"}]
        result = compare(before, after)
        self.assertFalse(any(result["delta"].values()))
        self.assertEqual(len(result["changed"]), 2)

    def test_scope_changes_and_unknown_status_are_visible(self):
        result = compare([{"id": "a", "status": "done"}], [{"id": "b", "status": "planned"}])
        self.assertEqual((result["added"], result["removed"]), (["b"], ["a"]))
        for items in ([{"id": "a", "status": "approved"}], [{"id": "a", "status": "done"}] * 2):
            with self.assertRaises(ValueError):
                distribution(items)

    def test_pending_heads_and_repeated_refresh_keep_verified_baseline(self):
        items = [{"id": "a", "status": "planned"}]
        def receipt(source, number):
            return {"source_commit": source, "pr": {"number": number, "merge_commit": source}, "pr_ci": {"conclusion": "success"}}
        _, history = project([], items, "base", receipt("base", 1))
        changed = [{"id": "a", "status": "done"}]
        for pending in ("head1", "head2"):
            result, history = project(history, changed, pending, {"stale": True})
            self.assertEqual((result["baseline_pr"], len(history), result["delta"]["done"]), (1, 1, 1))
        result, history = project(history, changed, "merged", receipt("merged", 2))
        again, same = project(history, changed, "merged", receipt("merged", 2))
        self.assertEqual((again, same), (result, history))
        self.assertEqual(result["baseline_pr"], 1)

    def test_same_source_rewrite_and_history_rewind_are_refused(self):
        original = [{"id": "a", "status": "planned"}]
        history = [{"source_commit": "one", "pr": 1, "items": original}, {"source_commit": "two", "pr": 2, "items": original}]
        with self.assertRaises(ValueError):
            project(history, [{"id": "a", "status": "done"}], "two", None)
        with self.assertRaises(ValueError):
            project(history, original, "one", {"source_commit": "one", "pr": {"number": 1, "merge_commit": "one"}, "pr_ci": {"conclusion": "success"}})
