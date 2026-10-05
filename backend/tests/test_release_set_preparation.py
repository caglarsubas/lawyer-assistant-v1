"""Synthetic combined-review compiler tests; no live ledgers or legal approvals."""

import copy
import json

import pytest
from rdflib import RDF, Graph, Literal
from test_preparation_publication_gate import release, trust_and_attestation
from test_release_preparation import ONTOLOGY, refresh_fixture_binding, sha
from test_release_preparation import preparation as single_preparation

from app import release_preparation as single
from app import release_set_preparation as compiler
from app.provision_candidates import find_candidates

LA = single.LA


def replace_package(preparation, *, text=None, raw=None, suffix="second"):
    """Reimport only isolated fixture bytes and coherently rebuild their mappings."""
    public, incoming, args, metadata, _ = preparation["source_parts"]
    previous = preparation["snapshot"]["package"]
    text = previous.text if text is None else text
    raw = previous.raw if raw is None else raw
    metadata = {**metadata, "title": "ISOLATED COMBINED TEST " + suffix,
                "source_version_id": "engineering-set-" + suffix}
    passages, offset = [], 0
    for index, line in enumerate(text.splitlines(keepends=True)):
        exact = line.rstrip("\r\n")
        if exact:
            passages.append({"id": f"p{index}", "start": offset, "end": offset + len(exact),
                             "locator": f"engineering line {index}", "text_sha256": sha(exact.encode())})
        offset += len(line)
    locators = {"schema_version": "public-locators-v1", "offset_unit": "unicode_code_points",
                "raw_sha256": sha(raw), "text_sha256": sha(text.encode()), "passages": passages}
    for filename, value in (("source.json", metadata), ("locators.json", locators)):
        (incoming / filename).write_bytes(single.canonical(value))
    (incoming / "raw.bin").write_bytes(raw)
    (incoming / "text.txt").write_bytes(text.encode())
    package = public.verified_package(public.import_package(**args)["id"])
    snapshot = preparation["snapshot"]
    snapshot["package"] = package
    snapshot["state"]["source"] = package.detail
    snapshot["source_review"]["source_binding"] = {
        "source_id": package.detail["id"], "artifacts": package.detail["artifacts"],
    }
    snapshot["binding"].update(source_id=package.detail["id"], source_artifacts=package.detail["artifacts"],
                               source_version_id=package.metadata.source_version_id)
    candidates = find_candidates(package)["items"]
    assert len(candidates) == len(snapshot["state"]["items"])
    for item, candidate in zip(snapshot["state"]["items"], candidates, strict=True):
        item.update(candidate_id=candidate["id"], span=candidate["proposed_span"],
                    passage_ids=candidate["passage_ids"])
        item["resolution"].update(start=candidate["proposed_span"]["start"],
                                 end=candidate["proposed_span"]["end"])
    preparation["source_parts"] = (public, incoming, args, metadata, locators)
    refresh_fixture_binding(preparation)


def refresh_set(preparation):
    """Create the exact nonauthorizing set envelope around independent v1 snapshots."""
    for source in preparation["sources"]:
        refresh_fixture_binding(source)
    snapshots = sorted((source["snapshot"] for source in preparation["sources"]),
                       key=lambda snapshot: snapshot["binding"]["source_id"])
    binding = {"schema_version": "legal-review-snapshot-set-v1",
               "firm_id": snapshots[0]["binding"]["firm_id"],
               "operator_id": snapshots[0]["binding"]["operator_id"],
               "sources": [copy.deepcopy(snapshot["binding"]) for snapshot in snapshots],
               "publication_eligible": False}
    summary = {"schema_version": "legal-review-snapshot-set-summary-v1", "source_count": len(snapshots),
               "mapping_count": sum(len(snapshot["state"]["items"]) for snapshot in snapshots),
               "artifact_bytes": sum(len(raw) for snapshot in snapshots for raw in snapshot["package"].artifacts.values()),
               "binding_sha256": sha(single.canonical(binding)),
               "consistency_mode": "sqlite_demo_optimistic_revalidation", "signed": False,
               "publication_eligible": False, "confidentiality": "firm_confidential"}
    preparation["snapshot_set"] = {"snapshots": snapshots, "binding": binding, "summary": summary}
    preparation["resolutions"] = {
        "schema_version": "provision-source-set-resolutions-v1",
        "sources": [{"source_id": source["snapshot"]["binding"]["source_id"],
                     "items": copy.deepcopy(source["resolutions"]["items"])} for source in preparation["sources"]],
    }
    entities = {}
    for source in preparation["sources"]:
        for entity in source["registry"]["entities"]:
            if entity["id"] in entities:
                assert {key: value for key, value in entity.items() if key != "evidence_sha256"} == {
                    key: value for key, value in entities[entity["id"]].items() if key != "evidence_sha256"}
                entities[entity["id"]]["evidence_sha256"] = sorted(set(
                    entities[entity["id"]]["evidence_sha256"] + entity["evidence_sha256"]))
            else:
                entities[entity["id"]] = copy.deepcopy(entity)
    preparation["registry"] = {"schema_version": "legal-identity-registry-v1", "entities": list(entities.values())}
    preparation["evidence"] = {key: raw for source in preparation["sources"] for key, raw in source["evidence"].items()}


