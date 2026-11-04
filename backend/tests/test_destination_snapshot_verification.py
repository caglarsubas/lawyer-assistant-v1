"""Receiver authorization and exact versions, not bearer-digest authority."""

import sqlite3
import sys
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import destination_snapshot_verification as verification  # noqa: E402
import operator_enrollment_evidence as e  # noqa: E402
from destination_snapshot_fixture import make_pair  # noqa: E402
from operator_recovery_inputs import FLAGS  # noqa: E402
from recovery_input_fixture import SELECTION  # noqa: E402
from recovery_inventory_fixture import DESTINATION, ENTRY  # noqa: E402
from recovery_review_inventory import ReviewInventory  # noqa: E402


@pytest.fixture
def pair(tmp_path):
    f = make_pair(tmp_path / "pair")
    yield f
    f.close()


def safe(value):
    assert all(value[k] is False for k in FLAGS)
    assert not value["destination_attestation_verified"]
    assert not value["ready_for_pinned_disposable_review_handoff"]
    assert not value["ready_for_disposable_input_handoff"]
    assert not value["atomic_snapshot"] and not value["joint_rollback_qualified"]
    assert value["inventory"] is None and value["handoff"] is None


def no_metadata(value):
    safe(value)
    assert not value["snapshot_verified"] and value["verification"] is None


def records(pair):
    return [{p.name: p.read_bytes() for p in f.sidecar.root.iterdir()} for f in (pair.source, pair.target)]


def test_exact_receiver_verification_reopens_without_writes_or_expiry_renewal(pair):
    before = pair.protected()
    first = pair.call()
    assert first["state"] == "destination_snapshot_verified" and first["snapshot_verified"]
    safe(first)
    assert first == pair.call(pair.verifier())
    metadata = first["verification"]
    assert metadata["original_handoff_expires_at"] == pair.snapshot["expires_at"]
    assert metadata["expires_at"] <= pair.snapshot["expires_at"]
    assert metadata["reference_sha256"] == pair.reference.sha256
    assert metadata["snapshot_sha256"] == verification.Snapshot.parse(pair.snapshot).sha256
    assert "session_sha256" not in e.encode(first).decode() and "cookie" not in e.encode(first).decode()
    assert pair.protected() == before


def test_denied_receiver_never_reads_source_or_target_snapshot(pair, monkeypatch):
    s = pair.verifier()
    monkeypatch.setattr(s, "observe_target", lambda *a: pytest.fail("Denied receiver inspected target"))
    monkeypatch.setattr(s, "source_matches", lambda *a: pytest.fail("Denied receiver inspected source"))
    before = pair.protected()
    for role, fault in [("other", None), ("preparer", None), ("reviewer", "cookie"),
                        ("reviewer", "origin"), ("reviewer", "x-csrf-token")]:
        scope = pair.target.account.scope(role)
        if fault:
            scope["headers"] = [(k, b"bad" if k == fault.encode() else v) for k, v in scope["headers"]]
        value = pair.call(s, scope=scope)
        assert value["state"] == "denied"
        no_metadata(value)
    assert pair.protected() == before


def test_source_and_destination_cookies_are_not_interchangeable(pair):
    before = pair.protected()
    value = pair.call(scope=pair.source.account.scope("reviewer"))
    assert value["state"] == "denied"
    no_metadata(value)
    wrong_source = pair.verifier(source_scope=pair.target.account.scope("reviewer"))
    value = pair.call(wrong_source)
    assert value["state"] == "source_snapshot_unavailable"
    no_metadata(value)
    assert pair.protected() == before


def test_every_handoff_field_is_bound_to_the_independent_pins_and_fresh_source(pair):
    before = pair.protected()
    for name in pair.snapshot:
        changed = deepcopy(pair.snapshot)
        changed[name] = changed[name] + 1 if name == "expires_at" else "0" * len(changed[name])
        value = pair.call(snapshot=changed)
        assert value["state"] in {"snapshot_binding_mismatch", "source_snapshot_unavailable"}
        no_metadata(value)
    assert pair.protected() == before


def test_closed_packet_shape_types_and_missing_fields_never_release_metadata(pair):
    before = pair.protected()
    for packet in [None, [], {}, {**pair.snapshot, "execute": True},
                   {**pair.snapshot, "expires_at": True}, {**pair.snapshot, "inventory_sha256": "f" * 65}]:
        value = pair.verifier().dispatch(pair.target.account.scope("reviewer"), "verify",
            snapshot=packet, reference=asdict(pair.reference))
        assert value["state"] == "unverifiable"
        no_metadata(value)
    assert pair.protected() == before


