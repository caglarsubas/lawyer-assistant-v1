"""Pure, deterministic preparation of private legal-review inputs, never releases.

The live snapshot provider owns authentication, ledger integrity and freshness.
This compiler independently checks scopes, identities, evidence bytes and spans.
It never signs, publishes, infers missing legal dates, or resolves free-text IDs.
"""

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Literal as TypeLiteral

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef

from .graph_release import _load_serving
from .provision_candidates import span_details
from .provision_mappings import Resolution, validate_open_ended_validity
from .public_sources import SHA256, VerifiedPublicSource, _validate

VERSION = "provision-review-preparation-v1"
MAX_EVIDENCE_FILES = 128
MAX_EVIDENCE_FILE_BYTES = 8 * 1024 * 1024
MAX_EVIDENCE_TOTAL_BYTES = 32 * 1024 * 1024
MAX_ASSERTION_EVIDENCE_LINKS = 25_000
REQUIRED_USES = {"storage", "local_processing", "internal_display", "export", "indexing", "local_inference"}
LA = Namespace("https://lawyer-assistant.local/ontology/")
_ID = re.compile(r"^urn:tr-law:(instrument|provision|provision-version):[a-z0-9][a-z0-9.-]{0,119}$")
_MAPPING_ID = re.compile(r"^[a-f0-9]{32}$")
_KINDS = {"instrument": "instrument", "provision": "provision", "provision_version": "provision-version"}


class PreparationError(ValueError):
    """Only bounded, non-sensitive messages may cross the CLI boundary."""


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RegistryEntity(StrictInput):
    id: str
    kind: TypeLiteral["instrument", "provision", "provision_version"]
    parent_id: str | None
    evidence_sha256: list[str] = Field(min_length=1, max_length=10)

    @field_validator("evidence_sha256")
    @classmethod
    def evidence(cls, value):
        if len(set(value)) != len(value) or any(not SHA256.fullmatch(item) for item in value):
            raise ValueError("Invalid identity evidence hashes")
        return value


class Registry(StrictInput):
    schema_version: TypeLiteral["legal-identity-registry-v1"]
    entities: list[RegistryEntity] = Field(max_length=600)


class IdentityResolution(StrictInput):
    mapping_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    instrument_id: str
    provision_id: str
    provision_version_id: str


class Resolutions(StrictInput):
    schema_version: TypeLiteral["provision-identity-resolutions-v1"]
    items: list[IdentityResolution] = Field(max_length=200)


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _registry(value: dict) -> tuple[dict, dict]:
    try:
        parsed = Registry.model_validate(value)
    except (ValidationError, TypeError, ValueError):
        raise PreparationError("Identity registry schema is invalid") from None
    entities = {item.id: item.model_dump() for item in parsed.entities}
    if len(entities) != len(parsed.entities):
        raise PreparationError("Duplicate identity registry IDs")
    for item in entities.values():
        match = _ID.fullmatch(item["id"])
        if not match or match.group(1) != _KINDS[item["kind"]]:
            raise PreparationError("Identity registry namespace does not match its kind")
        if item["kind"] == "instrument":
            if item["parent_id"] is not None:
                raise PreparationError("Instrument registry entries cannot have a parent")
        else:
            parent_kind = "instrument" if item["kind"] == "provision" else "provision"
            if item["parent_id"] not in entities or entities[item["parent_id"]]["kind"] != parent_kind:
                raise PreparationError("Identity registry parent chain is invalid")
    return parsed.model_dump(), entities


def _resolutions(value: dict, mappings: dict, entities: dict) -> tuple[dict, dict]:
    try:
        parsed = Resolutions.model_validate(value)
    except (ValidationError, TypeError, ValueError):
        raise PreparationError("Identity resolution schema is invalid") from None
    items = {item.mapping_id: item.model_dump() for item in parsed.items}
    if len(items) != len(parsed.items):
        raise PreparationError("Duplicate mapping resolutions")
    for identifier, item in items.items():
        if identifier not in mappings:
            raise PreparationError("Resolution does not name a current accepted mapping")
        for field, kind in (("instrument_id", "instrument"), ("provision_id", "provision"),
                            ("provision_version_id", "provision_version")):
            if item[field] not in entities or entities[item[field]]["kind"] != kind:
                raise PreparationError("Resolution identity is missing or has the wrong kind")
        if (entities[item["provision_id"]]["parent_id"] != item["instrument_id"]
                or entities[item["provision_version_id"]]["parent_id"] != item["provision_id"]):
            raise PreparationError("Resolution parent chain does not match the registry")
    return parsed.model_dump(), items


