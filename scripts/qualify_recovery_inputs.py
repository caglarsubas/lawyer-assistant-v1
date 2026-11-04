"""Frozen local fixture qualification; no native, provider or production action."""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import operator_enrollment_evidence as e  # noqa: E402
from operator_recovery_inputs import DECISIONS, FLAGS, REFS  # noqa: E402
from private_inventory_receipts import RetentionUncertain  # noqa: E402
from recovery_input_fixture import ALTERNATE, ROOT, SELECTION, make  # noqa: E402

CASES = ("Q01_explicit_selection", "Q02_original_expiry", "Q03_independent_actor_required",
    "Q04_decision_reference_required", "Q05_independent_accept", "Q06_exact_decision_pin",
    "Q07_selection_cannot_change", "Q08_fresh_instance_readiness", "Q09_no_decision_overwrite",
    "Q10_read_only_history", "Q11_expired_review_withheld", "Q12_history_retained",
    "Q13_maintenance_withheld", "Q14_encrypted_sidecar", "Q15_uncertain_publication_retained",
    "Q16_uncertain_retry_conflicts", "Q17_no_acknowledgement_adoption", "Q18_original_inputs_exact")
NEW = ("scripts/operator_recovery_inputs.py", "scripts/recovery_input_fixture.py",
       "scripts/qualify_recovery_inputs.py", "backend/tests/test_operator_recovery_inputs.py")


def plan_sha256():
    return e.sha(e.encode(CASES))


def files(f):
    return {p.name: p.read_bytes() for p in f.sidecar.root.iterdir()}


def prepare(f):
    observed = f.service().dispatch(f.account.scope(), "observe", selection_id=SELECTION)
    assert observed["state"] == "inputs_observed"
    prepared = f.service().dispatch(f.account.scope(), "prepare", selection_id=SELECTION,
        review_id="1" * 32, expected_input_sha256=observed["input_sha256"])
    assert prepared["state"] == "pending_independent_review"
    return prepared, {k: prepared[k] for k in REFS}


def decision(f, prepared, refs):
    value = f.service().dispatch(f.account.scope("reviewer"), "decide", **refs,
        expected_input_sha256=prepared["input_sha256"], decision="accept", reason_code=DECISIONS["accept"])
    assert value["state"] == "independent_review_recorded"
    return {**refs, "decision_ciphertext_sha256": value["decision_ciphertext_sha256"]}


