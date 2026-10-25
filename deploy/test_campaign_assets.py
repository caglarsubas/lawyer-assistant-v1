import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from campaign_test_assets import share_immutable_assets


class CampaignAssetContracts(unittest.TestCase):
    def fixture_class(self):
        calls = []
        class Case:
            def setUp(self):
                calls.append("setup")
                self.prior_bytecode = sys.dont_write_bytecode
                self.temp = tempfile.TemporaryDirectory()
                self.root = Path(self.temp.name)
                self.stage, self.models = self.root / "stage", self.root / "models"
                for path in (self.stage, self.models):
                    path.mkdir()
                    (path / "invented").write_bytes(b"immutable fixture")
                self.api, self.approved = SimpleNamespace(), "invented"
            def tearDown(self):
                calls.append("teardown")
                sys.dont_write_bytecode = self.prior_bytecode
                self.temp.cleanup()
        share_immutable_assets(Case)
        return Case, calls

    def test_only_immutable_assets_are_shared_and_case_work_roots_are_fresh(self):
        cls, calls = self.fixture_class()
        cls.setUpClass()
        try:
            a, b = cls(), cls()
            a.setUp()
            b.setUp()
            try:
                self.assertIs(a.api, b.api)
                self.assertEqual(a.models, b.models)
                self.assertNotEqual(a.work, b.work)
                self.assertNotEqual(a.anchors, b.anchors)
                (a.work / "account").write_bytes(b"invented session")
                self.assertFalse((b.work / "account").exists())
                self.assertEqual(calls, ["setup"])
            finally:
                b.tearDown()
                a.tearDown()
        finally:
            cls.tearDownClass()
        self.assertEqual(calls, ["setup", "teardown"])

    def test_shared_asset_change_is_rejected_before_the_next_case(self):
        cls, _ = self.fixture_class()
        cls.setUpClass()
        file = cls._campaign_assets.models / "invented"
        original = file.read_bytes()
        try:
            file.write_bytes(b"changed")
            with self.assertRaises(AssertionError):
                cls().setUp()
        finally:
            file.write_bytes(original)
            cls.tearDownClass()
