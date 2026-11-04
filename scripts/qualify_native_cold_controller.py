"""Additive opt-in cold campaign using the retained mount/isolation controller."""

import argparse
import json
import os
from pathlib import Path

import qualify_native_operator_preview as mounts
from native_cold_controller_report import plan_sha256, validate

FILES = (*mounts.FILES, "native_preview_restart.py", "native_preview_restart_report.py",
         "native_cold_controller.py", "native_cold_controller_report.py", "operator_cold_recovery.py", "cold_controller_fixture.py")
mounts_arguments = mounts.arguments


def arguments(image, name, volumes, *, preparing):
    args = mounts_arguments(image, name, volumes, preparing=preparing)
    if args[-2] != "/controller/native_operator_preview.py":
        raise ValueError("Exact retained entrypoint required")
    args[-2] = "/controller/native_cold_controller.py"
    return args


def run(base_image):
    previous = {k: getattr(mounts, k) for k in ("FILES", "LABEL", "arguments", "plan_sha256", "validate")}
    try:
        mounts.FILES, mounts.LABEL = FILES, "lawyer-native-cold-controller-v1"
        mounts.arguments, mounts.plan_sha256, mounts.validate = arguments, plan_sha256, validate
        result = mounts.run(base_image)
        result["schema"] = "native-cold-controller-campaign-v1"
        result["not_qualified"].extend(["host reboot or changed volume inode", "joint account-store rollback"])
        return result
    finally:
        for key, value in previous.items():
            setattr(mounts, key, value)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-image", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    with args.output.open("x") as stream:
        stream.write('{"status":"incomplete"}\n')
    try:
        report = run(args.base_image)
    except (OSError, ValueError, KeyError, RuntimeError, mounts.subprocess.SubprocessError) as exc:
        args.output.write_text(json.dumps({"status": "incomplete", "error_type": type(exc).__name__,
                                          "diagnostic": mounts.LAST_FAILURE}, indent=2) + "\n")
        raise SystemExit("Native cold qualification failed; activation disabled") from None
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"qualified": True, "native_cases": len(report["native"]["cases"]), "production_activation": False}))
