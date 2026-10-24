import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import control_journal_report as report  # noqa: E402


class RetainedControlContracts(unittest.TestCase):
    def setUp(self):
        self.first = json.loads((ROOT / "deploy/fixtures/control_journal_first_report.json").read_text())

    def rejected(self, change):
        value = copy.deepcopy(self.first)
        change(value)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            report.grade(value)

    def test_actual_first_native_metadata_receipt(self):
        self.assertEqual(report.grade(self.first)["native_cases"], 32)
        self.assertFalse(report.grade(self.first)["production_activation"])

    def test_every_frozen_source_and_controller_is_retained_exactly(self):
        for name, expected in self.first["candidate"]["source"].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)

    def test_missing_duplicate_or_rewritten_case_expectations_reject(self):
        self.rejected(lambda r: r["cases"].pop())
        self.rejected(lambda r: r["cases"].__setitem__(1, r["cases"][0]))
        self.rejected(lambda r: r["cases"][0].update(expected="rejected", observed="rejected"))

    def test_partial_cascade_or_nonce_reset_cannot_pass(self):
        row = next(i for i, r in enumerate(self.first["cases"]) if r["id"] == "C03_atomic_descendant_revocation")
        self.rejected(lambda r: r["cases"][row]["evidence"].update(operation_states={"revoked": 1, "sealed": 4}))
        row = next(i for i, r in enumerate(self.first["cases"]) if r["id"] == "C14_exact_backup_nonce")
        self.rejected(lambda r: r["cases"][row]["evidence"].update(restored_nonce_states={}))

    def test_backup_with_anchor_or_stale_fence_rejects(self):
        name = "C15_stale_backup"
        self.rejected(lambda r: r["backup_packet"][name]["latest"].update(anchor_in_backup=True))
        self.rejected(lambda r: r["backup_packet"][name].update(older=r["backup_packet"][name]["latest"]))

    def test_weakened_profile_or_promoted_native_claim_rejects(self):
        self.rejected(lambda r: r["profile"].update(memory_mib=1024))
        self.rejected(lambda r: r.update(production_activation=True))
        self.rejected(lambda r: r.update(model_performance_retested=True))
        self.rejected(lambda r: r.update(real_keys_or_trust=True))

    def test_replaced_policy_or_writable_fixture_proof_rejects(self):
        self.rejected(lambda r: r.update(policy_sha256="0" * 64))
        self.rejected(lambda r: r["fixture_proofs"][0].update(kernel_readonly=False))


if __name__ == "__main__":
    unittest.main()
