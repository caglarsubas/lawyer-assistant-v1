"""Signed staged metadata handoff. Never dispatches inference or provisions trust."""

import base64
from dataclasses import dataclass

import artifact_store as a
import sealed_volume as volume
from signed_provider_contract import (
    CONTRACT,
    decode,
    encode,
    identity,
    label,
    lifetime,
    pin,
    sha,
    signed,
    verified,
)
from signed_provider_handoff import preserve_envelope

KIND = "sealed-store-handoff"
FIELDS = {"contract", "kind", "issuer_key_id", "nonce", "identity_nonce", "identity_issuer_key_id",
          "identity_base64", "identity_sha256", "pin_sha256", "operation_id", "generation_id",
          "bundle_index_sha256", "content_sha256", "manifest_digest", "volume_binding_sha256",
          "receipt_sha256", "verification_base64", "verification_sha256", "issued_at", "expires_at",
          "scope", "native_execution_authorized", "production_activation"}


def b64(raw):
    return base64.b64encode(raw).decode()


def unb64(value):
    if not isinstance(value, str):
        volume.reject()
    raw = base64.b64decode(value, validate=True)
    if b64(raw) != value:
        volume.reject()
    return raw


@dataclass(frozen=True)
class ExpectedHandoff:
    """Trusted caller context, never populated from the bundle or relay body."""

    operation_id: str
    volume_binding_sha256: str
    identity_nonce: str
    handoff_nonce: str
    pin_bytes: bytes
    issuer_key_id: str
    identity_issuer_key_id: str

    def validate(self):
        volume.token(self.operation_id)
        volume.token(self.identity_nonce)
        volume.token(self.handoff_nonce)
        volume.digest(self.volume_binding_sha256)
        label(self.issuer_key_id)
        label(self.identity_issuer_key_id)
        return pin(decode(self.pin_bytes))


def current_identity(raw, expected, key_for, resolve_pin, clock):
    wanted = expected.validate()
    actual = pin(resolve_pin())
    if encode(actual) != encode(wanted):
        volume.reject()
    certificate = identity(decode(raw), key_for(expected.identity_issuer_key_id), expected.identity_issuer_key_id,
                           clock(), expected_nonce=expected.identity_nonce, expected_pin=wanted)
    return certificate, wanted


def issue(root, journal, expected, identity_bytes, signing_key, *, key_for, resolve_pin, clock):
    certificate, runtime = current_identity(identity_bytes, expected, key_for, resolve_pin, clock)
    observed = volume.seal(root, journal, expected.operation_id, expected.volume_binding_sha256)
    record = observed["record"]
    if record["manifest_digest"] != "sha256:" + runtime["model_digest_sha256"]:
        volume.reject()
    current_identity(identity_bytes, expected, key_for, resolve_pin, clock)
    now = clock()
    verification = a.canonical(observed["proof"])
    claims = {"contract": CONTRACT, "kind": KIND, "issuer_key_id": expected.issuer_key_id,
              "nonce": expected.handoff_nonce, "identity_nonce": expected.identity_nonce,
              "identity_issuer_key_id": expected.identity_issuer_key_id,
              "identity_base64": b64(identity_bytes), "identity_sha256": sha(identity_bytes),
              "pin_sha256": sha(encode(runtime)), "operation_id": expected.operation_id,
              "generation_id": record["generation_id"], "bundle_index_sha256": record["bundle_index_sha256"],
              "content_sha256": record["content_sha256"], "manifest_digest": record["manifest_digest"],
              "volume_binding_sha256": record["volume_binding_sha256"], "receipt_sha256": sha(a.canonical(record)),
              "verification_base64": b64(verification), "verification_sha256": sha(verification),
              "issued_at": now, "expires_at": min(now + 120, certificate["expires_at"]),
              "scope": "staged-model-metadata-only", "native_execution_authorized": False,
              "production_activation": False}
    lifetime(claims, now, 120)
    raw = encode(signed(signing_key, claims))
    if len(raw) > 24576:
        volume.reject()
    return raw


def relay_bytes(raw):
    """Opaque existing proof-envelope codec, not verification or permission."""
    return preserve_envelope(raw, "identity")


def consume(raw, root, journal, expected, *, key_for, resolve_pin, clock, checkpoint=None):
    runtime = expected.validate()
    proof = decode(raw)
    claims = verified(proof, key_for(expected.issuer_key_id), expected.issuer_key_id)
    if (set(claims) != FIELDS or claims["kind"] != KIND or claims["nonce"] != expected.handoff_nonce
            or claims["identity_nonce"] != expected.identity_nonce
            or claims["identity_issuer_key_id"] != expected.identity_issuer_key_id
            or claims["operation_id"] != expected.operation_id
            or claims["volume_binding_sha256"] != expected.volume_binding_sha256
            or claims["pin_sha256"] != sha(encode(runtime))
            or claims["scope"] != "staged-model-metadata-only" or claims["native_execution_authorized"] is not False
            or claims["production_activation"] is not False):
        volume.reject()
    lifetime(claims, clock(), 120)
    identity_bytes = unb64(claims["identity_base64"])
    certificate, _ = current_identity(identity_bytes, expected, key_for, resolve_pin, clock)
    if sha(identity_bytes) != claims["identity_sha256"] or claims["expires_at"] > certificate["expires_at"]:
        volume.reject()
    verification = unb64(claims["verification_base64"])
    sent = decode(verification)
    a.validate_proof(sent, claims["manifest_digest"], a.Budget(), strategy="windowed-pinned")
    row = journal.get(expected.operation_id)
    record = row["record"]
    if (row["state"] != "sealed" or sha(verification) != claims["verification_sha256"]
            or sha(a.canonical(record)) != claims["receipt_sha256"]
            or record["generation_id"] != claims["generation_id"]
            or record["bundle_index_sha256"] != claims["bundle_index_sha256"]
            or record["content_sha256"] != claims["content_sha256"]
            or record["manifest_digest"] != claims["manifest_digest"]
            or claims["manifest_digest"] != "sha256:" + runtime["model_digest_sha256"]
            or sent["content_identity_sha256"] != record["content_sha256"]):
        volume.reject()
    # Reserve before local re-verification. Crashes/failures cannot replay a nonce.
    journal.reserve_nonce(expected.operation_id, expected.handoff_nonce, sha(raw))
    if checkpoint is not None:
        checkpoint("reserved_nonce")
    current = volume.seal(root, journal, expected.operation_id, expected.volume_binding_sha256)
    if volume.projection(current["proof"]) != volume.projection(sent):
        volume.reject()
    current_identity(identity_bytes, expected, key_for, resolve_pin, clock)
    verified(proof, key_for(expected.issuer_key_id), expected.issuer_key_id)
    lifetime(claims, clock(), 120)
    journal.consume_nonce(expected.operation_id, expected.handoff_nonce)
    lifetime(claims, clock(), 120)
    if journal.get(expected.operation_id)["state"] != "sealed":
        volume.reject()
    return {"kind": KIND, "wire_sha256": sha(raw), "operation_id": expected.operation_id,
            "generation_id": claims["generation_id"], "content_sha256": claims["content_sha256"],
            "metadata_handoff_verified": True, "native_execution_authorized": False, "production_activation": False}
