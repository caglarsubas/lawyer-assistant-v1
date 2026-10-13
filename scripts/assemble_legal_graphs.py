#!/usr/bin/env python3
"""Trusted offline declared assembly and EXTERNAL independent final review.

No signer, production key, graph transition or serving authorization. The sealed
reviewed packet preserves final inputs; serving qualification is a separate gate.
"""
import base64
import json
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_graph_b_publication import _sources  # noqa: E402

from app.declared_graph_assembly import (  # noqa: E402
    PACKET_SCHEMA,
    Declaration,
    _fingerprint,
    current_assembly,
    trust,
)
from app.graph_release import _load_serving  # noqa: E402
from app.release_authorization import _instant, _packet_tools  # noqa: E402
from app.release_preparation import canonical, digest  # noqa: E402
from app.release_snapshot import readonly_store  # noqa: E402

io = _packet_tools()
NOTICE = canonical({"schema_version": PACKET_SCHEMA, "confidentiality": "firm_confidential",
    "coverage_scope": "declared_components_only", "national_release_serving_authorized": False})


def review_body(files, loaded, declaration, reviewer, reviewed_at):
    if (type(reviewer) is not str or not 1 <= len(reviewer) <= 300 or reviewer != reviewer.strip()
            or any(ord(char) < 32 for char in reviewer)):
        raise ValueError("An independently accountable final reviewer is required")
    reviews = [loaded["a_info"]["review"], *(item["info"]["review"] for item in loaded["jurisprudence"])]
    if reviewer in {declaration.operator_id, *(item["reviewer"] for item in reviews)}:
        raise ValueError("Final reviewer must be independent of source ownership and component review")
    approved = [loaded["structure"]["body"]["approved_at"],
                *(io.parse_json(item["raw"])["body"]["approved_at"] for item in loaded["jurisprudence"])]
    timestamp = _instant(reviewed_at)
    if timestamp > datetime.now(timezone.utc) or any(timestamp < _instant(value) for value in
            [*approved, *(item["reviewed_at"] for item in reviews)]):
        raise ValueError("Final review must follow all component reviews and permissions")
    return {"reviewer": reviewer, "reviewed_at": reviewed_at, "decision": "approve",
            "scope": "national_ontology_and_assertions", "ontology_sha256": io.parse_json(files["assembly-inputs.json"])["ontology_sha256"],
            "input_graphs_sha256": {family: digest(files["inputs/" + family + ".ttl"])
                                    for family in ("structure", "jurisprudence")}}


def _binding(declaration, loaded, files):
    return {"schema_version": PACKET_SCHEMA, "selection": declaration.model_dump(),
            "dependencies_sha256": _fingerprint(loaded), "public_inventory_sha256": digest(files["assembly-inputs.json"]),
            "national_release_serving_authorized": False}


def prepare(settings, *, selection, reviewer, reviewed_at, output):
    declaration = Declaration.model_validate(io.parse_json(io.read_file(selection, 128 * 1024)))
    created = None
    try:
        with readonly_store(settings) as store:
            with current_assembly(settings, store, _sources(settings), declaration, ROOT / "ontology") as (files, _, loaded):
                body = review_body(files, loaded, declaration, reviewer, reviewed_at)
                outputs = {**files, "public-review-body.json": canonical(body), "NOTICE.json": NOTICE,
                           "dependencies.fernet": store.seal_preparation(_binding(declaration, loaded, files))}
                created = io.atomic_packet(output, io.sealed_files(outputs, store, schema_version=PACKET_SCHEMA))
                if io.read_packet(output, store, schema_version=PACKET_SCHEMA)[0] != outputs:
                    raise ValueError("Assembly output changed")
            if io.read_packet(output, store, schema_version=PACKET_SCHEMA)[0] != outputs:
                raise ValueError("Assembly output changed after original-source checks")
    except BaseException:
        io._remove_own_output(output, created)
        raise
    return {"complete_declared_inputs_created": True, "signature_created": False,
            "final_attestation_required": True, "national_release_serving_authorized": False}


