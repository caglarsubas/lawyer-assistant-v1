"""TEST-ONLY signed reviews; actual publication still requires independent gates."""
import base64
import json
from datetime import datetime, timezone

import pytest
from rdflib import RDF, Graph, Literal, URIRef
from test_decision_equivalence import pins, proof
from test_decision_graph_handoff import decode
from test_graph_b_review import (  # noqa: F401
    accept,
    incoming,
    path,
    source,
    workspace,
)
from test_graph_b_review import (
    evidence_set as evidence_fixture,
)
from test_graph_b_review import (
    signed_review as signed_fixture,
)
from test_source_reviews import assess

from app import graph_b_signing as signing
from app.config import ROOT
from app.graph_release import _load_serving
from app.release_preparation import digest

evidence_set = evidence_fixture
signed_review = signed_fixture


def download(evidence_set, signed_review, **changes):
    return signed_review[1].post(path(evidence_set, "/signing-inputs"), json={
        "expected_review_revision": 1, "expected_equivalence_revision": 2, "pins": pins(evidence_set), **changes})


def public_files(data):
    return {name: base64.b64decode(data["files"][name]["data"]) for name in data["public_input_paths"]}


def test_exact_qualified_draft_is_reproducible_public_inputs_exclude_private_ledger(evidence_set, signed_review):
    assert accept(evidence_set, signed_review).status_code == 200
    response = download(evidence_set, signed_review)
    data = decode(response)
    assert response.headers["cache-control"] == "no-store" and download(evidence_set, signed_review).json() == response.json()
    assert data["schema_version"] == signing.VERSION and data["confidentiality"] == "firm_confidential"
    assert data["signed_review_revision"] == 1 and data["structural_preflight"] == {"conforms": True, "assertion_count": 6, "legal_truth_verified": False}
    assert all(data[key] is False for key in ("signed", "publication_eligible", "graph_updated", "identity_reservations_changed", "institutional_competence_verified", "finality_verified"))
    files = public_files(data)
    assert "NOTICE.json" not in files and set(files) == {"inputs/structure.ttl", "inputs/jurisprudence.ttl", "public-review-body.json", *(name for name in files if name.startswith("evidence/"))}
    rdf = Graph().parse(data=files["inputs/jurisprudence.ttl"].decode(), format="turtle")
    assertions = set(rdf.subjects(RDF.type, signing.LA.Assertion))
    assert len(assertions) == 6 and set(rdf.objects(None, signing.LA.subject)) == {URIRef("urn:tr-law:decision:synthetic-0")}
    assert len(set(rdf.subjects(RDF.type, signing.LA.DecisionVersion))) == 2
    assert not list(rdf.triples((None, signing.LA.reviewPreparationOnly, None)))
    assert all(rdf.value(a, signing.LA.claimStatus) == Literal("legally_reviewed") for a in assertions)
    assert all(rdf.value(a, signing.LA.validityStatus) == Literal("unknown") and rdf.value(a, signing.LA.validFrom) is None for a in assertions)
    flat = b"\n".join(files.values())
    for private in [b"credential_data", b"appointment", b"firm_id", b"context_id", b"rationale", b"equivalence_history", b"accepted_key", b"Second confidential reviewer", b"identity-peer", b"equivalence-peer", b"Invented appointment"]:
        assert private not in flat
    review = signed_review[1].get(path(evidence_set)).json()["current"]
    for private in (review["id"], review["actor"]["id"], review["envelope"]["body"]["operator_id"], review["envelope"]["body"]["source_snapshot_sha256"]):
        assert private.encode() not in flat
    assert b"TEST-ONLY PUBLIC REVIEWER" in flat
    public_body = json.loads(files["public-review-body.json"])
    assert public_body["input_graphs_sha256"] == {family: digest(files[f"inputs/{family}.ttl"]) for family in ("structure", "jurisprudence")}
    with pytest.raises(ValueError, match="trusted.*attestation"):
        _load_serving()._release.check_data({"structure": Graph(), "jurisprudence": rdf}, ROOT / "ontology", {"verified": False})
    assert [i[2].detail(i[3])["publication_status"] for i in evidence_set[0]] == ["staged"] * 3


