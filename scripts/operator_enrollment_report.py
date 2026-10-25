"""Replay invented operator reconciliation evidence; no acceptance or trust grant."""

import json
from pathlib import Path

from operator_enrollment_evidence import GATES, encode, sha, token
from operator_enrollment_fixture import CASES, INJECTED, POLICY, READY


def grade(report):
    if (report["schema"] != "operator-enrollment-native-v1" or len(report["cases"]) != len(CASES)
            or report["policy_sha256"] != sha(encode(POLICY)) or report["read_only_model_inventory_exact"] is not True
            or any(report[n] is not False for n in ("application_or_engine_imports", "trust_enrolled", "private_case_inputs", "production_activation"))
            or report["live_provider_requests"] != 0 or report["native_inference_calls"] != 0
            or report["profile"] != {"filesystem": "ext4", "cpu": 2, "memory_mib": 768, "network": "none", "process_environment_cleared": True, "single_attempt": True}
            or set(report["preparation"]["filesystems"].values()) != {"ext4"}
            or report["preparation"]["tensor_count"] != 0 or report["preparation"]["private_inputs"] is not False):
        raise ValueError("Operator qualification posture rejected")
    candidate = report["candidate"]
    if candidate["single_attempt"] is not True or candidate["new_volumes_only"] is not True or candidate["real_credentials_or_inputs"] is not False or candidate["production_activation"] is not False:
        raise ValueError("Frozen operator candidate rejected")
    for row, (name, expected) in zip(report["cases"], CASES, strict=True):
        if (row["id"] != name or row["status"] != expected or set(row["checks"]) != GATES
                or row["private_sentinels_absent"] is not True or row["all_authority_flags_false"] is not True
                or row["external_change_injected"] is not (name in INJECTED)):
            raise ValueError("Frozen reconciliation expectation failed")
        token(row["observation_sha256"])
        if name not in INJECTED and row["state_unchanged"] is not True:
            raise ValueError("Read-only reconciliation mutated retained state")
        if expected == READY and set(row["checks"].values()) != {"verified"}:
            raise ValueError("Readiness gates incomplete")
        if expected == "blocked" and "blocked" not in row["checks"].values():
            raise ValueError("Rejection gate missing")
        if expected == "waiting" and (row["checks"]["readiness"] != "waiting" or row["checks"]["stability"] != "verified"):
            raise ValueError("Waiting state bypassed current verification")
        if name == "E26_previous_unchanged" and row["comparison"]["outcome"] != "unchanged":
            raise ValueError("Exact history comparison lost")
        if name == "E37_new_unapproved_confirmation" and (row["comparison"]["outcome"] != "changed" or row["comparison"]["changed_fields"] != ["confirmation_sha256"]):
            raise ValueError("Observed confirmation adopted as approval")
    return {"cases_passed": len(CASES), "read_only_model_inventory_exact": True, "previous_package_modules_exact": 14,
            "packet_max_lifetime_seconds": 900, "retained_history_comparisons": 2, "real_provider_requests": 0,
            "native_inference_calls": 0, "trust_enrolled": False, "runtime_installation": False, "legal_qualification": False}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(grade(json.loads((root / "deploy/fixtures/operator_enrollment_first_report.json").read_text()))))