@contextmanager
def current_packet(settings, packet, *, reviewed=False):
    with readonly_store(settings) as store:
        retained, fingerprint = io.read_packet(packet, store, schema_version=PACKET_SCHEMA)
        binding = store.decode(SimpleNamespace(payload=retained["dependencies.fernet"].decode("ascii")))
        declaration = Declaration.model_validate(binding["selection"])
        with current_assembly(settings, store, _sources(settings), declaration, ROOT / "ontology") as (files, _, loaded):
            if binding != _binding(declaration, loaded, files):
                raise ValueError("Assembly dependency binding changed")
            body = io.parse_json(retained["public-review-body.json"])
            if body != review_body(files, loaded, declaration, body["reviewer"], body["reviewed_at"]):
                raise ValueError("Final review inputs differ")
            expected = {**files, "public-review-body.json": canonical(body), "NOTICE.json": NOTICE,
                        "dependencies.fernet": retained["dependencies.fernet"]}
            if reviewed:
                expected["review-attestation.json"] = retained["review-attestation.json"]
                verify_attestation(expected, loaded)
            if retained != expected:
                raise ValueError("Assembly packet has missing or extra content")
            yield store, retained, loaded
            if reviewed:
                verify_attestation(retained, loaded)
            if io.read_packet(packet, store, schema_version=PACKET_SCHEMA) != (retained, fingerprint):
                raise ValueError("Retained assembly changed during use")
        if io.read_packet(packet, store, schema_version=PACKET_SCHEMA) != (retained, fingerprint):
            raise ValueError("Retained assembly changed after source exit")


def verify_attestation(files, loaded):
    raw = files["review-attestation.json"]
    envelope = io.parse_json(raw)
    if (type(envelope) is not dict or set(envelope) != {"algorithm", "body", "signature"}
            or envelope["algorithm"] != "Ed25519" or type(envelope["signature"]) is not str
            or len(base64.b64decode(envelope["signature"], validate=True)) != 64
            or canonical(envelope["body"]) != files["public-review-body.json"]):
        raise ValueError("An exact independently signed final attestation is required")
    # Reuse the production public bundle checks (SHACL, temporal, partitions,
    # original artifacts, exact quotes), without retaining or publishing a bundle.
    with TemporaryDirectory(prefix="legal-final-review-") as scratch:
        root = Path(scratch)
        for name, value in files.items():
            if name.startswith(("inputs/", "evidence/")) or name == "review-attestation.json":
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)
        _load_serving()._release.create_bundle(ROOT / "ontology",
            {family: root / "inputs" / (family + ".ttl") for family in ("structure", "jurisprudence")},
            root / "evidence", root / "bundle", root / "review-attestation.json", loaded["paths"][3])
    if trust_material(loaded) != loaded["keys"]:
        raise ValueError("Final review trust changed")


def trust_material(loaded):
    from app.graph_b_review import configured_key_path
    return tuple((value[0], value[2]) for value in (configured_key_path(path) for path in loaded["paths"]))


def accept(settings, *, packet, attestation, output):
    raw = io.read_file(attestation, 128 * 1024)
    created = None
    try:
        with current_packet(settings, packet) as (store, retained, loaded):
            outputs = {**retained, "review-attestation.json": raw}
            verify_attestation(outputs, loaded)
            created = io.atomic_packet(output, io.sealed_files(outputs, store, schema_version=PACKET_SCHEMA))
            if (io.read_packet(output, store, schema_version=PACKET_SCHEMA)[0] != outputs
                    or io.read_file(attestation, 128 * 1024) != raw or trust(settings)[1] != loaded["keys"]):
                raise ValueError("Final review output or trust changed")
        with current_packet(settings, output, reviewed=True):
            pass
        if io.read_file(attestation, 128 * 1024) != raw:
            raise ValueError("External attestation changed after acceptance")
    except BaseException:
        io._remove_own_output(output, created)
        raise
    return {"independent_final_attestation_accepted": True, "complete_declared_assembly": True,
            "publication_performed": False, "national_release_serving_authorized": False}


def validate(settings, packet, *, reviewed=False):
    with current_packet(settings, packet, reviewed=reviewed):
        pass
    return {"current_complete_declared_assembly": True, "independent_final_attestation_verified": reviewed,
            "national_release_serving_authorized": False}


def parser():
    import argparse
    result = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = result.add_subparsers(dest="command", required=True)
    proposed = commands.add_parser("prepare", allow_abbrev=False)
    for name in ("selection", "output"):
        proposed.add_argument("--" + name, required=True, type=Path)
    for name in ("reviewer", "reviewed-at"):
        proposed.add_argument("--" + name, required=True)
    accepted = commands.add_parser("accept", allow_abbrev=False)
    for name in ("packet", "attestation", "output"):
        accepted.add_argument("--" + name, required=True, type=Path)
    checked = commands.add_parser("validate", allow_abbrev=False)
    checked.add_argument("packet", type=Path)
    checked.add_argument("--reviewed", action="store_true")
    return result


def main(argv=None):
    try:
        args = vars(parser().parse_args(argv))
        command = args.pop("command")
        from app.config import load_settings
        print(json.dumps({"prepare": prepare, "accept": accept, "validate": validate}[command](load_settings(), **args), sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"error": "declared_graph_assembly_failed", "publication_performed": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
