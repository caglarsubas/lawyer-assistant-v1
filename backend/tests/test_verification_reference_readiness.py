"""Retained bytes never create acknowledgement, current authority or a new window."""

import json
import os
import sqlite3
import sys
from dataclasses import asdict, replace
from pathlib import Path
from types import MappingProxyType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import operator_enrollment_evidence as e  # noqa: E402
import verification_reference_readiness as access  # noqa: E402
from destination_snapshot_fixture import make_pair  # noqa: E402
from operator_recovery_inputs import FLAGS  # noqa: E402
from qualify_destination_snapshot import short_session  # noqa: E402
from verification_reference_fixture import ENTRY, RECORD, make_frame, retain_external  # noqa: E402

OTHER = "d" * 32


@pytest.fixture(scope="module")
def shared_pair(tmp_path_factory):
    pair = make_pair(tmp_path_factory.mktemp("verification-reference-read-only") / "pair")
    yield pair
    pair.close()


@pytest.fixture
def frame(shared_pair, tmp_path):
    before = shared_pair.protected()
    value = make_frame(shared_pair, tmp_path / "records")
    yield value
    assert shared_pair.protected() == before


@pytest.fixture
def isolated(tmp_path):
    pair = make_pair(tmp_path / "pair")
    value = make_frame(pair, tmp_path / "records")
    yield value
    pair.close()


def safe(value, *, withheld=False):
    assert value["read_only"] and all(value[k] is False for k in FLAGS)
    assert not value["genuine_acknowledgement_verified"]
    assert not value["snapshot_verified"] and not value["destination_attestation_verified"]
    assert not value["atomic_snapshot"] and not value["joint_rollback_qualified"]
    assert not value["ready_for_disposable_input_handoff"] and not value["ready_for_pinned_disposable_review_handoff"]
    if withheld:
        assert value["retention_plan"] is None and value["reobservation"] is None
        assert not value["retention_plan_ready"] and not value["host_acknowledgement_pin_matched"]


def read(frame, callback):
    before = frame.protected()
    value = callback()
    assert frame.protected() == before
    safe(value)
    return value


def test_preview_and_exact_retained_reference_reopen_without_service_writes(frame):
    preview = read(frame, frame.preview)
    assert preview["state"] == "private_retention_plan_ready" and preview["retention_plan_ready"]
    assert preview == read(frame, frame.preview)
    original = frame.pair.protected()
    ref, ack = retain_external(frame)
    assert frame.pair.protected() == original
    current = read(frame, lambda: frame.reobserve(ref, ack))
    assert current["state"] == "retained_verification_reobserved" and current["host_acknowledgement_pin_matched"]
    assert current == read(frame, lambda: frame.reobserve(ref, ack))
    assert current["reobservation"]["reference_sha256"] == ref.sha256
    assert current["reobservation"]["plan_sha256"] == preview["retention_plan"]["plan_sha256"]
    assert current["reobservation"]["expires_at"] <= frame.pair.snapshot["expires_at"]
    assert current["reobservation"]["original_handoff_expires_at"] == frame.pair.snapshot["expires_at"]
    assert "cookie" not in json.dumps(current) and "session_sha256" not in json.dumps(current)


def test_destination_authentication_precedes_all_record_and_inventory_reads(frame, monkeypatch):
    ref, ack = retain_external(frame)
    s = frame.service(references={ENTRY: ref}, acknowledgements={ack.sha256: ack})
    monkeypatch.setattr(s, "record", lambda *a: pytest.fail("Denied actor decrypted a record"))
    monkeypatch.setattr(s, "inventory", lambda *a: pytest.fail("Denied actor inspected the namespace"))
    for role, fault in [("other", None), ("preparer", None), ("reviewer", b"cookie"),
                        ("reviewer", b"origin"), ("reviewer", b"x-csrf-token")]:
        scope = frame.pair.target.account.scope(role)
        if fault:
            scope["headers"] = [(k, b"invalid" if k == fault else v) for k, v in scope["headers"]]
        value = read(frame, lambda: s.dispatch(scope, "reobserve", entry_id=ENTRY, reference=asdict(ref)))
        assert value["state"] == "denied"
        safe(value, withheld=True)


