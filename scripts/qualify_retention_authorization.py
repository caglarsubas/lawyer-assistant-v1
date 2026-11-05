"""Frozen opt-in retention-review campaign; invented identities and signing keys only."""

import argparse
import json
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import operator_enrollment_evidence as e  # noqa: E402
import retention_authorization_readiness as access  # noqa: E402
from destination_snapshot_fixture import make_pair  # noqa: E402
from operator_recovery_inputs import FLAGS  # noqa: E402
from retention_authorization_fixture import ENTRY, make  # noqa: E402

CASES = ("A01_independent_roles_and_keys", "A02_signed_metadata_accepted", "A03_exact_versions_bound",
    "A04_fresh_reopen_same_result", "A05_original_expiry_ceiling", "A06_unassigned_actor_denied",
    "A07_request_key_provisioning_rejected", "A08_changed_proof_reference_rejected",
    "A09_revoked_issuer_key_rejected", "A10_changes_required_not_promoted", "A11_rejected_review_not_promoted",
    "A12_wrong_signed_purpose_rejected", "A13_signed_custody_claim_rejected", "A14_checked_budget_withholds_metadata",
    "A15_namespace_race_retained", "A16_revoked_preparer_withheld", "A17_revoked_source_withheld",
    "A18_original_sources_and_review_history_exact", "A19_service_reads_never_write", "A20_no_genuine_authority_claim")
NEW = ("scripts/retention_authorization_readiness.py", "scripts/retention_authorization_fixture.py",
       "scripts/qualify_retention_authorization.py", "backend/tests/test_retention_authorization_readiness.py")


def campaign(root):
    pairs, originals, rows, retained = [], [], [], []
    calls = 0

    def create(name):
        pair = make_pair(root / (name + "-pair"))
        pairs.append(pair)
        f = make(pair, root / (name + "-records"))
        originals.append(pair.protected())
        return f

    def call(f, callback):
        nonlocal calls
        before = f.protected()
        value = callback()
        assert f.protected() == before
        assert value["read_only"] and all(value[k] is False for k in FLAGS)
        assert not any(value[k] for k in ("retention_authorized", "genuine_acknowledgement_verified", "durability_qualified",
            "snapshot_verified", "destination_attestation_verified", "atomic_snapshot", "joint_rollback_qualified"))
        if value["state"] != "ready_for_disposable_retention_planning":
            assert value["evidence"] is None and not value["ready_for_disposable_retention_planning"]
            assert not value["independent_disposable_review_checked"] and not value["signed_provenance_matches_host_pins"]
        calls += 1
        return value

    def row(ident, condition):
        assert ident in CASES and condition
        rows.append({"id": ident, "state": "verified"})

    def publish(f, **options):
        proof = f.publish(**options)
        retained.append((f, proof))
        return proof

    try:
        f, g = create("accepted"), create("source-revoked")
        proof, other = publish(f), publish(g)
        row("A01_independent_roles_and_keys", len({k.principal_id for k in f.keys.values()}) == 3
            and len({k.public_key for k in f.keys.values()}) == 3)
        first = call(f, lambda: f.call(proof))
        row("A02_signed_metadata_accepted", first["state"] == "ready_for_disposable_retention_planning"
            and first["independent_disposable_review_checked"] and first["signed_provenance_matches_host_pins"])
        row("A03_exact_versions_bound", first["evidence"]["proof_set_sha256"] == proof.sha256
            and first["evidence"]["provenance_sha256"] == proof.provenance_sha256)
        row("A04_fresh_reopen_same_result", first == call(f, lambda: f.call(proof)))
        row("A05_original_expiry_ceiling", first["evidence"]["expires_at"] <= f.notes.pair.snapshot["expires_at"]
            and first["evidence"]["original_handoff_expires_at"] == f.notes.pair.snapshot["expires_at"])
        held = call(f, lambda: f.call(proof, scope=f.notes.pair.target.account.scope("other")))
        row("A06_unassigned_actor_denied", held["state"] == "denied")
        s = f.service({ENTRY: proof})
        scope = f.notes.pair.target.account.scope("reviewer")
        held = call(f, lambda: s.dispatch(scope, "inspect", entry_id=ENTRY, proof_set_sha256=proof.sha256, keys={}))
        row("A07_request_key_provisioning_rejected", held["state"] == "unverifiable")
        held = call(f, lambda: s.dispatch(scope, "inspect", entry_id=ENTRY, proof_set_sha256="0" * 64))
        row("A08_changed_proof_reference_rejected", held["state"] == "unverifiable")
        keys = {**f.keys, "acknowledger": replace(f.keys["acknowledger"], revoked=True)}
        held = call(f, lambda: f.call(proof, service=f.service({ENTRY: proof}, keys=keys)))
        row("A09_revoked_issuer_key_rejected", held["state"] == "unverifiable")
        for decision, ident in [("changes_required", "A10_changes_required_not_promoted"), ("reject", "A11_rejected_review_not_promoted")]:
            negative = publish(f, decision=decision)
            held = call(f, lambda: f.call(negative))
            row(ident, held["state"] == "independent_review_not_accepted")
        for index, kind, name, replacement, ident in [(0, "preparer", "purpose", "production_retention", "A12_wrong_signed_purpose_rejected"),
                (1, "acknowledger", "custody_status", "approved", "A13_signed_custody_claim_rejected")]:
            fork = f.fork(root / ("fault-" + str(index)))
            def mutate(selected, claims):
                if selected == kind:
                    claims[name] = replacement
            changed = publish(fork, mutate=mutate)
            held = call(fork, lambda: fork.call(changed))
            row(ident, held["state"] == "unverifiable")
        old = access.BUDGET_SECONDS
        try:
            access.BUDGET_SECONDS = 0
            held = call(f, lambda: f.call(proof))
        finally:
            access.BUDGET_SECONDS = old
        row("A14_checked_budget_withholds_metadata", held["state"] == "budget_exhausted")
        injected = f.root / ("9" * 32 + ".proposal.json")
        before = f.notes.protected()
        def race(_):
            e.retain(injected, b"INVENTED interrupted metadata")
        held = f.call(proof, service=f.service({ENTRY: proof}, checkpoint=race))
        assert f.notes.protected() == before and injected.read_bytes() == b"INVENTED interrupted metadata"
        row("A15_namespace_race_retained", held["state"] == "observation_conflict" and held["evidence"] is None)
        f.notes.pair.target.account.revoke("preparer")  # Declared fixture-only revocation.
        held = call(f, lambda: f.call(proof))
        row("A16_revoked_preparer_withheld", held["state"] == "denied")
        g.notes.pair.source.account.revoke("reviewer")  # Declared fixture-only revocation.
        held = call(g, lambda: g.call(other))
        row("A17_revoked_source_withheld", held["state"] == "verification_unavailable")
        row("A18_original_sources_and_review_history_exact", all(
            pair.protected()[i][:2] == baseline[i][:2] for pair, baseline in zip(pairs, originals, strict=True) for i in (0, 1)))
        row("A19_service_reads_never_write", calls == 13)
        row("A20_no_genuine_authority_claim", not first["retention_authorized"] and not first["genuine_acknowledgement_verified"]
            and not first["durability_qualified"] and all(first[k] is False for k in FLAGS))
        assert rows == [{"id": ident, "state": "verified"} for ident in CASES]
        assert len(retained) == 6 and all(e.sha(e.read(f.root / (p.proof_id + "." + suffix + ".json"))) == digest
            for f, p in retained for suffix, digest in (("proposal", p.proposal_sha256),
                ("decision", p.decision_sha256), ("provenance", p.provenance_sha256)))
        return {"cases": rows, "fixture_pairs": 2, "isolated_account_contexts": 4,
            "retained_original_review_records": 4, "fixture_verification_records": 2,
            "fixture_signed_envelopes": 3 * len(retained), "disposable_signing_keys": 12,
            "service_reads": calls + 1, "service_writes": 0, "declared_fixture_revocations": 2,
            "declared_fixture_namespace_injections": 1, "source_inputs_and_review_history_exact": True,
            "account_bytes_exact_except_declared_fixture_revocations": True,
            "original_expiry_ceiling_preserved": True, "retention_authorized": False,
            "genuine_acknowledgement_verified": False, "durability_qualified": False,
            "provenance_basis": "signed metadata verified against independent invented host pins; real custody, enrollment and durability unqualified",
            "native_mount_qualification": False, "listener_started": False, "provider_requests": 0, "model_requests": 0,
            **dict.fromkeys(FLAGS, False)}
    finally:
        for pair in pairs:
            pair.close()


