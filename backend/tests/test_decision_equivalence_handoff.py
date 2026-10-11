"""Invented multi-source Graph B candidates; not actual review or publication."""
import base64

import pytest
from rdflib import RDF, Graph, Literal, URIRef
from test_decision_equivalence import (  # noqa: F401
    endpoint,
    incoming,
    opinion,
    pins,
    propose,
    source,
    workspace,
)
from test_decision_equivalence import evidence_set as evidence_fixture
from test_decision_graph_handoff import decode
from test_source_reviews import another_client, assess

from app import decision_equivalence_handoff as handoff

evidence_set = evidence_fixture


def download(evidence_set, client=None, **changes):
    path = endpoint(evidence_set).replace("/decision-equivalence?", "/decision-equivalence/graph-b-handoff?")
    return (client or evidence_set[0][0][1]).post(path, json={"expected_revision": 2, "pins": pins(evidence_set), **changes})


def accepted(evidence_set):
    assert propose(evidence_set).status_code == opinion(evidence_set).status_code == 200


def test_reproducible_full_three_source_packet_preserves_ids_and_private_history(evidence_set):
    accepted(evidence_set)
    response = download(evidence_set)
    data = decode(response)
    assert response.headers["cache-control"] == "no-store" and download(evidence_set).json() == response.json()
    assert data["schema_version"] == handoff.VERSION and data["confidentiality"] == "firm_confidential"
    assert data["canonical_candidate"] == "urn:tr-law:decision:synthetic-0"
    assert len(data["equivalence_history"]) == 2 and data["history_complete"]
    assert {v["decision_id"] for v in data["original_decisions"].values()} == {"urn:tr-law:decision:synthetic-0", "urn:tr-law:decision:synthetic-1"}
    assert data["structural_validation"] == {"conforms": True, "assertion_count": 6, "legal_truth_verified": False}
    for key in ("signed", "graph_updated", "identity_reservations_changed", "global_registry_qualified", "institutional_competence_verified", "legal_effect_verified", "publication_eligible"):
        assert data[key] is False
    for index, item in enumerate(evidence_set[0]):
        source_id = item[3]
        assert len(data["source_review_histories"][source_id]) == 6
        assert len(data["mapping_histories"][source_id]) == (2 if index < 2 else 0)
        if index < 2:
            assert len(data["identity_histories"][source_id]) == 2
        for name, raw in item[6].artifacts.items():
            assert base64.b64decode(data["files"][f"original/{source_id}/{name}"]["data"]) == raw
        assert item[2].detail(source_id)["publication_status"] == "staged"
    rdf = Graph().parse(data=base64.b64decode(data["files"]["candidate/jurisprudence.nt"]["data"]).decode(), format="nt")
    assertions = list(rdf.subjects(RDF.type, handoff.LA.Assertion))
    assert len(assertions) == 6 and len(set(rdf.subjects(RDF.type, handoff.LA.SourceArtifact))) == 3
    assert set(rdf.objects(None, handoff.LA.subject)) == {URIRef(data["canonical_candidate"])}
    assert set(rdf.objects(None, handoff.LA.predicate)) == {handoff.LA.issuedBy, handoff.LA.decidedIn, handoff.LA.hasDecisionVersion}
    assert set(rdf.objects(None, handoff.LA.object)).issuperset(URIRef(v["version_id"]) for v in data["original_decisions"].values())
    for assertion in assertions:
        assert rdf.value(assertion, handoff.LA.claimStatus) == Literal("unreviewed")
        assert rdf.value(assertion, handoff.LA.validityStatus) == Literal("unknown")
        quotes = [str(rdf.value(p, handoff.LA.quotedText)) for p in rdf.objects(assertion, handoff.LA.evidence)]
        assert any("register record 7" in text for text in quotes) == (rdf.value(assertion, handoff.LA.predicate) == handoff.LA.issuedBy)
    assert (None, handoff.LA.reviewPreparationOnly, Literal(True)) in rdf
    assert "sameAs" not in rdf.serialize(format="nt") and "equivalence-peer" not in rdf.serialize(format="nt")
    with pytest.raises(ValueError, match="Preparation-only"):
        handoff._load_serving()._release.check_data({"structure": Graph(), "jurisprudence": rdf}, handoff.ROOT / "ontology", {"verified": False})


@pytest.mark.parametrize("decision", ["needs_changes", "rejected"])
def test_independent_acceptance_required(evidence_set, decision):
    assert propose(evidence_set).status_code == 200
    assert download(evidence_set, expected_revision=1).status_code == 409
    assert opinion(evidence_set, decision=decision).status_code == 200
    assert download(evidence_set).status_code == 409


@pytest.mark.parametrize("relation", ["undetermined", "different_decision"])
def test_accepted_disagreement_cannot_compile_same_decision_candidates(evidence_set, relation):
    from test_decision_equivalence import claims
    assert propose(evidence_set, claims=claims(evidence_set, relation=relation)).status_code == opinion(evidence_set).status_code == 200
    assert download(evidence_set).status_code == 409


