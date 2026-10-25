import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from operator_review_report import grade  # noqa: E402


class OperatorReviewReportContracts(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((ROOT / "deploy/fixtures/authenticated_operator_first_report.json").read_text())

    def test_retained_first_native_authentication_and_history_cases(self):
        self.assertEqual(grade(self.report)["actual_HTTP_requests"], 92)

    def test_unauthorized_decision_or_overwritten_history_is_rejected(self):
        self.report["cases"][5]["decision_records"] = 1
        with self.assertRaises(ValueError):
            grade(self.report)
        self.report = json.loads((ROOT / "deploy/fixtures/authenticated_operator_first_report.json").read_text())
        self.report["cases"][26]["decision_records"] = 0
        with self.assertRaises(ValueError):
            grade(self.report)

    def test_native_authority_or_live_identity_claims_are_rejected(self):
        for key in ("production_activation", "real_trust_enrolled", "real_accounts_or_sessions_used", "app_main_or_provider_imported"):
            report = copy.deepcopy(self.report)
            report[key] = True
            with self.assertRaises(ValueError):
                grade(report)

    def test_skipped_case_or_fabricated_request_count_is_rejected(self):
        report = copy.deepcopy(self.report)
        report["cases"].pop()
        with self.assertRaises(ValueError):
            grade(report)
        self.report["actual_HTTP_requests"] = 101
        with self.assertRaises(ValueError):
            grade(self.report)


if __name__ == "__main__":
    unittest.main()
