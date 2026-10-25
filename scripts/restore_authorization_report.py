"""Closed frozen disposable qualification; no production or legal acceptance."""

import json
from pathlib import Path

from operator_enrollment_evidence import encode, sha, token
from restore_authorization_fixture import CASES, POLICY

REQUESTS = [14, 5, 8, 10, 8, 10, 12, 12, 10, 10, 10, 10, 12, 10, 12, 16, 19, 16, 11, 5, 6, 6, 7, 14, 10, 7]
EVENTS = [4, 0, 1, 2, 1, 2, 3, 3, 2, 2, 2, 2, 3, 2, 3, 5, 4, 3, 3, 0, 0, 0, 1, 4, 2, 1]
RESTORED = {1, 7, 13, 15, 16, 17, 19, 24}


def grade(report):
    if (report["schema"] != "restore-authorization-native-v1" or len(report["cases"]) != len(CASES)
            or report["policy_sha256"] != sha(encode(POLICY)) or report["actual_HTTP_requests"] != sum(REQUESTS)
            or report["actual_loopback_servers"] != 52 or report["min_distinct_worker_processes"] != 2
            or any(report[k] is not True for k in ("read_only_model_and_package_inventory_exact", "actual_app_auth_used", "separate_backup_and_control_mounts"))
            or any(report[k] is not False for k in ("app_main_or_provider_imported", "real_accounts_or_sessions_used", "real_trust_enrolled", "runtime_installation", "private_case_inputs", "production_activation"))
            or report["live_provider_requests"] != 0 or report["native_inference_calls"] != 0
            or report["profile"] != {"filesystem": "ext4", "cpu": 2, "memory_mib": 768, "network": "none", "process_environment_cleared": True, "single_attempt": True}
            or set(report["preparation"]["filesystems"].values()) != {"ext4"}
            or report["preparation"]["tensor_count"] != 0 or report["preparation"]["private_inputs"] is not False):
        raise ValueError("Disposable restore qualification posture rejected")
    candidate = report["candidate"]
    if candidate["single_attempt"] is not True or candidate["new_volumes_only"] is not True or candidate["real_credentials_or_inputs"] is not False or candidate["production_activation"] is not False:
        raise ValueError("Frozen restore candidate rejected")
    for n, (row, (name, expected), requests, events) in enumerate(zip(report["cases"], CASES, REQUESTS, EVENTS, strict=True), 1):
        if (row["id"] != name or row["status"] != expected or row["HTTP_requests"] != requests or row["restore_control_events"] != events
                or row["restore_attempts"] != int(n in RESTORED) or row["encrypted_bundles"] != 1 or row["independent_manifests"] != 1
                or row["distinct_worker_processes"] != 2 or row["actual_loopback_servers"] != 2 or row["handoff_records"] != 1 or row["decision_records"] != 1
                or any(row[k] is not True for k in ("credentials_absent_from_responses_and_review_records", "all_authority_flags_false", "actual_app_session_auth",
                                                  "original_history_preserved", "anchor_and_intents_not_restored", "no_automatic_activation", "shared_disposable_identity_store",
                                                  "all_worker_processes_exited_cleanly", "independent_restore_authorization", "key_custody_pinned", "no_live_target_selected"))
                or row["runtime_installation"] is not False or row["real_trust_enrolled"] is not False):
            raise ValueError("Frozen restore authorization outcome rejected")
        token(row["ledger_sha256"])
    return {"cases_passed": len(CASES), "actual_loopback_servers": 52, "actual_HTTP_requests": sum(REQUESTS),
            "actual_app_session_and_RBAC_checks": True, "disposable_accounts_only": True,
            "native_inference_calls": 0, "real_trust_enrolled": False, "runtime_installation": False, "legal_qualification": False}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(grade(json.loads((root / "deploy/fixtures/restore_authorization_first_report.json").read_text()))))
