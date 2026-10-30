"""Real disposable auth and filesystem copies; never a live journal or key."""

import asyncio
import os
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts")]
import operator_enrollment_evidence as e  # noqa: E402
import private_inventory_receipts as receipts  # noqa: E402
from journal_backup_fixture import Fixture  # noqa: E402
from journal_materialization import DECISIONS, FLAGS, OP_REFS, CopyOrigin  # noqa: E402
from journal_materialization_fixture import make  # noqa: E402


def call(f, service, operation, role="preparer", **body):
    return asyncio.run(service.dispatch(f.scope(role), operation, **body))


def readiness(f, service):
    r = service.readiness
    def invoke(action, role="preparer", **kw):
        return asyncio.run(r.dispatch(f.scope(role), action, **kw))
    observed = invoke("observe")
    assert observed["state"] == "observed_copy_metadata"
    p = invoke("prepare", plan_id="7" * 32, expected_snapshot_sha256=observed["snapshot_sha256"])
    assert p["state"] == "pending_independent_review"
    reviewed = invoke("decide", "reviewer", **f.refs(p), decision="accept", reason_code="exact_copy_context_checked")
    assert reviewed["state"] == "reviewed_for_disposable_copy_qualification"
    return observed, {**f.refs(p), "decision_ciphertext_sha256": reviewed["decision_ciphertext_sha256"]}


def refs(plan):
    return {k: plan[k] for k in OP_REFS}


def prepare(f, service, ident="8" * 32):
    observed, reviewed = readiness(f, service)
    return call(f, service, "prepare", operation_id=ident, expected_snapshot_sha256=observed["snapshot_sha256"], readiness_refs=reviewed)


def decide(f, service, plan, decision="authorize", role="reviewer"):
    return call(f, service, "decide", role, **refs(plan), decision=decision, reason_code=DECISIONS[decision])


def materialize(f, service, plan, review):
    return call(f, service, "materialize", **refs(plan), decision_ciphertext_sha256=review["decision_ciphertext_sha256"])


def proof(plan, review, completion):
    return {**refs(plan), "decision_ciphertext_sha256": review["decision_ciphertext_sha256"],
            **{k: completion[k] for k in ("intent_ciphertext_sha256", "intent_sha256", "completion_ciphertext_sha256")}}


def files(root):
    return {p.name: (p.read_bytes(), p.stat().st_mode, p.stat().st_uid, p.stat().st_nlink) for p in root.iterdir()}


@pytest.fixture
def f(tmp_path):
    f = Fixture(tmp_path)
    original = f.prepare()
    assert f.decide(original)["state"] == "reviewed_for_metadata_planning"
    f.copy = make(f)
    yield f
    f.store.engine.dispose()


def test_backup_and_freshly_reviewed_restore_preserve_both_histories_and_ciphertext(f):
    original = files(f.source), files(f.journal)
    backup = f.copy
    p = prepare(f, backup)
    assert p["state"] == "copy_needs_independent_authorization"
    d = decide(f, backup, p)
    assert d["state"] == "disposable_copy_authorized"
    c = materialize(f, backup, p, d)
    assert c["state"] == "ciphertext_backup_materialized"
    exact = proof(p, d, c)
    before = files(backup.readiness.candidate.root), files(backup.controls.planner.journal.root), files(backup.readiness.reviews.planner.journal.root)
    v = call(f, backup, "verify", **exact)
    assert v["state"] == "retained_copy_verified" and all(v[k] is False for k in FLAGS)
    assert v["production_execution_authorized"] is False and v["content_authenticity"] == "unassessed"
    restored = make(f, "restore", source=backup.readiness.candidate, origin=CopyOrigin(service=backup, **exact))
    rp = prepare(f, restored, "9" * 32)
    rd = decide(f, restored, rp)
    rc = materialize(f, restored, rp, rd)
    assert rc["state"] == "ciphertext_restore_materialized"
    verified = call(f, restored, "verify", **proof(rp, rd, rc))
    assert verified["state"] == "retained_copy_verified" and all(verified[k] is False for k in FLAGS)
    assert (files(f.source), files(f.journal)) == original
    assert (files(backup.readiness.candidate.root), files(backup.controls.planner.journal.root), files(backup.readiness.reviews.planner.journal.root)) == before
    assert {n: row[0] for n, row in files(restored.readiness.candidate.root).items()} == {n: row[0] for n, row in original[1].items()}
    history = files(restored.controls.planner.journal.root)
    assert len(history) == 4
    assert materialize(f, restored, rp, rd)["state"] == "copy_context_or_publication_conflict"
    assert files(restored.controls.planner.journal.root) == history


