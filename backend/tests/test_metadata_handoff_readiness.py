"""Exact metadata transport never grants retention, trust renewal or legal approval."""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import metadata_handoff_readiness as access  # noqa: E402
import operator_enrollment_evidence as e  # noqa: E402
from destination_snapshot_fixture import make_pair  # noqa: E402
from metadata_handoff_fixture import make, make_recipient, wrap  # noqa: E402
from operator_recovery_inputs import FLAGS  # noqa: E402


@pytest.fixture(scope="module")
def shared(tmp_path_factory):
    root = tmp_path_factory.mktemp("metadata-handoff")
    recipient = make_recipient(root / "older-recipient", age_seconds=120)
    pair = make_pair(root / "pair")
    f = None
    try:
        f = make(pair, root / "frame", recipient=recipient)
        digest, value = f.publish()
        yield f, digest, e.encode(value["handoff"]["manifest"])
    finally:
        pair.close()
        recipient.account.store.engine.dispose()


@pytest.fixture
def frame(shared, tmp_path):
    base, digest, raw = shared
    f = base.fork(tmp_path / "transport", specification=base.specification)
    e.retain(f.root / (f.specification.handoff_id + ".metadata.json"), raw)
    return f, digest


def safe(value, withheld=False):
    assert value["read_only"] and all(value[k] is False for k in FLAGS)
    assert not any(value[k] for k in ("retention_authorized", "genuine_acknowledgement_verified", "durability_qualified",
        "snapshot_verified", "destination_attestation_verified", "atomic_snapshot", "joint_rollback_qualified",
        "ready_for_disposable_input_handoff", "ready_for_disposable_retention_planning"))
    assert value["evidence"] is None and value["review"] is None and value["decision"] is None
    assert value["retention_plan"] is None and value["reobservation"] is None
    if withheld:
        assert value["handoff"] is value["acceptance"] is None
        assert not value["metadata_package_ready"] and not value["read_only_destination_acceptance"]


def read(f, callback):
    before = f.protected()
    result = callback()
    assert f.protected() == before
    safe(result)
    return result


def service(f, digest, **options):
    return f.service(packages={f.specification.handoff_id: digest}, **options)


def test_canonical_hash_only_package_and_fresh_acceptance_preserve_every_version(frame):
    f, digest = frame
    # The shared fixture packages once through the real read-only service.
    raw = (f.root / (f.specification.handoff_id + ".metadata.json")).read_bytes()
    assert e.sha(raw) == digest
    manifest = e.decode(raw)
    assert manifest["specification"] == json.loads(e.encode(f.specification.__dict__))
    assert set(manifest["evidence"]) == access.EVIDENCE and manifest["expires_at"] <= f.pair.snapshot["expires_at"]
    for forbidden in ("cookie", "session_sha256", "public_key", "private_key", "path", "document", "plaintext"):
        assert forbidden not in json.dumps(manifest)
    s = service(f, digest)
    accepted = read(f, lambda: f.call("accept", service=s, package_sha256=digest))
    assert accepted["state"] == "read_only_destination_acceptance"
    assert accepted == read(f, lambda: f.call("accept", service=s, package_sha256=digest))
    assert accepted["acceptance"]["package_sha256"] == digest
    assert accepted["acceptance"]["expires_at"] <= manifest["expires_at"]
    assert f.recipient_input_expires_at < manifest["expires_at"]
    assert accepted["acceptance"]["expires_at"] == f.recipient_input_expires_at


def test_source_and_recipient_authentication_precede_lookup_and_file_reads(frame, monkeypatch):
    f, digest = frame
    s = service(f, digest)
    monkeypatch.setattr(s, "binding", lambda: pytest.fail("Unauthorized request inspected bindings"))
    for operation, account in [("package", f.pair.target.account), ("accept", f.target.account)]:
        for role, fault in [("preparer", None), ("other", None), ("reviewer", b"cookie"),
                            ("reviewer", b"origin"), ("reviewer", b"x-csrf-token")]:
            scope = account.scope(role)
            if fault:
                scope["headers"] = [(k, b"invalid" if k == fault else v) for k, v in scope["headers"]]
            value = read(f, lambda: f.call(operation, service=s, scope=scope, package_sha256=digest))
            assert value["state"] == "denied"
            safe(value, True)


def test_exact_versions_host_pins_and_closed_operations_cannot_be_request_provisioned(frame):
    f, digest = frame
    s, spec = service(f, digest), f.specification
    request = {"entry_id": spec.handoff_id, "specification_sha256": spec.sha256, "package_sha256": digest}
    for operation, changes in [("accept", {"entry_id": "0" * 32}), ("accept", {"specification_sha256": "0" * 64}),
        ("accept", {"package_sha256": "0" * 64}), ("accept", {"keys": {}}), ("retain", {}), ("restore", {})]:
        value = read(f, lambda: s.dispatch(f.target.account.scope("reviewer"), operation, **{**request, **changes}))
        assert value["state"] == "unverifiable"
        safe(value, True)
    missing = read(f, lambda: f.call("accept", service=f.service(), package_sha256=digest))
    assert missing["state"] == "unverifiable"
    with pytest.raises(ValueError):
        f.service(pins=replace(f.pins, destination_context_sha256="0" * 64))
    with pytest.raises(ValueError):
        f.service(target=f.pair.target.service())  # Sender cannot act as its own recipient.


