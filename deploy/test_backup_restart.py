"""Synthetic restart schedules: no real Docker services or private data."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import manage_backup as backup
from restart_test_fixtures import role_metadata


class BackupRestartTests(unittest.TestCase):
    def test_relay_reservation_and_web_api_resolution_survive_reversed_discovery(self):
        roles = {"edge": "web", "application": "api", "database": "postgres", "relay": "provider-relay"}
        discovery = list(roles)
        with patch.object(backup, "run", return_value=role_metadata(roles)) as inspect:
            plan = backup.restart_plan(discovery)
        self.assertIn('com.docker.compose.service', inspect.call_args.args[0][3])
        self.assertNotIn('Env', inspect.call_args.args[0][3])
        self.assertIn('NetworkSettings.Networks', inspect.call_args.args[0][3])
        started, address_owner = set(), None
        for group in plan:
            for ident in group:
                if ident == "relay":
                    self.assertIsNone(address_owner, "Dynamic API must not steal the relay address")
                    address_owner = "relay"
                if ident == "application":
                    self.assertEqual(address_owner, "relay")
                    self.assertIn("database", started)
                if ident == "edge":
                    self.assertIn("application", started, "Web resolves the API IP only at startup")
                started.add(ident)
        self.assertEqual(started, set(discovery))
        self.assertEqual(sum(len(group) for group in plan), len(discovery))

    def test_optional_relay_absence_and_previously_stopped_services_do_not_add_starts(self):
        with patch.object(backup, "run", return_value=role_metadata({"edge": "web", "application": "api"})):
            self.assertEqual(backup.restart_plan(["edge", "application"]), [["application"], ["edge"]])
        with patch.object(backup, "run") as run:
            self.assertEqual(backup.restart_plan([]), [])
            run.assert_not_called()

    def test_incomplete_duplicate_or_ambiguous_inventory_fails_before_downtime(self):
        for metadata in ("application api", "application api\napplication api", "application\nrelay provider-relay",
                         "application api\nother provider-relay"):
            with self.subTest(metadata=metadata), patch.object(backup, "run", return_value=metadata):
                with self.assertRaises(ValueError):
                    backup.restart_plan(["application", "relay"])
        with patch.object(backup, "run") as run:
            with self.assertRaises(ValueError):
                backup.restart_plan(["application", "application"])
            run.assert_not_called()

    def test_encryption_failure_still_restarts_original_services_in_safe_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recipients = root / "recipients"
            recipients.write_text("SYNTHETIC")
            archive = root / "backup.age"
            starts = []

            def run(command, **_options):
                if "--status" in command:
                    return "edge\napplication\nrelay"
                if command[:2] == ["docker", "inspect"]:
                    return role_metadata({"edge": "web", "application": "api", "relay": "provider-relay"})
                if command[:2] == ["docker", "start"]:
                    starts.append(command[2:])
                return ""

            with patch.object(backup, "compose_command", return_value=["docker", "compose"]), \
                    patch.object(backup, "inventory", return_value=({}, {})), \
                    patch.object(backup, "helper", return_value=["SYNTHETIC-helper"]), \
                    patch.object(backup, "run", side_effect=run), \
                    patch.object(backup.subprocess, "run") as helper, \
                    patch("sys.argv", ["backup", "backup", str(archive), "--recipients-file", str(recipients), "--stop-services"]):
                helper.return_value.returncode = 1
                self.assertEqual(backup.main(), 1)
            self.assertEqual(starts, [["relay"], ["application"], ["edge"]])
            self.assertFalse(archive.exists())
            self.assertFalse(archive.with_name("backup.age.partial").exists())


if __name__ == "__main__":
    unittest.main()
