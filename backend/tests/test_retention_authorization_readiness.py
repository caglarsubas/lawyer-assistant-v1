"""Independent, exact-version metadata review never supplies real retention authority."""

import json
import os
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import operator_enrollment_evidence as e  # noqa: E402
import retention_authorization_readiness as access  # noqa: E402
from destination_snapshot_fixture import make_pair  # noqa: E402
from operator_recovery_inputs import FLAGS  # noqa: E402
from qualify_destination_snapshot import short_session  # noqa: E402
from retention_authorization_fixture import ENTRY, make  # noqa: E402


@pytest.fixture(scope="module")
def shared_pair(tmp_path_factory):
    pair = make_pair(tmp_path_factory.mktemp("retention-authorization-read-only") / "pair")
    yield pair
    pair.close()


@pytest.fixture
def frame(shared_pair, tmp_path):
    before = shared_pair.protected()
    f = make(shared_pair, tmp_path / "fixture")
    yield f
    assert shared_pair.protected() == before


@pytest.fixture
def isolated(tmp_path):
    pair = make_pair(tmp_path / "pair")
    f = make(pair, tmp_path / "fixture")
    yield f
    pair.close()


def safe(value, withheld=False):
    assert value["read_only"] and all(value[k] is False for k in FLAGS)
    assert not any(value[k] for k in ("retention_authorized", "durability_qualified", "genuine_acknowledgement_verified",
        "snapshot_verified", "destination_attestation_verified", "atomic_snapshot", "joint_rollback_qualified",
        "ready_for_disposable_input_handoff", "ready_for_pinned_disposable_review_handoff"))
    assert value["retention_plan"] is None and value["reobservation"] is None
    if withheld:
        assert value["evidence"] is None and not value["ready_for_disposable_retention_planning"]
        assert not value["independent_disposable_review_checked"] and not value["signed_provenance_matches_host_pins"]


def read(f, callback):
    before = f.protected()
    value = callback()
    assert f.protected() == before
    safe(value)
    return value


def test_independent_signed_versions_reopen_exactly_without_writes_or_new_authority(frame):
    first, second = frame.publish(), frame.publish()
    s = frame.service({ENTRY: first, "a" * 32: second})
    value = read(frame, lambda: frame.call(first, service=s))
    assert value["state"] == "ready_for_disposable_retention_planning"
    assert value["independent_disposable_review_checked"] and value["signed_provenance_matches_host_pins"]
    assert value["evidence"]["proof_set_sha256"] == first.sha256 != second.sha256
    assert value == read(frame, lambda: frame.call(first))
    assert value["evidence"]["original_handoff_expires_at"] == frame.notes.pair.snapshot["expires_at"]
    assert value["evidence"]["expires_at"] <= frame.notes.pair.snapshot["expires_at"]
    assert "session_sha256" not in json.dumps(value) and "public_key" not in json.dumps(value)


def test_authentication_precedes_registry_namespace_and_proof_reads(frame, monkeypatch):
    proof = frame.publish()
    s = frame.service({ENTRY: proof})
    monkeypatch.setattr(s, "observe", lambda: pytest.fail("Denied caller inspected private proofs"))
    monkeypatch.setattr(s, "read", lambda *a: pytest.fail("Denied caller parsed proofs"))
    for role, fault in [("other", None), ("preparer", None), ("reviewer", b"cookie"),
                        ("reviewer", b"origin"), ("reviewer", b"x-csrf-token")]:
        scope = frame.notes.pair.target.account.scope(role)
        if fault:
            scope["headers"] = [(k, b"invalid" if k == fault else v) for k, v in scope["headers"]]
        value = read(frame, lambda: frame.call(proof, service=s, scope=scope))
        assert value["state"] == "denied"
        safe(value, True)


def test_explicit_entries_versions_and_closed_operations_reject_request_provisioning(frame):
    proof = frame.publish()
    s, scope = frame.service({ENTRY: proof}), frame.notes.pair.target.account.scope("reviewer")
    for operation, request in [("inspect", {"entry_id": ENTRY, "proof_set_sha256": "0" * 64}),
        ("inspect", {"entry_id": "d" * 32, "proof_set_sha256": proof.sha256}),
        ("retain", {"entry_id": ENTRY, "proof_set_sha256": proof.sha256}),
        ("inspect", {"entry_id": ENTRY, "proof_set_sha256": proof.sha256, "keys": {}})]:
        value = read(frame, lambda: s.dispatch(scope, operation, **request))
        assert value["state"] == "unverifiable"
        safe(value, True)


