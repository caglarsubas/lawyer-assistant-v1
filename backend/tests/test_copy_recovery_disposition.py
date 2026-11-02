"""Independent, metadata-only disposition reviews against exact retained observations."""
import asyncio
import copy
import os
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import operator_enrollment_evidence as e  # noqa: E402
import private_inventory_receipts as receipts  # noqa: E402
from copy_disposition_fixture import make as make_disposition  # noqa: E402
from copy_recovery_disposition import DECISIONS, FLAGS, REFS, DispositionPlanner  # noqa: E402
from journal_backup_fixture import Fixture  # noqa: E402
from journal_materialization import CopyOrigin  # noqa: E402
from journal_materialization_fixture import make  # noqa: E402
from test_journal_copy_reconciliation import request, roots  # noqa: E402
from test_journal_materialization import decide, files, materialize, prepare, proof  # noqa: E402


@pytest.fixture
def f(tmp_path):
    value = Fixture(tmp_path)
    assert value.decide(value.prepare())["state"] == "reviewed_for_metadata_planning"
    value.copy = make(value)
    value.operation = prepare(value, value.copy)
    value.copy_review = decide(value, value.copy, value.operation)
    value.disposition = make_disposition(value.copy, tmp_path / "dispositions")
    yield value
    value.store.engine.dispose()


def call(f, op, role="preparer", **body):
    return asyncio.run(f.disposition.dispatch(f.scope(role), op, **body))


def proposed(f, **overrides):
    body = {"plan_id": "a" * 32, "copy_refs": request(f, f.operation, f.copy_review),
            "disposition": "retain_for_independent_assessment", **overrides}
    return call(f, "prepare", **body)


def refs(plan):
    return {k: plan[k] for k in REFS}


def reviewed(f, plan, decision="accept", role="reviewer"):
    return call(f, "decide", role, **refs(plan), decision=decision, reason_code=DECISIONS[decision])


def inspected(f, plan, decision=None, role="preparer"):
    return call(f, "inspect", role, **refs(plan), decision_ciphertext_sha256=decision and decision["decision_ciphertext_sha256"])


def safe(value, state):
    assert value["state"] == state and value["metadata_only"] and value["planning_only"]
    assert value["source_read_only"] and value["fresh_independent_review_required"]
    assert not value["production_execution_authorized"] and not value["automatic_resume"]
    assert all(value[k] is False for k in FLAGS)
    if state in {"denied", "unverifiable", "snapshot_or_publication_conflict", "budget_exhausted", "unavailable", "retention_uncertain"}:
        assert value["plan"] is value["review"] is None


def test_acceptance_is_only_planning_and_never_changes_existing_histories(f):
    before = roots(f)
    p = proposed(f)
    safe(p, "disposition_needs_independent_review")
    d = reviewed(f, p)
    safe(d, "reviewed_disposition_plan")
    journal = files(f.disposition.planner.journal.root)
    v = inspected(f, p, d)
    safe(v, "retained_disposition_review")
    assert v["review"]["decision"] == "accept" and v["planning_review_current"]
    assert v["plan"]["reconciliation"]["state"] == "intent_not_observed"
    assert roots(f) == before and files(f.disposition.planner.journal.root) == journal and len(journal) == 2
    assert all(receipts.MAGIC in row[0] and b"retain_for_independent_assessment" not in row[0] for row in journal.values())
    safe(call(f, "materialize", **refs(p)), "unverifiable")
    safe(inspected(f, p), "retained_disposition_review")
    assert inspected(f, p)["review"] is None  # Never recover an unacknowledged decision.


@pytest.mark.parametrize("decision", ["changes_required", "reject"])
def test_negative_decisions_are_retained_without_execution(f, decision):
    p = proposed(f)
    safe(reviewed(f, p, decision), decision)
    before = files(f.disposition.planner.journal.root)
    safe(reviewed(f, p), "snapshot_or_publication_conflict")
    assert files(f.disposition.planner.journal.root) == before


