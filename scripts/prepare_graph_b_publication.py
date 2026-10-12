#!/usr/bin/env python3
"""Trusted local Graph B preparation. No signer, public grant or graph transition.

All outputs are private. Independent public review and a final complete national
release assembly are separate gates. Never run against untrusted remote requests.
"""
import json
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.graph_b_publication import (  # noqa: E402
    PACKET_SCHEMA,
    match_public_component,
    permission_request,
    prepare_files,
    private_evidence,
    verify_files,
)
from app.graph_b_snapshot import SnapshotRequest, locked_graph_b_snapshot  # noqa: E402
from app.graph_release import _load_serving  # noqa: E402
from app.public_sources import PublicSourceStore  # noqa: E402
from app.release_authorization import _packet_tools  # noqa: E402
from app.release_snapshot import readonly_store  # noqa: E402

io = _packet_tools()


def _sources(settings):
    root = io.checked_path(settings.public_source_dir)
    if not root.is_dir():
        raise ValueError("Existing verified public sources are required")
    return PublicSourceStore(root)


def _open(store, settings, operator_id, selection, *, shared=False):
    return locked_graph_b_snapshot(store, _sources(settings), operator_id=operator_id, request=selection,
        trusted_key=settings.graph_b_review_trusted_key, ontology_root=ROOT / "ontology", shared=shared)


def prepare(settings, *, operator_id, selection, evidence_dir, output):
    selection = SnapshotRequest.model_validate(io.parse_json(io.read_file(selection, 64 * 1024)))
    evidence = io.evidence_files(evidence_dir)
    configured_key = settings.graph_b_review_trusted_key
    created = None
    try:
        with readonly_store(settings) as store:
            with _open(store, settings, operator_id, selection) as snapshot:
                files = prepare_files(store, snapshot, evidence, ROOT / "ontology")
                sealed = io.sealed_files(files, store, schema_version=PACKET_SCHEMA)
                created = io.atomic_packet(output, sealed)
                written, fingerprint = io.read_packet(output, store, schema_version=PACKET_SCHEMA)
                if written != files or fingerprint != io.digest(sealed["manifest.json"]):
                    raise ValueError("Private preparation changed during output")
            # Re-read the durable seal after complete source/trust exit checks.
            if io.read_packet(output, store, schema_version=PACKET_SCHEMA) != (files, fingerprint):
                raise ValueError("Private preparation changed at final validation")
            if settings.graph_b_review_trusted_key != configured_key:
                raise ValueError("Configured review trust changed")
    except BaseException:
        io._remove_own_output(output, created)
        raise
    return {"packet_created": True, "signed": False, "publication_eligible": False,
            "encrypted_private_evidence": True, "public_assertions": 6, "national_release_serving_authorized": False}


@contextmanager
def current_packet(settings, packet, operator_id, *, shared=False):
    configured_key = settings.graph_b_review_trusted_key
    with readonly_store(settings) as store:
        files, fingerprint = io.read_packet(packet, store, schema_version=PACKET_SCHEMA)
        private = private_evidence(store, files)
        if private["binding"]["operator_id"] != operator_id:
            raise ValueError("Exact current source owner is required")
        selection = SnapshotRequest.model_validate(private["binding"]["selection"])
        with _open(store, settings, operator_id, selection, shared=shared) as snapshot:
            private = verify_files(store, files, snapshot, ROOT / "ontology")
            yield store, files, fingerprint, private, snapshot
            if io.read_packet(packet, store, schema_version=PACKET_SCHEMA) != (files, fingerprint):
                raise ValueError("Private preparation changed during validation")
        if io.read_packet(packet, store, schema_version=PACKET_SCHEMA) != (files, fingerprint):
            raise ValueError("Private preparation changed at final validation")
        if settings.graph_b_review_trusted_key != configured_key:
            raise ValueError("Configured review trust changed")


def validate(settings, packet, *, operator_id):
    with current_packet(settings, packet, operator_id, shared=True):
        pass
    return {"current_at_validation": True, "signed": False, "publication_eligible": False,
            "national_release_serving_authorized": False}