def campaign(root):
    fixtures, original, rows = [], [], []
    def fixture(name):
        f = make(root / name)
        fixtures.append(f)
        original.append((f.protected(), e.sha((f.account.profile / "disposable-identities.sqlite").read_bytes())))
        return f
    def row(name, condition, value=None):
        assert name in CASES and condition
        if value is not None:
            assert all(value[k] is False for k in FLAGS)
        rows.append({"id": name, "state": "verified"})
    try:
        f = fixture("reviewed")
        observed = f.service().dispatch(f.account.scope(), "observe", selection_id=SELECTION)
        row("Q01_explicit_selection", observed["state"] == "inputs_observed", observed)
        issued = observed["inputs"]["prepared_at"]
        f.account.now += 30
        prepared, refs = prepare(f)
        row("Q02_original_expiry", prepared["expires_at"] == issued + 300, prepared)
        denied = f.service().dispatch(f.account.scope(), "decide", **refs, expected_input_sha256=prepared["input_sha256"],
            decision="accept", reason_code=DECISIONS["accept"])
        row("Q03_independent_actor_required", denied["state"] == "denied", denied)
        pending = f.service().dispatch(f.account.scope("reviewer"), "readiness", **refs, decision_ciphertext_sha256=None)
        row("Q04_decision_reference_required", pending["state"] == "decision_reference_required", pending)
        full = decision(f, prepared, refs)
        row("Q05_independent_accept", len(files(f)) == 2)
        changed = f.service().dispatch(f.account.scope("reviewer"), "readiness", **{**full, "decision_ciphertext_sha256": "0" * 64})
        row("Q06_exact_decision_pin", changed["state"] == "unverifiable", changed)
        alternate = f.service().dispatch(f.account.scope("reviewer"), "readiness", **{**full, "selection_id": ALTERNATE})
        row("Q07_selection_cannot_change", alternate["state"] == "unverifiable", alternate)
        stored = files(f)
        ready = f.service().dispatch(f.account.scope("reviewer"), "readiness", **full)
        row("Q08_fresh_instance_readiness", ready["state"] == "reviewed_for_disposable_inputs"
            and ready["ready_for_disposable_input_handoff"], ready)
        retry = f.service().dispatch(f.account.scope("reviewer"), "decide", **refs, expected_input_sha256=prepared["input_sha256"],
            decision="reject", reason_code=DECISIONS["reject"])
        row("Q09_no_decision_overwrite", retry["state"] == "input_or_review_conflict" and files(f) == stored, retry)
        inspected = f.service().dispatch(f.account.scope("reviewer"), "inspect", **full)
        row("Q10_read_only_history", not inspected["ready_for_disposable_input_handoff"] and stored == files(f), inspected)
        f.account.now += 301
        stale = f.service().dispatch(f.account.scope("reviewer"), "readiness", **full)
        row("Q11_expired_review_withheld", stale["state"] == "review_retained_needs_revalidation"
            and not stale["ready_for_disposable_input_handoff"], stale)
        row("Q12_history_retained", files(f) == stored)
        maintenance = fixture("maintenance")
        m, mr = prepare(maintenance)
        md = decision(maintenance, m, mr)
        retained = files(maintenance)
        e.retain(maintenance.account.profile / ".runtime-key-rotation", b"invented maintenance")
        held = maintenance.service().dispatch(maintenance.account.scope("reviewer"), "readiness", **md)
        row("Q13_maintenance_withheld", held["state"] == "review_retained_needs_revalidation"
            and files(maintenance) == retained, held)
        row("Q14_encrypted_sidecar", all(b"operator-recovery-input-review-v1" not in raw
            for f2 in fixtures for raw in files(f2).values()))
        uncertain = fixture("uncertain")
        u, ur = prepare(uncertain)
        def checkpoint(name):
            if name == "after_decision_publish":
                raise RetentionUncertain
        lost = uncertain.service(checkpoint).dispatch(uncertain.account.scope("reviewer"), "decide", **ur,
            expected_input_sha256=u["input_sha256"], decision="accept", reason_code=DECISIONS["accept"])
        row("Q15_uncertain_publication_retained", lost["state"] == "retention_uncertain"
            and len(files(uncertain)) == 2 and "decision_ciphertext_sha256" not in lost, lost)
        saved = files(uncertain)
        duplicate = uncertain.service().dispatch(uncertain.account.scope("reviewer"), "decide", **ur,
            expected_input_sha256=u["input_sha256"], decision="accept", reason_code=DECISIONS["accept"])
        row("Q16_uncertain_retry_conflicts", duplicate["state"] == "input_or_review_conflict" and files(uncertain) == saved, duplicate)
        unpinned = uncertain.service().dispatch(uncertain.account.scope("reviewer"), "readiness", **ur, decision_ciphertext_sha256=None)
        row("Q17_no_acknowledgement_adoption", unpinned["state"] == "decision_reference_required"
            and not unpinned["ready_for_disposable_input_handoff"], unpinned)
        row("Q18_original_inputs_exact", all(f2.protected() == before[0]
            and e.sha((f2.account.profile / "disposable-identities.sqlite").read_bytes()) == before[1]
            for f2, before in zip(fixtures, original, strict=True)))
        assert rows == [{"id": name, "state": "verified"} for name in CASES]
        return {"cases": rows, "fixture_contexts": 3, "encrypted_review_records": 6,
            "real_session_auth_exercised": True, "original_inputs_and_accounts_exact": True,
            "original_expiry_preserved": True, "listener_started": False, "native_mount_qualification": False,
            "publication_fault_basis": "trusted_post_publish_checkpoint", "model_requests": 0, "provider_requests": 0,
            **dict.fromkeys(FLAGS, False)}
    finally:
        for f in fixtures:
            f.account.store.engine.dispose()


def run():
    prior = ROOT / "docs/evidence/native-cold-controller-2026-11-04.json"
    old = json.loads(prior.read_bytes())
    hashes = {**old["source_sha256"], **{n: e.sha((ROOT / n).read_bytes()) for n in NEW}}
    assert len(old["source_sha256"]) == 753 and len(hashes) == 757
    assert all(e.sha((ROOT / n).read_bytes()) == value for n, value in hashes.items())
    with tempfile.TemporaryDirectory(prefix="lawyer-input-review-") as name:
        evidence = campaign(Path(name).resolve())
    assert all(e.sha((ROOT / n).read_bytes()) == value for n, value in hashes.items())
    return {"schema": "reviewed-recovery-input-qualification-v1", "status": "qualified",
        "scope": "local invented fixture readiness review only", "case_plan_sha256": plan_sha256(),
        "source_sha256": hashes, "prior_native_report_sha256": hashlib.sha256(prior.read_bytes()).hexdigest(),
        "evidence": evidence, "production_activation": False, "legal_qualification": False,
        "not_qualified": ["genuine operator appointment and key custody", "external checksum channel authenticity",
                          "kernel readonly mounts in this campaign", "privileged joint rollback", "production deployment", "legal review"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    with args.output.open("x") as stream:
        stream.write('{"status":"incomplete"}\n')
    try:
        report = run()
    except Exception as exc:  # noqa: BLE001 - no private error values or records.
        args.output.write_text(json.dumps({"status": "incomplete", "error_type": type(exc).__name__}) + "\n")
        raise SystemExit("Input-review qualification incomplete") from None
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True) + "\n")
    print(json.dumps({"qualified": True, "outcomes": len(CASES), "production_activation": False}))
