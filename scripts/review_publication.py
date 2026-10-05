#!/usr/bin/env python3
"""Trusted offline publication review coordinator. Never creates signing keys.

All outputs remain private. Independent signatures are supplied by the operator;
this program cannot perform legal review or infer deployment-wide source rights.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
SPEC = importlib.util.spec_from_file_location("publication_preparation_io", ROOT / "scripts" / "prepare_legal_review.py")
io = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(io)


@contextmanager
def current_packet(settings, packet, operator_id):
    from app.public_sources import PublicSourceStore
    from app.release_preparation import compile_review
    from app.release_snapshot import locked_snapshot, readonly_store

    with readonly_store(settings) as store:
        files, fingerprint = io.read_packet(packet, store)
        binding = io.parse_json(files["binding.json"])
        if binding["operator_id"] != operator_id:
            raise ValueError("Current source review owner is required")
        with locked_snapshot(store, PublicSourceStore(settings.public_source_dir), operator_id=operator_id,
                             source_id=binding["source_id"],
                             expected_source_review_revision=binding["source_review_revision"],
                             expected_mapping_revision=binding["mapping_revision"]) as snapshot:
            rebuilt, _ = compile_review(snapshot, io.parse_json(files["registry.json"]),
                                        io.parse_json(files["resolutions.json"]),
                                        {Path(name).stem: raw for name, raw in files.items()
                                         if name.startswith("private-evidence/")}, ROOT / "ontology")
            if rebuilt != files:
                raise ValueError("Preparation is not current")
            yield store, files, fingerprint
            if io.read_packet(packet, store) != (files, fingerprint):
                raise ValueError("Preparation changed during review operation")


def policy(settings):
    """Create once, outside normal app startup; a restore requires explicit rotation."""
    directory = io.checked_path(settings.data_dir)
    if not directory.is_dir():
        raise ValueError("Existing private data directory is required")
    root = io.checked_path(directory / "release-authorizations")
    root.mkdir(mode=0o700, exist_ok=True)
    if not root.is_dir():
        raise ValueError("Private authorization directory is invalid")
    root.chmod(0o700)
    path = directory / "publication-epoch"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write((str(uuid.uuid4()) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return {"policy_initialized": True, "publication_performed": False}


def candidate(settings, packet, *, operator_id, public_reviewer, reviewed_at, output):
    from app.release_promotion import signing_inputs

    created = None
    try:
        with current_packet(settings, packet, operator_id) as (_, files, _):
            ontology_sha = io.parse_json(files["review-report.json"])["input_digests"]["ontology_sha256"]
            outputs = signing_inputs(files, ontology_sha256=ontology_sha,
                                     public_reviewer=public_reviewer, reviewed_at=reviewed_at)
            created = io.atomic_packet(output, outputs)
            if any(io.read_file(Path(output) / name, io.MAX_FILE) != raw for name, raw in outputs.items()):
                raise ValueError("Signing inputs changed during output")
    except BaseException:
        io._remove_own_output(output, created)
        raise
    return {"candidate_created": True, "signed": False, "publication_eligible": False}


def request(settings, prepared, *, packet, operator_id, trusted_review_key, reviewer,
            approved_at, expires_at, audience_evidence_sha256, output):
    from app.graph_release import _load_serving
    from app.release_authorization import build_authorization_body
    from app.release_promotion import promoted_graphs

    created = None
    try:
        with current_packet(settings, packet, operator_id) as (_, files, fingerprint):
            info = _load_serving().validate_prepared(prepared, trusted_review_key)
            for family, raw in promoted_graphs(files, info["review"]["reviewer"], info["review"]["reviewed_at"]).items():
                if io.read_file(info["bundle_path"] / "inputs" / (family + ".ttl"), io.MAX_FILE) != raw:
                    raise ValueError("Signed public inputs differ from the current preparation")
            epoch = io.read_file(settings.data_dir / "publication-epoch", 64).decode().strip()
            body = build_authorization_body(info, files, fingerprint, epoch, reviewer,
                                            approved_at, expires_at, audience_evidence_sha256)
            created = io.atomic_packet(output, {"authorization-body.json": io.canonical(body)})
            if io.read_file(Path(output) / "authorization-body.json", io.MAX_JSON) != io.canonical(body):
                raise ValueError("Authorization request changed during output")
    except BaseException:
        io._remove_own_output(output, created)
        raise
    return {"authorization_requested": True, "signed": False, "publication_eligible": False}


def accept(settings, prepared, *, packet, operator_id, trusted_review_key, authorization):
    from app.graph_release import _load_serving
    from app.public_sources import PublicSourceStore
    from app.release_authorization import ReleaseAuthorization
    from app.release_snapshot import readonly_store

    serving = _load_serving()
    info = serving.validate_prepared(prepared, trusted_review_key)
    root = io.checked_path(settings.data_dir / "release-authorizations")
    if not root.is_dir():
        raise ValueError("Initialize the private publication policy first")
    destination = root / info["release_id"]
    envelope = io.read_file(authorization, io.MAX_JSON)
    created = None
    # The record becomes usable only after signature/freshness checks. Stage under
    # an unpredictable private root first; never temporarily install an unverified record.
    import shutil
    import tempfile
    stage = Path(tempfile.mkdtemp(prefix=".authorization-", dir=root))
    try:
        with current_packet(settings, packet, operator_id) as (store, files, _):
            content = {"authorization.json": envelope,
                       **{"packet/" + name: raw for name, raw in io.sealed_files(files, store).items()}}
        io.atomic_packet(stage / info["release_id"], content)
        with readonly_store(settings) as store:
            gate = ReleaseAuthorization(store, PublicSourceStore(settings.public_source_dir), stage,
                                        trusted_review_key, ROOT / "ontology", settings.data_dir / "publication-epoch")
            with gate.guard(info, "install"):
                created = io.atomic_packet(destination, content)
            # Validate the exact durable record after installation as well.
            durable = ReleaseAuthorization(store, PublicSourceStore(settings.public_source_dir), root,
                                           trusted_review_key, ROOT / "ontology", settings.data_dir / "publication-epoch")
            with durable.guard(info, "read"):
                pass
    except BaseException:
        io._remove_own_output(destination, created)
        raise
    finally:
        shutil.rmtree(stage)
    return {"authorization_accepted": True, "release_id": info["release_id"], "publication_performed": False}


def parser():
    result = io.SafeParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
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
    for field in ("reviewer", "approved-at", "expires-at", "audience-evidence-sha256"):
        proposal.add_argument("--" + field, required=True)
    proposal.add_argument("--output", required=True, type=Path)
    accepted.add_argument("--authorization", required=True, type=Path)
    return result


def main(argv=None):
    from app.config import load_settings
    try:
        args = vars(parser().parse_args(argv))
        command = args.pop("command")
        operation = {"init-policy": policy, "candidate": candidate, "request": request, "accept": accept}[command]
        print(json.dumps(operation(load_settings(), **args), sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print("Publication review stopped: invalid signature, scope, current review or private storage. "
              "No graph activation was performed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
