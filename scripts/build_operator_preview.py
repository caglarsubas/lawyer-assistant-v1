"""Deterministic source-only export; never exports credentials or creates a host."""

import argparse
import json
from pathlib import Path

from controller_stage_manifest import digest
from operator_preview_manifest import (
    ASSETS,
    MANIFEST,
    SCHEMA,
    files,
    host_paths,
    inspect_package,
)

ROOT = Path(__file__).resolve().parents[1]


def build(destination):
    root = Path(destination)
    host = files(ROOT, host_paths(ROOT), readonly=False, host=True)
    assets = files(ROOT / "scripts", ASSETS, readonly=False)
    root.mkdir(mode=0o755)  # Fail rather than reuse, merge or overwrite a destination.
    root.chmod(0o755)
    for name, raw in assets.items():
        (root / name).write_bytes(raw)
        (root / name).chmod(0o644)
    value = {"schema": SCHEMA, "version": 1, "stage_only": True, "production_activation": False,
             "private_material_included": False, "compatible_application_host_required": True, "python": ">=3.12",
             "asset_sha256": {name: digest(raw) for name, raw in sorted(assets.items())},
             "host_sha256": {name: digest(raw) for name, raw in sorted(host.items())}}
    raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    (root / MANIFEST).write_bytes(raw)
    (root / MANIFEST).chmod(0o644)
    inspect_package(root, digest(raw), require_readonly=False)
    return {"manifest_sha256": digest(raw), "host_files": len(host), "stage_only": True,
            "compatible_application_host_required": True, "production_activation": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    print(json.dumps(build(parser.parse_args().destination), sort_keys=True))
