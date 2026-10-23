import io
import json
import ssl
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "scripts"), str(Path(__file__).resolve().parents[1] / "backend")]
from evaluate_metadata_phases import evaluate  # noqa: E402 - standalone deployment-test bootstrap
from metadata_phase_fixture import RELAY, SENTINEL, Fixture  # noqa: E402
from metadata_phase_probe import binding_target, probe, strict_json  # noqa: E402


class Contracts(unittest.TestCase):
    def test_frozen_eight_phase_cases(self):
        self.assertEqual(evaluate()["summary"], {"cases": 8, "expected_results": 8, "mock_connections": 8,
                                               "mock_GET_attempts": 6, "mock_POST_requests": 0, "qualified_identities": 0})

    def test_every_timeout_has_exact_phase_and_one_connection(self):
        for mode, phase in (("tcp_timeout", "tcp_connect"), ("tls_timeout", "tls_handshake"), ("send_timeout", "request_send"),
                            ("headers_timeout", "response_headers"), ("body_timeout", "response_body")):
            fixture = Fixture(mode)
            result = fixture.run()
            self.assertEqual((result["last_phase"], result["outcome"], result["error"]), (phase, "timeout", "socket_timeout"))
            self.assertEqual(result["connection_attempts"], 1)
            self.assertEqual(fixture.operations.count("socket_created"), 1)
            self.assertTrue(result["deadline_reached"])

    def test_exact_get_host_auth_and_no_private_report(self):
        fixture = Fixture()
        result = fixture.run()
        wire = b"".join(fixture.sent).decode()
        self.assertTrue(wire.startswith("GET /v1/models HTTP/1.1\r\n"))
        self.assertIn("Host: synthetic.example\r\n", wire)
        self.assertIn("Authorization: Bearer " + fixture.binding["api_key"] + "\r\n", wire)
        self.assertTrue(wire.endswith("\r\n\r\n"))
        for private in (fixture.binding["api_key"], fixture.binding["model_id"], "synthetic.example", "8.8.4.4", SENTINEL):
            self.assertNotIn(private, json.dumps(result))
        self.assertEqual(fixture.address, ("8.8.4.4", 443))
        self.assertEqual(fixture.server_hostname, "synthetic.example")

    def test_no_request_dns_resolution_or_redirect(self):
        with patch("socket.getaddrinfo", side_effect=AssertionError("DNS prohibited")):
            fixture = Fixture("redirect")
            result = fixture.run()
        self.assertEqual(result["http_status"], 302)
        self.assertEqual(result["error"], "http_status_rejected")
        self.assertEqual(result["metadata_GET_attempts"], 1)
        self.assertEqual(fixture.operations.count("socket_created"), 1)

    def test_binding_field_set_and_origin_rejected_before_io(self):
        for change in ({"relay_base": "https://invalid.example/v1"}, {"extra": "private"}, {"model_id": "../ bad"},
                       {"app_context": 8193}, {"app_context": True}, {"api_key": "bad\r\nheader"}, {"api_key": "short"}):
            fixture = Fixture()
            fixture.binding.update(change)
            result = fixture.run()
            self.assertFalse(fixture.operations)
            self.assertEqual(result["connection_attempts"], 0)
            self.assertEqual(result["error"], "configuration_rejected")

    def test_route_hostname_hash_and_mode_must_match(self):
        for change in ({"approved_hostname": "other.example"}, {"route_sha256": "0" * 64}, {"transport_mode": "native_private"}):
            fixture = Fixture()
            fixture.binding.update(change)
            result = fixture.run()
            self.assertEqual(result["error"], "route_rejected")
            self.assertFalse(fixture.operations)

    def test_unapproved_bootstrap_pin_sends_nothing(self):
        for change in ({"PROVIDER_TUNNEL_IP": "127.0.0.1"}, {"PROVIDER_TUNNEL_IP": "192.168.1.3"},
                       {"PROVIDER_TUNNEL_APPROVED": "false"}, {"PROVIDER_TUNNEL_URL": "http://synthetic.example/v1"}):
            fixture = Fixture()
            fixture.environ.update(change)
            result = fixture.run()
            self.assertEqual(result["connection_attempts"], 0)
            self.assertFalse(fixture.operations)

    def test_native_private_mode_skips_tls_without_cloud_target(self):
        fixture = Fixture()
        fixture.environ = {"PROVIDER_NATIVE_IP": "192.168.1.5"}
        fixture.binding.update(transport_mode="native_private", approved_hostname=None, route_sha256=None)
        result = fixture.run()
        self.assertTrue(result["metadata_accepted"])
        self.assertFalse(result["tls_required"])
        self.assertNotIn("tls_handshake", result["completed_phases"])
        self.assertEqual(fixture.address, ("192.168.1.5", 8080))

    def test_tls_verification_cannot_be_disabled(self):
        for field, value in (("check_hostname", False), ("verify_mode", ssl.CERT_NONE)):
            fixture = Fixture()
            setattr(fixture.context, field, value)
            result = fixture.run()
            self.assertEqual(result["error"], "tls_policy_rejected")
            self.assertEqual(result["connection_attempts"], 0)

    def test_tls_failure_does_not_send_credentials(self):
        fixture = Fixture("tls_error")
        result = fixture.run()
        self.assertEqual((result["last_phase"], result["error"]), ("tls_handshake", "tls_error"))
        self.assertEqual(result["metadata_GET_attempts"], 0)
        self.assertFalse(fixture.sent)

    def test_shared_four_second_budget_never_expands(self):
        fixture = Fixture()
        result = fixture.run()
        self.assertEqual(result["budget_seconds"], 4)
        self.assertTrue(fixture.timeouts)
        self.assertTrue(all(0 < v <= 4 for v in fixture.timeouts))

    def test_connection_close_body_retains_socket_deadline(self):
        fixture = Fixture("body_timeout")
        result = fixture.run()
        self.assertIn("response_headers", result["completed_phases"])
        self.assertEqual(result["last_phase"], "response_body")
        self.assertEqual(result["error"], "socket_timeout")
        self.assertGreaterEqual(len(fixture.timeouts), 4)

    def test_body_size_and_encoding_fail_closed(self):
        for mode, error in (("oversized", "body_budget_exceeded"), ("encoded", "encoding_rejected")):
            result = Fixture(mode).run()
            self.assertEqual(result["error"], error)
            self.assertFalse(result["metadata_accepted"])

    def test_strict_json_rejects_duplicates_nonfinite_and_bad_utf8(self):
        for raw in (b'{"a":1,"a":2}', b'{"n":NaN}', b'{"n":Infinity}', b'{"n":1e999}', b'{"nested":[-1e999]}', b'\xff'):
            with self.assertRaises((ValueError, UnicodeError)):
                strict_json(raw)

    def test_parser_failure_is_silent_and_does_not_reflect_body(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = Fixture("invalid_json").run()
        self.assertFalse(result["metadata_accepted"])
        self.assertNotIn(SENTINEL, json.dumps(result))
        self.assertEqual(out.getvalue() + err.getvalue(), "")

    def test_cleanup_failure_is_redacted(self):
        with patch("http.client.HTTPResponse.close", side_effect=RuntimeError(SENTINEL)):
            result = Fixture().run()
        self.assertFalse(result["cleanup_complete"])
        self.assertNotIn(SENTINEL, json.dumps(result))

    def test_success_is_not_identity_or_native_authority(self):
        result = Fixture().run()
        self.assertTrue(result["metadata_accepted"])
        self.assertFalse(result["qualified_identity"] or result["native_execution_authorization"] or result["production_activation"])
        self.assertEqual(result["completion_POST_requests"], 0)

    def test_unknown_transport_exception_is_redacted(self):
        fixture = Fixture()
        def fail(*args):
            raise RuntimeError(SENTINEL)
        result = probe(fixture.binding, RELAY, fixture.environ, socket_factory=fail, context_factory=lambda: fixture.context, clock=lambda: fixture.now)
        self.assertEqual(result["error"], "unclassified_rejection")
        self.assertNotIn(SENTINEL, json.dumps(result))

    def test_unrelated_context_cannot_retarget_route(self):
        fixture = Fixture()
        fixture.binding["approved_hostname"] = "other.example"
        with self.assertRaises(ValueError):
            binding_target(fixture.binding, RELAY, fixture.environ)

    def test_fixed_report_has_no_body_hash_or_identifiers(self):
        self.assertEqual(set(Fixture().run()), {"recipe", "last_phase", "outcome", "error", "completed_phases", "connection_attempts",
                                               "metadata_GET_attempts", "completion_POST_requests", "http_status", "tls_required", "tls_verified",
                                               "metadata_accepted", "budget_seconds", "deadline_reached", "cleanup_complete", "qualified_identity",
                                               "native_execution_authorization", "production_activation"})

    def test_truncated_declared_body_cannot_admit_a_valid_json_prefix(self):
        fixture = Fixture()
        def short_file(sock, mode):
            body = b'{"data":[]}'
            return Fixture.File(sock.owner, sock, b'HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 999\r\n\r\n' + body)
        with patch.object(Fixture.Socket, "makefile", short_file):
            result = fixture.run()
        self.assertEqual(result["error"], "incomplete_body")
        self.assertEqual(result["last_phase"], "response_body")
        self.assertFalse(result["metadata_accepted"])

    def test_connection_closed_before_headers_has_no_invented_http_status(self):
        fixture = Fixture()
        def empty_file(sock, mode):
            return Fixture.File(sock.owner, sock, b'')
        with patch.object(Fixture.Socket, "makefile", empty_file):
            result = fixture.run()
        self.assertEqual(result["last_phase"], "response_headers")
        self.assertEqual(result["error"], "provider_connection_closed")
        self.assertIsNone(result["http_status"])
        self.assertEqual(result["completed_phases"], ["tcp_connect", "tls_handshake", "request_send"])


if __name__ == "__main__":
    unittest.main()
