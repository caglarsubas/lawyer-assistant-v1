"""Disposable exact-version restart reads, never recovery execution or adoption."""

import asyncio
import copy
import hashlib
import json
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
from copy_recovery_disposition import FLAGS, REFS  # noqa: E402
from disposition_journal_reconciliation import DispositionReconciler  # noqa: E402
from test_copy_recovery_disposition import f as f  # noqa: E402
from test_copy_recovery_disposition import inspected, proposed, reviewed  # noqa: E402
from test_journal_copy_reconciliation import roots  # noqa: E402
from test_journal_materialization import files  # noqa: E402


def call(f, operation="inventory", role="preparer", **body):
    return asyncio.run(DispositionReconciler(disposition=f.disposition).dispatch(f.scope(role), operation, **body))


def body(f, plan=None, decision=None):
    observed = call(f)
    assert observed["state"] == "observed_disposition_journal_metadata"
    return {"plan_id": "a" * 32, "plan_ciphertext_sha256": None, "plan_sha256": None,
            **({k: plan[k] for k in REFS} if plan else {}),
            "decision_ciphertext_sha256": decision and decision["decision_ciphertext_sha256"],
            "expected_snapshot_sha256": observed["snapshot_sha256"]}


def protected(f):
    return roots(f), files(f.disposition.planner.journal.root)


def safe(v, state):
    assert v["state"] == state and v["read_only"] and v["source_read_only"]
    assert v["planning_only"] and v["metadata_only"] and v["fresh_independent_review_required"]
    assert not v["atomic_snapshot"] and not v["current_authority_assessed"]
    assert not v["production_execution_authorized"] and not v["automatic_resume"]
    assert all(v[k] is False for k in FLAGS)
    if state in {"denied", "unverifiable", "snapshot_or_publication_conflict", "budget_exhausted", "unavailable"}:
        assert v["plan"] is v["review"] is v["observation"] is v["snapshot_sha256"] is None


def test_empty_and_pending_plans_have_distinct_exact_readonly_states(f):
    request = body(f)
    before = protected(f)
    safe(call(f, "reconcile", **request), "plan_not_observed")
    assert protected(f) == before
    p = proposed(f)
    missing = body(f)
    exact = body(f, p)
    before = protected(f)
    v = call(f, "reconcile", **missing)
    safe(v, "plan_references_unavailable")
    assert v["plan"] is v["review"] is None
    v = call(f, "reconcile", **exact)
    safe(v, "decision_not_observed")
    assert v["plan"]["plan_id"] == p["plan_id"] and v["review"] is None
    assert protected(f) == before


@pytest.mark.parametrize("decision", ["accept", "changes_required", "reject"])
def test_independent_decisions_retain_their_exact_versions_without_new_authority(f, decision):
    p = proposed(f)
    d = reviewed(f, p, decision)
    exact = body(f, p, d)
    before = protected(f)
    v = call(f, "reconcile", **exact)
    safe(v, "retained_disposition_reconciled")
    assert v["review"]["decision"] == decision and v["planning_review_current"]
    assert v["decision_reference_basis"] == "caller_supplied"
    assert v["plan"] == inspected(f, p, d)["plan"]
    assert protected(f) == before


@pytest.mark.parametrize("record", ["plan", "review"])
def test_lost_publication_response_cannot_supply_an_acknowledgement(f, record):
    p = proposed(f) if record == "review" else None
    original = receipts._publish
    def lost(store, ident, raw):
        value = original(store, ident, raw)
        if store is f.disposition.planner.journal:
            raise OSError("SYNTHETIC lost response; never publish this message")
        return value
    with patch.object(receipts, "_publish", lost):
        outcome = proposed(f) if record == "plan" else reviewed(f, p)
    assert outcome["state"] == "unavailable"
    request = body(f, p)
    before = protected(f)
    v = call(f, "reconcile", **request)
    safe(v, "plan_references_unavailable" if record == "plan" else "decision_reference_not_supplied")
    assert v["review"] is None and not v["acknowledgement_recovered"]
    if record == "plan":
        assert v["plan"] is None
    else:
        assert v["decision_publication_observed"]
    assert protected(f) == before


