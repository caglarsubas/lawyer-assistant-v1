import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StagedReaderSourceContracts(unittest.TestCase):
    def test_native_report_pins_current_runtime_and_qualification_sources(self):
        report = json.loads((ROOT / "deploy/fixtures/staged_reader_first_report.json").read_text())
        pins = report["candidate"]["source"]
        required = {"scripts/staged_reader.py", "scripts/staged_reader_log.py", "scripts/staged_reader_fixture.py",
                    "scripts/staged_reader_native.py", "scripts/staged_reader_worker.py", "scripts/staged_reader_report.py",
                    "scripts/operator_review_auth.py", "scripts/withdrawal_history_backup.py", "scripts/withdrawal_history_service.py",
                    "backend/app/auth.py", "backend/app/db.py", "deploy/test_staged_reader.py",
                    "deploy/test_staged_reader_report.py", "deploy/fixtures/staged_reader_policy.json"}
        self.assertTrue(required <= pins.keys())
        for name, digest in pins.items():
            with self.subTest(source=name):
                path = ROOT / name
                self.assertTrue(path.resolve().is_relative_to(ROOT))
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest,
                                 "Changed source requires fresh native qualification")
