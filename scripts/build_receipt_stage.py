"""Deterministic public source export; no key, profile, receipt or installation."""

import ast
import json
from pathlib import Path

from receipt_stage_manifest import MANIFEST, MODULES, PACKAGE, SCHEMA, SOURCES, digest, inspect_stage

ROOT = Path(__file__).resolve().parents[1]


class PortableImports(ast.NodeTransformer):
    def visit_ImportFrom(self, node):
        if node.level == 0 and node.module in SOURCES:
            return ast.copy_location(ast.ImportFrom(module=SOURCES[node.module], names=node.names, level=1), node)
        return node

    def visit_Import(self, node):
        result = []
        for entry in node.names:
            if entry.name in SOURCES:
                result.append(ast.copy_location(ast.ImportFrom(module=None, names=[ast.alias(name=SOURCES[entry.name],
                              asname=entry.asname or entry.name)], level=1), node))
            else:
                result.append(ast.copy_location(ast.Import(names=[entry]), node))
        return result


def portable(raw):
    tree = PortableImports().visit(ast.parse(raw))
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def build(destination):
    root = Path(destination)
    root.mkdir(mode=0o755)  # Never reuse or overwrite an existing stage.
    root.chmod(0o755)
    package = root / PACKAGE
    package.mkdir(mode=0o755)
    package.chmod(0o755)
    (package / "__init__.py").write_text('"""Unregistered disposable receipt adapter stage."""\n')
    (package / "__init__.py").chmod(0o644)
    sources = {}
    for name, output in SOURCES.items():
        relative = "scripts/" + name + ".py"
        raw = (ROOT / relative).read_bytes()
        sources[relative] = digest(raw)
        path = package / (output + ".py")
        path.write_text(portable(raw))
        path.chmod(0o644)
    assert {p.stem for p in package.iterdir()} == MODULES
    value = {"schema": SCHEMA, "version": 1, "package_name": PACKAGE, "stage_only": True,
             "production_activation": False, "private_material_included": False, "application_or_engine_imports": False,
             "imports_rewritten_only_for_portability": True, "required_dependencies": ["cryptography>=44,<47"],
             "source_sha256": sources, "package_sha256": {p.name: digest(p.read_bytes()) for p in sorted(package.iterdir())}}
    raw = (json.dumps(value, indent=2) + "\n").encode()
    (root / MANIFEST).write_bytes(raw)
    (root / MANIFEST).chmod(0o644)
    inspect_stage(root, digest(raw), require_readonly=False)
    return {"manifest_sha256": digest(raw), "manifest": value, "production_activation": False}