def _snapshot(snapshot: dict) -> tuple[VerifiedPublicSource, dict, set[str]]:
    try:
        if set(snapshot) != {"package", "state", "source_review", "binding"}:
            raise ValueError()
        package, state, review = snapshot["package"], snapshot["state"], snapshot["source_review"]
        if not isinstance(package, VerifiedPublicSource) or not isinstance(snapshot["binding"], dict):
            raise ValueError()
        metadata, locators, text = _validate(package.artifacts)
        if (metadata != package.metadata.model_dump() or locators != package.locators or text != package.text
                or not SHA256.fullmatch(package.detail["id"])
                or set(package.detail["artifacts"]) != set(package.artifacts)
                or any(package.detail["artifacts"][name] != {"sha256": digest(raw), "bytes": len(raw)}
                       for name, raw in package.artifacts.items())
                or state["source"] != package.detail
                or type(state["source_review_revision"]) is not int or state["source_review_revision"] < 1
                or type(state["revision"]) is not int or state["revision"] < 1
                or review["context"]["revision"] != state["source_review_revision"]
                or review["source_binding"] != {"source_id": package.detail["id"], "artifacts": package.detail["artifacts"]}
                or set(review["assessments"]) != {"rights", "source_identity", "extraction", "legal"}
                or any(item["decision"] != "accepted" for item in review["assessments"].values())
                or not REQUIRED_USES.issubset(review["assessments"]["rights"]["permitted_uses"])
                or not state["source_review_ready"] or not state["handoff_ready"]
                or state["publication_eligible"] is not False
                or not 1 <= len(state["items"]) <= 200):
            raise ValueError()
        rights = review["assessments"]["rights"]["evidence_refs"]
        if not 1 <= len(rights) <= 10 or any(not SHA256.fullmatch(item["sha256"]) for item in rights):
            raise ValueError()
        mappings = {}
        for item in state["items"]:
            identifier = item["id"]
            if (not _MAPPING_ID.fullmatch(identifier) or identifier in mappings
                    or item["status"] != "accepted" or item["stale"] is not False
                    or item["reviewed_source_revision"] != state["source_review_revision"]
                    or item["non_whitespace_covered"] is not True):
                raise ValueError()
            resolved = Resolution.model_validate(item["resolution"])
            resolution = resolved.model_dump()
            details = span_details(package, resolution["start"], resolution["end"])
            if (item["span"] != details["span"] or item["passage_ids"] != details["passage_ids"]
                    or not details["non_whitespace_covered"] or not item["span"]["text"].strip()
                    or item["kind"] not in {"article", "temporary_article", "additional_article"}):
                raise ValueError()
            if (resolution["valid_from"] and resolution["valid_until"]
                    and resolution["valid_from"] >= resolution["valid_until"]):
                raise ValueError()
            # This timestamp is already an immutable review event, never generated here.
            recorded = datetime.fromisoformat(item["last_event"]["created_at"].replace("Z", "+00:00"))
            if recorded.tzinfo is None:
                raise ValueError()
            validate_open_ended_validity(resolved, package, item["last_event"]["created_at"])
            mappings[identifier] = {**item, "resolution": resolution}
        _binding(snapshot, mappings)
        return package, mappings, {item["sha256"] for item in rights}
    except (KeyError, TypeError, ValueError, AttributeError):
        raise PreparationError("Live review snapshot, rights scope or exact mapping evidence is invalid") from None