def test_exact_reference_versions_are_required_including_missing_acknowledgement(pair):
    before = pair.protected()
    for name, original in asdict(pair.reference).items():
        ref = {**asdict(pair.reference), name: "0" * len(original)}
        value = pair.call(reference=ref)
        assert value["state"] == "unverifiable"
        no_metadata(value)
    value = pair.call(reference={**asdict(pair.reference), "decision_ciphertext_sha256": None})
    assert value["state"] == "unverifiable"
    no_metadata(value)
    assert pair.protected() == before


@pytest.mark.parametrize("decision,acknowledged", [("changes_required", True), ("reject", True), ("accept", False)])
def test_unaccepted_or_unacknowledged_review_cannot_reuse_an_accepted_packet(tmp_path, decision, acknowledged):
    p = make_pair(tmp_path / "unaccepted", decision=decision, acknowledged=acknowledged)
    try:
        assert p.snapshot is None
        fake = {"entry_id": ENTRY, "reference_sha256": p.reference.sha256,
            "inventory_sha256": "0" * 64, "destination_id": DESTINATION,
            "destination_context_sha256": p.pin.destination_context_sha256,
            "destination_pin_sha256": p.pin.sha256, "expires_at": p.pin.expires_at}
        before = p.protected()
        value = p.call(snapshot=fake)
        assert value["state"] == "source_snapshot_unavailable"
        no_metadata(value)
        assert p.protected() == before
    finally:
        p.close()


def test_revoked_source_session_withholds_even_an_exact_previously_valid_packet(pair):
    pair.source.account.revoke("reviewer")
    before = pair.protected()
    value = pair.call()
    assert value["state"] == "source_snapshot_unavailable"
    no_metadata(value)
    assert pair.protected() == before


def test_receiver_revocation_during_reobservation_withholds_all_metadata(pair):
    old = records(pair)
    s = pair.verifier(checkpoint=lambda _: pair.target.account.revoke("reviewer"))
    value = pair.call(s)
    assert value["state"] == "denied"
    no_metadata(value)
    assert records(pair) == old


def test_source_revocation_during_reobservation_withholds_all_metadata(pair):
    old = records(pair)
    s = pair.verifier(checkpoint=lambda _: pair.source.account.revoke("reviewer"))
    value = pair.call(s)
    assert value["state"] == "source_snapshot_unavailable"
    no_metadata(value)
    assert records(pair) == old


def test_changed_source_versions_are_not_resolved_to_current_after_restart(pair):
    e.retain(pair.source.account.profile / ".runtime-key-rotation", b"INVENTED maintenance marker")
    before = pair.protected()
    value = pair.call(pair.verifier())
    assert value["state"] == "source_snapshot_unavailable"
    no_metadata(value)
    assert pair.protected() == before


def test_destination_source_change_between_observations_withholds_everything(pair):
    old = records(pair)
    def changed(_):
        e.retain(pair.target.account.profile / ".runtime-key-rotation", b"INVENTED maintenance marker")
    value = pair.call(pair.verifier(checkpoint=changed))
    assert value["state"] in {"unverifiable", "denied", "observation_conflict"}
    no_metadata(value)
    assert records(pair) == old


def test_new_source_ciphertext_invalidates_snapshot_without_adoption(pair):
    path = pair.source.sidecar.root / ("9" * 32 + ".receipt")
    e.retain(path, next(pair.source.sidecar.root.iterdir()).read_bytes())
    before = pair.protected()
    value = pair.call()
    assert value["state"] == "source_snapshot_unavailable"
    no_metadata(value)
    assert pair.protected() == before and path.is_file()


def test_destination_journal_race_is_detected_and_injected_bytes_retained(pair):
    path = pair.target.sidecar.root / ("8" * 32 + ".receipt")
    def changed(_):
        e.retain(path, b"INVENTED unregistered record")
    value = pair.call(pair.verifier(checkpoint=changed))
    assert value["state"] == "observation_conflict"
    no_metadata(value)
    assert path.read_bytes() == b"INVENTED unregistered record"


def test_interrupted_destination_staging_blocks_without_cleanup(pair):
    path = pair.target.sidecar.root / ".pending-invented"
    e.retain(path, b"INVENTED interrupted staging")
    before = pair.protected()
    value = pair.call()
    assert value["state"] == "unverifiable"
    no_metadata(value)
    assert pair.protected() == before and path.is_file()


