"""Reject incomplete native evidence and unsafe disposable container wiring."""

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import qualify_receipt_stage as harness  # noqa: E402
from receipt_stage_native_report import CASES, FALSE, validate  # noqa: E402

PIN = "a" * 64
NAME = "lawyer-receipt-native-" + "b" * 16
VOLUMES = {key: NAME + "-" + key for key in ("models", "work")}


def report():
    return {"schema": "receipt-stage-native-packaging-v1", "package_manifest_sha256": PIN,
            "cases": [{"id": name, "state": state, "inspected_before_import": True, "package_imported": state == "verified",
                       "application_or_engine_imports": False, "kernel_write_rejected": state == "verified",
                       "disposable_readiness": "verified" if state == "verified" else "not_checked"} for name, state in CASES.items()],
            "read_only_inventory_exact": True, "distinct_processes": 10, "filesystem": "ext4", "kernel_readonly": True,
            "native_inference_calls": 0, "live_provider_requests": 0, "HTTP_requests": 0,
            "operator_authorization": "unassessed", "key_custody": "unassessed", **dict.fromkeys(FALSE, False)}


def test_complete_packaging_evidence_does_not_grant_operator_authority():
    result = validate(report(), PIN)
    assert result["qualified"] is True
    assert result["operator_authorization"] == "unassessed"
    assert result["production_activation"] is False


def test_checked_in_first_report_pins_current_sources_and_keeps_native_HTTP_open():
    evidence = json.loads((ROOT / "docs/evidence/native-receipt-packaging-2026-10-28.json").read_text())
    assert evidence["status"] == "qualified" and evidence["disposable_volumes_removed"] is True
    assert evidence["production_activation"] is False and len(evidence["source_sha256"]) == 12
    assert "native authenticated HTTP handoff" in evidence["not_qualified"]
    for name, expected in evidence["source_sha256"].items():
        assert name.startswith("scripts/") and hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    result = validate(evidence["native"], evidence["native"]["package_manifest_sha256"])
    assert result["cases"] == 10


@pytest.mark.parametrize("key,value", [
    ("private_case_inputs", True), ("real_trust_confirmed", True), ("production_activation", True),
    ("application_or_engine_imports", True), ("native_inference_calls", 1), ("HTTP_requests", 1),
    ("live_provider_requests", 1), ("read_only_inventory_exact", False), ("kernel_readonly", False),
    ("filesystem", "overlay"), ("distinct_processes", 9), ("key_custody", "approved"),
    ("operator_authorization", "verified"), ("native_inference_calls", False), ("production_activation", 0)])
def test_scope_inflation_or_missing_native_proof_is_rejected(key, value):
    evidence = report()
    evidence[key] = value
    with pytest.raises(ValueError):
        validate(evidence, PIN)


@pytest.mark.parametrize("change", ["missing", "duplicate", "order", "extra", "uninspected", "premature_import", "no_EROFS", "authority"])
def test_frozen_case_inventory_and_preimport_failures_are_mandatory(change):
    evidence = report()
    rows = evidence["cases"]
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows[-1] = copy.deepcopy(rows[-2])
    elif change == "order":
        rows.reverse()
    elif change == "extra":
        rows[0]["unreviewed"] = True
    elif change == "uninspected":
        rows[1]["inspected_before_import"] = False
    elif change == "premature_import":
        rows[1]["package_imported"] = True
    elif change == "no_EROFS":
        rows[0]["kernel_write_rejected"] = False
    else:
        rows[0]["disposable_readiness"] = "production_ready"
    with pytest.raises(ValueError):
        validate(evidence, PIN)


def test_source_pin_is_independently_supplied():
    with pytest.raises(ValueError):
        validate(report(), "c" * 64)
    evidence = report()
    evidence["unreviewed"] = True
    with pytest.raises(ValueError):
        validate(evidence, PIN)


