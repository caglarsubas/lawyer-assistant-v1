"""Frozen process-interruption and read-only restart matrix; no adoption authority."""

from controller_stage_manifest import hex_digest

STATES = ["connection_closed", "plan_not_observed", "connection_closed", "plan_publication_unverifiable",
          "connection_closed", "plan_references_unavailable", "connection_closed", "decision_not_observed",
          "connection_closed", "decision_publication_unverifiable", "connection_closed", "retained_decision_observed",
          "retained_decision_observed", "snapshot_conflict", "stale_decision_preserved", "denied",
          "stale_decision_preserved", "stale_decision_preserved", "pending_independent_review",
          "reviewed_for_metadata_planning", "retained_decision_observed", "conflict"]
COUNTS = {"journal_processes": 25, "intentional_SIGKILL_exits": 6, "clean_journal_exits": 19,
          "fresh_readonly_processes": 13, "journal_API_attempts": 44, "acknowledged_responses": 38,
          "journal_controller_reads": 0, "source_preparation_controller_reads": 4,
          "original_source_entries": 1, "final_source_entries": 2, "final_journal_entries": 5}
TRUE = {"actual_app_auth_used", "independent_principals_used", "all_process_exits_verified", "source_ciphertext_exact",
        "four_histories_exact", "readonly_operations_preserved_all_bytes_and_links", "prior_journal_ciphertext_exact"}
FALSE = {"automatic_repair", "record_adoption", "acknowledgement_recovery", "authority_renewal", "production_activation"}


def validate(value, receipt_manifest, controller_manifest):
    fields = {"schema", "receipt_manifest_sha256", "controller_manifest_sha256", "modes", "filesystem",
              "read_only_packages_exact", "private_case_inputs", "live_provider_requests", "native_inference_calls",
              "key_custody", "operator_appointments", "power_loss_qualified", "production_activation"}
    if (not isinstance(value, dict) or set(value) != fields or value["schema"] != "native-planning-journal-restart-v1"
            or value["receipt_manifest_sha256"] != hex_digest(receipt_manifest)
            or value["controller_manifest_sha256"] != hex_digest(controller_manifest)
            or value["filesystem"] != "ext4" or value["read_only_packages_exact"] is not True
            or any(value[k] is not False for k in ("private_case_inputs", "power_loss_qualified", "production_activation"))
            or any(type(value[k]) is not int or value[k] != 0 for k in ("live_provider_requests", "native_inference_calls"))
            or any(value[k] != "unassessed" for k in ("key_custody", "operator_appointments"))
            or not isinstance(value["modes"], list) or len(value["modes"]) != 2):
        raise ValueError("Closed journal restart scope required")
    for item, mode in zip(value["modes"], ("retirement", "rollback"), strict=True):
        if (not isinstance(item, dict) or set(item) != {"mode", "cases", "operation_attempts", *COUNTS, *TRUE, *FALSE}
                or item["mode"] != mode or any(type(item[k]) is not int or item[k] != v for k, v in COUNTS.items())
                or any(item[k] is not True for k in TRUE) or any(item[k] is not False for k in FALSE)
                or item["operation_attempts"] != {"source_inventory": 7, "prepare": 7, "decide": 5, "inventory": 12, "reconcile": 13}
                or not isinstance(item["cases"], list) or item["cases"] != [{"id": f"J{i:02}", "state": state} for i, state in enumerate(STATES, 1)]):
            raise ValueError("Frozen journal restart outcomes differ")
    return {"qualified_modes": 2, "frozen_outcomes": 44, "intentional_SIGKILL_exits": 12, "production_activation": False}