@pytest.mark.parametrize("phase", ["partial", "exact_without_completion", "complete"])
def test_dispositions_require_exact_evidence_of_completion(f, phase):
    original = receipts._publish
    def publish(store, ident, raw):
        if phase == "exact_without_completion" and store is f.copy.controls.planner.journal and len(files(f.copy.readiness.candidate.root)) == 2:
            raise OSError("invented missing completion")
        value = original(store, ident, raw)
        if phase == "partial" and store is f.copy.readiness.candidate:
            raise OSError("invented partial copy")
        return value
    with patch.object(receipts, "_publish", publish):
        completion = materialize(f, f.copy, f.operation, f.copy_review)
    body = request(f, f.operation, f.copy_review, completion if phase == "complete" else None)
    if phase != "complete":
        iid = f.copy.ident("intent", f.operation["operation_id"], f.operation["plan_ciphertext_sha256"])
        body["intent_ciphertext_sha256"] = e.sha((f.copy.controls.planner.journal.root / (iid + ".receipt")).read_bytes())
    before = roots(f)
    p = proposed(f, copy_refs=body, disposition="retain_verified_history")
    if phase != "complete":
        safe(p, "unverifiable")
        assert not files(f.disposition.planner.journal.root)
        p = proposed(f, copy_refs=body, disposition="seek_fresh_independent_context")
    safe(p, "disposition_needs_independent_review")
    d = reviewed(f, p)
    safe(d, "reviewed_disposition_plan")
    v = inspected(f, p, d)
    assert v["plan"]["reconciliation"]["history"]["completion_authenticated"] is (phase == "complete")
    assert roots(f) == before


@pytest.mark.parametrize("change", ["expiry", "reviewer", "source"])
def test_retained_history_is_visible_but_stale_without_fresh_authority(f, change):
    p = proposed(f)
    d = reviewed(f, p)
    if change == "expiry":
        f.now += 301
    elif change == "reviewer":
        f.revoke("reviewer")
    else:
        e.retain(f.copy.readiness.candidate.root / ("e" * 32 + ".receipt"), receipts.MAGIC + os.urandom(48))
    before = roots(f), files(f.disposition.planner.journal.root)
    v = inspected(f, p, d)
    safe(v, "retained_disposition_review_stale")
    assert v["review"]["decision"] == "accept" and not v["planning_review_current"]
    assert (roots(f), files(f.disposition.planner.journal.root)) == before
    safe(reviewed(f, p), "snapshot_or_publication_conflict" if change != "reviewer" else "denied")


@pytest.mark.parametrize("kind", ["self", "other", "revoked", "csrf", "origin", "duplicate_cookie", "get"])
def test_review_requires_current_independent_authenticated_reviewer(f, kind):
    p = proposed(f)
    role = "preparer" if kind == "self" else "other" if kind == "other" else "reviewer"
    scope = f.scope(role)
    if kind == "revoked":
        f.revoke(role)
    elif kind in {"csrf", "origin"}:
        key = b"origin" if kind == "origin" else b"x-csrf-token"
        scope["headers"] = [(k, b"invalid" if k == key else v) for k, v in scope["headers"]]
    elif kind == "duplicate_cookie":
        scope["headers"].append((b"cookie", b"la_session=invalid"))
    elif kind == "get":
        scope["method"] = "GET"
    before = roots(f), files(f.disposition.planner.journal.root)
    safe(asyncio.run(f.disposition.dispatch(scope, "decide", **refs(p), decision="accept", reason_code=DECISIONS["accept"])), "denied")
    assert (roots(f), files(f.disposition.planner.journal.root)) == before


@pytest.mark.parametrize("field", ["plan_id", "plan_ciphertext_sha256", "plan_sha256", "decision_ciphertext_sha256"])
def test_wrong_retained_reference_withholds_history(f, field):
    p = proposed(f)
    d = reviewed(f, p)
    body = {**refs(p), "decision_ciphertext_sha256": d["decision_ciphertext_sha256"]}
    body[field] = "f" * (32 if field == "plan_id" else 64)
    before = files(f.disposition.planner.journal.root)
    safe(call(f, "inspect", **body), "unverifiable")
    assert files(f.disposition.planner.journal.root) == before


@pytest.mark.parametrize("kind", ["snapshot", "disposition", "extra", "duplicate"])
def test_prepare_is_closed_create_only_and_exact_snapshot_bound(f, kind):
    p = proposed(f)
    body = {"plan_id": "b" * 32, "copy_refs": request(f, f.operation, f.copy_review), "disposition": "retain_for_independent_assessment"}
    if kind == "snapshot":
        body["copy_refs"]["expected_snapshot_sha256"] = "f" * 64
    elif kind == "disposition":
        body["disposition"] = "resume"
    elif kind == "extra":
        body["path"] = "/invented"
    else:
        body["plan_id"] = p["plan_id"]
    before = roots(f), files(f.disposition.planner.journal.root)
    safe(call(f, "prepare", **body), "snapshot_or_publication_conflict" if kind in {"snapshot", "duplicate"} else "unverifiable")
    assert (roots(f), files(f.disposition.planner.journal.root)) == before


