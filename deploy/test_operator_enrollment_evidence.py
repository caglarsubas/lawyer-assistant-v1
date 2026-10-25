import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "deploy")]
import build_guarded_controller_stage as builder  # noqa: E402
import operator_enrollment_evidence as operator  # noqa: E402
import operator_enrollment_fixture as fixture  # noqa: E402
import portable_controller_fixture as portable  # noqa: E402
from test_portable_controller import unit_readonly  # noqa: E402


class OperatorEvidenceContracts(unittest.TestCase):
    def setUp(self):
        self.prior_bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.stage = self.root / "stage"
        self.approved = builder.build(self.stage)["manifest_sha256"]
        for name in list(sys.modules):
            if name == "lawyer_provider_stage" or name.startswith("lawyer_provider_stage."):
                del sys.modules[name]
        sys.path.insert(0, str(self.stage))
        self.api = portable.modules()

    def tearDown(self):
        sys.dont_write_bytecode = self.prior_bytecode
        sys.path.remove(str(self.stage))
        for name in list(sys.modules):
            if name == "lawyer_provider_stage" or name.startswith("lawyer_provider_stage."):
                del sys.modules[name]
        self.temp.cleanup()

    def layout(self):
        models, work, anchors = [self.root / n for n in ("models", "work", "anchors")]
        for path in (models, work, anchors):
            path.mkdir(mode=0o700)
        portable.prepare(models, self.stage, self.api)
        for p in (models / "model").rglob("*"):
            if p.is_dir():
                p.chmod(0o700)
        (models / "model").chmod(0o700)
        return models, work, anchors

    def test_frozen_operator_cases_with_explicit_unit_readonly_adapter(self):
        models, work, anchors = self.layout()
        inspect = operator.inspect_stage
        with unit_readonly(self.api), patch.object(operator, "inspect_stage", side_effect=lambda p, h: inspect(p, h, require_readonly=False)):
            for name, expected in fixture.CASES:
                if name == "E36_writable_package":
                    continue  # Native campaign requires actual ST_RDONLY rejection.
                with self.subTest(case=name):
                    row = fixture.run_case(name, self.stage, self.approved, models, work, anchors, self.api)
                    self.assertEqual(row["status"], expected)

    def test_packet_and_observation_writes_are_exclusive_owner_only(self):
        path = self.root / "immutable.json"
        result = operator.retain(path, b"invented")
        self.assertEqual(result["sha256"], operator.sha(b"invented"))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            operator.retain(path, b"replacement")
        self.assertEqual(path.read_bytes(), b"invented")

    def test_bounded_packet_schema_and_no_self_review(self):
        models, work, anchors = self.layout()
        with unit_readonly(self.api):
            f = portable.Fixture("schema", models, work, anchors, self.api)
        expected = fixture.expectations(f, self.approved)
        for lifetime in (0, 901, True):
            with self.assertRaises(ValueError):
                operator.packet(expected, packet_id="1" * 32, now=portable.NOW, lifetime=lifetime)
        expected["enrollment"]["reviewer"] = expected["enrollment"]["provisioned_by"]
        with self.assertRaises(ValueError):
            operator.packet(expected, packet_id="1" * 32, now=portable.NOW)

    def test_unexpected_material_is_rejected_before_its_bytes_are_opened(self):
        trust = self.root / "trust"
        trust.mkdir(mode=0o700)
        operator.retain(trust / "signer-password", b"invented-private-sentinel")
        with patch.object(operator, "read", side_effect=AssertionError("Unexpected private read")) as reader:
            with self.assertRaises(ValueError):
                operator.public_snapshot(trust)
            reader.assert_not_called()

    def test_missing_confirmation_never_autofills_approval(self):
        models, work, anchors = self.layout()
        inspect = operator.inspect_stage
        with unit_readonly(self.api), patch.object(operator, "inspect_stage", side_effect=lambda p, h: inspect(p, h, require_readonly=False)):
            row = fixture.run_case("E37_new_unapproved_confirmation", self.stage, self.approved, models, work, anchors, self.api)
        self.assertEqual(row["status"], "waiting")
        self.assertEqual(row["comparison"]["changed_fields"], ["confirmation_sha256"])

    def test_fifos_links_and_oversized_files_do_not_become_packets(self):
        fifo = self.root / "fifo"
        os.mkfifo(fifo, 0o600)
        with self.assertRaises(ValueError):
            operator.read(fifo)
        path = self.root / "huge"
        path.write_bytes(b"x" * (operator.MAX_BYTES + 1))
        path.chmod(0o600)
        with self.assertRaises(ValueError):
            operator.read(path)

    def test_cli_only_creates_unsigned_metadata_and_masks_errors(self):
        models, work, anchors = self.layout()
        with unit_readonly(self.api):
            f = portable.Fixture("cli", models, work, anchors, self.api)
        input_path, output_path = self.root / "input.json", self.root / "packet.json"
        operator.retain(input_path, operator.encode(fixture.expectations(f, self.approved)))
        command = [sys.executable, str(ROOT / "scripts/operator_enrollment_evidence.py"), str(input_path), str(output_path), "--packet-id", "2" * 32]
        result = subprocess.run(command, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(json.loads(result.stdout)["trust_enrolled"])
        result = subprocess.run(command, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(str(output_path).encode(), result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)

    def test_existing_package_bytes_and_frozen_policy_remain_exact(self):
        previous = json.loads((ROOT / "deploy/fixtures/portable_controller_first_report.json").read_text())
        self.assertEqual(self.approved, previous["package_manifest_sha256"])
        self.assertEqual(json.loads((ROOT / "deploy/fixtures/operator_enrollment_policy.json").read_text()), fixture.POLICY)
        self.assertEqual(self.api.artifact_store.Budget().seconds, 20)


if __name__ == "__main__":
    unittest.main()
