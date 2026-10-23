import ast
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import httpx

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "scripts"), str(Path(__file__).resolve().parents[1] / "backend")]
from evaluate_routed_metadata import evaluate  # noqa: E402 - standalone deployment-test path bootstrap
from routed_metadata_diagnostics import (  # noqa: E402 - standalone deployment-test path bootstrap
    RELAY_CODES,
    Observation,
    diagnose,
)
from routed_metadata_fixture import (  # noqa: E402 - standalone deployment-test path bootstrap
    SENTINEL,
    Fixture,
)


class Stream(httpx.SyncByteStream):
    def __init__(self, chunks=(), error=None):
        self.chunks, self.error = chunks, error

    def __iter__(self):
        yield from self.chunks
        if self.error:
            raise self.error


class Contracts(unittest.TestCase):
    def custom(self, response, **kwargs):
        fixture = Fixture("legacy_ok")
        requests = []

        def serve(request):
            requests.append(request)
            if isinstance(response, Exception):
                raise response
            return response

        result = diagnose(fixture.provider, client=lambda **options: httpx.Client(transport=httpx.MockTransport(serve), **options), **kwargs)
        self.assertNotIn(SENTINEL, json.dumps(result))
        self.assertLessEqual(len(requests), 1)
        self.assertFalse(result["qualified_identity"])
        return result

    def test_frozen_first_stage_comparison(self):
        report = evaluate()
        self.assertEqual(report["summary"], {"cases": 12, "expected_stages": 12, "mock_GET_requests": 12,
                                           "mock_POST_requests": 0, "qualified_identities": 0})

    def test_exact_get_only_and_no_reflection(self):
        fixture = Fixture("legacy_ok")
        result = fixture.run()
        self.assertEqual(len(fixture.requests), 1)
        request = fixture.requests[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(str(request.url), fixture.provider._base() + "/models")
        self.assertEqual(request.content, b"")
        self.assertEqual(request.headers["authorization"], "Bearer " + fixture.provider.settings.provider_api_key)
        self.assertEqual(len(request.headers["X-Lawyer-Identity-Challenge"]), 32)
        self.assertNotIn(fixture.provider.settings.provider_api_key, json.dumps(result))
        self.assertEqual(result["metadata_GET_attempts"], 1)
        self.assertEqual(result["completion_POST_requests"], 0)

    def test_all_finite_relay_codes(self):
        for code in RELAY_CODES:
            result = self.custom(httpx.Response(502, json={"code": code, "error": SENTINEL}))
            self.assertEqual(result["relay_code"], code)
            self.assertEqual(result["http_status"], 502)
            self.assertEqual(result["stage"], "http_status_rejected")

    def test_unknown_fields_and_location_never_escape(self):
        for status in (301, 302, 307, 401, 403, 404, 409, 429, 500, 502, 503):
            result = self.custom(httpx.Response(status, headers={"Location": "https://invalid.example/" + SENTINEL},
                                               json={"code": SENTINEL, "error": SENTINEL, "trace": SENTINEL}))
            self.assertIsNone(result["relay_code"])
            self.assertEqual(result["stage"], "http_status_rejected")

    def test_invalid_configuration_sends_nothing(self):
        for field, value in (("provider_api_key", ""), ("provider_identity_verified", False),
                             ("provider_cloud_fallback_disabled", False), ("provider_context_limit", 8193),
                             ("provider_base_url", "https://invalid.example/v1")):
            fixture = Fixture("legacy_ok")
            setattr(fixture.provider.settings, field, value)
            result = fixture.run()
            self.assertEqual(result["stage"], "configuration_rejected")
            self.assertEqual(result["metadata_GET_attempts"], 0)
            self.assertFalse(fixture.requests)

    def test_nonprovider_fails_closed_without_network(self):
        self.assertEqual(diagnose(None)["stage"], "configuration_rejected")

    def test_observer_refuses_extra_methods_destinations_and_replay(self):
        fixture = Fixture("legacy_ok")
        observation = Observation(fixture.provider._base() + "/models", fixture.client, lambda: 0)
        with observation.factory(follow_redirects=False, trust_env=False) as client:
            for method, url, kwargs in (("POST", observation.expected_url, {"headers": {}}),
                                         ("GET", "https://invalid.example/", {"headers": {}}),
                                         ("GET", observation.expected_url, {"headers": {}, "content": b"private"})):
                with self.assertRaises(ValueError), client.stream(method, url, **kwargs):
                    self.fail("Unapproved diagnostic request admitted")
            with client.stream("GET", observation.expected_url, headers={}):
                pass
            with self.assertRaises(ValueError), client.stream("GET", observation.expected_url, headers={}):
                self.fail("Repeated diagnostic request admitted")
        self.assertEqual(len(fixture.requests), 1)

    def test_transport_options_cannot_enable_proxy_or_redirect(self):
        observation = Observation("unused", None, lambda: 0)
        for options in ({}, {"follow_redirects": True, "trust_env": False}, {"follow_redirects": False, "trust_env": True}):
            with self.assertRaises(ValueError):
                observation.factory(**options)

    def test_client_failures_are_finite_not_exception_messages(self):
        for cls, label in ((httpx.ConnectTimeout, "connect_timeout"), (httpx.ReadTimeout, "read_timeout"),
                           (httpx.WriteTimeout, "write_timeout"), (httpx.PoolTimeout, "pool_timeout"),
                           (httpx.ConnectError, "connect_error"), (httpx.ReadError, "read_error"),
                           (httpx.RemoteProtocolError, "remote_protocol_error"), (httpx.WriteError, "http_error")):
            result = self.custom(cls(SENTINEL))
            self.assertEqual(result["stage"], "http_transport_rejected")
            self.assertEqual(result["client_error"], label)

    def test_error_body_budget_cannot_reflect_or_admit_prefix(self):
        body = b'{"code":"provider_connection_closed","padding":"' + b"x" * 4096 + b'"}'
        result = self.custom(httpx.Response(502, stream=Stream((body[:50], body[50:]))))
        self.assertEqual(result["error_body_state"], "budget_exceeded")
        self.assertIsNone(result["relay_code"])

    def test_error_json_is_strict_and_shape_checked(self):
        for raw in (b'{"code":"provider_connection_closed","code":"other"}', b'{"code":NaN}',
                    b'\xff', b"[]", b"null", b'{"code":{}}', b'{"code":123}'):
            result = self.custom(httpx.Response(502, content=raw))
            self.assertIsNone(result["relay_code"])
            self.assertIn(result["error_body_state"], {"invalid_json", "no_allowlisted_code"})

    def test_encoded_error_body_is_not_parsed(self):
        result = self.custom(httpx.Response(502, headers={"Content-Encoding": "custom"}, content=SENTINEL))
        self.assertEqual(result["error_body_state"], "encoded_body_skipped")
        self.assertIsNone(result["relay_code"])

    def test_incomplete_error_body_does_not_hide_http_status(self):
        result = self.custom(httpx.Response(503, stream=Stream((b'{"code":',), httpx.ReadTimeout(SENTINEL))))
        self.assertEqual(result["http_status"], 503)
        self.assertEqual(result["stage"], "http_status_rejected")
        self.assertEqual(result["error_body_state"], "transport_error")

    def test_error_deadline_exhaustion_does_not_admit_code(self):
        values = iter((0, 11, 11))
        result = self.custom(httpx.Response(502, json={"code": "provider_connection_closed"}), clock=lambda: next(values))
        self.assertEqual(result["error_body_state"], "budget_exceeded")
        self.assertIsNone(result["relay_code"])

    def test_metadata_rejection_does_not_become_authentication_failure(self):
        for mode in ("invalid_json", "foreign_route", "absent_model", "small_context", "oversized", "encoded"):
            result = Fixture(mode).run()
            self.assertEqual(result["http_status"], 200)
            self.assertFalse(result["metadata_accepted"])
            self.assertNotEqual(result["stage"], "http_status_rejected")

    def test_unknown_exception_is_redacted_and_silent(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = self.custom(RuntimeError(SENTINEL))
        self.assertEqual(result["stage"], "unclassified_rejection")
        self.assertEqual(out.getvalue() + err.getvalue(), "")

    def test_legacy_success_remains_unqualified(self):
        result = Fixture("legacy_ok").run()
        self.assertTrue(result["metadata_accepted"])
        self.assertEqual(result["identity_issue"], "signed_provider_identity_unavailable")
        self.assertFalse(result["qualified_identity"] or result["native_execution_authorization"] or result["production_activation"])

    def test_changed_configuration_is_not_success(self):
        result = Fixture("changed_config").run()
        self.assertEqual(result["stage"], "configuration_changed")
        self.assertFalse(result["metadata_accepted"])

    def test_allowlist_matches_restricted_relay_source(self):
        tree = ast.parse((Path(__file__).resolve().parent / "provider/relay.py").read_text())
        value = next(n.value for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "FAILURE_CODES" for t in n.targets))
        self.assertEqual(RELAY_CODES, frozenset(ast.literal_eval(value.args[0])))

    def test_report_shape_excludes_identifiers_bodies_and_paths(self):
        result = Fixture("legacy_ok").run()
        self.assertEqual(set(result), {"recipe", "stage", "http_status", "client_error", "relay_code", "error_body_state",
                                      "metadata_GET_attempts", "completion_POST_requests", "native_inference_calls", "metadata_accepted",
                                      "identity_issue", "qualified_identity", "native_execution_authorization", "production_activation"})


if __name__ == "__main__":
    unittest.main()
