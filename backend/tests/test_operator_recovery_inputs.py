"""Current actors, exact inputs, immutable encrypted decisions and bounded reads."""

import fcntl
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import operator_enrollment_evidence as e  # noqa: E402
from operator_recovery_inputs import DECISIONS, FLAGS, REFS, RecoveryInputReview  # noqa: E402
from recovery_input_fixture import ALTERNATE, SELECTION, make  # noqa: E402


@pytest.fixture
def f(tmp_path):
    fixture = make(tmp_path / "case")
    yield fixture
    fixture.account.store.engine.dispose()


def prepare(f, service=None):
    service = service or f.service()
    scope = f.account.scope()
    observation = service.dispatch(scope, "observe", selection_id=SELECTION)
    assert observation["state"] == "inputs_observed"
    value = service.dispatch(scope, "prepare", selection_id=SELECTION, review_id="1" * 32,
        expected_input_sha256=observation["input_sha256"])
    assert value["state"] == "pending_independent_review"
    return value, {k: value[k] for k in REFS}


def decide(f, prepared, refs, service=None, decision="accept"):
    value = (service or f.service()).dispatch(f.account.scope("reviewer"), "decide", **refs,
        expected_input_sha256=prepared["input_sha256"], decision=decision, reason_code=DECISIONS[decision])
    assert value["state"] == "independent_review_recorded"
    return {**refs, "decision_ciphertext_sha256": value["decision_ciphertext_sha256"]}


def journal(f):
    return {p.name: p.read_bytes() for p in f.sidecar.root.iterdir()}


def test_selected_input_review_survives_reopen_with_exact_history_and_original_expiry(f):
    before = f.protected()
    source_created = e.decode(e.read(f.selected.anchors_root / "handoff.json"))["created_at"]
    f.account.now += 100
    prepared, refs = prepare(f)
    assert prepared["expires_at"] == source_created + 300
    pending = f.service().dispatch(f.account.scope("reviewer"), "readiness", **refs, decision_ciphertext_sha256=None)
    assert pending["state"] == "decision_reference_required" and not pending["ready_for_disposable_input_handoff"]
    full = decide(f, prepared, refs)
    stored = journal(f)
    ready = f.service().dispatch(f.account.scope("reviewer"), "readiness", **full)
    assert ready["state"] == "reviewed_for_disposable_inputs" and ready["ready_for_disposable_input_handoff"]
    assert all(ready[k] is False for k in FLAGS)
    assert ready["review"]["expires_at"] == source_created + 300
    assert f.service().dispatch(f.account.scope(), "inspect", **full)["ready_for_disposable_input_handoff"] is False
    assert journal(f) == stored and f.protected() == before
    assert all(b"operator-recovery-input-review-v1" not in raw for raw in stored.values())


@pytest.mark.parametrize("fault", ["wrong_preparer", "unassigned_actor", "wrong_csrf", "missing_cookie"])
def test_denied_actors_cannot_inspect_inputs_or_write_reviews(f, fault):
    service = f.service()
    scope = f.account.scope("reviewer" if fault == "wrong_preparer" else "other" if fault == "unassigned_actor" else "preparer")
    if fault in {"wrong_csrf", "missing_cookie"}:
        scope["headers"] = [(k, b"bad" if k == b"x-csrf-token" else v) for k, v in scope["headers"] if fault != "missing_cookie" or k != b"cookie"]
    service.capture = lambda *args: pytest.fail("Denied actor reached private selection")
    before = f.protected()
    value = service.dispatch(scope, "prepare", selection_id=SELECTION, review_id="1" * 32, expected_input_sha256="0" * 64)
    assert value["state"] == "denied" and not journal(f) and before == f.protected()