@pytest.mark.parametrize("decision", ["changes_required", "reject"])
def test_execution_needs_an_authorizing_decision(f, decision):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p, decision)
    assert materialize(f, f.copy, p, d)["state"] == "denied"
    assert not list(f.copy.readiness.candidate.root.iterdir())


@pytest.mark.parametrize("kind", ["self", "other", "revoked", "csrf", "origin", "duplicate_cookie", "get"])
def test_invalid_or_nonindependent_authorization_withholds_all_history(f, kind):
    p = prepare(f, f.copy)
    role = "preparer" if kind == "self" else "other" if kind == "other" else "reviewer"
    scope = f.scope(role)
    if kind == "revoked":
        f.revoke(role)
    elif kind in {"csrf", "origin"}:
        field = b"origin" if kind == "origin" else b"x-csrf-token"
        scope["headers"] = [(k, b"invalid" if k == field else v) for k, v in scope["headers"]]
    elif kind == "duplicate_cookie":
        scope["headers"].append((b"cookie", b"la_session=invalid"))
    elif kind == "get":
        scope["method"] = "GET"
    before = files(f.copy.controls.planner.journal.root)
    value = asyncio.run(f.copy.dispatch(scope, "decide", **refs(p), decision="authorize", reason_code=DECISIONS["authorize"]))
    assert value["state"] == "denied" and value["history"] is None
    assert files(f.copy.controls.planner.journal.root) == before and not list(f.copy.readiness.candidate.root.iterdir())


def test_readiness_acceptance_cannot_be_used_as_copy_authorization(f):
    observed, reviewed = readiness(f, f.copy)
    v = call(f, f.copy, "materialize", operation_id="8" * 32, **reviewed)
    assert v["state"] == "unverifiable" and v["history"] is None
    assert not list(f.copy.readiness.candidate.root.iterdir())


@pytest.mark.parametrize("change", ["original", "journal", "candidate", "expiry", "preparer", "reviewer"])
def test_change_before_copy_blocks_writes_and_preserves_review_history(f, change):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    before = files(f.copy.controls.planner.journal.root)
    if change == "expiry":
        f.now += 301
    elif change in {"preparer", "reviewer"}:
        f.revoke(change)
    else:
        root = {"original": f.source, "journal": f.journal, "candidate": f.copy.readiness.candidate.root}[change]
        e.retain(root / ("e" * 32 + ".receipt"), receipts.MAGIC + os.urandom(48))
    target = files(f.copy.readiness.candidate.root)
    v = materialize(f, f.copy, p, d)
    assert v["state"] in {"denied", "copy_context_or_publication_conflict"} and v["history"] is None
    assert files(f.copy.controls.planner.journal.root) == before and files(f.copy.readiness.candidate.root) == target


