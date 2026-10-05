"""Deterministic, private preparation across exact reviewed source snapshots.

The live caller owns authorization and holds all source locks. This compiler
independently checks input structure, evidence, identities and bounded RDF. It
never resolves a disagreement, promotes an assertion or grants publication rights.
"""

import json
from datetime import date
from pathlib import Path
from typing import Literal as TypeLiteral

from pydantic import ConfigDict, Field, model_validator
from rdflib import Graph

from . import release_preparation as single
from .public_sources import FILES, VerifiedPublicSource
from .release_snapshot_set import MAX_ARTIFACT_BYTES, MAX_MAPPINGS, MAX_SOURCES

VERSION = "provision-source-set-preparation-v1"
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_ASSERTION_EVIDENCE_LINKS = 25_000
PreparationError = single.PreparationError


class SourceResolutions(single.StrictInput):
    source_id: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    items: list[single.IdentityResolution] = Field(max_length=200)


class SourceSetResolutions(single.StrictInput):
    model_config = ConfigDict(extra="forbid", strict=True, revalidate_instances="always")

    schema_version: TypeLiteral["provision-source-set-resolutions-v1"]
    sources: list[SourceResolutions] = Field(min_length=2, max_length=MAX_SOURCES)

    @model_validator(mode="after")
    def unique_sources(self):
        if len({source.source_id for source in self.sources}) != len(self.sources):
            raise ValueError("Source resolution groups must be unique")
        return self


def _snapshots(value):
    try:
        if type(value) is not dict or set(value) != {"snapshots", "binding", "summary"}:
            raise ValueError()
        snapshots = value["snapshots"]
        if type(snapshots) is not list or not 2 <= len(snapshots) <= MAX_SOURCES:
            raise ValueError()
        records, artifact_bytes, mapping_count = [], 0, 0
        for snapshot in snapshots:
            # Enforce aggregate bounds before decoding source JSON or materializing
            # mapping projections. A pure compiler may receive forged Python input.
            package, items = snapshot["package"], snapshot["state"]["items"]
            if (not isinstance(package, VerifiedPublicSource) or type(package.artifacts) is not dict
                    or not {"raw.bin", "text.txt", "locators.json", "source.json"}.issubset(package.artifacts)
                    or not set(package.artifacts).issubset(FILES) or type(items) is not list
                    or not 1 <= len(items) <= 200):
                raise ValueError()
            for name, raw in package.artifacts.items():
                if type(raw) is not bytes or not 0 < len(raw) <= FILES[name]:
                    raise ValueError()
                artifact_bytes += len(raw)
            mapping_count += len(items)
            if artifact_bytes > MAX_ARTIFACT_BYTES or mapping_count > MAX_MAPPINGS:
                raise ValueError()
            package, mappings, rights = single._snapshot(snapshot)
            records.append((snapshot, package, mappings, rights))
        records.sort(key=lambda row: row[1].detail["id"])
        identifiers = [row[1].detail["id"] for row in records]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError()
        bindings = [row[0]["binding"] for row in records]
        firm, operator = bindings[0]["firm_id"], bindings[0]["operator_id"]
        if any(item["firm_id"] != firm or item["operator_id"] != operator for item in bindings):
            raise ValueError()
        binding = {"schema_version": "legal-review-snapshot-set-v1", "firm_id": firm,
                   "operator_id": operator, "sources": bindings, "publication_eligible": False}
        if single.canonical(value["binding"]) != single.canonical(binding):
            raise ValueError()
        mode = value["summary"]["consistency_mode"]
        if mode not in {"postgresql_transaction_locks", "sqlite_demo_optimistic_revalidation"}:
            raise ValueError()
        summary = {"schema_version": "legal-review-snapshot-set-summary-v1", "source_count": len(records),
                   "mapping_count": mapping_count, "artifact_bytes": artifact_bytes,
                   "binding_sha256": single.digest(single.canonical(binding)), "consistency_mode": mode,
                   "signed": False, "publication_eligible": False, "confidentiality": "firm_confidential"}
        if single.canonical(value["summary"]) != single.canonical(summary):
            raise ValueError()
        return records, binding, summary
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
        raise PreparationError("Source-set snapshot, binding or aggregate limits are invalid") from None


