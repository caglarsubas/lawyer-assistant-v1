#!/usr/bin/env python3
"""Trusted local final serving candidate and unsigned bounded permission inputs.

Never signs, accepts a serving grant, installs, activates or serves a graph.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from assemble_legal_graphs import NOTICE as ASSEMBLY_NOTICE  # noqa: E402, F401
from assemble_legal_graphs import (  # noqa: E402
    current_packet,
    trust,
)
from assemble_legal_graphs import (  # noqa: E402
    review_body as review_body,
)
from assemble_legal_graphs import (  # noqa: E402
    verify_captured_attestation as verify_captured_attestation,
)
from assemble_legal_graphs import (  # noqa: E402
    verify_public_payload as verify_public_payload,
)

from app.declared_graph_assembly import _fingerprint, _public_capture, component_nodes  # noqa: E402
from app.graph_b_review import configured_key_path  # noqa: E402
from app.graph_release import _load_serving  # noqa: E402
from app.release_authorization import _instant, _packet_tools  # noqa: E402
from app.release_preparation import canonical, digest  # noqa: E402
from app.release_snapshot import REQUIRED_USES, readonly_store  # noqa: E402

io = _packet_tools()
SCHEMA = "legal-final-assembly-permission-request-v1"
NOTICE = canonical({"schema_version": SCHEMA, "confidentiality": "firm_confidential",
                    "signed": False, "national_release_serving_authorized": False})


def grant_trust(settings):
    original = trust(settings)
    path = io.checked_path(settings.graph_final_grant_trusted_key)
    key, _, fingerprint = configured_key_path(path)
    if fingerprint in {value[1] for value in original[1]}:
        raise ValueError("Independent final serving permission trust is required")
    return original, (path, key, fingerprint)


def request_checks(settings, files, loaded, reviewer, approved_at, expires_at):
    keys, grant_key = grant_trust(settings)
    if keys != (loaded["paths"], loaded["keys"]):
        raise ValueError("Final serving candidate trust changed")
    public_review = io.parse_json(files["public-review-body.json"])
    nodes = component_nodes(loaded)
    parents = [node["retained"] for node in nodes if node.get("retained")]
    disallowed = {public_review["reviewer"]}
    for node in nodes:
        disallowed.update({node["structure"]["body"]["source_binding"]["operator_id"],
            node["a_info"]["review"]["reviewer"], node["structure"]["body"]["reviewer"],
            *(item["info"]["review"]["reviewer"] for item in node["jurisprudence"]),
            *(io.parse_json(item["raw"])["body"]["reviewer"] for item in node["jurisprudence"])})
    disallowed.update(parent["payload"].info["review"]["reviewer"] for parent in parents)
    if (type(reviewer) is not str or not 1 <= len(reviewer) <= 300 or reviewer != reviewer.strip()
            or any(ord(char) < 32 for char in reviewer) or reviewer in disallowed):
        raise ValueError("Independent accountable final permission reviewer is required")
    approved, expires, now = _instant(approved_at), _instant(expires_at), datetime.now(timezone.utc)
    grants = [body for node in nodes for body in [node["structure"]["body"],
        *(io.parse_json(item["raw"])["body"] for item in node["jurisprudence"])]]
    grants += [parent["body"] for parent in parents]
    if (approved > now or approved < _instant(public_review["reviewed_at"]) or expires <= now
            or expires <= approved or expires - approved > timedelta(days=90)
            or any(expires > _instant(body["expires_at"]) or approved < _instant(body["approved_at"]) for body in grants)):
        raise ValueError("Permission request exceeds current reviewed component lifetimes")
    return grant_key


def request_body(settings, files, loaded, info, packet_hash, reviewer, approved_at, expires_at):
    grant_key = request_checks(settings, files, loaded, reviewer, approved_at, expires_at)
    inventory = io.parse_json(files["assembly-inputs.json"])
    return {"schema_version": SCHEMA, "scope": "complete_declared_release", "signed": False,
        "national_release_serving_authorized": False, "decision": "request",
        "release_id": info["release_id"], "serving_sha256": info["serving_sha256"],
        "ontology_sha256": info["ontology_sha256"], "final_review_key_sha256": info["review"]["key_sha256"],
        "final_grant_key_sha256": grant_key[2], "reviewed_packet_sha256": packet_hash,
        "public_inventory_sha256": digest(files["assembly-inputs.json"]), "dependencies_sha256": _fingerprint(loaded),
        "component_release_ids": [member["release_id"] for member in inventory["components"]],
        "publication_epoch": loaded["epoch"], "audience": "deployment_shared", "permitted_uses": sorted(REQUIRED_USES),
        "reviewer": reviewer, "approved_at": approved_at, "expires_at": expires_at}


def match_candidate(root, files, loaded):
    serving = _load_serving()
    info = serving.validate_prepared(root, loaded["paths"][3])
    if info["ontology_sha256"] != io.parse_json(files["assembly-inputs.json"])["ontology_sha256"]:
        raise ValueError("Candidate ontology differs")
    for name, raw in files.items():
        if name.startswith(("inputs/", "evidence/")) or name == "review-attestation.json":
            if io.read_file(root / "bundle" / name, io.MAX_FILE) != raw:
                raise ValueError("Candidate differs from independently reviewed final bytes")
    return info


def _outer(root):
    root = io.checked_path(root)
    actual = _load_serving()._files(root)
    expected = {"prepared/" + name for name in _load_serving()._files(root / "prepared")}
    expected |= {"permission/" + name for name in _load_serving()._files(root / "permission")}
    expected.add("NOTICE.json")
    directories = {str(parent) for name in expected for parent in Path(name).parents if str(parent) != "."}
    actual_directories = {str(path.relative_to(root)) for path in root.rglob("*") if path.is_dir()}
    if (actual != expected or actual_directories != directories or len(actual) > io.MAX_FILES
            or io.read_file(root / "NOTICE.json", 2048) != NOTICE):
        raise ValueError("Candidate root contains undeclared content")


def validate(settings, candidate):
    _outer(candidate)
    original_trust = grant_trust(settings)
    with readonly_store(settings) as reader:
        permission, permission_hash = io.read_packet(candidate / "permission", reader)
        if set(permission) != {"binding.fernet", "request.fernet", "NOTICE.json"} or permission["NOTICE.json"] != NOTICE:
            raise ValueError("Candidate permission inventory differs")
        binding = reader.decode(SimpleNamespace(payload=permission["binding.fernet"].decode("ascii")))
        body = reader.decode(SimpleNamespace(payload=permission["request.fernet"].decode("ascii")))
    if type(binding) is not dict or set(binding) != {"reviewed_packet", "reviewed_packet_sha256"}:
        raise ValueError("Candidate source review binding differs")
    packet = io.checked_path(binding["reviewed_packet"])
    verified_public = verify_public_payload(candidate / "prepared", original_trust[0][0][3])
    with current_packet(settings, packet, reviewed=True, verified_public=verified_public) as (store, files, loaded):
        _, packet_hash = io.read_packet(packet, store, schema_version="legal-declared-graph-assembly-v1")
        if packet_hash != binding["reviewed_packet_sha256"]:
            raise ValueError("Original reviewed assembly changed")
        verify_captured_attestation(files, loaded, verified_public)
        info = verified_public.info
        public_capture = verified_public.files
        expected = request_body(settings, files, loaded, info, packet_hash, body["reviewer"], body["approved_at"], body["expires_at"])
        if canonical(body) != canonical(expected):
            raise ValueError("Candidate permission request differs")
        if (io.read_packet(candidate / "permission", store) != (permission, permission_hash)
                or _public_capture(info) != public_capture):
            raise ValueError("Candidate permission or public bytes changed")
    # Only byte/trust/expiry checks after original-source exit; expensive RDF
    # validation stays inside the protected original-source transaction.
    if _public_capture(info) != public_capture:
        raise ValueError("Candidate public bytes changed after source exit")
    if (request_body(settings, files, loaded, info, packet_hash, body["reviewer"], body["approved_at"], body["expires_at"]) != body
            or grant_trust(settings) != original_trust):
        raise ValueError("Candidate dependencies changed at final validation")
    with readonly_store(settings) as reader:
        if io.read_packet(candidate / "permission", reader) != (permission, permission_hash):
            raise ValueError("Candidate permission changed after source exit")
    _outer(candidate)
    return {"current_final_serving_candidate": True, "release_id": info["release_id"],
            "signature_created": False, "national_release_serving_authorized": False}


def prepare(settings, *, packet, reviewer, approved_at, expires_at, output):
    original_trust = grant_trust(settings)
    created = None
    try:
        with current_packet(settings, packet, reviewed=True) as (store, files, loaded):
            _, packet_hash = io.read_packet(packet, store, schema_version="legal-declared-graph-assembly-v1")
            # Reject invalid reviewer/time/lifetime inputs before canonicalizing
            # a public serving candidate; repeat against final info after staging.
            request_checks(settings, files, loaded, reviewer, approved_at, expires_at)
            with TemporaryDirectory(prefix="legal-final-candidate-") as scratch:
                root = Path(scratch)
                for name, raw in files.items():
                    if name.startswith(("inputs/", "evidence/")) or name == "review-attestation.json":
                        path = root / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(raw)
                _load_serving()._release.create_bundle(ROOT / "ontology",
                    {family: root / "inputs" / (family + ".ttl") for family in ("structure", "jurisprudence")},
                    root / "evidence", root / "bundle", root / "review-attestation.json", loaded["paths"][3])
                _load_serving().prepare(root / "bundle", loaded["paths"][3], root / "prepared")
                info = match_candidate(root / "prepared", files, loaded)
                body = request_body(settings, files, loaded, info, packet_hash, reviewer, approved_at, expires_at)
                binding = {"reviewed_packet": str(io.checked_path(packet)), "reviewed_packet_sha256": packet_hash}
                private_files = {"binding.fernet": store.seal_preparation(binding), "request.fernet": store.seal_preparation(body),
                                 "NOTICE.json": NOTICE}
                outputs = {"prepared/" + name: io.read_file(root / "prepared" / name, io.MAX_FILE)
                           for name in _load_serving()._files(root / "prepared")}
                outputs.update({"permission/" + name: raw for name, raw in io.sealed_files(private_files, store).items()})
                outputs["NOTICE.json"] = NOTICE
                if len(outputs) > io.MAX_FILES or sum(map(len, outputs.values())) > io.MAX_PACKET:
                    raise ValueError("Final candidate exceeds retained output budget")
                created = io.atomic_packet(output, outputs, max_depth=5)
                _outer(output)
                match_candidate(output / "prepared", files, loaded)
                if grant_trust(settings) != original_trust:
                    raise ValueError("Final permission trust changed")
        receipt = validate(settings, output)
    except BaseException:
        io._remove_own_output(output, created)
        raise
    return {**receipt, "final_permission_signing_inputs_created": True, "publication_performed": False}


def parser():
    import argparse
    result = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = result.add_subparsers(dest="command", required=True)
    proposed = commands.add_parser("prepare", allow_abbrev=False)
    for name in ("packet", "output"):
        proposed.add_argument("--" + name, required=True, type=Path)
    for name in ("reviewer", "approved-at", "expires-at"):
        proposed.add_argument("--" + name, required=True)
    checked = commands.add_parser("validate", allow_abbrev=False)
    checked.add_argument("candidate", type=Path)
    return result


def main(argv=None):
    try:
        args = vars(parser().parse_args(argv))
        command = args.pop("command")
        from app.config import load_settings
        print(json.dumps({"prepare": prepare, "validate": validate}[command](load_settings(), **args), sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"error": "final_graph_candidate_failed", "publication_performed": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
