"""Read-only, exact-reference reconciliation with real disposable authentication."""

import asyncio
import os
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import operator_enrollment_evidence as e  # noqa: E402
import private_inventory_receipts as receipts
from journal_backup_fixture import Fixture
from journal_copy_reconciliation import CopyReconciler
from journal_materialization import CopyOrigin
from journal_materialization_fixture import make
from test_journal_materialization import decide, files, materialize, prepare, proof, refs


@pytest.fixture
def f(tmp_path):
    value = Fixture(tmp_path)
    original = value.prepare()
    assert value.decide(original)["state"] == "reviewed_for_metadata_planning"
    value.copy = make(value)
    yield value
    value.store.engine.dispose()


def call(f, op="inventory", role="preparer", service=None, **body):
    return asyncio.run(CopyReconciler(service=service or f.copy).dispatch(f.scope(role), op, **body))


def request(f, p, d=None, c=None, service=None):
    v = call(f, service=service)
    assert v["state"] == "observed_copy_restart_metadata"
    return {**refs(p), "expected_snapshot_sha256": v["snapshot_sha256"],
            "decision_ciphertext_sha256": d and d["decision_ciphertext_sha256"],
            "intent_ciphertext_sha256": c and c["intent_ciphertext_sha256"],
            "completion_ciphertext_sha256": c and c["completion_ciphertext_sha256"]}


def roots(f):
    return {str(r): files(r) for r in (f.source, f.journal, f.copy.readiness.candidate.root,
        f.copy.controls.planner.journal.root, f.copy.readiness.reviews.planner.journal.root)}


def safe(value, state):
    assert value["state"] == state
    assert value["read_only"] and value["metadata_only"] and value["fresh_independent_review_required"]
    for k in ("automatic_resume", "acknowledgement_recovered", "production_execution_authorized", "trust_migrated",
              "authority_renewed", "record_adopted", "receipt_repair_authorized", "target_enrolled"):
        assert value[k] is False
    if state in {"denied", "unverifiable", "snapshot_or_publication_conflict", "budget_exhausted", "unavailable"}:
        assert value["history"] is value["observation"] is value["snapshot_sha256"] is None


def test_plan_and_independent_review_have_distinct_readonly_states(f):
    p = prepare(f, f.copy)
    before = roots(f)
    safe(call(f, "reconcile", **request(f, p)), "review_reference_not_supplied")
    assert roots(f) == before
    d = decide(f, f.copy, p)
    before = roots(f)
    v = call(f, "reconcile", **request(f, p, d))
    safe(v, "intent_not_observed")
    assert v["history"]["execution_review_current"] and roots(f) == before


@pytest.mark.parametrize("phase", ["intent_only", "partial", "exact_without_completion", "complete"])
def test_interrupted_and_complete_copies_are_never_conflated_or_resumed(f, phase):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    original = receipts._publish
    count = 0
    def publish(store, ident, raw):
        nonlocal count
        if store is f.copy.readiness.candidate:
            count += 1
            if phase == "intent_only" or phase == "partial" and count == 2:
                raise RuntimeError("invented interruption")
        if phase == "exact_without_completion" and store is f.copy.controls.planner.journal and count > 0:
            raise RuntimeError("invented pre-completion interruption")
        return original(store, ident, raw)
    with patch.object(receipts, "_publish", publish):
        c = materialize(f, f.copy, p, d)
    before = roots(f)
    body = request(f, p, d)
    safe(call(f, "reconcile", **body), "intent_reference_not_supplied")
    iid = f.copy.ident("intent", p["operation_id"], p["plan_ciphertext_sha256"])
    body["intent_ciphertext_sha256"] = e.sha((f.copy.controls.planner.journal.root / (iid + ".receipt")).read_bytes())
    v = call(f, "reconcile", **body)
    safe(v, "completion_reference_not_supplied" if phase == "complete" else "consumed_intent_without_completion")
    assert v["history"]["intent_authenticated"] and not v["history"]["completion_authenticated"]
    expected = {"intent_only": "empty_destination", "partial": "copy_mismatch", "exact_without_completion": "exact_ciphertext_copy", "complete": "exact_ciphertext_copy"}
    assert v["history"]["target_comparison"] == expected[phase]
    if phase == "complete":
        safe(call(f, "reconcile", **request(f, p, d, c)), "retained_completion_reconciled")
    assert roots(f) == before


@pytest.mark.parametrize("change", ["expiry", "reviewer", "source", "journal"])
def test_completion_survives_stale_execution_review_without_renewing_authority(f, change):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    c = materialize(f, f.copy, p, d)
    if change == "expiry":
        f.now += 301
    elif change == "reviewer":
        f.revoke("reviewer")
    else:
        r = f.source if change == "source" else f.journal
        e.retain(r / ("e" * 32 + ".receipt"), receipts.MAGIC + os.urandom(48))
    before = roots(f)
    v = call(f, "reconcile", **request(f, p, d, c))
    safe(v, "retained_completion_reconciled_review_stale")
    assert v["history"]["completion_authenticated"] and not v["history"]["execution_review_current"]
    assert roots(f) == before


@pytest.mark.parametrize("field", ["operation_id", "plan_ciphertext_sha256", "plan_sha256", "decision_ciphertext_sha256", "intent_ciphertext_sha256", "completion_ciphertext_sha256", "expected_snapshot_sha256"])
def test_wrong_exact_references_withhold_history(f, field):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    c = materialize(f, f.copy, p, d)
    body = request(f, p, d, c)
    body[field] = "f" * (32 if field == "operation_id" else 64)
    before = roots(f)
    v = call(f, "reconcile", **body)
    assert v["state"] in {"unverifiable", "snapshot_or_publication_conflict"}
    safe(v, v["state"])
    assert roots(f) == before


