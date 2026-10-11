"""Synthetic private Graph B staging; no release or legal qualification."""
import base64
import hashlib
import json

import pytest
from rdflib import RDF, Graph, Literal
from test_decision_identities import mapped, proposal, propose_identity, review_identity
from test_decision_mappings import mapping as mapping_fixture
from test_decision_mappings import propose, resolution, review
from test_jurisprudence_candidates import incoming as incoming_fixture
from test_public_sources import source as source_fixture
from test_source_reviews import another_client, assess
from test_workspace import workspace as workspace_fixture

from app import decision_graph_handoff as handoff
from app.release_preparation import canonical, digest

mapping = mapping_fixture
incoming = incoming_fixture
source = source_fixture
workspace = workspace_fixture


def evidence(mapping, passage="p2"):
    p = next(p for p in mapping[6].locators.passages if p.id == passage)
    return [{"reference": f"source:{mapping[3]}:passage:{passage}", "sha256": p.text_sha256}]


def accepted(mapping, *, export=True, refs=None):
    mapped(mapping, export=export)
    revision = 6 if export else 5
    identity = {**proposal(mapping)["identity"], "identity_evidence": refs or evidence(mapping), "institution_evidence": evidence(mapping)}
    assert propose_identity(mapping, expected_source_review_revision=revision, identity=identity).status_code == 200
    peer = another_client(mapping[0])
    assert review_identity(mapping, peer, expected_source_review_revision=revision, evidence_refs=evidence(mapping)).status_code == 200
    return peer


def download(mapping, client=None, **changes):
    return (client or mapping[1]).post(mapping[4] + "/decision-identities/graph-b-handoff", json={
        "expected_revision": 2, "expected_mapping_revision": 2, "expected_source_review_revision": 6, **changes})


def decode(response):
    assert response.status_code == 200, response.text
    envelope = response.json()
    assert digest(envelope["evidence_json"].encode()) == envelope["evidence_sha256"]
    result = json.loads(envelope["evidence_json"])
    core = {key: value for key, value in result.items() if key != "packet_id"}
    core["files"] = {name: {key: value for key, value in entry.items() if key != "data"} for name, entry in result["files"].items()}
    assert digest(canonical(core)) == result["packet_id"]
    for entry in result["files"].values():
        data = base64.b64decode(entry["data"], validate=True)
        assert len(data) == entry["bytes"] and hashlib.sha256(data).hexdigest() == entry["sha256"]
    return result


def test_exact_reproducible_packet_originals_private_history_and_candidate_rdf(mapping):
    accepted(mapping)
    result = download(mapping)
    data = decode(result)
    assert result.headers["cache-control"] == "no-store"
    assert download(mapping).json() == result.json()
    assert data["confidentiality"] == "firm_confidential" and data["history_complete"]
    assert len(data["identity_history"]) == len(data["mapping_history"]) == 2 and len(data["source_review_history"]) == 6
    assert data["structural_validation"] == {"conforms": True, "assertion_count": 3, "legal_truth_verified": False}
    assert data["scope"] == "own_decision_identity_candidates_only" and data["omitted_mapping_ids"] == []
    assert all(data[key] is False for key in ("signed", "graph_updated", "publication_eligible", "global_registry_qualified", "legal_effect_verified"))
    for name, raw in mapping[6].artifacts.items():
        assert base64.b64decode(data["files"]["original/" + name]["data"]) == raw
    rdf = Graph().parse(data=base64.b64decode(data["files"]["candidate/jurisprudence.nt"]["data"]).decode(), format="nt")
    assertions = list(rdf.subjects(RDF.type, handoff.LA.Assertion))
    assert len(assertions) == 3
    assert set(rdf.objects(None, handoff.LA.predicate)) == {handoff.LA.decidedIn, handoff.LA.issuedBy, handoff.LA.hasDecisionVersion}
    for node in assertions:
        assert rdf.value(node, handoff.LA.claimStatus) == Literal("unreviewed")
        assert rdf.value(node, handoff.LA.validityStatus) == Literal("unknown")
        assert list(rdf.objects(node, handoff.LA.evidence))
    assert not list(rdf.triples((None, handoff.LA.reviewer, None)))
    assert not list(rdf.triples((None, handoff.LA.finalityDate, None)))
    assert (None, handoff.LA.reviewPreparationOnly, Literal(True)) in rdf
    for passage in rdf.subjects(RDF.type, handoff.LA.EvidencePassage):
        start, end = int(rdf.value(passage, handoff.LA.startOffset)), int(rdf.value(passage, handoff.LA.endOffset))
        assert mapping[6].text[start:end] == str(rdf.value(passage, handoff.LA.quotedText))
    # Existing publication tooling rejects the intact preparation marker.
    with pytest.raises(ValueError, match="Preparation-only"):
        handoff._load_serving()._release.check_data({"structure": Graph(), "jurisprudence": rdf}, handoff.ROOT / "ontology", {"verified": False})
    assert mapping[2].detail(mapping[3])["publication_status"] == "staged"


