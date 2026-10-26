"""Frozen actual-process reader lifecycle results; no production acceptance."""

import json
from pathlib import Path

from operator_enrollment_evidence import encode, sha
from reader_namespace_fixture import CASES, POLICY

COUNTS = [{'HTTP_requests': 33, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 3}, {'HTTP_requests': 31, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 1}, {'HTTP_requests': 32, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 2}, {'HTTP_requests': 34, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 4, 'transition_events': 1}, {'HTTP_requests': 34, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 4, 'legacy_reader_events': 3, 'transition_events': 1}, {'HTTP_requests': 38, 'withdrawal_events': 2, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 3}, {'HTTP_requests': 32, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 2}, {'HTTP_requests': 32, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 2}, {'HTTP_requests': 36, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 3}, {'HTTP_requests': 39, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 3}, {'HTTP_requests': 33, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 3}, {'HTTP_requests': 33, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 3}, {'HTTP_requests': 32, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 2}, {'HTTP_requests': 32, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 2}, {'HTTP_requests': 33, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 3}, {'HTTP_requests': 35, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 3}, {'HTTP_requests': 30, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 0}, {'HTTP_requests': 35, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 3, 'legacy_reader_events': 3, 'transition_events': 3}, {'HTTP_requests': 30, 'withdrawal_events': 0, 'withdrawal_archives': 2, 'withdrawal_manifests': 2, 'withdrawal_restore_attempts': 2, 'reader_events': 4, 'legacy_reader_events': 3, 'transition_events': 0}, {'HTTP_requests': 41, 'withdrawal_events': 0, 'withdrawal_archives': 3, 'withdrawal_manifests': 3, 'withdrawal_restore_attempts': 3, 'reader_events': 7, 'legacy_reader_events': 3, 'transition_events': 3}]


def grade(report):
    if (report["schema"] != "reader-namespace-native-v1" or len(report["cases"]) != len(CASES)
            or report["policy_sha256"] != sha(encode(POLICY)) or report["actual_HTTP_requests"] != sum(r["HTTP_requests"] for r in COUNTS)
            or report["actual_loopback_servers"] != 40 or report["min_distinct_worker_processes"] != 2
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
                                                  "no_replay_or_automatic_reactivation", "bounded_metadata_only_inventory", "independent_withdrawal_controls_external", "canonical_fence_on_every_read", "ordinary_writes_use_original_journal", "reader_selection_is_not_runtime_activation", "independent_reader_controls_external", "retirement_permanent_per_selection", "fresh_independent_decision_for_succession", "historical_approvals_never_reactivated", "source_writer_unchanged", "both_reader_histories_unchanged_by_transition", "fresh_independent_transition_review", "no_automatic_namespace_fallback", "transition_does_not_reactivate_old_approvals"))
                or row["restore_grants_or_activation_created"] is not False or row["runtime_installation"] is not False or row["real_trust_enrolled"] is not False):
            raise ValueError("Frozen withdrawal backup outcome rejected")
    return {"cases_passed": 20, "actual_loopback_servers": 40, "actual_HTTP_requests": sum(r["HTTP_requests"] for r in COUNTS),
            "actual_app_session_and_RBAC_checks": True, "disposable_accounts_only": True, "independent_controls_external": True,
            "read_only_reconciliation": True, "independently_reviewed_reader_selection": True, "runtime_installation": False, "legal_qualification": False}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(grade(json.loads((root / "deploy/fixtures/reader_namespace_first_report.json").read_text()))))
