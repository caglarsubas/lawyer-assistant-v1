"""Opt-in frozen local receiver campaign; invented accounts and pins only."""

import argparse
import json
import os
import sys
import tempfile
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import destination_snapshot_verification as verification  # noqa: E402
import operator_enrollment_evidence as e  # noqa: E402
from destination_snapshot_fixture import make_pair  # noqa: E402
from operator_recovery_inputs import FLAGS  # noqa: E402
from recovery_inventory_fixture import DESTINATION, ENTRY  # noqa: E402

CASES = ("D01_separate_receiver_session", "D02_exact_packet_and_references", "D03_original_expiry_ceiling",
    "D04_fresh_receiver_exact_result", "D05_verification_grants_no_execution", "D06_unassigned_receiver_denied",
    "D07_source_cookie_is_not_receiver_authority", "D08_receiver_cookie_is_not_source_authority",
    "D09_changed_source_inventory_withheld", "D10_changed_review_version_withheld",
    "D11_changed_destination_pin_withheld", "D12_extra_packet_fields_rejected", "D13_checked_budget_fails_closed",
    "D14_short_receiver_session_restricts_expiry", "D15_destination_journal_race_withheld",
    "D16_injected_ciphertext_retained", "D17_missing_acknowledgement_not_adopted",
    "D18_negative_independent_review_not_promoted", "D19_expired_source_snapshot_withheld",
    "D20_interrupted_destination_staging_retained", "D21_original_source_and_review_bytes_exact",
    "D22_disposable_account_bytes_exact", "D23_service_reads_do_not_write", "D24_no_genuine_attestation_claim")
NEW = ("scripts/destination_snapshot_verification.py", "scripts/destination_snapshot_fixture.py",
       "scripts/qualify_destination_snapshot.py", "backend/tests/test_destination_snapshot_verification.py")
CI = ("scripts/ci_materialization_capacity.py", "deploy/fixtures/materialization_capacity_partition.json",
      "backend/tests/test_ci_materialization_capacity.py")


def candidate(pair):
    return pair.snapshot or {"entry_id": ENTRY, "reference_sha256": pair.reference.sha256,
        "inventory_sha256": "0" * 64, "destination_id": DESTINATION,
        "destination_context_sha256": pair.pin.destination_context_sha256,
        "destination_pin_sha256": pair.pin.sha256, "expires_at": pair.pin.expires_at}


def short_session(account):
    from app.auth import create_session
    from app.db import LoginSession, User, digest
    with account.store.session() as session:
        cookie, csrf = create_session(session, session.get(User, account.ids["reviewer"]), 1)
        session.get(LoginSession, digest(cookie)).expires_at = datetime.fromtimestamp(account.now + 30, timezone.utc).isoformat()
        session.commit()
    return {**account.scope("reviewer"), "headers": [(b"cookie", ("la_session=" + cookie).encode()),
        (b"x-csrf-token", csrf.encode()), (b"origin", b"http://operator.invalid")]}


