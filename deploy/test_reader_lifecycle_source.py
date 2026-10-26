import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReaderLifecycleSourceContracts(unittest.TestCase):
    def test_native_report_pins_current_runtime_and_qualification_sources(self):
        report = json.loads((ROOT / "deploy/fixtures/reader_lifecycle_first_report.json").read_text())
        pins = report["candidate"]["source"]
        previous = json.loads((ROOT / "deploy/fixtures/staged_reader_first_report.json").read_text())
        required = set(previous["candidate"]["source"]) | {"scripts/reader_lifecycle.py", "scripts/reader_lifecycle_log.py",
                    "scripts/reader_lifecycle_fixture.py", "scripts/reader_lifecycle_native.py", "scripts/reader_lifecycle_worker.py",
                    "scripts/reader_lifecycle_report.py", "deploy/test_reader_lifecycle.py", "deploy/test_reader_lifecycle_report.py",
                    "deploy/test_reader_lifecycle_source.py", "deploy/fixtures/reader_lifecycle_policy.json"}
        self.assertEqual(required, pins.keys())
        for name, digest in pins.items():
            with self.subTest(source=name):
                path = ROOT / name
                self.assertTrue(path.resolve().is_relative_to(ROOT))
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest,
                                 "Changed source requires fresh native qualification")
