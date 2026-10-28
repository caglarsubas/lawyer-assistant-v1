"""Opt-in native packaging campaign; fresh labelled volumes, no private host mounts."""

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

import build_receipt_stage
from controller_stage_manifest import digest, strict
from receipt_stage_native_report import validate

ROOT = Path(__file__).resolve().parents[1]
LABEL = "lawyer-receipt-native-packaging-v1"
FILES = ("receipt_stage_native.py", "receipt_stage_native_report.py", "receipt_stage_manifest.py", "controller_stage_manifest.py")


def command(argv, timeout=90):
    result = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError("Isolated native command failed; no runtime details emitted")
    return result.stdout


def arguments(image, name, volumes, *, preparing):
    if (set(volumes) != {"models", "work"} or volumes != {k: name + "-" + k for k in ("models", "work")}
            or not re.fullmatch(r"lawyer-receipt-native-[0-9a-f]{16}", name)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", image)):
        raise ValueError("Generated campaign identities required")
    args = ["docker", "create", "--name", name + ("-prepare" if preparing else "-run"),
            "--label", "qualification=" + LABEL, "--label", "campaign=" + name,
            "--network", "none", "--read-only", "--user", "0:0" if preparing else "10002:10002",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--cpus", "2", "--memory", "1g",
            "--pids-limit", "64", "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m,mode=1777"]
    if preparing:
        for cap in ("CHOWN", "DAC_OVERRIDE", "FOWNER"):
            args += ["--cap-add", cap]
    for target, volume in sorted(volumes.items()):
        args += ["--mount", "type=volume,src=" + volume + ",dst=/" + target + (",readonly" if target == "models" and not preparing else "")]
    return [*args, "--entrypoint", "/app/backend/.venv/bin/python", image, "-I", "-B", "/controller/receipt_stage_native.py",
            "prepare" if preparing else "run"]


def posture(value, volumes, image, *, preparing):
    host, config, mounts = value["HostConfig"], value["Config"], value["Mounts"]
    caps = {c.removeprefix("CAP_") for c in host.get("CapAdd") or []}
    if (value["Image"] != image or config["User"] != ("0:0" if preparing else "10002:10002")
            or host["NetworkMode"] != "none" or host["ReadonlyRootfs"] is not True or host["CapDrop"] != ["ALL"]
            or caps != ({"CHOWN", "DAC_OVERRIDE", "FOWNER"} if preparing else set())
            or host["SecurityOpt"] not in (["no-new-privileges"], ["no-new-privileges:true"])
            or host["Privileged"] is not False or host["PidMode"] or host["IpcMode"] != "private"
            or host["Tmpfs"] != {"/tmp": "rw,noexec,nosuid,size=32m,mode=1777"}
            or host["NanoCpus"] != 2_000_000_000 or host["Memory"] != 1024**3 or host["PidsLimit"] != 64
            or host.get("PortBindings") or len(mounts) != 2
            or {(m["Name"], m["Destination"], m["RW"]) for m in mounts if m["Type"] == "volume"}
            != {(v, "/" + k, preparing or k != "models") for k, v in volumes.items()}):
        raise ValueError("Container isolation differs from frozen policy")
    return {"no_network": True, "no_host_ports": True, "no_host_mounts": True, "root_filesystem_readonly": True,
            "nonroot_runtime": not preparing, "stage_volume_readonly": not preparing, "two_CPUs": True,
            "memory_bytes": 1024**3, "pids_limit": 64}


def run(base_image):
    # Read only the image API in memory; never emit raw configuration.
    base = strict(command(["docker", "image", "inspect", base_image]))[0]
    allowed_env = {"PATH", "LANG", "GPG_KEY", "PYTHON_VERSION", "PYTHON_SHA256", "PYTHONDONTWRITEBYTECODE",
                   "PYTHONUNBUFFERED", "UV_LINK_MODE", "PYTHON_PIP_VERSION", "PYTHON_GET_PIP_URL", "PYTHON_GET_PIP_SHA256"}
    if base["Config"].get("OnBuild") or any(s.partition("=")[0] not in allowed_env for s in base["Config"].get("Env", [])):
        raise ValueError("Public dependency image without runtime configuration required")
    name, containers, volumes = "lawyer-receipt-native-" + secrets.token_hex(8), [], {}
    base_tag = None
    try:
        with tempfile.TemporaryDirectory(prefix="lawyer-receipt-public-") as directory:
            context = Path(directory).resolve()
            built = build_receipt_stage.build(context / "receipt-export")
            controller = context / "controller"
            controller.mkdir()
            hashes = {}
            for file in FILES:
                source = ROOT / "scripts" / file
                hashes["scripts/" + file] = digest(source.read_bytes())
                shutil.copyfile(source, controller / file)
                (controller / file).chmod(0o644)
            for file in ("qualify_receipt_stage.py", "build_receipt_stage.py"):
                hashes["scripts/" + file] = digest((ROOT / "scripts" / file).read_bytes())
            (controller / "operator-packet.json").write_text(json.dumps({"approved_manifest_sha256": built["manifest_sha256"], "production_activation": False}))
            (controller / "operator-packet.json").chmod(0o644)
            # BuildKit resolves a local tag, not a bare image ID in FROM. Generate
            # a private-to-this-campaign tag and verify its immutable ID again.
            base_tag = name + ":dependencies"
            command(["docker", "image", "tag", base["Id"], base_tag])
            dockerfile = "FROM " + base_tag + "\nCOPY --chmod=755 controller /controller\nCOPY receipt-export /receipt-export\n"
            (context / "Dockerfile").write_text(dockerfile)
            tag = name + ":qualification"
            command(["docker", "build", "--network", "none", "--pull=false", "--tag", tag, str(context)], 180)
            if strict(command(["docker", "image", "inspect", base_tag]))[0]["Id"] != base["Id"]:
                raise ValueError("Dependency image changed during packaging")
            image = strict(command(["docker", "image", "inspect", tag]))[0]["Id"]
            for key in ("models", "work"):
                volume = name + "-" + key
                if command(["docker", "volume", "ls", "--quiet", "--filter", "name=^" + volume + "$"]).strip():
                    raise ValueError("Fresh generated volume name required")
                command(["docker", "volume", "create", "--label", "qualification=" + LABEL, "--label", "campaign=" + name, volume])
                volumes[key] = volume
            proofs = []
            for preparing in (True, False):
                container = command(arguments(image, name, volumes, preparing=preparing)).decode().strip()
                containers.append(container)
                actual = strict(command(["docker", "inspect", container]))[0]
                proofs.append(posture(actual, volumes, image, preparing=preparing))
                output = strict(command(["docker", "start", "--attach", container], 120))
                state = strict(command(["docker", "inspect", container]))[0]["State"]
                if state["Running"] or state["ExitCode"] != 0 or state["OOMKilled"]:
                    raise ValueError("Native process did not exit cleanly")
                if preparing and output != {"prepared": True, "filesystem": "ext4", "private_case_inputs": False}:
                    raise ValueError("Fresh volume preparation failed")
            gate = validate(output, built["manifest_sha256"])
            report = {"schema": "receipt-stage-native-campaign-v1", "status": "qualified", "scope": gate["scope"],
                      "source_sha256": {**built["manifest"]["source_sha256"], **hashes}, "base_dependency_image": base["Id"],
                      "qualification_image": image, "posture": proofs, "native": output, "production_activation": False,
                      "not_qualified": ["native authenticated HTTP handoff", "operator appointments and key custody", "real provider or inference",
                                        "production deployment", "legal or owner review"]}
    finally:
        # Generated resources only. No reused volume, production service or global prune.
        for container in reversed(containers):
            command(["docker", "rm", "--force", container])
        for volume in volumes.values():
            owned = strict(command(["docker", "volume", "inspect", volume]))[0]
            if owned["Labels"].get("campaign") != name or owned["Labels"].get("qualification") != LABEL:
                raise ValueError("Cleanup ownership differs")
            command(["docker", "volume", "rm", volume])
        if base_tag is not None:
            owned = strict(command(["docker", "image", "inspect", base_tag]))[0]
            if owned["Id"] != base["Id"]:
                raise ValueError("Generated dependency tag changed")
            command(["docker", "image", "rm", base_tag])
    report["disposable_volumes_removed"] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-image", required=True, help="Already loaded public dependency image; no pull")
    parser.add_argument("--output", required=True, type=Path, help="New owner-only aggregate JSON report")
    args = parser.parse_args()
    os.umask(0o077)
    with args.output.open("x") as stream:
        stream.write('{"status":"incomplete"}\n')
    try:
        value = run(args.base_image)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
        raise SystemExit("Native packaging qualification failed; activation remains disabled") from None
    args.output.write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps({"qualified": True, "cases": len(value["native"]["cases"]), "production_activation": False}))


if __name__ == "__main__":
    main()
