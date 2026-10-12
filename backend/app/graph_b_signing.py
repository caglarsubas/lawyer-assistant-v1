"""Bounded public signing drafts from current private signed Graph B reviews.

No signer, public attestation, audience authorization, graph write or activation.
Only the live locked review route calls this compiler; client RDF is never accepted.
"""
import base64
import json

from fastapi import HTTPException
from pydantic import Field, StrictInt
from rdflib import RDF, XSD, Graph, Literal, URIRef

from . import decision_equivalence as eq
from . import decision_equivalence_handoff as handoff
from . import source_reviews as reviews
from .decision_graph_handoff import LA, source_evidence
from .graph_release import _load_serving
from .release_preparation import canonical, digest

VERSION = "qualified-graph-b-signing-inputs-v1"


class SigningInput(reviews.StrictInput):
    expected_review_revision: StrictInt = Field(ge=1, le=50)
    expected_equivalence_revision: StrictInt = Field(ge=1, le=eq.MAX_EVENTS)
    pins: eq.Pins


def invalid():
    return HTTPException(409, "Current independently signed review and complete qualified public evidence are required")


def passages_for(packages, captured, bound, equivalence_event, body):
    chosen = {key: {p.id for p in value} for key, value in handoff.selected_passages(packages, captured, bound, equivalence_event).items()}
    qualified = body["qualifications"]
    proofs = [*qualified["decision_date_evidence"], *qualified["institution"]["identity_window"]["evidence"],
              *(proof for relation in qualified["relations"] for proof in relation["evidence"])]
    for proof in proofs:
        chosen[proof["source_id"]].add(proof["passage_id"])
    if (sum(len(value) for value in chosen.values()) > handoff.MAX_PASSAGES
            or any(not value.issubset(bound["sources"][key]["reviewed_passage_ids"]) for key, value in chosen.items())):
        raise invalid()
    return {key: [p for p in package.locators.passages if p.id in chosen[key]] for key, package in packages.items()}


def physical_check(graphs, ontology_root, physical):
    if any(type(raw) is not bytes or digest(raw) != fingerprint for fingerprint, raw in physical.items()):
        raise invalid()
    release = _load_serving()._release
    # This is a preflight of the desired public attestation inputs. Actual release
    # preparation independently verifies the externally signed public body.
    checked = release.check_data(graphs, ontology_root, {"verified": True})
    if checked["assertions"] != 6 or release.required_physical_hashes(checked) != set(physical):
        raise invalid()
    for passage in checked["passages"]:
        rep = checked["representations"][passage["representation_id"]]
        text = physical[rep["text_sha256"]].decode("utf-8")
        locators = json.loads(physical[rep["locator_map_sha256"]])
        if (text[passage["start"]:passage["end"]] != passage["text"] or not any(
                span["locator"] == passage["locator"] and span["start"] <= passage["start"] < passage["end"] <= span["end"]
                for span in locators["spans"])):
            raise invalid()