def _identities(registry, resolutions, records):
    try:
        registry, entities = single._registry(registry)
        # These arrays represent sets; their ordering must not alter packet bytes.
        registry["entities"].sort(key=lambda item: item["id"])
        for entity in registry["entities"]:
            entity["evidence_sha256"].sort()
        parsed = SourceSetResolutions.model_validate(resolutions).model_dump()
        if {item["source_id"] for item in parsed["sources"]} != {row[1].detail["id"] for row in records}:
            raise PreparationError("Resolution source groups must exactly match the selected source set")
        inputs = {item["source_id"]: item["items"] for item in parsed["sources"]}
        identity_maps, normalized = {}, []
        for _, package, mappings, _ in records:
            source_id = package.detail["id"]
            resolution, identity_maps[source_id] = single._resolutions(
                {"schema_version": "provision-identity-resolutions-v1", "items": inputs[source_id]},
                mappings, entities)
            resolution["items"].sort(key=lambda item: item["mapping_id"])
            normalized.append({"source_id": source_id, "items": resolution["items"]})
        return registry, entities, {"schema_version": parsed["schema_version"], "sources": normalized}, identity_maps
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
        raise PreparationError("Source-qualified identity inputs are invalid") from None


def _version_signature(item, identity):
    resolution = item["resolution"]
    support = resolution.get("open_ended_validity")
    # Equal legal text may occupy different offsets in different publications.
    # Temporal evidence is not merged into assertions from another source.
    return (item["span"]["sha256"], item["kind"], identity["instrument_id"], identity["provision_id"],
            resolution["valid_from"], resolution["valid_until"], resolution["text_role"],
            "open_ended" if support else "closed" if resolution["valid_until"] else "unknown",
            support["checked_through"] if support else None)


def _cross_source_blockers(records, identities):
    blockers, versions, artifacts, periods = [], {}, {}, {}
    for _, package, mappings, _ in records:
        source_id = package.detail["id"]
        prior_artifact = artifacts.get(package.locators.raw_sha256)
        if prior_artifact and prior_artifact[1] != package.metadata.acquired_at:
            blockers.append({"code": "source_artifact_acquisition_conflict", "source_id": source_id,
                             "other_source_id": prior_artifact[0]})
        artifacts.setdefault(package.locators.raw_sha256, (source_id, package.metadata.acquired_at))
        for mapping_id, item in sorted(mappings.items()):
            identity = identities[source_id].get(mapping_id)
            if identity is None:
                continue
            version = identity["provision_version_id"]
            signature = _version_signature(item, identity)
            reference = {"source_id": source_id, "mapping_id": mapping_id, "provision_version_id": version}
            prior = versions.get(version)
            if prior and prior[1]["source_id"] != source_id:
                if prior[0] != signature:
                    blockers.append({"code": "provision_version_identity_conflict", **reference,
                                     "other_source_id": prior[1]["source_id"],
                                     "other_mapping_id": prior[1]["mapping_id"]})
                elif item["resolution"].get("open_ended_validity"):
                    # Passage IDs include the source package ID. Existing temporal
                    # shapes demand identical evidence sets on a shared open version
                    # and each linking assertion. Adding another source's proof would
                    # silently change the assertion; require explicit reconciliation.
                    blockers.append({"code": "shared_open_validity_evidence_requires_reconciliation", **reference,
                                     "other_source_id": prior[1]["source_id"],
                                     "other_mapping_id": prior[1]["mapping_id"]})
            versions.setdefault(version, (signature, reference))
            resolution = item["resolution"]
            if resolution["valid_from"] is None or (resolution["valid_until"] is None
                                                     and not resolution.get("open_ended_validity")):
                continue
            start = date.fromisoformat(resolution["valid_from"])
            end = date.fromisoformat(resolution["valid_until"]) if resolution["valid_until"] else None
            for other in periods.setdefault(identity["provision_id"], []):
                other_source, other_version, other_start, other_end, other_mapping = other
                if (other_source != source_id and other_version != version
                        and (other_end is None or start < other_end) and (end is None or other_start < end)):
                    blockers.append({"code": "provision_version_interval_conflict", **reference,
                                     "other_source_id": other_source, "other_mapping_id": other_mapping,
                                     "other_provision_version_id": other_version})
            periods[identity["provision_id"]].append((source_id, version, start, end, mapping_id))
    return blockers