@pytest.mark.parametrize("refs", [[{"reference": "free text register", "sha256": "a" * 64}],
                                  [{"reference": "source:" + "f" * 64 + ":passage:p2", "sha256": "a" * 64}]])
def test_external_or_unresolved_references_do_not_become_graph_evidence(mapping, refs):
    accepted(mapping, refs=refs)
    result = download(mapping)
    assert result.status_code == 409 and "evidence_json" not in result.json()


def test_explicit_export_rights_independent_acceptance_and_freshness(mapping):
    accepted(mapping, export=False)
    assert download(mapping, expected_source_review_revision=5).status_code == 409
    assert assess(mapping[1], mapping[4] + "/review", 5, "rights",
                  permitted_uses=["local_processing", "internal_display", "export"]).status_code == 200
    assert download(mapping).status_code == 409  # old independent review stays stale


@pytest.mark.parametrize("changes", [{"expected_revision": 1}, {"expected_mapping_revision": 1},
                                      {"expected_source_review_revision": 5}, {"expected_revision": True}, {"extra": "no"}])
def test_all_revision_pins_and_closed_download_contract(mapping, changes):
    accepted(mapping)
    assert download(mapping, **changes).status_code in {409, 422}


@pytest.mark.parametrize("limit", ["MAX_PHYSICAL_BYTES", "MAX_PACKET_BYTES", "MAX_PASSAGES"])
def test_no_partial_oversized_packets(mapping, monkeypatch, limit):
    accepted(mapping)
    monkeypatch.setattr(handoff, limit, 1 if limit != "MAX_PASSAGES" else 0)
    result = download(mapping)
    assert result.status_code == 409 and "evidence_json" not in result.json()


def test_source_change_during_compilation_withholds_complete_packet(mapping, monkeypatch):
    accepted(mapping)
    compile_packet = handoff.compile_packet
    def change(*args):
        result = compile_packet(*args)
        assert assess(mapping[1], mapping[4] + "/review", 6, "legal").status_code == 200
        return result
    monkeypatch.setattr(handoff, "compile_packet", change)
    result = download(mapping)
    assert result.status_code == 409 and "evidence_json" not in result.json()


def test_ontology_change_during_compilation_withholds_packet(mapping, monkeypatch):
    accepted(mapping)
    original = handoff.compile_packet
    monkeypatch.setattr(handoff, "compile_packet", lambda *args: (original(*args)[0], "f" * 64))
    assert download(mapping).status_code == 409


def test_accepted_citation_mapping_is_retained_but_never_promoted(mapping):
    peer = accepted(mapping)
    result = propose(mapping, revision=2, source_revision=6, index=2)
    item = next(item for item in result.json()["items"] if item["status"] == "machine_proposed")
    c = item["candidate"]
    value = resolution(mapping, start=c["start"], end=c["end"], occurrence_role="cited_authority",
                       decision_ref=None, proceeding_ref=None, institution_ref=None,
                       target_ref="human-declared-law", target_version_ref="human-declared-version")
    assert review(mapping, item["id"], revision=3, source_revision=6, resolution=value).status_code == 200
    identity = {**proposal(mapping)["identity"], "identity_evidence": evidence(mapping), "institution_evidence": evidence(mapping)}
    assert propose_identity(mapping, expected_revision=2, expected_mapping_revision=4, expected_source_review_revision=6, identity=identity).status_code == 200
    assert review_identity(mapping, peer, expected_revision=3, expected_mapping_revision=4, expected_source_review_revision=6, evidence_refs=evidence(mapping)).status_code == 200
    data = decode(download(mapping, expected_revision=4, expected_mapping_revision=4))
    assert data["omitted_mapping_ids"] == [item["id"]]
    rdf = Graph().parse(data=base64.b64decode(data["files"]["candidate/jurisprudence.nt"]["data"]).decode(), format="nt")
    assert handoff.LA.cites not in set(rdf.objects(None, handoff.LA.predicate))
    assert "human-declared-version" not in base64.b64decode(data["files"]["candidate/jurisprudence.nt"]["data"]).decode()


def test_role_firm_and_csrf_boundaries_no_private_packet(mapping):
    accepted(mapping)
    foreign = another_client(mapping[0], username="foreign", firm="another-firm")
    assert download(mapping, foreign).status_code == 409
    lawyer = another_client(mapping[0], username="lawyer", role="lawyer")
    assert download(mapping, lawyer).status_code == 403
    mapping[1].headers.pop("X-CSRF-Token")
    assert download(mapping).status_code == 403