def _binding(snapshot, mappings):
    package, state, review, binding = (snapshot[key] for key in ("package", "state", "source_review", "binding"))
    fields = {"schema_version", "source_id", "source_version_id", "source_artifacts", "firm_id", "operator_id",
              "source_review_head_id", "mapping_head_id", "source_review_revision", "mapping_revision", "projections_sha256"}
    if (set(binding) != fields or binding["schema_version"] != "legal-review-snapshot-v1"
            or binding["source_id"] != package.detail["id"]
            or binding["source_version_id"] != package.metadata.source_version_id
            or binding["source_artifacts"] != package.detail["artifacts"]
            or binding["source_review_revision"] != state["source_review_revision"]
            or binding["mapping_revision"] != state["revision"]
            or any(type(binding[key]) is not int or not 1 <= binding[key] <= 1000
                   for key in ("source_review_revision", "mapping_revision"))
            or any(not isinstance(binding[key], str) or not 1 <= len(binding[key]) <= 64
                   for key in ("firm_id", "operator_id", "source_review_head_id", "mapping_head_id"))
            or binding["firm_id"] != review["context"]["firm_id"]
            or binding["source_review_head_id"] != review["context"]["head_id"]
            or binding["operator_id"] != review["assigned_to"]["id"]
            or state["assigned_to"] != review["assigned_to"]):
        raise ValueError("Inconsistent snapshot binding")
    snapshot_fields = {"candidate_id", "kind", "label", "span", "passage_ids", "non_whitespace_covered", "status",
                       "resolution", "reviewed_source_revision"}
    for identifier, item in mappings.items():
        event = item["last_event"]
        if (event["mapping_id"] != identifier or event["event_type"] != "review" or event["decision"] != "accepted"
                or event["source_review_revision"] != binding["source_review_revision"]
                or event["snapshot"] != {key: item[key] for key in snapshot_fields}
                or event["reviewer"]["id"] != binding["operator_id"]):
            raise ValueError("Inconsistent current mapping event")
    projection = {"source_binding": review["source_binding"],
                  "context": {"firm_id": binding["firm_id"], "head_id": binding["mapping_head_id"],
                              "revision": binding["mapping_revision"]},
                  "mappings": {identifier: item["last_event"] for identifier, item in mappings.items()}}
    if binding["projections_sha256"] != digest(canonical({"source_review": review, "provision_mappings": projection})):
        raise ValueError("Snapshot projection fingerprint differs")


def _evidence(evidence: dict[str, bytes], required: set[str]) -> dict[str, bytes]:
    if (not isinstance(evidence, dict) or not 1 <= len(evidence) <= MAX_EVIDENCE_FILES
            or set(evidence) != required):
        raise PreparationError("Identity and rights evidence is missing, extra or over capacity")
    total = 0
    for key, raw in evidence.items():
        if (not isinstance(key, str) or not SHA256.fullmatch(key) or type(raw) is not bytes
                or not 1 <= len(raw) <= MAX_EVIDENCE_FILE_BYTES or digest(raw) != key):
            raise PreparationError("Physical evidence does not match its digest or size limit")
        total += len(raw)
    if total > MAX_EVIDENCE_TOTAL_BYTES:
        raise PreparationError("Physical evidence exceeds the total size limit")
    return evidence


