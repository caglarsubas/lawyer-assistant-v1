"""Stdlib-only verification before importing an independently pinned receipt stage."""

import ast
import os
import sys
from pathlib import Path

from controller_stage_manifest import digest, directory, hex_digest, read, strict

PACKAGE, SCHEMA = "lawyer_receipt_stage", "private-receipt-adapter-stage-v1"
SOURCES = {"operator_enrollment_evidence": "evidence", "operator_recovery_inventory": "inventory",
           "operator_inventory_handoff": "handoff", "private_inventory_receipts": "receipts",
           "controller_stage_manifest": "stage_helpers", "receipt_stage_manifest": "manifest",
           "receipt_provisioning_readiness": "readiness", "staged_receipt_adapter": "adapter"}
MODULES = {"__init__", *SOURCES.values()}
MANIFEST = "receipt-stage-manifest.json"


def inspect_stage(root, approved_manifest_sha256, *, require_readonly=True):
    if type(require_readonly) is not bool:
        raise ValueError("Explicit stage policy required")
    owner = os.getuid()
    root = directory(Path(root), owner, require_readonly)
    if {p.name for p in root.iterdir()} != {PACKAGE, MANIFEST}:
        raise ValueError("Closed receipt stage required")
    raw = read(root / MANIFEST, owner, require_readonly)
    if digest(raw) != hex_digest(approved_manifest_sha256):
        raise ValueError("Independent stage pin differs")
    value = strict(raw)
    if (not isinstance(value, dict) or set(value) != {"schema", "version", "package_name", "stage_only",
            "production_activation", "private_material_included", "application_or_engine_imports",
            "imports_rewritten_only_for_portability", "required_dependencies", "source_sha256", "package_sha256"}
            or value["schema"] != SCHEMA or type(value["version"]) is not int or value["version"] != 1
            or value["package_name"] != PACKAGE or value["stage_only"] is not True
            or any(value[k] is not False for k in ("production_activation", "private_material_included", "application_or_engine_imports"))
            or value["imports_rewritten_only_for_portability"] is not True
            or value["required_dependencies"] != ["cryptography>=44,<47"]
            or not isinstance(value["source_sha256"], dict)
            or set(value["source_sha256"]) != {"scripts/" + name + ".py" for name in SOURCES}
            or not isinstance(value["package_sha256"], dict)
            or set(value["package_sha256"]) != {name + ".py" for name in MODULES}):
        raise ValueError("Closed public-only stage manifest required")
    for expected in value["source_sha256"].values():
        hex_digest(expected)
    package = directory(root / PACKAGE, owner, require_readonly)
    if {p.name for p in package.iterdir()} != set(value["package_sha256"]):
        raise ValueError("Closed stage modules required")
    total = len(raw)
    for name, expected in value["package_sha256"].items():
        body = read(package / name, owner, require_readonly)
        if digest(body) != hex_digest(expected):
            raise ValueError("Pinned module differs")
        total += len(body)
        for node in ast.walk(ast.parse(body)):
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    if (node.level != 1 or (node.module is not None and node.module not in MODULES)
                            or (node.module is None and any(n.name not in MODULES for n in node.names))):
                        raise ValueError("Closed relative imports required")
                elif node.module.split(".")[0] not in sys.stdlib_module_names | {"cryptography"}:
                    raise ValueError("Application and engine imports prohibited")
            elif isinstance(node, ast.Import):
                if any(n.name.split(".")[0] not in sys.stdlib_module_names | {"cryptography"} for n in node.names):
                    raise ValueError("Application and engine imports prohibited")
    if total > 8 * 1024**2:
        raise ValueError("Stage work budget exceeded")
    return {"stage_only": True, "manifest_sha256": approved_manifest_sha256, "modules": len(MODULES),
            "bytes_checked": total, "kernel_readonly": require_readonly, "production_activation": False}
