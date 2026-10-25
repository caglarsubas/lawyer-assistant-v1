import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from operator_enrollment_report import grade  # noqa: E402


class OperatorReportContracts(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((ROOT / "deploy/fixtures/operator_enrollment_first_report.json").read_text())

    def test_retained_first_native_reconciliation_campaign(self):
        self.assertEqual(grade(self.report)["cases_passed"], 39)

    def test_missing_case_and_state_mutation_are_rejected(self):
        report = copy.deepcopy(self.report)
        report["cases"].pop()
        with self.assertRaises(ValueError):
            grade(report)
        self.report["cases"][1]["state_unchanged"] = False
        with self.assertRaises(ValueError):
            grade(self.report)

    def test_observed_confirmation_never_counts_as_approval(self):
        self.report["cases"][36]["status"] = "reconciled_for_disposable_mock_validation"
        with self.assertRaises(ValueError):
            grade(self.report)

    def test_no_authority_or_false_native_qualification(self):
        for key in ("trust_enrolled", "production_activation", "application_or_engine_imports"):
            report = copy.deepcopy(self.report)
            report[key] = True
            with self.assertRaises(ValueError):
                grade(report)


if __name__ == "__main__":
    unittest.main()
