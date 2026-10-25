import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from withdrawal_backup_report import grade  # noqa: E402


class WithdrawalBackupReportContracts(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((ROOT / "deploy/fixtures/withdrawal_backup_first_report.json").read_text())

    def test_frozen_native_archive_campaign(self):
        self.assertEqual(grade(self.report)["actual_HTTP_requests"], 448)

    def test_missing_history_or_independent_controls_is_refused(self):
        for field, value in (("withdrawal_events", 0), ("independent_withdrawal_controls_external", False), ("actual_loopback_servers", 1)):
            changed = copy.deepcopy(self.report)
            changed["cases"][1][field] = value
            with self.assertRaises(ValueError):
                grade(changed)

    def test_mutation_or_activation_claim_is_refused(self):
        for field, value in (("comparison_read_only", False), ("original_history_preserved", False), ("restore_grants_or_activation_created", True)):
            changed = copy.deepcopy(self.report)
            changed["cases"][0][field] = value
            with self.assertRaises(ValueError):
                grade(changed)

    def test_real_account_and_provider_execution_is_refused(self):
        for field, value in (("real_accounts_or_sessions_used", True), ("native_inference_calls", 1), ("production_activation", True)):
            changed = copy.deepcopy(self.report)
            changed[field] = value
            with self.assertRaises(ValueError):
                grade(changed)
