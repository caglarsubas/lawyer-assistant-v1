"""Frozen invented operator metadata; never opens real enrollment or case material."""

import json
import os
import shutil
from unittest.mock import patch

import httpx
import operator_enrollment_evidence as operator
import portable_controller_fixture as q

READY = "reconciled_for_disposable_mock_validation"
CASES = [("E01_candidate_only", "waiting"), ("E02_confirmed", READY),
         ("E03_tampered_packet", "blocked"), ("E04_wrong_approval", "blocked"), ("E05_unknown_field", "blocked"),
         ("E06_expired", "blocked"), ("E07_future", "blocked"), ("E08_lifetime", "blocked"),
         ("E09_duplicate", "blocked"), ("E10_symlink", "blocked"), ("E11_hardlink", "blocked"),
         ("E12_permissions", "blocked"), ("E13_record", "blocked"), ("E14_pin", "blocked"),
         ("E15_journal", "blocked"), ("E16_unsealed", "blocked"), ("E17_candidate_version", "blocked"),
         ("E18_fingerprint", "blocked"), ("E19_unapproved_confirmation", "waiting"),
         ("E20_confirmation_hash", "blocked"), ("E21_packet_expires_during_check", "blocked"),
         ("E22_revoked_during_check", "blocked"), ("E23_packet_replaced", "blocked"),
         ("E24_candidate_replaced", "blocked"), ("E25_ancestor_state_changed", "blocked"),
         ("E26_previous_unchanged", READY), ("E27_foreign_previous", "blocked"),
         ("E28_previous_tampered", "blocked"), ("E29_previous_permissions", "blocked"),
         ("E30_missing_candidate", "waiting"), ("E31_unexpected_private_material", "blocked"),
         ("E32_no_privileged_helpers", READY), ("E33_fifo", "blocked"), ("E34_illicit_authority", "blocked"),
         ("E35_previous_approval", "blocked"), ("E36_writable_package", "blocked"),
         ("E37_new_unapproved_confirmation", "waiting"), ("E38_clock_rollback", "blocked"),
         ("E39_confirmation_expires_during_check", "blocked")]
POLICY = {"schema": "operator-enrollment-qualification-v1", "cases": [dict(id=n, expected=s) for n, s in CASES],
          "attempts_per_native_case": 1, "packet_max_bytes": 32768, "packet_max_lifetime_seconds": 900,
          "model_verification_seconds": 20, "model_tensor_count": 0,
          "real_provider_requests": 0, "native_inference_calls": 0, "trust_enrolled": False,
          "runtime_installation_authorized": False, "production_activation": False}
INJECTED = {"E21_packet_expires_during_check", "E22_revoked_during_check", "E23_packet_replaced", "E24_candidate_replaced",
            "E25_ancestor_state_changed", "E38_clock_rollback", "E39_confirmation_expires_during_check"}


def expectations(f, approved):
    b = f.binding
    return {"package_manifest_sha256": approved,
            "binding": {"journal_id": b.journal_id, "operation_id": b.operation_id, "record_sha256": b.record_sha256,
                        "volume_binding_sha256": b.volume_binding_sha256, "pin_sha256": operator.sha(b.pin_bytes)},
            "enrollment": {"issuer_key_id": q.ISSUER, "fingerprint": f.fingerprint,
                           "candidate_sha256": operator.sha((f.trust / "candidate.json").read_bytes()),
                           "confirmation_sha256": operator.sha((f.trust / "key-confirmation.json").read_bytes()),
                           "reviewer": "fixture-reviewer", "provisioned_by": "fixture-provisioner"}}


