"""Fresh real authorization and unchanged encrypted files across reconciliation."""

import asyncio
import copy
import hashlib
import json
import os
import sys
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import operator_enrollment_evidence as e  # noqa: E402
import private_inventory_receipts as receipts  # noqa: E402
from planning_journal_reconciliation import JournalBinding, JournalReconciler  # noqa: E402
from receipt_provisioning_readiness import Pins, fingerprint  # noqa: E402
from receipt_recovery_planning import RecoveryPlanner  # noqa: E402
from test_receipt_recovery_planning import Fixture  # noqa: E402


def binding(f):
    return JournalBinding(pins=Pins(context_id=f.pins.context_id, scope_sha256=f.pins.scope_sha256,
        key_fingerprint=fingerprint(f.journal_store.key), store_identity=f.journal_store.identity,
        profile_id=f.pins.profile_id, profile_sha256=f.pins.profile_sha256),
        source_pins_sha256=e.sha(e.encode(asdict(f.pins))), preparer_id=f.ids["preparer"], reviewer_id=f.ids["reviewer"])


@pytest.fixture
def f(tmp_path):
    value = Fixture(tmp_path)
    value.reconciler = JournalReconciler(planner=value.planner, binding=binding(value))
    yield value
    value.store.engine.dispose()


def call(f, operation="inventory", role="preparer", **body):
    return asyncio.run(f.reconciler.dispatch(f.scope(role), operation, **body))


def request(f, plan=None, ident="2" * 32):
    observed = call(f)
    assert observed["state"] == "observed_journal_metadata"
    return {"plan_id": plan["plan_id"] if plan else ident, "plan_ciphertext_sha256": plan and plan["plan_ciphertext_sha256"],
            "plan_sha256": plan and plan["plan_sha256"], "expected_journal_snapshot_sha256": observed["journal_snapshot_sha256"],
            "expected_source_snapshot_sha256": observed["source_snapshot_sha256"]}


def closed(value, state):
    assert value["state"] == state and value["read_only"] and value["fresh_independent_review_required"]
    for key in ("acknowledgement_recovered", "record_adopted", "automatic_recovery", "receipt_repair_authorized", "authority_renewed", "native_execution_authorized"):
        assert value[key] is False


def test_restart_with_independent_pins_preserves_exact_metadata_and_journal_ciphertext(f):
    plan = f.prepare()
    review = f.decide(plan)
    before, journal = f.files(), f.files(f.journal)
    f.reconciler = JournalReconciler(planner=RecoveryPlanner(f.source_store, f.journal_store, f.pins, f.authority,
        preparer_id=f.ids["preparer"], reviewer_id=f.ids["reviewer"], clock=lambda: f.now), binding=binding(f))
    value = call(f, "reconcile", **request(f, plan))
    closed(value, "retained_decision_observed")
    assert value["decision_ciphertext_sha256"] == review["decision_ciphertext_sha256"]
    assert value["decision_digest_basis"] == "observed_in_exact_journal_snapshot" and value["journal_record_authenticated"]
    assert f.files() == before and f.files(f.journal) == journal


@pytest.mark.parametrize("kind", ["absent", "unclaimed", "linked", "unknown_refs", "decision_absent", "decision_linked"])
def test_interrupted_and_unacknowledged_entries_are_preserved_without_adoption(f, kind):
    plan = None
    if kind in {"linked", "unknown_refs", "decision_absent", "decision_linked"}:
        plan = f.prepare()
    if kind == "unclaimed":
        e.retain(f.journal / (".pending-" + "3" * 32), receipts.MAGIC + os.urandom(48))
    if kind == "linked":
        os.link(f.journal / (plan["plan_id"] + ".receipt"), f.journal / (".pending-" + "3" * 32))
    if kind == "decision_linked":
        f.decide(plan)
        ident = f.planner.decision_id(plan["plan_id"], plan["plan_ciphertext_sha256"])
        os.link(f.journal / (ident + ".receipt"), f.journal / (".pending-" + "3" * 32))
    body = request(f, None if kind == "unknown_refs" else plan)
    before, journal = f.files(), f.files(f.journal)
    expected = {"absent": "plan_not_observed", "unclaimed": "plan_not_observed", "linked": "plan_publication_unverifiable",
                "unknown_refs": "plan_references_unavailable", "decision_absent": "decision_not_observed", "decision_linked": "decision_publication_unverifiable"}
    value = call(f, "reconcile", **body)
    closed(value, expected[kind])
    if kind not in {"decision_absent"}:
        assert value["plan"] is None and value["review"] is None and not value["journal_record_authenticated"]
    assert f.files() == before and f.files(f.journal) == journal


