"""Opt-in Linux/ext4 package probe; disposable files, no HTTP or host auth adapter."""

import errno
import importlib
import json
import os
import secrets
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import receipt_stage_manifest as external
from receipt_stage_native_report import CASES, FALSE, validate

MODELS, WORK = Path("/models"), Path("/work")


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def inventory(root):
    return {str(p.relative_to(root)): external.digest(p.read_bytes()) for p in sorted(root.rglob("*"))
            if p.is_file() and not p.is_symlink()}


def filesystem(root):
    rows = Path("/proc/self/mountinfo").read_text().splitlines()
    matches = [r.split(" - ")[1].split()[0] for r in rows if r.split()[4] == str(root)]
    if matches != ["ext4"]:
        raise ValueError("Exact Linux/ext4 volume mount required")
    return matches[0]


def prepare(packet):
    if any(root.is_symlink() or list(root.iterdir()) for root in (MODELS, WORK)) or os.getuid() != 0:
        raise ValueError("Fresh owned qualification volumes required")
    source = Path("/receipt-export")
    external.inspect_stage(source, packet["approved_manifest_sha256"])
    for name in CASES:
        if name == "N08_writable":
            continue
        shutil.copytree(source, MODELS / name)
    extra = MODELS / "N03_extra" / "extra.txt"
    extra.write_text("disposable unknown file\n")
    module = "lawyer_receipt_stage/adapter.py"
    (MODELS / "N05_symlink" / module).unlink()
    (MODELS / "N05_symlink" / module).symlink_to(MODELS / "N01_valid" / module)
    os.link(MODELS / "N06_hardlink" / module, MODELS / "external-hardlink.py")
    forbidden = MODELS / "N07_forbidden_import"
    with (forbidden / module).open("a") as stream:
        stream.write("\nfrom app import db\n")
    manifest = external.strict((forbidden / external.MANIFEST).read_bytes())
    manifest["package_sha256"]["adapter.py"] = external.digest((forbidden / module).read_bytes())
    (forbidden / external.MANIFEST).write_bytes(encode(manifest))
    (MODELS / "N10_bytes" / module).write_text("# changed module without a matching manifest\n")
    for root in (MODELS, WORK):
        for parent, _, files in os.walk(root, topdown=False):
            for name in files:
                path = Path(parent) / name
                if path.is_symlink():
                    os.lchown(path, 10002, 10002)
                else:
                    path.chmod(0o644)
                    os.chown(path, 10002, 10002)
            Path(parent).chmod(0o755 if root == MODELS else 0o700)
            os.chown(parent, 10002, 10002)
    (MODELS / "N04_mode" / module).chmod(0o640)
    os.chown(MODELS / "N09_owner" / module, 10003, 10003)
    return {"prepared": True, "filesystem": filesystem(MODELS), "private_case_inputs": False}


def forbidden_imports():
    return any(n == "app" or n.startswith(("app.", "inference_engine")) for n in sys.modules)


