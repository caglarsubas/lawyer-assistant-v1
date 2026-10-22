"""Deterministic relay saturation and disposable real-job boundaries; no inference."""

import errno
import importlib.util
import json
import os
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPMessage
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from load_fixture import MARKER as LOAD_MARKER  # noqa: E402
from provider_job_fixture import MARKER, real_settings  # noqa: E402
from qualify_provider_jobs import definition  # noqa: E402

from app.evidence_prompt import quote_catalog, quote_messages, resolve_quote_selection  # noqa: E402

spec = importlib.util.spec_from_file_location("backpressure_relay", ROOT / "deploy/provider/relay.py")
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


def handler(slots=None):
    value = relay.Handler.__new__(relay.Handler)
    value.server = SimpleNamespace(upstream=relay.Upstream("10.1.2.3"), model="synthetic-model",
                                   upstream_slots=slots if slots is not None else threading.BoundedSemaphore(2))
    value.headers = HTTPMessage()
    value.headers["Authorization"] = "Bearer fixture-only"
    value.command, value.path = "POST", "/v1/chat/completions"
    value.results = []
    value.send_json = lambda status, payload: value.results.append((status, payload))
    return value


class BackpressureContracts(unittest.TestCase):
    def test_only_overlapping_same_credential_metadata_is_shared_without_a_cache(self):
        server = relay.Server(("127.0.0.1", 0), "10.1.2.3", "synthetic-model")
        calls, lock = [], threading.Lock()
        joined = threading.Barrier(6, timeout=2)
        original_join = server.join_metadata

        def synchronized(auth):
            result = original_join(auth)
            joined.wait()
            return result

        server.join_metadata = synchronized

        class Response:
            status, sent = 200, False

            def getheader(self, name, default=None):
                return default

            def read1(self, size):
                if self.sent:
                    return b""
                self.sent = True
                return b'{"data":[]}'

        class Connection:
            def __init__(self, *args, **kwargs):
                with lock:
                    calls.append(1)

            def request(self, *args, **kwargs):
                pass

            def getresponse(self):
                return Response()

            def close(self):
                pass

        def request():
            value = handler()
            value.server = server
            value.command, value.path = "GET", "/v1/models"

            def capture(status, payload):
                if getattr(value, "metadata_flight", None) is not None:
                    server.publish_metadata(value.metadata_key, value.metadata_flight, (status, payload))
                value.results.append((status, payload))

            value.send_json = capture
            value.forward(None)
            return value.results

        try:
            with patch.object(relay.http.client, "HTTPConnection", Connection), ThreadPoolExecutor(5) as pool:
                futures = [pool.submit(request) for _ in range(5)]
                joined.wait()
                self.assertTrue(all(f.result(2)[0][0] == 200 for f in futures))
                self.assertEqual(len(calls), 1)
                self.assertEqual(server.metadata_flights, {})
                server.join_metadata = original_join
                self.assertEqual(request()[0][0], 200)
                self.assertEqual(len(calls), 2)  # No TTL or stale reuse by a later task.
            a, first, first_leader = original_join("Bearer fixture-one")
            b, second, second_leader = original_join("Bearer fixture-two")
            self.assertNotEqual(a, b)
            self.assertTrue(first_leader and second_leader)
            server.publish_metadata(a, first, (401, {"error": "denied"}))
            self.assertFalse(second["ready"].is_set())
            server.publish_metadata(b, second, (200, {"data": []}))
            self.assertEqual(server.metadata_flights, {})
        finally:
            server.server_close()

    def test_server_copies_selected_original_text_without_normalizing_it(self):
        passages = [{"id": "frozen-version-A", "text": "SYNTHETIC ornek tutar 100 birimdir.\r\nI\u0307 exact."}]
        original = json.loads(json.dumps(passages))
        envelope = json.loads(quote_messages("payment", passages)[1]["content"])
        quote = envelope["evidence"][0]["quotes"][0]
        self.assertEqual(quote, {"id": "Q1", "start": 0, "end": len(passages[0]["text"])})
        result = json.loads(resolve_quote_selection('{"quote_ids":["Q1"]}', passages))
        self.assertEqual(result, {"summary": "", "claims": [{"text": passages[0]["text"], "evidence_ids": ["frozen-version-A"]}]})
        self.assertEqual(passages, original)

    def test_unknown_duplicate_or_augmented_selections_fail_and_legacy_is_not_repaired(self):
        passages = [{"id": "frozen", "text": "ornek payment evidence."}]
        for value in ({"quote_ids": ["Q2"]}, {"quote_ids": ["Q1", "Q1"]}, {"quote_ids": "Q1"},
                      {"quote_ids": [True]}, {"quote_ids": ["Q1"], "text": "invented"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_quote_selection(json.dumps(value), passages)
        legacy = json.dumps({"summary": "", "claims": [{"text": "örnek payment evidence.", "evidence_ids": ["frozen"]}]})
        self.assertEqual(resolve_quote_selection(legacy, passages), legacy)
        self.assertNotIn(json.loads(legacy)["claims"][0]["text"], passages[0]["text"])

    def test_long_unbroken_source_is_not_silently_clipped_into_a_quote(self):
        passages = [{"id": "long", "text": "x" * 3000}]
        self.assertEqual(quote_catalog(passages), {})
        self.assertEqual(json.loads(quote_messages("x", passages)[1]["content"])["evidence"][0]["text"], passages[0]["text"])
        with self.assertRaises(ValueError):
            resolve_quote_selection('{"quote_ids":["Q1"]}', passages)
        self.assertEqual(json.loads(resolve_quote_selection('{"quote_ids":[]}', passages))["claims"], [])

    def test_metadata_has_an_independent_lease_when_both_generations_are_busy(self):
        server = relay.Server(("127.0.0.1", 0), "10.1.2.3", "synthetic-model")
        self.assertTrue(server.upstream_slots.acquire(False))
        self.assertTrue(server.upstream_slots.acquire(False))
        value = handler()
        value.server = server
        value.command, value.path = "GET", "/v1/models"

        class Response:
            status, sent = 200, False

            def getheader(self, name, default=None):
                return default

            def read1(self, size):
                if self.sent:
                    return b""
                self.sent = True
                return b'{"data":[]}'

        connection = SimpleNamespace(request=lambda *a, **k: None, getresponse=Response, close=lambda: None)
        try:
            with patch.object(relay.http.client, "HTTPConnection", return_value=connection):
                value.forward(None)
            self.assertEqual(value.results[0][0], 200)
            self.assertFalse(server.upstream_slots.acquire(False))
            self.assertTrue(server.metadata_slots.acquire(False))
            server.metadata_slots.release()
        finally:
            server.upstream_slots.release()
            server.upstream_slots.release()
            server.server_close()

    def test_transport_categories_never_export_error_messages(self):
        for error, expected in ((PermissionError(errno.EPERM, "sensitive"), "provider_network_denied"),
                                (ConnectionResetError(errno.ECONNRESET, "sensitive"), "provider_connection_reset"),
                                (OSError(errno.EMFILE, "sensitive"), "provider_transport_resource_exhausted"),
                                (relay.http.client.RemoteDisconnected("sensitive"), "provider_connection_closed")):
            value = handler()
            with patch.object(relay.http.client, "HTTPConnection", side_effect=error):
                value.forward(b"{}")
            self.assertEqual(value.results, [(502, {"error": "Local provider request could not be admitted", "code": expected})])
            self.assertNotIn("sensitive", json.dumps(value.results))
            self.assertTrue(value.server.upstream_slots.acquire(False))
            self.assertTrue(value.server.upstream_slots.acquire(False))

    def test_queue_expiry_never_connects_or_releases_unowned_lease(self):
        slots = SimpleNamespace(acquire=lambda **kwargs: False, release=lambda: self.fail("Unowned release"))
        value = handler(slots)
        with patch.object(relay.http.client, "HTTPConnection", side_effect=AssertionError("No dispatch")):
            value.forward(b"{}")
        self.assertEqual(value.results[0][0], 503)
        self.assertEqual(value.results[0][1]["code"], "provider_upstream_timeout")

    def test_socket_deadline_shrinks_and_closed_response_socket_is_bounded(self):
        observed = []
        sock = SimpleNamespace(settimeout=observed.append)
        connection = SimpleNamespace(sock=None)
        response = SimpleNamespace(fp=SimpleNamespace(raw=SimpleNamespace(_sock=sock)))
        with patch.object(relay.time, "monotonic", side_effect=[1, 3, 5]):
            relay.Handler.remaining_timeout(connection, 5, response)
            relay.Handler.remaining_timeout(connection, 5, response)
            with self.assertRaises(TimeoutError):
                relay.Handler.remaining_timeout(connection, 5, response)
        self.assertEqual(observed, [4, 2])

    def test_tcp_connect_cannot_restart_the_tls_deadline(self):
        calls = []
        raw = SimpleNamespace(settimeout=lambda value: calls.append(("timeout", value)),
                              connect=lambda endpoint: calls.append(("connect",)), close=lambda: calls.append(("close",)))
        context = SimpleNamespace(check_hostname=True, verify_mode=relay.ssl.CERT_REQUIRED,
                                  wrap_socket=lambda *args, **kwargs: self.fail("TLS after deadline"))
        with patch.object(relay.ssl, "create_default_context", return_value=context), patch.object(relay.socket, "socket", return_value=raw):
            connection = relay.PinnedHTTPSConnection(relay.Upstream("1.1.1.1", "fixture.example.com"), 3)
            connection.deadline = 3
            with patch.object(relay.time, "monotonic", side_effect=[0, 4]), self.assertRaises(TimeoutError):
                connection.connect()
        self.assertEqual(calls, [("timeout", 3), ("connect",), ("close",)])

    def test_health_has_headroom_while_five_metadata_lifetimes_overlap(self):
        release, two_closing = threading.Event(), threading.Event()
        lock = threading.Lock()
        counts = {"active": 0, "peak": 0, "closing": 0}

        class Response:
            status = 200
            sent = False

            def getheader(self, name, default=None):
                return default

            def read1(self, size):
                if self.sent:
                    return b""
                self.sent = True
                return json.dumps({"data": [{"id": "synthetic-model", "backend": "ollama_http",
                    "format": "ollama_http", "request_key_source": "local-inference", "max_model_len": 8192}]}).encode()

        class Connection:
            def __init__(self, *args, **kwargs):
                pass

            def request(self, *args, **kwargs):
                with lock:
                    counts["active"] += 1
                    counts["peak"] = max(counts["peak"], counts["active"])

            def getresponse(self):
                return Response()

            def close(self):
                with lock:
                    counts["closing"] += 1
                    if counts["closing"] == 2:
                        two_closing.set()
                release.wait(2)
                with lock:
                    counts["active"] -= 1

        server = relay.Server(("127.0.0.1", 0), "10.1.2.3", "synthetic-model")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(relay.http.client, "HTTPConnection", Connection), ThreadPoolExecutor(5) as pool:
                def metadata(_):
                    with httpx.Client(trust_env=False, timeout=4) as client:
                        return client.get(f"http://127.0.0.1:{server.server_port}/v1/models",
                                          headers={"Authorization": "Bearer fixture-only"}).status_code
                futures = [pool.submit(metadata, i) for i in range(5)]
                try:
                    self.assertTrue(two_closing.wait(1))
                    with httpx.Client(trust_env=False, timeout=1) as client:
                        self.assertEqual(client.get(f"http://127.0.0.1:{server.server_port}/health").status_code, 200)
                finally:
                    release.set()
                self.assertEqual([f.result(4) for f in futures], [200] * 5)
            self.assertEqual(counts["peak"], 2)
            self.assertEqual(counts["active"], 0)
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_fixture_profile_is_explicit_local_and_ignores_inherited_credentials(self):
        environment = {"LA_LOAD_DRILL": LOAD_MARKER, "LA_LOAD_REAL_PROVIDER": MARKER,
            "LA_LOAD_CONTROL_TOKEN": "x" * 32, "LA_ENCRYPTION_KEY": "fixture",
            "LA_DATABASE_URL": "postgresql+psycopg://lawyer:fixture@postgres:5432/lawyer_load_drill",
            "LLM_PROVIDER_API_KEY": "inherited-must-not-be-used"}
        profile = {"provider_base_url": "http://172.30.240.2:8083/v1", "provider_model": "synthetic-model",
            "provider_context_limit": 8192, "provider_allow_plain_http": True, "provider_identity_verified": True,
            "provider_cloud_fallback_disabled": True, "provider_tenant_id": "lawyer-assistant-v1", "provider_org_id": "org-lawyer",
            "provider_key_id": "lawyer-assistant-v1-primary", "provider_tunnel_url": "", "provider_tunnel_approved": False,
            "provider_tunnel_approved_host": ""}
        with patch.dict(os.environ, environment, clear=True):
            settings, _ = real_settings(profile, "explicit-fixture-key")
            self.assertEqual(settings.provider_api_key, "explicit-fixture-key")
            for invalid in ({**profile, "provider_tenant_id": "other"}, {**profile, "provider_identity_verified": "false"},
                            {**profile, "provider_base_url": "https://public.example/v1"}, {**profile, "database_url": "private"}):
                with self.assertRaises(ValueError):
                    real_settings(invalid, "explicit-fixture-key")
            with patch.dict(os.environ, {"LA_LOAD_REAL_PROVIDER": ""}), self.assertRaises(ValueError):
                real_settings(profile, "explicit-fixture-key")

    def test_real_job_definition_mounts_key_only_in_disposable_api_and_publishes_nothing(self):
        value = definition({"api": "sha256:api", "postgres": "sha256:postgres"}, "fixture", "password", "t" * 32,
                           "198.19.0.0/28", Path("/protected/profile"), Path("/protected/key"), "fixture-provider")
        self.assertEqual(set(value["services"]), {"api", "postgres", "driver"})
        self.assertEqual(value["networks"]["provider"], {"external": True, "name": "fixture-provider"})
        api = value["services"]["api"]
        self.assertEqual(api["networks"]["provider"], {"ipv4_address": "172.30.240.14"})
        self.assertTrue(all(v["read_only"] for v in api["volumes"] if isinstance(v, dict)))
        self.assertNotIn("volumes", value["services"]["driver"])
        for name, service in value["services"].items():
            self.assertNotIn("ports", service)
            self.assertNotIn("env_file", service)
            self.assertNotIn("LLM_PROVIDER_API_KEY", service["environment"])
            if name != "api":
                self.assertNotIn("provider", service["networks"])


if __name__ == "__main__":
    unittest.main()
