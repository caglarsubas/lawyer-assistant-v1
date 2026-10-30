"""Frozen ciphertext-copy and interrupted-attempt qualification; no live trust."""

from controller_stage_manifest import hex_digest

ROUND_TRIP = ["observed_copy_metadata", "pending_independent_review", "reviewed_for_disposable_copy_qualification",
    "copy_needs_independent_authorization", "denied", "denied", "disposable_copy_authorized",
    "ciphertext_backup_materialized", "retained_copy_verified", "copy_context_or_publication_conflict",
    "observed_copy_metadata", "pending_independent_review", "reviewed_for_disposable_copy_qualification",
    "copy_needs_independent_authorization", "denied", "denied", "disposable_copy_authorized",
    "ciphertext_restore_materialized", "retained_copy_verified", "retained_copy_verified",
    "copy_context_or_publication_conflict", "retained_copy_verified", "retained_copy_verified_review_stale", "denied"]
INTERRUPTED = [*ROUND_TRIP[:7], "connection_closed", "completion_reference_not_supplied",
               "copy_context_or_publication_conflict", "denied", "completion_reference_not_supplied"]
TRUE = {"actual_app_auth", "independent_execution_review", "original_ciphertext_exact", "earlier_history_exact",
        "readonly_operations_exact", "all_process_exits_verified", "independent_destination_and_manifest_pins"}
FALSE = {"trust_migrated", "acknowledgement_recovered", "automatic_resume", "production_activation"}
COUNTS = {"round_trip": {"processes": 24, "intentional_SIGKILL_exits": 0, "clean_exits": 24, "acknowledged_responses": 24,
            "operation_attempts": {"ready_observe": 2, "ready_prepare": 2, "ready_decide": 2, "copy_prepare": 2,
                                   "copy_decide": 4, "materialize": 5, "verify": 7}, "target_entries": 3},
          "interrupted_copy": {"processes": 12, "intentional_SIGKILL_exits": 1, "clean_exits": 11, "acknowledged_responses": 11,
            "operation_attempts": {"ready_observe": 1, "ready_prepare": 1, "ready_decide": 1, "copy_prepare": 1,
                                   "copy_decide": 2, "materialize": 3, "verify": 3}, "target_entries": 1}}


def validate(value, receipt_manifest, controller_manifest):
    fields = {"schema", "receipt_manifest_sha256", "controller_manifest_sha256", "protocols", "filesystem", "read_only_packages_exact",
              "private_case_inputs", "live_provider_requests", "native_inference_calls", "key_custody", "operator_appointments",
              "power_loss_qualified", "production_activation"}
    if (not isinstance(value, dict) or set(value) != fields or value["schema"] != "native-journal-materialization-v1"
            or value["receipt_manifest_sha256"] != hex_digest(receipt_manifest)
            or value["controller_manifest_sha256"] != hex_digest(controller_manifest)
            or value["filesystem"] != "ext4" or value["read_only_packages_exact"] is not True
            or any(value[k] is not False for k in ("private_case_inputs", "power_loss_qualified", "production_activation"))
            or any(type(value[k]) is not int or value[k] != 0 for k in ("live_provider_requests", "native_inference_calls"))
            or value["key_custody"] != "unassessed" or value["operator_appointments"] != "unassessed"
            or not isinstance(value["protocols"], list) or len(value["protocols"]) != 2):
        raise ValueError("Closed materialization report required")
    for item, name, states in zip(value["protocols"], ("round_trip", "interrupted_copy"), (ROUND_TRIP, INTERRUPTED), strict=True):
        expected = COUNTS[name]
        if (not isinstance(item, dict) or set(item) != {"name", "cases", "source_preparation_operations", "controller_reads", *expected, *TRUE, *FALSE}
                or item["name"] != name or item["cases"] != [{"id": f"M{i:02}", "state": s} for i, s in enumerate(states, 1)]
                or any(item[k] is not True for k in TRUE) or any(item[k] is not False for k in FALSE)
                or type(item["source_preparation_operations"]) is not int or item["source_preparation_operations"] != 3
                or type(item["controller_reads"]) is not int or item["controller_reads"] != 0
                or any(item[k] != v or type(item[k]) is not type(v) for k, v in expected.items())):
            raise ValueError("Frozen materialization outcomes differ")
    return {"qualified_protocols": 2, "frozen_outcomes": 36, "intentional_SIGKILL_exits": 1, "production_activation": False}
