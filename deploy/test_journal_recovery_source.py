import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class JournalRecoverySourceContracts(unittest.TestCase):
    def test_native_report_pins_current_runtime_and_qualification_sources(self):
        report = json.loads((ROOT / "deploy/fixtures/journal_recovery_first_report.json").read_text())
        pins = report["candidate"]["source"]
        previous = json.loads((ROOT / "deploy/fixtures/destination_change_first_report.json").read_text())
        required = set(previous["candidate"]["source"]) | {"scripts/journal_recovery.py",
                    "scripts/journal_recovery_fixture.py", "scripts/journal_recovery_native.py", "scripts/journal_recovery_worker.py",
                    "scripts/journal_recovery_report.py", "deploy/test_journal_recovery.py", "deploy/test_journal_recovery_report.py",
                    "deploy/test_journal_recovery_source.py", "deploy/fixtures/journal_recovery_policy.json"}
        self.assertEqual(required, pins.keys())
        for name, digest in pins.items():
            with self.subTest(source=name):
                path = ROOT / name
                self.assertTrue(path.resolve().is_relative_to(ROOT))
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest,
                                 "Changed source requires fresh native qualification")
