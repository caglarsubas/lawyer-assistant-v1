"""GET-only collection and prospective signed response verification, never inference.

Current engine/relay contracts do not emit these attestations. Unsigned observations
remain useful diagnostics but cannot produce an admitted runtime pin. Trusted
public keys must be provisioned independently of response/configuration content.
"""

import base64
import hashlib
import json
import re
import secrets
import time
from threading import Lock

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.evidence_prompt import canonical
from app.provider import Provider

RECIPE = "disposable-readonly-provider-identity-v1"
CONTRACT = "lawyer-provider-binding-v1"
MAX_METADATA, MAX_BOUND_RESPONSE = 1024 * 1024, 16384


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


PIN_FIELDS = {"model_id", "model_digest_sha256", "backend", "format", "model_context_units", "application_context_units",
              "tenant_id", "organization_id", "key_id", "transport_mode", "route_sha256", "cloud_fallback_disabled"}


def validate_pin(pin, limit):
    if not isinstance(pin, dict) or set(pin) != PIN_FIELDS:
        raise ValueError("Complete immutable runtime pin required")
    for k in ("model_id", "tenant_id", "organization_id", "key_id"):
        if not isinstance(pin[k], str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", pin[k]):
            raise ValueError("Invalid runtime identity label")
    if (not digest(pin["model_digest_sha256"]) or not digest(pin["route_sha256"])
            or pin["backend"] not in {"llama_cpp", "ollama_http", "mlx"}
            or pin["format"] != {"llama_cpp": "gguf", "ollama_http": "ollama_http", "mlx": "mlx"}.get(pin["backend"])
            or pin["transport_mode"] not in {"native_private", "approved_laptop_tunnel"}
            or pin["cloud_fallback_disabled"] is not True
            or type(pin["model_context_units"]) is not int or not limit <= pin["model_context_units"] <= 10**7
            or type(pin["application_context_units"]) is not int or pin["application_context_units"] != limit):
        raise ValueError("Unqualified model, route or context identity")
    return json.loads(canonical(pin))



def decode(raw, maximum):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError("Duplicate provider field")
            out[k] = v
        return out
    if not isinstance(raw, bytes) or not 0 < len(raw) <= maximum:
        raise ValueError("Unbounded provider identity/response body")
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid JSON number")))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("Invalid bounded provider JSON") from None


def signed_claims(proof, key):
    if (type(key) is not Ed25519PublicKey and not isinstance(key, Ed25519PublicKey)) or not isinstance(proof, dict) or set(proof) != {"claims", "signature"}:
        raise ValueError("Independent trusted key and exact provider proof required")
    try:
        signature = base64.b64decode(proof["signature"], validate=True)
        if len(signature) != 64 or not isinstance(proof["claims"], dict):
            raise ValueError("Malformed provider proof")
        key.verify(signature, (CONTRACT + "\0" + canonical(proof["claims"])).encode())
    except (InvalidSignature, ValueError, TypeError):
        raise ValueError("Provider proof signature rejected") from None
    return json.loads(canonical(proof["claims"]))


def verify_identity(proof, key, *, nonce, expected_model, expected_identity, route_sha256, context_limit, now):
    c = signed_claims(proof, key)
    if (set(c) != {"contract", "kind", "nonce", "pin", "issued_at", "expires_at"} or c["contract"] != CONTRACT
            or c["kind"] != "identity" or c["nonce"] != nonce
            or type(c["issued_at"]) is not int or type(c["expires_at"]) is not int
            or not 0 < c["expires_at"] - c["issued_at"] <= 300 or c["issued_at"] > now + 5 or c["expires_at"] <= now):
        raise ValueError("Stale or unrelated provider identity proof")
    pin = validate_pin(c["pin"], context_limit)
    if (pin["model_id"] != expected_model or pin["route_sha256"] != route_sha256
            or any(pin[k] != expected_identity[k] for k in ("tenant_id", "organization_id", "key_id"))):
        raise ValueError("Provider identity proof differs from expected caller/route")
    return {"claims": c, "identity_sha256": sha(canonical(c)), "pin": pin, "proof": json.loads(canonical(proof))}


def provider_state(provider):
    # Keep settings/credential values only in memory; never publish this tuple.
    s = provider.settings
    return tuple(getattr(s, k, None) for k in ("provider_base_url", "provider_api_key", "provider_model", "provider_context_limit",
        "provider_identity_verified", "provider_cloud_fallback_disabled", "provider_allow_plain_http", "provider_tunnel_url",
        "provider_tunnel_approved", "provider_tunnel_approved_host", "provider_tenant_id", "provider_org_id", "provider_key_id"))


def read_models(provider, *, challenge, client_factory=httpx.Client):
    if not isinstance(provider, Provider) or not isinstance(challenge, str) or len(challenge) != 32 or any(c not in "0123456789abcdef" for c in challenge):
        raise ValueError("Explicit provider and bounded identity challenge required")
    if (type(provider.settings.provider_context_limit) is not int or not 0 < provider.settings.provider_context_limit <= 8192
            or provider.configuration_issues()):
        raise ValueError("Provider configuration cannot admit read-only metadata")
    provider.validate_origin()
    started, body = time.monotonic(), bytearray()
    try:
        with client_factory(timeout=httpx.Timeout(5, connect=3), follow_redirects=False, trust_env=False) as client:
            with client.stream("GET", provider._base() + "/models", headers={"Authorization": "Bearer " + provider.settings.provider_api_key,
                "Accept-Encoding": "identity", "X-Lawyer-Identity-Challenge": challenge, **provider._route_headers()}) as response:
                if response.status_code != 200 or response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise ValueError("Provider metadata unavailable or compressed")
                for chunk in response.iter_bytes():
                    if time.monotonic() - started >= 10 or len(body) + len(chunk) > MAX_METADATA:
                        raise ValueError("Provider metadata exceeded bounds")
                    body.extend(chunk)
        if time.monotonic() - started >= 10:
            raise ValueError("Provider metadata deadline exceeded")
        return bytes(body)
    except httpx.HTTPError:
        raise ValueError("Read-only provider metadata unavailable") from None


def collect_identity(provider, *, trusted_key=None, expected_pin=None, client_factory=httpx.Client, now=None, nonce=None):
    """Exactly one GET, no retry/POST; output cannot authorize native execution.

    Configured identity labels are not authenticated identity. Only a valid
    prospective signed proof yields a qualified pin; deployed legacy metadata
    remains unqualified. New proof fields require provider and relay support.
    """
    stamp = int(time.time()) if now is None else now
    if type(stamp) is not int or stamp < 0:
        raise ValueError("Valid observation time required")
    challenge = secrets.token_hex(16) if nonce is None else nonce
    before = provider_state(provider)
    raw = read_models(provider, challenge=challenge, client_factory=client_factory)
    payload = decode(raw, MAX_METADATA)
    provider._verify_transport(payload)
    models = payload.get("data")
    if not isinstance(models, list) or len(models) > 4096:
        raise ValueError("Invalid model metadata inventory")
    selected = [m for m in models if isinstance(m, dict) and m.get("id") == provider.settings.provider_model]
    if len(selected) != 1:
        raise ValueError("Missing or ambiguous configured model")
    model = selected[0]
    if (model.get("request_key_source") != "local-inference" or model.get("backend") not in {"llama_cpp", "ollama_http", "mlx"}
            or model.get("format") != {"llama_cpp": "gguf", "ollama_http": "ollama_http", "mlx": "mlx"}.get(model.get("backend"))
            or type(model.get("max_model_len")) is not int or not 0 < provider.settings.provider_context_limit <= model["max_model_len"]):
        raise ValueError("Model metadata cannot establish local context capability")
    route = provider._tunnel_contract()
    route_sha = route["route_sha256"] if route else sha(canonical({"mode": "native_private", "base": provider._base()}))
    expected = {"tenant_id": getattr(provider.settings, "provider_tenant_id", None),
                "organization_id": getattr(provider.settings, "provider_org_id", None), "key_id": getattr(provider.settings, "provider_key_id", None)}
    proof, verified, issues = payload.get("identity_attestation"), None, []
    if proof is None:
        issues.append("signed_provider_identity_unavailable")
    elif trusted_key is None:
        issues.append("independent_provider_trust_key_unavailable")
    else:
        try:
            verified = verify_identity(proof, trusted_key, nonce=challenge, expected_model=model["id"], expected_identity=expected,
                route_sha256=route_sha, context_limit=provider.settings.provider_context_limit, now=stamp)
            pin = verified["pin"]
            if (pin["backend"] != model["backend"] or pin["format"] != model["format"] or pin["model_context_units"] != model["max_model_len"]
                    or pin["transport_mode"] != ("approved_laptop_tunnel" if route else "native_private")
                    or (expected_pin is not None and canonical(pin) != canonical(expected_pin))):
                raise ValueError("Signed identity conflicts with current metadata or prior pin")
        except (ValueError, TypeError, KeyError, RecursionError):
            verified = None
            issues.append("provider_identity_proof_rejected")
    if provider_state(provider) != before:
        raise ValueError("Provider configuration changed during identity collection")
    return {"recipe": RECIPE, "observation": {"metadata_sha256": sha(raw), "model": {k: model[k] for k in ("id", "backend", "format", "max_model_len", "request_key_source")},
            "transport_mode": "approved_laptop_tunnel" if route else "native_private", "route_sha256": route_sha,
            "configured_identity_labels_not_server_attestation": expected},
        "issues": issues, "verified_identity": verified, "qualified_pin": verified["pin"] if verified else None,
        "native_execution_authorization": False, "production_activation": False, "metadata_GET_requests": 1, "completion_POST_requests": 0}


def read_ollama_manifest(model_id, *, client_factory=httpx.Client):
    """Independent fixed-loopback GET. Manifest identity is not served-weight proof."""
    if not isinstance(model_id, str) or not 1 <= len(model_id) <= 128:
        raise ValueError("Bounded exact model name required")
    raw = bytearray()
    started = time.monotonic()
    with client_factory(timeout=httpx.Timeout(5, connect=3), follow_redirects=False, trust_env=False) as client:
        with client.stream("GET", "http://127.0.0.1:11434/api/tags", headers={"Accept-Encoding": "identity"}) as response:
            if response.status_code != 200 or response.headers.get("content-encoding", "identity").lower() != "identity":
                raise ValueError("Local manifest metadata unavailable")
            for chunk in response.iter_bytes():
                if len(raw) + len(chunk) > MAX_METADATA or time.monotonic() - started >= 10:
                    raise ValueError("Local manifest metadata exceeded bounds")
                raw.extend(chunk)
    models = decode(bytes(raw), MAX_METADATA).get("models")
    if not isinstance(models, list) or len(models) > 4096:
        raise ValueError("Invalid local manifest inventory")
    matches = [m for m in models if isinstance(m, dict) and m.get("name") == model_id]
    if len(matches) != 1:
        raise ValueError("Exact local model manifest unavailable")
    m = matches[0]
    value = m.get("digest", "")
    if not isinstance(value, str):
        raise ValueError("Invalid local manifest digest")
    if value.startswith("sha256:"):
        value = value[7:]
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value) or type(m.get("size")) is not int or m["size"] <= 0 or model_id.endswith(":cloud"):
        raise ValueError("Local immutable manifest unavailable")
    return {"source": "independent_loopback_ollama_manifest", "model_id": model_id, "manifest_sha256": value,
            "metadata_sha256": sha(bytes(raw)), "proves_selected_engine_route_or_executed_weights": False}


