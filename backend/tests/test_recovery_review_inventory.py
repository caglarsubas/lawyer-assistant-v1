"""Acknowledged references only, fresh actors and separately supplied target pins."""

import hashlib
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import operator_enrollment_evidence as e  # noqa: E402
import recovery_review_inventory as inventory  # noqa: E402
from operator_recovery_inputs import FLAGS  # noqa: E402
from recovery_input_fixture import ALTERNATE, make  # noqa: E402
from recovery_inventory_fixture import (  # noqa: E402
    ENTRY,
    OTHER_ENTRY,
    handoff,
    invented_pin,
    retained_reference,
    service,
)


@pytest.fixture
def f(tmp_path):
    value = make(tmp_path / "case")
    yield value
    value.account.store.engine.dispose()


def observe(s, f, role="reviewer"):
    value = s.dispatch(f.account.scope(role), "inventory")
    assert value["state"] == "acknowledged_review_inventory"
    return value


def snapshot(f):
    return (f.protected(), {p.name: p.read_bytes() for p in f.sidecar.root.iterdir()},
            {str(p.relative_to(f.account.profile)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in f.account.profile.rglob("*") if p.is_file()})


def test_exact_inventory_and_pinned_handoff_survive_reopen_without_any_write(f):
    ref = retained_reference(f)
    pin = invented_pin(f, ref)
    before = snapshot(f)
    s = service(f, ref, pin=pin)
    original_write = s.reviews.planner.write
    s.reviews.planner.write = lambda *a, **k: pytest.fail("Read-only service tried publication")
    observed = observe(s, f)
    assert observe(service(f, ref, pin=pin), f) == observed
    entry = observed["inventory"]["entries"][0]
    assert entry["reference"] == asdict(ref) and entry["state"] == "accept"
    value = handoff(s, f, ref, observed)
    assert value["state"] == "ready_for_pinned_disposable_review_handoff"
    assert value["ready_for_pinned_disposable_review_handoff"]
    assert value["handoff"]["expires_at"] == min(pin.expires_at, entry["review"]["expires_at"])
    assert value["handoff"]["reference_sha256"] == ref.sha256
    assert not value["destination_attestation_verified"] and all(value[k] is False for k in FLAGS)
    assert not value["atomic_snapshot"] and not value["joint_rollback_qualified"]
    assert snapshot(f) == before
    s.reviews.planner.write = original_write


def test_denied_requests_do_not_reach_inventory_or_retained_ciphertext(f):
    ref = retained_reference(f)
    s = service(f, ref)
    s.collect = lambda *a: pytest.fail("Denied caller reached retained inventory")
    before = snapshot(f)
    for role, fault in [("other", None), ("reviewer", "csrf"), ("reviewer", "cookie"), ("reviewer", "origin")]:
        scope = f.account.scope(role)
        if fault:
            header = {"csrf": b"x-csrf-token", "cookie": b"cookie", "origin": b"origin"}[fault]
            scope["headers"] = [(k, b"bad" if k == header else v) for k, v in scope["headers"]]
        value = s.dispatch(scope, "inventory")
        assert value["state"] == "denied" and value["inventory"] is None
    assert snapshot(f) == before


def test_missing_acknowledgement_is_not_recovered_from_a_retained_decision(f):
    ref = retained_reference(f, acknowledged=False)
    s = service(f, ref)
    s.reviews.read_decision = lambda *a: pytest.fail("Unacknowledged decision was discovered")
    before = snapshot(f)
    value = observe(s, f)
    entry = value["inventory"]["entries"][0]
    assert entry["state"] == "decision_reference_required" and entry["decision"] is None
    assert entry["reference"]["decision_ciphertext_sha256"] is None
    assert handoff(s, f, ref, value)["state"] == "independent_acceptance_required"
    assert snapshot(f) == before


def test_unregistered_records_are_not_listed_or_adopted_and_change_the_snapshot(f):
    ref = retained_reference(f)
    s = service(f, ref, pin=invented_pin(f, ref))
    old = observe(s, f)
    e.retain(f.sidecar.root / ("9" * 32 + ".receipt"), next(f.sidecar.root.iterdir()).read_bytes())
    before = snapshot(f)
    current = observe(s, f)
    assert len(current["inventory"]["entries"]) == 1
    assert handoff(s, f, ref, old)["state"] == "observation_conflict"
    assert snapshot(f) == before


def test_unexpected_staging_is_retained_without_listing_or_cleanup(f):
    ref = retained_reference(f)
    e.retain(f.sidecar.root / ".pending-invented", b"SYNTHETIC interrupted bytes")
    before = snapshot(f)
    value = service(f, ref).dispatch(f.account.scope("reviewer"), "inventory")
    assert value["state"] == "unverifiable" and value["inventory"] is None
    assert snapshot(f) == before


@pytest.mark.parametrize("field", ["reference_sha256", "selection_sha256", "review_context_sha256", "journal_pins_sha256", "entry_id"])
def test_separately_supplied_destination_pins_cannot_be_filled_or_substituted(f, field):
    ref = retained_reference(f)
    pin = replace(invented_pin(f, ref), **{field: OTHER_ENTRY if field == "entry_id" else "0" * 64})
    s = service(f, ref, pin=pin)
    before = snapshot(f)
    value = handoff(s, f, ref, observe(s, f))
    assert value["state"] == "destination_pin_mismatch" and value["handoff"] is None
    missing = service(f, ref)
    assert handoff(missing, f, ref, observe(missing, f))["state"] == "destination_pin_required"
    assert snapshot(f) == before


def test_changed_source_is_historical_metadata_and_never_handoff_readiness(f):
    ref = retained_reference(f)
    s = service(f, ref, pin=invented_pin(f, ref))
    e.retain(f.account.profile / ".runtime-key-rotation", b"SYNTHETIC maintenance")
    before = snapshot(f)
    observed = observe(s, f)
    assert observed["inventory"]["entries"][0]["state"] == "review_retained_needs_revalidation"
    assert handoff(s, f, ref, observed)["state"] == "independent_acceptance_required"
    assert snapshot(f) == before


def test_destination_expiry_is_not_extended_by_a_fresh_inventory(f):
    ref = retained_reference(f)
    pin = invented_pin(f, ref)
    s = service(f, ref, pin=pin)
    f.account.now = pin.expires_at
    before = snapshot(f)
    assert handoff(s, f, ref, observe(s, f))["state"] == "handoff_expired"
    assert snapshot(f) == before


def test_caller_revocation_between_observations_withholds_all_metadata(f):
    ref = retained_reference(f)
    def checkpoint(_):
        f.account.revoke("reviewer")
    s = service(f, ref, checkpoint=checkpoint)
    records = {p.name: p.read_bytes() for p in f.sidecar.root.iterdir()}
    value = s.dispatch(f.account.scope("reviewer"), "inventory")
    assert value["state"] == "denied" and value["inventory"] is None
    assert records == {p.name: p.read_bytes() for p in f.sidecar.root.iterdir()}


def test_changed_source_between_observations_returns_no_partial_inventory(f):
    ref = retained_reference(f)
    s = service(f, ref, checkpoint=lambda _: setattr(f.account, "now", f.account.now + 301))
    before = snapshot(f)
    value = s.dispatch(f.account.scope("reviewer"), "inventory")
    assert value["state"] == "observation_conflict" and value["inventory"] is None
    assert snapshot(f) == before


def test_exact_registered_versions_are_never_resolved_to_current_or_latest(f):
    ref = retained_reference(f)
    before = snapshot(f)
    for changed in [replace(ref, review_ciphertext_sha256="0" * 64),
                    replace(ref, decision_ciphertext_sha256="0" * 64), replace(ref, selection_id=ALTERNATE)]:
        value = service(f, changed).dispatch(f.account.scope("reviewer"), "inventory")
        assert value["state"] == "unverifiable" and value["inventory"] is None
    assert snapshot(f) == before


def test_inventory_hash_is_bound_to_the_current_actor_session(f):
    ref = retained_reference(f)
    s = service(f, ref, pin=invented_pin(f, ref))
    observed = observe(s, f, "preparer")
    assert handoff(s, f, ref, observed)["state"] == "observation_conflict"


@pytest.mark.parametrize("decision", ["changes_required", "reject"])
def test_negative_independent_decisions_are_retained_without_handoff(f, decision):
    ref = retained_reference(f, decision=decision)
    s = service(f, ref, pin=invented_pin(f, ref))
    before = snapshot(f)
    observed = observe(s, f)
    assert observed["inventory"]["entries"][0]["state"] == decision
    assert handoff(s, f, ref, observed)["state"] == "independent_acceptance_required"
    assert snapshot(f) == before


def test_request_and_execution_budgets_fail_closed(f, monkeypatch):
    ref = retained_reference(f)
    s = service(f, ref)
    before = snapshot(f)
    assert s.dispatch(f.account.scope("reviewer"), "inventory", limit=100)["state"] == "unverifiable"
    monkeypatch.setattr(inventory, "BUDGET_SECONDS", 0)
    value = s.dispatch(f.account.scope("reviewer"), "inventory")
    assert value["state"] == "budget_exhausted" and value["inventory"] is None
    assert snapshot(f) == before


def test_trusted_registry_limits_and_destination_aliases_are_explicit(f):
    ref = retained_reference(f)
    with pytest.raises(ValueError):
        inventory.ReviewInventory(f.service(), {str(i) * 32: ref for i in range(5)}, {})
    with pytest.raises(ValueError):
        inventory.ReviewInventory(f.service(), {ENTRY: ref}, {OTHER_ENTRY: invented_pin(f, ref)})


def test_tampered_acknowledged_ciphertext_is_retained_without_any_metadata(f):
    ref = retained_reference(f)
    path = f.sidecar.root / (ref.review_id + ".receipt")
    path.write_bytes(path.read_bytes()[:-1] + bytes([path.read_bytes()[-1] ^ 1]))
    before = snapshot(f)
    value = service(f, ref).dispatch(f.account.scope("reviewer"), "inventory")
    assert value["state"] == "unverifiable" and value["inventory"] is None
    assert snapshot(f) == before



def test_closed_inventory_test_placement_preserves_every_identity_once():
    import ci_recovery_inventory as placement
    contract = placement.load_contract()
    actual = []
    for lane in placement.COUNTS:
        selected = placement.select(contract, lane, ["tests/test_unrelated.py::test_preserved", *contract.ids])
        assert selected[0] == "tests/test_unrelated.py::test_preserved"
        actual += selected[1:]
    assert sorted(actual) == list(contract.ids) and len(actual) == len(set(actual)) == 26


@pytest.mark.parametrize("fault", ["missing", "overlap", "source", "unknown_lane"])
def test_corrupt_inventory_test_placement_fails_closed(tmp_path, fault):
    import json

    import ci_recovery_inventory as placement
    value = json.loads(placement.MANIFEST.read_text())
    if fault == "missing":
        value["test_ids"].pop()
    elif fault == "overlap":
        value["lanes"]["postgres"][0] = value["lanes"]["capacity"][0]
        value["lanes"]["postgres"].sort()
    elif fault == "source":
        value["source_sha256"] = "0" * 64
    else:
        value["lanes"]["unapproved"] = value["lanes"].pop("capacity")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        placement.load_contract(manifest)
