"""Synthetic independently reviewed journal-copy readiness, never live restore."""

import asyncio
import copy
import os
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(Path(__file__).resolve().parent)]
import operator_enrollment_evidence as e  # noqa: E402
import private_inventory_receipts as receipts  # noqa: E402
from journal_backup_fixture import Fixture, service  # noqa: E402
from journal_backup_readiness import DECISIONS, FLAGS, JournalBackupReadiness  # noqa: E402


def call(f, action, role="preparer", **body):
    return asyncio.run(f.readiness.dispatch(f.scope(role), action, **body))


def prepare(f, ident="8" * 32):
    observation = call(f, "observe")
    assert observation["state"] == "observed_copy_metadata"
    return call(f, "prepare", plan_id=ident, expected_snapshot_sha256=observation["snapshot_sha256"])


def decide(f, plan, decision="accept", role="reviewer"):
    return call(f, "decide", role, **f.refs(plan), decision=decision, reason_code=DECISIONS[decision][0])


def inspect(f, plan, review=None, role="preparer"):
    return call(f, "inspect", role, **f.refs(plan), decision_ciphertext_sha256=review and review["decision_ciphertext_sha256"])


def copy_fixture(f):
    for p in f.journal.iterdir():
        e.retain(f.readiness.candidate.root / p.name, p.read_bytes())


@pytest.fixture
def f(tmp_path):
    f = Fixture(tmp_path)
    plan = f.prepare()
    assert f.decide(plan)["state"] == "reviewed_for_metadata_planning"
    f.readiness = service(f)
    yield f
    f.store.engine.dispose()


@pytest.mark.parametrize("copied", [False, True])
def test_independent_exact_review_is_metadata_only_and_all_histories_are_untouched(f, copied):
    if copied:
        copy_fixture(f)
    roots = (f.source, f.journal, f.readiness.candidate.root)
    before = [f.files(r) for r in roots]
    observed = call(f, "observe")
    assert observed["observation"]["comparison"] == ("exact_ciphertext_copy" if copied else "empty_destination")
    plan = prepare(f)
    assert plan["state"] == "pending_independent_review"
    review = decide(f, plan)
    assert review["state"] == "reviewed_for_disposable_copy_qualification"
    view = inspect(f, plan, review)
    assert view["state"] == review["state"] and view["review_reference_basis"] == "caller_retained_exact_digest"
    assert all(view[k] is False for k in FLAGS)
    assert view["content_authenticity"] == "unassessed" and view["atomic_snapshot"] is False
    assert [f.files(r) for r in roots] == before
    history = f.files(f.readiness.reviews.planner.journal.root)
    assert len(history) == 2 and all(b"assigned_reviewer" not in raw for raw, _ in history.values())
    assert decide(f, plan)["state"] == "snapshot_or_publication_conflict"
    assert f.files(f.readiness.reviews.planner.journal.root) == history


@pytest.mark.parametrize("decision", list(DECISIONS))
def test_closed_decisions_and_exact_ref_replay(f, decision):
    plan = prepare(f)
    review = decide(f, plan, decision)
    assert review["state"] == DECISIONS[decision][1]
    assert inspect(f, plan, review)["state"] == review["state"]
    assert inspect(f, plan)["state"] == "review_reference_not_supplied"


@pytest.mark.parametrize("kind", ["self", "other", "revoked", "csrf", "origin", "duplicate", "get"])
def test_authentication_and_independence_fail_closed_without_cached_metadata(f, kind):
    plan = prepare(f)
    role = "preparer" if kind == "self" else "other" if kind == "other" else "reviewer"
    scope = f.scope(role)
    if kind == "revoked":
        f.revoke(role)
    elif kind in {"csrf", "origin"}:
        field = b"origin" if kind == "origin" else b"x-csrf-token"
        scope["headers"] = [(k, b"invalid" if k == field else v) for k, v in scope["headers"]]
    elif kind == "duplicate":
        scope["headers"].append((b"cookie", b"la_session=invalid"))
    elif kind == "get":
        scope["method"] = "GET"
    history = f.files(f.readiness.reviews.planner.journal.root)
    value = asyncio.run(f.readiness.dispatch(scope, "decide", **f.refs(plan), decision="accept", reason_code=DECISIONS["accept"][0]))
    assert value["state"] == "denied" and all(value[k] is None for k in ("plan", "review", "observation"))
    assert f.files(f.readiness.reviews.planner.journal.root) == history


