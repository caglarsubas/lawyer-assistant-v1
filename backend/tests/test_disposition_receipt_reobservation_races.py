"""Fresh authorized reads of pinned metadata using disposable encrypted histories."""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import disposition_receipt_reobservation as r  # noqa: E402
import disposition_reconciliation_receipt as receipts  # noqa: E402
import operator_enrollment_evidence as e  # noqa: E402
import private_inventory_receipts as stored  # noqa: E402
from disposition_journal_reconciliation import DispositionReconciler  # noqa: E402
from test_disposition_journal_reconciliation import body, proposed, protected, reviewed  # noqa: E402
from test_disposition_journal_reconciliation import f as f  # noqa: E402
from test_disposition_receipt_reobservation import call, retained, safe  # noqa: E402


@pytest.mark.parametrize("change", ["window", "reviewer", "source"])
def test_changed_current_context_preserves_exact_stale_review_as_history(f, change):
    p = proposed(f)
    d = reviewed(f, p)
    service, raw = retained(f, body(f, p, d))
    if change == "window":
        f.now += 301
    elif change == "reviewer":
        f.revoke("reviewer")
    else:
        e.retain(f.copy.readiness.candidate.root / ("e" * 32 + ".receipt"), stored.MAGIC + os.urandom(48))
    before = protected(f)
    value = call(f, service, raw)
    safe(value, "receipt_reobserved")
    v = value["reobservation"]
    assert v["comparison"]["outcome"] == "changed_metadata"
    assert "planning_review_current" in v["comparison"]["changed_fields"]
    assert v["current_receipt"]["outcome"] == "retained_disposition_reconciled_stale"
    assert not v["current_receipt"]["planning_review_current"]
    assert v["current_receipt"]["decision"] == "accept" and protected(f) == before


@pytest.mark.parametrize("change", ["caller", "window", "source", "exception", "timeout"])
def test_changes_during_fresh_reads_withhold_the_complete_comparison(f, change):
    p = proposed(f)
    d = reviewed(f, p)
    service, raw = retained(f, body(f, p, d))
    original = receipts.DispositionReceiptService.dispatch
    count = 0
    async def dispatch(self, *args, **kwargs):
        nonlocal count
        value = await original(self, *args, **kwargs)
        count += 1
        if count == 1:
            if change == "caller":
                f.revoke("preparer")
            elif change == "window":
                f.now += 301
            elif change == "source":
                e.retain(f.copy.readiness.candidate.root / ("e" * 32 + ".receipt"), stored.MAGIC + os.urandom(48))
            elif change == "exception":
                raise RuntimeError("SYNTHETIC private diagnostic")
            else:
                raise TimeoutError
        return value
    before = protected(f)
    with patch.object(receipts.DispositionReceiptService, "dispatch", dispatch):
        value = call(f, service, raw)
    safe(value, {"caller": "denied", "window": "snapshot_or_publication_conflict", "source": "snapshot_or_publication_conflict",
                 "exception": "unavailable", "timeout": "budget_exhausted"}[change])
    assert "SYNTHETIC" not in json.dumps(value)
    if change != "source":
        assert protected(f) == before


def test_final_revocation_expiry_size_budget_and_cancellation_withhold_output(f):
    p = proposed(f)
    d = reviewed(f, p)
    service, raw = retained(f, body(f, p, d))
    before = protected(f)
    with patch.object(receipts, "MAX_BYTES", 1):
        safe(call(f, service, raw), "unverifiable")
    original = r.project
    def late_expiry(*args):
        value = original(*args)
        f.now += 301
        return value
    with patch.object(r, "project", late_expiry):
        safe(call(f, service, raw), "snapshot_or_publication_conflict")
    f.now -= 301
    def late_revocation(*args):
        value = original(*args)
        f.revoke("preparer")
        return value
    with patch.object(r, "project", late_revocation):
        safe(call(f, service, raw), "denied")
    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError
    with patch.object(service.service.reconciler.__class__, "dispatch", cancelled):
        # The revoked reader is rejected before any source read can occur.
        safe(call(f, service, raw), "denied")
    assert protected(f) == before


def test_cancellation_propagates_and_oversized_projection_never_returns_partial_output(f):
    service, raw = retained(f, body(f))
    before = protected(f)
    previous = e.decode(raw)
    with pytest.raises(TimeoutError):
        r.project(previous, {**previous, "oversized": "x" * receipts.MAX_BYTES}, e.sha(raw))
    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError
    with patch.object(DispositionReconciler, "dispatch", cancelled), pytest.raises(asyncio.CancelledError):
        call(f, service, raw)
    with patch.object(r, "project", side_effect=TimeoutError):
        safe(call(f, service, raw), "budget_exhausted")
    assert protected(f) == before


def test_clock_regression_between_fresh_reads_withholds_even_empty_metadata(f):
    service, raw = retained(f, body(f))
    original = receipts.DispositionReceiptService.dispatch
    count = 0
    async def dispatch(self, *args, **kwargs):
        nonlocal count
        value = await original(self, *args, **kwargs)
        count += 1
        if count == 1:
            f.now -= 1
        return value
    before = protected(f)
    with patch.object(receipts.DispositionReceiptService, "dispatch", dispatch):
        # The first fresh receipt is future-dated relative to the regressed clock.
        safe(call(f, service, raw), "unverifiable")
    assert protected(f) == before


