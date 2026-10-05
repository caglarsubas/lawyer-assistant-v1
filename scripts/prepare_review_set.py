#!/usr/bin/env python3
"""Prepare and revalidate confidential multi-source review packets on a trusted host.

Uses existing accounts, source packages and review ledgers. Never signs or publishes.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.qualification_evidence import read_exact_directory  # noqa: E402
from app.release_snapshot_set import SnapshotSetRequest  # noqa: E402

_spec = importlib.util.spec_from_file_location("review_set_packet_io", ROOT / "scripts/prepare_legal_review.py")
io = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(io)

PACKET_SCHEMA = "legal-review-source-set-packet-v1"
MAX_REQUEST_BYTES = 64 * 1024


def capture_inputs(request_dir, registry, resolutions, evidence_dir):
    raw = read_exact_directory(Path(request_dir), {"sources.json": MAX_REQUEST_BYTES}, MAX_REQUEST_BYTES)
    raw["registry.json"] = io.read_file(registry, io.MAX_JSON)
    raw["resolutions.json"] = io.read_file(resolutions, io.MAX_JSON)
    evidence = io.evidence_files(evidence_dir)
    from app.release_preparation import Registry
    from app.release_set_preparation import SourceSetResolutions

    request = SnapshotSetRequest.model_validate(io.parse_json(raw["sources.json"]))
    registry_data = Registry.model_validate(io.parse_json(raw["registry.json"])).model_dump()
    resolution_data = SourceSetResolutions.model_validate(io.parse_json(raw["resolutions.json"])).model_dump()
    return raw, evidence, request, registry_data, resolution_data


def _unchanged(paths, captured):
    current = capture_inputs(**paths)
    if current[:2] != captured[:2]:
        raise ValueError("Preparation inputs changed")


def _ontology_digest(root):
    from app.graph_release import _load_serving

    return _load_serving()._release.ontology_digest(Path(root))


def _same_ontology(root, expected):
    if _ontology_digest(root) != expected:
        raise ValueError("Ontology changed during preparation")


def _read_packet(directory, store):
    return io.read_packet(directory, store, schema_version=PACKET_SCHEMA)


def prepare(settings, *, operator_id, request_dir, registry, resolutions, evidence_dir, output,
            ontology_root=ROOT / "ontology"):
    from app.public_sources import PublicSourceStore
    from app.release_set_preparation import compile_review_set
    from app.release_snapshot import readonly_store
    from app.release_snapshot_set import locked_snapshot_set

    paths = dict(request_dir=request_dir, registry=registry, resolutions=resolutions, evidence_dir=evidence_dir)
    captured = capture_inputs(**paths)
    _, evidence, request, registry_data, resolution_data = captured
    ontology_sha = _ontology_digest(ontology_root)
    created = None
    try:
        with readonly_store(settings) as store:
            source_store = PublicSourceStore(settings.public_source_dir)
            with locked_snapshot_set(store, source_store, operator_id=operator_id, request=request) as snapshot:
                files, summary = compile_review_set(snapshot, registry_data, resolution_data, evidence,
                                                     Path(ontology_root))
                packet = io.sealed_files(files, store, schema_version=PACKET_SCHEMA)
                _unchanged(paths, captured)
                _same_ontology(ontology_root, ontology_sha)
            # The first exit must succeed before writing. Reacquire all heads,
            # then retain only output whose final live check also succeeds.
            with locked_snapshot_set(store, source_store, operator_id=operator_id, request=request) as current:
                if current["binding"] != snapshot["binding"]:
                    raise ValueError("Source set changed before output")
                _unchanged(paths, captured)
                _same_ontology(ontology_root, ontology_sha)
                created = io.atomic_packet(output, packet)
                if _read_packet(output, store) != (files, io.digest(packet["manifest.json"])):
                    raise ValueError("Packet changed during output")
            _unchanged(paths, captured)
            _same_ontology(ontology_root, ontology_sha)
            if _read_packet(output, store) != (files, io.digest(packet["manifest.json"])):
                raise ValueError("Packet changed during final validation")
    except BaseException:
        if created is not None:
            io._remove_own_output(output, created)
        raise
    return {**summary, "packet_sha256": io.digest(packet["manifest.json"]), "current_at_validation": True}


def _request(binding, operator_id):
    if (type(binding) is not dict or binding.get("operator_id") != operator_id
            or binding.get("schema_version") != "legal-review-snapshot-set-v1"
            or type(binding.get("sources")) is not list or not 2 <= len(binding["sources"]) <= 8):
        raise ValueError("Invalid source-set binding")
    return SnapshotSetRequest.model_validate({
        "schema_version": "legal-review-source-selection-v1", "sources": [
            {"source_id": source["source_id"],
             "expected_source_review_revision": source["source_review_revision"],
             "expected_mapping_revision": source["mapping_revision"]} for source in binding["sources"]]})


def validate(settings, directory, *, operator_id, ontology_root=ROOT / "ontology"):
    from app.public_sources import PublicSourceStore
    from app.release_set_preparation import compile_review_set
    from app.release_snapshot import readonly_store
    from app.release_snapshot_set import locked_snapshot_set

    ontology_sha = _ontology_digest(ontology_root)
    with readonly_store(settings) as store:
        files, packet_digest = _read_packet(directory, store)
        request = _request(io.parse_json(files["binding.json"]), operator_id)
        registry = io.parse_json(files["registry.json"])
        resolutions = io.parse_json(files["resolutions.json"])
        evidence = {Path(name).stem: raw for name, raw in files.items() if name.startswith("private-evidence/")}
        with locked_snapshot_set(store, PublicSourceStore(settings.public_source_dir),
                                 operator_id=operator_id, request=request) as snapshot:
            rebuilt, summary = compile_review_set(snapshot, registry, resolutions, evidence, Path(ontology_root))
            if rebuilt != files:
                raise ValueError("Packet differs from current sources, reviews, identities or ontology")
            _same_ontology(ontology_root, ontology_sha)
            if _read_packet(directory, store) != (files, packet_digest):
                raise ValueError("Packet changed during validation")
        _same_ontology(ontology_root, ontology_sha)
        if _read_packet(directory, store) != (files, packet_digest):
            raise ValueError("Packet changed during final revalidation")
    return {**summary, "packet_sha256": packet_digest, "current_at_validation": True}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("Invalid command arguments")


def main(argv=None):
    try:
        parser = Parser(description=__doc__)
        commands = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
        commands.add_parser("schema", help="Print input schemas without loading deployment settings")
        preparing = commands.add_parser("prepare")
        checking = commands.add_parser("validate")
        for command in (preparing, checking):
            command.add_argument("--operator-id", required=True)
        for name in ("request-dir", "registry", "resolutions", "evidence-dir", "output"):
            preparing.add_argument("--" + name, type=Path, required=True)
        checking.add_argument("directory", type=Path)
        args = vars(parser.parse_args(argv))
        command = args.pop("command")
        if command == "schema":
            from app.release_preparation import Registry
            from app.release_set_preparation import SourceSetResolutions

            result = {"selection": SnapshotSetRequest.model_json_schema(), "registry": Registry.model_json_schema(),
                      "resolutions": SourceSetResolutions.model_json_schema(), "packet_schema": PACKET_SCHEMA}
        else:
            if command == "prepare":
                capture_inputs(**{name: args[name] for name in
                                  ("request_dir", "registry", "resolutions", "evidence_dir")})
            from app.config import load_settings

            settings = load_settings()
            result = prepare(settings, **args) if command == "prepare" else validate(settings, **args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"error": "review_source_set_preparation_failed", "publication_eligible": False}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
