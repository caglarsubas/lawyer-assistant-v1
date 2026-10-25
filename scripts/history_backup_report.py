"""Frozen metadata-only qualification; no production or legal acceptance."""

import json
from pathlib import Path

from history_backup_fixture import CASES, POLICY
from operator_enrollment_evidence import encode, sha, token

REQUESTS = [8, 8, 8, 5, 5, 5, 7, 5, 5, 6, 6, 5, 8, 8, 4, 4, 4, 5, 6, 5, 2, 6, 8, 9, 6, 7]
BUNDLES = [1] * 14 + [0, 0, 0, 1, 1, 0, 0, 1, 1, 1, 2, 1]
MANIFESTS = [1] * 8 + [0] + [1] * 5 + [0, 0, 0, 1, 1, 0, 0, 1, 1, 1, 1, 1]
RESTORES = [1, 1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 2, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1]
THREE_WORKERS = {1, 2, 3, 13, 23}


def grade(report):
    if (report["schema"] != "review-history-backup-native-v1" or len(report["cases"]) != 26
            or report["policy_sha256"] != sha(encode(POLICY)) or report["actual_HTTP_requests"] != sum(REQUESTS)
            or report["actual_loopback_servers"] != 57 or report["min_distinct_worker_processes"] != 2
            or report["read_only_model_and_package_inventory_exact"] is not True or report["actual_app_auth_used"] is not True
            or report["separate_backup_and_control_mounts"] is not True
            or any(report[k] is not False for k in ("app_main_or_provider_imported", "real_accounts_or_sessions_used", "real_trust_enrolled", "runtime_installation", "private_case_inputs", "production_activation"))
            or report["live_provider_requests"] != 0 or report["native_inference_calls"] != 0
            or report["profile"] != {"filesystem": "ext4", "cpu": 2, "memory_mib": 768, "network": "none", "process_environment_cleared": True, "single_attempt": True}
            or set(report["preparation"]["filesystems"].values()) != {"ext4"}
            or report["preparation"]["tensor_count"] != 0 or report["preparation"]["private_inputs"] is not False):
        raise ValueError("History qualification posture rejected")
    c = report["candidate"]
    if c["single_attempt"] is not True or c["new_volumes_only"] is not True or c["real_credentials_or_inputs"] is not False or c["production_activation"] is not False:
        raise ValueError("Frozen history candidate rejected")
    for i, (row, (name, expected), requests, bundles, manifests, restores) in enumerate(zip(report["cases"], CASES, REQUESTS, BUNDLES, MANIFESTS, RESTORES, strict=True), 1):
        workers = 3 if i in THREE_WORKERS else 2
        if (row["id"] != name or row["status"] != expected or row["HTTP_requests"] != requests
                or row["encrypted_bundles"] != bundles or row["independent_manifests"] != manifests or row["restore_attempts"] != restores
                or row["distinct_worker_processes"] != workers or row["actual_loopback_servers"] != workers
                or row["handoff_records"] != (2 if i in {7, 22} else 1) or row["decision_records"] != (0 if i == 21 else 1)
                or any(row[k] is not True for k in ("credentials_absent_from_responses_and_review_records", "all_authority_flags_false", "actual_app_session_auth", "original_history_preserved", "anchor_and_intents_not_restored", "no_automatic_activation", "shared_disposable_identity_store", "all_worker_processes_exited_cleanly"))
                or row["runtime_installation"] is not False or row["real_trust_enrolled"] is not False):
            raise ValueError("Frozen backup, restore or process outcome rejected")
        token(row["ledger_sha256"])
    return {"cases_passed": 26, "actual_loopback_servers": 57, "actual_HTTP_requests": sum(REQUESTS),
            "min_distinct_worker_processes": 2, "actual_app_session_and_RBAC_checks": True,
            "disposable_accounts_only": True, "read_only_model_and_package_exact": True,
            "native_inference_calls": 0, "real_trust_enrolled": False, "runtime_installation": False, "legal_qualification": False}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(grade(json.loads((root / "deploy/fixtures/history_backup_first_report.json").read_text()))))