def test_partial_publication_is_retained_without_retry_or_automatic_cleanup(f):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    original = files(f.source), files(f.journal)
    publish = receipts._publish
    def interrupted(store, ident, raw):
        publish(store, ident, raw)
        if store is f.copy.readiness.candidate:
            raise OSError("Invented interruption")
    with patch.object(receipts, "_publish", interrupted):
        v = materialize(f, f.copy, p, d)
    assert v["state"] == "unavailable" and v["history"] is None
    assert len(list(f.copy.readiness.candidate.root.iterdir())) == 1
    retained = files(f.copy.controls.planner.journal.root), files(f.copy.readiness.candidate.root)
    assert len(retained[0]) == 3
    assert materialize(f, f.copy, p, d)["state"] == "copy_context_or_publication_conflict"
    missing = call(f, f.copy, "verify", **refs(p), decision_ciphertext_sha256=d["decision_ciphertext_sha256"],
        intent_ciphertext_sha256=None, intent_sha256=None, completion_ciphertext_sha256=None)
    assert missing["state"] == "completion_reference_not_supplied" and missing["acknowledgement_recovered"] is False
    assert (files(f.copy.controls.planner.journal.root), files(f.copy.readiness.candidate.root)) == retained
    assert (files(f.source), files(f.journal)) == original


@pytest.mark.parametrize("change", ["original", "journal", "expiry", "reviewer"])
def test_retained_copy_verification_keeps_stale_review_separate_from_data_integrity(f, change):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    c = materialize(f, f.copy, p, d)
    before = files(f.copy.controls.planner.journal.root), files(f.copy.readiness.candidate.root)
    if change == "expiry":
        f.now += 301
    elif change == "reviewer":
        f.revoke(change)
    else:
        e.retain((f.source if change == "original" else f.journal) / ("e" * 32 + ".receipt"), receipts.MAGIC + os.urandom(48))
    v = call(f, f.copy, "verify", **proof(p, d, c))
    assert v["state"] == "retained_copy_verified_review_stale" and v["execution_review_current"] is False
    assert all(v[k] is False for k in FLAGS)
    assert (files(f.copy.controls.planner.journal.root), files(f.copy.readiness.candidate.root)) == before


@pytest.mark.parametrize("change", ["bytes", "extra", "version", "link", "symlink", "mode"])
def test_restored_copy_verification_rejects_any_content_version_or_topology_change(f, change):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    c = materialize(f, f.copy, p, d)
    root = f.copy.readiness.candidate.root
    path = next(root.iterdir())
    if change == "bytes":
        path.write_bytes(receipts.MAGIC + os.urandom(48))
    elif change == "extra":
        e.retain(root / ("e" * 32 + ".receipt"), receipts.MAGIC + os.urandom(48))
    elif change == "version":
        raw = path.read_bytes()
        path.unlink()
        e.retain(path, raw)
    elif change == "link":
        os.link(path, f.root / "unaccounted-link")
    elif change == "symlink":
        path.unlink()
        path.symlink_to(next(f.journal.iterdir()))
    elif change == "mode":
        path.chmod(0o644)
    before = files(f.copy.controls.planner.journal.root)
    v = call(f, f.copy, "verify", **proof(p, d, c))
    assert v["state"] == "copy_context_or_publication_conflict" and v["history"] is None
    assert files(f.copy.controls.planner.journal.root) == before


@pytest.mark.parametrize("field", ["plan_ciphertext_sha256", "plan_sha256", "decision_ciphertext_sha256", "intent_ciphertext_sha256", "intent_sha256", "completion_ciphertext_sha256"])
def test_exact_reference_mismatch_withholds_decrypted_history(f, field):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    c = materialize(f, f.copy, p, d)
    body = proof(p, d, c)
    body[field] = "f" * 64
    v = call(f, f.copy, "verify", **body)
    assert v["state"] == "unverifiable" and v["history"] is None


def test_restore_requires_exact_backup_origin_and_new_review(f):
    with pytest.raises(ValueError):
        replace(f.copy, mode="restore")
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    c = materialize(f, f.copy, p, d)
    exact = proof(p, d, c)
    restored = make(f, "restore", source=f.copy.readiness.candidate, origin=CopyOrigin(service=f.copy, **exact))
    v = call(f, restored, "materialize", **refs(p), decision_ciphertext_sha256=d["decision_ciphertext_sha256"])
    assert v["state"] in {"unavailable", "unverifiable"} and not list(restored.readiness.candidate.root.iterdir())
    with pytest.raises(ValueError):
        replace(restored, manifest_sha256="f" * 64)


