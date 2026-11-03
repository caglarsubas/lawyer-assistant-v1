"""Opt-in frozen native preview campaign; public source and generated volumes only."""

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

import build_operator_preview
from controller_stage_manifest import digest, strict
from native_operator_preview_report import plan_sha256, validate

ROOT = Path(__file__).resolve().parents[1]
LABEL = "lawyer-native-operator-preview-v1"
FILES = ("native_operator_preview.py", "native_operator_preview_report.py", "controller_stage_manifest.py")
ALLOWED_ENV = {"PATH", "LANG", "GPG_KEY", "PYTHON_VERSION", "PYTHON_SHA256", "PYTHONDONTWRITEBYTECODE",
               "PYTHONUNBUFFERED", "UV_LINK_MODE", "PYTHON_PIP_VERSION", "PYTHON_GET_PIP_URL", "PYTHON_GET_PIP_SHA256"}
LAST_FAILURE = None


def command(args, timeout=90):
    global LAST_FAILURE
    result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        LAST_FAILURE = {"operation": args[1], "stdout_sha256": digest(result.stdout), "stderr_sha256": digest(result.stderr)}
        try:
            parsed = strict(result.stdout)
            if (isinstance(parsed, dict) and set(parsed) == {"schema", "phase", "error_type", "frames"}
                    and parsed["schema"] == "native-preview-failure-v1"):
                LAST_FAILURE["probe"] = parsed
        except ValueError:
            pass
        raise RuntimeError("Native preview command failed; activation disabled")
    return result.stdout


def public_paths():
    tracked = set(command(["git", "-C", str(ROOT), "ls-files"]).decode().splitlines())
    paths = {n for n in tracked if (n.startswith(("scripts/", "backend/app/", "backend/tests/")) and n.endswith(".py"))
             or (n.startswith(("ontology/", "deploy/fixtures/", "qualification/")) and n.endswith((".py", ".ttl", ".json", ".md", ".txt", ".csv")))}
    paths |= {"backend/pyproject.toml", "backend/uv.lock"}
    if not {"scripts/" + name for name in FILES} <= paths or len(paths) > 1600:
        raise ValueError("Tracked bounded public input inventory required")
    if any((ROOT / n).is_symlink() or not (ROOT / n).is_file() for n in paths):
        raise ValueError("Regular public source files required")
    if sum((ROOT / n).stat().st_size for n in paths) > 32 * 1024**2:
        raise ValueError("Public input byte budget exceeded")
    return sorted(paths)


def arguments(image, name, volumes, *, preparing):
    if (not re.fullmatch(r"sha256:[0-9a-f]{64}", image)
            or not re.fullmatch(r"lawyer-preview-native-[0-9a-f]{16}", name)
            or volumes != {k: name + "-" + k for k in ("host", "stage", "work")}
            or type(preparing) is not bool):
        raise ValueError("Generated campaign identities required")
    args = ["docker", "create", "--name", name + ("-prepare" if preparing else "-run"),
        "--label", "qualification=" + LABEL, "--label", "campaign=" + name,
        "--network", "none", "--read-only", "--user", "0:0" if preparing else "10002:10002",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--cpus", "2", "--memory", "1g",
        "--pids-limit", "64", "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m,mode=1777", "--workdir", "/work"]
    if preparing:
        for capability in ("CHOWN", "DAC_OVERRIDE", "FOWNER"):
            args += ["--cap-add", capability]
    for key, volume in volumes.items():
        args += ["--mount", "type=volume,src=" + volume + ",dst=/" + key + (",readonly" if not preparing and key != "work" else "")]
    return [*args, "--entrypoint", "/app/backend/.venv/bin/python", image, "-I", "-B",
            "/controller/native_operator_preview.py", "prepare" if preparing else "run"]


def posture(value, volumes, image, *, preparing):
    host, config, mounts = value["HostConfig"], value["Config"], value["Mounts"]
    caps = {c.removeprefix("CAP_") for c in host.get("CapAdd") or []}
    if (value["Image"] != image or config["User"] != ("0:0" if preparing else "10002:10002")
            or config["WorkingDir"] != "/work" or host["NetworkMode"] != "none" or host["ReadonlyRootfs"] is not True
            or host["CapDrop"] != ["ALL"] or caps != ({"CHOWN", "DAC_OVERRIDE", "FOWNER"} if preparing else set())
            or host["SecurityOpt"] not in (["no-new-privileges"], ["no-new-privileges:true"])
            or host["Privileged"] is not False or host["PidMode"] or host["IpcMode"] != "private"
            or host["Tmpfs"] != {"/tmp": "rw,noexec,nosuid,size=32m,mode=1777"}
            or host["NanoCpus"] != 2_000_000_000 or host["Memory"] != 1024**3 or host["PidsLimit"] != 64
            or host.get("PortBindings") or len(mounts) != 3
            or {(m["Name"], m["Destination"], m["RW"]) for m in mounts if m["Type"] == "volume"}
            != {(v, "/" + k, preparing or k == "work") for k, v in volumes.items()}):
        raise ValueError("Native isolation differs from frozen policy")
    return {"no_egress": True, "no_host_ports": True, "no_host_mounts": True, "nonroot_runtime": not preparing,
            "root_filesystem_readonly": True, "host_and_stage_readonly": not preparing, "two_CPUs": True,
            "memory_bytes": 1024**3, "pids_limit": 64}


