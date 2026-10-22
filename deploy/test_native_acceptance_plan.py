"""Frozen plan, denominator, exact-version and non-execution contracts."""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from native_acceptance_cases import CASES, SUITE_SHA256  # noqa: E402
from native_acceptance_grading import grade_selection, preflight  # noqa: E402
from native_acceptance_plan import build_plan, validate_plan  # noqa: E402

from app.evidence_prompt import canonical  # noqa: E402
from app.provider import Provider  # noqa: E402


class NativeAcceptancePlanContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads((ROOT / "qualification/frozen-native-acceptance-plan-v1.json").read_text())

    def row(self, key):
        return next(c for c in self.plan["cases"] if c["id"] == key)

    def test_frozen_declaration_exactly_rebuilds_with_code_and_dependency_pins(self):
        validate_plan(self.plan)
        self.assertEqual(canonical(self.plan), canonical(build_plan()))
        self.assertEqual(SUITE_SHA256, "b2e28d8c895af7b9524479bb1f8b56e3818898fe0412618ca33c7c1eed6f5854")
        self.assertEqual(self.plan["plan_sha256"], "455dbba16a3a22482a1c083a4ce7ec60be64a98e2ff2605b77496cb3cd6a01c9")
        self.assertIn("backend/uv.lock", self.plan["code_sha256"])

    def test_preflight_retains_every_missing_group_and_non_model_scope(self):
        report = preflight(self.plan)
        self.assertEqual(report["summary"], {"cases": 14, "required_groups": 20, "available_groups": 14,
            "unavailable_groups": 6, "source_passages": 113, "source_versions": 41,
            "dispositions": {"blocked_before_transport": 1, "native_candidate": 11, "no_candidates_no_call": 2},
            "explicit_empty_cases": 2,
            "candidate_upper_bound_failing_cases": ["P1406", "P1408", "P1409", "P1411", "P1412", "P1414"]})
        self.assertFalse(report["native_qualification"])
        self.assertEqual(report["counts"], {"native_calls": 0, "http_calls": 0, "private_documents": 0, "review_decisions": 0})

    def test_exact_schedule_has_no_excluded_or_replacement_cases(self):
        s = self.plan["schedule"]
        native = s["serial_smoke"] + [key for wave in s["concurrent_waves"] for key in wave]
        self.assertEqual(len(native), len(set(native)))
        self.assertEqual(set(native), {r["id"] for r in self.plan["cases"] if r["disposition"] == "native_candidate"})
        self.assertEqual(set(native + s["preflight_controls"]), {c["id"] for c in CASES})
        self.assertEqual([len(w) for w in s["concurrent_waves"]], [5, 5])
        self.assertEqual(s["attempts_per_case"], 1)
        self.assertEqual(s["completion_requests_upper_bound"], 11)
        self.assertEqual(s["total_metadata_requests_upper_bound"], 35)

    def test_expected_groups_stay_outside_exact_wire_payload(self):
        for row in self.plan["cases"]:
            payload = json.loads(row["messages"][1]["content"])
            self.assertEqual(set(payload), {"question", "bundles"})
            self.assertNotIn("groups", canonical(payload))
            self.assertNotIn("criteria_sha256", canonical(payload))
            self.assertEqual(row["wire"]["bundle_ids"], [b["id"] for b in payload["bundles"]])
            self.assertTrue(row["wire"]["not_execution_authorization"])

    def test_partial_conditions_and_unavailable_sources_cannot_earn_full_group_credit(self):
        for key in ["P1408", "P1409", "P1411"]:
            result = grade_selection(self.plan, key, self.row(key)["wire"]["bundle_ids"])
            self.assertFalse(result["selection_quality_rule_pass"])
            self.assertTrue(any(not g["selected"] for g in result["groups"]))

    def test_wrong_revision_or_omitted_adverse_source_is_a_quality_failure(self):
        row = self.row("P1402")
        all_ids = row["wire"]["bundle_ids"]
        self.assertTrue(grade_selection(self.plan, "P1402", all_ids)["selection_quality_rule_pass"])
        support_only = [b["id"] for b in row["planner"]["bundles"] if b["source_version"] == "S1"]
        result = grade_selection(self.plan, "P1402", support_only)
        self.assertTrue(next(g["selected"] for g in result["groups"] if g["side"] == "support"))
        self.assertFalse(next(g["selected"] for g in result["groups"] if g["side"] == "adverse"))
        self.assertFalse(result["selection_quality_rule_pass"])

    def test_empty_rules_do_not_promote_schema_valid_irrelevant_fallback(self):
        self.assertTrue(grade_selection(self.plan, "P1406", [])["selection_quality_rule_pass"])
        self.assertFalse(grade_selection(self.plan, "P1406", self.row("P1406")["wire"]["bundle_ids"])["selection_quality_rule_pass"])
        self.assertFalse(grade_selection(self.plan, "P1401", [])["selection_quality_rule_pass"])
        self.assertTrue(grade_selection(self.plan, "P1413", [])["selection_quality_rule_pass"])
        self.assertFalse(grade_selection(self.plan, "P1414", [])["selection_quality_rule_pass"])
        self.assertFalse(grade_selection(self.plan, "P1412", [])["selection_quality_rule_pass"])

    def test_unknown_legacy_duplicate_or_forged_selections_fail_closed(self):
        for ids in [["B1"], ["D999"], ["D1", "D1"], [True], "D1", None]:
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                grade_selection(self.plan, "P1401", ids)
        with self.assertRaises(ValueError):
            grade_selection(self.plan, "P1412", ["D1"])
        with self.assertRaises(ValueError):
            grade_selection(self.plan, "missing", [])

    def test_source_wire_criteria_budget_authorization_and_schedule_tampering_rejected(self):
        changes = [lambda p: p["cases"][0]["originals"][0].update(text="changed"),
                   lambda p: p["cases"][0]["wire"].update(wire_sha256="0" * 64),
                   lambda p: p["cases"][0].update(criteria_sha256="0" * 64),
                   lambda p: p["provider_contract"].update(context_limit_units=9000),
                   lambda p: p.update(execution_authorized=True),
                   lambda p: p["schedule"].update(attempts_per_case=2),
                   lambda p: p["cases"].pop()]
        for change in changes:
            altered = copy.deepcopy(self.plan)
            change(altered)
            with self.assertRaises(ValueError):
                grade_selection(altered, "P1401", ["D1"])

    def test_source_code_drift_invalidates_even_unchanged_fixture_data(self):
        original = Path.read_bytes

        def drift(path):
            data = original(path)
            return data + b"\n# drift" if path == ROOT / "backend/app/provider.py" else data

        with patch.object(Path, "read_bytes", drift), self.assertRaises(ValueError):
            validate_plan(self.plan)

    def test_no_network_settings_credentials_or_provider_execution_and_no_native_certification(self):
        before = canonical(self.plan)
        with patch.dict(os.environ, {}, clear=True), patch.object(Provider, "_complete", side_effect=AssertionError("no calls")), \
                patch("socket.create_connection", side_effect=AssertionError("no network")):
            report = preflight(self.plan)
            perfect = grade_selection(self.plan, "P1401", ["D1"])
        self.assertTrue(perfect["selection_quality_rule_pass"])
        self.assertFalse(perfect["native_execution_verified"])
        self.assertFalse(report["native_execution_verified"])
        self.assertFalse(self.plan["execution_authorized"])
        self.assertIsNone(self.plan["provider_contract"]["expected_native_model_digest"])
        self.assertEqual(canonical(self.plan), before)

    def test_cli_prepares_only_and_cannot_overwrite_a_frozen_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "plan.json"
            command = [sys.executable, str(ROOT / "scripts/native_acceptance_plan.py"), "--output", str(output)]
            env = {**os.environ, "PYTHONPATH": str(ROOT / "backend") + os.pathsep + str(ROOT / "scripts")}
            first = subprocess.run(command, env=env, capture_output=True, timeout=15)
            self.assertEqual(first.returncode, 0)
            self.assertEqual(json.loads(output.read_text()), self.plan)
            frozen = output.read_bytes()
            second = subprocess.run(command, env=env, capture_output=True, timeout=15)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(output.read_bytes(), frozen)


if __name__ == "__main__":
    unittest.main()
