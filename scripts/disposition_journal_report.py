"""Frozen plan/review publication interruptions; observations never recover acks."""

from controller_stage_manifest import hex_digest

PLAN = ["observed_disposition_journal_metadata", "connection_closed", "observed_disposition_journal_metadata"]
TAIL = ["snapshot_or_publication_conflict", "denied", "denied"]
REVIEW = ["disposition_needs_independent_review", "observed_disposition_journal_metadata", "connection_closed",
          "observed_disposition_journal_metadata"]
CASES = {
    "plan_before_link": [*PLAN, "plan_not_observed", *TAIL],
    "plan_after_publish": [*PLAN, "plan_references_unavailable", *TAIL],
    "review_before_link": [*REVIEW, "decision_not_observed", "unverifiable", "snapshot_or_publication_conflict", "denied",
                           "observed_disposition_journal_metadata", "decision_not_observed", "denied", "denied"],
    "review_after_publish": [*REVIEW, "decision_reference_not_supplied", "unverifiable", "snapshot_or_publication_conflict", "denied",
                             "observed_disposition_journal_metadata", "decision_reference_not_supplied", "denied", "denied"],
    "acknowledged_review": ["disposition_needs_independent_review", "reviewed_disposition_plan", "observed_disposition_journal_metadata",
        "retained_disposition_reconciled", "decision_reference_not_supplied", "unverifiable", "snapshot_or_publication_conflict",
        "snapshot_or_publication_conflict", "denied", "observed_disposition_journal_metadata", "retained_disposition_reconciled_stale",
        "retained_disposition_reconciled_stale", "denied", "denied"],
}
TRUE = {"actual_app_auth", "exact_versions_rechecked", "source_histories_exact", "readonly_operations_exact",
        "disposition_history_append_only", "all_process_exits_verified", "independent_bindings_preserved"}
FALSE = {"acknowledgement_recovered", "automatic_resume", "production_activation"}
RECORDS = {"plan_before_link": (0, 1), "plan_after_publish": (1, 0), "review_before_link": (1, 1),
           "review_after_publish": (2, 0), "acknowledged_review": (2, 0)}


def validate(value, receipt_manifest, controller_manifest):
    fields = {"schema", "receipt_manifest_sha256", "controller_manifest_sha256", "protocols", "filesystem", "read_only_packages_exact",
              "private_case_inputs", "live_provider_requests", "native_inference_calls", "key_custody", "operator_appointments",
              "power_loss_qualified", "production_activation"}
    if (not isinstance(value, dict) or set(value) != fields or value["schema"] != "native-disposition-journal-v1"
            or value["receipt_manifest_sha256"] != hex_digest(receipt_manifest)
            or value["controller_manifest_sha256"] != hex_digest(controller_manifest)
            or value["filesystem"] != "ext4" or value["read_only_packages_exact"] is not True
            or any(value[k] is not False for k in ("private_case_inputs", "power_loss_qualified", "production_activation"))
            or any(type(value[k]) is not int or value[k] != 0 for k in ("live_provider_requests", "native_inference_calls"))
            or value["key_custody"] != "unassessed" or value["operator_appointments"] != "unassessed"
            or not isinstance(value["protocols"], list) or len(value["protocols"]) != len(CASES)):
        raise ValueError("Closed disposition journal report required")
    for item, (name, states) in zip(value["protocols"], CASES.items(), strict=True):
        killed = int(name != "acknowledged_review")
        n = len(states)
        counts = {"processes": n, "intentional_SIGKILL_exits": killed, "clean_exits": n - killed,
                  "acknowledged_responses": n - killed, "source_preparation_operations": 9,
                  "controller_reads": 0, "retained_records": RECORDS[name][0], "retained_staging": RECORDS[name][1]}
        if (not isinstance(item, dict) or set(item) != {"name", "cases", *counts, *TRUE, *FALSE}
                or item["name"] != name or item["cases"] != [{"id": f"D{i:02}", "state": s} for i, s in enumerate(states, 1)]
                or any(item[k] is not True for k in TRUE) or any(item[k] is not False for k in FALSE)
                or any(type(item[k]) is not int or item[k] != v for k, v in counts.items())):
            raise ValueError("Frozen disposition journal outcomes differ")
    return {"qualified_protocols": 5, "frozen_outcomes": 52, "intentional_SIGKILL_exits": 4, "production_activation": False}