@pytest.mark.parametrize("change", ["source", "journal", "candidate", "expiry", "reviewer", "preparer"])
def test_changed_context_keeps_exact_prior_review_and_requires_fresh_preparation(f, change):
    plan = prepare(f)
    review = decide(f, plan)
    history = f.files(f.readiness.reviews.planner.journal.root)
    if change == "expiry":
        f.now += 301
    elif change in {"reviewer", "preparer"}:
        f.revoke(change)
    else:
        root = {"source": f.source, "journal": f.journal, "candidate": f.readiness.candidate.root}[change]
        e.retain(root / ("e" * 32 + ".receipt"), receipts.MAGIC + os.urandom(48))
    role = "reviewer" if change == "preparer" else "preparer"
    view = inspect(f, plan, review, role=role)
    assert view["state"] == "stale_readiness_review_retained" and view["review"] is not None
    assert f.files(f.readiness.reviews.planner.journal.root) == history
    assert all(view[k] is False for k in FLAGS)


@pytest.mark.parametrize("kind", ["missing", "extra", "modified", "staging", "partial", "pair", "cross_link", "symlink"])
def test_copy_is_not_inferred_from_partial_or_linked_matching_bytes(f, kind):
    if kind == "cross_link":
        path = next(f.journal.iterdir())
        os.link(path, f.readiness.candidate.root / path.name)
    else:
        copy_fixture(f)
        root = f.readiness.candidate.root
        path = next(root.iterdir())
        if kind == "missing":
            path.unlink()
        elif kind == "extra":
            e.retain(root / ("e" * 32 + ".receipt"), receipts.MAGIC + os.urandom(48))
        elif kind == "modified":
            path.write_bytes(receipts.MAGIC + os.urandom(48))
        elif kind in {"staging", "partial"}:
            if kind == "partial":
                (root / (".pending-" + "e" * 32)).touch(mode=0o600)
            else:
                e.retain(root / (".pending-" + "e" * 32), path.read_bytes())
        elif kind == "pair":
            os.link(path, root / (".pending-" + "e" * 32))
        elif kind == "symlink":
            path.unlink()
            path.symlink_to(next(f.journal.iterdir()))
    before = f.files(f.readiness.reviews.planner.journal.root)
    observation = call(f, "observe")
    if kind == "symlink":
        assert observation["state"] == "snapshot_or_publication_conflict"
    else:
        assert observation["observation"]["comparison"] in {"copy_mismatch", "interrupted_or_unverifiable_entries"}
        assert call(f, "prepare", plan_id="9" * 32, expected_snapshot_sha256=observation["snapshot_sha256"])["state"] == "blocked_copy_context"
    assert f.files(f.readiness.reviews.planner.journal.root) == before


@pytest.mark.parametrize("kind", ["key", "root", "profile", "scope", "context"])
def test_independently_pinned_candidate_cannot_be_replaced_or_auto_enrolled(f, kind):
    target = f.readiness.candidate_pins
    value = {"key": {"key_fingerprint": "f" * 64}, "root": {"store_identity": (0, 0)}, "profile": {"profile_sha256": "f" * 64},
             "scope": {"scope_sha256": "f" * 64}, "context": {"context_id": "f" * 32}}[kind]
    with pytest.raises(ValueError):
        replace(f.readiness, candidate_pins=replace(target, **value))


@pytest.mark.parametrize("field", ["plan_ciphertext_sha256", "plan_sha256", "decision_ciphertext_sha256"])
def test_wrong_exact_reference_never_returns_partial_plaintext(f, field):
    plan = prepare(f)
    review = decide(f, plan)
    body = {**f.refs(plan), "decision_ciphertext_sha256": review["decision_ciphertext_sha256"]}
    body[field] = "f" * 64
    value = call(f, "inspect", **body)
    assert value["state"] == "unverifiable" and value["plan"] is value["review"] is None


@pytest.mark.parametrize("stage", ["before", "after"])
def test_late_expiry_withholds_success_and_preserves_every_committed_byte(f, stage):
    observation = call(f, "observe")
    original = f.readiness.reviews.planner.write
    def write(kind, ident, value):
        if stage == "before":
            f.now += 301
        committed = original(kind, ident, value)
        if stage == "after":
            f.now += 301
        return committed
    with patch.object(f.readiness.reviews.planner, "write", write):
        plan = call(f, "prepare", plan_id="9" * 32, expected_snapshot_sha256=observation["snapshot_sha256"])
    assert plan["state"] == "snapshot_or_publication_conflict" and plan["plan"] is None
    assert len(f.files(f.readiness.reviews.planner.journal.root)) == 1