def test_missing_acknowledgement_and_missing_pin_do_not_decrypt_retained_bytes(frame, monkeypatch):
    ref, ack = retain_external(frame)
    missing = replace(ref, acknowledgement_sha256=None)
    for selected, pins, expected in [(missing, {ack.sha256: ack}, "acknowledgement_required"),
                                      (ref, {}, "acknowledgement_pin_required")]:
        s = frame.service(references={ENTRY: selected}, acknowledgements=pins)
        monkeypatch.setattr(s, "record", lambda *a: pytest.fail("Missing acknowledgement was adopted"))
        monkeypatch.setattr(s, "inventory", lambda *a: pytest.fail("Missing acknowledgement triggered discovery"))
        value = read(frame, lambda: s.dispatch(frame.pair.target.account.scope("reviewer"), "reobserve",
                                             entry_id=ENTRY, reference=asdict(selected)))
        assert value["state"] == expected
        safe(value, withheld=True)


def test_explicit_versions_and_entry_selection_never_follow_a_newer_record(frame):
    first, ack1 = retain_external(frame)
    second, ack2 = retain_external(frame, record_id="7" * 32)
    s = frame.service(references={ENTRY: first, OTHER: second}, acknowledgements={ack1.sha256: ack1, ack2.sha256: ack2})
    scope = frame.pair.target.account.scope("reviewer")
    value = read(frame, lambda: s.dispatch(scope, "reobserve", entry_id=ENTRY, reference=asdict(first)))
    assert value["reobservation"]["reference_sha256"] == first.sha256
    for selected in [asdict(second), {**asdict(first), "ciphertext_sha256": "0" * 64},
                     {**asdict(first), "plaintext_sha256": "0" * 64},
                     {**asdict(first), "acknowledgement_sha256": None}]:
        value = read(frame, lambda: s.dispatch(scope, "reobserve", entry_id=ENTRY, reference=selected))
        assert value["state"] == "unverifiable"
        safe(value, withheld=True)
    value = read(frame, lambda: s.dispatch(scope, "reobserve", entry_id="a" * 32, reference=asdict(first)))
    assert value["state"] == "unverifiable"
    safe(value, withheld=True)


def test_tampered_ciphertext_is_retained_without_metadata_or_repair(frame):
    ref, ack = retain_external(frame)
    path = frame.store.root / (ref.record_id + ".receipt")
    old = path.read_bytes()
    path.write_bytes(old[:-1] + bytes([old[-1] ^ 1]))  # Deliberate fault in this test-owned sidecar only.
    value = read(frame, lambda: frame.reobserve(ref, ack))
    assert value["state"] == "unverifiable"
    safe(value, withheld=True)
    assert path.read_bytes() != old


def test_unknown_staging_links_permissions_and_limits_block_without_cleanup(frame, tmp_path):
    for index, fault in enumerate(["staging", "symlink", "hardlink", "permissions", "count", "size"]):
        f = make_frame(frame.pair, tmp_path / str(index))
        path = f.store.root / (RECORD + ".receipt")
        if fault == "staging":
            e.retain(f.store.root / ".pending-invented", b"INVENTED interrupted bytes")
        elif fault == "symlink":
            path.symlink_to(__file__)
        elif fault == "hardlink":
            original = tmp_path / ("link-source-" + str(index))
            e.retain(original, b"INVENTED linked bytes")
            os.link(original, path)
        elif fault == "permissions":
            e.retain(path, b"INVENTED broad mode")
            path.chmod(0o644)
        elif fault == "count":
            for n in range(9):
                e.retain(f.store.root / (format(n, "032x") + ".receipt"), b"INVENTED bounded-count fault")
        else:
            e.retain(path, b"x" * (access.MAX_PLAIN + 100))
        value = read(f, f.preview)
        assert value["state"] == "unverifiable"
        safe(value, withheld=True)


def test_record_namespace_and_registry_races_withhold_metadata(frame, tmp_path):
    for index, fault in enumerate(["new_record", "registry"]):
        f = make_frame(frame.pair, tmp_path / str(index))
        ref, ack = retain_external(f)
        s = f.service(references={ENTRY: ref}, acknowledgements={ack.sha256: ack})
        def changed(_):
            if fault == "new_record":
                e.retain(f.store.root / ("9" * 32 + ".receipt"), b"INVENTED unregistered bytes")
            else:
                s.references = MappingProxyType({})
        s.checkpoint = changed
        originals = f.pair.protected()
        value = s.dispatch(f.pair.target.account.scope("reviewer"), "reobserve", entry_id=ENTRY, reference=asdict(ref))
        assert value["state"] == "observation_conflict"
        safe(value, withheld=True)
        assert f.pair.protected() == originals
        assert (f.store.root / (ref.record_id + ".receipt")).is_file()
        if fault == "new_record":
            assert (f.store.root / ("9" * 32 + ".receipt")).read_bytes() == b"INVENTED unregistered bytes"