def probe(name, packet):
    if name not in CASES or forbidden_imports() or any(n.startswith(external.PACKAGE) for n in sys.modules):
        raise ValueError("Fresh isolated process required")
    stage, expected = MODELS / name, packet["approved_manifest_sha256"]
    if name == "N02_pin":
        expected = "0" * 64
    if name == "N07_forbidden_import":
        # Matching byte hashes cannot bypass the pre-import dependency policy.
        expected = external.digest((stage / external.MANIFEST).read_bytes())
    if name == "N08_writable":
        stage = WORK / name
        shutil.copytree(MODELS / "N01_valid", stage)
    row = {"id": name, "state": "rejected", "inspected_before_import": True, "package_imported": False,
           "application_or_engine_imports": False, "kernel_write_rejected": False, "disposable_readiness": "not_checked"}
    try:
        external.inspect_stage(stage, expected)  # Default policy, never mocked or relaxed.
    except (ValueError, OSError, SyntaxError):
        return {"pid": os.getpid(), "row": row}
    if name != "N01_valid":
        raise ValueError("A rejected fixture passed inspection")
    try:
        with (stage / ".write-probe").open("xb"):
            pass
    except OSError as error:
        if error.errno != errno.EROFS:
            raise ValueError("Kernel read-only denial required") from None
    else:
        raise ValueError("Stage unexpectedly writable")
    sys.path.insert(0, str(stage))
    modules = {n: importlib.import_module(external.PACKAGE + "." + n) for n in sorted(external.MODULES - {"__init__"})}
    if forbidden_imports():
        raise ValueError("Application or inference dependency loaded")
    receipts, readiness, e = (modules[n] for n in ("receipts", "readiness", "evidence"))
    root, profile = WORK / "receipts", WORK / "disposable-profile.json"
    root.mkdir(mode=0o700)
    profile_id, context_id, scope = secrets.token_hex(16), secrets.token_hex(16), secrets.token_hex(32)
    e.retain(profile, e.encode({"schema": "disposable-operator-review-v1", "profile_id": profile_id, "production_activation": False}))
    store = receipts.ReceiptStore(root=root, context_id=context_id, scope_sha256=scope, key=secrets.token_bytes(32))
    pins = readiness.Pins(context_id=context_id, scope_sha256=scope, key_fingerprint=readiness.fingerprint(store.key),
                          store_identity=store.identity, profile_id=profile_id, profile_sha256=e.sha(profile.read_bytes()))
    before = inventory(WORK)
    result = readiness.assess(stage, expected, store, profile, pins)
    if (result["state"] != "ready_for_disposable_validation" or result["key_custody"] != "unassessed"
            or result["operator_appointments"] != "unassessed" or any(result[k] is not False for k in e.FLAGS)):
        raise ValueError("Readiness must not grant authority")
    for wrong in (replace(pins, key_fingerprint="0" * 64), replace(pins, profile_sha256="0" * 64),
                  replace(pins, store_identity=(0, 0)), replace(pins, scope_sha256="0" * 64)):
        if readiness.assess(stage, expected, store, profile, wrong)["state"] != "blocked":
            raise ValueError("Independent binding mismatch accepted")
    if inventory(WORK) != before:
        raise ValueError("Readiness changed disposable state")
    row.update(state="verified", package_imported=True, kernel_write_rejected=True, disposable_readiness="verified")
    return {"pid": os.getpid(), "row": row}


def campaign(packet):
    if os.getuid() != 10002 or not os.statvfs(MODELS).f_flag & os.ST_RDONLY or os.statvfs(WORK).f_flag & os.ST_RDONLY:
        raise ValueError("Bound non-root read-only stage and writable fixture volume required")
    before, rows, pids = inventory(MODELS), [], set()
    for name in CASES:
        result = subprocess.run([sys.executable, "-I", "-B", __file__, "probe", name], capture_output=True, timeout=10, check=False)
        if result.returncode:
            raise ValueError("Native packaging subprocess failed")
        value = external.strict(result.stdout)
        if (not isinstance(value, dict) or set(value) != {"pid", "row"} or type(value["pid"]) is not int
                or value["pid"] in pids or value["pid"] == os.getpid()):
            raise ValueError("Distinct subprocess receipts required")
        pids.add(value["pid"])
        rows.append(value["row"])
    report = {"schema": "receipt-stage-native-packaging-v1", "package_manifest_sha256": packet["approved_manifest_sha256"],
              "cases": rows, "read_only_inventory_exact": before == inventory(MODELS), "distinct_processes": len(pids),
              "filesystem": filesystem(MODELS), "kernel_readonly": True, "native_inference_calls": 0,
              "live_provider_requests": 0, "HTTP_requests": 0, "operator_authorization": "unassessed", "key_custody": "unassessed",
              **dict.fromkeys(FALSE, False)}
    validate(report, packet["approved_manifest_sha256"])
    return report


def main():
    os.umask(0o077)
    packet = external.strict(Path("/controller/operator-packet.json").read_bytes())
    if (set(packet) != {"approved_manifest_sha256", "production_activation"} or packet["production_activation"] is not False):
        raise ValueError("Closed public pin packet required")
    external.hex_digest(packet["approved_manifest_sha256"])
    action = sys.argv[1:]
    if action == ["prepare"]:
        value = prepare(packet)
    elif action == ["run"]:
        value = campaign(packet)
    elif len(action) == 2 and action[0] == "probe":
        value = probe(action[1], packet)
    else:
        raise ValueError("Closed native action required")
    print(json.dumps(value), flush=True)


if __name__ == "__main__":
    main()