def test_late_expiry_after_completion_withholds_acknowledgement_and_preserves_all_bytes(f):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    write = f.copy.controls.planner.write
    def expired(kind, ident, value):
        cipher = write(kind, ident, value)
        if kind == "materialization-completion-v1":
            f.now += 301
        return cipher
    with patch.object(f.copy.controls.planner, "write", expired):
        v = materialize(f, f.copy, p, d)
    assert v["state"] == "copy_context_or_publication_conflict" and v["history"] is None
    assert len(list(f.copy.controls.planner.journal.root.iterdir())) == 4
    assert len(list(f.copy.readiness.candidate.root.iterdir())) == 2


def test_wrong_manifest_is_not_replaced_by_current_source(f):
    changed = replace(f.copy, manifest_sha256="f" * 64)
    p = prepare(f, changed)
    assert p["state"] == "copy_context_or_publication_conflict" and not list(changed.controls.planner.journal.root.iterdir())


def test_request_cannot_supply_filesystem_key_or_actor_wiring(f):
    v = call(f, f.copy, "prepare", target="/untrusted", key="invented", actor="invented")
    assert v["state"] == "unverifiable" and not list(f.copy.readiness.candidate.root.iterdir())


@pytest.mark.parametrize("role", ["preparer", "reviewer"])
def test_revocation_after_first_ciphertext_keeps_partial_copy_and_consumed_intent(f, role):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    original = files(f.source), files(f.journal)
    publish = receipts._publish
    def revoked(store, ident, raw):
        publish(store, ident, raw)
        if store is f.copy.readiness.candidate:
            f.revoke(role)
    with patch.object(receipts, "_publish", revoked):
        v = materialize(f, f.copy, p, d)
    assert v["state"] == "denied" and v["history"] is None
    assert len(list(f.copy.readiness.candidate.root.iterdir())) == 1
    assert len(list(f.copy.controls.planner.journal.root.iterdir())) == 3
    assert (files(f.source), files(f.journal)) == original


def test_execution_window_cannot_extend_the_prerequisite_review(f):
    observed, reviewed = readiness(f, f.copy)
    f.now += 290
    p = call(f, f.copy, "prepare", operation_id="8" * 32, expected_snapshot_sha256=observed["snapshot_sha256"], readiness_refs=reviewed)
    d = decide(f, f.copy, p)
    plan = f.copy.plan(refs(p))
    assert plan["expires_at"] - plan["created_at"] == 10
    f.now += 11
    assert materialize(f, f.copy, p, d)["state"] == "copy_context_or_publication_conflict"
    assert not list(f.copy.readiness.candidate.root.iterdir())


def test_historical_backup_needs_fresh_restore_review_without_renewing_its_old_decision(f):
    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    c = materialize(f, f.copy, p, d)
    exact = proof(p, d, c)
    old = files(f.copy.controls.planner.journal.root), files(f.copy.readiness.candidate.root)
    f.now += 301
    restored = make(f, "restore", source=f.copy.readiness.candidate, origin=CopyOrigin(service=f.copy, **exact))
    rp = prepare(f, restored, "9" * 32)
    rd = decide(f, restored, rp)
    rc = materialize(f, restored, rp, rd)
    assert rc["state"] == "ciphertext_restore_materialized"
    assert call(f, restored, "verify", **proof(rp, rd, rc))["state"] == "retained_copy_verified"
    assert call(f, f.copy, "verify", **exact)["state"] == "retained_copy_verified_review_stale"
    assert (files(f.copy.controls.planner.journal.root), files(f.copy.readiness.candidate.root)) == old


def test_execution_control_key_is_separate_from_source_and_readiness_keys(f):
    from journal_backup_fixture import pins, reconciler
    from receipt_recovery_planning import RecoveryPlanner

    old = f.copy.controls.planner
    store = receipts.ReceiptStore(root=old.journal.root, context_id=old.journal.context_id,
        scope_sha256=old.journal.scope_sha256, key=f.copy.readiness.reviews.planner.journal.key)
    p = RecoveryPlanner(old.source, store, pins(f, old.source), f.authority,
        preparer_id=old.preparer, reviewer_id=old.reviewer, clock=lambda: f.now)
    with pytest.raises(ValueError):
        replace(f.copy, controls=reconciler(f, p))