@pytest.fixture
def set_preparation(tmp_path):
    sources = []
    for index in range(2):
        directory = tmp_path / f"source-{index}"
        directory.mkdir()
        source = single_preparation.__wrapped__(directory)
        if index:
            replace_package(source, text="SECOND SOURCE HEADER\r\n\r\n" + source["snapshot"]["package"].text,
                            raw=source["snapshot"]["package"].raw + b" DIFFERENT RAW ARTIFACT")
            rename = {entity["id"]: entity["id"] + "-second" for entity in source["registry"]["entities"]}
            for entity in source["registry"]["entities"]:
                entity["id"] = rename[entity["id"]]
                entity["parent_id"] = rename.get(entity["parent_id"])
            for identity in source["resolutions"]["items"]:
                for field in ("instrument_id", "provision_id", "provision_version_id"):
                    identity[field] = rename[identity[field]]
            proofs = {key: raw + b" SECOND SOURCE" for key, raw in source["evidence"].items()}
            replacement = {key: sha(raw) for key, raw in proofs.items()}
            source["evidence"] = {sha(raw): raw for raw in proofs.values()}
            for entity in source["registry"]["entities"]:
                entity["evidence_sha256"] = [replacement[key] for key in entity["evidence_sha256"]]
            for assessment in source["snapshot"]["source_review"]["assessments"].values():
                for ref in assessment["evidence_refs"]:
                    ref["sha256"] = replacement[ref["sha256"]]
        sources.append(source)
    result = {"sources": sources, "ontology_root": ONTOLOGY}
    refresh_set(result)
    return result


def compile_fixture(preparation):
    return compiler.compile_review_set(**{key: preparation[key] for key in (
        "snapshot_set", "registry", "resolutions", "evidence", "ontology_root")})


def open_preparation(preparation, *, checked):
    item = preparation["snapshot"]["state"]["items"][0]
    support = preparation["snapshot"]["package"].locators.passages[1]
    item["resolution"]["valid_until"] = None
    item["resolution"]["open_ended_validity"] = {
        "checked_through": checked, "evidence_start": support.start, "evidence_end": support.end,
    }


def share_versions(preparation):
    first, second = preparation["sources"]
    second["resolutions"] = copy.deepcopy(first["resolutions"])
    second["registry"] = copy.deepcopy(first["registry"])
    # Retain both identity proof sets in the explicit common registry.
    second_identity = next(key for key, raw in second["evidence"].items() if b"IDENTITY" in raw)
    for entity in second["registry"]["entities"]:
        entity["evidence_sha256"] = [second_identity]
    refresh_set(preparation)


