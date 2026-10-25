import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from roadmap_delivery import project, readiness, records, snapshot  # noqa: E402

A, B = "a" * 40, "b" * 40


def pr(number, *, merged=True, state=None, labels=(), sha=A):
    return {"number": number, "title": "Delivered change", "html_url": f"https://github.com/caglarsubas/lawyer-assistant-v1/pull/{number}",
            "state": state or ("closed" if merged else "open"), "merged_at": "2026-10-25T12:00:00Z" if merged else None,
            "merge_commit_sha": sha, "labels": list(labels)}


class RoadmapDeliveryContracts(unittest.TestCase):
    def test_only_merged_ancestor_is_completed(self):
        result = records([pr(1), pr(2, merged=False), pr(3, merged=False, state="closed"), pr(4, sha=B)], {A}, [])
        self.assertEqual({row["number"]: row["status"] for row in result}, {1: "done", 2: "in_progress"})

    def test_explicit_blocked_label_is_not_inferred_from_pending(self):
        result = records([pr(1, merged=False, labels=["Blocked"]), pr(2, merged=False, labels=["ci-pending"])], {A}, [])
        self.assertEqual({row["number"]: row["status"] for row in result}, {1: "waiting", 2: "in_progress"})

    def test_duplicate_foreign_or_false_merge_identity_is_rejected(self):
        foreign = pr(1) | {"html_url": "https://example.invalid/pull/1"}
        for values in ([pr(1), pr(1)], [foreign], [pr(1, state="open")], [pr(1, sha="invalid")], [pr(1) | {"merged_at": True}]):
            with self.assertRaises(ValueError):
                records(values, {A}, [])

    def test_references_are_catalog_mentions_not_inferred_approval(self):
        result = records([pr(25), pr(2)], {A}, [{"id": "F00-06", "delivered": "PR #25 is qualified only with disposable identities."}])
        self.assertEqual(result[0]["referenced_items"], ["F00-06"])
        self.assertEqual(result[1]["referenced_items"], [])

    def test_historical_unknown_counts_are_not_zero(self):
        old = snapshot(records([pr(1)], {A}, []), A, pr=1, observed_at="then", historical=True)
        new = snapshot(records([pr(1), pr(2, sha=B)], {A, B}, []), B, pr=2, observed_at="now")
        result, _ = project([old], new, A, verified=True)
        self.assertEqual(result["delta"], {"done": 1, "open": None, "blocked_waiting": None})
        self.assertEqual(result["newly_completed"], ["ENG-PR-2"])

    def test_pending_and_repeated_refresh_preserve_history(self):
        old = snapshot(records([pr(1)], {A}, []), A, pr=1, observed_at="then")
        pending = snapshot(records([pr(1), pr(2, merged=False)], {A}, []), B, observed_at="now")
        result, unchanged = project([old], pending, A, verified=False)
        self.assertEqual((result["delta"]["open"], len(unchanged)), (1, 1))
        new = snapshot(records([pr(1), pr(2, sha=B)], {A, B}, []), B, pr=2, observed_at="later")
        result, history = project([old], new, A, verified=True)
        repeated, same = project(history, new | {"observed_at": "later still"}, A, verified=True)
        self.assertEqual((repeated, same), (result, history))

    def test_verified_rewrite_or_rollback_is_refused(self):
        old = snapshot(records([pr(1)], {A}, []), A, pr=1, observed_at="then")
        new = snapshot(records([pr(1), pr(2, sha=B)], {A, B}, []), B, pr=2, observed_at="now")
        with self.assertRaises(ValueError):
            project([old, new], old, A, verified=True)
        with self.assertRaises(ValueError):
            project([old], old | {"counts": {"done": 100, "open": 0, "blocked_waiting": 0}}, A, verified=True)
        with self.assertRaises(ValueError):
            project([old | {"counts": {"done": 100, "open": 0, "blocked_waiting": 0}}], new, A, verified=False)

    def test_milestone_readiness_has_its_own_denominator(self):
        result = readiness([{"id": "a", "status": "partial"}, {"id": "b", "status": "waiting"}, {"id": "c", "status": "planned"}])
        self.assertEqual(result, {"total": 3, "counts": {"ready": 0, "partial": 1, "waiting": 1, "planned": 1}})
        with self.assertRaises(ValueError):
            readiness([{"id": "a", "status": "merged"}])