def request(settings, prepared, *, packet, operator_id, reviewer, approved_at, expires_at, source_permissions, output):
    configured_public_key = settings.graph_trusted_review_key
    if not configured_public_key:
        raise ValueError("Configure separately vetted national review trust")
    trusted_public_key = io.checked_path(configured_public_key)
    public_key_bytes = io.read_file(trusted_public_key, 16384)
    created = None
    try:
        with current_packet(settings, packet, operator_id) as (store, files, fingerprint, private, snapshot):
            info = _load_serving().validate_prepared(prepared, trusted_public_key)
            info = match_public_component(files, info, trusted_public_key, ROOT / "ontology")
            epoch_path = settings.data_dir / "publication-epoch"
            epoch_bytes = io.read_file(epoch_path, 37)
            body = permission_request(files, private, snapshot, info, packet_sha256=fingerprint,
                epoch=epoch_bytes.decode("ascii").removesuffix("\n"), reviewer=reviewer,
                approved_at=approved_at, expires_at=expires_at, source_permissions=source_permissions)
            # The retained request includes private source selections. An external
            # signer must decrypt it only in trusted local memory, not publish it.
            outputs = {"permission-request.fernet": store.seal_preparation(body), "NOTICE.json": io.canonical({
                "schema_version": body["schema_version"], "signed": False, "confidentiality": "firm_confidential",
                "publication_eligible": False, "national_release_serving_authorized": False,
                "purpose": "Encrypted unsigned component inclusion request; requires independent signature and complete national assembly"})}
            sealed = io.sealed_files(outputs, store, schema_version=PACKET_SCHEMA)
            created = io.atomic_packet(output, sealed)
            if io.read_packet(output, store, schema_version=PACKET_SCHEMA)[0] != outputs:
                raise ValueError("Encrypted request changed during output")
            # Trust, prepared bytes and epoch must still match AFTER encryption
            # and durable writes. The enclosing current packet protects sources.
            final = match_public_component(files, info, trusted_public_key, ROOT / "ontology")
            if (final != info or io.read_file(epoch_path, 37) != epoch_bytes
                    or settings.graph_trusted_review_key != configured_public_key or io.read_file(trusted_public_key, 16384) != public_key_bytes
                    or io.read_packet(output, store, schema_version=PACKET_SCHEMA)[0] != outputs
                    or permission_request(files, private, snapshot, final, packet_sha256=fingerprint,
                        epoch=epoch_bytes.decode("ascii").removesuffix("\n"), reviewer=reviewer,
                        approved_at=approved_at, expires_at=expires_at, source_permissions=source_permissions) != body):
                raise ValueError("Publication dependencies changed")
        with readonly_store(settings) as store:
            if io.read_packet(output, store, schema_version=PACKET_SCHEMA)[0] != outputs:
                raise ValueError("Encrypted request changed at final validation")
        if (io.read_file(epoch_path, 37) != epoch_bytes or settings.graph_trusted_review_key != configured_public_key
                or io.read_file(trusted_public_key, 16384) != public_key_bytes
                or datetime.now(timezone.utc) >= datetime.fromisoformat(expires_at.replace("Z", "+00:00"))):
            raise ValueError("Publication dependencies changed at final validation")
    except BaseException:
        io._remove_own_output(output, created)
        raise
    return {"component_permission_requested": True, "signed": False, "publication_eligible": False,
            "national_release_serving_authorized": False}


def parser():
    import argparse
    result = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = result.add_subparsers(dest="command", required=True)
    prepared = commands.add_parser("prepare", allow_abbrev=False)
    prepared.add_argument("--selection", required=True, type=Path)
    prepared.add_argument("--evidence-dir", required=True, type=Path)
    prepared.add_argument("--output", required=True, type=Path)
    validated = commands.add_parser("validate", allow_abbrev=False)
    proposed = commands.add_parser("request", allow_abbrev=False)
    for command in (validated, proposed):
        command.add_argument("packet", type=Path)
    for command in (prepared, validated, proposed):
        command.add_argument("--operator-id", required=True)
    proposed.add_argument("--prepared", required=True, type=Path)
    proposed.add_argument("--source-permissions", required=True, type=Path)
    for name in ("reviewer", "approved-at", "expires-at"):
        proposed.add_argument("--" + name, required=True)
    proposed.add_argument("--output", required=True, type=Path)
    return result


def main(argv=None):
    try:
        args = vars(parser().parse_args(argv))
        command = args.pop("command")
        if command == "request":
            args["source_permissions"] = io.parse_json(io.read_file(args["source_permissions"], 64 * 1024))
        from app.config import load_settings
        print(json.dumps({"prepare": prepare, "validate": validate, "request": request}[command](load_settings(), **args), sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"error": "graph_b_publication_preparation_failed", "publication_performed": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
