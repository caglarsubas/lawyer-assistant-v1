import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from history_backup_report import REQUESTS, grade  # noqa: E402


class HistoryReportContracts(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((ROOT / "deploy/fixtures/history_backup_first_report.json").read_text())

    def test_retained_frozen_multi_process_campaign(self):
        self.assertEqual(grade(self.report)["actual_HTTP_requests"], sum(REQUESTS))

    def test_collapsed_process_boundary_and_skipped_request_are_refused(self):
        for field, value in (("distinct_worker_processes", 1), ("HTTP_requests", 0)):
            report = copy.deepcopy(self.report)
            report["cases"][0][field] = value
            with self.assertRaises(ValueError):
                grade(report)

    def test_original_rewrite_or_unencrypted_backup_claim_is_refused(self):
        self.report["cases"][0]["original_history_preserved"] = False
        with self.assertRaises(ValueError):
            grade(self.report)
        report = copy.deepcopy(self.report)
        report["cases"][0]["encrypted_bundles"] = 0
        with self.assertRaises(ValueError):
            grade(report)

    def test_production_or_real_account_claim_is_refused(self):
        for field in ("production_activation", "real_accounts_or_sessions_used", "runtime_installation", "real_trust_enrolled"):
            report = copy.deepcopy(self.report)
            report[field] = True
            with self.assertRaises(ValueError):
                grade(report)


if __name__ == "__main__":
    unittest.main()
