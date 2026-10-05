#!/usr/bin/env python3
"""Prepare and accept independent multi-source publication approvals, locally.

This trusted operator command never signs, creates a signing key or activates a
graph. Its inputs and outputs are confidential, including selections of public law.
"""

import importlib.util
import json
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def _module(name, script):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / script)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


preparation = _module("publication_source_set_preparation", "prepare_review_set.py")
io = preparation.io


@contextmanager
def current_packet(settings, packet, operator_id):
    from app.public_sources import PublicSourceStore
    from app.release_set_preparation import compile_review_set
    from app.release_snapshot import readonly_store
    from app.release_snapshot_set import locked_snapshot_set

    ontology_sha = preparation._ontology_digest(ROOT / "ontology")
    with readonly_store(settings) as store:
        files, fingerprint = preparation._read_packet(packet, store)
        request = preparation._request(io.parse_json(files["binding.json"]), operator_id)
        with locked_snapshot_set(store, PublicSourceStore(settings.public_source_dir),
                                 operator_id=operator_id, request=request) as snapshot:
            rebuilt, summary = compile_review_set(
                snapshot, io.parse_json(files["registry.json"]), io.parse_json(files["resolutions.json"]),
                {Path(name).stem: raw for name, raw in files.items() if name.startswith("private-evidence/")},
                ROOT / "ontology")
            if rebuilt != files or summary["rdf_generated"] is not True:
                raise ValueError("An exact current unblocked source-set packet is required")
            preparation._same_ontology(ROOT / "ontology", ontology_sha)
            yield store, files, fingerprint, snapshot
            if preparation._read_packet(packet, store) != (files, fingerprint):
                raise ValueError("Source-set packet changed during independent review")
            preparation._same_ontology(ROOT / "ontology", ontology_sha)
        if preparation._read_packet(packet, store) != (files, fingerprint):
            raise ValueError("Source-set packet changed at final validation")
        preparation._same_ontology(ROOT / "ontology", ontology_sha)


def _verify_output(directory, files, *, max_depth=4):
    """Check exact private output bytes and inventory, including extra directories."""
    io._inventory(files, max_depth=max_depth)
    root = io.checked_path(directory)
    expected = set(files)
    directories = {str(parent) for name in expected for parent in Path(name).parents if str(parent) != "."}
    actual, count = set(), 0
    for path in root.rglob("*"):
        count += 1
        if count > io.MAX_FILES * 3 or path.is_symlink():
            raise ValueError("Invalid private output inventory")
        name = str(path.relative_to(root))
        if path.is_dir():
            if name not in directories:
                raise ValueError("Unexpected private output directory")
        else:
            actual.add(name)
    if actual != expected or any(io.read_file(root / name, io.MAX_FILE) != raw for name, raw in files.items()):
        raise ValueError("Private review output changed")


def policy(settings):
    return _module("source_set_publication_policy", "review_publication.py").policy(settings)


def candidate(settings, packet, *, operator_id, public_reviewer, reviewed_at, output):
    from app.release_set_promotion import signing_inputs

    created = None
    try:
        with current_packet(settings, packet, operator_id) as (_, files, _, _):
            ontology_sha = io.parse_json(files["review-report.json"])["input_digests"]["ontology_sha256"]
            outputs = signing_inputs(files, ontology_sha256=ontology_sha,
                                     public_reviewer=public_reviewer, reviewed_at=reviewed_at)
            io._inventory(outputs)
            created = io.atomic_packet(output, outputs)
            _verify_output(output, outputs)
        _verify_output(output, outputs)
    except BaseException:
        io._remove_own_output(output, created)
        raise
    return {"candidate_created": True, "signed": False, "publication_eligible": False}


def request(settings, prepared, *, packet, operator_id, trusted_review_key, reviewer,
            approved_at, expires_at, source_permissions, output):
    from app.graph_release import _load_serving
    from app.release_set_authorization import (
        build_set_authorization_body,
        match_public_bundle,
        validate_source_permissions,
    )

    created = None
    try:
        with current_packet(settings, packet, operator_id) as (_, files, fingerprint, snapshot):
            info = _load_serving().validate_prepared(prepared, trusted_review_key)
            match_public_bundle(files, info, ROOT / "ontology")
            epoch = io.read_file(settings.data_dir / "publication-epoch", 37).decode("ascii").removesuffix("\n")
            body = build_set_authorization_body(info, files, fingerprint, epoch, reviewer,
                                                approved_at, expires_at, source_permissions)
            validate_source_permissions(body, snapshot)
            outputs = {"authorization-body.json": io.canonical(body)}
            io._inventory(outputs)
            created = io.atomic_packet(output, outputs)
            _verify_output(output, outputs)
        _verify_output(output, outputs)
    except BaseException:
        io._remove_own_output(output, created)
        raise
    return {"authorization_requested": True, "signed": False, "publication_eligible": False}