def compile_inputs(packages, decisions, captured, bound, equivalence_event, review_event, ontology_root):
    """Trusted live caller has verified complete signature/context/roles/rights."""
    body = review_event["envelope"]["body"]
    graph = Graph()
    passages = passages_for(packages, captured, bound, equivalence_event, body)
    physical, proof_nodes = {}, {}
    for key, package in packages.items():
        locators = canonical({"schema_version": 1, "artifact_sha256": package.locators.raw_sha256,
            "text_sha256": package.locators.text_sha256, "extractor_version": VERSION,
            "spans": [{"locator": p.locator, "start": p.start, "end": p.end} for p in package.locators.passages]})
        for raw in (package.raw, package.artifacts["text.txt"], locators):
            physical[digest(raw)] = raw
        nodes = source_evidence(graph, package, passages[key], locators, compiler_version=VERSION, scoped_artifact=True)
        proof_nodes.update({(key, passage.id): node for passage, node in zip(passages[key], nodes, strict=True)})
    if sum(len(raw) for raw in physical.values()) > handoff.MAX_PHYSICAL_BYTES:
        raise invalid()
    proposal = equivalence_event["proposal"]
    decision = URIRef(proposal["claims"]["canonical_decision_id"])
    register = next(key for key in packages if key not in decisions)
    assessments = {(entry["source_id"], entry["relation"]): entry for entry in body["qualifications"]["relations"]}
    for source in decisions:
        value = proposal["decisions"][source]
        proceeding, institution, version = (URIRef(value[key]) for key in ("proceeding_id", "institution_id", "version_id"))
        for node, kind in ((decision, LA.JudicialDecision), (proceeding, LA.Proceeding), (institution, LA.Institution), (version, LA.DecisionVersion)):
            graph.add((node, RDF.type, kind))
            graph.add((node, LA.scope, Literal("public")))
        for relation, obj in (("decidedIn", proceeding), ("issuedBy", institution), ("hasDecisionVersion", version)):
            temporal = assessments[source, relation]
            supporting = {proof_nodes[key, p.id] for key in decisions for p in passages[key]}
            if relation == "issuedBy":
                supporting.update(proof_nodes[register, p.id] for p in passages[register])
            supporting.update(proof_nodes[p["source_id"], p["passage_id"]] for p in temporal["evidence"])
            # No private event, firm/account, snapshot or credential identifiers.
            assertion = URIRef("urn:la:reviewed-decision-assertion:" + digest(canonical([
                str(decision), str(LA[relation]), str(obj), source, sorted(map(str, supporting)),
                body["public_reviewer"], body["reviewed_at"],
                {name: temporal[name] for name in ("end_status", "valid_from", "valid_until", "checked_through")}, VERSION])))
            for predicate, item in ((RDF.type, LA.Assertion), (LA.subject, decision), (LA.predicate, LA[relation]), (LA.object, obj),
                    (LA.scope, Literal("public")), (LA.graphFamily, Literal("jurisprudence")), (LA.claimStatus, Literal("legally_reviewed")),
                    (LA.synthetic, Literal(False)), (LA.recordedAt, Literal(body["reviewed_at"], datatype=XSD.dateTime)),
                    (LA.reviewer, Literal(body["public_reviewer"])), (LA.reviewedAt, Literal(body["reviewed_at"], datatype=XSD.dateTime)),
                    (LA.extractionMethod, Literal("independently_signed_decision_identity_temporal_review")), (LA.extractorVersion, Literal(VERSION)),
                    (LA.validityStatus, Literal("unknown" if temporal["end_status"] == "unknown" else "known")),
                    (LA.validityEndStatus, Literal(temporal["end_status"]))):
                graph.add((assertion, predicate, item))
            for proof_node in supporting:
                graph.add((assertion, LA.evidence, proof_node))
            if temporal["end_status"] == "unknown":
                graph.add((assertion, LA.unresolvedReason, Literal("Temporal applicability not established by the reviewed sources")))
            else:
                graph.add((assertion, LA.validFrom, Literal(temporal["valid_from"], datatype=XSD.date)))
                if temporal["end_status"] == "closed":
                    graph.add((assertion, LA.validTo, Literal(temporal["valid_until"], datatype=XSD.date)))
                else:
                    graph.add((assertion, LA.validityCheckedThrough, Literal(temporal["checked_through"], datatype=XSD.date)))
                    for proof in temporal["evidence"]:
                        graph.add((assertion, LA.validityEvidence, proof_nodes[proof["source_id"], proof["passage_id"]]))
    graphs = {"structure": Graph(), "jurisprudence": graph}
    physical_check(graphs, ontology_root, physical)
    inputs = {family: ("\n".join(sorted(value.serialize(format="nt").splitlines())) + "\n").encode() for family, value in graphs.items()}
    public_body = {"reviewer": body["public_reviewer"], "reviewed_at": body["reviewed_at"], "decision": "approve",
        "scope": "national_ontology_and_assertions", "ontology_sha256": body["ontology_sha256"],
        "input_graphs_sha256": {family: digest(raw) for family, raw in inputs.items()}}
    files = {f"inputs/{family}.ttl": raw for family, raw in inputs.items()}
    files.update({f"evidence/{key}.bin": raw for key, raw in physical.items()})
    files["public-review-body.json"] = canonical(public_body)
    files["NOTICE.json"] = canonical({"schema_version": VERSION, "confidentiality": "firm_confidential", "signed": False,
        "publication_eligible": False, "purpose": "Externally reviewed public signing inputs; separate decision-specific audience authorization and activation required",
        "institution_scope": "historical_identity_only", "institutional_competence_verified": False, "finality_verified": False})
    public_paths = sorted(name for name in files if name != "NOTICE.json")
    encoded = {name: {"sha256": digest(raw), "bytes": len(raw), "encoding": "base64", "data": base64.b64encode(raw).decode()}
               for name, raw in sorted(files.items())}
    core = {"schema_version": VERSION, "confidentiality": "firm_confidential", "firm_id": body["firm_id"], "context_id": body["context_id"],
        "signed_review_revision": review_event["revision"], "equivalence_revision": body["equivalence_revision"], "pins": body["pins"],
        "signed_review_sha256": digest(canonical(review_event["envelope"])), "ontology_sha256": body["ontology_sha256"],
        "public_input_paths": public_paths, "files": {name: {k: v for k, v in data.items() if k != "data"} for name, data in encoded.items()},
        "structural_preflight": {"conforms": True, "assertion_count": 6, "legal_truth_verified": False},
        "signed": False, "publication_eligible": False, "graph_updated": False, "identity_reservations_changed": False,
        "institutional_competence_verified": False, "finality_verified": False}
    payload = canonical({**core, "packet_id": digest(canonical(core)), "files": encoded})
    if len(payload) > handoff.MAX_PACKET_BYTES:
        raise invalid()
    return {"evidence_json": payload.decode(), "evidence_sha256": digest(payload)}
