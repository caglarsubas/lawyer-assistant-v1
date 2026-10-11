"""Private, grounded Graph B candidates. No graph mutation or publication."""
import base64

from fastapi import HTTPException
from pydantic import Field, StrictInt
from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef
from sqlalchemy.exc import OperationalError

from . import decision_identities as identities
from . import decision_mappings as mappings
from . import source_reviews as reviews
from .config import ROOT
from .graph_release import _load_serving
from .release_preparation import PreparationError, _validate_rdf, canonical, digest
from .source_reviews import StrictInput

VERSION = "decision-graph-b-handoff-v1"
LA = Namespace("https://lawyer-assistant.local/ontology/")
MAX_PHYSICAL_BYTES = 2 * 1024 * 1024
MAX_PACKET_BYTES = 8 * 1024 * 1024
MAX_PASSAGES = 50


class HandoffInput(StrictInput):
    expected_revision: StrictInt = Field(ge=1, le=identities.MAX_EVENTS)
    expected_mapping_revision: StrictInt = Field(ge=1, le=mappings.MAX_EVENTS)
    expected_source_review_revision: StrictInt = Field(ge=1, le=reviews.MAX_EVENTS)


def _passage_references(package, captured, event):
    """Resolve exact retained passages only; free text and external hashes stay unknown."""
    passages = {f"source:{package.detail['id']}:passage:{p.id}": p for p in package.locators.passages}
    reviewed = set(captured["source_review"]["reviewed_passage_ids"])
    result = set()
    proposal = event["proposal"]
    refs = proposal["identity"]["identity_evidence"] + proposal["identity"]["institution_evidence"] + event["evidence_refs"]
    for ref in refs:
        passage = passages.get(ref["reference"])
        if passage is None or passage.text_sha256 != ref["sha256"] or passage.id not in reviewed:
            raise HTTPException(409, "Devir için kimlik, kurum ve bağımsız inceleme dayanakları bu kaynağın incelemesi kabul edilmiş tam pasaj referansı ve SHA256'sı olmalı; harici dayanaklar henüz çözümlenemiyor")
        result.add(passage.id)
    for item in captured["state"]["items"]:
        if item["id"] in proposal["own_mapping_ids"]:
            span = mappings._validate_resolution(mappings.Resolution.model_validate(item["resolution"]), item["candidate"], package)
            result.update(span["passage_ids"])
    if not result or len(result) > MAX_PASSAGES or not result.issubset(reviewed):
        raise HTTPException(409, "Tam devir dayanakları pasaj sınırını veya inceleme kapsamını aşıyor")
    return [p for p in package.locators.passages if p.id in result]


def source_evidence(graph, package, passages, locator_raw, *, compiler_version=VERSION, scoped_artifact=False):
    artifact = URIRef("urn:la:source:" + (digest(canonical([package.detail["id"], package.locators.raw_sha256, compiler_version])) if scoped_artifact else package.locators.raw_sha256))
    representation = URIRef("urn:la:representation:" + digest(canonical([
        package.detail["id"], package.locators.text_sha256, digest(locator_raw), compiler_version])))
    for node, kind in ((artifact, LA.SourceArtifact), (representation, LA.SourceRepresentation)):
        graph.add((node, RDF.type, kind))
        graph.add((node, LA.scope, Literal("public")))
        graph.add((node, LA.synthetic, Literal(False)))
    for key, value in ((LA.contentHash, Literal(package.locators.raw_sha256)), (LA.rightsStatus, Literal("permitted")),
                       (LA.fetchedAt, Literal(package.metadata.acquired_at, datatype=XSD.dateTime))):
        graph.add((artifact, key, value))
    for key, value in ((LA.artifact, artifact), (LA.contentHash, Literal(package.locators.text_sha256)),
                       (LA.locatorMapHash, Literal(digest(locator_raw))),
                       (LA.extractionMethod, Literal("verified_public_source_locator_conversion")), (LA.extractorVersion, Literal(compiler_version))):
        graph.add((representation, key, value))
    evidence = []
    for passage in passages:
        node = URIRef("urn:la:passage:" + digest(canonical([package.detail["id"], passage.id, passage.start, passage.end] + ([compiler_version] if scoped_artifact else []))))
        evidence.append(node)
        for key, value in ((RDF.type, LA.EvidencePassage), (LA.scope, Literal("public")), (LA.artifact, artifact),
                           (LA.textRepresentation, representation), (LA.startOffset, Literal(passage.start, datatype=XSD.integer)),
                           (LA.endOffset, Literal(passage.end, datatype=XSD.integer)), (LA.locator, Literal(passage.locator)),
                           (LA.quotedText, Literal(package.text[passage.start:passage.end]))):
            graph.add((node, key, value))
    return evidence


