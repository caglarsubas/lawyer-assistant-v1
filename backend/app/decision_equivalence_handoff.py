"""Private multi-source Graph B candidates from an exact reviewed equivalence."""
import base64

from fastapi import HTTPException
from pydantic import Field, StrictInt
from rdflib import RDF, XSD, Graph, Literal, URIRef
from sqlalchemy.exc import OperationalError

from . import decision_equivalence as equivalence
from . import decision_mappings as mappings
from . import source_reviews as reviews
from .config import ROOT
from .decision_graph_handoff import LA, source_evidence
from .graph_release import _load_serving
from .release_preparation import PreparationError, canonical, digest, validate_candidate_physical

VERSION = "decision-equivalence-graph-b-handoff-v1"
MAX_PHYSICAL_BYTES = 6 * 1024 * 1024
MAX_PACKET_BYTES = 16 * 1024 * 1024
MAX_PASSAGES = 150


class HandoffInput(reviews.StrictInput):
    expected_revision: StrictInt = Field(ge=1, le=equivalence.MAX_EVENTS)
    pins: equivalence.Pins


def selected_passages(packages, captured, bound, event):
    selected = {key: set() for key in packages}
    for proof in event["proposal"]["claims"]["evidence"] + event["evidence"]:
        selected[proof["source_id"]].add(proof["passage_id"])
    lookup = {f"source:{key}:passage:{p.id}": (key, p.id) for key, package in packages.items() for p in package.locators.passages}
    for key, events in bound["identities"].items():
        identity_event = events[-1]
        proposal = identity_event["proposal"]
        for ref in proposal["identity"]["identity_evidence"] + proposal["identity"]["institution_evidence"] + identity_event["evidence_refs"]:
            source, passage = lookup[ref["reference"]]
            selected[source].add(passage)
        for item in captured["sources"][key]["state"]["items"]:
            if item["id"] in proposal["own_mapping_ids"]:
                span = mappings._validate_resolution(mappings.Resolution.model_validate(item["resolution"]), item["candidate"], packages[key])
                selected[key].update(span["passage_ids"])
    if (sum(len(ids) for ids in selected.values()) > MAX_PASSAGES
            or any(not ids or not ids.issubset(bound["sources"][key]["reviewed_passage_ids"]) for key, ids in selected.items())):
        raise HTTPException(409, "Üç kaynağın tam dayanakları 150 pasaj sınırını veya kabul edilmiş kapsamı aşıyor")
    return {key: [p for p in package.locators.passages if p.id in selected[key]] for key, package in packages.items()}


def candidate_graph(packages, decision_ids, register_id, event, passages, locators):
    graph = Graph()
    evidence = {key: source_evidence(graph, package, passages[key], locators[key], compiler_version=VERSION,
                                   scoped_artifact=True) for key, package in packages.items()}
    proposal = event["proposal"]
    decision = URIRef(proposal["claims"]["canonical_decision_id"])
    for key in decision_ids:
        value = proposal["decisions"][key]
        proceeding, institution, version = (URIRef(value[name]) for name in ("proceeding_id", "institution_id", "version_id"))
        for node, kind in ((decision, LA.JudicialDecision), (proceeding, LA.Proceeding), (institution, LA.Institution), (version, LA.DecisionVersion)):
            graph.add((node, RDF.type, kind))
            graph.add((node, LA.scope, Literal("public")))
        for predicate, obj in ((LA.decidedIn, proceeding), (LA.issuedBy, institution), (LA.hasDecisionVersion, version)):
            assertion = URIRef("urn:la:decision-assertion-proposal:" + digest(canonical([
                str(decision), str(predicate), str(obj), key, proposal["snapshot_sha256"], event["id"], VERSION])))
            for prop, item in ((RDF.type, LA.Assertion), (LA.subject, decision), (LA.predicate, predicate), (LA.object, obj),
                               (LA.scope, Literal("public")), (LA.graphFamily, Literal("jurisprudence")),
                               (LA.claimStatus, Literal("unreviewed")), (LA.synthetic, Literal(False)),
                               (LA.recordedAt, Literal(event["created_at"], datatype=XSD.dateTime)),
                               (LA.validityStatus, Literal("unknown")),
                               (LA.unresolvedReason, Literal("Reviewed equivalence candidate; competence, temporal validity and legal effects require separate review")),
                               (LA.extractionMethod, Literal("reviewed_cross_source_identity_candidate")), (LA.extractorVersion, Literal(VERSION))):
                graph.add((assertion, prop, item))
            # Both decisions ground the reviewed alignment. Register passages only
            # support the institution identity candidate, never competence.
            supporting = [*evidence[decision_ids[0]], *evidence[decision_ids[1]]]
            if predicate == LA.issuedBy:
                supporting += evidence[register_id]
            for passage in supporting:
                graph.add((assertion, LA.evidence, passage))
    graph.add((URIRef("urn:la:decision-preparation:" + proposal["snapshot_sha256"]), LA.reviewPreparationOnly, Literal(True)))
    return graph