def _graph_budget(records, current_bytes):
    links, estimated_bytes, passages = 0, current_bytes, set()
    for _, package, mappings, _ in records:
        estimated_bytes += 8192 * len(mappings) + 4096
        for item in mappings.values():
            spans = [(item["span"]["start"], item["span"]["end"], 2)]
            support = item["resolution"].get("open_ended_validity")
            if support:
                spans.append((support["evidence_start"], support["evidence_end"], 3))
            for start, end, owners in spans:
                for source in package.locators.passages:
                    left, right = max(start, source.start), min(end, source.end)
                    if left >= right or not package.text[left:right].strip():
                        continue
                    links += owners
                    key = (package.detail["id"], source.id, left, right)
                    if key not in passages:
                        passages.add(key)
                        # Conservative allowance for escaped text and passage triples.
                        estimated_bytes += 2 * len(package.text[left:right].encode("utf-8")) + 2048
                    if links > MAX_ASSERTION_EVIDENCE_LINKS or estimated_bytes > MAX_OUTPUT_BYTES:
                        raise PreparationError("Combined candidate graph exceeds its preparation budget")


def _validate_graphs(graphs, ontology_root, physical):
    release = single._load_serving()._release
    stripped = {}
    for family, graph in graphs.items():
        plain = Graph()
        for triple in graph:
            if triple[1] != single.LA.reviewPreparationOnly:
                plain.add(triple)
        stripped[family] = plain
    try:
        checked = release.check_data(stripped, ontology_root, {"verified": False})
        if set(release.required_physical_hashes(checked)) != set(physical):
            raise ValueError()
        for passage in checked["passages"]:
            representation = checked["representations"][passage["representation_id"]]
            text = physical[representation["text_sha256"]].decode("utf-8")
            locators = json.loads(physical[representation["locator_map_sha256"]])
            if (text[passage["start"]:passage["end"]] != passage["text"]
                    or not any(span["locator"] == passage["locator"]
                               and span["start"] <= passage["start"] < passage["end"] <= span["end"]
                               for span in locators["spans"])):
                raise ValueError()
        return checked["assertions"]
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise PreparationError("Combined candidate RDF or physical evidence failed validation") from None


def _output_budget(files):
    if sum(len(raw) for raw in files.values()) > MAX_OUTPUT_BYTES:
        raise PreparationError("Combined review files exceed the output byte budget")


