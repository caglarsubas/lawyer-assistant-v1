"""Synthetic end-to-end publication; signatures here are isolated TEST-ONLY fixtures."""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from rdflib import RDF, XSD, Graph, Literal, URIRef
from test_provision_mappings import TEXT, propose, ready, review
from test_provision_mappings import mapping as mapping_fixture
from test_provision_mappings import source as source_fixture
from test_provision_mappings import workspace as workspace_fixture
from test_release_authorization import guard, sha, signed
from test_release_snapshot import operator_id
from test_source_reviews import assess

from app.graph import GraphService
from app.graph_release import LA, RuntimeGraphRelease, _load_serving, temporal
from app.release_authorization import AuthorizationError, _packet_tools, build_authorization_body
from app.release_preparation import compile_review
from app.release_promotion import promoted_graphs
from app.release_snapshot import REQUIRED_USES, locked_snapshot, readonly_store
from app.search import PublicSearchService

mapping = mapping_fixture
source = source_fixture
workspace = workspace_fixture
ONTOLOGY = Path(__file__).resolve().parents[2] / "ontology"


@pytest.fixture
def open_authorized(mapping, tmp_path):
    app, client, sources, source_id, base = mapping
    tools = _packet_tools()
    proof = b"PRIVATE TEST-ONLY IDENTITY RIGHTS AND AUDIENCE; NEVER PUBLIC"
    proof_hash = sha(proof)
    ready(mapping, uses=sorted(REQUIRED_USES))
    assert assess(client, base + "/review", 5, "rights", evidence_refs=[
        {"reference": "PRIVATE TEST PROOF", "sha256": proof_hash}],
        permitted_uses=sorted(REQUIRED_USES)).status_code == 200
    proposed = propose(mapping, source_revision=6).json()["items"][0]
    # Deliberately use the preamble outside the reviewed provision body. This
    # proves distinct physical grounding, not the truth of synthetic legal text.
    evidence_end = TEXT.index("MADDE 1")
    assert evidence_end <= proposed["span"]["start"]
    resolution = {
        "start": proposed["span"]["start"], "end": proposed["span"]["end"],
        "instrument_ref": "PRIVATE TEST instrument", "provision_ref": "PRIVATE TEST provision",
        "provision_version_ref": "PRIVATE TEST version", "text_role": "operative_text",
        "valid_from": "2011-01-01", "valid_until": None,
        "open_ended_validity": {"checked_through": "2011-06-01", "evidence_start": 0, "evidence_end": evidence_end},
    }
    accepted = review(mapping, proposed["id"], source_revision=6, resolution=resolution)
    assert accepted.status_code == 200, accepted.text
    entities = [("urn:tr-law:instrument:open-test", "instrument", None),
                ("urn:tr-law:provision:open-test", "provision", "urn:tr-law:instrument:open-test"),
                ("urn:tr-law:provision-version:open-test", "provision_version", "urn:tr-law:provision:open-test")]
    registry = {"schema_version": "legal-identity-registry-v1", "entities": [
        {"id": identifier, "kind": kind, "parent_id": parent, "evidence_sha256": [proof_hash]}
        for identifier, kind, parent in entities]}
    resolutions = {"schema_version": "provision-identity-resolutions-v1", "items": [{
        "mapping_id": proposed["id"], "instrument_id": entities[0][0], "provision_id": entities[1][0],
        "provision_version_id": entities[2][0]}]}
    key = Ed25519PrivateKey.generate()  # TEST ONLY; temporary directory, no deployment trust.
    public_key = tmp_path / "TEST-ONLY-public.pem"
    public_key.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                       serialization.PublicFormat.SubjectPublicKeyInfo))
    epoch_path = tmp_path / "publication-epoch"
    epoch = str(uuid4())
    epoch_path.write_text(epoch + "\n", encoding="ascii")
    root = tmp_path / "release-authorizations"
    with readonly_store(app.state.settings) as store:
        with locked_snapshot(store, sources, operator_id=operator_id(app), source_id=source_id,
                             expected_source_review_revision=6, expected_mapping_revision=2) as snapshot:
            files, summary = compile_review(snapshot, registry, resolutions, {proof_hash: proof}, ONTOLOGY)
        assert summary["rdf_generated"] and not summary["blocker_codes"]
        reviewed_at = datetime.now(timezone.utc).isoformat()
        promoted = promoted_graphs(files, "TEST-ONLY PUBLIC REVIEWER", reviewed_at)
        graph_paths = {}
        for family, raw in promoted.items():
            path = tmp_path / f"{family}.ttl"
            path.write_bytes(raw)
            graph_paths[family] = path
        serving = _load_serving()
        release = serving._release
        evidence_dir = tmp_path / "public-evidence"
        evidence_dir.mkdir()
        for name in ("candidate/raw.bin", "candidate/text.txt", "candidate/locators.json"):
            raw = files[name]
            (evidence_dir / (sha(raw) + ".bin")).write_bytes(raw)
        review_body = {"reviewer": "TEST-ONLY PUBLIC REVIEWER", "reviewed_at": reviewed_at, "decision": "approve",
                       "scope": "national_ontology_and_assertions", "ontology_sha256": release.ontology_digest(ONTOLOGY),
                       "input_graphs_sha256": {family: release.file_hash(path) for family, path in graph_paths.items()}}
        attestation = tmp_path / "TEST-ONLY-attestation.json"
        signed(attestation, review_body, key, tools)
        release.create_bundle(ONTOLOGY, graph_paths, evidence_dir, tmp_path / "bundle", attestation, public_key)
        serving.prepare(tmp_path / "bundle", public_key, tmp_path / "prepared")
        info = serving.validate_prepared(tmp_path / "prepared", public_key)
        directory = root / info["release_id"]
        directory.mkdir(parents=True)
        packet = tools.sealed_files(files, store)
        tools.atomic_packet(directory / "packet", packet)
        packet_digest = sha(packet["manifest.json"])
        approved_at = datetime.now(timezone.utc)
        body = build_authorization_body(info, files, packet_digest, epoch, "PRIVATE TEST REVIEW IDENTITY",
                                        approved_at.isoformat(), (approved_at + timedelta(days=1)).isoformat(), proof_hash)
        auth_path = directory / "authorization.json"
        signed(auth_path, body, key, tools)
    fixture = {"mapping": mapping, "tools": tools, "key": key, "public_key": public_key, "root": root,
               "epoch_path": epoch_path, "auth_path": auth_path, "body": body, "files": files,
               "info": info, "packet_digest": packet_digest, "evidence_digest": proof_hash,
               "mapping_id": proposed["id"], "resolution": resolution}

    def authorization(info, action):
        return guard(fixture, info=info, action=action)

    runtime_root = tmp_path / "runtime"
    serving.install(runtime_root, tmp_path / "prepared", public_key, authorization_guard=authorization)
    serving.activate(runtime_root, info["release_id"], public_key, expected_current=None,
                     authorization_guard=authorization)
    fixture["runtime"] = RuntimeGraphRelease(runtime_root, public_key, authorization)
    fixture["runtime_root"] = runtime_root
    assert fixture["runtime"].status()["status"] == "verified"
    return fixture


