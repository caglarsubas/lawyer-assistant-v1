"""TEST-ONLY RDF and ephemeral signing keys. No legal source or actual review is used."""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = ROOT / "ontology"
SPEC = importlib.util.spec_from_file_location("preparation_gate_test_releases", ONTOLOGY / "releases.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)

MARKERS = [Literal(True), Literal(False), Literal("true"), Literal("false"), Literal("untrusted marker"),
           Literal("0", datatype=XSD.integer), URIRef("urn:test-only:not-a-boolean")]


def inputs():
    # Unconnected metadata must still block publication. The check cannot rely
    # on finding an assertion, SHACL class or known resource type first.
    return {family: Graph() for family in release.FAMILIES}


@pytest.mark.parametrize("family", release.FAMILIES)
@pytest.mark.parametrize("marker", MARKERS, ids=["boolean-true", "boolean-false", "string-true", "string-false",
                                                 "arbitrary-string", "integer-zero", "iri-value"])
@pytest.mark.parametrize("verified", [False, True], ids=["unsigned", "trusted-review"])
def test_marker_presence_blocks_every_family_before_shacl(family, marker, verified, monkeypatch):
    graphs = inputs()
    graphs[family].add((URIRef("urn:test-only:unconnected-preparation"), release.LA.reviewPreparationOnly, marker))

    def forbidden_shacl(*args, **kwargs):
        pytest.fail("Review-only publication rejection must run before SHACL")

    monkeypatch.setattr(release._validation, "validate_graph", forbidden_shacl)
    with pytest.raises(ValueError, match="(?i)preparation|review.only"):
        release.check_data(graphs, ONTOLOGY, {"verified": verified})


def test_unmarked_empty_engineering_graphs_retain_normal_validation():
    checked = release.check_data(inputs(), ONTOLOGY, {"verified": False})
    assert checked["assertions"] == 0
    assert checked["artifacts"] == checked["representations"] == {}


def trust_and_attestation(tmp_path, graph_paths):
    key = Ed25519PrivateKey.generate()
    public = tmp_path / "TEST-ONLY-review-public.pem"
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                   serialization.PublicFormat.SubjectPublicKeyInfo))
    body = {"reviewer": "TEST ONLY - no actual legal review", "reviewed_at": "2025-01-01T00:00:00Z",
            "decision": "approve", "scope": "national_ontology_and_assertions",
            "ontology_sha256": release.ontology_digest(ONTOLOGY),
            "input_graphs_sha256": {family: release.file_hash(path) for family, path in graph_paths.items()}}
    attestation = tmp_path / "TEST-ONLY-review-attestation.json"
    write_attestation(attestation, body, key)
    assert release.check_review_attestation(attestation, public, body)["verified"] is True
    return key, public, attestation, body


def write_attestation(path, body, key):
    path.write_bytes(release.canonical({"algorithm": "Ed25519", "body": body,
                                       "signature": base64.b64encode(key.sign(release.canonical(body))).decode()}))


@pytest.mark.parametrize("family", release.FAMILIES)
@pytest.mark.parametrize("marker", [Literal(True), Literal(False), Literal("false")],
                         ids=["boolean-true", "boolean-false", "string-false"])
def test_exact_trusted_signature_cannot_admit_a_preparation_input(tmp_path, family, marker):
    graphs = inputs()
    graphs[family].add((URIRef("urn:test-only:preparation"), release.LA.reviewPreparationOnly, marker))
    paths = {}
    for name, graph in graphs.items():
        paths[name] = tmp_path / f"{name}.ttl"
        graph.serialize(paths[name], format="turtle")
    _, public, attestation, _ = trust_and_attestation(tmp_path, paths)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    destination = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="(?i)preparation|review.only"):
        release.create_bundle(ONTOLOGY, paths, evidence, destination, attestation, public)
    assert not destination.exists()


@pytest.mark.parametrize("family", release.FAMILIES)
def test_bundle_revalidation_rejects_copied_draft_even_after_all_hashes_and_signature_are_updated(tmp_path, family):
    paths = {}
    for name in release.FAMILIES:
        paths[name] = tmp_path / f"{name}.ttl"
        paths[name].write_text("# TEST ONLY: empty engineering graph\n", encoding="utf-8")
    key, public, attestation, body = trust_and_attestation(tmp_path, paths)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    destination = tmp_path / "test-bundle"
    original = release.create_bundle(ONTOLOGY, paths, evidence, destination, attestation, public)
    assert original["review"]["verified"] is True and original["assertions"] == 0
    for path in destination.rglob("*"):
        if path.is_file():
            path.chmod(0o600)
    marker = '<urn:test-only:copied-draft> <https://lawyer-assistant.local/ontology/reviewPreparationOnly> false .\n'
    # A valid review signature plus internally consistent graph partitions and
    # inventory must not bypass the semantic review-preparation gate.
    for relative in (f"inputs/{family}.ttl", f"graphs/{family}.proposed.ttl", f"graphs/{family}.reviewed.ttl"):
        (destination / relative).write_text(marker, encoding="utf-8")
    manifest = json.loads((destination / "manifest.json").read_bytes())
    manifest["input_graphs_sha256"][family] = release.file_hash(destination / f"inputs/{family}.ttl")
    body["input_graphs_sha256"] = manifest["input_graphs_sha256"]
    write_attestation(destination / "review-attestation.json", body, key)
    manifest["files"] = {relative: release.file_hash(destination / relative) for relative in manifest["files"]}
    raw = release.canonical(manifest)
    (destination / "manifest.json").write_bytes(raw)
    (destination / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
    assert release.check_review_attestation(destination / "review-attestation.json", public, manifest)["verified"]
    with pytest.raises(ValueError, match="(?i)preparation|review.only"):
        release.validate_bundle(destination, public)