def test_tampered_signature_and_exact_hash_mismatch_are_not_repaired(frame):
    proof = frame.publish()
    path = frame.root / (proof.proof_id + ".decision.json")
    original = path.read_bytes()
    value = e.decode(original)
    value["signature"] = "0" * 128
    raw = e.encode(value)
    path.write_bytes(raw)  # Declared injection into this test-owned proof only.
    for selected in [proof, replace(proof, decision_sha256=e.sha(raw))]:
        value = read(frame, lambda: frame.call(selected))
        assert value["state"] == "unverifiable"
        safe(value, True)
    assert path.read_bytes() == raw != original


def test_valid_signatures_cannot_promote_self_review_wrong_purpose_or_custody(frame, tmp_path):
    faults = [("reviewer", "reviewed_by", lambda f: f.notes.pair.target.service().planner.actor(f.notes.pair.target.account.scope("preparer"), "preparer")),
              ("preparer", "purpose", lambda f: "production_retention"),
              ("acknowledger", "custody_status", lambda f: "approved"),
              ("reviewer", "authority_renewed", lambda f: True)]
    for index, (kind, field, replacement) in enumerate(faults):
        f = frame.fork(tmp_path / str(index))
        def mutate(selected, claims):
            if selected == kind:
                claims[field] = replacement(f)
        proof = f.publish(mutate=mutate)
        value = read(f, lambda: f.call(proof))
        assert value["state"] == "unverifiable"
        safe(value, True)


def test_independent_key_roles_revocation_expiry_and_scope_are_mandatory(frame):
    proof = frame.publish()
    now = frame.notes.pair.target.account.now
    for kind, edits in [("reviewer", {"revoked": True}), ("preparer", {"expires_at": now}),
        ("acknowledger", {"profile_id": "0" * 32}), ("acknowledger", {"issuer_context_sha256": "0" * 64}),
        ("reviewer", {"public_key": b"\x01" * 32})]:
        keys = {**frame.keys, kind: replace(frame.keys[kind], **edits)}
        value = read(frame, lambda: frame.call(proof, service=frame.service({ENTRY: proof}, keys=keys)))
        assert value["state"] == "unverifiable"
        safe(value, True)
    with pytest.raises(ValueError):
        frame.service({ENTRY: proof}, keys={**frame.keys, "reviewer": replace(frame.keys["reviewer"], principal_id=frame.keys["preparer"].principal_id)})


def test_negative_reviews_remain_negative_without_source_decryption(frame, monkeypatch):
    for decision in ("changes_required", "reject"):
        proof = frame.publish(decision=decision)
        s = frame.service({ENTRY: proof})
        monkeypatch.setattr(s, "current", lambda *a: pytest.fail("Negative review triggered source decryption"))
        value = read(frame, lambda: frame.call(proof, service=s))
        assert value["state"] == "independent_review_not_accepted"
        safe(value, True)


def test_provenance_version_and_proof_root_are_bound_to_the_review(frame, tmp_path):
    proof = frame.publish()
    path = frame.root / (proof.proof_id + ".provenance.json")
    old = path.read_bytes()
    claims = e.decode(old)["claims"]
    claims["expires_at"] -= 1
    raw = frame.sign("acknowledger", claims)
    path.write_bytes(raw)  # Fixture-owned version substitution; old proposal still pins old provenance.
    changed = replace(proof, provenance_sha256=e.sha(raw))
    value = read(frame, lambda: frame.call(changed))
    assert value["state"] == "unverifiable"
    safe(value, True)
    other = frame.fork(tmp_path / "other-root")
    other.keys, other.private_keys = frame.keys, frame.private_keys
    for source in frame.root.iterdir():
        e.retain(other.root / source.name, source.read_bytes())
    value = read(other, lambda: other.call(changed))
    assert value["state"] == "unverifiable"
    safe(value, True)


