"""Invented model bundles and disposable issuer fixtures; no real trust or inputs."""

import hashlib
import os
import random
import shutil
from pathlib import Path

import artifact_store as a
import sealed_relay_handoff as relay
import sealed_volume as volume
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from signed_provider_contract import Issuer, decode, encode, sha

NOW = 1800000200
TRANSFER_CASES = [("T01_import", "prepared"), ("T02_wrong_index", "rejected"),
                  ("T03_unknown_index_field", "rejected"), ("T04_duplicate_artifact", "rejected"),
                  ("T05_boolean_size", "rejected"), ("T06_path_digest", "rejected"),
                  ("T07_missing_blob", "rejected"), ("T08_corrupt_blob", "rejected"),
                  ("T09_symlink_blob", "rejected"), ("T10_hardlink_blob", "rejected"),
                  ("T11_extra_blob", "rejected"), ("T12_control_in_bundle", "rejected"),
                  ("T13_nonempty_target", "rejected"), ("T14_byte_budget", "rejected"),
                  ("T15_cancelled", "rejected"), ("T16_writable_bundle", "rejected")]
HANDOFF_CASES = [("H01_valid", "verified"), ("H02_replay", "rejected"), ("H03_foreign_key", "rejected"),
                 ("H04_wrong_binding", "rejected"), ("H05_wrong_model", "rejected"),
                 ("H06_expired", "rejected"), ("H07_signature_tamper", "rejected"),
                 ("H08_revoked_key", "rejected"), ("H10_cross_identity_kind", "rejected"),
                 ("H11_wrong_tenant", "rejected"), ("H09_revoked_operation", "rejected")]
LIFECYCLE_CASES = [("S01_writable_seal", "rejected"), ("S02_operation_replay", "rejected"),
                   ("S03_copy_crash", "quarantined"), ("S04_rename_crash", "quarantined"),
                   ("S05_nonce_crash", "burned"), ("S06_restore_generation", "verified"),
                   ("S07_prior_handoff_restore", "rejected"), ("S08_revoked_parent_restore", "rejected")]
POLICY = {"schema": "sealed-volume-handoff-qualification-v1", "fresh_seed": 20261029,
          "model_bytes": 8 * a.GIB, "small_model_bytes": 65561, "transfer_seconds": 90,
          "transfer_max_bytes": a.MAX_TOTAL, "verification_seconds": 20,
          "cpu_limit": 2, "memory_limit_mib": 768, "filesystem": "ext4",
          "transfer_cases": [dict(id=n, expected=v) for n, v in TRANSFER_CASES],
          "handoff_cases": [dict(id=n, expected=v) for n, v in HANDOFF_CASES],
          "lifecycle_cases": [dict(id=n, expected=v) for n, v in LIFECYCLE_CASES],
          "crash_checkpoints": ["copied_blob", "renamed", "reserved_nonce"],
          "attempts_per_case": 1, "real_signers_or_credentials": False,
          "native_inference_qualified": False, "production_activation": False}


def operation(name):
    return sha(name.encode())[:32]


def descriptor(media, raw):
    return {"mediaType": media, "digest": "sha256:" + sha(raw), "size": len(raw)}


def make_store(root, *, large=None):
    root = Path(root)
    if root.exists() or root.is_symlink():
        raise ValueError("Fresh fixture store required")
    root.mkdir(mode=0o700)
    for name in ("blobs", "manifests", "manifests-v2"):
        (root / name).mkdir(mode=0o700)
    raw = None if large else b"GGUF\x03\0\0\0" + b"\0" * 16 + random.Random(20261029).randbytes(65561 - 24)
    model = {k: large[k] for k in ("mediaType", "digest", "size")} if large else descriptor(a.MODEL, raw)
    text = b"Invented sealed-volume transfer fixture; no client or legal material."
    layers = [model, descriptor("application/vnd.ollama.image.template", text)]
    config = encode({"model_format": "gguf", "model_family": "llama", "model_families": ["llama"],
                     "rootfs": {"type": "layers", "diff_ids": [v["digest"] for v in layers]}})
    cd = descriptor(a.CONFIG, config)
    mr = encode({"schemaVersion": 2, "mediaType": a.MANIFEST, "config": cd, "layers": layers})
    md = "sha256:" + sha(mr)
    for ref, body in [(md, mr), (cd["digest"], config), (layers[1]["digest"], text)]:
        volume.write_new(root / "blobs" / ref.replace(":", "-"), body)
    model_path = root / "blobs" / model["digest"].replace(":", "-")
    if large:
        Path(large["path"]).rename(model_path)
    else:
        volume.write_new(model_path, raw)
    artifacts = [{"digest": md, "bytes": len(mr)}, {"digest": cd["digest"], "bytes": len(config)},
                 *[{"digest": v["digest"], "bytes": v["size"]} for v in layers]]
    projection = {"manifest": md, "artifacts": artifacts}
    return {"format": volume.FORMAT, **projection, "content_sha256": sha(a.canonical(projection)),
            "total_bytes": sum(v["bytes"] for v in artifacts)}