@pytest.mark.parametrize("side", ["source", "destination"])
def test_current_session_revocation_withholds_retained_metadata(isolated, side):
    ref, ack = retain_external(isolated)
    getattr(isolated.pair, "target" if side == "destination" else "source").account.revoke("reviewer")
    value = read(isolated, lambda: isolated.reobserve(ref, ack))
    assert value["state"] == ("denied" if side == "destination" else "verification_unavailable")
    safe(value, withheld=True)


def test_expiry_and_a_new_receiver_session_require_fresh_validation_without_rewriting_history(isolated, monkeypatch):
    ref, ack = retain_external(isolated)
    for side in [isolated.pair.source, isolated.pair.target]:
        with monkeypatch.context() as patch:
            patch.setattr(side.account, "now", isolated.pair.snapshot["expires_at"])
            value = read(isolated, lambda: isolated.reobserve(ref, ack))
            assert value["state"] == "verification_unavailable"
            safe(value, withheld=True)
    scope = short_session(isolated.pair.target.account)  # Fixture-owned setup, before the read-only baseline.
    value = read(isolated, lambda: isolated.reobserve(ref, ack, scope=scope))
    assert value["state"] == "retained_verification_needs_revalidation"
    safe(value, withheld=True)
    preview = read(isolated, lambda: isolated.preview(scope=scope))
    assert preview["retention_plan"]["plan_sha256"] != ack.plan_sha256
    assert preview["retention_plan"]["plan"]["verification"]["expires_at"] == isolated.pair.target.account.now + 30
    assert read(isolated, lambda: isolated.reobserve(ref, ack))["state"] == "retained_verification_reobserved"


def test_closed_operations_budgets_and_unavailable_checks_fail_closed(frame, monkeypatch):
    ref, ack = retain_external(frame)
    s = frame.service(references={ENTRY: ref}, acknowledgements={ack.sha256: ack})
    for operation, extra in [("retain", {}), ("restore", {}), ("reobserve", {"source_scope": {}})]:
        value = read(frame, lambda: s.dispatch(frame.pair.target.account.scope("reviewer"), operation,
                                              entry_id=ENTRY, reference=asdict(ref), **extra))
        assert value["state"] == "unverifiable"
        safe(value, withheld=True)
    with monkeypatch.context() as patch:
        patch.setattr(access, "BUDGET_SECONDS", 0)
        patch.setattr(s, "record", lambda *a: pytest.fail("Exhausted budget reached retained plaintext"))
        value = read(frame, lambda: s.dispatch(frame.pair.target.account.scope("reviewer"), "reobserve",
                                              entry_id=ENTRY, reference=asdict(ref)))
        assert value["state"] == "budget_exhausted"
        safe(value, withheld=True)
    def unavailable(*a, **k):
        raise sqlite3.OperationalError("INVENTED private driver detail")
    with monkeypatch.context() as patch:
        patch.setattr(s.verifier.target.planner, "actor", unavailable)
        value = read(frame, lambda: s.dispatch(frame.pair.target.account.scope("reviewer"), "reobserve",
                                              entry_id=ENTRY, reference=asdict(ref)))
        assert value["state"] == "unverifiable" and "INVENTED" not in json.dumps(value)
        safe(value, withheld=True)


def test_separate_store_pins_and_bounded_registries_cannot_be_filled_from_requests(frame):
    ref, ack = retain_external(frame)
    with pytest.raises(ValueError):
        access.VerificationReferences(frame.pair.verifier(), frame.store, frame.pins,
                                      {format(n, "032x"): ref for n in range(5)}, {})
    with pytest.raises(ValueError):
        access.VerificationReferences(frame.pair.verifier(), frame.store, replace(frame.pins, key_fingerprint="0" * 64), {}, {})
    with pytest.raises(ValueError):
        access.VerificationReferences(frame.pair.verifier(), frame.store, frame.pins, {}, {"0" * 64: ack})
