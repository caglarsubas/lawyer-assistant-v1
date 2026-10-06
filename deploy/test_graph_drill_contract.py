"""Fast drill isolation/failure boundaries. No Docker or SHACL workload in CI."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import graph_drill_fixture as fixture  # noqa: E402
import qualify_graph as drill  # noqa: E402


class GraphDrillContracts(unittest.TestCase):
    def test_isolation_and_readonly_runtime_with_explicit_test_trust(self):
        definition = drill.compose_definition({"api": "sha256:api", "fuseki": "sha256:fuseki"})
        self.assertEqual(definition["networks"], {"isolated": {"internal": True}})
        self.assertEqual(set(definition["volumes"]), {"graphs", "fixture"})
        for service in definition["services"].values():
            for prohibited in ("ports", "env_file", "network_mode", "privileged", "build"):
                self.assertNotIn(prohibited, service)
            self.assertEqual(service["pull_policy"], "never")
            self.assertEqual(service["networks"], ["isolated"])
            self.assertTrue(service["read_only"])
            self.assertTrue(all(mount["type"] == "volume" and mount["source"] in definition["volumes"]
                                and mount["volume"]["nocopy"] for mount in service["volumes"]))
            self.assertFalse(any(name.startswith("LLM_") or "KEY" in name and "TRUSTED_REVIEW" not in name
                                 for name in service["environment"]))
        runtime = definition["services"]["fuseki"]
        self.assertTrue(all(mount["read_only"] for mount in runtime["volumes"]))
        self.assertEqual(runtime["environment"], {"LA_GRAPH_TRUSTED_REVIEW_KEY": "/drill/TEST-ONLY-public.pem"})
        self.assertNotIn("LA_GRAPH_DRILL", runtime["environment"])
        self.assertEqual(definition["services"]["bootstrap"]["cap_add"], ["CHOWN"])
        self.assertNotIn("cap_add", definition["services"]["fixture"])

    def test_fixture_requires_explicit_marker_before_engine_or_volume_access(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(fixture, "engine") as engine:
            with self.assertRaises(ValueError):
                fixture.dispatch("seed")
        engine.assert_not_called()

    def test_bootstrap_rejects_either_nonempty_root_before_changing_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            roots = [Path(directory) / name for name in ("graphs", "fixture")]
            for root in roots:
                root.mkdir(mode=0o700)
            for dirty in roots:
                sentinel = dirty / "existing"
                sentinel.write_text("must not change")
                with (patch.object(fixture, "VOLUME", roots[0]), patch.object(fixture, "WORK", roots[1]),
                      patch.object(fixture.os, "geteuid", return_value=0), patch.object(fixture.os, "chown") as chown,
                      self.assertRaises(ValueError)):
                    fixture.bootstrap()
                chown.assert_not_called()
                self.assertTrue(all(root.stat().st_mode & 0o777 == 0o700 for root in roots))
                self.assertEqual(sentinel.read_text(), "must not change")
                sentinel.unlink()

    def test_synthetic_guard_rejects_foreign_or_unsigned_release_and_real_reviewer(self):
        state = {"releases": {name: {"release_id": name * 64} for name in ("a", "b", "c")}}
        info = {"release_id": "a" * 64, "review": {"verified": True, "reviewer": fixture.REVIEWER}}
        with patch.dict(os.environ, {"LA_GRAPH_DRILL": fixture.MARKER}), patch.object(fixture, "state", return_value=state):
            with fixture.synthetic_guard(info, "install"):
                pass
            for override in ({"release_id": "d" * 64}, {"review": {"verified": False, "reviewer": fixture.REVIEWER}},
                             {"review": {"verified": True, "reviewer": "real reviewer"}}):
                with self.subTest(override=override), self.assertRaises(ValueError), fixture.synthetic_guard({**info, **override}, "install"):
                    pass
            with self.assertRaises(ValueError), fixture.synthetic_guard(info, "read"):
                pass

    def test_corruption_must_be_an_integrity_exit_not_oom_or_generic_failure(self):
        state = {"Running": False, "ExitCode": 1, "OOMKilled": False, "Restarting": False}
        message = "Fuseki serving release startup failed: Serving payload differs from signed source graph"
        drill.require_failed_start(state, message)
        for changed in ({"Running": True}, {"ExitCode": 0}, {"ExitCode": 137}, {"OOMKilled": True}, {"Restarting": True}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                drill.require_failed_start({**state, **changed}, message)
        for log in ("", "a different startup error", message + '\n{"event": "no_active_release"}',
                    message + '\n{"event": "verified_release_loaded"}'):
            with self.subTest(log=log), self.assertRaises(ValueError):
                drill.require_failed_start(state, log)

    def test_denial_requires_expected_reason_and_unchanged_pointer(self):
        serving = SimpleNamespace(read_pointer=lambda root: {"sequence": 1})
        self.assertTrue(fixture.denied(serving, lambda: (_ for _ in ()).throw(ValueError("stop Fuseki")), "stop Fuseki")["denied"])
        with self.assertRaises(ValueError):
            fixture.denied(serving, lambda: None, "stop Fuseki")
        with self.assertRaises(ValueError):
            fixture.denied(serving, lambda: (_ for _ in ()).throw(ValueError("other failure")), "stop Fuseki")
        with patch.object(serving, "read_pointer", side_effect=[{"sequence": 1}, {"sequence": 2}]), self.assertRaises(ValueError):
            fixture.denied(serving, lambda: (_ for _ in ()).throw(ValueError("stop Fuseki")), "stop Fuseki")

    def test_runtime_verification_rejects_extra_or_mixed_named_graphs(self):
        info = {"release_id": "a" * 64, "metadata_graph_iri": "urn:meta",
                "graphs": {"structure": {"graph_iri": "urn:a", "triple_count": 10}}}
        def row(iri, count):
            return {"g": {"value": iri}, "count": {"value": str(count)}}
        for rows in ([row("urn:b", 10), row("urn:meta", 5)], [row("urn:a", 10)],
                     [row("urn:a", 10), row("urn:meta", 5), row("urn:b", 10)]):
            with (patch.object(fixture, "state", return_value={"releases": {"a": info}}),
                  patch.object(fixture, "select", return_value=rows), self.assertRaises(ValueError)):
                fixture.verify_served("a")

    def test_fuseki_fingerprint_detects_runtime_and_added_ontology_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (*drill.FUSEKI_FILES, "ontology/modules/a.ttl"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("initial")
            before = drill.fuseki_fingerprint(root)
            (root / "deploy/fuseki/runtime.py").write_text("different")
            self.assertNotEqual(drill.fuseki_fingerprint(root), before)
            (root / "deploy/fuseki/runtime.py").write_text("initial")
            (root / "ontology/modules/added.ttl").write_text("extra")
            self.assertNotEqual(drill.fuseki_fingerprint(root), before)

    def test_preflight_failure_writes_failed_report_without_owning_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            args = ["qualify_graph.py", "--api-image", "fixture-api", "--fuseki-image", "fixture-fuseki", "--output", str(output)]
            with (patch("sys.argv", args), patch.object(drill, "command", side_effect=RuntimeError("PRIVATE")),
                  patch.object(drill, "cleanup_project") as cleanup):
                self.assertEqual(drill.main(), 1)
            cleanup.assert_not_called()
            report = json.loads(output.read_bytes())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["failure_stage"], "preflight")
            self.assertNotIn("PRIVATE", output.read_text())
            with patch("sys.argv", args), patch.object(drill, "command") as command, self.assertRaises(FileExistsError):
                drill.main()
            command.assert_not_called()

    def test_successful_workload_cannot_pass_when_cleanup_fails_or_is_interrupted(self):
        def command(args, **kwargs):
            if "--format" in args and "NCPU" in args[args.index("--format") + 1]:
                return "{}"
            if args[:2] == ["docker", "exec"]:
                return "100\n1024\n16\n256\nusage_usec 1200\nnr_periods 10\nnr_throttled 0\nthrottled_usec 0\n"
            return "fixture-id"

        def probe(compose, action, **kwargs):
            return {"verify-a": {"release_id": "a"}, "verify-b": {"release_id": "b"},
                    "ready": {"ready": True}, "activate-b": {"sequence": 2},
                    "rollback-a": {"sequence": 3, "release_id": "a"}}.get(action, {})

        for failure in (RuntimeError("cleanup failed"), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "report.json"
                args = ["qualify_graph.py", "--api-image", "fixture", "--fuseki-image", "fixture", "--output", str(output)]
                with (patch("sys.argv", args), patch.object(drill, "command", side_effect=command),
                      patch.object(drill, "verify_images", return_value={}), patch.object(drill, "fresh_project"),
                      patch.object(drill, "probe", side_effect=probe),
                      patch.object(drill, "container_state", return_value={"Running": True, "OOMKilled": False, "Restarting": False}),
                      patch.object(drill, "wait_exit", return_value={"ExitCode": 137, "OOMKilled": False}),
                      patch.object(drill, "require_failed_start"),
                      patch.object(drill.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")),
                      patch.object(drill, "cleanup_project", side_effect=failure) as cleanup):
                    if isinstance(failure, KeyboardInterrupt):
                        with self.assertRaises(KeyboardInterrupt):
                            drill.main()
                    else:
                        self.assertEqual(drill.main(), 1)
                cleanup.assert_called_once()
                report = json.loads(output.read_bytes())
                self.assertEqual(len(report["startups"]), 5)
                self.assertEqual(report["status"], "failed")
                self.assertFalse(report["cleanup"]["complete"])


if __name__ == "__main__":
    unittest.main()