def test_two_sources_keep_exact_quotes_and_private_review_material_out_of_rdf(set_preparation):
    files, summary = compile_fixture(set_preparation)
    assert summary["rdf_generated"] is True
    assert summary["signed"] is summary["publication_eligible"] is False
    assert summary["confidentiality"] == "firm_confidential"
    assert summary["blocker_codes"] == []
    data = Graph().parse(data=files["candidate/structure.ttl"], format="turtle")
    sources = {source["snapshot"]["package"].locators.raw_sha256: source["snapshot"]["package"]
               for source in set_preparation["sources"]}
    assert len(set(data.subjects(RDF.type, LA.SourceArtifact))) == 2
    assert len(set(data.subjects(RDF.type, LA.ProvisionVersion))) == 4
    for passage in data.subjects(RDF.type, LA.EvidencePassage):
        artifact = data.value(passage, LA.artifact)
        source = sources[str(data.value(artifact, LA.contentHash))]
        start, end = int(data.value(passage, LA.startOffset)), int(data.value(passage, LA.endOffset))
        assert str(data.value(passage, LA.quotedText)) == source.text[start:end]
    for name, raw in files.items():
        if name.startswith("candidate/"):
            assert b"PRIVATE " not in raw and b"private-reviewer-id" not in raw
            assert all(item["id"].encode() not in raw for source in set_preparation["sources"]
                       for item in source["snapshot"]["state"]["items"])
    assert b"PRIVATE " not in single.canonical(summary)
    manifest = json.loads(files["candidate/sources.json"])
    assert manifest["schema_version"] == "provision-source-set-public-candidates-v1"
    expected = {f"candidate/sources/{source['snapshot']['binding']['source_id']}/{name}"
                for source in set_preparation["sources"] for name in ("raw.bin", "text.txt", "locators.json")}
    assert set(manifest["files"]) == expected
    for name, details in manifest["files"].items():
        assert details == {"sha256": sha(files[name]), "bytes": len(files[name])}
    other = Graph().parse(data=files["candidate/jurisprudence.ttl"], format="turtle")
    assert release._validation.validate_graph(
        data + other, Graph().parse(ONTOLOGY / "shapes.ttl", format="turtle"), release.load_schema(ONTOLOGY))[0]


def test_compilation_is_deterministic_with_source_local_mapping_id_collisions(set_preparation):
    first, second = set_preparation["sources"]
    assert [item["id"] for item in first["snapshot"]["state"]["items"]] == [
        item["id"] for item in second["snapshot"]["state"]["items"]]
    keys = ("snapshot_set", "registry", "resolutions", "evidence")
    original = copy.deepcopy({key: set_preparation[key] for key in keys})
    expected = compile_fixture(set_preparation)
    assert {key: set_preparation[key] for key in keys} == original
    snapshot = copy.deepcopy(set_preparation["snapshot_set"])
    set_preparation["snapshot_set"]["snapshots"].reverse()
    set_preparation["registry"]["entities"].reverse()
    set_preparation["resolutions"]["sources"].reverse()
    for source in set_preparation["resolutions"]["sources"]:
        source["items"].reverse()
    assert compile_fixture(set_preparation) == expected
    set_preparation["snapshot_set"]["snapshots"].reverse()
    assert set_preparation["snapshot_set"] == snapshot


def test_same_canonical_versions_allow_independent_source_offsets(set_preparation):
    share_versions(set_preparation)
    first, second = set_preparation["sources"]
    assert first["snapshot"]["state"]["items"][0]["span"]["start"] != second["snapshot"]["state"]["items"][0]["span"]["start"]
    files, summary = compile_fixture(set_preparation)
    assert summary["rdf_generated"] is True and not summary["blocker_codes"]
    data = Graph().parse(data=files["candidate/structure.ttl"], format="turtle")
    assert len(set(data.subjects(RDF.type, LA.ProvisionVersion))) == 2
    assert len(set(data.subjects(RDF.type, LA.SourceArtifact))) == 2


@pytest.mark.parametrize("change", ["text", "period", "role", "open_horizon", "open_proof"])
def test_shared_version_disagreement_blocks_all_candidate_graphs(set_preparation, change):
    share_versions(set_preparation)
    first, second = set_preparation["sources"]
    expected = "provision_version_identity_conflict"
    if change == "text":
        replace_package(second, text=second["snapshot"]["package"].text.replace("İşlem", "Farklı işlem"))
    elif change == "period":
        second["snapshot"]["state"]["items"][0]["resolution"]["valid_until"] = "2013-01-01"
    elif change == "role":
        second["snapshot"]["state"]["items"][0]["resolution"]["text_role"] = "transitional_text"
    else:
        open_preparation(first, checked="2025-01-01")
        open_preparation(second, checked="2025-01-02" if change == "open_horizon" else "2025-01-01")
        if change == "open_proof":
            expected = "shared_open_validity_evidence_requires_reconciliation"
    refresh_set(set_preparation)
    files, summary = compile_fixture(set_preparation)
    assert not summary["rdf_generated"] and expected in summary["blocker_codes"]
    assert "candidate/structure.ttl" not in files and "candidate/jurisprudence.ttl" not in files