def test_repeated_double_observation_rejects_changed_destination_before_publication(f):
    observed = call(f, "observe")
    original = f.readiness.capture
    count = 0
    async def capture(self, actor):
        nonlocal count
        value = await original(actor)
        count += 1
        if count == 1:
            e.retain(f.readiness.candidate.root / ("e" * 32 + ".receipt"), receipts.MAGIC + os.urandom(48))
        return value
    with patch.object(JournalBackupReadiness, "capture", capture):
        result = call(f, "prepare", plan_id="9" * 32, expected_snapshot_sha256=observed["snapshot_sha256"])
    assert result["state"] == "snapshot_or_publication_conflict"
    assert not list(f.readiness.reviews.planner.journal.root.iterdir())


def test_encrypted_schemas_are_closed_and_purpose_bound(f):
    plan = prepare(f)
    value = f.readiness.plan(**{k: v for k, v in zip(("ident", "cipher", "digest"), f.refs(plan).values(), strict=True)})
    bad = copy.deepcopy(value)
    bad["restore_execution_authorized"] = True
    audit = f.readiness.reviews.planner
    ident = "a" * 32
    bad["plan_id"] = ident
    cipher = audit.write("journal-copy-plan-v1", ident, bad)
    response = call(f, "inspect", plan_id=ident, plan_ciphertext_sha256=cipher, plan_sha256=e.sha(e.encode(bad)), decision_ciphertext_sha256=None)
    assert response["state"] == "unverifiable"
    cipher = audit.write("plan", "b" * 32, value)
    response = call(f, "inspect", plan_id="b" * 32, plan_ciphertext_sha256=cipher, plan_sha256=e.sha(e.encode(value)), decision_ciphertext_sha256=None)
    assert response["state"] == "unverifiable"


def test_a_new_namespace_requires_new_pins_new_plan_and_new_independent_review(f):
    plan = prepare(f)
    review = decide(f, plan)
    audit = f.readiness.reviews.planner.journal.root
    history = f.files(audit)
    root = f.root / "new-candidate"
    root.mkdir(mode=0o700)
    for path in f.journal.iterdir():
        e.retain(root / path.name, path.read_bytes())
    store = receipts.ReceiptStore(root=root, context_id=f.readiness.candidate.context_id,
        scope_sha256=f.readiness.candidate.scope_sha256, key=f.readiness.candidate.key)
    with pytest.raises(ValueError):
        replace(f.readiness, candidate=store)
    from journal_backup_fixture import pins
    renewed = replace(f.readiness, candidate=store, candidate_pins=pins(f, store))
    prior = f.readiness
    f.readiness = renewed
    assert inspect(f, plan, review)["state"] == "unverifiable"
    fresh = prepare(f, "a" * 32)
    assert fresh["plan_id"] != plan["plan_id"]
    assert decide(f, fresh, role="preparer")["state"] == "denied"
    fresh_review = decide(f, fresh)
    assert inspect(f, fresh, fresh_review)["state"] == "reviewed_for_disposable_copy_qualification"
    assert all(f.files(audit)[k] == v for k, v in history.items())
    f.readiness = prior
    assert inspect(f, plan, review)["state"] == "reviewed_for_disposable_copy_qualification"


@pytest.mark.parametrize("operation", ["backup", "restore", "adopt", "enroll", "repair", "execute"])
def test_no_execution_or_enrollment_operation_exists(f, operation):
    before = [f.files(r) for r in (f.source, f.journal, f.readiness.candidate.root, f.readiness.reviews.planner.journal.root)]
    value = call(f, operation)
    assert value["state"] == "unverifiable" and value["plan"] is value["observation"] is value["review"] is None
    assert before == [f.files(r) for r in (f.source, f.journal, f.readiness.candidate.root, f.readiness.reviews.planner.journal.root)]


