"""Cheap restart evidence contracts. CI never starts Docker or a native listener."""

import copy
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import qualify_native_operator_preview as mounts  # noqa: E402
import qualify_native_preview_restart as harness  # noqa: E402
from native_preview_restart_report import CASES, FALSE, TRUE, plan_sha256, validate  # noqa: E402

PIN = "a" * 64


def report():
    return {"schema": "native-preview-restart-v1", "package_manifest_sha256": PIN,
        "case_plan_sha256": plan_sha256(), "cases": [{"id": k, "state": v} for k, v in CASES.items()],
        "filesystem": "ext4", "processes": 7, "SIGKILL_exitcodes": [-9, -9, -9], "HTTP_requests": 15,
        "native_inference_calls": 0, "provider_requests": 0, "session_replacements": 1,
        "fixture_scope": "invented_accounts_and_encrypted_metadata_only",
        "restart_scope": "forked_workers_controller_retains_fixture_in_memory",
        **dict.fromkeys(TRUE, True), **dict.fromkeys(FALSE, False)}


def test_closed_restart_receipt_qualifies_only_the_native_fixture_subset():
    with patch.object(mounts.subprocess, "run", side_effect=AssertionError("offline only")):
        value = validate(report(), PIN)
    assert value["cases"] == 25 and value["qualified"]
    assert value["real_operator_approval"] is value["production_activation"] is value["legal_review"] is False


@pytest.mark.parametrize("key,value", [
    ("six_stores_exact", False), ("fresh_connection_pools", False), ("all_listeners_closed", False),
    ("same_handoff_and_expiry", False), ("kernel_readonly", False), ("source_inventory_exact", False),
    ("stage_inventory_exact", False), ("listener_loopback_only", False), ("automatic_replay", True),
    ("authority_renewed", True), ("private_case_inputs", True), ("real_operator_approval", True),
    ("production_activation", True), ("legal_review", True), ("external_checksum_channel_verified", True),
    ("processes", 6), ("HTTP_requests", 14), ("SIGKILL_exitcodes", [-9, 0, -9]),
    ("SIGKILL_exitcodes", [-9.0, -9, -9]), ("provider_requests", 1), ("native_inference_calls", False),
    ("session_replacements", 0), ("fixture_scope", "real_operator"), ("restart_scope", "cold_reboot"),
])
def test_scope_inflation_or_incomplete_execution_withholds_qualification(key, value):
    candidate = report()
    candidate[key] = value
    with pytest.raises(ValueError):
        validate(candidate, PIN)


def test_all_interruption_and_fresh_authorization_cases_are_required_in_frozen_order():
    for fault in ("missing", "duplicate", "reorder", "changed_outcome", "unknown_field", "wrong_plan"):
        candidate = copy.deepcopy(report())
        if fault == "missing":
            candidate["cases"].pop()
        elif fault == "duplicate":
            candidate["cases"][-1] = candidate["cases"][0]
        elif fault == "reorder":
            candidate["cases"].reverse()
        elif fault == "changed_outcome":
            candidate["cases"][0]["state"] = "not_run"
        elif fault == "unknown_field":
            candidate["allow_replay"] = True
        else:
            candidate["case_plan_sha256"] = "0" * 64
        with pytest.raises(ValueError):
            validate(candidate, PIN)
    with pytest.raises(ValueError):
        validate(report(), "b" * 64)


def test_additive_entrypoint_retains_the_original_mount_and_privilege_policy():
    name = "lawyer-preview-native-" + "b" * 16
    volumes = {k: name + "-" + k for k in ("host", "stage", "work")}
    for preparing in (False, True):
        previous = mounts.arguments("sha256:" + PIN, name, volumes, preparing=preparing)
        current = harness.arguments("sha256:" + PIN, name, volumes, preparing=preparing)
        assert previous[:-2] == current[:-2] and previous[-1] == current[-1]
        assert current[-2] == "/controller/native_preview_restart.py"
    with pytest.raises(ValueError):
        harness.arguments("sha256:" + PIN, name, {**volumes, "work": "live-client-volume"}, preparing=False)


def test_original_controller_configuration_is_restored_even_after_an_incomplete_campaign():
    fields = ("FILES", "LABEL", "arguments", "plan_sha256", "validate")
    before = {k: getattr(mounts, k) for k in fields}
    def incomplete(_):
        assert mounts.FILES == harness.FILES and mounts.LABEL == "lawyer-native-preview-restart-v1"
        assert mounts.validate is validate and mounts.plan_sha256 is plan_sha256
        raise ValueError("invented failure")
    with patch.object(mounts, "run", side_effect=incomplete), pytest.raises(ValueError):
        harness.run("invented-public-image")
    assert before == {k: getattr(mounts, k) for k in fields}


def test_checked_native_restart_report_preserves_sources_and_existing_evidence():
    value = json.loads((ROOT / "docs/evidence/native-preview-restart-2026-11-03.json").read_bytes())
    assert value["status"] == "qualified" and value["schema"] == "native-preview-restart-campaign-v1"
    assert value["disposable_volumes_removed"] and value["owned_containers_removed"]
    assert value["generated_image_tags_removed"] and value["production_activation"] is False
    assert "cold descriptor reload or host reboot" in value["not_qualified"]
    for path, expected in value["source_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    assert validate(value["native"], value["native"]["package_manifest_sha256"])["cases"] == 25
    prior = ROOT / "docs/evidence/native-operator-preview-2026-11-03.json"
    assert hashlib.sha256(prior.read_bytes()).hexdigest() == value["prior_native_report_sha256"]
