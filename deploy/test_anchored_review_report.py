import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from anchored_review_report import REQUESTS, grade  # noqa: E402


class AnchoredReportContracts(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((ROOT / "deploy/fixtures/anchored_review_first_report.json").read_text())

    def test_retained_first_frozen_native_campaign(self):
        self.assertEqual(grade(self.report)["actual_HTTP_requests"], sum(REQUESTS))

    def test_missing_or_rewritten_history_is_rejected(self):
        for index in (2, 16, 21):
            report = copy.deepcopy(self.report)
            report["cases"][index]["decision_records"] += 1
            with self.assertRaises(ValueError):
                grade(report)

    def test_authority_or_live_identity_claims_are_rejected(self):
        for key in ("production_activation", "real_trust_enrolled", "real_accounts_or_sessions_used", "app_main_or_provider_imported"):
            report = copy.deepcopy(self.report)
            report[key] = True
            with self.assertRaises(ValueError):
                grade(report)

    def test_case_or_request_count_changes_are_rejected(self):
        self.report["cases"][0]["HTTP_requests"] += 1
        with self.assertRaises(ValueError):
            grade(self.report)


if __name__ == "__main__":
    unittest.main()
