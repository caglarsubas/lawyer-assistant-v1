"""Reject incomplete, changed or over-claiming disposable native receipts."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from journal_copy_restart_report import COUNTS, FALSE, INTERRUPTED, ROUND_TRIP, TRUE, validate  # noqa: E402


def report():
    return {"schema": "native-journal-copy-restart-v1", "receipt_manifest_sha256": "a" * 64,
        "controller_manifest_sha256": "b" * 64, "filesystem": "ext4", "read_only_packages_exact": True,
        "private_case_inputs": False, "power_loss_qualified": False, "production_activation": False,
        "live_provider_requests": 0, "native_inference_calls": 0, "key_custody": "unassessed",
        "operator_appointments": "unassessed", "protocols": [{"name": name,
            "cases": [{"id": f"M{i:02}", "state": state} for i, state in enumerate(states, 1)],
            "source_preparation_operations": 3, "controller_reads": 0, **copy.deepcopy(COUNTS[name]),
            **dict.fromkeys(TRUE, True), **dict.fromkeys(FALSE, False)}
            for name, states in (("round_trip", ROUND_TRIP), ("interrupted_copy", INTERRUPTED))]}


def test_declared_native_matrix_requires_all_processes_and_one_real_interruption():
    assert validate(report(), "a" * 64, "b" * 64) == {"qualified_protocols": 2, "frozen_outcomes": 41,
        "intentional_SIGKILL_exits": 1, "production_activation": False}


@pytest.mark.parametrize("change", ["missing_case", "acknowledged_kill", "automatic_resume", "extra_field",
    "wrong_source_pin", "private_input", "power_loss_claim", "unverified_exit", "target_count"])
def test_changed_or_overclaiming_report_cannot_qualify(change):
    v = report()
    p = v["protocols"][1]
    if change == "missing_case":
        p["cases"].pop()
    elif change == "acknowledged_kill":
        p["acknowledged_responses"] += 1
    elif change == "automatic_resume":
        p["automatic_resume"] = True
    elif change == "extra_field":
        v["operator_approved"] = True
    elif change == "wrong_source_pin":
        v["controller_manifest_sha256"] = "f" * 64
    elif change == "private_input":
        v["private_case_inputs"] = True
    elif change == "power_loss_claim":
        v["power_loss_qualified"] = True
    elif change == "unverified_exit":
        p["all_process_exits_verified"] = False
    else:
        p["target_entries"] += 1
    with pytest.raises(ValueError):
        validate(v, "a" * 64, "b" * 64)