@pytest.mark.parametrize("fault", ["selection", "review_cipher", "review_plain", "decision_cipher", "missing_decision"])
def test_exact_selection_and_all_review_references_are_required(f, fault):
    prepared, refs = prepare(f)
    full = decide(f, prepared, refs)
    changed = dict(full)
    if fault == "selection":
        changed["selection_id"] = ALTERNATE
    elif fault == "review_cipher":
        changed["review_ciphertext_sha256"] = "0" * 64
    elif fault == "review_plain":
        changed["review_sha256"] = "0" * 64
    elif fault == "decision_cipher":
        changed["decision_ciphertext_sha256"] = "0" * 64
    else:
        changed["decision_ciphertext_sha256"] = None
    before = journal(f), f.protected()
    value = f.service().dispatch(f.account.scope("reviewer"), "readiness", **changed)
    assert value["state"] in {"unverifiable", "decision_reference_required"}
    assert not value["ready_for_disposable_input_handoff"] and before == (journal(f), f.protected())


@pytest.mark.parametrize("decision", ["accept", "changes_required", "reject"])
def test_independent_outcomes_stay_explicit_and_never_enroll_trust(f, decision):
    prepared, refs = prepare(f)
    full = decide(f, prepared, refs, decision=decision)
    value = f.service().dispatch(f.account.scope("reviewer"), "readiness", **full)
    assert value["decision"]["decision"] == decision
    assert value["ready_for_disposable_input_handoff"] is (decision == "accept")
    assert all(value[k] is False for k in FLAGS)


@pytest.mark.parametrize("fault", ["expired", "maintenance", "package", "retained_key", "preparer_revoked", "reviewer_session_replaced", "reviewer_role_changed"])
def test_changed_inputs_or_actor_state_withhold_readiness_but_retain_review(f, fault):
    prepared, refs = prepare(f)
    full = decide(f, prepared, refs)
    records = journal(f)
    if fault == "expired":
        f.account.now += 301
    elif fault == "maintenance":
        e.retain(f.account.profile / ".runtime-key-rotation", b"invented maintenance")
    elif fault == "package":
        (f.selected.stage_root / "operator_inspection_preview.html").write_bytes(b"changed export")
    elif fault == "retained_key":
        (f.selected.anchors_root / "source.key").write_bytes(b"x" * 32)
    elif fault == "preparer_revoked":
        f.account.revoke("preparer")
    elif fault == "reviewer_session_replaced":
        from app.auth import create_session
        from app.db import User, digest
        f.account.revoke("reviewer")
        with f.account.store.session() as db:
            cookie, csrf = create_session(db, db.get(User, f.account.ids["reviewer"]), 1)
        f.account.cookies["reviewer"], f.account.csrf["reviewer"] = cookie, csrf
        f.account.sessions["reviewer"] = digest(cookie)
    else:
        from app.db import FirmRole
        with f.account.store.session() as db:
            role = db.get(FirmRole, e.sha(b"reviewer-role")[:32])
            role.revision += 1
            db.commit()
    before = f.protected()
    service = f.service()
    for operation in ("readiness", "inspect"):
        value = service.dispatch(f.account.scope("reviewer"), operation, **full)
        assert value["state"] == "review_retained_needs_revalidation"
        assert not value["ready_for_disposable_input_handoff"]
    assert records == journal(f) and f.protected() == before


def test_preparer_cannot_supply_own_independent_decision(f):
    prepared, refs = prepare(f)
    before = journal(f)
    value = f.service().dispatch(f.account.scope(), "decide", **refs, expected_input_sha256=prepared["input_sha256"],
        decision="accept", reason_code=DECISIONS["accept"])
    assert value["state"] == "denied" and before == journal(f)


def test_changed_inputs_after_prepare_cannot_be_silently_reselected(f):
    prepared, refs = prepare(f)
    before = journal(f)
    request = {**refs, "selection_id": ALTERNATE}
    value = f.service().dispatch(f.account.scope("reviewer"), "decide", **request,
        expected_input_sha256=prepared["input_sha256"], decision="accept", reason_code=DECISIONS["accept"])
    assert value["state"] == "unverifiable" and before == journal(f)