def test_inconsistent_canonical_parent_chain_is_not_silently_reassigned(set_preparation):
    share_versions(set_preparation)
    item = set_preparation["resolutions"]["sources"][1]["items"][0]
    item["provision_id"] = set_preparation["resolutions"]["sources"][1]["items"][1]["provision_id"]
    with pytest.raises(single.PreparationError):
        compile_fixture(set_preparation)


@pytest.mark.parametrize("period", ["overlap", "adjacent", "open_ended"])
def test_cross_source_version_intervals_use_real_ends_not_observation_horizons(set_preparation, period):
    first, second = set_preparation["sources"]
    original, replacement = first["resolutions"]["items"][0], second["resolutions"]["items"][0]
    replacement["instrument_id"] = original["instrument_id"]
    replacement["provision_id"] = original["provision_id"]
    next(entity for entity in second["registry"]["entities"] if entity["id"] == replacement["provision_version_id"])[
        "parent_id"] = original["provision_id"]
    if period == "adjacent":
        second["snapshot"]["state"]["items"][0]["resolution"].update(
            valid_from="2012-01-01", valid_until="2013-01-01")
    elif period == "open_ended":
        open_preparation(first, checked="2025-01-01")
        second["snapshot"]["state"]["items"][0]["resolution"].update(
            valid_from="2025-01-02", valid_until="2026-01-01")
    refresh_set(set_preparation)
    files, summary = compile_fixture(set_preparation)
    if period == "adjacent":
        assert summary["rdf_generated"] and summary["blocker_codes"] == []
    else:
        assert not summary["rdf_generated"]
        assert "provision_version_interval_conflict" in summary["blocker_codes"]
        assert "candidate/structure.ttl" not in files


@pytest.mark.parametrize("field", ["valid_from", "valid_until"])
def test_unknown_dates_stay_explicit_and_block_combined_graph_generation(set_preparation, field):
    item = set_preparation["sources"][1]["snapshot"]["state"]["items"][0]
    item["resolution"][field] = None
    refresh_set(set_preparation)
    files, summary = compile_fixture(set_preparation)
    assert not summary["rdf_generated"] and "unknown_" + field in summary["blocker_codes"]
    assert "candidate/structure.ttl" not in files
    assert item["resolution"][field] is None
    source_id = set_preparation["sources"][1]["snapshot"]["binding"]["source_id"]
    source = next(source for source in json.loads(files["review-report.json"])["sources"]
                  if source["source_id"] == source_id)
    assert next(unknown for unknown in source["mapping_unknowns"] if unknown["mapping_id"] == item["id"])[field] is None


def test_duplicate_raw_artifact_cannot_claim_two_acquisition_dates(set_preparation):
    first, second = set_preparation["sources"]
    source_parts = list(second["source_parts"])
    source_parts[3] = {**source_parts[3], "acquired_at": "2025-01-02T00:00:00Z"}
    second["source_parts"] = tuple(source_parts)
    replace_package(second, raw=first["snapshot"]["package"].raw)
    refresh_set(set_preparation)
    files, summary = compile_fixture(set_preparation)
    assert not summary["rdf_generated"]
    assert "source_artifact_acquisition_conflict" in summary["blocker_codes"]
    assert "candidate/structure.ttl" not in files


def test_same_raw_artifact_with_agreed_acquisition_keeps_distinct_representations(set_preparation):
    first, second = set_preparation["sources"]
    replace_package(second, raw=first["snapshot"]["package"].raw)
    refresh_set(set_preparation)
    files, summary = compile_fixture(set_preparation)
    assert summary["rdf_generated"] and not summary["blocker_codes"]
    graph = Graph().parse(data=files["candidate/structure.ttl"], format="turtle")
    assert len(set(graph.subjects(RDF.type, LA.SourceArtifact))) == 1
    assert len(set(graph.subjects(RDF.type, LA.SourceRepresentation))) == 2


@pytest.mark.parametrize("change", ["rights", "revision", "binding", "source_count", "package", "foreign_firm"])
def test_every_source_and_aggregate_binding_must_remain_current(set_preparation, change):
    snapshot = set_preparation["sources"][1]["snapshot"]
    if change == "rights":
        snapshot["source_review"]["assessments"]["rights"]["permitted_uses"].remove("local_inference")
        refresh_set(set_preparation)
    elif change == "revision":
        snapshot["state"]["revision"] += 1
    elif change == "binding":
        set_preparation["snapshot_set"]["summary"]["binding_sha256"] = "f" * 64
    elif change == "source_count":
        set_preparation["snapshot_set"]["summary"]["source_count"] = 1
    elif change == "package":
        snapshot["package"].artifacts["text.txt"] = b"changed"
    elif change == "foreign_firm":
        snapshot["binding"]["firm_id"] = "different-firm"
        snapshot["source_review"]["context"]["firm_id"] = "different-firm"
        refresh_set(set_preparation)
    with pytest.raises(single.PreparationError):
        compile_fixture(set_preparation)


