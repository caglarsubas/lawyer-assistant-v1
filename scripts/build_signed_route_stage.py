"""Add staged execution/ASGI support without changing the retained stage builder."""

import ast
import json
from pathlib import Path

from build_provider_stage import ROOT, build
from signed_provider_contract import sha


def build_route(destination):
    manifest = build(destination)
    package = Path(destination) / "lawyer_provider_stage"
    for source, target in {
        "immutable_provider_hook": "hook",
        "staged_signed_route": "route",
    }.items():
        path = "scripts/" + source + ".py"
        raw = (ROOT / path).read_text()
        manifest["source_sha256"][path] = sha(raw.encode())
        for old, new in {
            "provider_trust_stage": "trust",
            "signed_provider_contract": "contract",
        }.items():
            raw = raw.replace("from " + old + " import ", "from ." + new + " import ")
        ast.parse(raw)
        output = package / (target + ".py")
        output.write_text(raw)
        output.chmod(0o644)
    manifest.update(
        stage_kind="unregistered_signed_route_and_digest_execution_hook",
        required_dependencies=["cryptography>=44,<47", "httpx==0.28.1"],
        package_sha256={p.name: sha(p.read_bytes()) for p in sorted(package.iterdir())},
        native_compatibility_qualified=False,
        executed_weights_qualified=False,
    )
    receipt = Path(destination) / "route-stage-manifest.json"
    receipt.write_text(json.dumps(manifest, indent=2) + "\n")
    receipt.chmod(0o644)
    return manifest