@pytest.mark.parametrize("change", ["journal", "source", "plan_hash", "plan_cipher", "half_refs", "extra", "future_references"])
def test_exact_prior_references_and_both_snapshots_are_required(f, change):
    plan = f.prepare()
    f.decide(plan)
    body = request(f, plan)
    if change in {"journal", "source"}:
        e.retain((f.journal if change == "journal" else f.source) / (".pending-" + "3" * 32), b"unfinished")
    elif change in {"plan_hash", "plan_cipher"}:
        body["plan_sha256" if change == "plan_hash" else "plan_ciphertext_sha256"] = "e" * 64
    elif change == "half_refs":
        body["plan_sha256"] = None
    elif change == "extra":
        body["repair_authorized"] = True
    else:
        body["expected_journal_snapshot_sha256"] = "e" * 64
    before, journal = f.files(), f.files(f.journal)
    value = call(f, "reconcile", **body)
    closed(value, "snapshot_conflict" if change in {"journal", "source", "future_references"} else "version_conflict" if change == "plan_cipher" else "unverifiable")
    assert value["plan"] is None and value["review"] is None
    assert f.files() == before and f.files(f.journal) == journal


@pytest.mark.parametrize("change", ["expired", "source_changed", "reviewer_revoked", "preparer_revoked"])
def test_stale_history_is_visible_only_to_a_current_authorized_caller(f, change):
    plan = f.prepare()
    f.decide(plan)
    if change == "expired":
        f.now += 301
    elif change == "source_changed":
        f.add(".pending-" + "3" * 32)
    else:
        f.revoke(change.split("_")[0])
    role = "reviewer" if change == "preparer_revoked" else "preparer"
    before, journal = f.files(), f.files(f.journal)
    # Inventory requires that same current caller, not a revoked preparer.
    observed = call(f, role=role)
    refs = {**f.refs(plan), "expected_journal_snapshot_sha256": observed["journal_snapshot_sha256"],
            "expected_source_snapshot_sha256": observed["source_snapshot_sha256"]}
    value = call(f, "reconcile", role, **refs)
    closed(value, "stale_decision_preserved")
    assert value["review"] and value["historical_review_state"] == "stale_review_retained"
    assert f.files() == before and f.files(f.journal) == journal


@pytest.mark.parametrize("role", ["other", "reviewer", "preparer"])
def test_unassigned_or_revoked_callers_receive_no_partial_inventory_or_history(f, role):
    plan = f.prepare()
    f.decide(plan)
    body = request(f, plan)
    if role != "other":
        f.revoke(role)
    value = call(f, "reconcile", role, **body)
    closed(value, "denied")
    assert value["journal"] is None and value["plan"] is None and value["review"] is None


@pytest.mark.parametrize("change", ["key", "root", "scope", "profile", "source", "assignee"])
def test_restart_cannot_self_provision_or_change_independent_binding(f, change):
    b = binding(f)
    field = {"key": "key_fingerprint", "root": "store_identity", "scope": "scope_sha256", "profile": "profile_sha256"}.get(change)
    if field:
        b = replace(b, pins=replace(b.pins, **{field: (0, 0) if change == "root" else "e" * 64}))
    elif change == "source":
        b = replace(b, source_pins_sha256="e" * 64)
    else:
        b = replace(b, reviewer_id=f.ids["other"])
    with pytest.raises(ValueError):
        JournalReconciler(planner=f.planner, binding=b)


def test_changes_or_revocation_after_history_read_withhold_cached_body(f):
    plan = f.prepare()
    f.decide(plan)
    body = request(f, plan)
    original = JournalReconciler.capture
    calls = 0
    async def revoked(self, actor):
        nonlocal calls
        calls += 1
        value = await original(self, actor)
        if calls == 2:
            f.revoke("preparer")
        return value
    with patch.object(JournalReconciler, "capture", revoked):
        value = call(f, "reconcile", **body)
    closed(value, "denied")
    assert value["journal"] is None and value["plan"] is None and value["review"] is None


@pytest.mark.parametrize("change", ["expiry", "reviewer_revoked"])
def test_expiry_during_final_observation_keeps_history_stale_and_source_read_only(f, change):
    plan = f.prepare()
    f.decide(plan)
    body = request(f, plan)
    before, journal = f.files(), f.files(f.journal)
    original = JournalReconciler.capture
    calls = 0
    async def expired(self, actor):
        nonlocal calls
        calls += 1
        value = await original(self, actor)
        if calls == 2:
            if change == "expiry":
                f.now += 301
            else:
                f.revoke("reviewer")
        return value
    with patch.object(JournalReconciler, "capture", expired):
        value = call(f, "reconcile", **body)
    closed(value, "stale_decision_preserved")
    assert f.files() == before and f.files(f.journal) == journal


