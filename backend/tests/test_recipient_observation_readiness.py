"""Receipt metadata and independent review never grant retention or authority."""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import operator_enrollment_evidence as e  # noqa: E402
import recipient_observation_readiness as access  # noqa: E402
from metadata_handoff_fixture import make as make_metadata  # noqa: E402
from operator_recovery_inputs import FLAGS  # noqa: E402
from recipient_observation_fixture import make, make_independent_pair  # noqa: E402


@pytest.fixture(scope="module")
def shared(tmp_path_factory):
    root = tmp_path_factory.mktemp("recipient-observation")
    pair = make_independent_pair(root / "pair")
    metadata = frame = None
    try:
        metadata = make_metadata(pair, root / "metadata")
        digest, _ = metadata.publish()
        frame = make(metadata, digest, root / "recipient")
        seed = frame.observe()
        yield frame, seed
    finally:
        pair.close()
        if metadata:
            metadata.target.account.store.engine.dispose()
        if frame:
            frame.review.account.store.engine.dispose()


@pytest.fixture
def frame(shared, tmp_path):
    original, seed = shared
    return original.fork(tmp_path / "notes", seed)


def safe(value, withheld=False):
    assert value["read_only"] and value["metadata_only"] and all(value[k] is False for k in FLAGS)
    assert not any(value[k] for k in ("retention_authorized", "genuine_acknowledgement_verified", "durability_qualified",
        "snapshot_verified", "destination_attestation_verified", "atomic_snapshot", "joint_rollback_qualified"))
    assert value["evidence"] is value["review"] is value["decision"] is value["retention_plan"] is None
    assert value["handoff"] is value["acceptance"] is None
    if withheld:
        assert not value["recipient_observation_receipt_ready"] and not value["recipient_retention_plan_ready"]
        assert value["recipient_receipt"] is value["recipient_retention_plan"] is None


def read(f, call):
    before = f.protected()
    value = call()
    assert f.protected() == before
    safe(value)
    return value


def test_exact_receipt_and_independently_reviewed_plan_preserve_versions_and_original_expiry(frame, monkeypatch):
    f, raw = frame
    value = e.decode(raw)
    assert set(value) == access.RECEIPT and set(value["acceptance"]) == access.ACCEPTANCE
    for forbidden in ("cookie", "session_sha256", "private_key", "public_key", "document", "plaintext", "path"):
        assert forbidden not in json.dumps(value)
    proof = f.publish(raw)
    service = f.service(proof)
    counts = {"source": 0, "recipient": 0}
    source, recipient = service.source.current, service.source.destination_observation
    def source_read(*args):
        counts["source"] += 1
        return source(*args)
    def recipient_read(*args):
        counts["recipient"] += 1
        return recipient(*args)
    monkeypatch.setattr(service.source, "current", source_read)
    monkeypatch.setattr(service.source, "destination_observation", recipient_read)
    plan = read(f, lambda: f.call("plan", proof=proof, service=service))
    assert plan["state"] == "ready_for_disposable_recipient_retention_planning"
    assert plan["independent_recipient_review_checked"] and counts == {"source": 2, "recipient": 2}
    assert plan["recipient_retention_plan"]["receipt_sha256"] == e.sha(raw)
    assert plan["recipient_retention_plan"]["review_set_sha256"] == proof.sha256
    assert plan["recipient_retention_plan"]["expires_at"] <= value["expires_at"] <= f.metadata.recipient_input_expires_at


def test_fresh_receipt_reobservation_does_not_extend_the_original_window(frame):
    f, seed = frame
    observed = read(f, lambda: f.call("observe"))
    assert observed["state"] == "recipient_observation_receipt_ready"
    raw = e.encode(observed["recipient_receipt"]["manifest"])
    assert observed["recipient_receipt"]["sha256"] == e.sha(raw)
    assert e.decode(raw)["acceptance"] == e.decode(seed)["acceptance"]
    assert e.decode(raw)["expires_at"] == e.decode(seed)["expires_at"]


def test_authentication_precedes_registry_lookup_and_all_metadata_reads(frame, monkeypatch):
    f, _ = frame
    service = f.service()
    def forbidden(*args):
        raise AssertionError("Unauthenticated request reached a private read")
    monkeypatch.setattr(service, "binding", forbidden)
    for operation, account in (("observe", f.metadata.target.account), ("plan", f.review.account)):
        denied = read(f, lambda: f.call(operation, service=service, scope=account.scope("preparer"),
                                       entry_id="not-an-identifier"))
        assert denied["state"] == "denied"
        safe(denied, True)


