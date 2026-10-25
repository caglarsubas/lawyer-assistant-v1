"""Grade retained frozen recovery evidence, never authorize enrollment or review."""

import json
from pathlib import Path

from anchored_review_fixture import CASES, POLICY
from operator_enrollment_evidence import encode, sha, token

# Frozen from each case's explicit request path before native execution.
REQUESTS = [3, 5, 5, 5, 5, 3, 6, 6, 3, 5, 3, 3, 4, 3, 4, 5, 5, 3, 2, 3, 4, 3, 5, 4, 4, 3, 3, 4, 5, 5, 3]
HANDOFFS = [1, 1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 2, 2, 1, 1, 1, 2, 2, 2, 2, 2, 1, 1, 1, 2, 1, 1]
DECISIONS = [1, 1, 1, 1, 1, 1, 1, 2, 0, 1, 0, 0, 0, 0, 1, 2, 2, 1, 0, 1, 1, 1, 2, 1, 1, 1, 1, 0, 2, 1, 0]


def grade(report):
    if (report["schema"] != "anchored-operator-review-native-v1" or len(report["cases"]) != len(CASES)
            or report["policy_sha256"] != sha(encode(POLICY)) or report["actual_loopback_servers"] != len(CASES)
            or report["actual_HTTP_requests"] != sum(REQUESTS)
            or report["read_only_model_and_package_inventory_exact"] is not True or report["actual_app_auth_used"] is not True
            or any(report[k] is not False for k in ("app_main_or_provider_imported", "real_accounts_or_sessions_used", "real_trust_enrolled", "runtime_installation", "private_case_inputs", "production_activation"))
            or report["live_provider_requests"] != 0 or report["native_inference_calls"] != 0
            or report["profile"] != {"filesystem": "ext4", "cpu": 2, "memory_mib": 768, "network": "none", "process_environment_cleared": True, "single_attempt": True}
            or set(report["preparation"]["filesystems"].values()) != {"ext4"}
            or report["preparation"]["tensor_count"] != 0 or report["preparation"]["private_inputs"] is not False):
        raise ValueError("Frozen recovery posture rejected")
    for row, (name, expected), requests, handoffs, decisions in zip(report["cases"], CASES, REQUESTS, HANDOFFS, DECISIONS, strict=True):
        if (row["id"] != name or row["status"] != expected or row["HTTP_requests"] != requests
                or row["handoff_records"] != handoffs or row["decision_records"] != decisions
                or any(row[k] is not True for k in ("credentials_absent_from_responses_and_review_records", "all_authority_flags_false", "actual_app_session_auth", "independent_anchor", "original_records_not_rewritten_by_recovery", "recovery_is_not_new_review", "fresh_review_requires_new_decision"))
                or row["runtime_installation"] is not False or row["real_trust_enrolled"] is not False):
            raise ValueError("Frozen recovery history or request count rejected")
        token(row["ledger_sha256"])
    return {"cases_passed": len(CASES), "actual_loopback_servers": len(CASES), "actual_HTTP_requests": sum(REQUESTS),
            "actual_app_session_and_RBAC_checks": True, "disposable_accounts_only": True,
            "read_only_model_and_package_exact": True, "native_inference_calls": 0, "real_trust_enrolled": False,
            "runtime_installation": False, "legal_qualification": False}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(grade(json.loads((root / "deploy/fixtures/anchored_review_first_report.json").read_text()))))
