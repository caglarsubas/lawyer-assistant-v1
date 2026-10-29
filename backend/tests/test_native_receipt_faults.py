"""Frozen failure evidence and private barrier controls; Docker remains opt-in."""

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import qualify_receipt_faults as harness  # noqa: E402
from receipt_fault_probe import Probe  # noqa: E402
from receipt_fault_report import CASES, COUNTS, FALSE, PRESERVED, TRUE, validate  # noqa: E402

PIN, CONTROLLER = "a" * 64, "b" * 64


def report():
    rows = [{"id": ident, "status": status, "state": state, "controller_reads": reads} for ident, status, state, reads in CASES]
    return {"schema": "native-receipt-fault-v1", "receipt_manifest_sha256": PIN, "controller_manifest_sha256": CONTROLLER,
            "filesystem": "ext4", "key_custody": "unassessed", "operator_appointments": "unassessed",
            **dict.fromkeys(TRUE, True), **dict.fromkeys(FALSE, False), "live_provider_requests": 0, "native_inference_calls": 0,
            "modes": [{"mode": mode, "cases": copy.deepcopy(rows), **COUNTS, **dict.fromkeys(PRESERVED, True),
                       "campaign_controller_requests": 48 if mode == "retirement" else 66} for mode in ("retirement", "rollback")]}


def test_complete_frozen_matrix_does_not_claim_power_loss_or_real_enrollment():
    assert validate(report(), PIN, CONTROLLER) == {"qualified_modes": 2, "frozen_HTTP_cases": 34,
        "intentional_SIGKILL_exits": 6, "production_activation": False}


@pytest.mark.parametrize("field", sorted(TRUE | FALSE))
def test_scope_inflation_or_missing_required_native_proof_rejects(field):
    value = report()
    value[field] = False if field in TRUE else True
    with pytest.raises(ValueError):
        validate(value, PIN, CONTROLLER)


@pytest.mark.parametrize("field", sorted(COUNTS | dict.fromkeys(PRESERVED)))
def test_process_reuse_missing_kills_or_history_changes_reject(field):
    value = report()
    value["modes"][0][field] = False if field in PRESERVED else 0
    with pytest.raises(ValueError):
        validate(value, PIN, CONTROLLER)


@pytest.mark.parametrize("change", ["missing", "order", "status", "acknowledged_kill", "stale_read", "disclosure", "extra"])
def test_partial_or_misreported_failure_outcomes_reject(change):
    value = report()
    rows = value["modes"][0]["cases"]
    if change == "missing":
        rows.pop()
    elif change == "order":
        rows.reverse()
    elif change == "status":
        rows[1]["status"] = 200
    elif change == "acknowledged_kill":
        rows[7]["status"] = 200
    elif change == "stale_read":
        rows[2]["controller_reads"] = 0
    elif change == "disclosure":
        rows[11]["state"] = "pending_anchors"
    else:
        rows[0]["new_authority"] = True
    with pytest.raises(ValueError):
        validate(value, PIN, CONTROLLER)


@pytest.mark.parametrize("change", ["receipt_pin", "controller_pin", "custody", "appointments", "filesystem", "mode", "count_bool", "extra"])
def test_independent_binding_closed_counts_and_pending_authority_remain_required(change):
    value = report()
    if change in {"receipt_pin", "controller_pin"}:
        value["receipt_manifest_sha256" if change == "receipt_pin" else "controller_manifest_sha256"] = "c" * 64
    elif change == "custody":
        value["key_custody"] = "approved"
    elif change == "appointments":
        value["operator_appointments"] = "approved"
    elif change == "filesystem":
        value["filesystem"] = "overlay"
    elif change == "mode":
        value["modes"].reverse()
    elif change == "count_bool":
        value["live_provider_requests"] = False
    else:
        value["unreviewed"] = True
    with pytest.raises(ValueError):
        validate(value, PIN, CONTROLLER)


class Pipe:
    def __init__(self, ack):
        self.ack, self.events, self.polls = ack, [], []

    def send(self, event):
        self.events.append(event)

    def poll(self, seconds):
        self.polls.append(seconds)
        return self.ack is not None

    def recv(self):
        return self.ack


def test_barrier_is_one_shot_matching_and_bounded():
    pipe = Pipe({"resume": True})
    probe = Probe("after_read_1", pipe)
    probe.pause("after_read_2")
    assert not pipe.events
    probe.pause("after_read_1", 1)
    probe.pause("after_read_1", 1)
    assert probe.fired and len(pipe.events) == 1 and pipe.polls == [5]
    assert set(pipe.events[0]) == {"pid", "checkpoint", "controller_reads"}


@pytest.mark.parametrize("ack", [None, {}, {"resume": 1}, {"resume": False}, {"resume": True, "secret": "unexpected"}])
def test_missing_ambiguous_or_extra_private_acknowledgement_rejects(ack):
    probe = Probe("after_publish", Pipe(ack))
    with pytest.raises(ValueError):
        probe.pause("after_publish")


def test_docker_has_four_disposable_volumes_and_no_new_network_or_host_fault_endpoint():
    name = "lawyer-receipt-native-" + "d" * 16
    args = harness.arguments("sha256:" + PIN, name, {k: name + "-" + k for k in ("models", "work", "anchors", "backups")}, preparing=False)
    assert args[-2:] == ["/controller/receipt_fault_native.py", "run"]
    assert args[args.index("--network") + 1] == "none" and "--publish" not in args
    assert args[args.index("--user") + 1] == "10002:10002" and "--cap-add" not in args
    assert sum(x == "--mount" for x in args) == 4


def test_source_bound_native_evidence_preserves_previous_reports_and_limits():
    value = json.loads((ROOT / "docs/evidence/native-receipt-faults-2026-10-29.json").read_text())
    assert value["status"] == "qualified" and value["disposable_volumes_removed"] is True
    for name, expected in value["source_sha256"].items():
        assert name.startswith(("scripts/", "backend/app/", "deploy/fixtures/"))
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    native = value["native"]
    assert validate(native, native["receipt_manifest_sha256"], native["controller_manifest_sha256"])["frozen_HTTP_cases"] == 34
    prior = json.loads((ROOT / "docs/evidence/native-receipt-http-2026-10-28.json").read_text())
    assert native["receipt_manifest_sha256"] == prior["native"]["receipt_manifest_sha256"]
    assert native["controller_manifest_sha256"] == prior["native"]["controller_manifest_sha256"]
    assert "power-loss durability" in value["not_qualified"] and "automatic orphan repair" in value["not_qualified"]
