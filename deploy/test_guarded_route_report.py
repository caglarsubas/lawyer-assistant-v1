import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import guarded_route_report as report  # noqa: E402


class RetainedGuardContracts(unittest.TestCase):
    def setUp(self):
        self.first = json.loads((ROOT / "deploy/fixtures/guarded_route_first_report.json").read_text())

    def rejected(self, mutate):
        altered = copy.deepcopy(self.first)
        mutate(altered)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            report.grade(altered)

    def test_actual_first_native_HTTP_and_exact_signature_evidence(self):
        result = report.grade(self.first)
        self.assertEqual(result["native_cases"], 29)
        self.assertEqual(result["verified_signed_frames"], 2)
        self.assertFalse(result["native_inference_qualified"])

    def test_native_frozen_dependencies_stay_exact(self):
        for name, expected in self.first["candidate"]["source"].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)

    def test_missing_duplicate_or_changed_status_cannot_pass(self):
        self.rejected(lambda r: r["cases"].pop())
        self.rejected(lambda r: r["cases"].__setitem__(1, r["cases"][0]))
        self.rejected(lambda r: r["cases"][0].update(status=400))

    def test_signed_wire_or_public_key_substitution_rejects(self):
        self.rejected(lambda r: r["cases"][0]["frame"].update(response_nonce="0" * 32))
        self.rejected(lambda r: r["cases"][0]["frame"].update(public_key_base64=r["cases"][-1]["frame"]["public_key_base64"]))

    def test_nonce_reset_or_partial_revocation_rejects(self):
        row = next(i for i, r in enumerate(self.first["cases"]) if r["id"] == "G22_receipt_rollback")
        self.rejected(lambda r: r["cases"][row].update(nonce_counts={}))
        row = next(i for i, r in enumerate(self.first["cases"]) if r["id"] == "G09_before_release")
        self.rejected(lambda r: r["cases"][row].update(operation_state="sealed"))

    def test_profile_and_runtime_scope_cannot_be_promoted(self):
        self.rejected(lambda r: r["profile"].update(memory_mib=1024))
        self.rejected(lambda r: r.update(native_inference_calls=1))
        self.rejected(lambda r: r.update(runtime_keys_used=True))
        self.rejected(lambda r: r.update(production_activation=True))

    def test_readonly_and_policy_proofs_are_required(self):
        self.rejected(lambda r: r.update(policy_sha256="0" * 64))
        self.rejected(lambda r: r["cases"][0]["fixture_proof"].update(kernel_readonly=False))
        self.rejected(lambda r: r.update(read_only_model_inventory_exact=False))


if __name__ == "__main__":
    unittest.main()
