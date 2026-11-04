"""Frozen opt-in local campaign; no native listener, provider or live matter."""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import operator_enrollment_evidence as e  # noqa: E402
from operator_recovery_inputs import FLAGS  # noqa: E402
from recovery_input_fixture import make  # noqa: E402
from recovery_inventory_fixture import (  # noqa: E402
    DESTINATION,
    ENTRY,
    handoff,
    invented_pin,
    retained_reference,
    service,
)

CASES = ("V01_acknowledged_registry_only", "V02_exact_retained_versions", "V03_inventory_grants_no_handoff",
    "V04_destination_pin_required", "V05_exact_pinned_handoff", "V06_original_expiry_not_extended",
    "V07_fresh_instance_exact_inventory", "V08_changed_snapshot_withheld", "V09_missing_reference_not_adopted",
    "V10_destination_binding_mismatch", "V11_unassigned_caller_denied", "V12_actor_bound_snapshot",
    "V13_unregistered_ciphertext_not_listed", "V14_added_ciphertext_invalidates_old_snapshot",
    "V15_expired_history_retained", "V16_lost_acknowledgement_not_recovered",
    "V17_negative_independent_review_retained", "V18_racing_source_withheld",
    "V19_interrupted_staging_retained", "V20_original_inputs_accounts_and_history_exact")
NEW = ("scripts/recovery_review_inventory.py", "scripts/recovery_inventory_fixture.py",
       "scripts/qualify_recovery_review_inventory.py", "backend/tests/test_recovery_review_inventory.py")
CI = ("scripts/ci_authority_trials.py", "backend/tests/test_ci_authority_trials.py",
      "scripts/run_ci_reserve_guard_v2.py", "scripts/ci_recovery_inventory.py",
      "deploy/fixtures/recovery_review_inventory_partition.json")


def snapshot(f):
    return (f.protected(), {p.name: p.read_bytes() for p in f.sidecar.root.iterdir()},
        {str(p.relative_to(f.account.profile)): e.sha(p.read_bytes())
         for p in f.account.profile.rglob("*") if p.is_file()})


