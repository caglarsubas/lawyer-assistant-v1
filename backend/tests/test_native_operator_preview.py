"""Offline native-campaign contracts; opt-in Docker is never started by CI."""

import copy
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import qualify_native_operator_preview as harness  # noqa: E402
from native_operator_preview_report import CASES, FALSE, plan_sha256, validate  # noqa: E402

PIN = "a" * 64
NAME = "lawyer-preview-native-" + "b" * 16
VOLUMES = {k: NAME + "-" + k for k in ("host", "stage", "work")}


def report():
    return {"schema": "native-operator-preview-v1", "package_manifest_sha256": PIN, "case_plan_sha256": plan_sha256(),
        "cases": [{"id": k, "state": v} for k, v in CASES.items()], "filesystem": "ext4", "kernel_readonly": True,
        "source_inventory_exact": True, "stage_inventory_exact": True, "four_histories_exact": True,
        "separate_server_and_client": True, "listener_loopback_only": True, "listener_closed": True,
        "native_inference_calls": 0, "provider_requests": 0, "HTTP_requests": 12,
        "clock_scope": "controlled_disposable_clock", **dict.fromkeys(FALSE, False)}


def test_complete_native_evidence_retains_narrow_scope_without_starting_docker():
    with patch.object(harness.subprocess, "run", side_effect=AssertionError("offline only")):
        result = validate(report(), PIN)
    assert result["qualified"] and result["cases"] == 22
    assert result["real_operator_approval"] is result["production_activation"] is result["legal_review"] is False


@pytest.mark.parametrize("key,value", [("kernel_readonly", False), ("four_histories_exact", False),
    ("source_inventory_exact", False), ("stage_inventory_exact", False), ("separate_server_and_client", False),
    ("listener_loopback_only", False), ("listener_closed", False), ("private_case_inputs", True),
    ("real_operator_approval", True), ("production_activation", True), ("legal_review", True),
    ("HTTP_requests", 11), ("native_inference_calls", False), ("provider_requests", 1),
    ("filesystem", "overlay"), ("clock_scope", "real_time_qualified")])
def test_scope_inflation_and_incomplete_native_receipts_fail_closed(key, value):
    candidate = report()
    candidate[key] = value
    with pytest.raises(ValueError):
        validate(candidate, PIN)


def test_case_inventory_and_independent_pin_are_closed():
    for kind in ("missing", "duplicate", "order", "extra_field", "wrong_plan", "wrong_state"):
        candidate = report()
        if kind == "missing":
            candidate["cases"].pop()
        elif kind == "duplicate":
            candidate["cases"][-1] = copy.deepcopy(candidate["cases"][0])
        elif kind == "order":
            candidate["cases"].reverse()
        elif kind == "extra_field":
            candidate["allow_incomplete"] = True
        elif kind == "wrong_plan":
            candidate["case_plan_sha256"] = "0" * 64
        else:
            candidate["cases"][1]["state"] = "verified"
        with pytest.raises(ValueError):
            validate(candidate, PIN)
    with pytest.raises(ValueError):
        validate(report(), "c" * 64)


@pytest.mark.parametrize("preparing", [False, True])
def test_container_mounts_have_no_host_or_client_inputs_and_no_runtime_preparation_capabilities(preparing):
    args = harness.arguments("sha256:" + PIN, NAME, VOLUMES, preparing=preparing)
    assert args[args.index("--network") + 1] == "none" and "--read-only" in args
    assert not {"--publish", "--env-file", "--env", "--privileged"} & set(args)
    assert args[args.index("--user") + 1] == ("0:0" if preparing else "10002:10002")
    mounts = [args[i + 1] for i, v in enumerate(args) if v == "--mount"]
    assert mounts == ["type=volume,src=" + v + ",dst=/" + k + (",readonly" if not preparing and k != "work" else "")
                      for k, v in VOLUMES.items()]
    assert ("--cap-add" in args) is preparing
    assert args[-4:] == ["-I", "-B", "/controller/native_operator_preview.py", "prepare" if preparing else "run"]


def test_existing_or_injected_volume_selectors_are_rejected():
    for values in ({**VOLUMES, "work": "existing-client-data"}, {**VOLUMES, "host": NAME + "-host,type=bind"},
                   {**VOLUMES, "other": NAME + "-other"}):
        with pytest.raises(ValueError):
            harness.arguments("sha256:" + PIN, NAME, values, preparing=False)


def test_actual_posture_must_match_all_mount_and_kernel_controls():
    value = {"Image": "sha256:" + PIN, "Config": {"User": "10002:10002", "WorkingDir": "/work"},
        "HostConfig": {"CapAdd": [], "CapDrop": ["ALL"], "NetworkMode": "none", "ReadonlyRootfs": True,
            "SecurityOpt": ["no-new-privileges:true"], "Privileged": False, "PidMode": "", "IpcMode": "private",
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,size=32m,mode=1777"}, "NanoCpus": 2_000_000_000,
            "Memory": 1024**3, "PidsLimit": 64, "PortBindings": {}},
        "Mounts": [{"Name": v, "Destination": "/" + k, "Type": "volume", "RW": k == "work"} for k, v in VOLUMES.items()]}
    assert harness.posture(value, VOLUMES, "sha256:" + PIN, preparing=False)["host_and_stage_readonly"]
    for mutate in (lambda x: x["Mounts"][0].update(RW=True), lambda x: x["Mounts"][0].update(Type="bind"),
                   lambda x: x["HostConfig"].update(NetworkMode="bridge"), lambda x: x["HostConfig"].update(Privileged=True)):
        wrong = copy.deepcopy(value)
        mutate(wrong)
        with pytest.raises(ValueError):
            harness.posture(wrong, VOLUMES, "sha256:" + PIN, preparing=False)


def test_checked_native_report_pins_sources_and_preserves_unqualified_operator_and_legal_gates():
    value = json.loads((ROOT / "docs/evidence/native-operator-preview-2026-11-03.json").read_bytes())
    assert value["status"] == "qualified" and value["disposable_volumes_removed"]
    assert value["owned_containers_removed"] and value["generated_image_tags_removed"]
    assert value["production_activation"] is False
    assert "legal or owner review" in value["not_qualified"]
    for path, expected in value["source_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    assert validate(value["native"], value["native"]["package_manifest_sha256"])["cases"] == 22