def compile_packet(packages, decision_ids, key, captured, bound, events, firm_id, ontology_root):
    ontology_sha = _load_serving()._release.ontology_digest(ontology_root)
    event = events[-1]
    register_id = next(source for source in packages if source not in decision_ids)
    passages = selected_passages(packages, captured, bound, event)
    raw_files, physical, locators = {}, {}, {}
    for source, package in packages.items():
        locator = {"schema_version": 1, "artifact_sha256": package.locators.raw_sha256,
                   "text_sha256": package.locators.text_sha256, "extractor_version": VERSION,
                   "spans": [{"locator": p.locator, "start": p.start, "end": p.end} for p in package.locators.passages]}
        locators[source] = canonical(locator)
        raw_files.update({f"original/{source}/{name}": data for name, data in package.artifacts.items()})
        raw_files[f"candidate/{source}/locators.json"] = locators[source]
        physical.update({package.locators.raw_sha256: package.raw, package.locators.text_sha256: package.artifacts["text.txt"],
                         digest(locators[source]): locators[source]})
    if sum(len(raw) for raw in raw_files.values()) > MAX_PHYSICAL_BYTES:
        raise HTTPException(409, "Üç kaynağın tam dosyaları 6 MiB sınırını aşıyor; kısmi paket verilmedi")
    graph = candidate_graph(packages, decision_ids, register_id, event, passages, locators)
    try:
        count = validate_candidate_physical({"structure": Graph(), "jurisprudence": graph}, ontology_root, physical)
    except (PreparationError, OSError):
        raise HTTPException(409, "Çok kaynaklı Graph B adayları yapı veya fiziksel dayanak doğrulamasından geçmedi") from None
    raw_files["candidate/jurisprudence.nt"] = ("\n".join(sorted(graph.serialize(format="nt").splitlines())) + "\n").encode("utf-8")
    files = {name: {"sha256": digest(raw), "bytes": len(raw), "encoding": "base64", "data": base64.b64encode(raw).decode("ascii")}
             for name, raw in sorted(raw_files.items())}
    core = {"schema_version": VERSION, "compiler_version": VERSION, "confidentiality": "firm_confidential", "firm_id": firm_id,
            "context_id": key, "equivalence_revision": len(events), "pins": equivalence.current_pins(captured),
            "decision_source_ids": decision_ids, "register_source_id": register_id,
            "canonical_candidate": event["proposal"]["claims"]["canonical_decision_id"], "original_decisions": event["proposal"]["decisions"],
            "source_bindings": {source: reviews._binding(package) for source, package in packages.items()},
            "ontology_sha256": ontology_sha, "equivalence_history": events, "identity_histories": captured["identities"],
            "source_review_histories": {source: value["source_history"] for source, value in captured["sources"].items()},
            "mapping_histories": {source: value["mapping_history"] for source, value in captured["sources"].items()}, "history_complete": True,
            "files": {name: {k: v for k, v in entry.items() if k != "data"} for name, entry in files.items()},
            "structural_validation": {"conforms": True, "assertion_count": count, "legal_truth_verified": False},
            "omitted_mapping_ids": {source: sorted(item["id"] for item in captured["sources"][source]["state"]["items"]
                if source not in decision_ids or item["id"] not in bound["identities"][source][-1]["proposal"]["own_mapping_ids"]) for source in packages},
            "scope": "reviewed_equivalence_identity_candidates_only", "signed": False, "graph_updated": False,
            "identity_reservations_changed": False, "global_registry_qualified": False, "legal_effect_verified": False,
            "institutional_competence_verified": False, "publication_eligible": False,
            "limitations": ["Paket ve bütün inceleme geçmişleri büroya özeldir; ortak grafa otomatik aktarılmaz.",
                            "Altı ilişki yalnızca kimlik adayıdır; yapı doğrulaması hukuki doğruluk veya yayımlama izni değildir.",
                            "Özgün iki kimlik ve belge sürümleri korunur; genel veya geçişli eşdeğerlik kurulmaz.",
                            "Sicil yalnızca kurum kimliği dayanağıdır; görev/yetki, tarihsel geçerlilik ve hukuki etki bilinmiyor."]}
    packet_id = digest(canonical(core))
    payload = canonical({**core, "packet_id": packet_id, "files": files})
    if len(payload) > MAX_PACKET_BYTES:
        raise HTTPException(409, "Tam çok kaynaklı Graph B paketi 16 MiB sınırını aşıyor; kısmi paket verilmedi")
    return {"evidence_json": payload.decode("utf-8"), "evidence_sha256": digest(payload)}, ontology_sha


def build_handoff(request, source_id, peer_source_id, register_source_id, body, user):
    packages, decision_ids, key = equivalence.context(request, source_id, peer_source_id, register_source_id, user)
    store = request.app.state.store
    ontology_root = ROOT / "ontology"
    try:
        with store.session() as session:
            current = reviews._lock_identity(session, request, user)
            role = current.role
            captured = equivalence.capture(store, session, packages, decision_ids, current.firm_id, lock=True)
            events = equivalence.ledger(store, session, equivalence._head(session, current.firm_id, key), packages, decision_ids, captured)
            if body.expected_revision != len(events) or body.pins.model_dump() != equivalence.current_pins(captured):
                raise equivalence._error()
            state = equivalence.view(packages, decision_ids, key, captured, events, current, source_id)
            bound = equivalence.snapshot(packages, captured, decision_ids, body.pins.model_dump())
            if not state["same_decision_supported"] or not all(value["export_allowed"] for value in bound["sources"].values()):
                raise HTTPException(409, "Güncel bağımsız aynı-karar kabulü ve üç kaynağın açık dışa aktarma izni gerekir")
            result, ontology_sha = compile_packet(packages, decision_ids, key, captured, bound, events, current.firm_id, ontology_root)
            equivalence.verify(request, packages, user)
            if (_load_serving()._release.ontology_digest(ontology_root) != ontology_sha
                    or reviews._lock_identity(session, request, user).role != role
                    or equivalence.capture(store, session, packages, decision_ids, current.firm_id, lock=True) != captured
                    or equivalence.ledger(store, session, equivalence._head(session, current.firm_id, key), packages, decision_ids, captured) != events):
                raise equivalence._error()
            return result
    except (OperationalError, OSError, ValueError):
        raise equivalence._error() from None
