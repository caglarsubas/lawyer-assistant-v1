"""Versioned public-only controller export; no runtime files or installation."""

import ast
import json
import zipfile
from pathlib import Path

from build_provider_stage import ROOT
from build_signed_route_stage import build_route
from controller_stage_manifest import MODULES, PACKAGE, SCHEMA, digest, inspect_stage

ALIASES = {"provider_trust_stage": "trust", "provider_stage_adapters": "adapters", "signed_provider_contract": "contract",
           "metadata_phase_probe": "strict_json", "provider_identity_binding": "pin_schema", "immutable_provider_hook": "hook",
           "staged_signed_route": "route", "artifact_store": "artifact_store", "sealed_volume": "sealed_volume",
           "sealed_control_journal": "control", "guarded_controller_route": "controller",
           "controller_stage_manifest": "manifest", "controller_stage_readiness": "readiness"}
SOURCES = {"artifact_store": "artifact_store", "sealed_volume": "sealed_volume", "sealed_control_journal": "control",
           "guarded_controller_route": "controller", "controller_stage_manifest": "manifest", "controller_stage_readiness": "readiness"}


class PortableImports(ast.NodeTransformer):
    def visit_ImportFrom(self, node):
        if node.level == 0 and node.module in ALIASES:
            return ast.copy_location(ast.ImportFrom(module=ALIASES[node.module], names=node.names, level=1), node)
        return node

    def visit_Import(self, node):
        nodes = []
        for entry in node.names:
            if entry.name in ALIASES:
                nodes.append(ast.copy_location(ast.ImportFrom(module=None, names=[ast.alias(name=ALIASES[entry.name], asname=entry.asname or entry.name)], level=1), node))
            else:
                nodes.append(ast.copy_location(ast.Import(names=[entry]), node))
        return nodes


def portable(source):
    tree = PortableImports().visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def build(destination):
    destination = Path(destination)
    previous = build_route(destination)
    package = destination / PACKAGE
    destination.chmod(0o755)
    package.chmod(0o755)
    hashes = dict(previous["source_sha256"])
    for source, output in SOURCES.items():
        name = "scripts/" + source + ".py"
        raw = (ROOT / name).read_bytes()
        hashes[name] = digest(raw)
        target = package / (output + ".py")
        target.write_text(portable(raw.decode()))
        target.chmod(0o644)
    if {p.name for p in package.iterdir()} != {n + ".py" for n in MODULES}:
        raise ValueError("Unexpected controller export inventory")
    value = {"schema": SCHEMA, "version": 1, "package_name": PACKAGE, "stage_only": True,
             "production_activation": False, "private_material_included": False,
             "backend_transport": "explicit_httpx_mock_only", "application_or_engine_imports": False,
             "imports_rewritten_only_for_portability": True,
             "required_dependencies": ["cryptography>=44,<47", "httpx==0.28.1"], "source_sha256": hashes,
             "package_sha256": {p.name: digest(p.read_bytes()) for p in sorted(package.iterdir())},
             "metadata_sha256": {n: digest((destination / n).read_bytes()) for n in ("stage-manifest.json", "route-stage-manifest.json")}}
    raw = (json.dumps(value, indent=2) + "\n").encode()
    path = destination / "guarded-stage-manifest.json"
    path.write_bytes(raw)
    path.chmod(0o644)
    inspect_stage(destination, digest(raw), require_readonly=False)
    return {"manifest_sha256": digest(raw), "manifest": value, "stage_only": True, "production_activation": False}


def archive(root, destination, approved_manifest_sha256):
    """Deterministic public-only ZIP beside the stage, with exclusive creation."""
    root, destination = Path(root), Path(destination)
    inspect_stage(root, approved_manifest_sha256, require_readonly=False)
    if destination.parent.resolve() == root.resolve() or root.resolve() in destination.parents:
        raise ValueError("Archive must be outside the closed stage")
    with zipfile.ZipFile(destination, mode="x", compression=zipfile.ZIP_STORED) as output:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(str(path.relative_to(root)), date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            output.writestr(info, path.read_bytes())
    destination.chmod(0o644)
    return {"archive_sha256": digest(destination.read_bytes()), "manifest_sha256": approved_manifest_sha256,
            "source_only": True, "production_activation": False}
