import base64
import json
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path[:0] = [
    str(Path(__file__).resolve().parents[1] / "scripts"),
    str(Path(__file__).resolve().parents[1] / "backend"),
]
from evaluate_signed_provider import evaluate  # noqa: E402
from signed_provider_contract import (  # noqa: E402
    IdentityChallenge,
    Issuer,
    ResponseChallenge,
    completion,
    decode,
    encode,
    identity,
    request,
    sha,
    signed,
)
from signed_provider_fixture import CREDENTIAL, I_NONCE, NOW, R_NONCE, SENTINEL, Fixture  # noqa: E402
from signed_provider_handoff import metadata_headers, preserve_envelope  # noqa: E402


class Contracts(unittest.TestCase):
    def prepare(self):
        f = Fixture()
        proof = f.identity()
        f.pending = ResponseChallenge(
            f.request,
            proof,
            trusted_key=f.key.public_key(),
            issuer_key_id="synthetic-issuer-v2",
            expected_pin=f.pin,
            identity_nonce=I_NONCE,
            now=NOW,
            challenge=R_NONCE,
        )
        return f, proof

    def envelope(self, f, proof, **changes):
        return f.issuer.bind_response(
            changes.get("credential", CREDENTIAL),
            changes.get("request_bytes", f.request),
            changes.get("response_bytes", f.response),
            f.pending.expectation(),
            proof,
            "synthetic-handle",
            now=changes.get("now", NOW + 1),
        )

    def test_frozen_fourteen_cases_without_network(self):
        with patch("socket.socket", side_effect=AssertionError("Real socket prohibited")):
            report = evaluate()
            self.assertEqual(report, evaluate())
        self.assertEqual(
            report["summary"], {"cases": 14, "expected_results": 14, "bound_synthetic_responses": 1}
        )
        self.assertEqual(report["real_network_calls"], 0)
        self.assertEqual(report["persisted_or_provisioned_keys"], 0)

    def test_provider_relay_consumer_binds_exact_wire_bytes(self):
        f, proof = self.prepare()
        raw = self.envelope(f, proof)
        self.assertEqual(preserve_envelope(raw, "completion"), raw)
        result = f.pending.consume(raw, now=NOW + 1)
        self.assertEqual(result["response_sha256"], sha(f.response))
        self.assertEqual(result["request_sha256"], sha(f.request))
        for k in ("native_execution_authorization", "production_activation", "legal_qualification"):
            self.assertIs(result[k], False)
        self.assertNotIn(CREDENTIAL, json.dumps(proof))
        self.assertNotIn(SENTINEL, json.dumps(result))
        self.assertEqual(
            f.adapter_calls, ["authenticated_runtime", "authenticated_runtime", "completed_execution"]
        )

    def test_current_authentication_is_required_again_before_signing(self):
        f, proof = self.prepare()
        with self.assertRaisesRegex(ValueError, "Authenticated runtime unavailable") as error:
            self.envelope(f, proof, credential="SYNTHETIC-REVOKED")
        self.assertNotIn(SENTINEL, str(error.exception))
        self.assertNotIn("completed_execution", f.adapter_calls)

        def unavailable(*args):
            raise RuntimeError(SENTINEL)

        f.issuer.resolve_identity = unavailable
        with self.assertRaisesRegex(ValueError, "Authenticated runtime unavailable"):
            self.envelope(f, proof)

    def test_execution_receipt_cannot_come_from_request_or_stale_history(self):
        changes = [
            {"request_sha256": "0" * 64},
            {"response_sha256": "0" * 64},
            {"response_nonce": "0" * 32},
            {"identity_sha256": "0" * 64},
            {"local_execution": False},
            {"substituted": True},
            {"started_at": NOW - 1},
            {"completed_at": NOW + 10},
            {"started_at": True},
            {"runtime_pin": None},
            {"runtime_pin": dict(Fixture().pin, tenant_id="other")},
            {"runtime_pin": dict(Fixture().pin, model_digest_sha256="0" * 64)},
        ]
        for change in changes:
            f, proof = self.prepare()
            original = f.resolve_execution("synthetic-handle")
            f.issuer.resolve_execution = lambda _: replace(original, **change)
            with self.assertRaises(ValueError):
                self.envelope(f, proof)
        f, proof = self.prepare()
        f.issuer.resolve_execution = lambda _: {"runtime_pin": f.pin}
        with self.assertRaises(ValueError):
            self.envelope(f, proof)

    def test_request_and_response_whitespace_alter_exact_binding(self):
        f, proof = self.prepare()
        with self.assertRaises(ValueError):
            self.envelope(f, proof, request_bytes=f.request + b" ")
        raw = self.envelope(f, proof)
        value = decode(raw)
        value["response_base64"] = base64.b64encode(f.response + b" ").decode()
        with self.assertRaises(ValueError):
            f.pending.consume(encode(value), now=NOW + 1)
        with self.assertRaises(ValueError):
            f.pending.consume(raw, now=NOW + 1)

    def test_one_shot_thread_safety_for_identity_and_response(self):
        f, proof = self.prepare()
        raw = self.envelope(f, proof)

        def consume(_):
            try:
                f.pending.consume(raw, now=NOW + 1)
                return True
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(consume, range(2))), 1)
        challenge = IdentityChallenge(f.key.public_key(), "synthetic-issuer-v2", f.pin, challenge=I_NONCE)
        with self.assertRaises(ValueError):
            challenge.consume(b"{}", now=NOW)
        with self.assertRaises(ValueError):
            challenge.consume(encode(proof), now=NOW)

    def test_independent_trust_nonce_key_identifier_version_and_expiry(self):
        f, proof = self.prepare()
        for change in (
            {"nonce": "9" * 32},
            {"issuer_key_id": "other"},
            {"contract": "lawyer-provider-binding-v1"},
            {"expires_at": NOW},
            {"expires_at": NOW + 301},
            {"issued_at": NOW + 10},
            {"issued_at": True},
            {"extra": True},
        ):
            claims = dict(proof["claims"], **change)
            with self.assertRaises(ValueError):
                identity(
                    signed(f.key, claims),
                    f.key.public_key(),
                    "synthetic-issuer-v2",
                    NOW,
                    expected_nonce=I_NONCE,
                    expected_pin=f.pin,
                )
        with self.assertRaises(ValueError):
            identity(proof, Ed25519PrivateKey.generate().public_key(), "synthetic-issuer-v2", NOW)
        with self.assertRaises(ValueError):
            ResponseChallenge(
                f.request,
                proof,
                trusted_key=f.key.public_key(),
                issuer_key_id="synthetic-issuer-v2",
                expected_pin=dict(f.pin, key_id="other"),
                identity_nonce=I_NONCE,
                now=NOW,
            )
        raw = self.envelope(f, proof)
        with self.assertRaises(ValueError):
            f.pending.consume(raw, now=NOW + 120)

    def test_strict_finite_duplicate_bounded_json(self):
        for raw in (
            b'{"a":1,"a":2}',
            b'{"n":1e999}',
            b'{"n":NaN}',
            b'{"n":Infinity}',
            b"[" * 10000 + b"]" * 10000,
            b"\xff",
            b"",
            b" " * 24577,
        ):
            with self.assertRaises(ValueError):
                decode(raw)
        self.assertEqual(decode(b'{"n":1.25}'), {"n": 1.25})
        with self.assertRaises(ValueError):
            encode({"n": float("inf")})

    def test_relay_headers_and_handoff_are_bounded_opaque_and_narrow(self):
        good = [("Authorization", "Bearer " + CREDENTIAL), ("X-Lawyer-Identity-Challenge", I_NONCE)]
        self.assertEqual(metadata_headers(good)["X-Lawyer-Identity-Challenge"], I_NONCE)
        for headers in (
            good + [good[1]],
            [good[0], ("authorization", "Bearer " + CREDENTIAL)],
            [good[0], ("X-Admin", "1")],
            [good[0], ("X-Lawyer-Identity-Challenge", "bad")],
            [("Authorization", "Bearer bad\r\nsecret"), good[1]],
            [good[0], ("bad",)],
            [],
        ):
            with self.assertRaises(ValueError):
                metadata_headers(headers)
        for raw, kind in ((b"{}", "identity"), (b"{}", "completion"), (b"{}", "admin")):
            with self.assertRaises(ValueError):
                preserve_envelope(raw, kind)
        # Relay does not claim trust: malformed opaque proof still fails at client.
        f, _ = self.prepare()
        client = IdentityChallenge(f.key.public_key(), "synthetic-issuer-v2", f.pin, challenge=I_NONCE)
        raw = encode({"claims": {}, "signature": "synthetic"})
        with self.assertRaises(ValueError):
            client.consume(preserve_envelope(raw, "identity"), now=NOW)

    def test_stop_local_model_and_complete_token_accounting_required(self):
        f = Fixture()
        original = decode(f.response)
        mutations = [
            {"model": "other"},
            {"request_key_source": "external-api-key"},
            {"fallback_reason": "x"},
            {"choices": [{"finish_reason": "length", "message": {"role": "assistant", "content": "x"}}]},
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "x", "tool_calls": []},
                    }
                ]
            },
            {"usage": None},
            {"usage": {"prompt_tokens": 1, "completion_tokens": True, "total_tokens": 2}},
            {"usage": {"prompt_tokens": 1, "completion_tokens": 101, "total_tokens": 102}},
            {"usage": {"prompt_tokens": 40, "completion_tokens": 10, "total_tokens": 51}},
        ]
        for mutation in mutations:
            with self.assertRaises(ValueError):
                completion(encode(dict(original, **mutation)), f.pin, 100)

    def test_request_contract_and_snapshot_copy(self):
        f, proof = self.prepare()
        value = decode(f.request)
        for change in (
            {"stream": True},
            {"max_completion_tokens": True},
            {"max_completion_tokens": 1001},
            {"model": "other"},
            {"messages": []},
            {"tools": []},
        ):
            with self.assertRaises(ValueError):
                request(encode(dict(value, **change)), f.pin)
        expected = f.pending.expectation()
        expected["nonce"] = "f" * 32
        proof["claims"]["pin"]["tenant_id"] = "tampered-after-construction"
        self.assertEqual(f.pending.expectation()["nonce"], R_NONCE)
        # The pending certificate is an independent byte snapshot.
        raw = self.envelope(f, f.pending._identity and decode(f.pending._identity))
        self.assertEqual(f.pending.consume(raw, now=NOW + 1)["response_sha256"], sha(f.response))

    def test_issuer_cannot_start_without_explicit_keys_and_adapters(self):
        f = Fixture()
        for key, first, second in (
            (None, f.resolve_identity, f.resolve_execution),
            (f.key, None, f.resolve_execution),
            (f.key, f.resolve_identity, None),
        ):
            with self.assertRaises(ValueError):
                Issuer(key, "synthetic-issuer-v2", resolve_identity=first, resolve_execution=second)
        with self.assertRaises(ValueError):
            IdentityChallenge(
                f.key.public_key(), "synthetic-issuer-v2", dict(f.pin, application_context_units=True)
            )