@pytest.mark.parametrize("target", ["journal", "source"])
def test_change_after_decryption_withholds_both_inventory_and_history(f, target):
    plan = f.prepare()
    f.decide(plan)
    body = request(f, plan)
    original = JournalReconciler.capture
    calls = 0
    async def changed(self, actor):
        nonlocal calls
        calls += 1
        if calls == 2:
            e.retain((f.journal if target == "journal" else f.source) / (".pending-" + "3" * 32), b"unfinished")
        return await original(self, actor)
    with patch.object(JournalReconciler, "capture", changed):
        value = call(f, "reconcile", **body)
    closed(value, "snapshot_conflict")
    assert value["journal"] is None and value["plan"] is None and value["review"] is None


@pytest.mark.parametrize("change", ["ciphertext", "wrong_reviewer", "replay"])
def test_observed_ciphertext_is_not_enough_to_accept_a_decision(f, change):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    plan = f.prepare()
    review = f.decide(plan)
    ident = f.planner.decision_id(plan["plan_id"], plan["plan_ciphertext_sha256"])
    path = f.journal / (ident + ".receipt")
    raw = path.read_bytes()
    if change == "ciphertext":
        path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    elif change == "wrong_reviewer":
        value = f.planner.read("decision", ident, review["decision_ciphertext_sha256"])
        value["reviewed_by"]["user_id"] = f.ids["preparer"]
        nonce = os.urandom(12)
        path.write_bytes(receipts.MAGIC + nonce + AESGCM(f.journal_store.key).encrypt(nonce, e.encode(value), f.planner.aad("decision", ident)))
    else:
        plan = f.prepare("6" * 32)
        copied_id = f.planner.decision_id(plan["plan_id"], plan["plan_ciphertext_sha256"])
        e.retain(f.journal / (copied_id + ".receipt"), raw)
    before, journal = f.files(), f.files(f.journal)
    value = call(f, "reconcile", **request(f, plan))
    closed(value, "unverifiable")
    assert value["journal"] is None and value["plan"] is None and value["review"] is None
    assert f.files() == before and f.files(f.journal) == journal


def native_report():
    return json.loads((ROOT / "docs/evidence/native-planning-journal-restart-2026-10-29.json").read_text())


def test_native_report_binds_actual_restarts_source_files_and_preserved_histories():
    from planning_journal_report import validate
    value = native_report()
    native = value["native"]
    assert value["status"] == "qualified" and value["disposable_volumes_removed"] is True
    assert validate(native, native["receipt_manifest_sha256"], native["controller_manifest_sha256"]) == {
        "qualified_modes": 2, "frozen_outcomes": 44, "intentional_SIGKILL_exits": 12, "production_activation": False}
    for name, expected in value["source_sha256"].items():
        assert name.startswith(("scripts/", "backend/app/", "deploy/fixtures/"))
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(p["no_network"] and p["no_host_ports"] and p["no_host_mounts"] and p["root_filesystem_readonly"]
        and p["four_distinct_named_volumes"] and p["two_CPUs"] and p["memory_bytes"] == 1073741824
        and p["pids_limit"] == 64 for p in value["posture"])
    assert value["posture"][1]["nonroot_runtime"] and value["posture"][1]["stage_volume_readonly"]


@pytest.mark.parametrize("change", ["missing_case", "wrong_state", "missing_kill", "process_reuse", "fabricated_ack",
    "repair", "adoption", "renewal", "source_change", "scope", "case_input", "real_inference", "power_loss"])
def test_frozen_report_rejects_missing_native_proof_or_scope_inflation(change):
    from planning_journal_report import validate
    value = copy.deepcopy(native_report()["native"])
    mode = value["modes"][0]
    if change == "missing_case":
        mode["cases"].pop()
    elif change == "wrong_state":
        mode["cases"][3]["state"] = "retained_decision_observed"
    elif change in {"missing_kill", "process_reuse", "fabricated_ack"}:
        mode[{"missing_kill": "intentional_SIGKILL_exits", "process_reuse": "journal_processes", "fabricated_ack": "acknowledged_responses"}[change]] += 1
    elif change in {"repair", "adoption", "renewal", "source_change"}:
        mode[{"repair": "automatic_repair", "adoption": "record_adoption", "renewal": "authority_renewal", "source_change": "source_ciphertext_exact"}[change]] = change != "source_change"
    elif change == "scope":
        value["receipt_manifest_sha256"] = "e" * 64
    elif change == "case_input":
        value["private_case_inputs"] = True
    elif change == "real_inference":
        value["native_inference_calls"] = 1
    else:
        value["power_loss_qualified"] = True
    pins = native_report()["native"]
    with pytest.raises(ValueError):
        validate(value, pins["receipt_manifest_sha256"], pins["controller_manifest_sha256"])