@pytest.mark.parametrize("field", ["plan_id", "plan_ciphertext_sha256", "plan_sha256", "decision_ciphertext_sha256", "expected_snapshot_sha256"])
def test_wrong_exact_reference_withholds_every_decrypted_record(f, field):
    p = proposed(f)
    d = reviewed(f, p)
    request = body(f, p, d)
    request[field] = "f" * (32 if field == "plan_id" else 64)
    before = protected(f)
    v = call(f, "reconcile", **request)
    safe(v, "unverifiable" if field == "plan_sha256" else "snapshot_or_publication_conflict")
    assert protected(f) == before


@pytest.mark.parametrize("change", ["window", "reviewer", "source"])
def test_fresh_authorized_reader_can_see_stale_history_without_renewal(f, change):
    p = proposed(f)
    d = reviewed(f, p)
    if change == "window":
        f.now += 301
    elif change == "reviewer":
        f.revoke("reviewer")
    else:
        e.retain(f.copy.readiness.candidate.root / ("e" * 32 + ".receipt"), receipts.MAGIC + os.urandom(48))
    request = body(f, p, d)
    before = protected(f)
    v = call(f, "reconcile", **request)
    safe(v, "retained_disposition_reconciled_stale")
    assert v["review"]["decision"] == "accept" and not v["planning_review_current"]
    assert protected(f) == before


@pytest.mark.parametrize("kind", ["other", "revoked", "csrf", "origin", "cookie", "method"])
def test_current_authentication_is_required_for_every_inventory_and_read(f, kind):
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
    for operation, payload in (("inventory", {}), ("reconcile", request)):
        safe(asyncio.run(DispositionReconciler(disposition=f.disposition).dispatch(scope, operation, **payload)), "denied")
    assert protected(f) == before


@pytest.mark.parametrize("operation", ["prepare", "decide", "resume", "repair", "adopt"])
def test_no_mutation_or_execution_operation_exists(f, operation):
    before = protected(f)
    safe(call(f, operation), "unverifiable")
    assert protected(f) == before


@pytest.mark.parametrize("kind", ["extra", "missing", "unpaired", "decision_without_plan"])
def test_closed_fields_do_not_allow_inferred_plan_or_path_selection(f, kind):
    request = body(f)
    if kind == "extra":
        request["root"] = "/invented-private-location"
    elif kind == "missing":
        request.pop("decision_ciphertext_sha256")
    elif kind == "unpaired":
        request["plan_sha256"] = "f" * 64
    else:
        request["decision_ciphertext_sha256"] = "f" * 64
    before = protected(f)
    safe(call(f, "reconcile", **request), "unverifiable")
    assert protected(f) == before
    safe(call(f, "inventory", root="/invented"), "unverifiable")


@pytest.mark.parametrize("kind", ["staging", "multiple_links", "symlink", "ciphertext"])
def test_partial_or_unverifiable_publication_is_never_authenticated(f, kind):
    p = proposed(f)
    request = body(f, p)
    root = f.disposition.planner.journal.root
    path = root / (p["plan_id"] + ".receipt")
    if kind == "staging":
        path.rename(root / (".pending-" + "b" * 32))
        request.update(plan_ciphertext_sha256=None, plan_sha256=None)
    elif kind == "multiple_links":
        os.link(path, root / ("b" * 32 + ".receipt"))
    elif kind == "symlink":
        (root / ("b" * 32 + ".receipt")).symlink_to(path)
    else:
        raw = path.read_bytes()
        path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    if kind in {"staging", "multiple_links", "ciphertext"}:
        # Re-observe physical state, without manufacturing a content reference.
        request["expected_snapshot_sha256"] = call(f)["snapshot_sha256"]
    before = protected(f)
    safe(call(f, "reconcile", **request), {"staging": "plan_not_observed", "multiple_links": "unverifiable",
         "symlink": "unverifiable", "ciphertext": "snapshot_or_publication_conflict"}[kind])
    assert protected(f) == before


