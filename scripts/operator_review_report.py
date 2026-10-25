"""Verify retained disposable authenticated-review evidence; never grant authority."""

import json
from pathlib import Path

from operator_enrollment_evidence import encode, sha, token
from operator_review_fixture import CASES, POLICY

PREPARE_DENIED = {2, 3, 4, 5, 28, 32, 33, 34, 35, 36, 37, 42}
THREE_REQUESTS = {1, 22, 23, 24, 26, 31, 38, 39, 41, 43}
FOUR_REQUESTS = {27, 30, 40}
RECORDED = THREE_REQUESTS | FOUR_REQUESTS


def grade(report):
    if (report["schema"] != "authenticated-operator-review-native-v1" or len(report["cases"]) != len(CASES)
            or report["policy_sha256"] != sha(encode(POLICY)) or report["actual_loopback_servers"] != 44
            or report["actual_HTTP_requests"] != 92 or report["read_only_model_and_package_inventory_exact"] is not True
            or report["actual_app_auth_used"] is not True
            or any(report[k] is not False for k in ("app_main_or_provider_imported", "real_accounts_or_sessions_used", "real_trust_enrolled", "runtime_installation", "private_case_inputs", "production_activation"))
            or report["live_provider_requests"] != 0 or report["native_inference_calls"] != 0
            or report["profile"] != {"filesystem": "ext4", "cpu": 2, "memory_mib": 768, "network": "none", "process_environment_cleared": True, "single_attempt": True}
            or set(report["preparation"]["filesystems"].values()) != {"ext4"}
            or report["preparation"]["tensor_count"] != 0 or report["preparation"]["private_inputs"] is not False):
        raise ValueError("Authenticated review qualification posture rejected")
    candidate = report["candidate"]
    if candidate["single_attempt"] is not True or candidate["new_volumes_only"] is not True or candidate["real_credentials_or_inputs"] is not False or candidate["production_activation"] is not False:
        raise ValueError("Frozen authenticated-review candidate rejected")
    for row, (name, expected) in zip(report["cases"], CASES, strict=True):
        number = int(name[1:3])
        requests = 1 if number in PREPARE_DENIED else 3 if number in THREE_REQUESTS else 4 if number in FOUR_REQUESTS else 2
        if (row["id"] != name or row["status"] != expected or row["HTTP_requests"] != requests
                or row["handoff_records"] != (0 if number in PREPARE_DENIED else 1)
                or row["decision_records"] != (1 if number in RECORDED else 0)
                or row["credentials_absent_from_responses_and_review_records"] is not True
                or row["all_authority_flags_false"] is not True or row["actual_app_session_auth"] is not True
                or row["runtime_installation"] is not False or row["real_trust_enrolled"] is not False):
            raise ValueError("Frozen review expectation or immutable history failed")
        token(row["ledger_sha256"])
    return {"cases_passed": 44, "actual_loopback_servers": 44, "actual_HTTP_requests": 92,
            "actual_app_session_and_RBAC_checks": True, "disposable_accounts_only": True,
            "read_only_model_and_package_exact": True, "native_inference_calls": 0, "real_trust_enrolled": False,
            "runtime_installation": False, "legal_qualification": False}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(grade(json.loads((root / "deploy/fixtures/authenticated_operator_first_report.json").read_text()))))
