"""Private exact-reference receipts using real disposable sessions and journals."""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import disposition_reconciliation_receipt as r  # noqa: E402
import operator_enrollment_evidence as e  # noqa: E402
from disposition_journal_reconciliation import DispositionReconciler  # noqa: E402
from test_disposition_journal_reconciliation import body, proposed, protected, reviewed  # noqa: E402
from test_disposition_journal_reconciliation import f as f  # noqa: E402


def call(f, request, scope=None, operation="receipt"):
    service = r.DispositionReceiptService(reconciler=DispositionReconciler(disposition=f.disposition))
    return asyncio.run(service.dispatch(scope or f.scope("preparer"), operation, **request))


def safe(v, state):
    assert v["state"] == state
    assert {k: v[k] for k in r.LIMITS} == r.LIMITS
    if state != "receipt_ready":
        assert v["receipt"] is v["receipt_sha256"] is None
    else:
        receipt = v["receipt"]
        raw = e.encode(receipt)
        assert len(raw) <= r.MAX_BYTES and e.sha(raw) == v["receipt_sha256"]
        assert {k: receipt[k] for k in r.LIMITS} == r.LIMITS
        assert receipt["integrity_basis"] == "sha256_transport_checksum_only"


@pytest.mark.parametrize("decision", ["accept", "changes_required", "reject"])
def test_receipt_preserves_exact_independent_decision_and_both_histories(f, decision):
    p = proposed(f)
    d = reviewed(f, p, decision)
    request = body(f, p, d)
    before = protected(f)
    v = call(f, request)
    safe(v, "receipt_ready")
    receipt = v["receipt"]
    assert receipt["references"] == request and receipt["decision"] == decision
    assert receipt["plan_authenticated"] and receipt["decision_authenticated"]
    assert receipt["planning_review_current"]
    assert receipt["snapshot_sha256"] == request["expected_snapshot_sha256"]
    for key in ["binding_sha256", "source_snapshot_sha256", "journal_snapshot_sha256", "copy_snapshot_sha256"]:
        e.token(receipt[key])
    assert "plan" not in receipt and "review" not in receipt and "observation" not in receipt
    assert str(f.disposition.planner.journal.root) not in json.dumps(v)
    assert protected(f) == before


@pytest.mark.parametrize("phase", ["empty", "plan_missing_refs", "plan_only", "decision_missing_ref"])
def test_missing_references_stay_null_without_recovering_an_acknowledgement(f, phase):
    p = proposed(f) if phase != "empty" else None
    if phase == "decision_missing_ref":
        reviewed(f, p)
    request = body(f, p if phase in {"plan_only", "decision_missing_ref"} else None)
    before = protected(f)
    v = call(f, request)
    safe(v, "receipt_ready")
    receipt = v["receipt"]
    assert receipt["outcome"] == {"empty": "plan_not_observed", "plan_missing_refs": "plan_references_unavailable",
                                   "plan_only": "decision_not_observed", "decision_missing_ref": "decision_reference_not_supplied"}[phase]
    assert receipt["references"] == request and receipt["references"]["decision_ciphertext_sha256"] is None
    assert receipt["decision"] is None and not receipt["decision_authenticated"]
    assert not receipt["planning_review_current"]
    assert not receipt["acknowledgement_recovered"] and protected(f) == before


def test_stale_exact_review_is_history_and_never_renewed_authority(f):
    p = proposed(f)
    d = reviewed(f, p)
    f.now += 301
    request = body(f, p, d)
    before = protected(f)
    v = call(f, request)
    safe(v, "receipt_ready")
    assert v["receipt"]["outcome"] == "retained_disposition_reconciled_stale"
    assert v["receipt"]["decision"] == "accept" and not v["receipt"]["planning_review_current"]
    assert protected(f) == before


@pytest.mark.parametrize("kind", ["other", "revoked", "csrf", "origin", "cookie", "method"])
def test_receipts_do_not_bypass_current_session_scope_or_origin(f, kind):
    request = body(f)
    scope = f.scope("other" if kind == "other" else "preparer")
    if kind == "revoked":
        f.revoke("preparer")
    elif kind in {"csrf", "origin"}:
        field = b"origin" if kind == "origin" else b"x-csrf-token"
        scope["headers"] = [(k, b"invalid" if k == field else v) for k, v in scope["headers"]]
    elif kind == "cookie":
        scope["headers"].append((b"cookie", b"la_session=invalid"))
    elif kind == "method":
        scope["method"] = "GET"
    before = protected(f)
    safe(call(f, request, scope), "denied")
    assert protected(f) == before


def test_cancellation_propagates_without_creating_a_receipt_or_changing_history(f):
    request = body(f)
    before = protected(f)
    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError
    with patch.object(DispositionReconciler, "dispatch", cancelled), pytest.raises(asyncio.CancelledError):
        call(f, request)
    assert protected(f) == before


@pytest.mark.parametrize("kind", ["extra", "missing", "wrong_snapshot", "wrong_digest", "import", "execute"])
def test_closed_selection_requires_exact_versions_and_has_no_import_or_execution(f, kind):
    p = proposed(f)
    request = body(f, p)
    operation = "receipt"
    if kind == "extra":
        request["root"] = "/invented-private-location"
    elif kind == "missing":
        request.pop("decision_ciphertext_sha256")
    elif kind == "wrong_snapshot":
        request["expected_snapshot_sha256"] = "f" * 64
    elif kind == "wrong_digest":
        request["plan_sha256"] = "f" * 64
    else:
        operation = kind
    before = protected(f)
    safe(call(f, request, operation=operation), "snapshot_or_publication_conflict" if kind == "wrong_snapshot" else "unverifiable")
    assert protected(f) == before


@pytest.mark.parametrize("change", ["caller", "window", "exception", "timeout", "binding"])
def test_late_changes_and_failures_withhold_the_entire_receipt(f, change):
    p = proposed(f)
    d = reviewed(f, p)
    request = body(f, p, d)
    before = protected(f)
    original = DispositionReconciler.dispatch
    count = 0
    async def dispatch(self, scope, operation, **body):
        nonlocal count
        count += 1
        if count == 2:
            if change == "caller":
                f.revoke("preparer")
            elif change == "window":
                f.now += 301
            elif change == "exception":
                raise RuntimeError("SYNTHETIC confidential diagnostic")
            elif change == "timeout":
                raise TimeoutError
            else:
                raise ValueError("SYNTHETIC changed trusted binding")
        return await original(self, scope, operation, **body)
    with patch.object(DispositionReconciler, "dispatch", dispatch):
        v = call(f, request)
    safe(v, {"caller": "denied", "window": "snapshot_or_publication_conflict", "exception": "unavailable",
             "timeout": "budget_exhausted", "binding": "unverifiable"}[change])
    assert "SYNTHETIC" not in json.dumps(v) and protected(f) == before


def test_size_budget_and_final_revocation_never_return_partial_receipts(f):
    request = body(f)
    before = protected(f)
    with patch.object(r, "MAX_BYTES", 1):
        safe(call(f, request), "budget_exhausted")
    original = r.project
    def project(*args):
        value = original(*args)
        f.revoke("preparer")
        return value
    with patch.object(r, "project", project):
        safe(call(f, request), "denied")
    assert protected(f) == before
