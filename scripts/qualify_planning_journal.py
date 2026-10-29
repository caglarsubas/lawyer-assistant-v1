"""Opt-in native authorization-loss and SIGKILL drill on disposable volumes."""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

import build_guarded_controller_stage as controller_builder
import build_receipt_stage as receipt_builder
import qualify_receipt_stage as retained
from controller_stage_manifest import digest, strict
from planning_journal_report import validate

ROOT = Path(__file__).resolve().parents[1]
LABEL = "lawyer-planning-journal-restart-v1"
command = retained.command


def arguments(image, name, volumes, *, preparing):
    if set(volumes) != {"models", "work", "anchors", "backups"} or volumes != {k: name + "-" + k for k in volumes}:
        raise ValueError("Four fresh generated volumes required")
    args = retained.arguments(image, name, {k: volumes[k] for k in ("models", "work")}, preparing=preparing)
    args[args.index("qualification=" + retained.LABEL)] = "qualification=" + LABEL
    index = args.index("--entrypoint")
    args[index:index] = [item for key in ("anchors", "backups")
                        for item in ("--mount", "type=volume,src=" + volumes[key] + ",dst=/" + key)]
    args[args.index("/controller/receipt_stage_native.py")] = "/controller/planning_journal_native.py"
    return args


def posture(actual, volumes, image, *, preparing):
    mounts = actual["Mounts"]
    expected = {(v, "/" + k, preparing or k != "models") for k, v in volumes.items()}
    if (len(mounts) != 4 or {(m.get("Name"), m["Destination"], m["RW"]) for m in mounts if m["Type"] == "volume"} != expected):
        raise ValueError("Four exact owned volume mounts required")
    reduced = {**actual, "Mounts": [m for m in mounts if m["Destination"] in {"/models", "/work"}]}
    proof = retained.posture(reduced, {k: volumes[k] for k in ("models", "work")}, image, preparing=preparing)
    return {**proof, "four_distinct_named_volumes": True}


def public_files():
    raw = command(["git", "-C", str(ROOT), "ls-files", "-z"]).decode().split("\0")
    # Only tracked public source/config; never a checkout-wide copy or ignore override.
    return sorted(n for n in raw if n and ((n.startswith("scripts/") and n.endswith(".py"))
                  or (n.startswith("backend/app/") and n.endswith(".py"))
                  or (n.startswith("deploy/fixtures/") and n.endswith(".json"))))


