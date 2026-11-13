"""A repair summary cannot conceal unresolved acceptance or replace its baseline."""

import copy
import json
from pathlib import Path

import pytest

from scripts.build_delivered_uat_report import followup_summary

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "d9ff2b16cc91726ffa4fb2f44dc45d18f53aff4c"


def fixture_receipt():
    # Invented passing copy for presentation tests; never written as evidence.
    receipt = json.loads((ROOT / "docs/quality/audit-run-results.json").read_text())
    receipt.update(audit_baseline=BASELINE, source_commit="2" * 40, selected_checks_passed=True,
                   source_worktree_dirty=False)
    for case in receipt["cases"]:
        case["result"] = "pass"
    receipt["counts"] = {"pass": len(receipt["cases"]), "fail": 0, "known_failure": 0, "not_passed": 0}
    return receipt


def test_repair_summary_keeps_prior_failures_and_deployment_gates_visible():
    text = followup_summary(fixture_receipt(), BASELINE)
    assert "18/18" in text and "previously 16/18" in text and "28 audit-tool" in text
    assert "remain pending" in text and "historical evidence" in text
    assert followup_summary(None, BASELINE) == ""


def test_incomplete_failed_unbound_or_unreviewed_run_cannot_claim_repair_acceptance():
    baseline = fixture_receipt()
    mutations = [
        {"selected_checks_passed": False}, {"audit_baseline": "3" * 40}, {"source_commit": "<script>"},
        {"source_worktree_dirty": True}, {"production_uat": "qualified"}, {"human_legal_review": "granted"},
        {"cases": baseline["cases"][:-1]},
        {"cases": baseline["cases"] + [baseline["cases"][0]]},
        {"inventory": {**baseline["inventory"], "browser_complete": False}},
        {"counts": {**baseline["counts"], "known_failure": 1}},
    ]
    failed = copy.deepcopy(baseline["cases"])
    failed[-1]["result"] = "known_failure"
    mutations.append({"cases": failed})
    for mutation in mutations:
        with pytest.raises(ValueError):
            followup_summary({**baseline, **mutation}, BASELINE)
