"""Fast disposable-index-drill boundaries; no Docker workload runs in CI."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import qualify_search_index as drill  # noqa: E402


class SearchIndexDrillContracts(unittest.TestCase):
    def test_internal_network_named_volumes_and_only_generated_test_credentials(self):
        definition = drill.compose_definition({"test": "sha256:test", "opensearch": "sha256:search", "postgres": "sha256:postgres"}, "generated-test-only")
        self.assertEqual(definition["networks"], {"isolated": {"internal": True}})
        self.assertEqual(set(definition["volumes"]), {"opensearch", "postgres"})
        for service in definition["services"].values():
            for field in ("ports", "env_file", "network_mode", "privileged", "build"):
                self.assertNotIn(field, service)
            self.assertEqual(service["networks"], ["isolated"])
            self.assertEqual(service["pull_policy"], "never")
            self.assertTrue(all(mount.split(":")[0] in definition["volumes"] for mount in service.get("volumes", [])))
        self.assertEqual(definition["services"]["postgres"]["cap_add"],
                         ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID"])
        driver = definition["services"]["driver"]
        self.assertNotIn("cap_add", driver)
        self.assertNotIn("volumes", driver)
        self.assertEqual(driver["environment"], {"LA_SEARCH_INDEX_DRILL": drill.MARKER, "LA_PUBLIC_SOURCE_DIR": "/tmp/public-only",
            "LA_TEST_POSTGRES_URL": "postgresql+psycopg://snapshot_test:generated-test-only@postgres:5432/lawyer_snapshot_test"})
        self.assertTrue(driver["read_only"])

    def test_test_fingerprint_binds_added_changed_and_removed_fixtures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / "backend/tests"
            tests.mkdir(parents=True)
            fixture = tests / "fixture.py"
            fixture.write_text("initial")
            initial = drill.tests_fingerprint(root)
            fixture.write_text("changed")
            self.assertNotEqual(drill.tests_fingerprint(root), initial)
            fixture.write_text("initial")
            extra = tests / "extra.py"
            extra.write_text("extra")
            self.assertNotEqual(drill.tests_fingerprint(root), initial)
            extra.unlink()
            fixture.unlink()
            self.assertNotEqual(drill.tests_fingerprint(root), initial)

    def test_failed_preflight_does_not_claim_or_clean_resources_or_overwrite_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            args = ["qualify_search_index.py", "--test-image", "fixture", "--output", str(output)]
            with (patch("sys.argv", args), patch.object(drill, "command", side_effect=RuntimeError("PRIVATE")),
                  patch.object(drill, "cleanup_project") as cleanup):
                self.assertEqual(drill.main(), 1)
            cleanup.assert_not_called()
            report = json.loads(output.read_bytes())
            self.assertEqual(report["status"], "failed")
            self.assertNotIn("PRIVATE", output.read_text())
            with patch("sys.argv", args), patch.object(drill, "command") as command, self.assertRaises(FileExistsError):
                drill.main()
            command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
