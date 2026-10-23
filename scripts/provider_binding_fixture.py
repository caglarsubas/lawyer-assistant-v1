"""In-process hypothetical signer, with ephemeral keys and synthetic identities.

This is not the deployed engine protocol. No private keys are serialized, stored
or provisioned. The collector's sole HTTP method is exercised via MockTransport.
"""

import base64
import json

import httpx
from bundle_adapter_fixture import settings
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from provider_identity_binding import CONTRACT, BoundResponse, canonical, collect_identity, sha

from app.provider import Provider

NOW = 1800000000
IDENTITY_NONCE, RESPONSE_NONCE = "a" * 32, "b" * 32


def provider():
    return Provider(settings(provider_tenant_id="synthetic-tenant", provider_org_id="synthetic-org", provider_key_id="synthetic-key-id"))


def pin_for(p):
    return {"model_id": p.settings.provider_model, "model_digest_sha256": sha("invented-manifest-digest"), "backend": "ollama_http",
        "format": "ollama_http", "model_context_units": 32768, "application_context_units": 8192,
        "tenant_id": "synthetic-tenant", "organization_id": "synthetic-org", "key_id": "synthetic-key-id",
        "transport_mode": "native_private", "route_sha256": sha(canonical({"mode": "native_private", "base": p._base()})),
        "cloud_fallback_disabled": True}


class SignedFixture:
    def __init__(self, mode="signed_valid"):
        self.mode, self.key, self.requests = mode, Ed25519PrivateKey.generate(), []
        self.provider = provider()
        self.pin = pin_for(self.provider)

    def sign(self, claims):
        return {"claims": claims, "signature": base64.b64encode(self.key.sign((CONTRACT + "\0" + canonical(claims)).encode())).decode()}

    def metadata(self, nonce=IDENTITY_NONCE):
        payload = {"data": [{"id": self.pin["model_id"], "backend": "ollama_http", "format": "ollama_http",
                             "request_key_source": "local-inference", "max_model_len": 32768}]}
        if self.mode != "legacy_metadata":
            pin = {**self.pin, **({"tenant_id": "foreign-tenant"} if self.mode == "foreign_tenant" else {})}
            payload["identity_attestation"] = self.sign({"contract": CONTRACT, "kind": "identity", "nonce": nonce,
                "pin": pin, "issued_at": NOW, "expires_at": NOW + 250})
        return payload

    def serve(self, request):
        self.requests.append(request)
        if request.method != "GET" or request.url.path != "/v1/models":
            raise AssertionError("Collector attempted nonmetadata HTTP")
        return httpx.Response(200, json=self.metadata(request.headers["X-Lawyer-Identity-Challenge"]))

    def client(self, **kwargs):
        return httpx.Client(transport=httpx.MockTransport(self.serve), **kwargs)

    def collect(self, **kwargs):
        return collect_identity(self.provider, trusted_key=self.key.public_key(), client_factory=self.client,
                                now=NOW, nonce=IDENTITY_NONCE, **kwargs)

    def request(self):
        return canonical({"model": self.pin["model_id"], "messages": [{"role": "user", "content": "Invented selection, no private evidence."}],
                          "stream": False, "max_completion_tokens": 1000}).encode()

    def pending(self, identity=None):
        return BoundResponse(self.request(), identity or self.collect(), trusted_key=self.key.public_key(), expected_pin=self.pin,
                             nonce=RESPONSE_NONCE, now=NOW)

    def response(self, pending):
        content = '{"bundle_ids":[]}' if self.mode == "signed_empty" else '{"bundle_ids":["W1"]}'
        completion = {"id": "synthetic-completion", "model": self.pin["model_id"], "request_key_source": "local-inference",
                      "choices": [{"finish_reason": "stop", "message": {"content": content}}],
                      "usage": {"completion_tokens": 12, "total_tokens": 500}}
        if self.mode == "legacy_completion":
            return canonical(completion).encode()
        claims = {**pending.expectation(), "response_payload_sha256": sha(canonical(completion))}
        if self.mode == "wrong_nonce":
            claims["nonce"] = "c" * 32
        if self.mode == "wrong_request":
            claims["request_sha256"] = sha("another request")
        envelope = {"completion": completion, "provider_binding": self.sign(claims)}
        if self.mode == "altered_payload":
            completion["choices"][0]["message"]["content"] = '{"bundle_ids":["W999"]}'
        return json.dumps(envelope, ensure_ascii=False).encode()
