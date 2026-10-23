import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "scripts"), str(Path(__file__).resolve().parents[1] / "backend")]
from evaluate_origin_route import evaluate, pair  # noqa: E402
from metadata_phase_fixture import RELAY, SENTINEL, Fixture  # noqa: E402
from origin_route_comparison import compare, local_observation, origin_owner, safe_diagnostic  # noqa: E402


class Contracts(unittest.TestCase):
    def test_fresh_frozen_comparisons(self):
        report = evaluate()
        self.assertEqual(report["summary"], {"cases": 10, "expected_results": 10, "mock_connections": 19, "mock_GET_attempts": 16})
        self.assertEqual(report["real_network_calls"], 0)

    def test_local_endpoint_is_fixed_and_origin_failure_sends_nothing(self):
        result, origin, route = pair("ok", "ok")
        self.assertEqual(origin.address, ("127.0.0.1", 8080))
        self.assertNotIn("tls", origin.operations)
        self.assertEqual(route.address, ("8.8.4.4", 443))
        self.assertIn("tls", route.operations)
        wire = b"".join(origin.sent).decode()
        self.assertTrue(wire.startswith("GET /v1/models HTTP/1.1\r\nHost: 127.0.0.1:8080\r\n"))
        self.assertNotIn(origin.binding["api_key"], json.dumps(result))
        _, unavailable, _ = pair("ok", "ok", False)
        self.assertFalse(unavailable.operations)
        fixture = Fixture()
        for bad in ({}, dict(fixture.binding, extra=SENTINEL)):
            observed = local_observation(bad, RELAY, "unused", verifier=lambda _: True, socket_factory=fixture.socket)
            self.assertIsNone(observed["diagnostic"])
            self.assertFalse(fixture.operations)

    def test_no_dns_redirect_retry_or_native_permission(self):
        with patch("socket.getaddrinfo", side_effect=AssertionError("DNS prohibited")):
            result, origin, route = pair("redirect", "preheader_close")
        self.assertEqual((result["aggregate_connection_attempts"], result["aggregate_metadata_GET_attempts"]), (2, 2))
        self.assertEqual(result["local_origin"]["http_status"], 302)
        self.assertEqual(result["approved_route"]["error"], "provider_connection_closed")
        for fixture in (origin, route):
            self.assertEqual(fixture.operations.count("socket_created"), 1)
            self.assertTrue(all(0 < t <= 4 for t in fixture.timeouts))
            self.assertTrue(fixture.closed)
            self.assertNotIn(b"POST", b"".join(fixture.sent))
        for key in ("qualified_identity", "production_activation", "native_execution_authorization", "historical_timeout_cause_established", "responsible_component_identified", "serving_request_trace"):
            self.assertIs(result[key], False)

    def test_report_redaction_and_rejection_of_untrusted_claims(self):
        raw = Fixture().run()
        raw["private"] = SENTINEL
        self.assertNotIn(SENTINEL, json.dumps(safe_diagnostic(raw)))
        for change in ({"error": SENTINEL}, {"http_status": True}, {"connection_attempts": 2}, {"completion_POST_requests": 1},
                       {"qualified_identity": True}, {"metadata_accepted": False}, {"cleanup_complete": False}):
            with self.assertRaises(ValueError):
                safe_diagnostic(dict(raw, **change))
        local = {"context": "host_loopback_origin", "owner_verified": False, "diagnostic": raw}
        with self.assertRaises(ValueError):
            compare(local, raw)
        local = {"context": "host_loopback_origin", "owner_verified": False, "diagnostic": None}
        with self.assertRaises(ValueError):
            compare(local, dict(raw, tls_verified=False))

    def test_owner_check_requires_exact_uid_cwd_interpreter_and_listener(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "src/inference_engine").mkdir(parents=True)
            (root / "src/inference_engine/main.py").touch()
            (root / ".venv/bin").mkdir(parents=True)
            (root / ".venv/bin/python").symlink_to(sys.executable)
            command = f"{sys.executable} -m uvicorn inference_engine.main:app --host 127.0.0.1 --port 8080"
            good = [b"p123\nn127.0.0.1:8080\n", f"{os.getuid()} {command}\n".encode(), f"p123\nn{root}\n".encode()]
            for replacements, expected in (({}, True), ({0: b"p123\nn*:8080\n"}, False),
                    ({0: b"p123\np124\nn127.0.0.1:8080\n"}, False),
                    ({1: f"{os.getuid()+1} {command}".encode()}, False),
                    ({1: f"{os.getuid()} {command} --reload".encode()}, False),
                    ({2: b"p123\nn/wrong\n"}, False)):
                outputs = iter([replacements.get(i, v) for i, v in enumerate(good)])
                def runner(args, **kwargs):
                    self.assertEqual(kwargs["timeout"], 2)
                    self.assertTrue(args[0] in {"/usr/sbin/lsof", "/bin/ps"})
                    return subprocess.CompletedProcess(args, 0, next(outputs), b"")
                self.assertIs(origin_owner(root, runner=runner), expected)
            def fail(*args, **kwargs):
                raise RuntimeError(SENTINEL)
            self.assertIs(origin_owner(root, runner=fail), False)

    def test_local_metadata_stays_unqualified_and_body_bounded(self):
        for mode in ("oversized", "nonfinite", "encoded", "body_timeout", "invalid_json"):
            result, _, _ = pair(mode, "ok")
            self.assertEqual(result["classification"], "route_only_metadata_accepted")
            self.assertFalse(result["local_origin"]["metadata_accepted"])
            self.assertNotIn(SENTINEL, json.dumps(result))

    def test_inconsistent_counts_and_tls_cannot_claim_metadata_acceptance(self):
        raw = Fixture().run()
        for change in ({"connection_attempts": 0}, {"metadata_GET_attempts": 0}, {"tls_required": None},
                       {"tls_required": False, "tls_verified": True}):
            with self.assertRaises(ValueError):
                safe_diagnostic(dict(raw, **change))
