"""Frozen opt-in read-only qualification; invented records and acknowledgement pins."""

import argparse
import json
import os
import sys
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import operator_enrollment_evidence as e  # noqa: E402
import verification_reference_readiness as access  # noqa: E402
from destination_snapshot_fixture import make_pair  # noqa: E402
from operator_recovery_inputs import FLAGS  # noqa: E402
from qualify_destination_snapshot import short_session  # noqa: E402
from verification_reference_fixture import ENTRY, make_frame, retain_external  # noqa: E402

CASES = ("V01_preview_without_publication", "V02_exact_independent_store_binding", "V03_explicit_reference_reobserved",
    "V04_fresh_instance_same_result", "V05_original_expiry_ceiling", "V06_no_acknowledgement_adoption",
    "V07_separate_host_pin_required", "V08_current_receiver_required", "V09_source_cookie_not_receiver_authority",
    "V10_exact_ciphertext_reference", "V11_unknown_entry_not_discovered", "V12_closed_write_operations",
    "V13_budget_exhaustion_withholds_metadata", "V14_fresh_session_requires_revalidation",
    "V15_original_session_and_history_retained", "V16_changed_namespace_withholds_metadata",
    "V17_revoked_source_withholds_metadata", "V18_original_sources_and_reviews_exact",
    "V19_service_reads_never_write", "V20_no_genuine_acknowledgement_or_authority_claim")
NEW = ("scripts/verification_reference_readiness.py", "scripts/verification_reference_fixture.py",
       "scripts/qualify_verification_references.py", "backend/tests/test_verification_reference_readiness.py")


def campaign(root):
    pairs, rows = [], []
    reads = 0

    def row(ident, valid):
        assert ident in CASES and valid
        rows.append({"id": ident, "state": "verified"})

    def call(frame, fn):
        nonlocal reads
        before = frame.protected()
        value = fn()
        assert frame.protected() == before
        assert value["read_only"] and all(value[k] is False for k in FLAGS)
        assert not any(value[k] for k in ("genuine_acknowledgement_verified", "snapshot_verified",
            "destination_attestation_verified", "atomic_snapshot", "joint_rollback_qualified",
            "ready_for_disposable_input_handoff", "ready_for_pinned_disposable_review_handoff"))
        if value["state"] not in {"private_retention_plan_ready", "retained_verification_reobserved"}:
            assert value["retention_plan"] is None and value["reobservation"] is None
            assert not value["retention_plan_ready"] and not value["host_acknowledgement_pin_matched"]
        reads += 1
        return value

    try:
        p = make_pair(root / "accepted")
        pairs.append(p)
        limited = short_session(p.target.account)  # Fixture-owned setup before immutable baseline.
        original = p.protected()
        f = make_frame(p, root / "records")
        preview = call(f, f.preview)
        row("V01_preview_without_publication", preview["state"] == "private_retention_plan_ready" and not tuple(f.store.root.iterdir()))
        row("V02_exact_independent_store_binding", preview["retention_plan"]["plan"]["store_context_sha256"] == f.service().binding())
        ref, ack = retain_external(f)  # Independent fixture writer; service has no publication route.
        current = call(f, lambda: f.reobserve(ref, ack))
        row("V03_explicit_reference_reobserved", current["state"] == "retained_verification_reobserved"
            and current["reobservation"]["reference_sha256"] == ref.sha256)
        row("V04_fresh_instance_same_result", current == call(f, lambda: f.reobserve(ref, ack)))
        row("V05_original_expiry_ceiling", current["reobservation"]["original_handoff_expires_at"] == p.snapshot["expires_at"]
            and current["reobservation"]["expires_at"] <= p.snapshot["expires_at"])
        held = call(f, lambda: f.reobserve(replace(ref, acknowledgement_sha256=None), ack))
        row("V06_no_acknowledgement_adoption", held["state"] == "acknowledgement_required")
        held = call(f, lambda: f.reobserve(ref))
        row("V07_separate_host_pin_required", held["state"] == "acknowledgement_pin_required")
        held = call(f, lambda: f.reobserve(ref, ack, scope=p.target.account.scope("other")))
        row("V08_current_receiver_required", held["state"] == "denied")
        held = call(f, lambda: f.reobserve(ref, ack, scope=p.source.account.scope("reviewer")))
        row("V09_source_cookie_not_receiver_authority", held["state"] == "denied")
        s = f.service(references={ENTRY: ref}, acknowledgements={ack.sha256: ack})
        held = call(f, lambda: s.dispatch(p.target.account.scope("reviewer"), "reobserve", entry_id=ENTRY,
            reference={**asdict(ref), "ciphertext_sha256": "0" * 64}))
        row("V10_exact_ciphertext_reference", held["state"] == "unverifiable")
        held = call(f, lambda: s.dispatch(p.target.account.scope("reviewer"), "reobserve", entry_id="a" * 32,
            reference=asdict(ref)))
        row("V11_unknown_entry_not_discovered", held["state"] == "unverifiable")
        held = call(f, lambda: s.dispatch(p.target.account.scope("reviewer"), "retain", entry_id=ENTRY, reference=asdict(ref)))
        row("V12_closed_write_operations", held["state"] == "unverifiable")
        old = access.BUDGET_SECONDS
        try:
            access.BUDGET_SECONDS = 0
            held = call(f, lambda: f.reobserve(ref, ack))
        finally:
            access.BUDGET_SECONDS = old
        row("V13_budget_exhaustion_withholds_metadata", held["state"] == "budget_exhausted")
        held = call(f, lambda: f.reobserve(ref, ack, scope=limited))
        fresh = call(f, lambda: f.preview(scope=limited))
        row("V14_fresh_session_requires_revalidation", held["state"] == "retained_verification_needs_revalidation"
            and fresh["retention_plan"]["plan_sha256"] != ack.plan_sha256
            and fresh["retention_plan"]["plan"]["verification"]["expires_at"] == p.target.account.now + 30)
        row("V15_original_session_and_history_retained", current == call(f, lambda: f.reobserve(ref, ack)) and p.protected() == original)
        unregistered = f.store.root / ("9" * 32 + ".receipt")
        before = p.protected()
        def changed(_):
            e.retain(unregistered, b"INVENTED unregistered bytes")
        held = f.reobserve(ref, ack, checkpoint=changed)
        # This one deliberate fixture injection is the sole expected delta, never a service write.
        assert p.protected() == before and unregistered.read_bytes() == b"INVENTED unregistered bytes"
        assert held["retention_plan"] is None and held["reobservation"] is None
        row("V16_changed_namespace_withholds_metadata", held["state"] == "observation_conflict")
        q = make_pair(root / "revoked")
        pairs.append(q)
        g = make_frame(q, root / "revoked-records")
        ref2, ack2 = retain_external(g)
        source_originals = q.protected()
        q.source.account.revoke("reviewer")  # Fixture-owned revocation, never restoration or service mutation.
        held = call(g, lambda: g.reobserve(ref2, ack2))
        row("V17_revoked_source_withholds_metadata", held["state"] == "verification_unavailable")
        row("V18_original_sources_and_reviews_exact", p.protected() == original and all(
            q.protected()[i][:2] == source_originals[i][:2] for i in (0, 1)))
        row("V19_service_reads_never_write", reads == 15)
        row("V20_no_genuine_acknowledgement_or_authority_claim", not current["genuine_acknowledgement_verified"]
            and all(current[k] is False for k in FLAGS))
        assert rows == [{"id": name, "state": "verified"} for name in CASES]
        return {"cases": rows, "fixture_pairs": 2, "isolated_account_contexts": 4,
            "retained_original_review_records": 4, "fixture_retained_verification_records": 2,
            "service_reads": reads + 1, "service_writes": 0, "declared_fixture_revocations": 1,
            "declared_fixture_namespace_injections": 1, "source_inputs_and_review_history_exact": True,
            "account_bytes_exact_except_declared_fixture_revocation": True,
            "original_expiry_ceiling_preserved": True, "genuine_acknowledgement_verified": False,
            "acknowledgement_basis": "independently supplied invented host pins; genuine provenance and durability unqualified",
            "native_mount_qualification": False, "listener_started": False, "provider_requests": 0,
            "model_requests": 0, **dict.fromkeys(FLAGS, False)}
    finally:
        for pair in pairs:
            pair.close()


