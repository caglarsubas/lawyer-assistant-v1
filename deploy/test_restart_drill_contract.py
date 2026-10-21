"""Drill admission and subnet planning never prune or reconfigure existing networks."""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "restart_drill", Path(__file__).resolve().parents[1] / "scripts/restart_preflight_drill.py")
drill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drill)


class DrillAdmissionTests(unittest.TestCase):
    def test_mutable_image_is_rejected_before_any_docker_operation(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(drill, "run") as run:
            with self.assertRaises(ValueError):
                drill.drill("python:latest", Path(directory))
            run.assert_not_called()

    def test_unused_subnet_is_calculated_from_inventory_without_network_mutation(self):
        commands = []

        def run(command):
            commands.append(command)
            raw = "a" * 12 if "ls" in command else json.dumps([{"Subnet": "198.19.255.240/28"}])
            return subprocess.CompletedProcess(command, 0, stdout=raw)

        with patch.object(drill, "run", side_effect=run):
            self.assertEqual(drill.unused_drill_subnet(), "198.19.255.224/28")
        self.assertTrue(all(command[2] in {"ls", "inspect"} for command in commands))
        self.assertEqual(len(commands), 2)

    def test_exhausted_or_unverifiable_inventory_cannot_trigger_pruning_or_creation(self):
        for raw in [json.dumps([{"Subnet": "198.19.0.0/16"}]), "[]\n[]", "{}"]:
            with self.subTest(raw=raw), patch.object(drill, "run") as run:
                run.side_effect = [subprocess.CompletedProcess([], 0, stdout="a" * 12),
                                   subprocess.CompletedProcess([], 0, stdout=raw)]
                with self.assertRaises(RuntimeError):
                    drill.unused_drill_subnet()
                self.assertTrue(all(call.args[0][2] in {"ls", "inspect"} for call in run.call_args_list))

    def test_large_inventory_fails_before_inspection(self):
        raw = "\n".join(f"{n:012x}" for n in range(1025))
        with patch.object(drill, "run", return_value=subprocess.CompletedProcess([], 0, stdout=raw)) as run:
            with self.assertRaises(RuntimeError):
                drill.unused_drill_subnet()
            self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