@pytest.mark.parametrize("stage", ["before_prepare_publish", "after_prepare_publish", "before_decision_publish", "after_decision_publish"])
def test_current_actor_is_rechecked_at_preparation_and_decision_publication(f, stage):
    def point(name):
        if name == stage:
            f.account.revoke("preparer" if "prepare" in stage else "reviewer")
    if "prepare" in stage:
        observed = f.service().dispatch(f.account.scope(), "observe", selection_id=SELECTION)
        value = f.service(point).dispatch(f.account.scope(), "prepare", selection_id=SELECTION,
            review_id="1" * 32, expected_input_sha256=observed["input_sha256"])
        expected_records = 1 if stage.startswith("after") else 0
    else:
        prepared, refs = prepare(f)
        value = f.service(point).dispatch(f.account.scope("reviewer"), "decide", **refs,
            expected_input_sha256=prepared["input_sha256"], decision="accept", reason_code=DECISIONS["accept"])
        expected_records = 2 if stage.startswith("after") else 1
    assert value["state"] == "denied" and len(journal(f)) == expected_records
    assert "review_ciphertext_sha256" not in value and "decision_ciphertext_sha256" not in value


def test_uncertain_published_decision_is_retained_without_recovered_acknowledgement(f):
    from private_inventory_receipts import RetentionUncertain
    prepared, refs = prepare(f)
    def point(name):
        if name == "after_decision_publish":
            raise RetentionUncertain
    value = f.service(point).dispatch(f.account.scope("reviewer"), "decide", **refs,
        expected_input_sha256=prepared["input_sha256"], decision="accept", reason_code=DECISIONS["accept"])
    assert value["state"] == "retention_uncertain" and "decision_ciphertext_sha256" not in value
    retained = journal(f)
    assert len(retained) == 2
    retry = f.service().dispatch(f.account.scope("reviewer"), "decide", **refs,
        expected_input_sha256=prepared["input_sha256"], decision="accept", reason_code=DECISIONS["accept"])
    assert retry["state"] == "input_or_review_conflict" and retained == journal(f)
    assert f.service().dispatch(f.account.scope("reviewer"), "readiness", **refs,
        decision_ciphertext_sha256=None)["state"] == "decision_reference_required"