@pytest.mark.parametrize("end_status", ["closed", "open_ended"])
def test_supported_temporal_ranges_use_exact_own_evidence_without_register_copy(evidence_set, signed_review, end_status):
    entry = signed_review[5]["qualifications"]["relations"][0]
    entry.update(end_status=end_status, valid_from="2021-01-12", valid_until="2023-01-01" if end_status == "closed" else None,
        checked_through="2024-01-01" if end_status == "open_ended" else None, evidence=[proof(evidence_set[0][0])], rationale="PRIVATE temporal assessment not exported")
    assert accept(evidence_set, signed_review).status_code == 200
    files = public_files(decode(download(evidence_set, signed_review)))
    rdf = Graph().parse(data=files["inputs/jurisprudence.ttl"].decode(), format="turtle")
    known = [a for a in rdf.subjects(RDF.type, signing.LA.Assertion) if rdf.value(a, signing.LA.validityStatus) == Literal("known")]
    assert len(known) == 1 and str(rdf.value(known[0], signing.LA.validFrom)) == "2021-01-12"
    assert rdf.value(known[0], signing.LA.predicate) == signing.LA.decidedIn
    assert len(set(rdf.objects(known[0], signing.LA.validityEvidence))) == (1 if end_status == "open_ended" else 0)
    assert b"PRIVATE temporal assessment" not in b"\n".join(files.values())
    assert not list(rdf.triples((None, signing.LA.validFrom, Literal("2020-01-01", datatype=signing.XSD.date))))


@pytest.mark.parametrize("change", ["absent", "rejected", "needs_changes", "review-pin", "equivalence-pin", "source-pin", "key", "rights"])
def test_exact_current_signed_approval_required(evidence_set, signed_review, change):
    if change != "absent":
        assert accept(evidence_set, signed_review).status_code == 200
    changes = {}
    if change in {"rejected", "needs_changes"}:
        signed_review[5].update(expected_review_revision=1, reviewed_at=datetime.now(timezone.utc).isoformat())
        assert accept(evidence_set, signed_review, decision="reject" if change == "rejected" else "needs_changes").status_code == 200
        changes["expected_review_revision"] = 2
    if change == "review-pin":
        changes["expected_review_revision"] = 2
    if change == "equivalence-pin":
        changes["expected_equivalence_revision"] = 1
    if change == "source-pin":
        changes["pins"] = pins(evidence_set)
        changes["pins"]["source_revisions"][evidence_set[0][0][3]] = 5
    if change == "key":
        signed_review[0].state.settings.graph_b_review_trusted_key = ""
    if change == "rights":
        item = evidence_set[0][2]
        assert assess(item[1], item[4] + "/review", 6, "rights", decision="rejected").status_code == 200
    response = download(evidence_set, signed_review, **changes)
    assert response.status_code in {409, 503} and "evidence_json" not in response.json()


@pytest.mark.parametrize("change", ["key", "ontology", "source", "packet-budget", "physical-budget", "passage-budget", "quote"])
def test_conversion_races_and_budgets_withhold_entire_draft(evidence_set, signed_review, monkeypatch, change):
    from app import graph_b_review
    assert accept(evidence_set, signed_review).status_code == 200
    if change.endswith("budget"):
        monkeypatch.setattr(signing.handoff, {"packet-budget": "MAX_PACKET_BYTES", "physical-budget": "MAX_PHYSICAL_BYTES", "passage-budget": "MAX_PASSAGES"}[change], 1)
    else:
        compile_original = graph_b_review.compile_inputs
        def changed(*args):
            result = compile_original(*args)
            if change == "key":
                signed_review[0].state.settings.graph_b_review_trusted_key = ""
            if change == "ontology":
                monkeypatch.setattr(_load_serving()._release, "ontology_digest", lambda *a: "f" * 64)
            if change == "source":
                item = evidence_set[0][2]
                item[2].root.joinpath(item[3], "text.txt").chmod(0o600)
                item[2].root.joinpath(item[3], "text.txt").write_text("tampered public fixture")
            if change == "quote":
                # Independently exercise the physical quote verifier with valid hashes.
                files = public_files(json.loads(result["evidence_json"]))
                rdf = Graph().parse(data=files["inputs/jurisprudence.ttl"].decode(), format="turtle")
                passage = next(rdf.subjects(RDF.type, signing.LA.EvidencePassage))
                rdf.set((passage, signing.LA.quotedText, Literal("wrong quotation")))
                physical = {name.split("/")[1][:-4]: raw for name, raw in files.items() if name.startswith("evidence/")}
                signing.physical_check({"structure": Graph(), "jurisprudence": rdf}, ROOT / "ontology", physical)
            return result
        monkeypatch.setattr(graph_b_review, "compile_inputs", changed)
    response = download(evidence_set, signed_review)
    assert response.status_code in {409, 503} and "evidence_json" not in response.json()