def run_case(name, stage, approved, models, work, anchors, m):
    f = q.Fixture("A23_unsealed" if name == "E16_unsealed" else name, models, work, anchors, m)
    e = expectations(f, approved)
    now = [q.NOW]
    if name in {"E01_candidate_only", "E37_new_unapproved_confirmation"}:
        confirmation = (f.trust / "key-confirmation.json").read_bytes()
        (f.trust / "key-confirmation.json").unlink()
        e["enrollment"]["confirmation_sha256"] = None
    if name == "E13_record":
        e["binding"]["record_sha256"] = "0" * 64
    if name == "E14_pin":
        e["binding"]["pin_sha256"] = "0" * 64
    if name == "E15_journal":
        e["binding"]["journal_id"] = "0" * 32
    if name == "E18_fingerprint":
        e["enrollment"]["fingerprint"] = "0" * 64
    if name == "E19_unapproved_confirmation":
        e["enrollment"]["confirmation_sha256"] = None
    if name == "E20_confirmation_hash":
        e["enrollment"]["confirmation_sha256"] = "0" * 64
    if name == "E39_confirmation_expires_during_check":
        path = f.trust / "candidate.json"
        candidate = json.loads(path.read_bytes())
        candidate["created_at"] = q.NOW - 86500
        path.write_bytes(operator.encode(candidate))
        path = f.trust / "key-confirmation.json"
        decision = json.loads(path.read_bytes())
        decision.update(confirmed_at=q.NOW - 86395, expires_at=q.NOW + 5)
        path.write_bytes(operator.encode(decision))
        e = expectations(f, approved)
    raw = operator.packet(e, packet_id=operator.sha(name.encode())[:32], now=q.NOW)
    value = json.loads(raw)
    if name == "E05_unknown_field":
        value["api_key"] = "SYNTHETIC-PRIVATE-MUST-NOT-READ"
    if name == "E06_expired":
        value.update(created_at=q.NOW - 900, expires_at=q.NOW)
    if name == "E07_future":
        value.update(created_at=q.NOW + 1, expires_at=q.NOW + 901)
    if name == "E08_lifetime":
        value["expires_at"] = q.NOW + 901
    if name == "E34_illicit_authority":
        value["production_activation"] = True
    raw = operator.encode(value)
    if name == "E09_duplicate":
        raw = raw.replace(b'"version":1', b'"version":1,"version":1')
    packet_path = f.work / "operator-packet.json"
    operator.retain(packet_path, raw)
    approval = operator.sha(raw)
    if name == "E03_tampered_packet":
        packet_path.write_bytes(raw + b" ")
    if name == "E04_wrong_approval":
        approval = "0" * 64
    if name == "E10_symlink":
        packet_path.unlink()
        packet_path.symlink_to("/absent-operator-fixture")
    if name == "E11_hardlink":
        os.link(packet_path, f.work / "second-link")
    if name == "E12_permissions":
        packet_path.chmod(0o644)
    if name == "E17_candidate_version":
        path = f.trust / "candidate.json"
        path.write_bytes(path.read_bytes() + b" ")
    if name == "E30_missing_candidate":
        (f.trust / "candidate.json").unlink()
        (f.trust / "key-confirmation.json").unlink()
    if name == "E31_unexpected_private_material":
        operator.retain(f.trust / "signer-password", b"SYNTHETIC-PRIVATE-MUST-NOT-READ")
    if name == "E33_fifo":
        packet_path.unlink()
        os.mkfifo(packet_path, 0o600)
    if name == "E36_writable_package":
        target = f.work / "writable-stage"
        shutil.copytree(stage, target)
        stage = target
    previous_path = previous_sha = None
    history = set(n for n, _ in CASES if n.startswith(("E26_", "E27_", "E28_", "E29_", "E35_", "E37_")))
    if name in history:
        initial = operator.reconcile(packet_path, approval, stage, f.model, f.journal, f.binding, f.trust, api=m, clock=lambda: now[0])
        if initial["status"] not in {READY, "waiting"}:
            raise ValueError("Frozen history fixture invalid")
        if name == "E27_foreign_previous":
            initial["packet_sha256"] = "0" * 64
        previous_path = f.work / "observation-1.json"
        previous_sha = operator.retain(previous_path, operator.encode(initial))["sha256"]
        if name == "E28_previous_tampered":
            previous_path.write_bytes(previous_path.read_bytes() + b" ")
        if name == "E29_previous_permissions":
            previous_path.chmod(0o644)
        if name == "E35_previous_approval":
            previous_sha = "0" * 64
        if name == "E37_new_unapproved_confirmation":
            operator.retain(f.trust / "key-confirmation.json", confirmation)
        now[0] += 1

    def inject(_):
        if name == "E21_packet_expires_during_check":
            now[0] = q.NOW + 900
        if name == "E22_revoked_during_check":
            operator.retain(f.trust / "revoked.json", b"malformed")
        if name == "E23_packet_replaced":
            target = f.work / "replacement.json"
            operator.retain(target, raw + b" ")
            target.replace(packet_path)
        if name == "E24_candidate_replaced":
            path = f.trust / "candidate.json"
            path.write_bytes(path.read_bytes() + b" ")
        if name == "E25_ancestor_state_changed":
            f.journal.revoke(f.operation)
        if name == "E38_clock_rollback":
            now[0] -= 1
        if name == "E39_confirmation_expires_during_check":
            now[0] += 6

    def inventory():
        return {str(p.relative_to(f.work.parent.parent)): operator.sha(p.read_bytes())
                for root in (f.work, f.anchors) for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()}
    before = inventory()
    from contextlib import ExitStack
    with ExitStack() as stack:
        for helper in ("create_issuer", "load_signer", "confirm_key", "revoke_key"):
            stack.enter_context(patch.object(m.trust, helper, side_effect=AssertionError("Forbidden privileged helper")))
        for helper in ("Client", "AsyncClient"):
            stack.enter_context(patch.object(httpx, helper, side_effect=AssertionError("Forbidden network request")))
        result = operator.reconcile(packet_path, approval, stage, f.model, f.journal, f.binding, f.trust, api=m, clock=lambda: now[0],
                                    previous_path=previous_path, approved_previous_sha256=previous_sha, checkpoint=inject if name in INJECTED else None)
    exact = before == inventory()
    if not exact and name not in INJECTED:
        raise ValueError("Reconciliation mutated metadata")
    raw_result = operator.encode(result)
    if any(result[k] is not False for k in operator.FLAGS) or any(s in raw_result for s in (b"SYNTHETIC-PRIVATE", str(f.work).encode(), f.fingerprint.encode())):
        raise ValueError("Operator evidence leaked private metadata or authority")
    if name == "E26_previous_unchanged" and result["comparison"]["outcome"] != "unchanged":
        raise ValueError("Unchanged history comparison failed")
    if name == "E37_new_unapproved_confirmation" and (result["comparison"]["outcome"] != "changed" or result["comparison"]["changed_fields"] != ["confirmation_sha256"]):
        raise ValueError("Observed confirmation was silently approved")
    # Explicit caller retention happens AFTER read-only state comparison.
    retained = operator.retain(f.work / "observation-final.json", raw_result)
    if operator.read(f.work / "observation-final.json") != raw_result:
        raise ValueError("Exact observation retention failed")
    return {"id": name, "status": result["status"], "checks": result["checks"], "comparison": result["comparison"],
            "state_unchanged": exact, "external_change_injected": name in INJECTED, "observation_sha256": retained["sha256"],
            "private_sentinels_absent": True, "all_authority_flags_false": True}
