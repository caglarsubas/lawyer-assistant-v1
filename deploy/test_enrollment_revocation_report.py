import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from enrollment_revocation_report import REQUESTS, grade  # noqa: E402


class EnrollmentWithdrawalReportContracts(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((ROOT / "deploy/fixtures/enrollment_revocation_first_report.json").read_text())

    def test_frozen_actual_process_campaign(self):
        self.assertEqual(grade(self.report)["actual_HTTP_requests"], sum(REQUESTS))

    def test_collapsed_process_or_omitted_control_event_is_refused(self):
        for field, value in (("distinct_worker_processes", 1), ("withdrawal_events", 0), ("HTTP_requests", 0)):
            report = copy.deepcopy(self.report)
            report["cases"][4][field] = value
            with self.assertRaises(ValueError):
                grade(report)

    def test_unbound_custody_or_rewritten_originals_are_refused(self):
        for field in ("no_system_evidence_or_key_mutation", "lineage_withdrawal_is_not_key_destruction", "no_replay_or_automatic_reactivation", "bounded_metadata_only_inventory"):
            report = copy.deepcopy(self.report)
            report["cases"][0][field] = False
            with self.assertRaises(ValueError):
                grade(report)

    def test_live_activation_or_real_accounts_are_refused(self):
        for field in ("production_activation", "real_accounts_or_sessions_used", "runtime_installation", "real_trust_enrolled"):
            report = copy.deepcopy(self.report)
            report[field] = True
            with self.assertRaises(ValueError):
                grade(report)


if __name__ == "__main__":
    unittest.main()