def _blockers(package, mappings, resolutions):
    blockers = []
    if package.metadata.acquired_at is None:
        blockers.append({"code": "unknown_acquired_at"})
    versions, periods = {}, {}
    for identifier, item in sorted(mappings.items()):
        resolution = item["resolution"]
        if identifier not in resolutions:
            blockers.append({"code": "unresolved_identity", "mapping_id": identifier})
        open_ended = resolution.get("open_ended_validity")
        for key in ("valid_from", "valid_until"):
            if resolution[key] is None and not (key == "valid_until" and open_ended):
                blockers.append({"code": "unknown_" + key, "mapping_id": identifier})
        if resolution["text_role"] not in {"operative_text", "transitional_text"}:
            blockers.append({"code": "unsupported_text_role", "mapping_id": identifier,
                             "text_role": resolution["text_role"]})
        if identifier not in resolutions:
            continue
        identity = resolutions[identifier]
        version = identity["provision_version_id"]
        fingerprint = (item["span"]["start"], item["span"]["end"], item["span"]["sha256"], item["kind"],
                       identity["instrument_id"], identity["provision_id"], resolution["valid_from"],
                       resolution["valid_until"], resolution["text_role"])
        if open_ended:
            support = span_details(package, open_ended["evidence_start"], open_ended["evidence_end"])
            fingerprint += ("open_ended", open_ended["checked_through"], support["span"]["start"],
                            support["span"]["end"], support["span"]["sha256"], tuple(support["passage_ids"]))
        if version in versions and versions[version] != fingerprint:
            raise PreparationError("Distinct provision spans or identities cannot share one version ID")
        versions[version] = fingerprint
        if resolution["valid_from"] is not None and (resolution["valid_until"] is not None or open_ended):
            # The checking horizon is an epistemic boundary, never a legal end.
            # Open-ended versions overlap all later versions until resolved.
            period = (date.fromisoformat(resolution["valid_from"]),
                      date.fromisoformat(resolution["valid_until"]) if resolution["valid_until"] else None)
            for old_version, old_period in periods.setdefault(identity["provision_id"], {}).items():
                if (old_version != version and (old_period[1] is None or period[0] < old_period[1])
                        and (period[1] is None or old_period[0] < period[1])):
                    raise PreparationError("Provision version validity intervals conflict")
            periods[identity["provision_id"]][version] = period
    return blockers


def _public_candidates(package):
    mapping = {"schema_version": 1, "artifact_sha256": package.locators.raw_sha256,
               "text_sha256": package.locators.text_sha256, "extractor_version": VERSION,
               "spans": [{"locator": p.locator, "start": p.start, "end": p.end} for p in package.locators.passages]}
    locator_raw = canonical(mapping)
    return {"candidate/raw.bin": package.raw, "candidate/text.txt": package.artifacts["text.txt"],
            "candidate/locators.json": locator_raw}, mapping