def make_bundle(root, mode="T01_import"):
    root.mkdir(mode=0o700)
    index = make_store(root / "store")
    model = root / "store/blobs" / index["artifacts"][2]["digest"].replace(":", "-")
    if mode == "T03_unknown_index_field":
        index["private_case"] = "forbidden-fixture-field"
    if mode == "T04_duplicate_artifact":
        index["artifacts"].append(dict(index["artifacts"][0]))
    if mode == "T05_boolean_size":
        index["artifacts"][2]["bytes"] = True
    if mode == "T06_path_digest":
        index["artifacts"][2]["digest"] = "../../not-an-artifact"
    if mode == "T07_missing_blob":
        model.unlink()
    if mode == "T08_corrupt_blob":
        data = model.read_bytes()
        model.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    if mode == "T09_symlink_blob":
        model.unlink()
        model.symlink_to("/absent-sealed-fixture")
    if mode == "T10_hardlink_blob":
        os.link(model, root.parent / (root.name + "-model-link"))
    if mode == "T11_extra_blob":
        volume.write_new(root / "store/blobs" / ("sha256-" + "e" * 64), b"unused")
    if mode == "T12_control_in_bundle":
        volume.write_new(root / "control.sqlite", b"Not a real control journal")
    raw = a.canonical(index)
    volume.write_new(root / "index.json", raw)
    return {"bundle_index_sha256": sha(raw), "manifest_digest": index["manifest"], "content_sha256": index["content_sha256"]}


def prepare_small(root):
    root.mkdir(mode=0o700)
    return {name: make_bundle(root / name, name) for name, _ in TRANSFER_CASES}


def runtime_pin(manifest_digest):
    return {"model_id": "fixture-sealed-model", "model_digest_sha256": manifest_digest[7:],
            "backend": "ollama_http", "format": "ollama_http", "model_context_units": 8192,
            "application_context_units": 4096, "tenant_id": "fixture-tenant", "organization_id": "fixture-org",
            "key_id": "fixture-key", "transport_mode": "native_private", "route_sha256": sha(b"fixture-route-v1"),
            "cloud_fallback_disabled": True}


