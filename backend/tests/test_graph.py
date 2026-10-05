"""Graph boundaries and legal-reasoning pitfalls, using SYNTHETIC records only."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from pyshacl import validate
from rdflib import OWL, RDF, RDFS, XSD, Graph, Literal, Namespace

from app.graph import NS, TOOL_NAMES, GraphBackendError, GraphService, valid_on

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = ROOT / "ontology"
LA = Namespace(NS)
FX = Namespace("urn:synthetic:lawyer-assistant:")


def schema() -> Graph:
    result = Graph()
    for file in sorted((ONTOLOGY / "modules").glob("*.ttl")):
        result.parse(file, format="turtle")
    result.parse(ONTOLOGY / "domains.ttl", format="turtle")
    return result


def fixture() -> Graph:
    return Graph().parse(ONTOLOGY / "fixtures" / "competency.ttl", format="turtle")


def conforms(data: Graph) -> bool:
    return bool(
        validate(
            data,
            shacl_graph=Graph().parse(ONTOLOGY / "shapes.ttl", format="turtle"),
            ont_graph=schema(),
            inference="rdfs",
            advanced=True,
        )[0]
    )


def corpus_for_query_tests() -> Graph:
    """In-memory simulation of an import, NEVER persisted or served by the app.

    Flip fixture eligibility flags in this isolated test copy to exercise the real
    production query filters. Labels/IRIs remain conspicuously SYNTHETIC.
    """
    result = schema() + fixture()
    for item in list(result.subjects(LA.synthetic, Literal(True))):
        result.set((item, LA.synthetic, Literal(False)))
    result.set((FX.artifact, LA.rightsStatus, Literal("permitted")))
    return result


def local_adapter(monkeypatch, corpus: Graph) -> GraphService:
    service = GraphService(ONTOLOGY, "http://127.0.0.1:3030")

    def select(_graph, query):
        # rdflib executes exactly the parameterized SELECT sent to Fuseki.
        return json.loads(corpus.query(query).serialize(format="json"))["results"]["bindings"]

    monkeypatch.setattr(service, "_select", select)
    return service


def test_catalog_is_broad_but_unreviewed_and_does_not_claim_data():
    service = GraphService(ONTOLOGY)
    catalog = service.catalog()
    assert catalog["review_status"] == "unreviewed"
    assert len(catalog["classes"]) >= 120
    assert len(catalog["relations"]) >= 100
    assert {"contracts", "commercial", "employment", "criminal", "tax", "immigration"} <= {
        d["key"] for d in catalog["domains"]
    }
    assert catalog["coverage"]["corpus"]["status"] == "not_loaded"
    assert catalog["coverage"]["corpus"]["total_expected"] is None
    assert catalog["coverage"]["ontology"]["national_legal_review_complete"] is False
    assert catalog["historical_scope"]["from_year"] == 1920


def test_catalog_exploration_never_loads_fixture_or_implies_historical_version():
    service = GraphService(ONTOLOGY)
    result = service.explore("Provision", as_of="1925-01-01")
    assert result["mode"] == "catalog"
    assert result["nodes"]
    assert all(n["type"] == "ontology_class" and not n["legal_usable"] for n in result["nodes"])
    assert "urn:synthetic" not in json.dumps(result)
    unresolved = service.tool("resolve_authority", {"identifier": str(FX.provision), "as_of": "2023-01-01"})
    assert unresolved["nodes"] == [] and unresolved["edges"] == []


def test_fixture_is_shacl_conformant_but_stays_synthetic():
    data = fixture()
    assert conforms(data)
    assert all((a, LA.synthetic, Literal(True)) in data for a in data.subjects(RDF.type, LA.Assertion))


@pytest.mark.parametrize(
    "failure",
    [
        "missing_evidence",
        "unreviewed_approval",
        "invalid_interval",
        "unknown_version",
        "private_leak",
        "wrong_range",
        "type_instance",
    ],
)
def test_shacl_rejects_legal_reasoning_pitfalls(failure):
    data = fixture()
    assertion = FX["version-link-a"]
    if failure == "missing_evidence":
        data.remove((assertion, LA.evidence, None))
    elif failure == "unreviewed_approval":
        data.set((assertion, LA.claimStatus, Literal("legally_reviewed")))
    elif failure == "invalid_interval":
        data.set((assertion, LA.validTo, Literal("1919-01-01", datatype=XSD.date)))
    elif failure == "unknown_version":
        data.set((FX["cites-a"], LA.predicate, LA.applies))
        data.set((FX["cites-a"], LA.object, FX.unknown))
    elif failure == "private_leak":
        data.set((FX.provision, LA.scope, Literal("private")))
    elif failure == "wrong_range":
        data.set((assertion, LA.object, FX.institution))
    elif failure == "type_instance":
        data.add((LA.Institution, RDF.type, LA.Institution))
        data.add((LA.Institution, RDF.type, OWL.Class))
    assert not conforms(data)


def test_exact_version_boundary_and_unknown_validity():
    assert valid_on("1920-01-01", "2024-01-01", "2023-12-31")
    assert not valid_on("1920-01-01", "2024-01-01", "2024-01-01")
    assert not valid_on("2024-01-01", None, "2024-01-01")
    assert valid_on("2024-01-01", None, "2024-01-01", end_status="open_ended", checked_through="2024-02-01")
    assert not valid_on(None, None, "2024-01-01")
    assert not valid_on("1920-01-01", None, "2024-01-01", "unknown")


@pytest.mark.parametrize("as_of,expected", [("2023-12-31", "version-a"), ("2024-01-01", "version-b")])
def test_real_sparql_resolves_exact_as_of_version(monkeypatch, as_of, expected):
    service = local_adapter(monkeypatch, corpus_for_query_tests())
    result = service.tool(
        "resolve_authority",
        {"identifier": str(FX.provision), "as_of": as_of, "known_at": "2026-02-01T00:00:00Z"},
    )
    assert [e["target"] for e in result["edges"]] == [str(FX[expected])]
    assert all(e["evidence"] and not e["legal_usable"] for e in result["edges"])


def test_transaction_time_cannot_see_not_yet_recorded_assertion(monkeypatch):
    service = local_adapter(monkeypatch, corpus_for_query_tests())
    result = service.tool(
        "resolve_authority",
        {"identifier": str(FX.provision), "as_of": "2023-01-01", "known_at": "2025-12-31T23:59:59Z"},
    )
    assert result["edges"] == []


def test_actual_synthetic_flags_are_never_served(monkeypatch):
    service = local_adapter(monkeypatch, schema() + fixture())
    assert service.explore(graph="structure", as_of="2025-01-01")["edges"] == []


def test_unresolved_version_is_not_substituted_with_latest(monkeypatch):
    corpus = corpus_for_query_tests()
    corpus.set((FX["cites-a"], LA.predicate, LA.applies))
    corpus.set((FX["cites-a"], LA.object, FX.unknown))
    service = local_adapter(monkeypatch, corpus)
    result = service.tool(
        "expand_authorities", {"entity_id": str(FX.decision), "graph": "jurisprudence", "as_of": "2025-01-01"}
    )
    assert result["edges"] == []


def test_citation_is_not_application_or_support(monkeypatch):
    service = local_adapter(monkeypatch, corpus_for_query_tests())
    result = service.tool(
        "expand_authorities", {"entity_id": str(FX.decision), "graph": "jurisprudence", "as_of": "2023-02-01"}
    )
    assert [e["predicate_code"] for e in result["edges"]] == ["cites"]
    assert not result["edges"][0]["legal_usable"]


def test_public_traversal_does_not_follow_private_nodes(monkeypatch):
    corpus = corpus_for_query_tests()
    corpus.set((FX["version-a"], LA.scope, Literal("private")))
    service = local_adapter(monkeypatch, corpus)
    assert (
        service.tool("resolve_authority", {"identifier": str(FX.provision), "as_of": "2023-01-01"})["edges"]
        == []
    )


def test_two_hop_expansion_stops_before_third_hop(monkeypatch):
    corpus = corpus_for_query_tests()
    for index in range(4):
        node = FX[f"node-{index}"]
        corpus.add((node, RDF.type, LA.Institution))
        corpus.add((node, LA.scope, Literal("public")))
        corpus.add((node, RDFS.label, Literal(f"SYNTHETIC institution {index}")))
        if index == 0:
            continue
        edge = FX[f"edge-{index}"]
        for _, predicate, obj in list(corpus.triples((FX.succession, None, None))):
            corpus.add((edge, predicate, obj))
        corpus.set((edge, LA.subject, FX[f"node-{index - 1}"]))
        corpus.set((edge, LA.object, node))
    service = local_adapter(monkeypatch, corpus)
    result = service.tool(
        "expand_authorities", {"entity_id": str(FX["node-0"]), "hops": 2, "as_of": "2025-01-01"}
    )
    assert {e["id"] for e in result["edges"]} == {str(FX["edge-1"]), str(FX["edge-2"])}


@pytest.mark.parametrize(
    "name,payload",
    [
        ("sparql", {"query": "SELECT * WHERE {?s ?p ?o}"}),
        ("locate_issues", {"query": "contract", "sparql": "DROP ALL"}),
        ("expand_authorities", {"entity_id": str(FX.provision), "hops": 3}),
        ("expand_authorities", {"entity_id": str(FX.provision), "limit": 101}),
        ("expand_authorities", {"entity_id": str(FX.provision), "limit": True}),
        ("expand_authorities", {"entity_id": "<urn:a> } UNION { ?s ?p ?o"}),
        ("resolve_authority", {"identifier": "x", "as_of": "2026-02-30"}),
        ("resolve_authority", {"identifier": "x", "known_at": "2026-01-01"}),
        ("get_coverage", {"graph": "private"}),
    ],
)
def test_tools_reject_unbounded_or_untyped_requests(name, payload):
    with pytest.raises(ValueError):
        GraphService(ONTOLOGY).tool(name, payload)


def test_search_input_is_sparql_literal_not_executable(monkeypatch):
    service = local_adapter(monkeypatch, corpus_for_query_tests())
    result = service.explore('" } UNION { ?s ?p ?o } #', as_of="2025-01-01")
    assert result["edges"] == []


def test_unavailable_backend_is_not_empty_success_or_fixture_fallback(monkeypatch):
    service = GraphService(ONTOLOGY, "http://127.0.0.1")

    def fail(*_args):
        raise GraphBackendError("offline")

    monkeypatch.setattr(service, "_select", fail)
    assert service.explore()["mode"] == "unavailable"
    coverage = service.coverage()
    assert coverage["mode"] == "unavailable"
    assert coverage["corpus"]["source_artifacts"] is None
    assert coverage["corpus"]["status"] == "unavailable"


def test_tool_allowlist_matches_catalog():
    assert set(GraphService(ONTOLOGY).catalog()["tool_allowlist"]) == TOOL_NAMES


def test_catalog_returns_copies_and_cannot_mutate_review_gate():
    service = GraphService(ONTOLOGY)
    catalog = service.catalog()
    catalog["review_status"] = "legally_reviewed"
    catalog["classes"].clear()
    assert service.catalog()["review_status"] == "unreviewed"
    assert service.catalog()["classes"]


def release_tools():
    spec = importlib.util.spec_from_file_location("ontology_release_tests", ONTOLOGY / "releases.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def empty_release_inputs(tmp_path):
    paths = {}
    for family in ("structure", "jurisprudence"):
        path = tmp_path / f"{family}.ttl"
        path.write_text("# Empty test input: no actual legal records.\n")
        paths[family] = path
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    return paths, evidence


def test_offline_bundle_is_staged_blocked_and_refuses_overwrite(tmp_path):
    release = release_tools()
    paths, evidence = empty_release_inputs(tmp_path)
    output = tmp_path / "snapshot"
    result = release.create_bundle(ONTOLOGY, paths, evidence, output)
    assert result["valid"] and result["assertions"] == 0
    assert not result["legal_publication_eligible"]
    assert result["runtime_mutation"] is False
    assert "blocked" in result["release_status"]
    assert release.validate_bundle(output)["bundle_sha256"] == result["bundle_sha256"]
    with pytest.raises(ValueError, match="already exists"):
        release.create_bundle(ONTOLOGY, paths, evidence, output)


def test_offline_bundle_detects_tampering(tmp_path):
    release = release_tools()
    paths, evidence = empty_release_inputs(tmp_path)
    output = tmp_path / "snapshot"
    release.create_bundle(ONTOLOGY, paths, evidence, output)
    changed = output / "inputs" / "structure.ttl"
    changed.chmod(0o644)
    changed.write_text("# Unauthorized modification\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        release.validate_bundle(output)


def test_offline_bundle_rejects_synthetic_fixture_before_writing(tmp_path):
    release = release_tools()
    paths, evidence = empty_release_inputs(tmp_path)
    paths["structure"] = ONTOLOGY / "fixtures" / "competency.ttl"
    output = tmp_path / "snapshot"
    with pytest.raises(ValueError, match="Synthetic"):
        release.create_bundle(ONTOLOGY, paths, evidence, output)
    assert not output.exists()


def test_offline_bundle_requires_physical_evidence(tmp_path):
    release = release_tools()
    paths, evidence = empty_release_inputs(tmp_path)
    graph = Graph()
    artifact = LA.unitTestArtifact
    graph.add((artifact, RDF.type, LA.SourceArtifact))
    graph.add((artifact, LA.scope, Literal("public")))
    graph.add((artifact, LA.synthetic, Literal(False)))
    graph.add((artifact, LA.rightsStatus, Literal("permitted")))
    graph.add((artifact, LA.contentHash, Literal("b" * 64)))
    graph.add((artifact, LA.fetchedAt, Literal("2026-01-01T00:00:00Z", datatype=XSD.dateTime)))
    graph.serialize(paths["structure"], format="turtle")
    with pytest.raises(ValueError, match="physical evidence"):
        release.create_bundle(ONTOLOGY, paths, evidence, tmp_path / "snapshot")


def test_offline_bundle_signature_requires_exact_input_and_explicit_trust(tmp_path):
    # Test-only key and empty data. This does not claim any real legal review.
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    release = release_tools()
    paths, evidence = empty_release_inputs(tmp_path)
    key = Ed25519PrivateKey.generate()
    key_path = tmp_path / "test-review-key.pem"
    key_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    body = {
        "reviewer": "TEST ONLY - cryptographic gate",
        "reviewed_at": "2026-01-01T00:00:00Z",
        "decision": "approve",
        "scope": "national_ontology_and_assertions",
        "ontology_sha256": release.ontology_digest(ONTOLOGY),
        "input_graphs_sha256": {family: release.file_hash(path) for family, path in paths.items()},
    }
    attestation = tmp_path / "test-attestation.json"
    attestation.write_text(
        json.dumps(
            {
                "algorithm": "Ed25519",
                "body": body,
                "signature": base64.b64encode(key.sign(release.canonical(body))).decode(),
            }
        )
    )
    with pytest.raises(ValueError, match="trusted"):
        release.create_bundle(ONTOLOGY, paths, evidence, tmp_path / "untrusted", attestation)
    result = release.create_bundle(ONTOLOGY, paths, evidence, tmp_path / "verified", attestation, key_path)
    assert result["review"]["verified"]
    assert result["runtime_mutation"] is False
    paths["structure"].write_text("# Different input\n")
    with pytest.raises(ValueError, match="different"):
        release.create_bundle(ONTOLOGY, paths, evidence, tmp_path / "changed", attestation, key_path)


@pytest.mark.parametrize("overflow", ["bytes", "deadline", "encoding"])
def test_streamed_fuseki_response_budget_and_proxy_isolation(monkeypatch, overflow):
    import app.graph as graph_module

    observed = {}
    if overflow == "deadline":
        times = iter((0.0, 16.0))
        monkeypatch.setattr(graph_module, "monotonic", lambda: next(times))

    class Response:
        headers = {"content-encoding": "gzip"} if overflow == "encoding" else {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def raise_for_status(self):
            return None

        def iter_bytes(self, chunk_size=None):
            assert chunk_size is None
            for _ in range(4):
                observed["chunks"] = observed.get("chunks", 0) + 1
                yield b"x" * 1_000_000

    class Client:
        def __init__(self, **kwargs):
            observed.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def stream(self, *_args, **_kwargs):
            observed["request_headers"] = _kwargs["headers"]
            return Response()

    monkeypatch.setattr(graph_module.httpx, "Client", Client)
    with pytest.raises(
        GraphBackendError,
        match={"bytes": "budget", "deadline": "deadline", "encoding": "Compressed"}[overflow],
    ):
        GraphService(ONTOLOGY, "http://127.0.0.1")._transport_select("structure", "SELECT ?s WHERE { ?s ?p ?o }")
    assert observed["trust_env"] is False
    assert observed["follow_redirects"] is False
    assert observed.get("chunks", 0) == {"bytes": 3, "deadline": 1, "encoding": 0}[overflow]
    assert observed["request_headers"]["Accept-Encoding"] == "identity"


@pytest.mark.parametrize("failure", ["private", "consequential_without_review", "missing_evidence"])
def test_offline_release_rejects_unsafe_assertions(tmp_path, failure):
    release = release_tools()
    paths, evidence = empty_release_inputs(tmp_path)
    data = Graph()
    if failure == "private":
        data.add((LA.unitTestNode, LA.scope, Literal("private")))
    else:
        node = LA.unitTestAssertion
        data.add((node, RDF.type, LA.Assertion))
        data.add((node, LA.scope, Literal("public")))
        data.add((node, LA.synthetic, Literal(False)))
        data.add((node, LA.graphFamily, Literal("structure")))
        data.add((node, LA.claimStatus, Literal("unreviewed")))
        data.add((node, LA.subject, LA.unitTestInstitutionA))
        data.add((node, LA.object, LA.unitTestInstitutionB))
        data.add((LA.unitTestInstitutionA, RDF.type, LA.Institution))
        data.add((LA.unitTestInstitutionB, RDF.type, LA.Institution))
        data.add((LA.unitTestInstitutionA, LA.scope, Literal("public")))
        data.add((LA.unitTestInstitutionB, LA.scope, Literal("public")))
        data.add(
            (node, LA.predicate, LA.successorOf if failure == "consequential_without_review" else LA.cites)
        )
    data.serialize(paths["structure"], format="turtle")
    with pytest.raises(
        ValueError,
        match={
            "private": "Private",
            "consequential_without_review": "Consequential",
            "missing_evidence": "SHACL",
        }[failure],
    ):
        release.create_bundle(ONTOLOGY, paths, evidence, tmp_path / "snapshot")


def test_offline_release_physically_links_and_revalidates_evidence(tmp_path):
    release = release_tools()
    paths, evidence = empty_release_inputs(tmp_path)
    physical = evidence / "unit-test-only.txt"
    physical.write_text("Unit-test bytes. No legal fact is asserted.")
    expected = release.file_hash(physical)
    data = Graph()
    artifact = LA.unitTestArtifact
    for predicate, obj in (
        (RDF.type, LA.SourceArtifact),
        (LA.scope, Literal("public")),
        (LA.synthetic, Literal(False)),
        (LA.rightsStatus, Literal("permitted")),
        (LA.contentHash, Literal(expected)),
        (LA.fetchedAt, Literal("2026-01-01T00:00:00Z", datatype=XSD.dateTime)),
    ):
        data.add((artifact, predicate, obj))
    data.serialize(paths["structure"], format="turtle")
    output = tmp_path / "snapshot"
    result = release.create_bundle(ONTOLOGY, paths, evidence, output)
    assert result["physical_evidence_files"] == 1
    copied = output / "evidence" / f"{expected}.bin"
    assert release.file_hash(copied) == expected
    copied.chmod(0o644)
    copied.write_text("Tampered bytes")
    with pytest.raises(ValueError, match="hash mismatch"):
        release.validate_bundle(output)


def test_every_catalog_class_and_relation_has_turkish_and_english_labels():
    catalog = GraphService(ONTOLOGY).catalog()
    for item in catalog["classes"] + catalog["relations"]:
        assert item["label"] and item["label_en"]
        assert item["label"] != item["label_en"]
    assert next(c for c in catalog["classes"] if c["id"] == str(LA.Court))["label"] == "Mahkeme"


@pytest.mark.parametrize("failure", [None, "invented_quote", "wrong_locator", "wrong_raw_hash"])
def test_physical_quote_and_locator_grounding(tmp_path, failure):
    release = release_tools()
    raw = tmp_path / "original.bin"
    raw.write_bytes(b"Unit-test original bytes only")
    text_file = tmp_path / "text.txt"
    text_file.write_text("Birinci satır. İkinci satır.", encoding="utf-8")
    text = text_file.read_text(encoding="utf-8")
    raw_hash, text_hash = release.file_hash(raw), release.file_hash(text_file)
    mapping = {
        "schema_version": 1,
        "artifact_sha256": raw_hash,
        "text_sha256": text_hash,
        "extractor_version": "test-1",
        "spans": [{"locator": "test paragraph 1", "start": 0, "end": len(text)}],
    }
    if failure == "wrong_raw_hash":
        mapping["artifact_sha256"] = "a" * 64
    map_file = tmp_path / "map.json"
    map_file.write_text(json.dumps(mapping))
    map_hash = release.file_hash(map_file)
    checked = {
        "artifacts": {"urn:test:artifact": raw_hash},
        "representations": {
            "urn:test:text": {
                "artifact_id": "urn:test:artifact",
                "text_sha256": text_hash,
                "locator_map_sha256": map_hash,
                "extractor_version": "test-1",
            }
        },
        "passages": [
            {
                "id": "urn:test:passage",
                "representation_id": "urn:test:text",
                "locator": "test paragraph 1",
                "text": text[:14],
                "start": 0,
                "end": 14,
            }
        ],
    }
    if failure == "invented_quote":
        checked["passages"][0]["text"] = "This does not exist in the source."
    if failure == "wrong_locator":
        checked["passages"][0]["locator"] = "test paragraph 999"
    physical = {raw_hash: raw, text_hash: text_file, map_hash: map_file}
    if failure:
        with pytest.raises(ValueError):
            release.check_quote_grounding(checked, physical)
    else:
        release.check_quote_grounding(checked, physical)


def test_false_review_status_and_expired_target_cannot_pass_read_filters(monkeypatch):
    corpus = corpus_for_query_tests()
    corpus.set((FX["version-link-a"], LA.claimStatus, Literal("legally_reviewed")))
    service = local_adapter(monkeypatch, corpus)
    assert (
        service.tool("resolve_authority", {"identifier": str(FX.provision), "as_of": "2023-01-01"})["edges"]
        == []
    )
    corpus.set((FX["version-link-a"], LA.claimStatus, Literal("unreviewed")))
    corpus.remove((FX["version-link-a"], LA.validTo, None))
    result = service.tool("resolve_authority", {"identifier": str(FX.provision), "as_of": "2025-01-01"})
    assert [e["target"] for e in result["edges"]] == [str(FX["version-b"])]


@pytest.mark.parametrize(
    "origin",
    [
        "https://public.example",
        "http://8.8.8.8",
        "http://169.254.169.254",
        "http://0.0.0.0",
        "http://[::]",
        "http://[::ffff:127.0.0.1]",
        "http://127.0.0.1/path",
        "http://user:secret@fuseki:3030",
    ],
)
def test_graph_origin_is_local_and_cannot_federate(origin):
    with pytest.raises(ValueError):
        GraphService(ONTOLOGY, origin)
