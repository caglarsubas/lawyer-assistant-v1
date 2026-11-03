"""Fresh authorized reads of pinned metadata using disposable encrypted histories."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import disposition_receipt_reobservation as r  # noqa: E402
import disposition_reconciliation_receipt as receipts  # noqa: E402
import operator_enrollment_evidence as e  # noqa: E402
from disposition_journal_reconciliation import DispositionReconciler  # noqa: E402
from test_disposition_journal_reconciliation import body, proposed, protected, reviewed  # noqa: E402
from test_disposition_journal_reconciliation import f as f  # noqa: E402


def retained(f, request):
    service = receipts.DispositionReceiptService(reconciler=DispositionReconciler(disposition=f.disposition))
    v = asyncio.run(service.dispatch(f.scope(), "receipt", **request))
    assert v["state"] == "receipt_ready"
    return r.DispositionReceiptReobserver(service=service, expected_receipt_sha256=v["receipt_sha256"]), e.encode(v["receipt"])


def call(f, service, raw, scope=None, operation="reobserve", **extra):
    return asyncio.run(service.dispatch(scope or f.scope(), operation, receipt_bytes=raw, **extra))


def safe(value, state):
    assert value["state"] == state and all(value[k] is v for k, v in r.LIMITS.items())
    if state != "receipt_reobserved":
        assert value["reobservation"] is value["reobservation_sha256"] is None
        return
    v = value["reobservation"]
    assert all(v[k] is b for k, b in r.LIMITS.items())
    assert len(e.encode(v)) <= receipts.MAX_BYTES and e.sha(e.encode(v)) == value["reobservation_sha256"]
    assert v["current_receipt_sha256"] == e.sha(e.encode(v["current_receipt"]))
    assert v["reference_basis"] == "exact_retained_selection_with_explicit_nulls"
    assert v["comparison_basis"] == "retained_unsigned_metadata_vs_fresh_authorized_reads"


@pytest.mark.parametrize("decision", ["accept", "changes_required", "reject"])
def test_exact_independent_decision_is_reobserved_without_changing_both_histories(f, decision):
    p = proposed(f)
    d = reviewed(f, p, decision)
    request = body(f, p, d)
    service, raw = retained(f, request)
    before = protected(f)
    value = call(f, service, raw)
    safe(value, "receipt_reobserved")
    observed = value["reobservation"]
    assert observed["comparison"] == {"outcome": "unchanged_metadata", "changed_fields": []}
    assert observed["current_receipt"]["references"] == request
    assert observed["current_receipt"]["decision"] == decision
    assert observed["retained_receipt_sha256"] == e.sha(raw)
    assert "plan" not in observed and "review" not in observed
    assert str(f.root) not in json.dumps(value) and protected(f) == before


def test_current_reader_is_authorized_independently_of_retained_actor_and_timestamp(f):
    p = proposed(f)
    service, raw = retained(f, body(f, p))
    f.now += 1
    before = protected(f)
    value = call(f, service, raw, f.scope("reviewer"))
    safe(value, "receipt_reobserved")
    current = value["reobservation"]["current_receipt"]
    assert current["actor_sha256"] != e.decode(raw)["actor_sha256"]
    assert current["issued_at"] > e.decode(raw)["issued_at"]
    assert value["reobservation"]["comparison"]["outcome"] == "unchanged_metadata"
    assert protected(f) == before


@pytest.mark.parametrize("phase", ["empty", "missing_plan_refs", "plan_only", "missing_decision_ref"])
def test_absent_references_are_not_filled_from_newly_visible_publications(f, phase):
    p = proposed(f) if phase != "empty" else None
    if phase == "missing_decision_ref":
        reviewed(f, p)
    service, raw = retained(f, body(f, p if phase in {"plan_only", "missing_decision_ref"} else None))
    if phase == "empty":
        proposed(f)
    elif phase == "plan_only":
        reviewed(f, p)
    before = protected(f)
    value = call(f, service, raw)
    safe(value, "receipt_reobserved")
    current = value["reobservation"]["current_receipt"]
    assert current["references"]["decision_ciphertext_sha256"] is None
    assert current["references"]["plan_sha256"] == e.decode(raw)["references"]["plan_sha256"]
    assert current["decision"] is None and not current["decision_authenticated"]
    assert not current["planning_review_current"] and not value["acknowledgement_recovered"]
    assert current["outcome"] == ("plan_references_unavailable" if phase in {"empty", "missing_plan_refs"}
                                   else "decision_reference_not_supplied")
    assert protected(f) == before