def _rdf(package, mappings, resolutions, locator_raw):
    # Fail before RDF allocation; repeated large spans must not amplify a small
    # input package into millions of assertion-to-passage triples.
    evidence_links = 0
    for item in mappings.values():
        spans = [(item["span"]["start"], item["span"]["end"], 2)]
        support = item["resolution"].get("open_ended_validity")
        if support:
            # Both assertions and their provision version carry temporal proof.
            spans.append((support["evidence_start"], support["evidence_end"], 3))
        for start, end, owners in spans:
            for source in package.locators.passages:
                left, right = max(start, source.start), min(end, source.end)
                if left < right and package.text[left:right].strip():
                    evidence_links += owners
                    if evidence_links > MAX_ASSERTION_EVIDENCE_LINKS:
                        raise PreparationError("Candidate assertion evidence links exceed preparation capacity")
    graph = Graph()
    raw_hash, text_hash, map_hash = package.locators.raw_sha256, package.locators.text_sha256, digest(locator_raw)
    artifact, representation = URIRef("urn:la:artifact:" + raw_hash), URIRef("urn:la:representation:" + map_hash)
    preparation = URIRef("urn:la:review-preparation:" + package.detail["id"])
    graph.add((preparation, LA.reviewPreparationOnly, Literal(True)))
    for node, kind in ((artifact, LA.SourceArtifact), (representation, LA.SourceRepresentation)):
        graph.add((node, RDF.type, kind))
        graph.add((node, LA.scope, Literal("public")))
        graph.add((node, LA.synthetic, Literal(False)))
    for predicate, value in ((LA.contentHash, Literal(raw_hash)), (LA.rightsStatus, Literal("permitted")),
                             (LA.fetchedAt, Literal(package.metadata.acquired_at, datatype=XSD.dateTime))):
        graph.add((artifact, predicate, value))
    for predicate, value in ((LA.artifact, artifact), (LA.contentHash, Literal(text_hash)),
                             (LA.locatorMapHash, Literal(map_hash)),
                             (LA.extractionMethod, Literal("verified_public_source_locator_conversion")),
                             (LA.extractorVersion, Literal(VERSION))):
        graph.add((representation, predicate, value))

    def add_passages(start, end):
        passages = []
        for source in package.locators.passages:
            left, right = max(start, source.start), min(end, source.end)
            if left >= right or not package.text[left:right].strip():
                continue
            passage_key = canonical([package.detail["id"], source.id, left, right])
            passage = URIRef("urn:la:passage:" + digest(passage_key))
            passages.append(passage)
            for predicate, value in ((RDF.type, LA.EvidencePassage), (LA.scope, Literal("public")),
                                     (LA.artifact, artifact), (LA.textRepresentation, representation),
                                     (LA.startOffset, Literal(left, datatype=XSD.integer)),
                                     (LA.endOffset, Literal(right, datatype=XSD.integer)),
                                     (LA.locator, Literal(source.locator)),
                                     (LA.quotedText, Literal(package.text[left:right]))):
                graph.add((passage, predicate, value))
        return passages

    for identifier, item in sorted(mappings.items()):
        identity, resolution = resolutions[identifier], item["resolution"]
        support = resolution.get("open_ended_validity")
        temporal = [(LA.validFrom, Literal(resolution["valid_from"], datatype=XSD.date))]
        if support:
            temporal += [(LA.validityEndStatus, Literal("open_ended")),
                         (LA.validityCheckedThrough, Literal(support["checked_through"], datatype=XSD.date))]
            temporal += [(LA.validityEvidence, passage)
                         for passage in add_passages(support["evidence_start"], support["evidence_end"])]
        else:
            temporal.append((LA.validTo, Literal(resolution["valid_until"], datatype=XSD.date)))
        instrument, provision, version = (URIRef(identity[field]) for field in
                                          ("instrument_id", "provision_id", "provision_version_id"))
        for node, kind in ((instrument, LA.LegalInstrument), (provision, LA.Provision), (version, LA.ProvisionVersion)):
            graph.add((node, RDF.type, kind))
            graph.add((node, LA.scope, Literal("public")))
            graph.add((node, LA.synthetic, Literal(False)))
        for predicate, value in [(LA.versionOf, provision), (LA.versionResolution, Literal("resolved")),
                                 (LA.textRole, Literal(resolution["text_role"])), *temporal]:
            graph.add((version, predicate, value))
        start, end = item["span"]["start"], item["span"]["end"]
        passages = add_passages(start, end)
        for subject, predicate, obj in ((instrument, LA.containsProvision, provision),
                                        (provision, LA.hasProvisionVersion, version)):
            identity_parts = [package.detail["id"], str(subject), str(predicate), str(obj), start, end,
                              resolution["valid_from"], resolution["valid_until"], resolution["text_role"]]
            if support:
                identity_parts.append({"validity_end_status": "open_ended", **support})
            assertion_key = canonical(identity_parts)
            assertion = URIRef("urn:la:assertion-proposal:" + digest(assertion_key))
            for key, value in ((RDF.type, LA.Assertion), (LA.subject, subject), (LA.predicate, predicate),
                               (LA.object, obj), (LA.scope, Literal("public")), (LA.synthetic, Literal(False)),
                               (LA.graphFamily, Literal("structure")), (LA.claimStatus, Literal("unreviewed")),
                               (LA.validityStatus, Literal("known")),
                               (LA.recordedAt, Literal(item["last_event"]["created_at"], datatype=XSD.dateTime)),
                               (LA.extractionMethod, Literal("explicit_reviewed_span_identity_proposal")),
                               (LA.extractorVersion, Literal(VERSION))):
                graph.add((assertion, key, value))
            for key, value in temporal:
                graph.add((assertion, key, value))
            for passage in passages:
                graph.add((assertion, LA.evidence, passage))
    empty = Graph()
    empty.add((preparation, LA.reviewPreparationOnly, Literal(True)))
    return {"structure": graph, "jurisprudence": empty}