def test_staging_links_modes_size_and_inventory_limits_preserve_unexpected_bytes(frame, tmp_path):
    for index, fault in enumerate(("staging", "symlink", "hardlink", "mode", "size", "count")):
        f = frame.fork(tmp_path / str(index))
        proof = f.publish()
        path = f.root / ("9" * 32 + ".proposal.json")
        if fault == "staging":
            e.retain(f.root / ".pending-invented", b"INVENTED interrupted bytes")
        elif fault == "symlink":
            path.symlink_to(__file__)
        elif fault == "hardlink":
            original = tmp_path / ("link-" + str(index))
            e.retain(original, b"INVENTED linked bytes")
            os.link(original, path)
        elif fault == "mode":
            e.retain(path, b"INVENTED broad mode")
            path.chmod(0o644)
        elif fault == "size":
            path.write_bytes(b"x" * (e.MAX_BYTES + 1))
            path.chmod(0o600)
        else:
            for n in range(10):
                e.retain(f.root / (format(n, "032x") + ".proposal.json"), b"INVENTED excess entries")
        value = read(f, lambda: f.call(proof))
        assert value["state"] == "unverifiable"
        safe(value, True)


def test_budget_and_unavailable_mandatory_checks_withhold_all_metadata(frame, monkeypatch):
    proof = frame.publish()
    s = frame.service({ENTRY: proof})
    with monkeypatch.context() as patch:
        patch.setattr(access, "BUDGET_SECONDS", 0)
        patch.setattr(s, "observe", lambda: pytest.fail("Exhausted budget inspected proofs"))
        value = read(frame, lambda: frame.call(proof, service=s))
        assert value["state"] == "budget_exhausted"
        safe(value, True)
    def unavailable(*a, **k):
        raise sqlite3.OperationalError("INVENTED private driver detail")
    with monkeypatch.context() as patch:
        patch.setattr(s.references.verifier.target.planner, "actor", unavailable)
        value = read(frame, lambda: frame.call(proof, service=s))
        assert value["state"] == "unverifiable" and "INVENTED" not in json.dumps(value)
        safe(value, True)


def test_namespace_and_key_registry_races_withhold_accepted_metadata(frame, tmp_path):
    for index, fault in enumerate(("namespace", "keys")):
        f = frame.fork(tmp_path / str(index))
        proof = f.publish()
        s = f.service({ENTRY: proof})
        def changed(_):
            if fault == "namespace":
                e.retain(f.root / ("9" * 32 + ".proposal.json"), b"INVENTED unregistered bytes")
            else:
                s.keys = MappingProxyType({**s.keys, "acknowledger": replace(s.keys["acknowledger"], revoked=True)})
        s.checkpoint = changed
        originals = f.notes.protected()
        value = f.call(proof, service=s)
        assert value["state"] in {"observation_conflict", "unverifiable"}
        safe(value, True)
        assert f.notes.protected() == originals
        if fault == "namespace":
            assert (f.root / ("9" * 32 + ".proposal.json")).read_bytes() == b"INVENTED unregistered bytes"


def test_expired_inputs_new_sessions_and_revoked_preparers_never_renew_review(isolated, monkeypatch):
    proof = isolated.publish()
    with monkeypatch.context() as patch:
        patch.setattr(isolated.notes.pair.source.account, "now", isolated.notes.pair.snapshot["expires_at"])
        value = read(isolated, lambda: isolated.call(proof))
        assert value["state"] == "verification_unavailable"
        safe(value, True)
    scope = short_session(isolated.notes.pair.target.account)  # Declared test setup before the read-only baseline.
    value = read(isolated, lambda: isolated.call(proof, scope=scope))
    assert value["state"] == "unverifiable"
    safe(value, True)
    isolated.notes.pair.target.account.revoke("preparer")
    value = read(isolated, lambda: isolated.call(proof))
    assert value["state"] == "denied"
    safe(value, True)


def test_real_source_and_destination_session_revocations_withhold_proofs(isolated):
    proof = isolated.publish()
    isolated.notes.pair.source.account.revoke("reviewer")
    value = read(isolated, lambda: isolated.call(proof))
    assert value["state"] == "verification_unavailable"
    safe(value, True)
    isolated.notes.pair.target.account.revoke("reviewer")
    value = read(isolated, lambda: isolated.call(proof))
    assert value["state"] == "denied"
    safe(value, True)
