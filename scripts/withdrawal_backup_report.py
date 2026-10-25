"""Frozen actual-process withdrawal archive results; no production acceptance."""

import json
from pathlib import Path

from operator_enrollment_evidence import encode, sha
from withdrawal_backup_fixture import CASES, POLICY

COUNTS = [{'HTTP_requests': 17, 'withdrawal_events': 0, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 1}, {'HTTP_requests': 21, 'withdrawal_events': 2, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 1}, {'HTTP_requests': 24, 'withdrawal_events': 2, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 1}, {'HTTP_requests': 20, 'withdrawal_events': 2, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 1}, {'HTTP_requests': 18, 'withdrawal_events': 2, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 0}, {'HTTP_requests': 18, 'withdrawal_events': 0, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 0}, {'HTTP_requests': 15, 'withdrawal_events': 0, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 0}, {'HTTP_requests': 15, 'withdrawal_events': 0, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 0}, {'HTTP_requests': 15, 'withdrawal_events': 0, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 0}, {'HTTP_requests': 17, 'withdrawal_events': 0, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 1}, {'HTTP_requests': 16, 'withdrawal_events': 0, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 1}, {'HTTP_requests': 17, 'withdrawal_events': 0, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 1}, {'HTTP_requests': 17, 'withdrawal_events': 0, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 1}, {'HTTP_requests': 17, 'withdrawal_events': 0, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 1}, {'HTTP_requests': 17, 'withdrawal_events': 0, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 1}, {'HTTP_requests': 18, 'withdrawal_events': 2, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 0}, {'HTTP_requests': 16, 'withdrawal_events': 0, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 1}, {'HTTP_requests': 16, 'withdrawal_events': 0, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 1}, {'HTTP_requests': 19, 'withdrawal_events': 2, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 1}, {'HTTP_requests': 15, 'withdrawal_events': 0, 'withdrawal_archives': 0, 'withdrawal_manifests': 0, 'withdrawal_restore_attempts': 0}, {'HTTP_requests': 17, 'withdrawal_events': 0, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 1}, {'HTTP_requests': 19, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 1}, {'HTTP_requests': 14, 'withdrawal_events': 0, 'withdrawal_archives': 0, 'withdrawal_manifests': 0, 'withdrawal_restore_attempts': 0}, {'HTTP_requests': 18, 'withdrawal_events': 1, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 0}, {'HTTP_requests': 16, 'withdrawal_events': 2, 'withdrawal_archives': 0, 'withdrawal_manifests': 0, 'withdrawal_restore_attempts': 0}, {'HTTP_requests': 16, 'withdrawal_events': 0, 'withdrawal_archives': 1, 'withdrawal_manifests': 1, 'withdrawal_restore_attempts': 0}]


def grade(report):
    if (report["schema"] != "withdrawal-backup-native-v1" or len(report["cases"]) != len(CASES)
            or report["policy_sha256"] != sha(encode(POLICY)) or report["actual_HTTP_requests"] != sum(r["HTTP_requests"] for r in COUNTS)
            or report["actual_loopback_servers"] != 52 or report["min_distinct_worker_processes"] != 2
            or any(report[k] is not True for k in ("read_only_model_and_package_inventory_exact", "actual_app_auth_used", "separate_backup_and_control_mounts"))
            or any(report[k] is not False for k in ("app_main_or_provider_imported", "real_accounts_or_sessions_used", "real_trust_enrolled", "runtime_installation", "private_case_inputs", "production_activation"))
            or report["live_provider_requests"] != 0 or report["native_inference_calls"] != 0
            or report["profile"] != {"filesystem": "ext4", "cpu": 2, "memory_mib": 768, "network": "none", "process_environment_cleared": True, "single_attempt": True}
            or set(report["preparation"]["filesystems"].values()) != {"ext4"} or report["preparation"]["tensor_count"] != 0
            or report["preparation"]["private_inputs"] is not False):
        raise ValueError("Frozen withdrawal backup posture rejected")
    c = report["candidate"]
    if c["single_attempt"] is not True or c["new_volumes_only"] is not True or c["real_credentials_or_inputs"] is not False or c["production_activation"] is not False:
        raise ValueError("Frozen archive candidate rejected")
    for row, (name, status), counts in zip(report["cases"], CASES, COUNTS, strict=True):
        if (row["id"] != name or row["status"] != status or any(row[k] != v for k, v in counts.items())
                or row["restore_control_events"] != 4 or row["restore_attempts"] != 1 or row["catalog_rows_defined"] != 3
                or row["encrypted_bundles"] != 1 or row["independent_manifests"] != 1 or row["handoff_records"] != 1 or row["decision_records"] != 1
                or row["distinct_worker_processes"] != 2 or row["actual_loopback_servers"] != 2
                or any(row[k] is not True for k in ("credentials_absent_from_responses_and_review_records", "all_authority_flags_false", "actual_app_session_auth",
                                                  "original_history_preserved", "anchor_and_intents_not_restored", "no_automatic_activation", "shared_disposable_identity_store",
                                                  "all_worker_processes_exited_cleanly", "no_system_evidence_or_key_mutation", "lineage_withdrawal_is_not_key_destruction",
                                                  "no_replay_or_automatic_reactivation", "bounded_metadata_only_inventory", "independent_withdrawal_controls_external", "comparison_read_only"))
                or row["restore_grants_or_activation_created"] is not False or row["runtime_installation"] is not False or row["real_trust_enrolled"] is not False):
            raise ValueError("Frozen withdrawal backup outcome rejected")
    return {"cases_passed": 26, "actual_loopback_servers": 52, "actual_HTTP_requests": sum(r["HTTP_requests"] for r in COUNTS),
            "actual_app_session_and_RBAC_checks": True, "disposable_accounts_only": True, "independent_controls_external": True,
            "read_only_reconciliation": True, "runtime_installation": False, "legal_qualification": False}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(grade(json.loads((root / "deploy/fixtures/withdrawal_backup_first_report.json").read_text()))))
