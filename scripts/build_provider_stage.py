"""Build a self-contained staged provider package from declared public sources only."""

import ast
import json
from pathlib import Path

from provider_trust_stage import directory
from signed_provider_contract import sha

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "lawyer_provider_stage"


def build(destination):
    destination = Path(destination)
    directory(destination.parent)
    destination.mkdir(mode=0o755)
    package = destination / PACKAGE
    package.mkdir(mode=0o755)
    aliases = {
        "provider_trust_stage": "trust",
        "provider_stage_adapters": "adapters",
        "signed_provider_contract": "contract",
        "metadata_phase_probe": "strict_json",
        "provider_identity_binding": "pin_schema",
    }
    origins = {
        "trust": "scripts/provider_trust_stage.py",
        "adapters": "scripts/provider_stage_adapters.py",
        "contract": "scripts/signed_provider_contract.py",
    }
    source_hashes = {}
    for output, source in origins.items():
        raw = (ROOT / source).read_text()
        source_hashes[source] = sha(raw.encode())
        for old, new in aliases.items():
            raw = raw.replace("from " + old + " import ", "from ." + new + " import ")
        ast.parse(raw)
        (package / (output + ".py")).write_text(raw)
    # Preserve the reviewed validators as exact AST fragments; no app import.
    source = (ROOT / "scripts/metadata_phase_probe.py").read_text()
    source_hashes["scripts/metadata_phase_probe.py"] = sha(source.encode())
    tree = ast.parse(source)
    parts = [
        ast.get_source_segment(source, n)
        for n in tree.body
        if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in {"Rejected", "strict_json"}
    ]
    (package / "strict_json.py").write_text("import json\nimport math\n\n" + "\n\n".join(parts) + "\n")
    source = (ROOT / "scripts/provider_identity_binding.py").read_text()
    source_hashes["scripts/provider_identity_binding.py"] = sha(source.encode())
    tree = ast.parse(source)
    parts = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in {"digest", "validate_pin"}:
            parts.append(ast.get_source_segment(source, node))
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "PIN_FIELDS" for t in node.targets
        ):
            parts.append(ast.get_source_segment(source, node))
    canonical = 'def canonical(value):\n    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)\n'
    (package / "pin_schema.py").write_text(
        "import json\nimport re\n\n" + canonical + "\n\n" + "\n\n".join(parts) + "\n"
    )
    (package / "__init__.py").write_text(
        '"""Staged-only provider support. No installed handler or activation."""\n'
    )
    for p in package.iterdir():
        p.chmod(0o644)
        ast.parse(p.read_text())
    interface_bytes = (ROOT / "deploy/fixtures/provider_engine_source.json").read_bytes()
    source_hashes["deploy/fixtures/provider_engine_source.json"] = sha(interface_bytes)
    policy_bytes = (ROOT / "deploy/fixtures/provider_stage_policy.json").read_bytes()
    source_hashes["deploy/fixtures/provider_stage_policy.json"] = sha(policy_bytes)
    manifest = {
        "required_provider_policy": json.loads(policy_bytes),
        "provider_interface_contract": json.loads(interface_bytes),
        "version": 1,
        "stage_only": True,
        "production_activation": False,
        "private_material_included": False,
        "source_sha256": source_hashes,
        "package_sha256": {p.name: sha(p.read_bytes()) for p in sorted(package.iterdir())},
        "imports_rewritten_only_for_portability": True,
        "required_dependency": "cryptography>=44,<47",
    }
    (destination / "stage-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (destination / "stage-manifest.json").chmod(0o644)
    return manifest