def search_fixture(authorized, monkeypatch):
    runtime = authorized["runtime"]
    graph = runtime._graphs["structure"]
    assertion = next(graph.subjects(LA.predicate, LA.hasProvisionVersion))
    evidence = graph.value(assertion, LA.evidence)
    artifact = graph.value(evidence, LA.artifact)
    source = {
        "passage_id": "PRIVATE-INDEX-PASSAGE", "document_id": "PRIVATE-INDEX-DOCUMENT",
        "source_version_id": "PRIVATE-INDEX-VERSION", "source_sha256": str(graph.value(artifact, LA.contentHash)),
        "text": str(graph.value(evidence, LA.quotedText)), "title": "PRIVATE-INDEX-TITLE",
        "source_url": "https://example.gov.tr/PRIVATE-INDEX-URL", "locator": str(graph.value(evidence, LA.locator)),
        "authority_id": str(graph.value(assertion, LA.subject)), "release_id": authorized["info"]["release_id"],
        "visibility": "public", "rights_status": "permitted", "review_status": "legally_reviewed",
        # Forged future index metadata must never extend the signed horizon.
        "valid_from": "2000-01-01", "valid_to": "9999-12-31", "validity_end_status": "closed",
        "validity_checked_through": None, "validity_evidence_ids": ["PRIVATE-INDEX-VALIDITY"],
    }
    hit = {"_id": source["passage_id"], "_index": "law-public-passages", "_source": source}
    service = PublicSearchService("http://opensearch:9200", release_id=source["release_id"], graph_release=runtime)
    monkeypatch.setattr(service, "_request", lambda *args: [hit])
    return service, assertion