@pytest.mark.parametrize("change", ["source", "caller", "timeout", "exception"])
def test_late_inspection_change_withholds_every_decrypted_record(f, change):
    p = proposed(f)
    d = reviewed(f, p)
    original = type(f.disposition.source).capture
    n = 0
    async def capture(self, actor):
        nonlocal n
        n += 1
        if n == 3:
            if change == "source":
                e.retain(f.copy.readiness.candidate.root / ("e" * 32 + ".receipt"), receipts.MAGIC + os.urandom(48))
            elif change == "caller":
                f.revoke("preparer")
            elif change == "timeout":
                raise TimeoutError
            else:
                raise RuntimeError("invented private exception must not escape")
        return await original(self, actor)
    with patch.object(type(f.disposition.source), "capture", capture):
        value = inspected(f, p, d)
    safe(value, {"source": "snapshot_or_publication_conflict", "caller": "denied", "timeout": "budget_exhausted", "exception": "unavailable"}[change])
    assert "invented private" not in str(value)


@pytest.mark.parametrize("which", ["prepare", "decide"])
def test_lost_ack_retains_ciphertext_but_never_recovers_acknowledgement(f, which):
    p = proposed(f) if which == "decide" else None
    original = f.disposition.planner.write
    def write(*args):
        cipher = original(*args)
        f.revoke("reviewer" if which == "decide" else "preparer")
        return cipher
    before = roots(f)
    with patch.object(type(f.disposition.planner), "write", lambda self, *args: write(*args)):
        value = reviewed(f, p) if p else proposed(f)
    safe(value, "denied")
    assert len(files(f.disposition.planner.journal.root)) == (2 if p else 1) and roots(f) == before


def test_separate_journal_and_independent_binding_are_mandatory(f):
    p = f.disposition.planner
    altered = copy.copy(p)
    altered.journal = f.copy.controls.planner.journal
    with pytest.raises(ValueError):
        replace(f.disposition, reviews=replace(f.disposition.reviews, planner=altered))
    with pytest.raises(ValueError):
        replace(f.disposition, reviews=replace(f.disposition.reviews, binding=replace(f.disposition.reviews.binding, source_pins_sha256="f" * 64)))
    assert isinstance(f.disposition, DispositionPlanner)


def test_restore_disposition_preserves_all_origin_dependencies(f):
    c = materialize(f, f.copy, f.operation, f.copy_review)
    backup = f.copy
    old = roots(f)
    f.copy = make(f, "restore", source=backup.readiness.candidate,
                  origin=CopyOrigin(service=backup, **proof(f.operation, f.copy_review, c)))
    f.operation = prepare(f, f.copy, "9" * 32)
    f.copy_review = decide(f, f.copy, f.operation)
    complete = materialize(f, f.copy, f.operation, f.copy_review)
    f.disposition = make_disposition(f.copy, f.root / "restore-dispositions")
    before = roots(f)
    p = proposed(f, copy_refs=request(f, f.operation, f.copy_review, complete), disposition="retain_verified_history")
    d = reviewed(f, p)
    v = inspected(f, p, d)
    safe(v, "retained_disposition_review")
    assert v["plan"]["reconciliation"]["observation"]["origin"] is not None
    assert roots(f) == before
    assert all(files(Path(r)) == rows for r, rows in old.items())


@pytest.mark.parametrize("which", ["plan", "review"])
def test_tampered_ciphertext_never_returns_decrypted_history(f, which):
    p = proposed(f)
    d = reviewed(f, p)
    ident = p["plan_id"] if which == "plan" else f.disposition.decision_id(p, p["plan_ciphertext_sha256"])
    path = f.disposition.planner.journal.root / (ident + ".receipt")
    raw = path.read_bytes()
    path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    safe(inspected(f, p, d), "unverifiable")


def test_source_change_before_review_cannot_append_a_decision(f):
    p = proposed(f)
    e.retain(f.copy.readiness.candidate.root / ("e" * 32 + ".receipt"), receipts.MAGIC + os.urandom(48))
    before = roots(f), files(f.disposition.planner.journal.root)
    safe(reviewed(f, p), "snapshot_or_publication_conflict")
    assert (roots(f), files(f.disposition.planner.journal.root)) == before


def test_plan_expiring_during_read_is_explicitly_stale(f):
    p = proposed(f)
    d = reviewed(f, p)
    original = DispositionPlanner.plan
    count = 0
    def read(self, request):
        nonlocal count
        value = original(self, request)
        count += 1
        if count == 2:
            f.now += 301
        return value
    with patch.object(DispositionPlanner, "plan", read):
        safe(inspected(f, p, d), "retained_disposition_review_stale")