def test_revocation_during_final_destination_read_withholds_completed_ack(f):
    from journal_materialization import JournalMaterializer

    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    target = JournalMaterializer.target
    fired = False
    async def late(self, actor):
        nonlocal fired
        value = await target(self, actor)
        if len(list(self.controls.planner.journal.root.iterdir())) == 4 and not fired:
            fired = True
            f.revoke("reviewer")
        return value
    with patch.object(JournalMaterializer, "target", late):
        v = materialize(f, f.copy, p, d)
    assert fired and v["state"] == "denied" and v["history"] is None
    assert len(list(f.copy.controls.planner.journal.root.iterdir())) == 4
    assert len(list(f.copy.readiness.candidate.root.iterdir())) == 2


def test_verifier_marks_review_stale_after_late_other_actor_revocation(f):
    from journal_materialization import JournalMaterializer

    p = prepare(f, f.copy)
    d = decide(f, f.copy, p)
    c = materialize(f, f.copy, p, d)
    target = JournalMaterializer.target
    calls = 0
    async def late(self, actor):
        nonlocal calls
        value = await target(self, actor)
        calls += 1
        if calls == 2:
            f.revoke("reviewer")
        return value
    before = files(f.copy.controls.planner.journal.root), files(f.copy.readiness.candidate.root)
    with patch.object(JournalMaterializer, "target", late):
        v = call(f, f.copy, "verify", **proof(p, d, c))
    assert v["state"] == "retained_copy_verified_review_stale" and v["execution_review_current"] is False
    assert (files(f.copy.controls.planner.journal.root), files(f.copy.readiness.candidate.root)) == before


def test_native_materialization_report_is_bound_to_current_source_and_closed_scope():
    import hashlib
    import json

    from journal_materialization_report import validate
    report = json.loads((ROOT / "docs/evidence/native-journal-materialization-2026-10-30.json").read_text())
    native = report["native"]
    assert report["status"] == "qualified" and report["production_activation"] is False and report["disposable_volumes_removed"] is True
    assert validate(native, native["receipt_manifest_sha256"], native["controller_manifest_sha256"])["frozen_outcomes"] == 36
    for name, digest in report["source_sha256"].items():
        assert not (ROOT / name).is_symlink() and hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    assert len(report["posture"]) == 2 and all(row["four_distinct_named_volumes"] for row in report["posture"])


@pytest.mark.parametrize("fault", ["missing", "extra", "outcome", "count", "boolean_count", "authority", "auth", "source", "provider", "custody", "protocol", "scope"])
def test_native_materialization_report_rejects_inflated_or_unbound_qualification(fault):
    import copy
    import json

    from journal_materialization_report import validate
    report = json.loads((ROOT / "docs/evidence/native-journal-materialization-2026-10-30.json").read_text())
    native = report["native"]
    value = copy.deepcopy(native)
    if fault == "missing":
        value.pop("read_only_packages_exact")
    elif fault == "extra":
        value["installed"] = True
    elif fault == "outcome":
        value["protocols"][0]["cases"][0]["state"] = "installed"
    elif fault in {"count", "boolean_count"}:
        value["protocols"][0]["processes"] = True if fault == "boolean_count" else 23
    elif fault == "authority":
        value["protocols"][0]["trust_migrated"] = True
    elif fault == "auth":
        value["protocols"][0]["independent_execution_review"] = False
    elif fault == "source":
        value["protocols"][0]["original_ciphertext_exact"] = False
    elif fault == "provider":
        value["live_provider_requests"] = 1
    elif fault == "custody":
        value["key_custody"] = "approved"
    elif fault == "protocol":
        value["protocols"][0]["name"] = "live_restore"
    elif fault == "scope":
        value["receipt_manifest_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        validate(value, native["receipt_manifest_sha256"], native["controller_manifest_sha256"])
