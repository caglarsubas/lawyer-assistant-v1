"""Offline v2 issuer/consumer contract. No HTTP, key loading, inference or activation.

Production adapters must supply authenticated/resolved identities and completed
execution receipts independently of request/configuration/metadata content.
"""

import base64
import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from threading import Lock

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from metadata_phase_probe import strict_json
from provider_identity_binding import validate_pin

CONTRACT = "lawyer-provider-binding-v2"
ID_FIELDS = {"contract", "kind", "issuer_key_id", "nonce", "pin", "issued_at", "expires_at"}
EXPECT_FIELDS = {
    "contract",
    "kind",
    "issuer_key_id",
    "nonce",
    "identity_sha256",
    "pin_sha256",
    "request_sha256",
    "issued_at",
    "expires_at",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("Invalid canonical protocol JSON") from None


def decode(raw, cap=24576):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= cap:
        raise ValueError("Protocol body exceeds bounds")
    try:
        return strict_json(raw)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("Invalid strict protocol JSON") from None


def label(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", value):
        raise ValueError("Invalid protocol label")
    return value


def nonce(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ValueError("Invalid protocol challenge")
    return value


def stamp(value):
    if type(value) is not int or not 0 <= value < 2**53:
        raise ValueError("Invalid protocol time")
    return value


def pin(value):
    if (
        not isinstance(value, dict)
        or type(value.get("application_context_units")) is not int
        or not 0 < value["application_context_units"] <= 8192
    ):
        raise ValueError("Invalid bounded runtime pin")
    return validate_pin(value, value["application_context_units"])


def signed(key, claims):
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Explicit signing key required")
    return {
        "claims": claims,
        "signature": base64.b64encode(key.sign(CONTRACT.encode() + b"\0" + encode(claims))).decode(),
    }


def verified(proof, key, issuer_key_id):
    if (
        not isinstance(key, Ed25519PublicKey)
        or not isinstance(proof, dict)
        or set(proof) != {"claims", "signature"}
    ):
        raise ValueError("Independent trust and exact proof required")
    try:
        claims = proof["claims"]
        signature = base64.b64decode(proof["signature"], validate=True)
        if (
            len(signature) != 64
            or not isinstance(claims, dict)
            or claims.get("contract") != CONTRACT
            or claims.get("issuer_key_id") != label(issuer_key_id)
        ):
            raise ValueError("Unexpected signing authority")
        key.verify(signature, CONTRACT.encode() + b"\0" + encode(claims))
        return decode(encode(claims))
    except (InvalidSignature, ValueError, TypeError, KeyError):
        raise ValueError("Protocol signature rejected") from None


def lifetime(claims, now, maximum):
    now = stamp(now)
    issued, expiry = stamp(claims["issued_at"]), stamp(claims["expires_at"])
    if not 0 < expiry - issued <= maximum or issued > now + 5 or expiry <= now:
        raise ValueError("Stale or unrelated protocol lifetime")


def identity(proof, key, issuer_key_id, now, *, expected_nonce=None, expected_pin=None):
    claims = verified(proof, key, issuer_key_id)
    if set(claims) != ID_FIELDS or claims["kind"] != "identity":
        raise ValueError("Identity shape rejected")
    nonce(claims["nonce"])
    lifetime(claims, now, 300)
    actual = pin(claims["pin"])
    if (expected_nonce is not None and claims["nonce"] != nonce(expected_nonce)) or (
        expected_pin is not None and encode(actual) != encode(pin(expected_pin))
    ):
        raise ValueError("Identity differs from independent challenge or pin")
    return claims


def request(raw, runtime_pin):
    value = decode(raw, 256 * 1024)
    if (
        not isinstance(value, dict)
        or set(value) != {"model", "messages", "stream", "max_completion_tokens"}
        or value["model"] != runtime_pin["model_id"]
        or value["stream"] is not False
        or type(value["max_completion_tokens"]) is not int
        or not 0 < value["max_completion_tokens"] <= 1000
        or not isinstance(value["messages"], list)
        or not 1 <= len(value["messages"]) <= 32
    ):
        raise ValueError("Bounded nonstreaming request required")
    for message in value["messages"]:
        if (
            not isinstance(message, dict)
            or set(message) != {"role", "content"}
            or message["role"] not in {"system", "user", "assistant"}
            or not isinstance(message["content"], str)
            or not message["content"].strip()
        ):
            raise ValueError("Unsupported request message")
    return value


def completion(raw, runtime_pin, maximum):
    value = decode(raw, 8192)
    if (
        not isinstance(value, dict)
        or set(value) != {"model", "request_key_source", "choices", "usage"}
        or value["model"] != runtime_pin["model_id"]
        or value["request_key_source"] != "local-inference"
        or not isinstance(value["choices"], list)
        or len(value["choices"]) != 1
    ):
        raise ValueError("Unsupported completion identity")
    choice = value["choices"][0]
    if (
        not isinstance(choice, dict)
        or set(choice) != {"finish_reason", "message"}
        or choice["finish_reason"] != "stop"
        or not isinstance(choice["message"], dict)
        or set(choice["message"]) != {"role", "content"}
        or choice["message"]["role"] != "assistant"
        or not isinstance(choice["message"]["content"], str)
        or not choice["message"]["content"].strip()
    ):
        raise ValueError("Incomplete completion")
    usage = value["usage"]
    if (
        not isinstance(usage, dict)
        or set(usage) != {"prompt_tokens", "completion_tokens", "total_tokens"}
        or any(type(v) is not int or v < 0 for v in usage.values())
        or usage["completion_tokens"] > maximum
        or usage["total_tokens"] > runtime_pin["application_context_units"]
        or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]
    ):
        raise ValueError("Completion usage exceeds bounds")
    return value


@dataclass(frozen=True)
class ExecutionReceipt:
    """Trusted adapter output, never accepted from HTTP or model-generated fields."""

    runtime_pin: dict
    request_sha256: str
    response_sha256: str
    local_execution: bool
    substituted: bool
    response_nonce: str
    identity_sha256: str
    started_at: int
    completed_at: int


class Issuer:
    def __init__(self, key, issuer_key_id, *, resolve_identity, resolve_execution):
        if (
            not isinstance(key, Ed25519PrivateKey)
            or not callable(resolve_identity)
            or not callable(resolve_execution)
        ):
            raise ValueError("Signing authority and independent adapters required")
        self.key, self.key_id = key, label(issuer_key_id)
        self.resolve_identity, self.resolve_execution = resolve_identity, resolve_execution

    def _runtime(self, credential, model, route_sha256):
        # Resolvers must authenticate credential and validate trusted route/model
        # state; copying these arguments or configured labels is not qualification.
        try:
            actual = pin(self.resolve_identity(credential, label(model), route_sha256))
        except Exception:  # noqa: BLE001 - never disclose credentials or adapter errors
            raise ValueError("Authenticated runtime unavailable") from None
        if actual["model_id"] != model or actual["route_sha256"] != route_sha256:
            raise ValueError("Resolved model or route differs")
        return actual

    def issue_identity(self, credential, model, route_sha256, challenge, *, now):
        actual = self._runtime(credential, model, route_sha256)
        claims = {
            "contract": CONTRACT,
            "kind": "identity",
            "issuer_key_id": self.key_id,
            "nonce": nonce(challenge),
            "pin": actual,
            "issued_at": stamp(now),
            "expires_at": now + 120,
        }
        return encode(signed(self.key, claims))

    def bind_response(
        self, credential, request_bytes, response_bytes, expectation, identity_proof, execution_handle, *, now
    ):
        certificate = identity(identity_proof, self.key.public_key(), self.key_id, now)
        actual = self._runtime(credential, certificate["pin"]["model_id"], certificate["pin"]["route_sha256"])
        req = request(request_bytes, actual)
        if not isinstance(expectation, dict) or set(expectation) != EXPECT_FIELDS:
            raise ValueError("Exact response expectation required")
        expected = decode(encode(expectation))
        lifetime(expected, now, 120)
        nonce(expected["nonce"])
        if (
            expected["contract"] != CONTRACT
            or expected["kind"] != "completion"
            or expected["issuer_key_id"] != self.key_id
            or expected["identity_sha256"] != sha(encode(certificate))
            or expected["pin_sha256"] != sha(encode(actual))
            or expected["request_sha256"] != sha(request_bytes)
            or actual != certificate["pin"]
            or expected["expires_at"] > certificate["expires_at"]
        ):
            raise ValueError("Request, identity, principal or expectation changed")
        completion(response_bytes, actual, req["max_completion_tokens"])
        try:
            receipt = self.resolve_execution(execution_handle)
        except Exception:  # noqa: BLE001 - execution handles/adapter errors stay private
            raise ValueError("Independent completed execution unavailable") from None
        if (
            type(receipt) is not ExecutionReceipt
            or pin(receipt.runtime_pin) != actual
            or receipt.local_execution is not True
            or receipt.substituted is not False
            or receipt.request_sha256 != sha(request_bytes)
            or receipt.response_sha256 != sha(response_bytes)
            or receipt.response_nonce != expected["nonce"]
            or receipt.identity_sha256 != expected["identity_sha256"]
            or type(receipt.started_at) is not int
            or type(receipt.completed_at) is not int
            or not expected["issued_at"] <= receipt.started_at <= receipt.completed_at <= stamp(now) + 5
            or receipt.completed_at >= expected["expires_at"]
        ):
            raise ValueError("Execution receipt differs from bound request/response/runtime")
        return encode(
            {
                "response_base64": base64.b64encode(response_bytes).decode(),
                "provider_binding": signed(self.key, {**expected, "response_sha256": sha(response_bytes)}),
            }
        )


class IdentityChallenge:
    def __init__(self, trusted_key, issuer_key_id, expected_pin, *, challenge=None):
        if not isinstance(trusted_key, Ed25519PublicKey):
            raise ValueError("Independent public trust key required")
        self.key, self.key_id, self._pin = trusted_key, label(issuer_key_id), pin(expected_pin)
        self.nonce, self._used, self._lock = (
            nonce(challenge if challenge is not None else secrets.token_hex(16)),
            False,
            Lock(),
        )

    def consume(self, raw, *, now):
        with self._lock:
            if self._used:
                raise ValueError("Identity challenge consumed; no replay")
            self._used = True
        proof = decode(raw)
        identity(proof, self.key, self.key_id, now, expected_nonce=self.nonce, expected_pin=self._pin)
        return proof


class ResponseChallenge:
    def __init__(
        self,
        request_bytes,
        identity_proof,
        *,
        trusted_key,
        issuer_key_id,
        expected_pin,
        identity_nonce,
        now,
        challenge=None,
    ):
        self.key, self.key_id, self._pin = trusted_key, label(issuer_key_id), pin(expected_pin)
        self._identity = encode(identity_proof)
        certificate = identity(
            decode(self._identity),
            trusted_key,
            issuer_key_id,
            now,
            expected_nonce=identity_nonce,
            expected_pin=self._pin,
        )
        req = request(request_bytes, self._pin)
        self.maximum = req["max_completion_tokens"]
        self._expected = encode(
            {
                "contract": CONTRACT,
                "kind": "completion",
                "issuer_key_id": self.key_id,
                "nonce": nonce(challenge if challenge is not None else secrets.token_hex(16)),
                "request_sha256": sha(request_bytes),
                "identity_sha256": sha(encode(certificate)),
                "pin_sha256": sha(encode(self._pin)),
                "issued_at": stamp(now),
                "expires_at": min(now + 120, certificate["expires_at"]),
            }
        )
        self._used, self._lock = False, Lock()

    def expectation(self):
        return decode(self._expected)

    def consume(self, raw, *, now):
        with self._lock:
            if self._used:
                raise ValueError("Response challenge consumed; no replay")
            self._used = True
        envelope = decode(raw)
        if not isinstance(envelope, dict) or set(envelope) != {"response_base64", "provider_binding"}:
            raise ValueError("Exact response envelope required")
        expected = decode(self._expected)
        lifetime(expected, now, 120)
        identity(decode(self._identity), self.key, self.key_id, now, expected_pin=self._pin)
        try:
            body = base64.b64decode(envelope["response_base64"], validate=True)
        except (ValueError, TypeError):
            raise ValueError("Response wire bytes rejected") from None
        claims = verified(envelope["provider_binding"], self.key, self.key_id)
        if claims != {**expected, "response_sha256": sha(body)}:
            raise ValueError("Signed response differs from exact expectation/bytes")
        value = completion(body, self._pin, self.maximum)
        return {
            "content": value["choices"][0]["message"]["content"],
            "response_sha256": sha(body),
            "request_sha256": expected["request_sha256"],
            "native_execution_authorization": False,
            "production_activation": False,
            "legal_qualification": False,
        }