@pytest.mark.parametrize("preparing", [False, True])
def test_kernel_volume_policy_is_explicit_and_preparation_privileges_do_not_reach_runtime(preparing):
    args = harness.arguments("sha256:" + PIN, NAME, VOLUMES, preparing=preparing)
    assert args[args.index("--network") + 1] == "none"
    assert "--read-only" in args and "--publish" not in args and "--env-file" not in args
    assert args[args.index("--user") + 1] == ("0:0" if preparing else "10002:10002")
    mounts = [args[i + 1] for i, value in enumerate(args) if value == "--mount"]
    assert mounts == ["type=volume,src=" + VOLUMES["models"] + ",dst=/models" + ("" if preparing else ",readonly"),
                      "type=volume,src=" + VOLUMES["work"] + ",dst=/work"]
    assert ("--cap-add" in args) is preparing
    assert args[-4:] == ["-I", "-B", "/controller/receipt_stage_native.py", "prepare" if preparing else "run"]


@pytest.mark.parametrize("volumes", [{"models": "existing-client-data", "work": VOLUMES["work"]},
    {"models": NAME + "-models,type=bind", "work": VOLUMES["work"]}, {**VOLUMES, "originals": "existing-client-data"}])
def test_no_existing_private_volume_or_mount_directive_can_be_selected(volumes):
    with pytest.raises(ValueError):
        harness.arguments("sha256:" + PIN, NAME, volumes, preparing=False)


def test_report_validator_does_not_read_environment_or_start_docker(monkeypatch):
    def prohibited(*args, **kwargs):
        raise AssertionError("Native evidence validation must be offline")
    monkeypatch.setattr(harness.subprocess, "run", prohibited)
    assert validate(report(), PIN)["cases"] == 10


def posture(preparing):
    return {"Image": "sha256:" + PIN, "Config": {"User": "0:0" if preparing else "10002:10002"},
            "HostConfig": {"CapAdd": ["CAP_CHOWN", "CAP_DAC_OVERRIDE", "CAP_FOWNER"] if preparing else [],
                           "CapDrop": ["ALL"], "NetworkMode": "none", "ReadonlyRootfs": True,
                           "SecurityOpt": ["no-new-privileges:true"], "NanoCpus": 2_000_000_000,
                           "Privileged": False, "PidMode": "", "IpcMode": "private",
                           "Tmpfs": {"/tmp": "rw,noexec,nosuid,size=32m,mode=1777"},
                           "Memory": 1024**3, "PidsLimit": 64, "PortBindings": {}},
            "Mounts": [{"Name": v, "Destination": "/" + k, "Type": "volume", "RW": preparing or k != "models"}
                       for k, v in VOLUMES.items()]}


@pytest.mark.parametrize("preparing", [False, True])
def test_actual_docker_posture_including_canonical_capability_names(preparing):
    actual = posture(preparing)
    result = harness.posture(actual, VOLUMES, "sha256:" + PIN, preparing=preparing)
    assert result["no_network"] and result["no_host_mounts"]
    assert result["stage_volume_readonly"] is not preparing


@pytest.mark.parametrize("change", ["network", "writable", "root", "capability", "port", "host_mount", "unowned", "RAM", "CPUs", "PIDs"])
def test_unsafe_actual_container_posture_is_rejected_before_start(change):
    actual = posture(False)
    host = actual["HostConfig"]
    if change == "network":
        host["NetworkMode"] = "bridge"
    elif change == "writable":
        actual["Mounts"][0]["RW"] = True
    elif change == "root":
        actual["Config"]["User"] = "0:0"
    elif change == "capability":
        host["CapAdd"] = ["CAP_SYS_ADMIN"]
    elif change == "port":
        host["PortBindings"] = {"8000/tcp": [{"HostPort": "8000"}]}
    elif change == "host_mount":
        actual["Mounts"][0]["Type"] = "bind"
    elif change == "unowned":
        actual["Mounts"][0]["Name"] = "existing-client-documents"
    elif change == "RAM":
        host["Memory"] = 0
    elif change == "CPUs":
        host["NanoCpus"] = 0
    else:
        host["PidsLimit"] = 0
    with pytest.raises(ValueError):
        harness.posture(actual, VOLUMES, "sha256:" + PIN, preparing=False)