def test_concurrent_instances_cannot_overwrite_an_independent_decision(f):
    prepared, refs = prepare(f)
    services = [f.service(), f.service()]
    def call(service):
        return service.dispatch(f.account.scope("reviewer"), "decide", **refs,
            expected_input_sha256=prepared["input_sha256"], decision="accept", reason_code=DECISIONS["accept"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(call, services))
    assert sorted(v["state"] for v in values) == ["independent_review_recorded", "input_or_review_conflict"]
    assert len(journal(f)) == 2


def test_unfinished_journal_names_remain_untouched_and_block_readiness(f):
    e.retain(f.sidecar.root / (".pending-" + "d" * 32), b"invented partial publication")
    before = journal(f), f.protected()
    value = f.service().dispatch(f.account.scope(), "observe", selection_id=SELECTION)
    assert value["state"] == "unverifiable" and before == (journal(f), f.protected())


def test_bounded_review_capacity_reserves_room_for_independent_decision(f):
    for i in range(63):
        e.retain(f.sidecar.root / (f"{i:032x}" + ".receipt"), b"invented retained record")
    before = journal(f)
    value = f.service().dispatch(f.account.scope(), "prepare", selection_id=SELECTION,
        review_id="f" * 32, expected_input_sha256="0" * 64)
    assert value["state"] == "input_or_review_conflict" and before == journal(f)


def test_directory_lock_contention_is_bounded_and_preserves_inputs(f):
    service = f.service()
    fd = os.open(f.sidecar.root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        value = service.dispatch(f.account.scope(), "observe", selection_id=SELECTION)
        assert value["state"] == "budget_exhausted" and not journal(f)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


@pytest.mark.parametrize("fault", ["profile", "principal", "database"])
def test_host_cannot_mix_review_authority_with_another_selected_identity(f, fault):
    service = f.service()
    changes = {"profile_id": "0" * 32} if fault == "profile" else {"reviewer_id": "0" * 32} if fault == "principal" else {"database_identity": (0, 0)}
    selected = replace(f.selected, pins=replace(f.selected.pins, **changes))
    with pytest.raises(ValueError):
        RecoveryInputReview(service.planner, service.journal_pins, {SELECTION: selected})


def test_public_input_readonly_policy_cannot_be_relaxed_by_a_request(f):
    service = f.service()
    strict = replace(f.selected, require_readonly=True)
    checked = RecoveryInputReview(service.planner, service.journal_pins, {SELECTION: strict})
    assert checked.dispatch(f.account.scope(), "observe", selection_id=SELECTION)["state"] == "unverifiable"
    assert checked.dispatch(f.account.scope(), "observe", selection_id=SELECTION,
        require_readonly=False)["state"] == "unverifiable"
    assert not journal(f)


def test_review_key_must_be_separate_from_every_retained_source_key(f):
    from journal_backup_fixture import pins
    from private_inventory_receipts import ReceiptStore
    from receipt_recovery_planning import RecoveryPlanner
    wrong = ReceiptStore(root=f.sidecar.root, context_id=f.sidecar.context_id, scope_sha256=f.sidecar.scope_sha256,
                         key=e.read(f.selected.anchors_root / "controls.key"))
    original = f.account.planner
    p = RecoveryPlanner(original.source, wrong, original.pins, f.account.authority,
        preparer_id=original.preparer, reviewer_id=original.reviewer, clock=original.clock)
    service = RecoveryInputReview(p, pins(f.account, wrong), {SELECTION: f.selected})
    before = f.protected()
    assert service.dispatch(f.account.scope(), "observe", selection_id=SELECTION)["state"] == "unverifiable"
    assert not journal(f) and before == f.protected()


def test_ciphertext_tampering_is_not_repaired_even_with_a_new_transport_hash(f):
    prepared, refs = prepare(f)
    full = decide(f, prepared, refs)
    path = f.sidecar.root / (refs["review_id"] + ".receipt")
    raw = path.read_bytes()
    path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    altered = {**full, "review_ciphertext_sha256": e.sha(path.read_bytes())}
    before = journal(f), f.protected()
    value = f.service().dispatch(f.account.scope("reviewer"), "readiness", **altered)
    assert value["state"] == "unverifiable" and value["review"] is None
    assert before == (journal(f), f.protected())


def test_pending_reference_response_rechecks_actor_after_reading_encrypted_review(f):
    _, refs = prepare(f)
    service = f.service()
    original = service.planner.read
    def read(*args):
        value = original(*args)
        f.account.revoke("reviewer")
        return value
    service.planner.read = read
    before = journal(f), f.protected()
    value = service.dispatch(f.account.scope("reviewer"), "readiness", **refs, decision_ciphertext_sha256=None)
    assert value["state"] == "denied" and value["review"] is None
    assert before == (journal(f), f.protected())


def test_selected_review_versions_are_reread_before_releasing_readiness(f):
    prepared, refs = prepare(f)
    full = decide(f, prepared, refs)
    path = f.sidecar.root / (refs["review_id"] + ".receipt")
    def checkpoint(name):
        if name == "before_read_release":
            raw = path.read_bytes()
            path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    before = f.protected()
    value = f.service(checkpoint).dispatch(f.account.scope("reviewer"), "readiness", **full)
    assert value["state"] == "unverifiable" and value["review"] is None
    assert not value["ready_for_disposable_input_handoff"] and f.protected() == before


def test_checked_fixture_report_binds_all_outcomes_sources_and_original_native_evidence():
    from qualify_recovery_inputs import CASES, plan_sha256
    value = json.loads((ROOT / "docs/evidence/reviewed-recovery-inputs-2026-11-04.json").read_bytes())
    assert value["schema"] == "reviewed-recovery-input-qualification-v1" and value["status"] == "qualified"
    assert value["case_plan_sha256"] == plan_sha256()
    evidence = value["evidence"]
    assert evidence["cases"] == [{"id": name, "state": "verified"} for name in CASES]
    assert evidence["fixture_contexts"] == 3 and evidence["encrypted_review_records"] == 6
    assert evidence["real_session_auth_exercised"] and evidence["original_inputs_and_accounts_exact"]
    assert evidence["original_expiry_preserved"] and not evidence["listener_started"]
    assert evidence["native_mount_qualification"] is False and value["production_activation"] is False
    assert all(evidence[name] is False for name in FLAGS)
    assert len(value["source_sha256"]) == 757
    for name, expected in value["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert hashlib.sha256((ROOT / "docs/evidence/native-cold-controller-2026-11-04.json").read_bytes()).hexdigest() == value["prior_native_report_sha256"]
