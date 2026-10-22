"""Prepare a sealed native acceptance declaration; no execution implementation.

Reads public source code and invented fixtures only. Never loads application
settings, credentials, private documents, a provider client or a network transport.
"""

import argparse
import hashlib
import json
from pathlib import Path

from disposable_diverse_adapter import prepared_context
from diverse_quote_bundles import plan_diverse, sha
from native_acceptance_cases import CASES, SUITE, SUITE_SHA256, originals_for

from app.evidence_prompt import canonical

ROOT = Path(__file__).resolve().parents[1]
CODE = (
    "scripts/native_acceptance_cases.py", "scripts/native_acceptance_plan.py", "scripts/native_acceptance_grading.py",
    "scripts/diverse_quote_bundles.py", "scripts/disposable_diverse_adapter.py",
    "scripts/disposable_bundle_adapter.py", "scripts/budgeted_quote_bundles.py", "scripts/offline_quotation_boundaries.py",
    "backend/app/context_packing.py", "backend/app/evidence_prompt.py", "backend/app/provider.py",
    "backend/app/config.py", "backend/app/analysis_output_contract.py", "backend/pyproject.toml", "backend/uv.lock",
)


def build_plan():
    rows = []
    for case in CASES:
        sources = originals_for(case)
        limit = case.get("context_limit", 8192)
        planner = plan_diverse(case["question"], sources, context_limit=limit)
        wire, messages = prepared_context(case["question"], sources, planner, limit)
        disposition = ("blocked_before_transport" if not wire["measurement"]["within_budget"]
                       else "no_candidates_no_call" if not planner["bundles"] else "native_candidate")
        # Expected groups are sealed separately. The later executor must send only
        # these exact messages, never the case record or grading data.
        rows.append({"id": case["id"], "kind": case["kind"], "originals": sources,
                     "planner": planner, "wire": wire, "messages": messages, "disposition": disposition,
                     "criteria_sha256": sha(canonical({"groups": case["groups"],
                                                       "expect_empty": case.get("expect_empty", False)}))})
    value = {
        "schema": "frozen-native-acceptance-plan-v1", "suite": SUITE, "suite_sha256": SUITE_SHA256,
        "code_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in CODE},
        "state": "frozen_plan_only_not_executed", "execution_authorized": False,
        "inputs": "invented_extracted_text_only_no_private_documents_or_file_format_qualification",
        "provider_contract": {
            "tenant": "lawyer-assistant-v1", "organization": "org-lawyer",
            "key_id": "lawyer-assistant-v1-primary", "model": "ministral-3:8b",
            "context_limit_units": 8192, "temperature": 0, "max_completion_tokens": 1000,
            "completion_reserve_units": 1200, "stream": False, "response_bytes": 8192,
            "selection_content_bytes": 4096, "response_format": {"type": "json_object"},
            "expected_native_model_digest": None, "model_digest_state": "not_yet_attested",
            "transport_origin_state": "not_yet_attested",
            "transport_policy": "private_native_or_explicitly_approved_laptop_tunnel_no_cloud_no_fallback",
            "relay_retries": 0, "metadata_ttl_seconds": 0,
            "identity_preconditions": ["fresh_digest_and_registry_context_pin_before_any_completion",
                "same_digest_model_tenant_origin_and_local_only_route_before_and_after_each_call",
                "retain_server_side_binding_receipt_without_bearer_or_source_text_in_public_output",
                "reject_unattested_unknown_or_changed_identity_not_just_a_matching_model_name"],
        },
        "schedule": {
            "seed": None, "order": "declared_no_shuffle_no_selection_after_results",
            "preflight_controls": ["P1412", "P1413", "P1414"],
            "serial_smoke": ["P1401"],
            "concurrent_waves": [["P1402", "P1403", "P1404", "P1405", "P1406"],
                                 ["P1407", "P1408", "P1409", "P1410", "P1411"]],
            "max_concurrent_jobs": 5, "attempts_per_case": 1, "completion_requests_upper_bound": 11,
            "adapter_metadata_requests_upper_bound": 11,
            "identity_binding_metadata_requests_upper_bound": 24,
            "total_metadata_requests_upper_bound": 35,
            "provider_total_response_budget_seconds": 120, "provider_http_socket_timeout_seconds": 90,
            "per_wave_wall_seconds": 150, "trial_wall_seconds": 450,
            "parallelism_proof": "five_worker_start_barrier_and_observed_completion_request_interval_overlap_required",
            "one_trial_is_not_sustained_capacity": True,
        },
        "grading": {
            "positive_cases": "all_required_groups_in_exact_selected_bundles_including_conditions_and_adverse_sources",
            "negative_cases": "expect_empty_requires_empty_selection_not_merely_a_schema_valid_response",
            "denominators": "all_frozen_cases_groups_and_source_versions_including_unavailable_and_blocked",
            "also_report": ["availability_before_model", "selected_over_available_groups",
                "selected_over_all_required_groups", "both_sides_per_adverse_case", "per_kind_results",
                "explicit_empty_case_accuracy", "no_call_controls_separately", "all_spans_versions_exact",
                "fallback_and_partial_source_counts", "transport_status_and_elapsed_time_including_failures"],
            "release_gate": "every_positive_case_and_group_and_explicit_empty_case_passes_no_integrity_or_transport_failure",
            "controls_do_not_erase_quality_failures": True,
            "offline_selection_grades_are_not_native_receipts": True,
        },
        "stop_conditions": {
            "before_any_transport": ["missing_separate_execution_authorization_or_identity_attestation",
                "plan_code_sources_criteria_wire_or_budget_differs", "negative_no_call_control_fails",
                "private_mount_input_egress_route_or_credential_logging_detected"],
            "stop_new_work_cancel_pending_drain_inflight_to_deadline_no_retry": ["smoke_failure", "HTTP_502_or_any_transport_or_metadata_failure",
                "wrong_model_digest_tenant_origin_or_fallback", "deadline_or_response_bound_failure",
                "unresolvable_or_fabricated_bundle_id_or_changed_evidence", "caller_cancellation"],
            "retain_all": "completed_and_inflight_failures_cancellations_and_not_started_cases_never_pass_or_drop",
            "semantic_failure": "retain_and_score_once_never_reword_repair_prompt_or_retry_same_case_into_success",
        },
        "later_receipt_contract": ["exact_plan_code_suite_prompt_wire_and_complete_source_hashes",
            "owner_execution_authorization_and_attested_model_digest_context_transport_binding",
            "one_attempt_per_declared_case_with_start_end_monotonic_duration_and_sanitized_request_ids",
            "raw_response_hash_strict_parsed_ids_exact_resolved_bundle_hash_and_provider_usage_finish_status",
            "per_case_metadata_and_completion_status_failure_phase_and_no_fallback_verification",
            "five_way_barrier_and_observed_overlap_not_only_five_workers_submitted",
            "skipped_cancelled_and_unavailable_cases_in_denominators_with_explicit_reasons",
            "before_after_originals_versions_private_data_review_history_and_production_posture_proof"],
        "production_activation": False, "native_qualification": False, "legal_qualification": False,
        "counts": {"native_calls": 0, "http_calls": 0, "private_documents": 0, "review_decisions": 0},
        "cases": rows,
    }
    value["plan_sha256"] = sha(canonical(value))
    return value


def validate_plan(value):
    if canonical(value) != canonical(build_plan()):
        raise ValueError("Stale or modified native acceptance declaration")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = build_plan()
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"state": value["state"], "plan_sha256": value["plan_sha256"], "counts": value["counts"]}))


if __name__ == "__main__":
    main()