def _rdf(package, event, passages, locator_raw):
    graph = Graph()
    proposal = event["proposal"]
    identity = proposal["identity"]
    decision, proceeding, institution, version = (URIRef(value) for value in (
        identity["decision_id"], identity["proceeding_id"], identity["institution_id"], proposal["version_id"]))
    for node, kind in ((decision, LA.JudicialDecision), (proceeding, LA.Proceeding),
                       (institution, LA.Institution), (version, LA.DecisionVersion)):
        graph.add((node, RDF.type, kind))
        graph.add((node, LA.scope, Literal("public")))
    evidence = source_evidence(graph, package, passages, locator_raw)
    for predicate, obj in ((LA.decidedIn, proceeding), (LA.issuedBy, institution), (LA.hasDecisionVersion, version)):
        assertion = URIRef("urn:la:decision-assertion-proposal:" + digest(canonical([
            str(decision), str(predicate), str(obj), proposal["snapshot_sha256"], event["id"], VERSION])))
        for key, value in ((RDF.type, LA.Assertion), (LA.subject, decision), (LA.predicate, predicate), (LA.object, obj),
                           (LA.scope, Literal("public")), (LA.graphFamily, Literal("jurisprudence")),
                           (LA.claimStatus, Literal("unreviewed")), (LA.synthetic, Literal(False)),
                           (LA.recordedAt, Literal(event["created_at"], datatype=XSD.dateTime)),
                           (LA.validityStatus, Literal("unknown")),
                           (LA.unresolvedReason, Literal("Candidate identity relationship; legal validity and effects require separate review")),
                           (LA.extractionMethod, Literal("explicit_identity_and_independent_account_review")),
                           (LA.extractorVersion, Literal(VERSION))):
            graph.add((assertion, key, value))
        for node in evidence:
            graph.add((assertion, LA.evidence, node))
    # The marker is rejected by existing publication bundle tooling. It is never
    # stripped in the exported candidate, only in the engineering validation view.
    marker = URIRef("urn:la:decision-preparation:" + proposal["snapshot_sha256"])
    graph.add((marker, LA.reviewPreparationOnly, Literal(True)))
    return graph