def run(base_image):
    base = strict(command(["docker", "image", "inspect", base_image]))[0]
    allowed_env = {"PATH", "LANG", "GPG_KEY", "PYTHON_VERSION", "PYTHON_SHA256", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED",
                   "UV_LINK_MODE", "PYTHON_PIP_VERSION", "PYTHON_GET_PIP_URL", "PYTHON_GET_PIP_SHA256"}
    if base["Config"].get("OnBuild") or any(s.partition("=")[0] not in allowed_env for s in base["Config"].get("Env", [])):
        raise ValueError("Public dependency image without runtime configuration required")
    name, containers, volumes, base_tag = "lawyer-receipt-native-" + secrets.token_hex(8), [], {}, None
    try:
        with tempfile.TemporaryDirectory(prefix="lawyer-receipt-http-public-") as temporary:
            context = Path(temporary).resolve()
            controller = controller_builder.build(context / "stage")
            receipt = receipt_builder.build(context / "receipt-export")
            hashes = {}
            for name_in_repo in sorted(set(public_files()) | {"scripts/" + n for n in
                ("qualify_planning_journal.py", "planning_journal_reconciliation.py", "planning_journal_native.py", "planning_journal_worker.py", "planning_journal_report.py")}):
                source = ROOT / name_in_repo
                if source.is_symlink():
                    raise ValueError("Public source symlinks prohibited")
                relative = "controller/" + Path(name_in_repo).name if name_in_repo.startswith("scripts/") else name_in_repo
                target = context / relative
                target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                target.chmod(0o644)
                hashes[name_in_repo] = digest(source.read_bytes())
            packet = {"approved_manifest_sha256": controller["manifest_sha256"], "receipt_manifest_sha256": receipt["manifest_sha256"],
                      "production_activation": False}
            (context / "controller/operator-packet.json").write_text(json.dumps(packet))
            (context / "controller/operator-packet.json").chmod(0o644)
            base_tag = name + ":dependencies"
            command(["docker", "image", "tag", base["Id"], base_tag])
            (context / "Dockerfile").write_text("FROM " + base_tag + "\nCOPY --chmod=755 controller /controller\n"
                "COPY --chmod=755 backend/app /backend/app\nCOPY --chmod=755 deploy/fixtures /deploy/fixtures\n"
                "COPY stage /stage\nCOPY receipt-export /receipt-export\n")
            command(["docker", "build", "--network", "none", "--pull=false", "--tag", name + ":qualification", str(context)], 180)
            if strict(command(["docker", "image", "inspect", base_tag]))[0]["Id"] != base["Id"]:
                raise ValueError("Pinned dependency image changed")
            image = strict(command(["docker", "image", "inspect", name + ":qualification"]))[0]["Id"]
            for key in ("models", "work", "anchors", "backups"):
                volume = name + "-" + key
                if command(["docker", "volume", "ls", "--quiet", "--filter", "name=^" + volume + "$"]).strip():
                    raise ValueError("Existing volume name refused")
                command(["docker", "volume", "create", "--label", "qualification=" + LABEL, "--label", "campaign=" + name, volume])
                volumes[key] = volume
            proofs = []
            for preparing in (True, False):
                ident = command(arguments(image, name, volumes, preparing=preparing)).decode().strip()
                containers.append(ident)
                proofs.append(posture(strict(command(["docker", "inspect", ident]))[0], volumes, image, preparing=preparing))
                raw = command(["docker", "start", "--attach", ident], 180)
                state = strict(command(["docker", "inspect", ident]))[0]["State"]
                if state["Running"] or state["ExitCode"] != 0 or state["OOMKilled"]:
                    raise ValueError("Native HTTP process failed")
                output = strict(raw)
                if preparing and output != {"prepared": True, "private_case_inputs": False}:
                    raise ValueError("Fresh disposable fixture preparation failed")
            validate(output, receipt["manifest_sha256"], controller["manifest_sha256"])
            report = {"schema": "native-planning-journal-campaign-v1", "status": "qualified", "native": output,
                      "source_sha256": hashes, "base_dependency_image": base["Id"], "qualification_image": image, "posture": proofs,
                      "production_activation": False, "not_qualified": ["power-loss durability", "automatic journal repair or record adoption",
                          "genuine operator appointments and key custody", "real inference or provider", "production activation", "owner legal review"]}
    finally:
        for ident in reversed(containers):
            command(["docker", "rm", "--force", ident])
        for volume in volumes.values():
            owned = strict(command(["docker", "volume", "inspect", volume]))[0]
            if owned["Labels"].get("campaign") != name or owned["Labels"].get("qualification") != LABEL:
                raise ValueError("Cleanup ownership differs")
            command(["docker", "volume", "rm", volume])
        if base_tag is not None:
            if strict(command(["docker", "image", "inspect", base_tag]))[0]["Id"] != base["Id"]:
                raise ValueError("Temporary dependency tag changed")
            command(["docker", "image", "rm", base_tag])
    report["disposable_volumes_removed"] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-image", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    with args.output.open("x") as stream:
        stream.write('{"status":"incomplete"}\n')
    try:
        value = run(args.base_image)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
        raise SystemExit("Native HTTP qualification failed; activation remains disabled") from None
    args.output.write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps({"qualified_modes": 2, "frozen_outcomes": 44, "production_activation": False}))


if __name__ == "__main__":
    main()
