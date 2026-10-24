import copy
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import artifact_store as a  # noqa: E402
import artifact_store_qualification as q  # noqa: E402


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def verify(self, root, pin, budget=a.Budget(), **kwargs):
        # Unit filesystems are writable. The real Linux campaign tests ST_RDONLY.
        with patch.object(a, "readonly", return_value=True):
            return a.verify_core(root, pin, budget, time.monotonic() + budget.seconds, **kwargs)

    def test_valid_hashes_all_three_artifacts_without_changing_bytes(self):
        info = q.snapshot(self.root / "valid")
        before = {p.name: p.read_bytes() for p in (self.root / "valid/blobs").iterdir()}
        proof = self.verify(self.root / "valid", info["manifest_digest"])
        self.assertEqual(proof["bytes_hashed"], sum(map(len, before.values())))
        self.assertEqual(len(proof["artifacts"]), 3)
        self.assertFalse(proof["executed_weights_qualified"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / "valid/blobs").iterdir()})

    def test_frozen_small_case_matrix(self):
        for name, expected in q.CASES:
            if name in {"valid", "root_link", "writable", "deadline", "cancelled", "byte_budget"}:
                continue
            with self.subTest(case=name):
                info = q.snapshot(self.root / name, name)
                with self.assertRaises(a.StoreRejected) as raised:
                    self.verify(self.root / name, info["manifest_digest"])
                self.assertEqual(raised.exception.code, expected)

    def test_actual_writable_root_rejected_even_with_owner_only_modes(self):
        info = q.snapshot(self.root / "writable")
        with patch.object(a, "readonly", return_value=False), self.assertRaises(a.StoreRejected) as raised:
            a.verify_core(self.root / "writable", info["manifest_digest"], a.Budget(), time.monotonic() + 1)
        self.assertEqual(raised.exception.code, "readonly")

    def test_linked_parent_and_root_rejected(self):
        info = q.snapshot(self.root / "real")
        (self.root / "link").symlink_to("real", target_is_directory=True)
        with self.assertRaises(a.StoreRejected) as raised:
            self.verify(self.root / "link", info["manifest_digest"])
        self.assertEqual(raised.exception.code, "root")

    def test_aggregate_byte_budget_is_enforced_before_layer_read(self):
        info = q.snapshot(self.root / "valid")
        with self.assertRaises(a.StoreRejected) as raised:
            self.verify(self.root / "valid", info["manifest_digest"], a.Budget(1))
        self.assertEqual(raised.exception.code, "byte_budget")

    def test_invalid_budget_types_and_unbounded_values_rejected(self):
        for value in (True, 0, -1, a.MAX_TOTAL + 1, 1.0):
            with self.assertRaises(a.StoreRejected):
                a.Budget(value).validate()
        for value in (True, 0, -1, 61, float("nan"), float("inf"), "20"):
            with self.assertRaises(a.StoreRejected):
                a.Budget(seconds=value).validate()

    def test_deadline_checked_before_open(self):
        with patch.object(a.os, "open", side_effect=AssertionError("Must not open")):
            with self.assertRaises(a.StoreRejected) as raised:
                a.verify_core(self.root, "sha256:" + "1" * 64, a.Budget(), 0)
        self.assertEqual(raised.exception.code, "deadline")

    def test_cancel_before_start_creates_no_process(self):
        with patch.object(a.multiprocessing, "get_context", wraps=a.multiprocessing.get_context) as context:
            with self.assertRaises(a.StoreRejected) as raised:
                a.supervised_verify(self.root, "sha256:" + "1" * 64, cancelled=lambda: True)
            self.assertEqual(context.call_count, 1)
        self.assertEqual(raised.exception.code, "cancelled")
        self.assertFalse(a.multiprocessing.active_children())

    def test_identity_includes_link_mode_size_owner_and_change_times(self):
        p = self.root / "item"
        p.write_bytes(b"invented")
        before = a.identity(p.stat())
        p.chmod(0o600)
        self.assertNotEqual(before, a.identity(p.stat()))
        after = a.identity(p.stat())
        os.link(p, self.root / "link")
        self.assertNotEqual(after, a.identity(p.stat()))

    def test_changed_entry_fails_closed(self):
        info = q.snapshot(self.root / "valid")
        original, calls = a.identity, [0]
        inode = (self.root / "valid/blobs" / info["model_digest"].replace(":", "-")).stat().st_ino

        def changed(value):
            result = original(value)
            if value.st_ino == inode:
                calls[0] += 1
                if calls[0] > 1:
                    result = (*result[:-1], result[-1] + 1)
            return result

        with patch.object(a, "identity", side_effect=changed), self.assertRaises(a.StoreRejected) as raised:
            self.verify(self.root / "valid", info["manifest_digest"])
        self.assertEqual(raised.exception.code, "changed")

    def test_config_remote_rootfs_and_unknown_fields_rejected(self):
        for config in ({"model_format": "gguf", "remote_model": "forbidden"},
                       {"model_format": "gguf", "rootfs": {"type": "layers", "diff_ids": ["wrong"]}},
                       {"model_format": "gguf", "model_families": ["same", "same"]},
                       {"model_format": "gguf", "unknown": "forbidden"}):
            with self.assertRaises(a.StoreRejected):
                a.config_valid(config, [])

    def test_proof_cannot_promote_weights_production_or_partial_artifacts(self):
        info = q.snapshot(self.root / "valid")
        proof = self.verify(self.root / "valid", info["manifest_digest"])
        proof["peak_rss_kib"] = 10000
        a.validate_proof(proof, info["manifest_digest"], a.Budget())
        changes = [("production_activation", True), ("bytes_hashed", 1), ("elapsed_seconds", 61),
                   ("executed_weights_qualified", True), ("content_identity_sha256", "0" * 64),
                   ("artifacts", proof["artifacts"][:-1]), ("peak_rss_kib", 0)]
        for key, value in changes:
            bad = copy.deepcopy(proof)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(a.StoreRejected):
                a.validate_proof(bad, info["manifest_digest"], a.Budget())

    def test_prepare_is_fresh_and_policy_has_one_attempt_no_native_claim(self):
        info = q.prepare(self.root / "fixtures")
        self.assertEqual(len(info), 38)
        self.assertEqual(len({v["id"] for v in q.POLICY["cases"]}), 38)
        self.assertEqual(q.POLICY["attempts"], 1)
        self.assertFalse(q.POLICY["native_inference_qualified"])
        self.assertEqual(q.POLICY["jobs"], 5)
        with self.assertRaises(FileExistsError):
            q.prepare(self.root / "fixtures")
        self.assertEqual(json.loads((self.root / "fixtures/fixtures.json").read_bytes()), info)

    def retained(self):
        fixture = Path(__file__).parent / "fixtures"
        return (json.loads((fixture / "artifact_store_first_cases.json").read_bytes()),
                json.loads((fixture / "artifact_store_first_budgets.json").read_bytes()))

    def test_actual_first_campaign_and_missed_target_are_revalidated(self):
        cases, budgets = self.retained()
        self.assertEqual(q.grade_cases(cases)["passed"], 38)
        pin = budgets["single"]["proofs"][0]["manifest_digest"]
        result = q.grade_budgets(budgets, pin)
        self.assertEqual(result["completed_verifications"], 12)
        self.assertTrue(result["hard_budget_pass"])
        self.assertTrue(result["memory_target_pass"])
        self.assertFalse(result["twenty_second_pre_post_target_pass"])
        self.assertFalse(result["native_inference_qualified"])
        policy = Path(__file__).parent / "fixtures/artifact_store_policy.json"
        self.assertEqual(json.loads(policy.read_bytes()), q.POLICY)

    def test_retained_reports_cannot_promote_rejections_or_missed_targets(self):
        cases, budgets = self.retained()
        cases["cases"][1]["observed"] = "ok"
        with self.assertRaises(ValueError):
            q.grade_cases(cases)
        pin = budgets["single"]["proofs"][0]["manifest_digest"]
        budgets["single"]["within_pre_post_target"] = True
        with self.assertRaises(ValueError):
            q.grade_budgets(budgets, pin)

    def test_blocked_worker_deadline_terminates_kills_and_reaps_without_retry(self):
        context, parent, child, process = Mock(), Mock(), Mock(), Mock()
        context.Pipe.return_value = (parent, child)
        context.Process.return_value = process
        parent.poll.return_value = False
        process.is_alive.return_value = True
        with patch.object(a.multiprocessing, "get_context", return_value=context), \
                patch.object(a.time, "monotonic", side_effect=[0, 0, 2]):
            with self.assertRaises(a.StoreRejected) as raised:
                a.supervised_verify(self.root, "sha256:" + "1" * 64, a.Budget(seconds=1))
        self.assertEqual(raised.exception.code, "deadline")
        process.start.assert_called_once()
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual(process.join.call_count, 2)
        process.close.assert_called_once()

    def test_cancellation_after_worker_reply_discards_proof(self):
        cases, _ = self.retained()
        proof = cases["cases"][0]["proof"]
        context, parent, child, process = Mock(), Mock(), Mock(), Mock()
        context.Pipe.return_value = (parent, child)
        context.Process.return_value = process
        parent.poll.return_value = True
        parent.recv_bytes.return_value = a.canonical({"ok": True, "proof": proof})
        process.is_alive.return_value = False
        process.exitcode = 0
        cancelled = Mock(side_effect=[False, False, True])
        with patch.object(a.multiprocessing, "get_context", return_value=context), \
                patch.object(a.time, "monotonic", return_value=0):
            with self.assertRaises(a.StoreRejected) as raised:
                a.supervised_verify(self.root, proof["manifest_digest"], a.Budget(seconds=5), cancelled=cancelled)
        self.assertEqual(raised.exception.code, "cancelled")
        process.start.assert_called_once()
        process.join.assert_called_once()


if __name__ == "__main__":
    unittest.main()