def _validate_rdf(graphs, ontology_root, package, locator_raw):
    release = _load_serving()._release
    stripped = {}
    for family, graph in graphs.items():
        plain = Graph()
        for triple in graph:
            if triple[1] != LA.reviewPreparationOnly:
                plain.add(triple)
        stripped[family] = plain
    try:
        checked = release.check_data(stripped, ontology_root, {"verified": False})
    except (ValueError, TypeError, KeyError):
        raise PreparationError("Candidate RDF failed structural validation") from None
    physical = {package.locators.raw_sha256: package.raw, package.locators.text_sha256: package.artifacts["text.txt"],
                digest(locator_raw): locator_raw}
    if set(release.required_physical_hashes(checked)) != set(physical):
        raise PreparationError("Candidate RDF physical evidence binding is inconsistent")
    for passage in checked["passages"]:
        representation = checked["representations"][passage["representation_id"]]
        text = physical[representation["text_sha256"]].decode("utf-8")
        locators = json.loads(physical[representation["locator_map_sha256"]])
        if (text[passage["start"]:passage["end"]] != passage["text"]
                or not any(span["locator"] == passage["locator"]
                           and span["start"] <= passage["start"] < passage["end"] <= span["end"]
                           for span in locators["spans"])):
            raise PreparationError("Candidate evidence quote is not grounded in its original locator")
    return checked["assertions"]


def compile_review(snapshot: dict, registry: dict, resolutions: dict,
                   evidence: dict[str, bytes], ontology_root: Path) -> tuple[dict[str, bytes], dict]:
    package, mappings, rights_hashes = _snapshot(snapshot)
    registry, entities = _registry(registry)
    resolutions, identity_map = _resolutions(resolutions, mappings, entities)
    required = rights_hashes | {value for entity in entities.values() for value in entity["evidence_sha256"]}
    evidence = _evidence(evidence, required)
    blockers = _blockers(package, mappings, identity_map)
    release = _load_serving()._release
    ontology_sha = release.ontology_digest(ontology_root)
    files = {"binding.json": canonical(snapshot["binding"]), "registry.json": canonical(registry),
             "resolutions.json": canonical(resolutions),
             **{"private-evidence/" + key + ".bin": evidence[key] for key in sorted(required)}}
    public, _ = _public_candidates(package)
    files.update(public)
    assertions = 0
    if not blockers:
        graphs = _rdf(package, mappings, identity_map, public["candidate/locators.json"])
        assertions = _validate_rdf(graphs, ontology_root, package, public["candidate/locators.json"])
        for family, graph in graphs.items():
            lines = sorted(line for line in graph.serialize(format="nt").splitlines() if line.strip())
            files[f"candidate/{family}.ttl"] = ("\n".join(lines) + "\n").encode("utf-8")
    inputs = {"source_id": package.detail["id"], "raw_sha256": package.locators.raw_sha256,
              "text_sha256": package.locators.text_sha256, "ontology_sha256": ontology_sha,
              "binding_sha256": digest(files["binding.json"]), "registry_sha256": digest(files["registry.json"]),
              "resolutions_sha256": digest(files["resolutions.json"]),
              "private_evidence_sha256": sorted(required)}
    report = {"schema_version": VERSION, "input_digests": inputs, "mapping_count": len(mappings),
              "resolved_count": len(identity_map), "assertion_count": assertions, "blockers": blockers,
              "rdf_generated": not blockers, "signed": False, "publication_eligible": False,
              "confidentiality": "firm_confidential", "source_acquired_at": package.metadata.acquired_at,
              "evidence_verification": "sha256_match_only", "identity_status": "operator_proposed_not_certified",
              "recorded_at_origin": "mapping_review_event_time_private_workflow_metadata",
              "mapping_unknowns": [{"mapping_id": identifier,
                                    "valid_from": item["resolution"]["valid_from"],
                                    "valid_until": item["resolution"]["valid_until"],
                                    "text_role": item["resolution"]["text_role"],
                                    **({"open_ended_validity": item["resolution"]["open_ended_validity"]}
                                       if item["resolution"].get("open_ended_validity") else {})}
                                   for identifier, item in sorted(mappings.items())]}
    files["review-report.json"] = canonical(report)
    summary = {key: report[key] for key in ("schema_version", "mapping_count", "resolved_count", "assertion_count",
                                           "rdf_generated", "signed", "publication_eligible", "confidentiality")}
    summary.update(blocker_codes=sorted({item["code"] for item in blockers}), ontology_sha256=ontology_sha,
                   binding_sha256=inputs["binding_sha256"], report_sha256=digest(files["review-report.json"]),
                   file_count=len(files))
    return files, summary