def campaign(root):
    pairs, originals, rows = [], [], []
    calls = 0

    def pair(name, **options):
        value = make_pair(root / name, **options)
        pairs.append(value)
        # Extra session is fixture setup, before the immutable account baseline.
        limited = short_session(value.target.account) if name == "accepted" else None
        originals.append(value.protected())
        return value, limited

    def call(p, callback, injected=None):
        nonlocal calls
        before = p.protected()
        value = callback()
        expected = deepcopy(before)
        if injected is not None:
            name, raw = injected
            expected[1][1][name] = raw
        assert p.protected() == expected
        assert all(value[k] is False for k in FLAGS)
        assert not value["destination_attestation_verified"] and not value["ready_for_pinned_disposable_review_handoff"]
        assert not value["ready_for_disposable_input_handoff"] and not value["atomic_snapshot"] and not value["joint_rollback_qualified"]
        assert value["handoff"] is None and value["inventory"] is None
        if value["state"] != "destination_snapshot_verified":
            assert not value["snapshot_verified"] and value["verification"] is None
        calls += 1
        return value

    def row(ident, condition):
        assert ident in CASES and condition
        rows.append({"id": ident, "state": "verified"})

    try:
        p, limited = pair("accepted")
        first = call(p, lambda: p.call())
        row("D01_separate_receiver_session", first["state"] == "destination_snapshot_verified"
            and p.source.account.authority.file_identity != p.target.account.authority.file_identity)
        row("D02_exact_packet_and_references", first["verification"]["snapshot_sha256"] ==
            verification.Snapshot.parse(p.snapshot).sha256 and first["verification"]["reference_sha256"] == p.reference.sha256)
        row("D03_original_expiry_ceiling", first["verification"]["original_handoff_expires_at"] == p.snapshot["expires_at"]
            and first["verification"]["expires_at"] <= p.snapshot["expires_at"])
        again = call(p, lambda: p.call(p.verifier()))
        row("D04_fresh_receiver_exact_result", first == again)
        row("D05_verification_grants_no_execution", all(first[k] is False for k in FLAGS)
            and not first["ready_for_pinned_disposable_review_handoff"])
        held = call(p, lambda: p.call(scope=p.target.account.scope("other")))
        row("D06_unassigned_receiver_denied", held["state"] == "denied")
        held = call(p, lambda: p.call(scope=p.source.account.scope("reviewer")))
        row("D07_source_cookie_is_not_receiver_authority", held["state"] == "denied")
        held = call(p, lambda: p.call(p.verifier(source_scope=p.target.account.scope("reviewer"))))
        row("D08_receiver_cookie_is_not_source_authority", held["state"] == "source_snapshot_unavailable")
        held = call(p, lambda: p.call(snapshot={**p.snapshot, "inventory_sha256": "0" * 64}))
        row("D09_changed_source_inventory_withheld", held["state"] == "source_snapshot_unavailable")
        held = call(p, lambda: p.call(reference={**asdict(p.reference), "review_ciphertext_sha256": "0" * 64}))
        row("D10_changed_review_version_withheld", held["state"] == "unverifiable")
        held = call(p, lambda: p.call(snapshot={**p.snapshot, "destination_pin_sha256": "0" * 64}))
        row("D11_changed_destination_pin_withheld", held["state"] == "snapshot_binding_mismatch")
        held = call(p, lambda: p.call(snapshot={**p.snapshot, "execute": True}))
        row("D12_extra_packet_fields_rejected", held["state"] == "unverifiable")
        old = verification.BUDGET_SECONDS
        try:
            verification.BUDGET_SECONDS = 0
            held = call(p, lambda: p.call())
        finally:
            verification.BUDGET_SECONDS = old
        row("D13_checked_budget_fails_closed", held["state"] == "budget_exhausted")
        shorter = call(p, lambda: p.call(scope=limited))
        row("D14_short_receiver_session_restricts_expiry", shorter["state"] == "destination_snapshot_verified"
            and shorter["verification"]["expires_at"] == p.target.account.now + 30
            and shorter["verification"]["original_handoff_expires_at"] == p.snapshot["expires_at"])
        injected_name, injected_raw = "8" * 32 + ".receipt", b"INVENTED unregistered destination record"
        def changed(_):
            e.retain(p.target.sidecar.root / injected_name, injected_raw)
        held = call(p, lambda: p.call(p.verifier(checkpoint=changed)), (injected_name, injected_raw))
        row("D15_destination_journal_race_withheld", held["state"] == "observation_conflict")
        row("D16_injected_ciphertext_retained", (p.target.sidecar.root / injected_name).read_bytes() == injected_raw)
        missing, _ = pair("missing", acknowledged=False)
        held = call(missing, lambda: missing.call(snapshot=candidate(missing)))
        row("D17_missing_acknowledgement_not_adopted", held["state"] == "source_snapshot_unavailable")
        negative, _ = pair("negative", decision="changes_required")
        held = call(negative, lambda: negative.call(snapshot=candidate(negative)))
        row("D18_negative_independent_review_not_promoted", held["state"] == "source_snapshot_unavailable")
        p.source.account.now = p.snapshot["expires_at"]
        held = call(p, lambda: p.call())
        row("D19_expired_source_snapshot_withheld", held["state"] == "source_snapshot_unavailable")
        pending = missing.target.sidecar.root / ".pending-invented"
        e.retain(pending, b"INVENTED interrupted bytes")
        held = call(missing, lambda: missing.call(snapshot=candidate(missing)))
        row("D20_interrupted_destination_staging_retained", held["state"] == "unverifiable" and pending.is_file())
        row("D21_original_source_and_review_bytes_exact", all(
            current[i][0] == original[i][0] and all(current[i][1][n] == raw for n, raw in original[i][1].items())
            for pair2, original in zip(pairs, originals, strict=True) for current in [pair2.protected()] for i in (0, 1)))
        row("D22_disposable_account_bytes_exact", all(pair2.protected()[i][2] == original[i][2]
            for pair2, original in zip(pairs, originals, strict=True) for i in (0, 1)))
        row("D23_service_reads_do_not_write", calls == 16)
        row("D24_no_genuine_attestation_claim", all(first[k] is False for k in FLAGS)
            and not first["destination_attestation_verified"])
        assert rows == [{"id": name, "state": "verified"} for name in CASES]
        return {"cases": rows, "fixture_pairs": 3, "isolated_account_contexts": 6,
            "retained_original_review_records": 6, "injected_retained_entries": 2,
            "service_reads": calls, "service_writes": 0, "source_inputs_accounts_and_review_history_exact": True,
            "real_source_and_receiver_sessions_exercised": True, "original_expiry_ceiling_preserved": True,
            "destination_pin_basis": "independently supplied invented fixture pins; genuine provenance unqualified",
            "native_mount_qualification": False, "listener_started": False, "provider_requests": 0,
            "model_requests": 0, "destination_attestation_verified": False, **dict.fromkeys(FLAGS, False)}
    finally:
        for p in pairs:
            p.close()


