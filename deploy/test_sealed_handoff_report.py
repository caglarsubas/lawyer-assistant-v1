"""Retained disposable evidence replay; no model I/O, admission or live keys."""

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import sealed_handoff_report as report  # noqa: E402


class RetainedContracts(unittest.TestCase):
    def setUp(self):
        self.first = json.loads((ROOT / "deploy/fixtures/sealed_handoff_first_report.json").read_text())

    def rejected(self, mutate):
        changed = copy.deepcopy(self.first)
        mutate(changed)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            report.grade(changed)

    def test_actual_frozen_native_report_and_public_signatures(self):
        result = report.grade(self.first)
        self.assertEqual(result["native_cases"], 35)
        self.assertEqual(result["signature_report_replays"], 3)
        self.assertFalse(result["native_execution_authorized"])
        self.assertLess(result["import_seal_seconds"], 20)
        self.assertLess(result["restore_seal_seconds"], 20)

    def test_missing_or_duplicate_cases_cannot_pass(self):
        self.rejected(lambda r: r["cases"].pop())
        self.rejected(lambda r: r["cases"].__setitem__(1, r["cases"][0]))

    def test_mutated_expectations_or_success_states_cannot_pass(self):
        self.rejected(lambda r: r["cases"][1].update(expected="verified", observed="verified"))
        self.rejected(lambda r: r["cases"][0].update(observed="sealed"))

    def test_restore_generation_parent_or_binding_reuse_rejects(self):
        for name in ("generation_id", "volume_binding_sha256", "operation_id"):
            self.rejected(lambda r: r["restore_seal"]["record"].__setitem__(name, r["import_seal"]["record"][name]))
        self.rejected(lambda r: r["restore_seal"]["record"].update(parent_operation=None))

    def test_shortened_hashing_or_over_budget_proof_rejects(self):
        self.rejected(lambda r: r["restore_seal"]["proof"].update(mapped_bytes=4096))
        self.rejected(lambda r: r["import_seal"]["proof"].update(elapsed_seconds=20))
        self.rejected(lambda r: r["import_seal"]["proof"].update(kernel_readonly=False))

    def test_exact_retained_wire_and_signature_reject_tampering(self):
        self.rejected(lambda r: r["retained_frames"][0].update(wire_sha256="0" * 64))
        self.rejected(lambda r: r["retained_frames"][2]["context"].update(store_public_key_base64=r["retained_frames"][0]["context"]["store_public_key_base64"]))

    def test_replay_cannot_promote_metadata_to_native_or_production(self):
        self.rejected(lambda r: r.update(production_activation=True))
        self.rejected(lambda r: r["restore_seal"].update(native_execution_authorized=True))
        self.rejected(lambda r: r.update(provider_requests=1))
        self.rejected(lambda r: r.update(real_issuers_or_credentials=True))

    def test_fixture_and_policy_are_not_replaced_by_a_used_profile(self):
        self.rejected(lambda r: r["preparation"].update(fresh_seed=20261028))
        self.rejected(lambda r: r["preparation"].update(tensor_count=1))
        self.rejected(lambda r: r["profile"].update(memory_mib=1024))
        self.rejected(lambda r: r.update(policy_sha256="0" * 64))

    def test_control_recovery_and_original_preservation_are_required(self):
        self.rejected(lambda r: r.update(control_recovery_readonly=False))
        self.rejected(lambda r: r.update(separate_live_control_volume=False))
        self.rejected(lambda r: r.update(original_nonempty_target_preserved=False))


if __name__ == "__main__":
    unittest.main()
