"""Disposable retention with current source, independent signatures and exact readback."""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import operator_enrollment_evidence as e  # noqa: E402
import private_inventory_receipts as storage  # noqa: E402
import recipient_receipt_retention as retention  # noqa: E402
from operator_recovery_inputs import FLAGS  # noqa: E402
from retention_authorization_readiness import KeyPin  # noqa: E402
from test_recipient_observation_readiness import shared  # noqa: E402,F401  (pytest fixture)


def provision(root, frame, observation, plan, *, record_id="1" * 32):
    store = storage.ReceiptStore(root=root, context_id="2" * 32, scope_sha256=observation.binding(), key=b"e" * 32)
    binding = retention.store_binding(store)
    now = observation.review.planner.clock()
    private = tuple(Ed25519PrivateKey.generate() for _ in range(2))
    keys = [
        KeyPin(kind=role, key_id=str(index) * 32, principal_id=str(index + 2) * 32, profile_id=str(index + 4) * 32,
               store_context_sha256=binding, issuer_context_sha256=store.scope_sha256,
               public_key=signer.public_key().public_bytes_raw(), not_before=now,
               expires_at=plan["expires_at"])
        for index, (role, signer) in enumerate(zip(("reviewer", "acknowledger"), private, strict=True), 3)
    ]
    permit = retention.Permission(record_id=record_id, receipt_id=frame.specification.receipt_id,
        plan_sha256=e.sha(e.encode(plan)), store_sha256=binding, issued_at=now, expires_at=plan["expires_at"],
        issuer_signature="", custodian_signature="")
    permit = replace(permit, issuer_signature=private[0].sign(permit.message("issuer", keys[0].key_id)).hex(),
                     custodian_signature=private[1].sign(permit.message("custodian", keys[1].key_id)).hex())
    return retention.RecipientReceiptRetention(observation=observation, store=store, permission=permit,
                                                issuer=keys[0], custodian=keys[1]), private[1]


def test_cold_reopening_requires_current_review_and_independent_exact_custody(shared, tmp_path, monkeypatch):  # noqa: F811
    seed, receipt = shared
    frame, receipt = seed.fork(tmp_path / "observation", receipt)
    proof = frame.publish(receipt)
    observation = frame.service(proof)
    plan = frame.call("plan", proof=proof, service=observation)["recipient_retention_plan"]
    root = tmp_path / "store"
    root.mkdir(mode=0o700)
    adapter, custodian = provision(root, frame, observation, plan)
    scope = frame.review.account.scope("reviewer")
    record_id = adapter.permission.record_id
    protected = frame.protected()
    calls = []
    dispatch = observation.dispatch

    def track(*args, **kwargs):
        calls.append(args[1])
        return dispatch(*args, **kwargs)

    monkeypatch.setattr(observation, "dispatch", track)
    denied = adapter.dispatch({}, "retain", record_id=object())
    assert denied["state"] == "denied" and not list(root.iterdir()) and not calls
    forged = replace(adapter, permission=replace(adapter.permission, issuer_signature="0" * 128))
    assert forged.dispatch(scope, "retain", record_id=record_id)["state"] == "unverifiable"
    assert not list(root.iterdir()) and not calls
    with pytest.raises(ValueError):
        replace(adapter, custodian=replace(adapter.custodian, public_key=adapter.issuer.public_key))
    retained = adapter.dispatch(scope, "retain", record_id=record_id)
    assert retained["state"] == "recipient_receipt_retained" and not retained["read_only"] and calls == ["plan"]
    digest = retained["ciphertext_sha256"]
    assert retained["receipt_sha256"] == e.sha(receipt)
    path = root / (record_id + ".receipt")
    raw, info = path.read_bytes(), path.stat()
    assert e.sha(raw) == digest and (info.st_mode & 0o777) == 0o600 and info.st_nlink == 1
    assert receipt not in raw and proof.receipt_sha256.encode() not in raw
    assert adapter.dispatch(scope, "reopen", record_id=record_id, ciphertext_sha256=digest)["state"] == "unverifiable"
    pin = retention.ReopenPin(ciphertext_sha256=digest, issued_at=adapter.permission.issued_at,
                              expires_at=adapter.permission.expires_at, signature="")
    pin = replace(pin, signature=custodian.sign(pin.message(adapter.permission, adapter.custodian.key_id)).hex())
    cold_observation = frame.service(proof)
    cold = replace(adapter, reopen_pin=pin, observation=cold_observation,
                   store=replace(adapter.store))
    reopen_request = {"record_id": record_id, "ciphertext_sha256": digest}
    assert cold.dispatch(scope, "reopen", **{**reopen_request, "ciphertext_sha256": "f" * 64})["state"] == "unverifiable"
    alias = root / "alias"
    os.link(path, alias)
    assert cold.dispatch(scope, "reopen", **reopen_request)["state"] == "unverifiable"
    alias.unlink()
    reopened = cold.dispatch(scope, "reopen", **reopen_request)
    assert reopened["state"] == "recipient_receipt_reopened" and reopened["read_only"]
    assert reopened["ciphertext_sha256"] == digest and reopened["receipt_sha256"] == e.sha(receipt)
    assert reopened["expires_at"] <= plan["expires_at"]
    assert all(not response[k] for response in (retained, reopened) for k in FLAGS | {
        "retention_authorized", "atomic_snapshot", "genuine_acknowledgement_verified", "durability_qualified"})
    assert all(reopened[k] is None for k in ("recipient_receipt", "recipient_retention_plan", "evidence", "review"))

    # A freshly observed mismatch prevents even a valid ciphertext and custody pin from reopening.
    current = cold_observation.current
    def changed(spec, deadline):
        return {**current(spec, deadline), "destination_observation_sha256": "f" * 64}
    monkeypatch.setattr(cold_observation, "current", changed)
    assert cold.dispatch(scope, "reopen", **reopen_request)["state"] == "unverifiable"
    revoked = replace(cold, custodian=replace(cold.custodian, revoked=True))
    assert revoked.dispatch(scope, "reopen", **reopen_request)["state"] == "unverifiable"
    assert frame.protected() == protected
    assert path.stat().st_ino == info.st_ino and path.read_bytes() == raw and list(root.iterdir()) == [path]


def test_create_only_collision_and_postpublication_interruption(tmp_path, monkeypatch):
    root = tmp_path / "store"
    root.mkdir(mode=0o700)
    store = storage.ReceiptStore(root=root, context_id="1" * 32, scope_sha256="2" * 64, key=b"f" * 32)
    record_id = "3" * 32
    values = [storage.MAGIC + b"a" * 32, storage.MAGIC + b"b" * 32]

    def publish(raw):
        try:
            storage._publish(store, record_id, raw)
            return raw
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        winners = [raw for raw in pool.map(publish, values) if raw is not None]
    assert len(winners) == 1
    assert storage._read(store, record_id, e.sha(winners[0])) == winners[0]

    def fsync(fd):
        if os.fstat(fd).st_ino == root.stat().st_ino:
            raise OSError
        original(fd)

    original = os.fsync
    monkeypatch.setattr(os, "fsync", fsync)
    uncertain = "4" * 32
    with pytest.raises(storage.RetentionUncertain):
        storage._publish(store, uncertain, values[0])
    assert storage._read(store, uncertain, e.sha(values[0])) == values[0]
    assert sorted(p.name for p in root.iterdir()) == [record_id + ".receipt", uncertain + ".receipt"]