def run():
    prior = ROOT / "docs/evidence/recovery-review-inventory-2026-11-04.json"
    old = json.loads(prior.read_bytes())
    hashes = {**old["source_sha256"], **{n: e.sha((ROOT / n).read_bytes()) for n in NEW + CI}}
    assert len(old["source_sha256"]) == 766 and len(hashes) == 773
    assert all(e.sha((ROOT / n).read_bytes()) == digest for n, digest in hashes.items())
    with tempfile.TemporaryDirectory(prefix="lawyer-destination-snapshot-") as name:
        evidence = campaign(Path(name).resolve())
    assert all(e.sha((ROOT / n).read_bytes()) == digest for n, digest in hashes.items())
    return {"schema": "destination-snapshot-qualification-v1", "status": "qualified",
        "scope": "local invented destination-side read-only snapshot verification only",
        "case_plan_sha256": e.sha(e.encode(CASES)), "source_sha256": hashes,
        "prior_inventory_report_sha256": e.sha(prior.read_bytes()), "evidence": evidence,
        "production_activation": False, "legal_qualification": False,
        "not_qualified": ["genuine destination provisioning or custody", "external channel authenticity",
            "native mounts or listeners", "cross-store atomicity or privileged joint rollback",
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
    except Exception as exc:  # noqa: BLE001 - only an error type is disclosed.
        args.output.write_text(json.dumps({"status": "incomplete", "error_type": type(exc).__name__}) + "\n")
        raise SystemExit("Destination qualification incomplete") from None
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"qualified": True, "outcomes": len(CASES), "production_activation": False}))