@pytest.mark.parametrize("change", ["missing_source", "extra_source", "duplicate_source", "missing_proof", "extra_proof"])
def test_resolutions_and_evidence_cover_the_exact_selected_source_set(set_preparation, change):
    plan = set_preparation["resolutions"]["sources"]
    if change == "missing_source":
        plan.pop()
    elif change == "extra_source":
        plan.append({**copy.deepcopy(plan[0]), "source_id": "f" * 64})
    elif change == "duplicate_source":
        plan.append(copy.deepcopy(plan[0]))
    elif change == "missing_proof":
        set_preparation["evidence"].pop(next(iter(set_preparation["sources"][1]["evidence"])))
    elif change == "extra_proof":
        raw = b"PRIVATE UNUSED PROOF"
        set_preparation["evidence"][sha(raw)] = raw
    with pytest.raises(single.PreparationError):
        compile_fixture(set_preparation)


def test_missing_mapping_resolution_is_source_qualified_and_never_guessed(set_preparation):
    group = set_preparation["resolutions"]["sources"][1]
    missing = group["items"].pop()
    files, summary = compile_fixture(set_preparation)
    assert not summary["rdf_generated"] and summary["resolved_count"] == 3
    assert summary["blocker_codes"] == ["unresolved_identity"]
    report = json.loads(files["review-report.json"])
    assert report["blockers"] == [{"code": "unresolved_identity", "source_id": group["source_id"],
                                   "mapping_id": missing["mapping_id"]}]
    assert "candidate/structure.ttl" not in files


@pytest.mark.parametrize("budget,limit", [
    ("MAX_ARTIFACT_BYTES", 1), ("MAX_MAPPINGS", 3), ("MAX_OUTPUT_BYTES", 1),
    ("MAX_ASSERTION_EVIDENCE_LINKS", 8),
])
def test_aggregate_budgets_fail_before_combined_rdf_allocation(set_preparation, monkeypatch, budget, limit):
    # Each source has two mappings/six evidence links. The combined caps must
    # apply to their total, even when each individual source would fit.
    monkeypatch.setattr(compiler, budget, limit)
    monkeypatch.setattr(single, "_rdf", lambda *args, **kwargs: pytest.fail("Over-budget RDF must not allocate"))
    with pytest.raises(single.PreparationError):
        compile_fixture(set_preparation)


def test_conflict_packet_keeps_exact_private_inputs_and_never_claims_publication(set_preparation):
    share_versions(set_preparation)
    set_preparation["sources"][1]["snapshot"]["state"]["items"][0]["resolution"]["valid_until"] = "2013-01-01"
    refresh_set(set_preparation)
    files, summary = compile_fixture(set_preparation)
    assert not summary["rdf_generated"]
    assert json.loads(files["binding.json"]) == set_preparation["snapshot_set"]["binding"]
    for key, raw in set_preparation["evidence"].items():
        assert files[f"private-evidence/{key}.bin"] == raw
    assert summary["signed"] is summary["publication_eligible"] is False
    assert b"PRIVATE " not in single.canonical(summary)


def test_both_graphs_remain_preparation_only_even_with_exact_trusted_test_signature(set_preparation, tmp_path):
    files, _ = compile_fixture(set_preparation)
    paths = {}
    for family in ("structure", "jurisprudence"):
        raw = files[f"candidate/{family}.ttl"]
        data = Graph().parse(data=raw, format="turtle")
        assert list(data.triples((None, LA.reviewPreparationOnly, Literal(True))))
        paths[family] = tmp_path / f"{family}.ttl"
        paths[family].write_bytes(raw)
    _, key, attestation, _ = trust_and_attestation(tmp_path, paths)
    evidence = tmp_path / "must-not-publish-evidence"
    evidence.mkdir()
    destination = tmp_path / "must-not-publish"
    with pytest.raises(ValueError, match="(?i)preparation|review.only"):
        release.create_bundle(ONTOLOGY, paths, evidence, destination, attestation, key)
    assert not destination.exists()
