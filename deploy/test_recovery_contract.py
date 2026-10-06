"""Fast recovery boundaries; the Docker drill is opt-in and outside routine CI."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import manage_backup

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixture = load("recovery_fixture")
drill = load("qualify_recovery")


class RecoveryContracts(unittest.TestCase):
    def mounts(self):
        return {service: [{"Destination": target, "Type": "volume", "Name": f"fixture-{service}-{index}", "RW": False}
                          for index, target in enumerate(targets)] + [{"Destination": "/graph-trust", "Type": "bind", "Source": "/private/trust"}]
                for service, targets in manage_backup.VOLUME_TARGETS.items()}

    def test_restore_mounts_readonly_service_volumes_directly_and_omits_unrelated_binds(self):
        mounts = self.mounts()
        with patch.object(manage_backup, "run", side_effect=lambda command: json.dumps(mounts[command[-1]])):
            for writable in (True, False):
                args = manage_backup.volume_mounts(dict(zip(mounts, mounts, strict=True)), writable=writable)
                self.assertEqual(args.count("--mount"), 5)
                self.assertNotIn("--volumes-from", args)
                self.assertFalse(any("trust" in arg for arg in args))
                self.assertEqual(sum("readonly" in arg for arg in args), 0 if writable else 5)
                self.assertTrue(any("dst=/fuseki" in arg for arg in args))
                self.assertTrue(any("dst=/public-sources" in arg for arg in args))

    def test_refuses_missing_bind_aliased_and_malformed_volume_names(self):
        for kind in ("missing", "bind", "alias", "malformed"):
            with self.subTest(kind=kind):
                mounts = self.mounts()
                if kind == "missing":
                    mounts["api"].pop(0)
                elif kind == "bind":
                    mounts["api"][0]["Type"] = "bind"
                elif kind == "alias":
                    mounts["api"][1]["Name"] = mounts["api"][0]["Name"]
                else:
                    mounts["api"][0]["Name"] = "volume,dst=/unexpected"
                with (patch.object(manage_backup, "run", side_effect=lambda command: json.dumps(mounts[command[-1]])),
                      self.assertRaises(ValueError)):
                    manage_backup.volume_mounts(dict(zip(mounts, mounts, strict=True)), writable=True)

    def test_explicit_compose_target_does_not_read_default_env_or_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "compose.json"
            config.write_text("{}")
            actual = manage_backup.compose_command("disposable-recovery", [config], "/dev/null")
            self.assertEqual(actual, ["docker", "compose", "--project-directory", str(ROOT),
                                     "--project-name", "disposable-recovery", "--env-file", "/dev/null", "-f", str(config.resolve())])
            self.assertEqual(manage_backup.compose_command(), manage_backup.COMPOSE)
            for name in ("../live", "", "--project", "UPPER"):
                with self.assertRaises(ValueError):
                    manage_backup.compose_command(name)

    def test_inventory_uses_only_selected_project(self):
        commands = []

        def run(command):
            commands.append(command)
            return "synthetic-container" if "ps" in command else "sha256:synthetic"

        with patch.object(manage_backup, "run", side_effect=run):
            containers, images = manage_backup.inventory(["selected-project"])
        self.assertEqual(set(containers), set(manage_backup.SERVICES))
        self.assertEqual(set(images), set(manage_backup.SERVICES))
        self.assertTrue(all(command[0] == "selected-project" for command in commands if "ps" in command))

    def test_backup_preserves_grace_and_restarts_only_previously_running_containers(self):
        import contextlib
        import io
        import subprocess

        for helper_code in (0, 1):
            with self.subTest(helper_code=helper_code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                key, archive = root / "recipients", root / "backup.age"
                key.write_text("synthetic recipient")
                commands = []

                def run(command, **options):
                    commands.append((command, options))
                    return "owned-api\nowned-postgres" if "ps" in command else ""

                def transfer(command, **options):
                    options["stdout"].write(b"synthetic encrypted archive")
                    return subprocess.CompletedProcess(command, helper_code)

                args = ["manage_backup.py", "backup", str(archive), "--recipients-file", str(key), "--stop-services"]
                with (patch("sys.argv", args), patch.object(manage_backup, "inventory", return_value=({}, {})),
                      patch.object(manage_backup, "helper", return_value=["synthetic-helper"]),
                      patch.object(manage_backup, "run", side_effect=run),
                      patch.object(manage_backup.subprocess, "run", side_effect=transfer),
                      contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO())):
                    self.assertEqual(manage_backup.main(), helper_code)
                self.assertEqual(commands[-1][0], ["docker", "start", "owned-api", "owned-postgres"])
                self.assertIn((["docker", "stop", "owned-api", "owned-postgres"], {"timeout": 600}), commands)
                self.assertEqual(archive.exists(), helper_code == 0)
                self.assertFalse(archive.with_name("backup.age.partial").exists())

    def test_drill_has_no_host_ports_bind_mounts_or_external_network(self):
        definition = drill.compose_definition(dict.fromkeys(manage_backup.SERVICES, "sha256:fixture"), "key", "password")
        self.assertEqual(definition["networks"], {"isolated": {"internal": True}})
        self.assertEqual(len(definition["volumes"]), 5)
        for service in definition["services"].values():
            self.assertNotIn("ports", service)
            self.assertNotIn("env_file", service)
            self.assertEqual(service["pull_policy"], "never")
            self.assertEqual(service["networks"], ["isolated"])
            self.assertGreater(service["pids_limit"], 0)
            self.assertTrue(all(mount.split(":")[0] in definition["volumes"] for mount in service["volumes"]))
        self.assertEqual(definition["services"]["api"]["stop_grace_period"], "240s")
        environment = definition["services"]["api"]["environment"]
        self.assertFalse(any(key.startswith("LLM_") for key in environment))
        self.assertEqual(environment["LA_RECOVERY_DRILL"], fixture.MARKER)

    def test_probe_rejects_without_explicit_drill_marker(self):
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(ValueError):
            fixture.require_drill()

    def test_image_fingerprint_detects_source_and_lock_changes_without_reading_env(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ("backend/app", "scripts", "ontology", "deploy"):
                (root / folder).mkdir(parents=True)
            files = ("backend/pyproject.toml", "backend/uv.lock", "deploy/volume_archive.py", "backend/app/main.py")
            for name in files:
                (root / name).write_text("initial")
            initial = fixture.code_fingerprint(root)
            # A broken .env link would fail if the fingerprint attempted to read it.
            (root / ".env").symlink_to(root / "does-not-exist")
            self.assertEqual(fixture.code_fingerprint(root), initial)
            for name in files:
                (root / name).write_text("changed")
                self.assertNotEqual(fixture.code_fingerprint(root), initial)
                (root / name).write_text("initial")

    def test_inventory_detects_byte_and_permission_changes_but_excludes_only_epoch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "data"
            path.write_text("first")
            initial = fixture.file_inventory({"documents": root})
            (root / "publication-epoch").write_text("old")
            self.assertEqual(fixture.file_inventory({"documents": root}), initial)
            path.write_text("other")
            changed = fixture.file_inventory({"documents": root})
            self.assertNotEqual(changed, initial)
            path.chmod(0o400)
            self.assertNotEqual(fixture.file_inventory({"documents": root}), changed)
            path.chmod(0o600)
            path.unlink()
            path.symlink_to("/etc/passwd")
            with self.assertRaises(ValueError):
                fixture.file_inventory({"documents": root})

    def test_existing_project_is_never_owned_or_cleaned_up(self):
        with patch.object(drill, "command", return_value="existing-resource") as call, self.assertRaises(RuntimeError):
            drill.fresh_project("disposable-recovery")
        self.assertEqual(call.call_count, 1)
        self.assertIn("ls", call.call_args.args[0])

    def test_expected_failure_must_really_fail_and_diagnostics_omit_output(self):
        import subprocess

        for expected, returncode in ((1, 0), (0, 1)):
            with patch.object(drill.subprocess, "run", return_value=subprocess.CompletedProcess([], returncode, "PRIVATE", "SECRET")):
                with self.assertRaises(RuntimeError) as caught:
                    drill.command(["fixture"], expected=expected)
                self.assertNotIn("PRIVATE", str(caught.exception))
                self.assertNotIn("SECRET", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