def compile_packet(package, captured, events, firm_id, ontology_root):
    release = _load_serving()._release
    ontology_sha = release.ontology_digest(ontology_root)
    event = events[-1]
    passages = _passage_references(package, captured, event)
    locator = {"schema_version": 1, "artifact_sha256": package.locators.raw_sha256,
               "text_sha256": package.locators.text_sha256, "extractor_version": VERSION,
               "spans": [{"locator": p.locator, "start": p.start, "end": p.end} for p in package.locators.passages]}
    locator_raw = canonical(locator)
    raw_files = {f"original/{name}": data for name, data in package.artifacts.items()}
    raw_files["candidate/locators.json"] = locator_raw
    if sum(len(data) for data in raw_files.values()) > MAX_PHYSICAL_BYTES:
        raise HTTPException(409, "Tam devir dosyaları 2 MiB sınırını aşıyor; kısmi paket verilmedi")
    graph = _rdf(package, event, passages, locator_raw)
    try:
        count = _validate_rdf({"structure": Graph(), "jurisprudence": graph}, ontology_root, package, locator_raw)
    except (PreparationError, OSError):
        raise HTTPException(409, "Graph B adayları yapı veya fiziksel dayanak doğrulamasından geçmedi") from None
    # No blank nodes; sorted N-Triples gives deterministic RDF bytes.
    raw_files["candidate/jurisprudence.nt"] = ("\n".join(sorted(graph.serialize(format="nt").splitlines())) + "\n").encode("utf-8")
    files = {name: {"sha256": digest(data), "bytes": len(data), "encoding": "base64",
                    "data": base64.b64encode(data).decode("ascii")} for name, data in sorted(raw_files.items())}
    core = {"schema_version": VERSION, "confidentiality": "firm_confidential", "firm_id": firm_id,
            "source_binding": reviews._binding(package), "identity_revision": len(events),
            "mapping_revision": captured["state"]["revision"], "source_review_revision": captured["state"]["source_review_revision"],
            "ontology_sha256": ontology_sha, "compiler_version": VERSION,
            "identity_history": events, "source_review_history": captured["source_history"],
            "mapping_history": captured["mapping_history"], "history_complete": True,
            "files": {name: {key: value for key, value in entry.items() if key != "data"} for name, entry in files.items()},
            "structural_validation": {"conforms": True, "assertion_count": count, "legal_truth_verified": False},
            "omitted_mapping_ids": sorted(item["id"] for item in captured["state"]["items"] if item["id"] not in event["proposal"]["own_mapping_ids"]),
            "scope": "own_decision_identity_candidates_only", "signed": False, "graph_updated": False,
            "global_registry_qualified": False, "legal_effect_verified": False, "publication_eligible": False,
            "limitations": ["Paket ve inceleme geçmişleri büroya özeldir; ortak grafa otomatik aktarılmaz.",
                            "Üç ilişki yalnızca kimlik adayıdır; yapı doğrulaması hukuki doğruluk veya yayımlama izni değildir.",
                            "Atıf hedefleri, tarihsel norm sürümleri, hukuki etki ve kesinleşme bu pakette çözümlenmez."]}
    packet_id = digest(canonical(core))
    payload = canonical({**core, "packet_id": packet_id, "files": files})
    if len(payload) > MAX_PACKET_BYTES:
        raise HTTPException(409, "Tam Graph B devir paketi 8 MiB sınırını aşıyor; kısmi paket verilmedi")
    return {"evidence_json": payload.decode("utf-8"), "evidence_sha256": digest(payload)}, ontology_sha


def build_handoff(request, source_id, body, user):
    package = reviews._package(request, source_id, user)
    store = request.app.state.store
    ontology_root = ROOT / "ontology"
    try:
        with store.session() as session:
            current = reviews._lock_identity(session, request, user)
            role = current.role
            captured = identities.capture(store, session, package, current.firm_id, lock=True)
            head = identities._head(session, current.firm_id, source_id)
            events = identities.ledger(store, session, head, package, captured)
            state = identities.view(package, captured, events, current)
            if (body.expected_revision != state["revision"] or body.expected_mapping_revision != state["mapping_revision"]
                    or body.expected_source_review_revision != state["source_review_revision"]
                    or not state["staged_handoff_ready"] or not state["export_allowed"]):
                raise HTTPException(409, "Devir için güncel bağımsız kimlik kabulü, üç güncel revizyon ve açık dışa aktarma izni gerekir")
            result, ontology_sha = compile_packet(package, captured, events, current.firm_id, ontology_root)
            identities.verify_package(request, source_id, package)
            if (_load_serving()._release.ontology_digest(ontology_root) != ontology_sha
                    or reviews._lock_identity(session, request, user).role != role
                    or identities.capture(store, session, package, current.firm_id, lock=True) != captured
                    or identities.ledger(store, session, identities._head(session, current.firm_id, source_id), package, captured) != events):
                raise identities._error()
            return result
    except (OperationalError, OSError, ValueError):
        raise identities._error() from None