@pytest.mark.parametrize("kind", ["other", "revoked", "csrf", "origin", "duplicate_cookie", "get"])
def test_unauthorized_inventory_withholds_every_observation(f, kind):
    role = "other" if kind == "other" else "preparer"
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
    before = roots(f)
    safe(asyncio.run(CopyReconciler(service=f.copy).dispatch(scope, "inventory")), "denied")
    assert roots(f) == before


@pytest.mark.parametrize("operation,body", [("materialize", {}), ("prepare", {}), ("decide", {}), ("repair", {}),
    ("inventory", {"path": "/invented"}), ("reconcile", {}), ("inventory", {"resume": True})])
def test_closed_readonly_protocol_rejects_mutating_and_extra_fields(f, operation, body):
    before = roots(f)
    safe(call(f, operation, **body), "unverifiable")
    assert roots(f) == before


@pytest.mark.parametrize("change", ["candidate", "controls", "caller", "timeout", "exception"])
def test_late_changes_suppress_all_decrypted_metadata(f, change):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    body = request(f, p, d)
    original = CopyReconciler.capture
    calls = 0
    async def capture(self, actor):
        nonlocal calls
        calls += 1
        if calls == 2:
            if change in {"candidate", "controls"}:
                r = f.copy.readiness.candidate.root if change == "candidate" else f.copy.controls.planner.journal.root
                e.retain(r / ("e" * 32 + ".receipt"), receipts.MAGIC + os.urandom(48))
            elif change == "caller":
                f.revoke("preparer")
            elif change == "timeout":
                raise TimeoutError
            else:
                raise RuntimeError("must never disclose this marker")
        return await original(self, actor)
    with patch.object(CopyReconciler, "capture", capture):
        v = call(f, "reconcile", **body)
    state = {"candidate": "snapshot_or_publication_conflict", "controls": "snapshot_or_publication_conflict", "caller": "denied", "timeout": "budget_exhausted", "exception": "unavailable"}[change]
    safe(v, state)
    assert "must never disclose" not in str(v)


@pytest.mark.parametrize("kind", ["hardlink", "staging", "tamper"])
def test_conflicting_publication_is_not_promoted_to_authenticated_intent(f, kind):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    c = materialize(f, f.copy, p, d)
    r = f.copy.controls.planner.journal.root
    iid = f.copy.ident("intent", p["operation_id"], p["plan_ciphertext_sha256"])
    path = r / (iid + ".receipt")
    if kind == "tamper":
        raw = bytearray(path.read_bytes())
        raw[-1] ^= 1
        path.write_bytes(raw)
    else:
        os.link(path, r / ((".pending-" + "e" * 32) if kind == "staging" else "e" * 32 + ".receipt"))
    body = request(f, p, d, c)
    if kind == "tamper":
        body["intent_ciphertext_sha256"] = e.sha(path.read_bytes())
    before = roots(f)
    v = call(f, "reconcile", **body)
    assert v["state"] in {"unverifiable", "snapshot_or_publication_conflict"}
    safe(v, v["state"])
    assert roots(f) == before


def test_restore_reconciliation_keeps_original_backup_dependency_and_both_histories(f):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    c = materialize(f, f.copy, p, d)
    exact = proof(p, d, c)
    restored = make(f, "restore", source=f.copy.readiness.candidate, origin=CopyOrigin(service=f.copy, **exact))
    rp = prepare(f, restored, "9" * 32)
    rd = decide(f, restored, rp)
    rc = materialize(f, restored, rp, rd)
    body = request(f, rp, rd, rc, service=restored)
    before = roots(f)
    rbefore = files(restored.readiness.candidate.root), files(restored.controls.planner.journal.root)
    safe(call(f, "reconcile", service=replace(restored), **body), "retained_completion_reconciled")
    assert roots(f) == before and (files(restored.readiness.candidate.root), files(restored.controls.planner.journal.root)) == rbefore
    # Losing the original completion cannot silently renew the dependent restore.
    old_completion = f.copy.ident("completion", p["operation_id"], c["intent_ciphertext_sha256"])
    (f.copy.controls.planner.journal.root / (old_completion + ".receipt")).unlink()
    safe(call(f, "reconcile", service=restored, **body), "snapshot_or_publication_conflict")


def test_reviewer_revoked_during_final_observation_is_reported_stale(f):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    c = materialize(f, f.copy, p, d)
    body = request(f, p, d, c)
    original = CopyReconciler.capture
    calls = 0
    async def capture(self, actor):
        nonlocal calls
        calls += 1
        if calls == 2:
            f.revoke("reviewer")
        return await original(self, actor)
    with patch.object(CopyReconciler, "capture", capture):
        v = call(f, "reconcile", **body)
    safe(v, "retained_completion_reconciled_review_stale")
    assert not v["history"]["execution_review_current"]


def test_bounded_store_inventory_withholds_partial_results(f):
    r = f.copy.controls.planner.journal.root
    for i in range(33):
        e.retain(r / (f"{i:032x}" + ".receipt"), receipts.MAGIC + os.urandom(48))
    before = roots(f)
    safe(call(f), "budget_exhausted")
    assert roots(f) == before


def test_mismatched_independent_destination_key_is_rejected(f):
    before = roots(f)
    with pytest.raises(ValueError):
        replace(f.copy, readiness=replace(f.copy.readiness,
            candidate=replace(f.copy.readiness.candidate, key=os.urandom(32))))
    assert roots(f) == before
