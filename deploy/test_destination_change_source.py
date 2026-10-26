import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DestinationChangeSourceContracts(unittest.TestCase):
    def test_native_report_pins_current_runtime_and_qualification_sources(self):
        report = json.loads((ROOT / "deploy/fixtures/destination_change_first_report.json").read_text())
        pins = report["candidate"]["source"]
        previous = json.loads((ROOT / "deploy/fixtures/reader_namespace_first_report.json").read_text())
        required = set(previous["candidate"]["source"]) | {"scripts/destination_change.py", "scripts/destination_change_log.py",
                    "scripts/destination_change_fixture.py", "scripts/destination_change_native.py", "scripts/destination_change_worker.py",
                    "scripts/destination_change_report.py", "deploy/test_destination_change.py", "deploy/test_destination_change_report.py",
                    "deploy/test_destination_change_source.py", "deploy/fixtures/destination_change_policy.json"}
        self.assertEqual(required, pins.keys())
        for name, digest in pins.items():
            with self.subTest(source=name):
                path = ROOT / name
                self.assertTrue(path.resolve().is_relative_to(ROOT))
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest,
                                 "Changed source requires fresh native qualification")
