"""Offline evidence and wiring rejection tests; Docker qualification is opt-in."""

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import qualify_receipt_http as harness  # noqa: E402
from receipt_http_report import CASES, FALSE, TRUE, validate  # noqa: E402

PIN, CONTROLLER = "a" * 64, "b" * 64
NAME = "lawyer-receipt-native-" + "c" * 16
VOLUMES = {k: NAME + "-" + k for k in ("models", "work", "anchors", "backups")}


def report():
    rows = [{"id": ident, "status": status, "state": state, "outcome": outcome,
             "controller_reads": 0 if status != 200 or ident == "H01_readiness" else 2} for ident, status, state, outcome in CASES]
    return {"schema": "native-receipt-http-v1", "receipt_manifest_sha256": PIN, "controller_manifest_sha256": CONTROLLER,
            "filesystem": "ext4", "key_custody": "unassessed", "operator_appointments": "unassessed",
            **dict.fromkeys(TRUE, True), **dict.fromkeys(FALSE, False), "live_provider_requests": 0, "native_inference_calls": 0,
            "modes": [{"mode": mode, "cases": copy.deepcopy(rows), "distinct_processes": 4, "loopback_servers": 4,
                       "receipt_worker_restarts": 1, "receipt_HTTP_requests": 15, "controller_reads": 12,
                       "campaign_controller_requests": 52 if mode == "retirement" else 73, "source_and_ciphertext_exact": True,
                       "four_histories_exact_across_reads": True, "negative_requests_no_controller_io": True}
                      for mode in ("retirement", "rollback")]}


def test_complete_native_evidence_retains_authority_limits():
    assert validate(report(), PIN, CONTROLLER) == {"qualified_modes": 2, "frozen_HTTP_cases": 30,
                                                  "actual_receipt_HTTP_requests": 30, "production_activation": False}


@pytest.mark.parametrize("field", sorted(TRUE | FALSE))
def test_missing_or_inflated_security_and_scope_proof_is_rejected(field):
    value = report()
    value[field] = False if field in TRUE else True
    with pytest.raises(ValueError):
        validate(value, PIN, CONTROLLER)


@pytest.mark.parametrize("field,value", [("distinct_processes", 3), ("loopback_servers", True),
    ("receipt_worker_restarts", 0), ("receipt_HTTP_requests", 14), ("controller_reads", 13),
    ("campaign_controller_requests", 53), ("source_and_ciphertext_exact", False),
    ("four_histories_exact_across_reads", False), ("negative_requests_no_controller_io", False)])
def test_process_reuse_missing_restart_partial_execution_and_state_changes_do_not_qualify(field, value):
    evidence = report()
    evidence["modes"][0][field] = value
    with pytest.raises(ValueError):
        validate(evidence, PIN, CONTROLLER)


@pytest.mark.parametrize("change", ["missing", "duplicate", "order", "denial_io", "no_fresh_io", "wrong_state", "wrong_outcome", "extra"])
def test_frozen_matrix_and_per_request_native_IO_are_required(change):
    evidence = report()
    rows = evidence["modes"][0]["cases"]
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows[-1] = rows[-2]
    elif change == "order":
        rows.reverse()
    elif change == "denial_io":
        rows[3]["controller_reads"] = 2
    elif change == "no_fresh_io":
        rows[2]["controller_reads"] = 0
    elif change == "wrong_state":
        rows[-1]["state"] = "reconciled_metadata"
    elif change == "wrong_outcome":
        rows[10]["outcome"] = "changed_metadata"
    else:
        rows[0]["unreviewed"] = True
    with pytest.raises(ValueError):
        validate(evidence, PIN, CONTROLLER)


@pytest.mark.parametrize("change", ["receipt_pin", "controller_pin", "custody", "appointments", "filesystem", "mode", "extra"])
def test_independent_pins_and_unassessed_real_enrollment_remain_mandatory(change):
    value = report()
    if change == "receipt_pin":
        value["receipt_manifest_sha256"] = "d" * 64
    elif change == "controller_pin":
        value["controller_manifest_sha256"] = "d" * 64
    elif change == "custody":
        value["key_custody"] = "approved"
    elif change == "appointments":
        value["operator_appointments"] = "approved"
    elif change == "filesystem":
        value["filesystem"] = "overlay"
    elif change == "mode":
        value["modes"].reverse()
    else:
        value["unreviewed"] = True
    with pytest.raises(ValueError):
        validate(value, PIN, CONTROLLER)


def test_container_wiring_extends_existing_isolation_without_host_mounts():
    args = harness.arguments("sha256:" + PIN, NAME, VOLUMES, preparing=False)
    mounts = [args[i + 1] for i, x in enumerate(args) if x == "--mount"]
    assert len(mounts) == 4 and all(x.startswith("type=volume,src=" + NAME) for x in mounts)
    assert args[args.index("--network") + 1] == "none" and args[args.index("--user") + 1] == "10002:10002"
    assert "--cap-add" not in args and "--read-only" in args
    assert "type=volume,src=" + VOLUMES["models"] + ",dst=/models,readonly" in mounts
    assert args[-2:] == ["/controller/receipt_http_native.py", "run"]


@pytest.mark.parametrize("volumes", [{**VOLUMES, "anchors": "existing-secrets"},
                                    {**VOLUMES, "backups": NAME + "-backups,type=bind"},
                                    {**VOLUMES, "originals": "existing-documents"}])
def test_existing_private_volume_selection_is_rejected(volumes):
    with pytest.raises(ValueError):
        harness.arguments("sha256:" + PIN, NAME, volumes, preparing=False)


def test_first_report_binds_current_public_sources_and_preserves_prior_package_gate():
    value = json.loads((ROOT / "docs/evidence/native-receipt-http-2026-10-28.json").read_text())
    assert value["status"] == "qualified" and value["disposable_volumes_removed"] is True
    assert value["production_activation"] is False and len(value["source_sha256"]) >= 400
    for name, expected in value["source_sha256"].items():
        assert name.startswith(("scripts/", "backend/app/", "deploy/fixtures/"))
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    native = value["native"]
    assert validate(native, native["receipt_manifest_sha256"], native["controller_manifest_sha256"])["frozen_HTTP_cases"] == 30
    prior = json.loads((ROOT / "docs/evidence/native-receipt-packaging-2026-10-28.json").read_text())
    assert prior["native"]["package_manifest_sha256"] == native["receipt_manifest_sha256"]
    assert "in-flight session revocation" in value["not_qualified"]