def run():
    prior = ROOT / "docs/evidence/verification-reference-2026-11-04.json"
    previous = json.loads(prior.read_bytes())
    hashes = {**previous["source_sha256"], **{n: e.sha((ROOT / n).read_bytes()) for n in NEW}}
    assert len(previous["source_sha256"]) == 777 and len(hashes) == 781
    assert all(e.sha((ROOT / n).read_bytes()) == sha for n, sha in hashes.items())
    with tempfile.TemporaryDirectory(prefix="lawyer-retention-authorization-") as name:
        evidence = campaign(Path(name).resolve())
    assert all(e.sha((ROOT / n).read_bytes()) == sha for n, sha in hashes.items())
    return {"schema": "retention-authorization-qualification-v1", "status": "qualified",
        "scope": "local invented independently reviewed retention metadata and signed host-pin provenance only",
        "case_plan_sha256": e.sha(e.encode(CASES)), "source_sha256": hashes,
        "prior_verification_report_sha256": e.sha(prior.read_bytes()), "evidence": evidence,
        "production_activation": False, "legal_qualification": False,
        "not_qualified": ["genuine key enrollment or signing custody", "storage durability or acknowledgement-channel authenticity",
            "production retention authorization or writes", "native mounts or listeners", "cross-store atomicity or rollback",
            "recovery or trust renewal", "production deployment", "owner legal review"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    with args.output.open("x") as stream:
        stream.write('{"status":"incomplete"}\n')
    try:
        report = run()
    except Exception as exc:  # noqa: BLE001 - disclose only an error type.
        args.output.write_text(json.dumps({"status": "incomplete", "error_type": type(exc).__name__}) + "\n")
        raise SystemExit("Retention authorization qualification incomplete") from None
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"qualified": True, "outcomes": len(CASES), "production_activation": False}))
