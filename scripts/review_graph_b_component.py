#!/usr/bin/env python3
"""Trusted offline component inclusion requests and externally signed grants.

Never creates a key/signature, installs or serves a graph. All retained selections,
credentials, audience proofs and signatures remain encrypted and firm confidential.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from fastapi import HTTPException  # noqa: E402
from prepare_graph_b_publication import _sources, current_packet  # noqa: E402

from app.graph_b_component_grants import (  # noqa: E402
    MAX_ENVELOPE,
    NOTICE,
    ComponentGrantError,
    GraphBComponentGrant,
    grant_body,
    match_grant,
    retained_files,
)
from app.graph_b_publication import PACKET_SCHEMA, match_public_component, permission_request  # noqa: E402
from app.graph_b_review import configured_key_path  # noqa: E402
from app.graph_release import _load_serving  # noqa: E402
from app.release_authorization import _packet_tools, _uuid  # noqa: E402
from app.release_snapshot import readonly_store  # noqa: E402

io = _packet_tools()


def trust(settings):
    paths = (settings.graph_trusted_review_key, settings.graph_b_review_trusted_key, settings.graph_b_component_trusted_key)
    if not all(paths):
        raise ValueError("Three independently configured trust roles are required")
    paths = tuple(io.checked_path(path) for path in paths)
    try:
        keys = tuple(configured_key_path(path) for path in paths)
    except (HTTPException, ValueError, OSError):
        raise ComponentGrantError("Current independently configured component trust could not be verified") from None
    # Role separation includes key material, not merely distinct filenames.
    if len({key[2] for key in keys}) != 3:
        raise ValueError("Independent component grant, public and private review keys are required")
    return paths, tuple((key[0], key[2]) for key in keys)


def gate(settings, store):
    return GraphBComponentGrant(store, _sources(settings), public_review_key=settings.graph_trusted_review_key,
        graph_b_review_key=settings.graph_b_review_trusted_key, component_grant_key=settings.graph_b_component_trusted_key,
        ontology_root=ROOT / "ontology", epoch_path=settings.data_dir / "publication-epoch")


def request(settings, prepared, *, packet, operator_id, reviewer, approved_at, expires_at, source_permissions, output):
    original_trust = trust(settings)
    paths, keys = original_trust
    epoch_path = settings.data_dir / "publication-epoch"
    epoch_bytes = io.read_file(epoch_path, 37)
    epoch = _uuid(epoch_bytes.decode("ascii").removesuffix("\n"))
    created = None
    try:
        with current_packet(settings, packet, operator_id) as (store, files, fingerprint, private, snapshot):
            info = _load_serving().validate_prepared(prepared, paths[0])
            info = match_public_component(files, info, paths[0], ROOT / "ontology")
            body = grant_body(permission_request(files, private, snapshot, info, packet_sha256=fingerprint, epoch=epoch,
                reviewer=reviewer, approved_at=approved_at, expires_at=expires_at, source_permissions=source_permissions), keys[2][1])
            outputs = {"grant-body.fernet": store.seal_preparation(body), "NOTICE.json": NOTICE}
            created = io.atomic_packet(output, io.sealed_files(outputs, store, schema_version=PACKET_SCHEMA))
            def recheck():
                current = match_public_component(files, info, paths[0], ROOT / "ontology")
                if (grant_body(permission_request(files, private, snapshot, current, packet_sha256=fingerprint, epoch=epoch,
                        reviewer=reviewer, approved_at=approved_at, expires_at=expires_at, source_permissions=source_permissions), keys[2][1]) != body
                        or trust(settings) != original_trust or io.read_file(epoch_path, 37) != epoch_bytes
                        or io.read_packet(output, store, schema_version=PACKET_SCHEMA)[0] != outputs):
                    raise ValueError("Current component request dependencies changed")
            recheck()
        # Original-source exit reconstruction may consume the remaining lifetime.
        recheck()
    except BaseException:
        io._remove_own_output(output, created)
        raise
    return {"signing_inputs_created": True, "signature_created": False, "national_release_serving_authorized": False}


def accept(settings, prepared, *, packet, operator_id, authorization, output):
    original_trust = trust(settings)
    paths = original_trust[0]
    raw = io.read_file(authorization, MAX_ENVELOPE)
    epoch_path = settings.data_dir / "publication-epoch"
    epoch_bytes = io.read_file(epoch_path, 37)
    epoch = _uuid(epoch_bytes.decode("ascii").removesuffix("\n"))
    created = None
    try:
        with current_packet(settings, packet, operator_id) as (store, files, fingerprint, private, snapshot):
            info = _load_serving().validate_prepared(prepared, paths[0])
            info = match_public_component(files, info, paths[0], ROOT / "ontology")
            match_grant(raw, paths[2], files, fingerprint, private, snapshot, info, epoch)
            outputs = retained_files(store, files, raw)
            created = io.atomic_packet(output, io.sealed_files(outputs, store, schema_version=PACKET_SCHEMA))
            final = match_public_component(files, info, paths[0], ROOT / "ontology")
            match_grant(raw, paths[2], files, fingerprint, private, snapshot, final, epoch)
            if (trust(settings) != original_trust or io.read_file(epoch_path, 37) != epoch_bytes
                    or io.read_file(authorization, MAX_ENVELOPE) != raw
                    or io.read_packet(output, store, schema_version=PACKET_SCHEMA)[0] != outputs):
                raise ValueError("Current component grant dependencies changed")
        # Validate the actual retained encrypted grant after the complete original
        # packet/source exit checks. No replay or success after an unknown outcome.
        with readonly_store(settings) as store, gate(settings, store).guard(info, output, purpose="inspect"):
            pass
        if trust(settings) != original_trust or io.read_file(authorization, MAX_ENVELOPE) != raw:
            raise ValueError("Component grant trust changed at acceptance")
    except BaseException:
        io._remove_own_output(output, created)
        raise
    return {"component_grant_accepted": True, "publication_performed": False, "national_release_serving_authorized": False}


def validate(settings, prepared, *, grant):
    original_trust = trust(settings)
    info = _load_serving().validate_prepared(prepared, original_trust[0][0])
    with readonly_store(settings) as store, gate(settings, store).guard(info, grant, purpose="inspect"):
        pass
    if trust(settings) != original_trust:
        raise ValueError("Component grant trust changed")
    return {"current_component_grant": True, "scope": "component_inclusion_only", "national_release_serving_authorized": False}


def parser():
    import argparse
    result = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = result.add_subparsers(dest="command", required=True)
    proposed = commands.add_parser("request", allow_abbrev=False)
    accepted = commands.add_parser("accept", allow_abbrev=False)
    checked = commands.add_parser("validate", allow_abbrev=False)
    for command in (proposed, accepted, checked):
        command.add_argument("--prepared", required=True, type=Path)
    for command in (proposed, accepted):
        command.add_argument("--packet", required=True, type=Path)
        command.add_argument("--operator-id", required=True)
        command.add_argument("--output", required=True, type=Path)
    accepted.add_argument("--authorization", required=True, type=Path)
    checked.add_argument("--grant", required=True, type=Path)
    for name in ("reviewer", "approved-at", "expires-at"):
        proposed.add_argument("--" + name, required=True)
    proposed.add_argument("--source-permissions", required=True, type=Path)
    return result


def main(argv=None):
    try:
        args = vars(parser().parse_args(argv))
        command = args.pop("command")
        if command == "request":
            args["source_permissions"] = io.parse_json(io.read_file(args["source_permissions"], 64 * 1024))
        from app.config import load_settings
        print(json.dumps({"request": request, "accept": accept, "validate": validate}[command](load_settings(), **args), sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"error": "graph_b_component_grant_failed", "publication_performed": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