def run():
    prior = ROOT / "docs/evidence/destination-snapshot-2026-11-04.json"
    old = json.loads(prior.read_bytes())
    hashes = {**old["source_sha256"], **{n: e.sha((ROOT / n).read_bytes()) for n in NEW}}
    assert len(old["source_sha256"]) == 773 and len(hashes) == 777
    assert all(e.sha((ROOT / n).read_bytes()) == digest for n, digest in hashes.items())
    with tempfile.TemporaryDirectory(prefix="lawyer-verification-reference-") as name:
        evidence = campaign(Path(name).resolve())
    assert all(e.sha((ROOT / n).read_bytes()) == digest for n, digest in hashes.items())
    return {"schema": "verification-reference-qualification-v1", "status": "qualified",
        "scope": "local invented read-only retention readiness and exact reference re-observation only",
        "case_plan_sha256": e.sha(e.encode(CASES)), "source_sha256": hashes,
        "prior_destination_report_sha256": e.sha(prior.read_bytes()), "evidence": evidence,
        "production_activation": False, "legal_qualification": False,
        "not_qualified": ["genuine acknowledgement provenance or durability", "retention authorization or key custody",
            "production writes or restore", "native mounts or listeners", "cross-store atomicity or joint rollback",
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
    except Exception as exc:  # noqa: BLE001 - disclose only the type.
        args.output.write_text(json.dumps({"status": "incomplete", "error_type": type(exc).__name__}) + "\n")
        raise SystemExit("Verification reference qualification incomplete") from None
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"qualified": True, "outcomes": len(CASES), "production_activation": False}))
