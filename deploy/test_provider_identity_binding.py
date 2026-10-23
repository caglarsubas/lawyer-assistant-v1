"""Read-only HTTP, independent trust, exact response identity and replay guards."""

import json
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from campaign_authority import validate_pin as old_validate_pin  # noqa: E402
from evaluate_provider_binding import evaluate  # noqa: E402
from provider_binding_fixture import IDENTITY_NONCE, NOW, SignedFixture  # noqa: E402
from provider_identity_binding import (  # noqa: E402
    BoundResponse,
    canonical,
    collect_identity,
    decode,
    read_ollama_manifest,
    sha,
    validate_pin,
)

from app.provider import ProviderError  # noqa: E402


class ProviderIdentityBindingContracts(unittest.TestCase):
    def test_frozen_eight_case_report_is_deterministic_and_unqualified(self):
        report = evaluate()
        self.assertEqual(report, evaluate())
        self.assertEqual(report["summary"], {"cases": 8, "expected_outcomes": 8, "bound_synthetic_responses": 2,
            "rejected_synthetic_responses": 4, "unqualified_identities": 2, "mock_GET_requests": 8, "mock_POST_requests": 0})
        self.assertEqual(report["native_inference_calls"], 0)
        self.assertFalse(report["live_identity_or_legal_capacity_qualification"])

    def test_collector_makes_exactly_one_authenticated_bounded_get_and_no_post(self):
        f = SignedFixture()
        record = f.collect()
        self.assertEqual(len(f.requests), 1)
        r = f.requests[0]
        self.assertEqual((r.method, r.url.path, r.content), ("GET", "/v1/models", b""))
        self.assertEqual(r.headers["X-Lawyer-Identity-Challenge"], IDENTITY_NONCE)
        self.assertNotIn(f.provider.settings.provider_api_key, canonical(record))
        self.assertFalse(record["native_execution_authorization"])
        self.assertEqual(record["qualified_pin"], f.pin)

    def test_legacy_metadata_and_missing_independent_trust_cannot_supply_authority_pin(self):
        f = SignedFixture("legacy_metadata")
        record = f.collect()
        self.assertIsNone(record["qualified_pin"])
        self.assertIn("signed_provider_identity_unavailable", record["issues"])
        with self.assertRaises(ValueError):
            f.pending(record)
        f = SignedFixture()
        record = collect_identity(f.provider, client_factory=f.client, now=NOW, nonce=IDENTITY_NONCE)
        self.assertIsNone(record["qualified_pin"])
        self.assertIn("independent_provider_trust_key_unavailable", record["issues"])

    def test_current_full_pin_matches_frozen_guard_schema_without_changing_old_recipe(self):
        f = SignedFixture()
        self.assertEqual(validate_pin(f.pin, 8192), old_validate_pin(f.pin, 8192))
        bad = {**f.pin, "model_digest_sha256": None}
        for check in (validate_pin, old_validate_pin):
            with self.assertRaises(ValueError):
                check(bad, 8192)
        changed = {**f.pin, "model_digest_sha256": sha("different")}
        self.assertIsNone(f.collect(expected_pin=changed)["qualified_pin"])

    def test_signature_from_response_key_or_other_trust_anchor_is_rejected(self):
        f = SignedFixture()
        record = collect_identity(f.provider, trusted_key=Ed25519PrivateKey.generate().public_key(),
                                  client_factory=f.client, now=NOW, nonce=IDENTITY_NONCE)
        self.assertIsNone(record["qualified_pin"])
        pending = f.pending()
        envelope = json.loads(f.response(pending))
        other = SignedFixture()
        envelope["provider_binding"] = other.sign(envelope["provider_binding"]["claims"])
        with self.assertRaises(ValueError):
            pending.consume(canonical(envelope).encode(), now=NOW + 1)

    def test_forged_collection_record_or_pin_is_reverified_before_request_binding(self):
        f = SignedFixture()
        record = f.collect()
        record["verified_identity"]["pin"]["model_digest_sha256"] = sha("forged")
        record["qualified_pin"] = record["verified_identity"]["pin"]
        with self.assertRaises(ValueError):
            f.pending(record)
        record = f.collect()
        record["verified_identity"]["claims"]["nonce"] = "f" * 32
        with self.assertRaises(ValueError):
            f.pending(record)

    def test_nonce_expiry_tenant_and_digest_missing_identity_proofs_fail_closed(self):
        for field, value in (("nonce", "c" * 32), ("expires_at", NOW), ("issued_at", NOW + 100)):
            f = SignedFixture()
            original = f.metadata()
            claims = original["identity_attestation"]["claims"]
            claims[field] = value
            original["identity_attestation"] = f.sign(claims)
            def serve(request):
                return httpx.Response(200, json=original)
            record = collect_identity(f.provider, trusted_key=f.key.public_key(), now=NOW, nonce=IDENTITY_NONCE,
                                      client_factory=lambda **k: httpx.Client(transport=httpx.MockTransport(serve), **k))
            self.assertIsNone(record["qualified_pin"])
        self.assertIsNone(SignedFixture("foreign_tenant").collect()["qualified_pin"])

    def test_model_metadata_route_and_duplicate_aliases_are_not_silently_admitted(self):
        for mode in ("duplicate", "remote", "context", "route"):
            f = SignedFixture()
            data = f.metadata()
            if mode == "duplicate":
                data["data"] *= 2
            elif mode == "remote":
                data["data"][0]["request_key_source"] = "external-api-key"
            elif mode == "context":
                data["data"][0]["max_model_len"] = 4096
            else:
                data["relay_transport"] = {"mode": "unapproved_public"}
            def serve(request):
                return httpx.Response(200, json=data)
            with self.assertRaises((ValueError, ProviderError)):
                collect_identity(f.provider, trusted_key=f.key.public_key(), now=NOW, nonce=IDENTITY_NONCE,
                    client_factory=lambda **k: httpx.Client(transport=httpx.MockTransport(serve), **k))

    def test_http_error_compression_redirect_and_oversize_are_rejected_without_retry(self):
        for response in (httpx.Response(502, content=b"synthetic failure"), httpx.Response(302, headers={"location": "https://example.invalid"}),
                         httpx.Response(200, headers={"content-encoding": "gzip"}, content=b""),
                         httpx.Response(200, content=b" " * (1024 * 1024 + 1))):
            f, calls = SignedFixture(), []
            def serve(request):
                calls.append(request)
                return response
            with self.assertRaises(ValueError):
                collect_identity(f.provider, client_factory=lambda **k: httpx.Client(transport=httpx.MockTransport(serve), **k), now=NOW)
            self.assertEqual(len(calls), 1)

    def test_duplicate_invalid_recursive_json_is_rejected(self):
        for raw in (b'{"data":[],"data":[]}', b'{"a":NaN}', b"[" * 10000 + b"]" * 10000, b"\xff", b""):
            with self.assertRaises(ValueError):
                decode(raw, 1024 * 1024)

    def test_provider_config_change_while_collecting_discards_result(self):
        f = SignedFixture()
        serve = f.serve
        def change(request):
            result = serve(request)
            f.provider.settings.provider_api_key = "SYNTHETIC-CHANGED"
            return result
        with self.assertRaises(ValueError):
            collect_identity(f.provider, client_factory=lambda **k: httpx.Client(transport=httpx.MockTransport(change), **k), now=NOW)

    def test_context_beyond_evaluated_profile_is_blocked_before_get(self):
        for limit in (True, 8193, 0):
            f = SignedFixture()
            f.provider.settings.provider_context_limit = limit
            with self.assertRaises(ValueError):
                f.collect()
            self.assertEqual(f.requests, [])

    def test_exact_request_wire_nonce_identity_and_payload_are_bound(self):
        f = SignedFixture()
        pending = f.pending()
        raw = f.response(pending)
        result = pending.consume(raw, now=NOW + 1)
        self.assertEqual(result["binding_receipt"]["request_sha256"], sha(f.request()))
        self.assertEqual(result["binding_receipt"]["raw_response_sha256"], sha(raw))
        self.assertEqual(result["content"], '{"bundle_ids":["W1"]}')
        self.assertFalse(result["native_or_legal_qualification"])
        spaced = f.request() + b" "
        other = BoundResponse(spaced, f.collect(), trusted_key=f.key.public_key(), expected_pin=f.pin, now=NOW)
        with self.assertRaises(ValueError):
            other.consume(raw, now=NOW + 1)

    def test_wrong_signed_nonce_request_or_tampered_payload_does_not_return_content(self):
        for mode in ("wrong_nonce", "wrong_request", "altered_payload", "legacy_completion"):
            f = SignedFixture(mode)
            pending = f.pending()
            with self.assertRaises(ValueError):
                pending.consume(f.response(pending), now=NOW + 1)

    def test_success_failure_and_concurrent_response_consumption_are_one_shot(self):
        f = SignedFixture()
        pending, raw = f.pending(), None
        raw = f.response(pending)
        def consume(_):
            try:
                pending.consume(raw, now=NOW + 1)
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=5) as pool:
            result = list(pool.map(consume, range(5)))
        self.assertEqual(result.count(True), 1)
        pending = f.pending()
        with self.assertRaises(ValueError):
            pending.consume(b"invalid", now=NOW)
        with self.assertRaises(ValueError):
            pending.consume(f.response(pending), now=NOW)

    def test_unsigned_and_expired_response_never_becomes_bound(self):
        f = SignedFixture()
        pending = f.pending()
        with self.assertRaises(ValueError):
            pending.consume(f.response(pending), now=NOW + 121)
        pending = f.pending()
        raw = canonical({"model": f.pin["model_id"], "choices": []}).encode()
        with self.assertRaises(ValueError):
            pending.consume(raw, now=NOW)

    def test_signed_fallback_wrong_model_incomplete_and_over_budget_response_rejected(self):
        for change in ("fallback", "model", "length", "usage"):
            f = SignedFixture()
            pending = f.pending()
            envelope = json.loads(f.response(pending))
            c = envelope["completion"]
            if change == "fallback":
                c["fallback_reason"] = "synthetic substitution"
            elif change == "model":
                c["model"] = "other"
            elif change == "length":
                c["choices"][0]["finish_reason"] = "length"
            else:
                c["usage"]["completion_tokens"] = 1001
            claims = {**pending.expectation(), "response_payload_sha256": sha(canonical(c))}
            envelope["provider_binding"] = f.sign(claims)
            with self.assertRaises(ValueError):
                pending.consume(canonical(envelope).encode(), now=NOW)

    def test_local_manifest_observation_is_exact_loopback_get_not_execution_proof(self):
        calls = []
        def serve(request):
            calls.append(request)
            return httpx.Response(200, json={"models": [{"name": "synthetic:8b", "digest": "sha256:" + "a" * 64, "size": 42}]})
        result = read_ollama_manifest("synthetic:8b", client_factory=lambda **k: httpx.Client(transport=httpx.MockTransport(serve), **k))
        self.assertEqual(str(calls[0].url), "http://127.0.0.1:11434/api/tags")
        self.assertEqual(calls[0].method, "GET")
        self.assertFalse(result["proves_selected_engine_route_or_executed_weights"])
        self.assertEqual(result["manifest_sha256"], "a" * 64)

    def test_manifest_alias_missing_digest_cloud_or_duplicate_does_not_infer_identity(self):
        for rows in ([{"name": "synthetic:8b", "digest": "", "size": 5}],
                     [{"name": "synthetic", "digest": "a" * 64, "size": 5}],
                     [{"name": "synthetic:8b", "digest": "a" * 64, "size": 0}],
                     [{"name": "synthetic:8b", "digest": "a" * 64, "size": 5}] * 2):
            def serve(request):
                return httpx.Response(200, json={"models": rows})
            with self.assertRaises(ValueError):
                read_ollama_manifest("synthetic:8b", client_factory=lambda **k: httpx.Client(transport=httpx.MockTransport(serve), **k))

    def test_bound_request_rejects_mismatched_pin_model_stream_or_unbounded_completion(self):
        f = SignedFixture()
        record = f.collect()
        for field, value in (("model", "other"), ("stream", True), ("max_completion_tokens", 1001)):
            request = json.loads(f.request())
            request[field] = value
            with self.assertRaises(ValueError):
                BoundResponse(canonical(request).encode(), record, trusted_key=f.key.public_key(), expected_pin=f.pin, now=NOW)
        with self.assertRaises(ValueError):
            BoundResponse(f.request(), record, trusted_key=f.key.public_key(), expected_pin={**f.pin, "model_digest_sha256": sha("different")}, now=NOW)
