"""Frozen disposable copy-readiness outcomes; no operational restore claim."""

from controller_stage_manifest import hex_digest

STATES = ["observed_copy_metadata", "pending_independent_review", "denied", "reviewed_for_disposable_copy_qualification",
          "reviewed_for_disposable_copy_qualification", "stale_readiness_review_retained", "snapshot_or_publication_conflict",
          "unverifiable", "observed_copy_metadata", "pending_independent_review", "reviewed_for_disposable_copy_qualification",
          "reviewed_for_disposable_copy_qualification", "snapshot_or_publication_conflict", "stale_readiness_review_retained",
          "pending_independent_review", "reviewed_for_disposable_copy_qualification", "unverifiable", "denied",
          "stale_readiness_review_retained"]
TRUE = {"actual_app_auth", "independent_review", "original_ciphertext_exact", "prior_readiness_history_exact",
        "readonly_source_and_candidates_exact", "all_worker_exits_verified", "new_target_independently_pinned"}
FALSE = {"backup_executed", "restore_executed", "trust_migrated", "acknowledgement_recovered", "production_activation"}


def validate(value, receipt_manifest, controller_manifest):
    fields = {"schema", "receipt_manifest_sha256", "controller_manifest_sha256", "modes", "filesystem", "read_only_packages_exact",
              "private_case_inputs", "live_provider_requests", "native_inference_calls", "key_custody", "operator_appointments",
              "power_loss_qualified", "production_activation"}
    if (not isinstance(value, dict) or set(value) != fields or value["schema"] != "native-journal-backup-readiness-v1"
            or value["receipt_manifest_sha256"] != hex_digest(receipt_manifest)
            or value["controller_manifest_sha256"] != hex_digest(controller_manifest)
            or value["filesystem"] != "ext4" or value["read_only_packages_exact"] is not True
            or any(value[k] is not False for k in ("private_case_inputs", "power_loss_qualified", "production_activation"))
            or any(type(value[k]) is not int or value[k] != 0 for k in ("live_provider_requests", "native_inference_calls"))
            or value["key_custody"] != "unassessed" or value["operator_appointments"] != "unassessed"
            or not isinstance(value["modes"], list) or len(value["modes"]) != 2):
        raise ValueError("Closed copy-readiness report required")
    for item, mode in zip(value["modes"], ("empty_target", "existing_copy"), strict=True):
        if (not isinstance(item, dict) or set(item) != {"mode", "cases", "fresh_worker_processes", "source_preparation_operations",
                                                     "readiness_API_attempts", "controller_reads", *TRUE, *FALSE}
                or item["mode"] != mode or item["cases"] != [{"id": f"B{i:02}", "state": s} for i, s in enumerate(STATES, 1)]
                or any(item[k] is not True for k in TRUE) or any(item[k] is not False for k in FALSE)
                or any(type(item[k]) is not int or item[k] != n for k, n in
                       (("fresh_worker_processes", 19), ("source_preparation_operations", 3), ("readiness_API_attempts", 19), ("controller_reads", 0)))):
            raise ValueError("Frozen copy-readiness outcomes differ")
    return {"qualified_modes": 2, "frozen_outcomes": 38, "production_activation": False}