def accept(settings, prepared, *, packet, operator_id, trusted_review_key, authorization):
    from app.graph_release import _load_serving
    from app.public_sources import PublicSourceStore
    from app.release_authorization import ReleaseAuthorization
    from app.release_set_authorization import MAX_AUTHORIZATION
    from app.release_snapshot import readonly_store

    info = _load_serving().validate_prepared(prepared, trusted_review_key)
    root = io.checked_path(settings.data_dir / "release-authorizations")
    if not root.is_dir():
        raise ValueError("Initialize the existing publication policy first")
    destination = root / info["release_id"]
    envelope = io.read_file(authorization, MAX_AUTHORIZATION)
    created, stage = None, None
    try:
        stage = Path(tempfile.mkdtemp(prefix=".source-set-authorization-", dir=root))
        with current_packet(settings, packet, operator_id) as (store, files, _, _):
            content = {"authorization.json": envelope,
                       **{"packet/" + name: raw for name, raw in io.sealed_files(
                           files, store, schema_version=preparation.PACKET_SCHEMA).items()}}
            io._inventory(content, max_depth=5)
            io.atomic_packet(stage / info["release_id"], content, max_depth=5)
            _verify_output(stage / info["release_id"], content, max_depth=5)
        with readonly_store(settings) as store:
            arguments = (store, PublicSourceStore(settings.public_source_dir))
            gate = ReleaseAuthorization(*arguments, stage, trusted_review_key, ROOT / "ontology",
                                        settings.data_dir / "publication-epoch")
            # The dispatcher verifies the distinct signed schema and every source
            # while holding the source-set locks through the durable write.
            with gate.guard(info, "install"):
                created = io.atomic_packet(destination, content, max_depth=5)
                _verify_output(destination, content, max_depth=5)
            durable = ReleaseAuthorization(*arguments, root, trusted_review_key, ROOT / "ontology",
                                           settings.data_dir / "publication-epoch")
            with durable.guard(info, "read"):
                _verify_output(destination, content, max_depth=5)
        _verify_output(destination, content, max_depth=5)
        shutil.rmtree(stage)
        stage = None
    except BaseException:
        io._remove_own_output(destination, created)
        raise
    finally:
        if stage is not None:
            shutil.rmtree(stage)
    return {"authorization_accepted": True, "release_id": info["release_id"], "publication_performed": False}


def parser():
    result = preparation.Parser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True, parser_class=preparation.Parser)
    commands.add_parser("init-policy")
    preview = commands.add_parser("candidate")
    preview.add_argument("packet", type=Path)
    preview.add_argument("--public-reviewer", required=True)
    preview.add_argument("--reviewed-at", required=True)
    preview.add_argument("--output", required=True, type=Path)
    proposal = commands.add_parser("request")
    accepted = commands.add_parser("accept")
    for command in (preview, proposal, accepted):
        command.add_argument("--operator-id", required=True)
    for command in (proposal, accepted):
        command.add_argument("prepared", type=Path)
        command.add_argument("--packet", required=True, type=Path)
        command.add_argument("--trusted-review-key", required=True, type=Path)
    for name in ("reviewer", "approved-at", "expires-at"):
        proposal.add_argument("--" + name, required=True)
    proposal.add_argument("--source-permissions", required=True, type=Path)
    proposal.add_argument("--output", required=True, type=Path)
    accepted.add_argument("--authorization", required=True, type=Path)
    return result


def main(argv=None):
    try:
        args = vars(parser().parse_args(argv))
        command = args.pop("command")
        if command == "request":
            # Bounded, duplicate-key rejecting JSON; semantic and per-source proof
            # checks run against the current locked source set before any output.
            args["source_permissions"] = io.parse_json(io.read_file(args["source_permissions"], 64 * 1024))
        from app.config import load_settings

        operation = {"init-policy": policy, "candidate": candidate, "request": request, "accept": accept}[command]
        print(json.dumps(operation(load_settings(), **args), sort_keys=True, allow_nan=False))
        return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"error": "source_set_publication_review_failed", "publication_performed": False}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