@pytest.mark.parametrize("index", [0, 1, 2])
def test_each_source_stale_or_missing_export_right_withholds_packet(evidence_set, index):
    accepted(evidence_set)
    item = evidence_set[0][index]
    assert assess(item[1], item[4] + "/review", 6, "rights", permitted_uses=["local_processing", "internal_display"]).status_code == 200
    result = download(evidence_set)
    assert result.status_code == 409 and "evidence_json" not in result.json()
    # A new equivalence never turns internal-display permission into export.
    if index == 2:
        new_pins = pins(evidence_set)
        new_pins["source_revisions"][item[3]] = 7
        assert propose(evidence_set, expected_revision=2, pins=new_pins).status_code == 200
        assert opinion(evidence_set, expected_revision=3, pins=new_pins).status_code == 200
        assert download(evidence_set, expected_revision=4, pins=new_pins).status_code == 409


@pytest.mark.parametrize("change", ["revision", "source", "mapping", "identity", "missing", "extra", "boolean"])
def test_exact_pins_and_closed_contract(evidence_set, change):
    accepted(evidence_set)
    body = {"expected_revision": 2, "pins": pins(evidence_set)}
    key = evidence_set[0][0][3]
    if change == "revision":
        body["expected_revision"] = 1
    if change in {"source", "mapping", "identity"}:
        body["pins"][change + "_revisions"][key] += 1
    if change == "missing":
        body["pins"]["source_revisions"].pop(key)
    if change == "extra":
        body["extra"] = "no"
    if change == "boolean":
        body["expected_revision"] = True
    assert download(evidence_set, **body).status_code in {409, 422}


@pytest.mark.parametrize("limit", ["MAX_PHYSICAL_BYTES", "MAX_PACKET_BYTES", "MAX_PASSAGES"])
def test_whole_packet_limits_never_return_partial_evidence(evidence_set, monkeypatch, limit):
    accepted(evidence_set)
    monkeypatch.setattr(handoff, limit, 1)
    result = download(evidence_set)
    assert result.status_code == 409 and "evidence_json" not in result.json()


@pytest.mark.parametrize("change", ["ontology", "register", "opinion", "original"])
def test_changed_dependencies_during_compilation_withhold_packet(evidence_set, monkeypatch, change):
    accepted(evidence_set)
    compile_packet = handoff.compile_packet
    def changed(*args):
        result, ontology_sha = compile_packet(*args)
        if change == "ontology":
            return result, "f" * 64
        if change == "register":
            item = evidence_set[0][2]
            assert assess(item[1], item[4] + "/review", 6, "legal").status_code == 200
        if change == "opinion":
            assert opinion(evidence_set, expected_revision=2, decision="rejected").status_code == 200
        if change == "original":
            item = evidence_set[0][2]
            path = item[2].root / item[3] / "source.bin"
            path.chmod(0o600)
            path.write_bytes(b"changed retained register")
        return result, ontology_sha
    monkeypatch.setattr(handoff, "compile_packet", changed)
    assert download(evidence_set).status_code == 409


def test_roles_firm_csrf_and_no_cross_context_output(evidence_set):
    accepted(evidence_set)
    app, client = evidence_set[0][0][:2]
    foreign = another_client(app, username="foreign", firm="other-firm")
    assert download(evidence_set, foreign).status_code == 409
    lawyer = another_client(app, username="lawyer", role="lawyer")
    assert download(evidence_set, lawyer).status_code == 403
    client.headers.pop("X-CSRF-Token")
    assert download(evidence_set).status_code == 403


def test_opposite_pair_download_keeps_explicit_anchor_and_identical_packet(evidence_set):
    accepted(evidence_set)
    forward = download(evidence_set)
    path = endpoint(evidence_set, reverse=True).replace("/decision-equivalence?", "/decision-equivalence/graph-b-handoff?")
    reverse = evidence_set[2].post(path, json={"expected_revision": 2, "pins": pins(evidence_set)})
    assert reverse.status_code == forward.status_code == 200
    assert reverse.json() == forward.json()


@pytest.mark.parametrize("change", ["quote", "locator"])
def test_structurally_valid_but_ungrounded_passages_withhold_packet(evidence_set, monkeypatch, change):
    accepted(evidence_set)
    original = handoff.candidate_graph
    def changed(*args):
        graph = original(*args)
        node = next(graph.subjects(RDF.type, handoff.LA.EvidencePassage))
        graph.set((node, handoff.LA.quotedText if change == "quote" else handoff.LA.locator, Literal("invented unsupported passage")))
        return graph
    monkeypatch.setattr(handoff, "candidate_graph", changed)
    assert download(evidence_set).status_code == 409


def test_physical_original_hash_is_checked_inside_candidate_validator(evidence_set, monkeypatch):
    accepted(evidence_set)
    original = handoff.validate_candidate_physical
    def changed(graphs, root, physical):
        tampered = dict(physical)
        package = evidence_set[0][2][6]
        tampered[package.locators.raw_sha256] = b"not the retained register"
        return original(graphs, root, tampered)
    monkeypatch.setattr(handoff, "validate_candidate_physical", changed)
    assert download(evidence_set).status_code == 409