class SigningFixture:
    def __init__(self, journal, operation_id, binding_sha, manifest_digest, *, challenge_label="initial"):
        self.journal, self.now, self.calls = journal, NOW, []
        self.provider_key, self.store_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        self.runtime = runtime_pin(manifest_digest)
        self.revoked = False
        self.expected = relay.ExpectedHandoff(operation_id, binding_sha, operation("identity-" + operation_id + challenge_label),
                                              operation("handoff-" + operation_id + challenge_label), encode(self.runtime),
                                              "fixture-store-issuer", "fixture-provider-issuer")

        def resolve(credential, model, route):
            self.calls.append("fixture_authenticated_identity")
            if credential != "SYNTHETIC-SEALED-ONLY" or model != self.runtime["model_id"] or route != self.runtime["route_sha256"]:
                raise ValueError("Fixture principal rejected")
            return dict(self.runtime)

        def no_execution(_):
            self.calls.append("forbidden_execution_resolver")
            raise ValueError("No execution exists in this fixture")

        self.issuer = Issuer(self.provider_key, "fixture-provider-issuer", resolve_identity=resolve, resolve_execution=no_execution)
        self.identity_bytes = self.issuer.issue_identity("SYNTHETIC-SEALED-ONLY", self.runtime["model_id"],
                                                        self.runtime["route_sha256"], self.expected.identity_nonce, now=self.now)

    def key_for(self, name):
        if self.revoked:
            return None
        return {"fixture-provider-issuer": self.provider_key.public_key(), "fixture-store-issuer": self.store_key.public_key()}[name]

    def issue(self, root):
        return relay.issue(root, self.journal, self.expected, self.identity_bytes, self.store_key,
                           key_for=self.key_for, resolve_pin=lambda: self.runtime, clock=lambda: self.now)

    def consume(self, raw, root, *, checkpoint=None):
        return relay.consume(raw, root, self.journal, self.expected, key_for=self.key_for,
                             resolve_pin=lambda: self.runtime, clock=lambda: self.now, checkpoint=checkpoint)

    def public_context(self):
        def public(key):
            return relay.b64(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        return {"provider_public_key_base64": public(self.provider_key), "store_public_key_base64": public(self.store_key),
                "expected": {k: (relay.b64(v) if k == "pin_bytes" else v) for k, v in self.expected.__dict__.items()},
                "now": self.now}


def public_receiver(context):
    expected = dict(context["expected"])
    expected["pin_bytes"] = relay.unb64(expected["pin_bytes"])
    expected = relay.ExpectedHandoff(**expected)
    keys = {"fixture-provider-issuer": Ed25519PublicKey.from_public_bytes(relay.unb64(context["provider_public_key_base64"])),
            "fixture-store-issuer": Ed25519PublicKey.from_public_bytes(relay.unb64(context["store_public_key_base64"]))}
    return expected, keys


def verify_retained(raw, context, record, *, wire_sha256):
    """Signature/report replay only; never grants admission or consumes a nonce."""
    expected, keys = public_receiver(context)
    claims = relay.verified(decode(raw), keys[expected.issuer_key_id], expected.issuer_key_id)
    if (sha(raw) != wire_sha256 or set(claims) != relay.FIELDS or claims["kind"] != relay.KIND
            or claims["operation_id"] != record["operation_id"] or claims["generation_id"] != record["generation_id"]
            or claims["receipt_sha256"] != sha(a.canonical(record)) or claims["nonce"] != expected.handoff_nonce
            or claims["identity_nonce"] != expected.identity_nonce or claims["pin_sha256"] != sha(expected.pin_bytes)
            or claims["volume_binding_sha256"] != expected.volume_binding_sha256
            or claims["bundle_index_sha256"] != record["bundle_index_sha256"]
            or claims["content_sha256"] != record["content_sha256"] or claims["manifest_digest"] != record["manifest_digest"]
            or claims["scope"] != "staged-model-metadata-only"):
        volume.reject()
    relay.lifetime(claims, context["now"], 120)
    certificate, _ = relay.current_identity(relay.unb64(claims["identity_base64"]), expected, keys.get,
                                           lambda: decode(expected.pin_bytes), lambda: context["now"])
    verification = relay.unb64(claims["verification_base64"])
    proof = decode(verification)
    a.validate_proof(proof, record["manifest_digest"], a.Budget(), strategy="windowed-pinned")
    if (sha(verification) != claims["verification_sha256"] or proof["content_identity_sha256"] != record["content_sha256"]
            or claims["expires_at"] > certificate["expires_at"] or claims["native_execution_authorized"] is not False
            or claims["production_activation"] is not False):
        volume.reject()
    return {"signature_verified": True, "metadata_replay_only": True, "native_execution_authorized": False}


def run_transfer_cases(bundles, targets, journal, approvals, binding_prefix, *, skip=()):
    rows = []
    for name, expected in TRANSFER_CASES:
        if name in skip:
            continue
        target = targets / name
        target.mkdir(mode=0o700)
        source = bundles / name
        if name == "T16_writable_bundle":
            source = targets / "writable-bundle"
            shutil.copytree(bundles / name, source)
        if name == "T13_nonempty_target":
            volume.write_new(target / "keep", b"untouched-fixture-original")
        expected_sha = "f" * 64 if name == "T02_wrong_index" else approvals[name]["bundle_index_sha256"]
        op = operation(name)
        try:
            result = volume.import_bundle(source, target, journal, op, expected_sha, sha((binding_prefix + name).encode()),
                                          budget=volume.TransferBudget(max_bytes=1) if name == "T14_byte_budget" else volume.TransferBudget(),
                                          cancelled=(lambda: True) if name == "T15_cancelled" else None)
            observed = "prepared" if result["requires_readonly_reverification"] and journal.get(op)["state"] == "prepared" else "invalid-admission"
        except (ValueError, OSError):
            observed = "rejected"
        try:
            state = journal.get(op)["state"]
        except ValueError:
            state = "absent"
        preserved = name != "T13_nonempty_target" or (target / "keep").read_bytes() == b"untouched-fixture-original"
        rows.append({"id": name, "expected": expected, "observed": observed, "control_state": state,
                     "original_preserved": preserved, "production_activation": False})
    return rows


def run_handoff_cases(root, journal, operation_id, binding_sha, manifest_digest):
    from dataclasses import replace

    from signed_provider_contract import identity

    rows, first, first_raw, first_public = [], None, None, None
    for name, expected_outcome in HANDOFF_CASES:
        fixture = first if name == "H02_replay" else SigningFixture(journal, operation_id, binding_sha, manifest_digest, challenge_label=name)
        raw = first_raw if name == "H02_replay" else fixture.issue(root)
        forwarded = relay.relay_bytes(raw)
        if forwarded != raw:
            raise ValueError("Opaque relay modified exact bytes")
        if name == "H03_foreign_key":
            fixture.key_for = lambda _: Ed25519PrivateKey.generate().public_key()
        if name == "H04_wrong_binding":
            fixture.expected = replace(fixture.expected, volume_binding_sha256="f" * 64)
        if name in {"H05_wrong_model", "H11_wrong_tenant"}:
            changed = dict(fixture.runtime)
            changed["model_digest_sha256" if name == "H05_wrong_model" else "tenant_id"] = "f" * 64 if name == "H05_wrong_model" else "fixture-other-tenant"
            fixture.expected = replace(fixture.expected, pin_bytes=encode(changed))
        if name == "H06_expired":
            fixture.now += 121
        if name == "H07_signature_tamper":
            value = decode(raw)
            signature = relay.unb64(value["signature"])
            value["signature"] = relay.b64(bytes([signature[0] ^ 1]) + signature[1:])
            forwarded = encode(value)
        if name == "H08_revoked_key":
            fixture.revoked = True
        if name == "H09_revoked_operation":
            journal.revoke(operation_id)
        try:
            if name == "H10_cross_identity_kind":
                identity(decode(forwarded), fixture.store_key.public_key(), "fixture-store-issuer", NOW)
            else:
                result = fixture.consume(forwarded, root)
                if result["native_execution_authorized"] or result["production_activation"]:
                    raise AssertionError("Metadata handoff became execution")
            observed = "verified"
        except ValueError:
            observed = "rejected"
        rows.append({"id": name, "expected": expected_outcome, "observed": observed, "opaque_relay_preserved": raw == relay.relay_bytes(raw)})
        if name == "H01_valid":
            first, first_raw = fixture, raw
            first_public = {"context": fixture.public_context(), "wire_base64": relay.b64(raw),
                            "wire_sha256": sha(raw), "record": journal.get(operation_id)["record"]}
    return {"cases": rows, "valid_frame": first_public, "execution_resolver_calls": sum(fixture.calls.count("forbidden_execution_resolver") for fixture in [first])}


def write_large(path):
    generator, h, total = random.Random(POLICY["fresh_seed"]), hashlib.sha256(), 0
    with path.open("xb", buffering=0) as stream:
        path.chmod(0o600)
        while total < POLICY["model_bytes"]:
            block = generator.randbytes(a.CHUNK)
            if total == 0:
                block = b"GGUF\x03\0\0\0" + b"\0" * 16 + block[24:]
            pending = memoryview(block)
            while pending:
                n = stream.write(pending)
                if not n:
                    volume.reject()
                pending = pending[n:]
            h.update(block)
            total += len(block)
            if total % (64 * a.CHUNK) == 0:
                os.fsync(stream.fileno())
                os.posix_fadvise(stream.fileno(), total - 64 * a.CHUNK, 64 * a.CHUNK, os.POSIX_FADV_DONTNEED)
        os.fsync(stream.fileno())
    return {"path": str(path), "mediaType": a.MODEL, "digest": "sha256:" + h.hexdigest(), "size": total}
