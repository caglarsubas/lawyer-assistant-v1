import ast
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_guarded_controller_stage as builder  # noqa: E402
import build_signed_route_stage as previous  # noqa: E402
import controller_stage_manifest as external  # noqa: E402
import portable_controller_fixture as q  # noqa: E402
import portable_controller_native as native  # noqa: E402


@contextmanager
def unit_readonly(m):
    # Explicit unit adapter only. Native qualification requires fstatvfs ST_RDONLY.
    inspect = external.inspect_stage
    def local(stage, approved, **kwargs):
        return inspect(stage, approved, require_readonly=False)
    def verify(root, manifest, budget=m.artifact_store.Budget(), **kwargs):
        result = m.artifact_store.verify_core(root, manifest, budget, time.monotonic() + budget.seconds,
                                               strategy=kwargs.get("strategy", "stream"))
        result["peak_rss_kib"] = 10000
        return result
    with patch.object(external, "inspect_stage", side_effect=local), patch.object(m.readiness, "inspect_stage", side_effect=local), \
            patch.object(m.artifact_store, "readonly", return_value=True), patch.object(m.artifact_store, "supervised_verify", side_effect=verify):
        yield


class PortableControllerContracts(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.prior_bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.stage = self.root / "stage"
        self.built = builder.build(self.stage)
        self.approved = self.built["manifest_sha256"]
        for name in list(sys.modules):
            if name == "lawyer_provider_stage" or name.startswith("lawyer_provider_stage."):
                del sys.modules[name]
        sys.path.insert(0, str(self.stage))
        self.m = q.modules()

    def tearDown(self):
        sys.dont_write_bytecode = self.prior_bytecode
        sys.path.remove(str(self.stage))
        for name in list(sys.modules):
            if name == "lawyer_provider_stage" or name.startswith("lawyer_provider_stage."):
                del sys.modules[name]
        self.temp.cleanup()

    async def test_frozen_package_and_readiness_cases(self):
        models, work, anchors = [self.root / n for n in ("models", "work", "anchors")]
        for p in (models, work, anchors):
            p.mkdir(mode=0o700)
        q.prepare(models, self.stage, self.m)
        for p in (models / "model").rglob("*"):
            if p.is_dir():
                p.chmod(0o700)
        (models / "model").chmod(0o700)
        with unit_readonly(self.m):
            for name, expected in q.CASES:
                if name == "A10_writable":
                    continue  # Actual mount rejection is a mandatory native case.
                with self.subTest(case=name):
                    row = await native.run_case(name, self.stage, self.approved, models, work, anchors, self.m, native=False)
                    self.assertEqual(row["status"], expected)

    async def test_deterministic_closed_public_archive(self):
        second = self.root / "second"
        built = builder.build(second)
        self.assertEqual(built, self.built)
        first_zip, second_zip = self.root / "first.zip", self.root / "second.zip"
        self.assertEqual(builder.archive(self.stage, first_zip, self.approved), builder.archive(second, second_zip, self.approved))
        self.assertEqual(first_zip.read_bytes(), second_zip.read_bytes())
        self.assertEqual(len(self.built["manifest"]["package_sha256"]), 14)
        self.assertFalse(self.built["manifest"]["private_material_included"])
        with self.assertRaises(FileExistsError):
            builder.archive(self.stage, first_zip, self.approved)

    async def test_prior_route_bytes_and_new_import_only_transform(self):
        prior = self.root / "prior"
        previous.build_route(prior)
        for file in (prior / external.PACKAGE).iterdir():
            self.assertEqual(file.read_bytes(), (self.stage / external.PACKAGE / file.name).read_bytes())
        for source, output in builder.SOURCES.items():
            tree = builder.PortableImports().visit(ast.parse((ROOT / "scripts" / (source + ".py")).read_text()))
            target = ast.parse((self.stage / external.PACKAGE / (output + ".py")).read_text())
            self.assertEqual(ast.dump(tree), ast.dump(target))

    async def test_isolated_import_does_not_load_application_or_engine(self):
        driver = ("import sys;sys.path.insert(0," + repr(str(ROOT / "scripts")) + ");"
                  "from controller_stage_manifest import inspect_stage;inspect_stage(" + repr(str(self.stage)) + "," + repr(self.approved) + ",require_readonly=False);"
                  "sys.path.insert(0," + repr(str(self.stage)) + ");from portable_controller_fixture import modules;modules();"
                  "assert not any(n=='app' or n.startswith(('app.','inference_engine')) for n in sys.modules)")
        result = subprocess.run([sys.executable, "-I", "-B", "-c", driver], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, "Standalone import failed")
        self.assertEqual(result.stdout, b"")

    async def test_unapproved_or_writable_package_rejected_before_import(self):
        with self.assertRaises(ValueError):
            external.inspect_stage(self.stage, "0" * 64, require_readonly=False)
        with self.assertRaises(ValueError):
            external.inspect_stage(self.stage, self.approved)

    async def test_sensitive_enrollment_material_is_outside_export(self):
        (self.stage / "signer-password").write_bytes(b"synthetic-only")
        with self.assertRaises(ValueError):
            external.inspect_stage(self.stage, self.approved, require_readonly=False)

    async def test_duplicate_manifest_key_rejected_even_with_approved_hash(self):
        path = self.stage / "guarded-stage-manifest.json"
        raw = path.read_bytes().replace(b'"version": 1,', b'"version": 1, "version": 1,')
        path.write_bytes(raw)
        with self.assertRaises(ValueError):
            external.inspect_stage(self.stage, q.sha(raw), require_readonly=False)

    async def test_build_under_restrictive_umask_and_pinned_limits(self):
        prior = os.umask(0o077)
        try:
            built = builder.build(self.root / "restrictive")
        finally:
            os.umask(prior)
        self.assertEqual(built, self.built)
        self.assertEqual(self.m.artifact_store.Budget().seconds, 20)
        self.assertEqual(json.loads((ROOT / "deploy/fixtures/portable_controller_policy.json").read_text()), q.POLICY)


if __name__ == "__main__":
    unittest.main()