def test_source_and_destination_registries_must_share_the_independent_exact_pin(pair):
    other = replace(pair.pin, destination_context_sha256="0" * 64)
    source = ReviewInventory(pair.source.service(), {ENTRY: pair.reference}, {DESTINATION: other})
    with pytest.raises(ValueError):
        verification.DestinationVerifier(source, pair.target.service(), source_scope=pair.source.account.scope("reviewer"),
            reference=pair.reference, pin=other, selection_id=SELECTION)
    with pytest.raises(ValueError):
        verification.DestinationVerifier(pair.inventory, pair.target.service(), source_scope=pair.source.account.scope("reviewer"),
            reference=pair.reference, pin=replace(pair.pin, expires_at=pair.pin.expires_at + 1), selection_id=SELECTION)


def test_original_expiry_and_both_clocks_cannot_be_renewed_by_a_fresh_receiver(pair):
    pair.source.account.now = pair.snapshot["expires_at"]
    before = pair.protected()
    value = pair.call(pair.verifier())
    assert value["state"] == "source_snapshot_unavailable"
    no_metadata(value)
    assert pair.protected() == before


def test_shorter_receiver_session_limits_result_without_changing_original_handoff(pair):
    from app.auth import create_session
    from app.db import LoginSession, User, digest
    account = pair.target.account
    with account.store.session() as session:
        cookie, csrf = create_session(session, session.get(User, account.ids["reviewer"]), 1)
        new = session.get(LoginSession, digest(cookie))
        new.expires_at = datetime.fromtimestamp(account.now + 30, timezone.utc).isoformat()
        session.commit()
    scope = account.scope("reviewer")
    scope["headers"] = [(b"cookie", ("la_session=" + cookie).encode()), (b"x-csrf-token", csrf.encode()),
                        (b"origin", b"http://operator.invalid")]
    before = pair.protected()
    value = pair.call(scope=scope)
    assert value["state"] == "destination_snapshot_verified"
    assert value["verification"]["expires_at"] == account.now + 30
    assert value["verification"]["original_handoff_expires_at"] == pair.snapshot["expires_at"]
    assert pair.protected() == before


def test_total_and_source_execution_budgets_fail_closed(pair, monkeypatch):
    before = pair.protected()
    monkeypatch.setattr(verification, "BUDGET_SECONDS", 0)
    value = pair.call()
    assert value["state"] == "budget_exhausted"
    no_metadata(value)
    monkeypatch.setattr(verification, "BUDGET_SECONDS", 10)
    import recovery_review_inventory as source
    monkeypatch.setattr(source, "BUDGET_SECONDS", 0)
    value = pair.call()
    assert value["state"] == "budget_exhausted"
    no_metadata(value)
    assert pair.protected() == before


@pytest.mark.parametrize("side", ["source", "destination"])
def test_unavailable_database_never_leaks_metadata_or_driver_details(pair, monkeypatch, side):
    selected = pair.inventory.reviews.planner if side == "source" else pair.verifier().target.planner
    s = pair.verifier()
    if side == "destination":
        selected = s.target.planner
    def unavailable(*a, **k):
        raise sqlite3.OperationalError("INVENTED private connection detail")
    monkeypatch.setattr(selected, "actor", unavailable)
    before = pair.protected()
    value = pair.call(s)
    assert value["state"] == ("source_snapshot_unavailable" if side == "source" else "unverifiable")
    no_metadata(value)
    assert "INVENTED" not in e.encode(value).decode()
    assert pair.protected() == before


def test_request_cannot_provision_pins_execute_or_supply_source_credentials(pair):
    s = pair.verifier()
    before = pair.protected()
    for operation, extra in [("execute", {}), ("verify", {"source_scope": {}}), ("verify", {"pin": asdict(pair.pin)})]:
        value = s.dispatch(pair.target.account.scope("reviewer"), operation,
            snapshot=pair.snapshot, reference=asdict(pair.reference), **extra)
        assert value["state"] == "unverifiable"
        no_metadata(value)
    assert pair.protected() == before


def test_source_cannot_be_its_own_receiving_namespace(pair):
    with pytest.raises(ValueError):
        verification.DestinationVerifier(pair.inventory, pair.source.service(),
            source_scope=pair.source.account.scope("reviewer"), reference=pair.reference,
            pin=pair.pin, selection_id=SELECTION)