def test_independent_profile_keys_and_host_only_configuration_cannot_be_substituted(frame):
    f, _ = frame
    bad = {**f.keys, "reviewer": replace(f.keys["reviewer"], public_key=f.keys["preparer"].public_key)}
    with pytest.raises(ValueError):
        f.service(keys=bad)
    with pytest.raises(ValueError):
        access.RecipientObservation(f.metadata.service(packages={f.metadata.specification.handoff_id: f.digest}),
            f.metadata.target.service(), f.root, f.pins, f.keys, {f.specification.receipt_id: f.specification}, {},
            recipient_scope=f.metadata.target.account.scope("reviewer"))
    held = read(f, lambda: f.call("observe", path="/untrusted", keys={}))
    assert held["state"] == "unverifiable"
    safe(held, True)


def test_negative_independent_reviews_withhold_plans_without_source_reads(frame, tmp_path, monkeypatch):
    base, seed = frame
    for decision in ("reject", "changes_required"):
        f, raw = base.fork(tmp_path / decision, seed)
        proof = f.publish(raw, decision=decision)
        service = f.service(proof)
        def forbidden(*args):
            raise AssertionError("Negative review read source evidence")
        monkeypatch.setattr(service, "current", forbidden)
        held = read(f, lambda: f.call("plan", proof=proof, service=service))
        assert held["state"] == "review_" + decision
        safe(held, True)


def test_exact_receipt_proposal_decision_and_signature_versions_cannot_be_replaced(frame, tmp_path):
    base, seed = frame
    for suffix in ("receipt", "proposal", "decision", "signature", "duplicate"):
        f, raw = base.fork(tmp_path / suffix, seed)
        proof = f.publish(raw)
        path = f.root / (f.specification.receipt_id + "." + ("decision" if suffix == "signature" else
                         "receipt" if suffix == "duplicate" else suffix) + ".json")
        content = path.read_bytes()
        if suffix == "signature":
            value = e.decode(content)
            value["signature"] = "0" * 128
            content = e.encode(value)
            proof = replace(proof, decision_sha256=e.sha(content))
        elif suffix == "duplicate":
            content = b'{"schema":"duplicate",' + content[1:]
            proof = replace(proof, receipt_sha256=e.sha(content))
        else:
            content += b" "
        path.write_bytes(content)  # Declared fixture-only exact-version fault.
        held = read(f, lambda: f.call("plan", proof=proof))
        assert held["state"] == "unverifiable" and path.read_bytes() == content
        safe(held, True)


def test_missing_linked_staged_and_oversized_metadata_are_retained_without_adoption(frame, tmp_path):
    base, seed = frame
    for mode in ("missing", "symlink", "hardlink", "staged", "oversized"):
        f, raw = base.fork(tmp_path / mode, seed)
        proof = f.publish(raw)
        path = f.root / (f.specification.receipt_id + ".receipt.json")
        if mode == "missing":
            path.unlink()
        elif mode in {"symlink", "hardlink"}:
            target = tmp_path / (mode + ".external")
            e.retain(target, raw)
            path.unlink()
            if mode == "symlink":
                path.symlink_to(target)
            else:
                os.link(target, path)
        elif mode == "staged":
            e.retain(f.root / "interrupted.part", b"INVENTED staged receipt")
        else:
            path.write_bytes(b"x" * (access.MAX_BYTES + 1))
        held = read(f, lambda: f.call("plan", proof=proof))
        assert held["state"] == "unverifiable"
        safe(held, True)


def test_metadata_race_withholds_onward_planning_and_preserves_original_histories(frame):
    f, raw = frame
    proof = f.publish(raw)
    path = f.root / (f.specification.receipt_id + ".receipt.json")
    changed = raw + b" "
    original = f.metadata.protected(), f.review.protected()
    def race(_):
        path.write_bytes(changed)
    value = f.call("plan", proof=proof, service=f.service(proof, checkpoint=race))
    assert value["state"] == "observation_conflict" and path.read_bytes() == changed
    assert (f.metadata.protected(), f.review.protected()) == original
    safe(value, True)


def test_expired_or_revoked_review_keys_and_checked_budget_fail_closed(frame, monkeypatch):
    f, raw = frame
    proof = f.publish(raw)
    for mode in ("revoked", "expired"):
        key = f.keys["reviewer"]
        key = replace(key, revoked=True) if mode == "revoked" else replace(key, expires_at=f.review.account.now)
        held = read(f, lambda: f.call("plan", proof=proof, service=f.service(proof, keys={**f.keys, "reviewer": key})))
        assert held["state"] == "unverifiable"
        safe(held, True)
    monkeypatch.setattr(access, "BUDGET_SECONDS", 0)
    held = read(f, lambda: f.call("plan", proof=proof))
    assert held["state"] == "budget_exhausted"
    safe(held, True)


def test_missing_review_or_unavailable_recipient_authority_does_not_fill_in_decisions(frame):
    f, raw = frame
    missing = read(f, lambda: f.call("plan"))
    assert missing["state"] == "unverifiable"
    safe(missing, True)
    proof = f.publish(raw)
    held = read(f, lambda: f.call("plan", proof=proof,
        service=f.service(proof, recipient_scope=f.metadata.target.account.scope("preparer"))))
    assert held["state"] == "source_unavailable"
    safe(held, True)
