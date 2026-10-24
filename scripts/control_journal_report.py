"""Replay synthetic metadata receipts; never recover a journal or admit a model."""

import json

import artifact_store as a
import control_journal_qualification as q
import sealed_volume as v


def grade(report):
    expected = dict(q.CASES)
    rows = report["cases"]
    if (report["schema"] != "control-journal-native-receipt-v1"
            or report["policy_sha256"] != a.digest((json.dumps(q.POLICY, indent=2) + "\n").encode())
            or len(rows) != 32 or len({r["id"] for r in rows}) != 32
            or {r["id"]: r["expected"] for r in rows} != expected
            or any(r["observed"] != expected[r["id"]] for r in rows)
            or report["independent_anchor_volume"] is not True
            or report["backup_volume_readonly_for_restore"] is not True
            or any(report[k] is not False for k in ("private_inputs", "real_keys_or_trust", "production_activation", "model_performance_retested"))
            or any(type(report[k]) is not int or report[k] != 0 for k in ("provider_requests", "inference_calls"))):
        v.reject()
    if report["profile"] != {"filesystem": "ext4", "cpu": 2, "memory_mib": 768, "network": "none", "process_environment_cleared": True, "single_attempt": True}:
        v.reject()
    candidate = report["candidate"]
    if candidate["single_attempt"] is not True or candidate["new_volumes_only"] is not True or candidate["real_credentials_or_inputs"] is not False or candidate["production_activation"] is not False:
        v.reject()
    prep = report["preparation"]
    if prep["synthetic_only"] is not True or prep["tensor_count"] != 0 or set(prep["filesystems"].values()) != {"ext4"}:
        v.reject()
    for proof in report["fixture_proofs"]:
        a.validate_proof(proof, prep["info"]["manifest_digest"], a.Budget(), strategy="windowed-pinned")
        if proof["mapped_bytes"] != 65561 or proof["content_identity_sha256"] != prep["info"]["content_sha256"]:
            v.reject()
    if len(report["fixture_proofs"]) != 2:
        v.reject()
    by_id = {r["id"]: r["evidence"] for r in rows}
    checks = {"C03_atomic_descendant_revocation": {"revoked": 4, "sealed": 1},
              "C04_branch_isolation": {"revoked": 2, "sealed": 2, "copying": 1},
              "C21_before_commit_crash": {"sealed": 2}, "C22_commit_anchor_gap": {"revoked": 2},
              "C23_after_anchor_crash": {"revoked": 2}, "C27_depth_bound": {"sealed": 32},
              "C28_count_bound": {"sealed": 2, "copying": 510}}
    if any(by_id[n]["operation_states"] != states for n, states in checks.items()):
        v.reject()
    if (by_id["C29_hot_journal_read"]["readable_without_repair"] is not False
            or by_id["C24_nonce_commit_gap"]["nonce_states"] != {"reserved": 1}
            or by_id["C14_exact_backup_nonce"]["restored_nonce_states"] != {"consumed": 1}
            or by_id["C14_exact_backup_nonce"]["restore_published"] is not True
            or any(by_id[n]["restore_published"] is not False for n in q.BACKUP_CASES if n != "C14_exact_backup_nonce")):
        v.reject()
    packet = report["backup_packet"]
    if set(packet) != q.BACKUP_CASES:
        v.reject()
    for item in packet.values():
        v.token(item["journal_id"])
        for label in ("older", "latest"):
            backup = item[label]
            v.digest(backup["backup_sha256"])
            if backup["anchor_in_backup"] is not False or backup["production_activation"] is not False or backup["fence"]["journal_id"] != item["journal_id"]:
                v.reject()
        if item["older"]["fence"]["seq"] >= item["latest"]["fence"]["seq"] or item["older"]["backup_sha256"] == item["latest"]["backup_sha256"]:
            v.reject()
    return {"native_cases": 32, "expected_rejections": sum(e == "rejected" for e in expected.values()),
            "crash_and_recovery_cases": 6, "fresh_backup_cases": 4, "metadata_only": True,
            "retained_nonce_and_revocation_history": True, "production_activation": False}