class BoundResponse:
    """One-shot prospective response verification, with no sending or persistence.

    The caller must carry real independently verified identity from collection.
    Durable campaign admission remains a separate mandatory execution boundary.
    """

    def __init__(self, request_bytes, identity_record, *, trusted_key, expected_pin, nonce=None, now=None):
        request = decode(request_bytes, 256 * 1024)
        verified = identity_record.get("verified_identity")
        if not verified or identity_record.get("qualified_pin") != verified.get("pin"):
            raise ValueError("A verified provider identity is required")
        stamp = int(time.time()) if now is None else now
        if type(stamp) is not int or stamp < 0:
            raise ValueError("Valid response binding time required")
        pin = validate_pin(expected_pin, expected_pin["application_context_units"])
        checked = verify_identity(verified.get("proof"), trusted_key, nonce=verified["claims"]["nonce"],
            expected_model=pin["model_id"], expected_identity=pin, route_sha256=pin["route_sha256"],
            context_limit=pin["application_context_units"], now=stamp)
        if canonical(checked) != canonical(verified) or canonical(checked["pin"]) != canonical(pin):
            raise ValueError("Identity certificate/pin changed before request binding")
        challenge = secrets.token_hex(16) if nonce is None else nonce
        if not isinstance(challenge, str) or len(challenge) != 32 or any(c not in "0123456789abcdef" for c in challenge):
            raise ValueError("Bounded fresh response nonce required")
        maximum = request.get("max_completion_tokens")
        if type(maximum) is not int or not 0 < maximum <= 1000:
            raise ValueError("Bounded packet completion budget required")
        if request.get("model") != pin["model_id"] or request.get("stream") is not False or verified["claims"]["expires_at"] <= stamp:
            raise ValueError("Request differs from current verified provider identity")
        self._claims = canonical({"contract": CONTRACT, "kind": "completion", "request_sha256": sha(request_bytes),
            "nonce": challenge, "identity_sha256": verified["identity_sha256"], "pin_sha256": sha(canonical(pin)),
            "expires_at": min(stamp + 120, verified["claims"]["expires_at"])})
        self._pin, self._key, self._maximum, self._lock, self._consumed = pin, trusted_key, maximum, Lock(), False

    def expectation(self):
        return json.loads(self._claims)

    def consume(self, raw, *, now=None):
        with self._lock:
            if self._consumed:
                raise ValueError("Response expectation already consumed; retries prohibited")
            self._consumed = True
        expected = json.loads(self._claims)
        stamp = int(time.time()) if now is None else now
        if type(stamp) is not int or stamp < 0:
            raise ValueError("Valid response verification time required")
        envelope = decode(raw, MAX_BOUND_RESPONSE)
        if not isinstance(envelope, dict) or set(envelope) != {"completion", "provider_binding"} or stamp >= expected["expires_at"]:
            raise ValueError("Unsigned, unbounded or stale provider response")
        claims = signed_claims(envelope["provider_binding"], self._key)
        completion = envelope["completion"]
        if claims != {**expected, "response_payload_sha256": sha(canonical(completion))}:
            raise ValueError("Provider response proof differs from the exact request/identity/payload")
        if (not isinstance(completion, dict) or len(canonical(completion).encode()) > 8192 or completion.get("model") != self._pin["model_id"]
                or completion.get("request_key_source") != "local-inference"
                or any(completion.get(k) for k in ("fallback_from_model", "fallback_reason", "substituted_from_model", "substitution_reason"))):
            raise ValueError("Provider served-model/fallback binding differs")
        choices = completion.get("choices")
        if (not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict) or choices[0].get("finish_reason") != "stop"
                or not isinstance(choices[0].get("message"), dict) or choices[0]["message"].get("tool_calls")
                or not isinstance(choices[0]["message"].get("content"), str) or not choices[0]["message"]["content"].strip()):
            raise ValueError("Bound completion is incomplete or unsupported")
        usage = completion.get("usage")
        if usage is not None:
            if not isinstance(usage, dict):
                raise ValueError("Invalid bound usage")
            for name, cap in (("completion_tokens", self._maximum), ("total_tokens", self._pin["application_context_units"])):
                if name in usage and (type(usage[name]) is not int or not 0 <= usage[name] <= cap):
                    raise ValueError("Bound response exceeds token budget")
        return {"content": choices[0]["message"]["content"], "binding_receipt": {**expected,
                "response_payload_sha256": sha(canonical(completion)), "raw_response_sha256": sha(raw)},
                "native_or_legal_qualification": False, "production_activation": False}