def campaign(root):
    fixtures, originals, history, rows = [], [], [], []

    def fixture(name, **options):
        f = make(root / name)
        fixtures.append(f)
        originals.append((f.protected(), snapshot(f)[2]))
        ref = retained_reference(f, **options)
        history.append(snapshot(f)[1])
        return f, ref

    def call(f, callback):
        before = snapshot(f)
        value = callback()
        assert snapshot(f) == before
        assert all(value[k] is False for k in FLAGS) and value["destination_attestation_verified"] is False
        return value

    def observed(f, s, role="reviewer"):
        value = call(f, lambda: s.dispatch(f.account.scope(role), "inventory"))
        assert value["state"] == "acknowledged_review_inventory"
        return value

    def row(name, condition):
        assert name in CASES and condition
        rows.append({"id": name, "state": "verified"})

    try:
        f, ref = fixture("accepted")
        s = service(f, ref)
        o = observed(f, s)
        entry = o["inventory"]["entries"][0]
        row("V01_acknowledged_registry_only", len(o["inventory"]["entries"]) == 1 and entry["entry_id"] == ENTRY)
        row("V02_exact_retained_versions", entry["reference"] == asdict(ref))
        row("V03_inventory_grants_no_handoff", o["ready_for_pinned_disposable_review_handoff"] is False)
        missing = call(f, lambda: handoff(s, f, ref, o))
        row("V04_destination_pin_required", missing["state"] == "destination_pin_required")
        pin = invented_pin(f, ref)
        s = service(f, ref, pin=pin)
        o = observed(f, s)
        ready = call(f, lambda: handoff(s, f, ref, o))
        row("V05_exact_pinned_handoff", ready["ready_for_pinned_disposable_review_handoff"]
            and ready["handoff"]["reference_sha256"] == ref.sha256)
        row("V06_original_expiry_not_extended", ready["handoff"]["expires_at"] ==
            min(pin.expires_at, o["inventory"]["entries"][0]["review"]["expires_at"]))
        row("V07_fresh_instance_exact_inventory", observed(f, service(f, ref, pin=pin)) == o)
        mismatch = call(f, lambda: s.dispatch(f.account.scope("reviewer"), "handoff", entry_id=ENTRY,
            reference=asdict(ref), destination_id=DESTINATION, expected_inventory_sha256="0" * 64))
        row("V08_changed_snapshot_withheld", mismatch["state"] == "observation_conflict")
        missing_ref = call(f, lambda: s.dispatch(f.account.scope("reviewer"), "handoff", entry_id=ENTRY,
            reference={**asdict(ref), "decision_ciphertext_sha256": None}, destination_id=DESTINATION,
            expected_inventory_sha256=o["inventory"]["inventory_sha256"]))
        row("V09_missing_reference_not_adopted", missing_ref["state"] == "unverifiable")
        other = service(f, ref, pin=replace(pin, selection_sha256="0" * 64))
        other_o = observed(f, other)
        held = call(f, lambda: handoff(other, f, ref, other_o))
        row("V10_destination_binding_mismatch", held["state"] == "destination_pin_mismatch")
        denied = call(f, lambda: s.dispatch(f.account.scope("other"), "inventory"))
        row("V11_unassigned_caller_denied", denied["state"] == "denied" and denied["inventory"] is None)
        preparer_o = observed(f, s, "preparer")
        held = call(f, lambda: handoff(s, f, ref, preparer_o))
        row("V12_actor_bound_snapshot", held["state"] == "observation_conflict")
        e.retain(f.sidecar.root / ("9" * 32 + ".receipt"), next(f.sidecar.root.iterdir()).read_bytes())
        new = observed(f, s)
        row("V13_unregistered_ciphertext_not_listed", len(new["inventory"]["entries"]) == 1)
        held = call(f, lambda: handoff(s, f, ref, o))
        row("V14_added_ciphertext_invalidates_old_snapshot", held["state"] == "observation_conflict")
        f.account.now += 301
        expired = observed(f, s)
        row("V15_expired_history_retained", expired["inventory"]["entries"][0]["state"] ==
            "review_retained_needs_revalidation" and all(snapshot(f)[1][n] == b for n, b in history[0].items()))
        pending, pending_ref = fixture("unacknowledged", acknowledged=False)
        pending_s = service(pending, pending_ref)
        pending_o = observed(pending, pending_s)
        row("V16_lost_acknowledgement_not_recovered", pending_o["inventory"]["entries"][0]["state"] ==
            "decision_reference_required" and pending_o["inventory"]["entries"][0]["decision"] is None)
        negative, negative_ref = fixture("negative", decision="changes_required")
        negative_s = service(negative, negative_ref, pin=invented_pin(negative, negative_ref))
        negative_o = observed(negative, negative_s)
        held = call(negative, lambda: handoff(negative_s, negative, negative_ref, negative_o))
        row("V17_negative_independent_review_retained", held["state"] == "independent_acceptance_required"
            and negative_o["inventory"]["entries"][0]["state"] == "changes_required")
        racing = service(negative, negative_ref, checkpoint=lambda _: setattr(negative.account, "now", negative.account.now + 301))
        held = call(negative, lambda: racing.dispatch(negative.account.scope("reviewer"), "inventory"))
        row("V18_racing_source_withheld", held["state"] == "observation_conflict" and held["inventory"] is None)
        e.retain(pending.sidecar.root / ".pending-invented", b"INVENTED interrupted staging")
        held = call(pending, lambda: pending_s.dispatch(pending.account.scope("reviewer"), "inventory"))
        row("V19_interrupted_staging_retained", held["state"] == "unverifiable" and held["inventory"] is None
            and (pending.sidecar.root / ".pending-invented").is_file())
        row("V20_original_inputs_accounts_and_history_exact", all(f2.protected() == original[0]
            and snapshot(f2)[2] == original[1] and all(snapshot(f2)[1][n] == b for n, b in h.items())
            for f2, original, h in zip(fixtures, originals, history, strict=True)))
        assert rows == [{"id": name, "state": "verified"} for name in CASES]
        return {"cases": rows, "fixture_contexts": 3, "retained_original_review_records": 6,
            "injected_retained_entries": 2, "service_writes": 0, "real_session_auth_exercised": True,
            "original_inputs_accounts_and_review_history_exact": True,
            "destination_pin_basis": "separately supplied invented fixture pins; genuine provenance unqualified",
            "native_mount_qualification": False, "listener_started": False, "provider_requests": 0,
            "model_requests": 0, **dict.fromkeys(FLAGS, False)}
    finally:
        for f in fixtures:
            f.account.store.engine.dispose()


def run():
    prior = ROOT / "docs/evidence/reviewed-recovery-inputs-2026-11-04.json"
    old = json.loads(prior.read_bytes())
    hashes = {**old["source_sha256"], **{n: e.sha((ROOT / n).read_bytes()) for n in NEW + CI}}
    assert len(old["source_sha256"]) == 757 and len(hashes) == 766
    assert all(e.sha((ROOT / n).read_bytes()) == value for n, value in hashes.items())
    with tempfile.TemporaryDirectory(prefix="lawyer-review-inventory-") as name:
        evidence = campaign(Path(name).resolve())
    assert all(e.sha((ROOT / n).read_bytes()) == value for n, value in hashes.items())
    return {"schema": "recovery-review-inventory-qualification-v1", "status": "qualified",
        "scope": "local invented acknowledged-review inventory and pinned metadata handoff only",
        "case_plan_sha256": e.sha(e.encode(CASES)), "source_sha256": hashes,
        "prior_review_report_sha256": hashlib.sha256(prior.read_bytes()).hexdigest(), "evidence": evidence,
        "production_activation": False, "legal_qualification": False,
        "not_qualified": ["genuine destination pin provenance or appointment", "external checksum channel authenticity",
            "native mounts or listeners in this campaign", "privileged joint rollback", "recovery execution",
            "production deployment", "owner legal review"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    with args.output.open("x") as stream:
        stream.write('{"status":"incomplete"}\n')
    try:
        report = run()
    except Exception as exc:  # noqa: BLE001 - no private values or receipts.
        args.output.write_text(json.dumps({"status": "incomplete", "error_type": type(exc).__name__}) + "\n")
        raise SystemExit("Inventory qualification incomplete") from None
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"qualified": True, "outcomes": len(CASES), "production_activation": False}))
