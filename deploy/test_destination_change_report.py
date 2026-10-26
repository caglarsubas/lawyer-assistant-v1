import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from destination_change_report import grade  # noqa: E402


class DestinationChangeReportContracts(unittest.TestCase):
    def report(self):
        return json.loads((ROOT / "deploy/fixtures/destination_change_first_report.json").read_text())

    def test_frozen_native_report_passes(self):
        self.assertEqual(grade(self.report())["cases_passed"], 20)

    def test_missing_duplicate_or_changed_case_outcome_is_rejected(self):
        for kind in ("missing", "duplicate", "outcome"):
            value = self.report()
            if kind == "missing":
                value["cases"].pop()
            elif kind == "duplicate":
                value["cases"][1] = copy.deepcopy(value["cases"][0])
            else:
                value["cases"][0]["status"] = 409
            with self.assertRaises(ValueError):
                grade(value)

    def test_activation_real_accounts_and_missing_fence_are_rejected(self):
        for key in ("real_accounts_or_sessions_used", "production_activation", "real_trust_enrolled"):
            value = self.report()
            value[key] = True
            with self.assertRaises(ValueError):
                grade(value)
        value = self.report()
        value["cases"][0]["no_inventory_during_change"] = False
        with self.assertRaises(ValueError):
            grade(value)

    def test_request_process_or_budget_changes_are_rejected(self):
        for key in ("actual_HTTP_requests", "actual_loopback_servers"):
            value = self.report()
            value[key] += 1
            with self.assertRaises(ValueError):
                grade(value)
        value = self.report()
        value["profile"]["cpu"] = 4
        with self.assertRaises(ValueError):
            grade(value)
