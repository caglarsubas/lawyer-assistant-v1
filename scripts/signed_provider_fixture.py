"""Ephemeral provider-side signing with independent synthetic adapter receipts."""

from dataclasses import replace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from provider_binding_fixture import pin_for, provider
from signed_provider_contract import (
    ExecutionReceipt,
    IdentityChallenge,
    Issuer,
    ResponseChallenge,
    decode,
    encode,
    sha,
)
from signed_provider_handoff import metadata_headers, preserve_envelope

NOW = 1800000000
I_NONCE, R_NONCE = "1" * 32, "2" * 32
CREDENTIAL = "SYNTHETIC-ONLY-NO-PRIVATE-KEY"
SENTINEL = "SYNTHETIC-PRIVATE-CONTENT-MUST-NOT-ESCAPE"


class Fixture:
    def __init__(self, mode="valid"):
        self.mode, self.key, self.pin = mode, Ed25519PrivateKey.generate(), pin_for(provider())
        self.adapter_calls = []
        self.issuer = Issuer(
            self.key,
            "synthetic-issuer-v2",
            resolve_identity=self.resolve_identity,
            resolve_execution=self.resolve_execution,
        )
        self.request = encode(
            {
                "model": self.pin["model_id"],
                "messages": [{"role": "user", "content": "Invented protocol input."}],
                "stream": False,
                "max_completion_tokens": 100,
            }
        )
        self.response = encode(
            {
                "model": self.pin["model_id"],
                "request_key_source": "local-inference",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "Invented response."},
                    }
                ],
                "usage": {"prompt_tokens": 40, "completion_tokens": 10, "total_tokens": 50},
            }
        )

    def resolve_identity(self, credential, model, route):
        self.adapter_calls.append("authenticated_runtime")
        if credential != CREDENTIAL or model != self.pin["model_id"] or route != self.pin["route_sha256"]:
            raise ValueError(SENTINEL)
        return dict(self.pin, **({"tenant_id": "synthetic-foreign"} if self.mode == "foreign_tenant" else {}))

    def resolve_execution(self, handle):
        self.adapter_calls.append("completed_execution")
        if handle != "synthetic-handle" or self.mode == "execution_missing":
            raise ValueError(SENTINEL)
        receipt = ExecutionReceipt(
            self.pin,
            sha(self.request),
            sha(self.response),
            True,
            False,
            R_NONCE,
            self.pending.expectation()["identity_sha256"],
            NOW,
            NOW + 1,
        )
        changes = {
            "execution_digest": {"runtime_pin": dict(self.pin, model_digest_sha256="f" * 64)},
            "execution_nonce": {"response_nonce": "9" * 32},
            "execution_old": {"started_at": NOW - 100},
        }
        return replace(receipt, **changes.get(self.mode, {}))

    def identity(self):
        client = IdentityChallenge(
            Ed25519PrivateKey.generate().public_key()
            if self.mode == "unknown_trust"
            else self.key.public_key(),
            "synthetic-issuer-v2",
            self.pin,
            challenge=I_NONCE,
        )
        headers = [("Authorization", "Bearer " + CREDENTIAL), ("X-Lawyer-Identity-Challenge", client.nonce)]
        if self.mode == "duplicate_challenge":
            headers.append(("x-lawyer-identity-challenge", client.nonce))
        forwarded = metadata_headers(headers)
        raw = self.issuer.issue_identity(
            CREDENTIAL,
            self.pin["model_id"],
            self.pin["route_sha256"],
            "3" * 32 if self.mode == "identity_nonce" else forwarded["X-Lawyer-Identity-Challenge"],
            now=NOW,
        )
        return client.consume(
            preserve_envelope(raw, "identity"), now=NOW + 120 if self.mode == "expired" else NOW
        )

    def bind(self, proof):
        self.pending = ResponseChallenge(
            self.request,
            proof,
            trusted_key=self.key.public_key(),
            issuer_key_id="synthetic-issuer-v2",
            expected_pin=self.pin,
            identity_nonce=I_NONCE,
            now=NOW,
            challenge=R_NONCE,
        )
        body = self.response
        if self.mode == "fallback":
            value = decode(body)
            value["fallback_reason"] = "synthetic"
            body = encode(value)
        if self.mode == "nonfinite":
            body = b'{"n":1e999}'
        raw = self.issuer.bind_response(
            CREDENTIAL,
            self.request + b" " if self.mode == "request_tamper" else self.request,
            body,
            self.pending.expectation(),
            proof,
            "synthetic-handle",
            now=NOW + 1,
        )
        if self.mode == "wire_tamper":
            import base64

            value = decode(raw)
            value["response_base64"] = base64.b64encode(body + b" ").decode()
            raw = encode(value)
        return self.pending.consume(preserve_envelope(raw, "completion"), now=NOW + 1)