def test_open_review_to_signed_runtime_preserves_distinct_evidence_and_horizon(open_authorized, monkeypatch):
    fixture = open_authorized
    runtime = fixture["runtime"]
    graph = runtime._graphs["structure"]
    version = next(graph.subjects(RDF.type, LA.ProvisionVersion))
    validity = set(graph.objects(version, LA.validityEvidence))
    assert validity and not list(graph.objects(version, LA.validTo))
    for assertion in graph.subjects(RDF.type, LA.Assertion):
        assert set(graph.objects(assertion, LA.validityEvidence)) == validity
        assert validity.isdisjoint(set(graph.objects(assertion, LA.evidence)))
        for passage in validity:
            assert str(graph.value(passage, LA.quotedText)) == TEXT[:fixture["resolution"]["open_ended_validity"]["evidence_end"]]
            assert int(graph.value(passage, LA.endOffset)) <= fixture["resolution"]["start"]
    for raw in (fixture["info"]["bundle_path"] / "inputs").glob("*.ttl"):
        assert b"PRIVATE TEST" not in raw.read_bytes()
    service, assertion = search_fixture(fixture, monkeypatch)
    for day in ("2011-01-01", "2011-06-01"):
        found = service.search("SYNTHETIC", as_of=day)
        assert len(found["hits"]) == 1
        hit = found["hits"][0]
        assert hit["valid_to"] is None and hit["valid_from"] == "2011-01-01"
        assert hit["validity_end_status"] == "open_ended" and hit["validity_checked_through"] == "2011-06-01"
        assert set(hit["validity_evidence_ids"]) == {str(item) for item in validity}
        assert "PRIVATE-INDEX" not in json.dumps(found)
    for day in ("2010-12-31", "2011-06-02", "9999-12-31"):
        assert service.search("SYNTHETIC", as_of=day)["hits"] == []
        assert not runtime._eligible("structure", assertion, as_of=day)
    assert runtime._eligible("structure", assertion, as_of="2011-06-02", history=True)
    assert runtime._eligible("structure", assertion, as_of="9999-12-31", history=True)
    assert not runtime._eligible("structure", assertion, as_of="2010-12-31", history=True)
    # Execute the actual evidence-tool SPARQL against the signed source graph;
    # a historical authority remains inspectable after its checking horizon.
    graph_service = GraphService(ONTOLOGY)
    graph_service.release = runtime
    graph_service.fuseki_url = "http://127.0.0.1:3030"

    def select_from_signed_graph(family, query):
        return [{str(key): {"value": str(value)} for key, value in row.asdict().items()}
                for row in runtime._graphs[family].query(query)]

    monkeypatch.setattr(graph_service, "_select", select_from_signed_graph)
    inspection = graph_service.tool("get_evidence", {"assertion_id": str(assertion), "as_of": "2011-06-02"})
    assert len(inspection["edges"]) == 1
    inspected = inspection["edges"][0]
    assert inspected["id"] == str(assertion) and not inspected["legal_usable"]
    assert {item["id"] for item in inspected["validity_evidence"]} == {str(item) for item in validity}
    assert any("applicability" in item and "not established" in item for item in inspection["limitations"])
    # Discovery can expose the explicit horizon, but cannot silently assert currency.
    discovery = service.search("SYNTHETIC")
    assert discovery["hits"][0]["validity_checked_through"] == "2011-06-01"
    assert any("currency is not established" in item for item in discovery["limitations"])


def test_horizon_reacceptance_revokes_prior_private_publication_authorization(open_authorized, monkeypatch):
    fixture = open_authorized
    service, _ = search_fixture(fixture, monkeypatch)
    assert service.search("SYNTHETIC", as_of="2011-06-01")["hits"]
    resolution = {**fixture["resolution"], "open_ended_validity": {
        **fixture["resolution"]["open_ended_validity"], "checked_through": "2011-06-02"}}
    accepted = review(fixture["mapping"], fixture["mapping_id"], revision=2, source_revision=6, resolution=resolution)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["items"][0]["resolution"]["open_ended_validity"]["checked_through"] == "2011-06-02"
    for action in ("install", "activate", "rollback", "read"):
        with pytest.raises(AuthorizationError), guard(fixture, action=action):
            pytest.fail("Previous signed authorization cannot outlive a changed horizon review")
    assert fixture["runtime"].status()["status"] == "unavailable"
    monkeypatch.setattr(service, "_request", lambda *args: pytest.fail("Stale authorization must prevent search"))
    result = service.search("SYNTHETIC", as_of="2011-06-02")
    assert result["hits"] == [] and result["coverage"]["status"] == "unavailable"
    assert "PRIVATE" not in json.dumps(result)


def test_maximum_date_is_not_an_artificial_legal_end_or_overflow():
    open_state = {"kind": "open_ended", "start": date(2011, 1, 1), "end": None,
                  "checked_through": date.max, "evidence": frozenset({URIRef("urn:test:evidence")})}
    assert temporal.valid_at(open_state, "9999-12-31")
    later_open = {**open_state, "start": date.max}
    assert temporal.intervals_overlap(open_state, later_open)
    assert temporal.intervals_overlap(later_open, open_state)
    old_horizon = {**open_state, "checked_through": date(2011, 6, 1)}
    later_closed = {"kind": "closed", "start": date(2012, 1, 1), "end": date(2013, 1, 1),
                    "checked_through": None, "evidence": frozenset()}
    assert temporal.intervals_overlap(old_horizon, later_closed)
    assert not temporal.valid_at(old_horizon, "2012-01-01")
    assert temporal.valid_at(old_horizon, "2012-01-01", history=True)


def test_unknown_end_is_not_reclassified_as_open_even_for_history():
    graph = Graph()
    node = URIRef("urn:test:unknown-version")
    graph.add((node, LA.validFrom, Literal("2011-01-01", datatype=XSD.date)))
    state = temporal.interval_state(graph, node)
    assert state["kind"] == "unknown"
    assert not temporal.valid_at(state, "2011-01-01")
    assert not temporal.valid_at(state, "2011-01-01", history=True)