def test_malformed_or_promoting_transport_fails_before_source_decryption(frame, monkeypatch):
    f, _ = frame
    path = f.root / (f.specification.handoff_id + ".metadata.json")
    base = e.decode(path.read_bytes())
    faults = [lambda v: v.update(production_activation=True), lambda v: v.update(purpose="production_retention"),
              lambda v: v.update(document="SYNTHETIC forbidden body"),
              lambda v: v["evidence"].update(reference_sha256="0" * 64),
              lambda v: v.update(expires_at=v["expires_at"] + 1)]
    for mutate in faults:
        value = e.decode(e.encode(base))
        mutate(value)
        raw = e.encode(value)
        path.write_bytes(raw)  # Explicit mutation of this test's transport copy only.
        s = service(f, e.sha(raw))
        if value["evidence"] == base["evidence"]:
            monkeypatch.setattr(s, "current", lambda *a: pytest.fail("Malformed transport read its source"))
        held = read(f, lambda: f.call("accept", service=s, package_sha256=e.sha(raw)))
        assert held["state"] == "unverifiable"
        safe(held, True)
        assert path.read_bytes() == raw
    duplicate = b'{"schema":"duplicate",' + e.encode(base)[1:]
    path.write_bytes(duplicate)
    held = read(f, lambda: f.call("accept", service=service(f, e.sha(duplicate)), package_sha256=e.sha(duplicate)))
    assert held["state"] == "unverifiable" and path.read_bytes() == duplicate


def test_negative_review_and_tampered_signed_proof_withhold_all_metadata(frame, tmp_path):
    f, _ = frame
    for index, decision in enumerate(("changes_required", "reject", "accept")):
        source = f.source.fork(tmp_path / ("proof-" + str(index)))
        proof = source.publish(decision=decision)
        g = f.fork(tmp_path / ("transport-" + str(index)), source=source, proof=proof)
        if decision == "accept":
            p = source.root / (proof.proof_id + ".decision.json")
            p.write_bytes(p.read_bytes() + b" ")  # Retain mismatched exact proof bytes, never repair them.
        held = read(g, lambda: g.call("package"))
        assert held["state"] == "source_unavailable"
        safe(held, True)


def test_expired_source_session_and_revoked_recipient_are_rechecked(frame, tmp_path):
    f, digest = frame
    source = f.source.service({f.specification.proof_entry_id: f.proof})
    p = source.references.verifier.target.planner
    expiry = p.actor(f.pair.target.account.scope("reviewer"), "reviewer")["expires_at"]
    def expire(_):
        p.clock = lambda: expiry + 1  # Advance only this isolated verifier's trusted clock.
    s = service(f, digest, source=source, checkpoint=expire)
    held = read(f, lambda: f.call("accept", service=s, package_sha256=digest))
    assert held["state"] == "source_unavailable"
    safe(held, True)
    recipient = make_recipient(tmp_path / "revoked-recipient")
    try:
        recipient.account.now = max(recipient.account.now, f.pair.target.account.now)
        root = tmp_path / "recipient-transport"
        root.mkdir(mode=0o700)
        g = wrap(f.pair, f.source, recipient, f.proof, root)
        pin, _ = g.publish()
        recipient.account.revoke("reviewer")  # Declared private fixture mutation before this read baseline.
        denied = read(g, lambda: g.call("accept", service=service(g, pin), package_sha256=pin))
        assert denied["state"] == "denied"
        safe(denied, True)
    finally:
        recipient.account.store.engine.dispose()


def test_manifest_and_destination_namespace_races_retain_unexpected_bytes(frame):
    f, digest = frame
    before = f.source.protected(), f.target.protected()
    path = f.root / (f.specification.handoff_id + ".metadata.json")
    injected = path.read_bytes() + b" "
    def change(_):
        path.write_bytes(injected)
    held = f.call("accept", service=service(f, digest, checkpoint=change), package_sha256=digest)
    assert held["state"] == "observation_conflict" and path.read_bytes() == injected
    assert (f.source.protected(), f.target.protected()) == before
    safe(held, True)


def test_expired_specification_and_budget_failure_do_not_extend_handoff_windows(frame, monkeypatch):
    f, digest = frame
    spec = replace(f.specification, created_at=f.target.account.now - 2, expires_at=f.target.account.now)
    s = f.service(specifications={spec.handoff_id: spec})
    held = read(f, lambda: f.call("package", service=s, specification=spec))
    assert held["state"] == "unverifiable"
    safe(held, True)
    monkeypatch.setattr(access, "BUDGET_SECONDS", 0)
    held = read(f, lambda: f.call("accept", service=service(f, digest), package_sha256=digest))
    assert held["state"] == "budget_exhausted"
    safe(held, True)


def test_missing_linked_staged_or_oversized_transport_is_never_adopted(frame, tmp_path):
    f, digest = frame
    raw = (f.root / (f.specification.handoff_id + ".metadata.json")).read_bytes()
    for kind in ("missing", "symlink", "hardlink", "staging", "oversized"):
        g = f.fork(tmp_path / kind, specification=f.specification)
        path = g.root / (f.specification.handoff_id + ".metadata.json")
        if kind == "symlink":
            path.symlink_to(f.root / path.name)
        elif kind == "hardlink":
            os.link(f.root / path.name, path)
        elif kind == "staging":
            e.retain(g.root / "interrupted.part", b"SYNTHETIC staged metadata")
        elif kind == "oversized":
            e.retain(path, b"x" * (access.MAX_BYTES + 1))
        held = read(g, lambda: g.call("accept", service=service(g, digest), package_sha256=digest))
        assert held["state"] == "unverifiable"
        safe(held, True)
    assert (f.root / (f.specification.handoff_id + ".metadata.json")).read_bytes() == raw
