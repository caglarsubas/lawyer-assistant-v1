"""Frozen exact lifecycle/process outcomes, distinct from production acceptance."""

import json
from pathlib import Path

from operator_enrollment_evidence import encode, sha, token
from restore_lifecycle_fixture import CASES, POLICY

REQUESTS = [18, 15, 17, 17, 21, 16, 19, 15, 27, 15, 17, 17, 13, 15, 15, 15, 16, 16, 19, 21, 14, 14, 15, 15, 22, 32]
EVENTS = [2, 1, 1, 2, 3, 2, 2, 1, 2, 1, 2, 2, 0, 1, 1, 1, 2, 2, 2, 4, 0, 0, 1, 1, 4, 4]


def grade(report):
    if (report["schema"] != "restore-lifecycle-native-v1" or len(report["cases"]) != 26
            or report["policy_sha256"] != sha(encode(POLICY)) or report["actual_HTTP_requests"] != sum(REQUESTS)
            or report["actual_loopback_servers"] != 52 or report["min_distinct_worker_processes"] != 2
            or any(report[k] is not True for k in ("read_only_model_and_package_inventory_exact", "actual_app_auth_used", "separate_backup_and_control_mounts"))
            or any(report[k] is not False for k in ("app_main_or_provider_imported", "real_accounts_or_sessions_used", "real_trust_enrolled", "runtime_installation", "private_case_inputs", "production_activation"))
            or report["live_provider_requests"] != 0 or report["native_inference_calls"] != 0
            or report["profile"] != {"filesystem": "ext4", "cpu": 2, "memory_mib": 768, "network": "none", "process_environment_cleared": True, "single_attempt": True}
            or set(report["preparation"]["filesystems"].values()) != {"ext4"}
            or report["preparation"]["tensor_count"] != 0 or report["preparation"]["private_inputs"] is not False):
        raise ValueError("Lifecycle qualification posture rejected")
    c = report["candidate"]
    if c["single_attempt"] is not True or c["new_volumes_only"] is not True or c["real_credentials_or_inputs"] is not False or c["production_activation"] is not False:
        raise ValueError("Lifecycle frozen candidate rejected")
    for n, (row, (name, expected), requests, events) in enumerate(zip(report["cases"], CASES, REQUESTS, EVENTS, strict=True), 1):
        if (row["id"] != name or row["status"] != expected or row["HTTP_requests"] != requests or row["lifecycle_events"] != events
                or row["restore_control_events"] != 4 or row["restore_attempts"] != (2 if n in {9, 26} else 1)
                or row["encrypted_bundles"] != 1 or row["independent_manifests"] != 1 or row["handoff_records"] != 1 or row["decision_records"] != 1
                or row["distinct_worker_processes"] != 2 or row["actual_loopback_servers"] != 2
                or any(row[k] is not True for k in ("credentials_absent_from_responses_and_review_records", "all_authority_flags_false", "actual_app_session_auth",
                                                  "original_history_preserved", "anchor_and_intents_not_restored", "no_automatic_activation", "shared_disposable_identity_store",
                                                  "all_worker_processes_exited_cleanly", "original_targets_and_backups_retained", "enrollment_renewal_is_not_key_rotation",
                                                  "fresh_restore_authorization_required", "retired_targets_not_served"))
                or row["runtime_installation"] is not False or row["real_trust_enrolled"] is not False):
            raise ValueError("Frozen lifecycle outcome rejected")
        token(row["ledger_sha256"])
    return {"cases_passed": 26, "actual_loopback_servers": 52, "actual_HTTP_requests": sum(REQUESTS),
            "actual_app_session_and_RBAC_checks": True, "disposable_accounts_only": True,
            "key_rotation": False, "native_inference_calls": 0, "runtime_installation": False, "legal_qualification": False}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(grade(json.loads((root / "deploy/fixtures/restore_lifecycle_first_report.json").read_text()))))