def compile_review_set(snapshot_set: dict, registry: dict, resolutions: dict,
                       evidence: dict[str, bytes], ontology_root: Path) -> tuple[dict[str, bytes], dict]:
    records, binding, source_summary = _snapshots(snapshot_set)
    registry, entities, resolutions, identities = _identities(registry, resolutions, records)
    required = {value for entity in entities.values() for value in entity["evidence_sha256"]}
    for _, _, _, rights in records:
        required.update(rights)
    evidence = single._evidence(evidence, required)
    blockers = []
    for _, package, mappings, _ in records:
        blockers.extend({**item, "source_id": package.detail["id"]}
                        for item in single._blockers(package, mappings, identities[package.detail["id"]]))
    blockers.extend(_cross_source_blockers(records, identities))
    blockers.sort(key=single.canonical)
    ontology_sha = single._load_serving()._release.ontology_digest(ontology_root)
    files = {"binding.json": single.canonical(binding), "registry.json": single.canonical(registry),
             "resolutions.json": single.canonical(resolutions),
             **{"private-evidence/" + key + ".bin": evidence[key] for key in sorted(required)}}
    source_inventory, physical, public_candidates = {}, {}, {}
    for _, package, _, _ in records:
        source_id = package.detail["id"]
        public, _ = single._public_candidates(package)
        public_candidates[source_id] = public
        for path, raw in public.items():
            name = f"candidate/sources/{source_id}/{Path(path).name}"
            files[name] = raw
            fingerprint = single.digest(raw)
            source_inventory[name] = {"sha256": fingerprint, "bytes": len(raw)}
            if fingerprint in physical and physical[fingerprint] != raw:
                raise PreparationError("Public physical evidence identity is ambiguous")
            physical[fingerprint] = raw
    files["candidate/sources.json"] = single.canonical({
        "schema_version": "provision-source-set-public-candidates-v1", "files": source_inventory})
    _output_budget(files)
    assertion_count = 0
    if not blockers:
        _graph_budget(records, sum(len(raw) for raw in files.values()))
        graphs = {"structure": Graph(), "jurisprudence": Graph()}
        for _, package, mappings, _ in records:
            source_id = package.detail["id"]
            generated = single._rdf(package, mappings, identities[source_id],
                                    public_candidates[source_id]["candidate/locators.json"])
            for family, graph in generated.items():
                graphs[family] += graph
        assertion_count = _validate_graphs(graphs, ontology_root, physical)
        for family, graph in graphs.items():
            lines = sorted(line for line in graph.serialize(format="nt").splitlines() if line.strip())
            files[f"candidate/{family}.ttl"] = ("\n".join(lines) + "\n").encode("utf-8")
    report = {"schema_version": VERSION, "source_count": len(records),
              "mapping_count": source_summary["mapping_count"],
              "resolved_count": sum(len(items) for items in identities.values()),
              "assertion_count": assertion_count, "blockers": blockers, "rdf_generated": not blockers,
              "signed": False, "publication_eligible": False, "confidentiality": "firm_confidential",
              "all_files_confidential": True,
              "evidence_verification": "sha256_match_only", "identity_status": "operator_proposed_not_certified",
              "recorded_at_origin": "mapping_review_event_time_private_workflow_metadata",
              "input_digests": {"ontology_sha256": ontology_sha,
                               **{name.removesuffix(".json") + "_sha256": single.digest(files[name])
                                  for name in ("binding.json", "registry.json", "resolutions.json")},
                               "private_evidence_sha256": sorted(required)},
              "sources": [{"source_id": package.detail["id"], "source_acquired_at": package.metadata.acquired_at,
                           "mapping_count": len(mappings), "resolved_count": len(identities[package.detail["id"]]),
                           "mapping_unknowns": [{"mapping_id": identifier,
                                                 **{key: item["resolution"][key] for key in
                                                    ("valid_from", "valid_until", "text_role")},
                                                 **({"open_ended_validity": item["resolution"]["open_ended_validity"]}
                                                    if item["resolution"].get("open_ended_validity") else {})}
                                                for identifier, item in sorted(mappings.items())]}
                          for _, package, mappings, _ in records]}
    files["review-report.json"] = single.canonical(report)
    _output_budget(files)
    summary = {key: report[key] for key in ("schema_version", "source_count", "mapping_count", "resolved_count",
                                          "assertion_count", "rdf_generated", "signed", "publication_eligible",
                                          "confidentiality")}
    summary.update(blocker_codes=sorted({item["code"] for item in blockers}), ontology_sha256=ontology_sha,
                   binding_sha256=report["input_digests"]["binding_sha256"],
                   report_sha256=single.digest(files["review-report.json"]), file_count=len(files),
                   output_bytes=sum(len(raw) for raw in files.values()))
    return files, summary