def run(base_image):
    base = strict(command(["docker", "image", "inspect", base_image]))[0]
    if (base["Config"].get("OnBuild") or base["Config"].get("Volumes")
            or any(s.partition("=")[0] not in ALLOWED_ENV for s in base["Config"].get("Env", []))):
        raise ValueError("Public dependency image without runtime configuration required")
    paths = public_paths()
    hashes = {n: digest((ROOT / n).read_bytes()) for n in paths}
    hashes["scripts/qualify_native_operator_preview.py"] = digest(Path(__file__).read_bytes())
    name = "lawyer-preview-native-" + secrets.token_hex(8)
    volumes, containers, tags = {}, [], {}
    report = None
    try:
        with tempfile.TemporaryDirectory(prefix="lawyer-preview-public-") as temporary:
            context = Path(temporary).resolve()
            host = context / "public-host"
            for name_in_repo in paths:
                target = host / name_in_repo
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name_in_repo).read_bytes())
                target.chmod(0o644)
            built = build_operator_preview.build(context / "public-preview")
            controller = context / "controller"
            controller.mkdir()
            for file in FILES:
                shutil.copyfile(ROOT / "scripts" / file, controller / file)
                (controller / file).chmod(0o644)
            (controller / "packet.json").write_text(json.dumps({"manifest_sha256": built["manifest_sha256"],
                "case_plan_sha256": plan_sha256(), "production_activation": False}))
            (controller / "packet.json").chmod(0o644)
            base_tag, image_tag = name + ":dependencies", name + ":qualification"
            command(["docker", "image", "tag", base["Id"], base_tag])
            tags[base_tag] = base["Id"]
            (context / "Dockerfile").write_text("FROM " + base_tag + "\nLABEL qualification=" + LABEL + " campaign=" + name
                + "\nCOPY --chmod=755 controller /controller\nCOPY public-host /public-host\nCOPY public-preview /public-preview\n")
            command(["docker", "build", "--network", "none", "--pull=false", "--tag", image_tag, str(context)], 180)
            if strict(command(["docker", "image", "inspect", base_tag]))[0]["Id"] != base["Id"]:
                raise ValueError("Dependency image changed")
            image = strict(command(["docker", "image", "inspect", image_tag]))[0]["Id"]
            tags[image_tag] = image
            for key in ("host", "stage", "work"):
                volume = name + "-" + key
                if command(["docker", "volume", "ls", "--quiet", "--filter", "name=^" + volume + "$"]).strip():
                    raise ValueError("Fresh volume required")
                command(["docker", "volume", "create", "--label", "qualification=" + LABEL, "--label", "campaign=" + name, volume])
                volumes[key] = volume
            proofs = []
            for preparing in (True, False):
                container = command(arguments(image, name, volumes, preparing=preparing)).decode().strip()
                containers.append(container)
                proofs.append(posture(strict(command(["docker", "inspect", container]))[0], volumes, image, preparing=preparing))
                raw = command(["docker", "start", "--attach", container], 180)
                value = strict(raw)
                state = strict(command(["docker", "inspect", container]))[0]["State"]
                if state["Running"] or state["ExitCode"] != 0 or state["OOMKilled"]:
                    raise ValueError("Native process did not exit cleanly")
                if preparing and value != {"prepared": True, "filesystem": "ext4", "private_case_inputs": False}:
                    raise ValueError("Preparation differs")
            gate = validate(value, built["manifest_sha256"])
            if any(digest((ROOT / n).read_bytes()) != h for n, h in hashes.items()):
                raise ValueError("Campaign source changed during execution")
            report = {"schema": "native-operator-preview-campaign-v1", "status": "qualified", "scope": gate["scope"],
                "source_sha256": hashes, "base_dependency_image": base["Id"], "qualification_image": image,
                "posture": proofs, "native": value, "production_activation": False,
                "not_qualified": ["genuine operator approval and key custody", "external checksum channel provenance",
                                  "TLS, DNS or reverse proxy", "production deployment", "provider inference", "legal or owner review"]}
    finally:
        for container in reversed(containers):
            command(["docker", "rm", "--force", container])
        for volume in volumes.values():
            actual = strict(command(["docker", "volume", "inspect", volume]))[0]
            if actual["Labels"].get("campaign") != name or actual["Labels"].get("qualification") != LABEL:
                raise ValueError("Cleanup ownership differs")
            command(["docker", "volume", "rm", volume])
        for tag, expected in reversed(list(tags.items())):
            if strict(command(["docker", "image", "inspect", tag]))[0]["Id"] != expected:
                raise ValueError("Generated image identity changed")
            command(["docker", "image", "rm", tag])
    report.update(disposable_volumes_removed=True, owned_containers_removed=True, generated_image_tags_removed=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-image", required=True, help="Already loaded public dependency image; no pull")
    parser.add_argument("--output", required=True, type=Path, help="New owner-only aggregate report")
    args = parser.parse_args()
    os.umask(0o077)
    with args.output.open("x") as stream:
        stream.write('{"status":"incomplete"}\n')
    try:
        result = run(args.base_image)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        args.output.write_text(json.dumps({"status": "incomplete", "error_type": type(exc).__name__,
                                          "diagnostic": LAST_FAILURE}, indent=2) + "\n")
        raise SystemExit("Native preview qualification failed; activation disabled") from None
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"qualified": True, "native_cases": len(result["native"]["cases"]), "production_activation": False}))