def test_separate_public_attestation_can_verify_draft_but_never_grants_installation(evidence_set, signed_review, tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from app.release_preparation import canonical
    assert accept(evidence_set, signed_review).status_code == 200
    files = public_files(decode(download(evidence_set, signed_review)))
    root = tmp_path / "public-signing-inputs"
    for name, raw in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    serving = _load_serving()
    inputs = {family: root / f"inputs/{family}.ttl" for family in ("structure", "jurisprudence")}
    with pytest.raises(ValueError, match="trusted.*attestation"):
        serving._release.create_bundle(ROOT / "ontology", inputs, root / "evidence", tmp_path / "unsigned-rejected")
    key = Ed25519PrivateKey.generate()  # Separate invented national-review signer.
    public = tmp_path / "TEST-ONLY-public-review.pem"
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    body = json.loads(files["public-review-body.json"])
    attestation = tmp_path / "TEST-ONLY-public-attestation.json"
    attestation.write_bytes(canonical({"algorithm": "Ed25519", "body": body, "signature": base64.b64encode(key.sign(canonical(body))).decode()}))
    bundle = tmp_path / "TEST-ONLY-public-bundle"
    checked = serving._release.create_bundle(ROOT / "ontology", inputs, root / "evidence", bundle, attestation, public)
    assert checked["review"]["verified"] and checked["assertions"] == 6
    assert not any("appointment" in p.name or "NOTICE" in p.name for p in bundle.rglob("*"))
    prepared = tmp_path / "TEST-ONLY-serving"
    serving.prepare(bundle, public, prepared)
    runtime = tmp_path / "never-installed"
    with pytest.raises(ValueError, match="authorization"):
        serving.install(runtime, prepared, public)
    assert not runtime.exists()


@pytest.mark.parametrize('actor', ['reviewer_id', 'operator_id'])
def test_actor_deactivation_during_conversion_withholds_all_signing_inputs(evidence_set, signed_review, monkeypatch, actor):
    from sqlalchemy import update

    from app import graph_b_review
    from app.db import User
    assert accept(evidence_set, signed_review).status_code == 200
    current = signed_review[1].get(path(evidence_set)).json()['current']['envelope']['body']
    original = graph_b_review.compile_inputs
    def change(*args):
        result = original(*args)
        with signed_review[0].state.store.session() as session:
            session.execute(update(User).where(User.id == current[actor]).values(active=False))
            session.commit()
        return result
    monkeypatch.setattr(graph_b_review, 'compile_inputs', change)
    response = download(evidence_set, signed_review)
    assert response.status_code in {401, 409} and 'evidence_json' not in response.json()


@pytest.mark.parametrize('decision', ['reject', 'needs_changes'])
def test_negative_review_records_unknown_institution_dates_without_inventing_positive_qualification(evidence_set, signed_review, decision):
    from test_graph_b_review import request_body
    assert accept(evidence_set, signed_review).status_code == 200
    signed_review[5].update(decision=decision, expected_review_revision=1, reviewed_at=datetime.now(timezone.utc).isoformat())
    qualification = signed_review[5]['qualifications']
    qualification['decision_on'] = None
    qualification['decision_date_evidence'] = []
    qualification['institution']['identity_window'].update(end_status='unknown',valid_from=None,valid_until=None,checked_through=None,evidence=[],rationale='Insufficient retained register dates; explicit negative opinion')
    request = request_body(evidence_set, signed_review)
    assert request.status_code == 200, request.text
    response = accept(evidence_set, signed_review)
    assert response.status_code == 200, response.text
    assert response.json()['revision'] == 2 and not response.json()['signed_review_current']
    assert response.json()['history'][0]['envelope']['body']['qualifications']['decision_on'] is None
    assert response.json()['history'][1]['envelope']['body']['decision'] == 'approve'
    assert download(evidence_set, signed_review, expected_review_revision=2).status_code == 409
    # The same missing evidence cannot be relabeled as positive approval.
    signed_review[5].update(decision='approve', expected_review_revision=2, reviewed_at=datetime.now(timezone.utc).isoformat())
    assert request_body(evidence_set, signed_review).status_code == 409