@pytest.mark.parametrize("operation", ["prepare", "decide"])
def test_late_session_revocation_withholds_acknowledgement_without_deleting_ciphertext(f, operation):
    original = f.readiness.reviews.planner.write
    plan = prepare(f) if operation == "decide" else None
    def write(kind, ident, value):
        cipher = original(kind, ident, value)
        f.revoke("reviewer" if operation == "decide" else "preparer")
        return cipher
    with patch.object(f.readiness.reviews.planner, "write", write):
        value = decide(f, plan) if operation == "decide" else prepare(f)
    assert value["state"] == "denied" and value["plan"] is value["review"] is None
    assert len(list(f.readiness.reviews.planner.journal.root.iterdir())) == (2 if operation == "decide" else 1)


def test_zero_scan_budget_is_reported_without_cached_inventory(f):
    import receipt_recovery_inventory as physical
    with patch.object(physical, "MAX_ENTRIES", 0):
        value = call(f, "observe")
    assert value["state"] == "budget_exhausted" and value["observation"] is None


def test_observation_never_decrypts_original_or_candidate_records(f):
    copy_fixture(f)
    with patch.object(f.planner, "read", side_effect=AssertionError), patch.object(f.readiness.reviews.planner, "read", side_effect=AssertionError):
        value = call(f, "observe")
    assert value["state"] == "observed_copy_metadata" and value["content_authenticity"] == "unassessed"


def test_request_cannot_supply_actor_key_path_or_trust_binding(f):
    value = call(f, "observe", candidate_root="/untrusted", api_key="invented")
    assert value["state"] == "unverifiable" and value["observation"] is None


def test_native_report_matches_actual_frozen_outcomes_and_current_source():
    import hashlib
    import json

    from journal_backup_report import validate
    report = json.loads((ROOT / "docs/evidence/native-journal-backup-readiness-2026-10-30.json").read_text())
    native = report["native"]
    assert report["status"] == "qualified" and report["production_activation"] is False and report["disposable_volumes_removed"] is True
    assert validate(native, native["receipt_manifest_sha256"], native["controller_manifest_sha256"])["frozen_outcomes"] == 38
    for name, digest in report["source_sha256"].items():
        assert not (ROOT / name).is_symlink() and hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    assert len(report["posture"]) == 2
    assert all(row["four_distinct_named_volumes"] for row in report["posture"])


@pytest.mark.parametrize("fault", ["missing", "extra", "outcome", "process_count", "boolean_count", "authority", "auth", "source", "network_claim", "semantic_claim", "mode", "scope"])
def test_frozen_native_report_rejects_scope_or_outcome_inflation(fault):
    import json

    from journal_backup_report import validate
    report = json.loads((ROOT / "docs/evidence/native-journal-backup-readiness-2026-10-30.json").read_text())
    native = report["native"]
    value = copy.deepcopy(native)
    if fault == "missing":
        value.pop("read_only_packages_exact")
    elif fault == "extra":
        value["restored"] = True
    elif fault == "outcome":
        value["modes"][0]["cases"][0]["state"] = "restored"
    elif fault in {"process_count", "boolean_count"}:
        value["modes"][0]["fresh_worker_processes"] = True if fault == "boolean_count" else 18
    elif fault == "authority":
        value["modes"][0]["trust_migrated"] = True
    elif fault == "auth":
        value["modes"][0]["independent_review"] = False
    elif fault == "source":
        value["modes"][0]["original_ciphertext_exact"] = False
    elif fault == "network_claim":
        value["live_provider_requests"] = 1
    elif fault == "semantic_claim":
        value["key_custody"] = "approved"
    elif fault == "mode":
        value["modes"][0]["mode"] = "operational_restore"
    elif fault == "scope":
        value["receipt_manifest_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        validate(value, native["receipt_manifest_sha256"], native["controller_manifest_sha256"])


def test_readiness_review_key_cannot_reuse_the_original_receipt_key(f):
    from journal_backup_fixture import pins, reconciler
    from receipt_recovery_planning import RecoveryPlanner

    old = f.readiness.reviews.planner
    reused = receipts.ReceiptStore(root=old.journal.root, context_id=old.journal.context_id,
        scope_sha256=old.journal.scope_sha256, key=f.source_store.key)
    planner = RecoveryPlanner(f.journal_store, reused, pins(f, f.journal_store), f.authority,
        preparer_id=f.ids["preparer"], reviewer_id=f.ids["reviewer"], clock=lambda: f.now)
    with pytest.raises(ValueError):
        replace(f.readiness, reviews=reconciler(f, planner))
