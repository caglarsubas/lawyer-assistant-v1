import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from portable_controller_report import grade  # noqa: E402


class PortableReportContracts(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((ROOT / "deploy/fixtures/portable_controller_first_report.json").read_text())

    def test_retained_first_native_campaign_and_original_consumer(self):
        self.assertEqual(grade(self.report)["cases_passed"], 29)

    def test_missing_negative_case_or_illicit_authority_is_rejected(self):
        for field, value in (("production_activation", True), ("native_inference_calls", 1), ("actual_HTTP_requests", 4)):
            report = copy.deepcopy(self.report)
            report[field] = value
            with self.assertRaises(ValueError):
                grade(report)
        self.report["cases"].pop()
        with self.assertRaises(ValueError):
            grade(self.report)

    def test_signature_tampering_and_readiness_mutation_are_rejected(self):
        self.report["cases"][26]["frame"]["request_base64"] = "eA=="
        with self.assertRaises(ValueError):
            grade(self.report)
        report = json.loads((ROOT / "deploy/fixtures/portable_controller_first_report.json").read_text())
        report["cases"][10]["read_only_state_exact"] = False
        with self.assertRaises(ValueError):
            grade(report)


if __name__ == "__main__":
    unittest.main()