@pytest.mark.parametrize("change", ["source", "caller", "plan", "timeout", "exception", "reviewer", "window"])
def test_last_observation_rechecks_versions_authorization_and_staleness(f, change):
    p = proposed(f)
    d = reviewed(f, p)
    request = body(f, p, d)
    original = DispositionReconciler.capture
    count = 0
    async def capture(self, actor):
        nonlocal count
        count += 1
        if count == 2:
            if change == "source":
                e.retain(f.copy.readiness.candidate.root / ("f" * 32 + ".receipt"), receipts.MAGIC + os.urandom(48))
            elif change in {"caller", "reviewer"}:
                f.revoke("preparer" if change == "caller" else "reviewer")
            elif change == "plan":
                path = f.disposition.planner.journal.root / (p["plan_id"] + ".receipt")
                raw = path.read_bytes()
                path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
            elif change == "window":
                f.now += 301
            elif change == "timeout":
                raise TimeoutError
            else:
                raise RuntimeError("SYNTHETIC secret exception must not escape")
        return await original(self, actor)
    before = protected(f)
    with patch.object(DispositionReconciler, "capture", capture):
        v = call(f, "reconcile", **request)
    state = {"source": "snapshot_or_publication_conflict", "caller": "denied", "plan": "snapshot_or_publication_conflict",
             "timeout": "budget_exhausted", "exception": "unavailable", "reviewer": "retained_disposition_reconciled_stale",
             "window": "retained_disposition_reconciled_stale"}[change]
    safe(v, state)
    assert "SYNTHETIC secret exception" not in str(v)
    if change not in {"source", "plan"}:
        assert protected(f) == before


def test_independent_journal_key_and_physical_budget_cannot_be_bypassed(f):
    from receipt_provisioning_readiness import fingerprint

    d = f.disposition
    mismatched = replace(d.reviews.binding.pins, key_fingerprint=fingerprint(b"x" * 32))
    with pytest.raises(ValueError):
        replace(d.reviews, binding=replace(d.reviews.binding, pins=mismatched))
    for n in range(33):
        e.retain(d.planner.journal.root / (f"{n:032x}" + ".receipt"), receipts.MAGIC + os.urandom(48))
    before = protected(f)
    safe(call(f), "budget_exhausted")
    assert protected(f) == before


def native_report():
    return json.loads((ROOT / "docs/evidence/native-disposition-journal-restart-2026-11-02.json").read_text())


def test_retained_native_evidence_binds_every_public_source_and_actual_interruption():
    from disposition_journal_report import validate

    report = native_report()
    assert report["status"] == "qualified" and report["disposable_volumes_removed"]
    for name, digest in report["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    v = report["native"]
    assert validate(v, v["receipt_manifest_sha256"], v["controller_manifest_sha256"]) == {
        "qualified_protocols": 5, "frozen_outcomes": 52, "intentional_SIGKILL_exits": 4, "production_activation": False}
    assert sum(x["clean_exits"] for x in v["protocols"]) == 48
    assert sum(x["retained_staging"] for x in v["protocols"]) == 2


@pytest.mark.parametrize("kind", ["case", "count", "missing", "private", "inference", "activation", "controller", "power_loss"])
def test_closed_native_report_rejects_changed_evidence_or_scope_inflation(kind):
    from disposition_journal_report import validate

    original = native_report()["native"]
    v = copy.deepcopy(original)
    if kind == "case":
        v["protocols"][0]["cases"][3]["state"] = "acknowledgement_recovered"
    elif kind == "count":
        v["protocols"][0]["intentional_SIGKILL_exits"] = 0
    elif kind == "missing":
        v["protocols"].pop()
    elif kind == "controller":
        v["protocols"][0]["controller_reads"] = True
    else:
        field, value = {"private": ("private_case_inputs", True), "inference": ("native_inference_calls", 1),
            "activation": ("production_activation", True), "power_loss": ("power_loss_qualified", True)}[kind]
        v[field] = value
    with pytest.raises(ValueError):
        validate(v, original["receipt_manifest_sha256"], original["controller_manifest_sha256"])
