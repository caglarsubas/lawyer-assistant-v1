"""Pure source-set conversion fixtures, never real legal approval or publication."""

import copy
import json

import pytest
from rdflib import RDF, XSD, Graph, Literal, URIRef
from test_release_preparation import preparation as single_preparation
from test_release_set_preparation import compile_fixture, open_preparation, refresh_set, replace_package
from test_release_set_preparation import set_preparation as set_preparation_fixture

from app import release_preparation as preparation
from app import release_promotion as single
from app import release_set_promotion as promotion

set_preparation = set_preparation_fixture
LA = preparation.LA
REVIEWER = "Intentional public engineering reviewer"
REVIEWED_AT = "2026-01-01T00:00:00Z"


@pytest.fixture
def files(set_preparation):
    return compile_fixture(set_preparation)[0]


def promote(files):
    return promotion.promoted_graphs(files, REVIEWER, REVIEWED_AT)


def test_exact_combined_transformation_preserves_evidence_and_legal_temporality(set_preparation):
    open_preparation(set_preparation["sources"][0], checked="2025-01-01")
    refresh_set(set_preparation)
    files, _ = compile_fixture(set_preparation)
    before = copy.deepcopy(files)
    output = promote(files)
    assert output == promote(dict(reversed(list(files.items()))))
    assert files == before
    assert set(output) == {"structure", "jurisprudence"}
    for family, raw in output.items():
        expected = Graph().parse(data=files[f"candidate/{family}.ttl"], format="turtle")
        expected.remove((None, LA.reviewPreparationOnly, None))
        for assertion in expected.subjects(RDF.type, LA.Assertion):
            for predicate, value in (
                (LA.claimStatus, Literal("legally_reviewed")), (LA.reviewer, Literal(REVIEWER)),
                (LA.reviewedAt, Literal(REVIEWED_AT, datatype=XSD.dateTime)),
                (LA.recordedAt, Literal(REVIEWED_AT, datatype=XSD.dateTime)),
            ):
                expected.set((assertion, predicate, value))
        actual = Graph().parse(data=raw, format="turtle")
        assert set(actual) == set(expected)
        assert not list(actual.triples((None, LA.reviewPreparationOnly, None)))
        assert b"2025-02-01T00:00:00" not in raw and b"PRIVATE " not in raw
    structure = Graph().parse(data=output["structure"], format="turtle")
    assert list(structure.objects(None, LA.validityCheckedThrough))
    assert list(structure.objects(None, LA.validityEvidence))


def test_signing_outputs_exclude_private_selection_identity_notes_and_proofs(files):
    ontology_hash = json.loads(files["review-report.json"])["input_digests"]["ontology_sha256"]
    output = promotion.signing_inputs(files, ontology_sha256=ontology_hash,
                                      public_reviewer=REVIEWER, reviewed_at=REVIEWED_AT)
    public = promotion.public_evidence(files)
    expected = {"inputs/structure.ttl", "inputs/jurisprudence.ttl", "public-review-body.json", "NOTICE.json"}
    assert set(output) == expected | {f"evidence/{digest}.bin" for digest in public}
    for digest, raw in public.items():
        assert output[f"evidence/{digest}.bin"] == raw
        assert preparation.digest(raw) == digest
    notice = json.loads(output["NOTICE.json"])
    assert notice["schema_version"] == promotion.TRANSFORMATION == "reviewed-provision-set-promotion-v1"
    assert notice["signed"] is notice["publication_eligible"] is False
    assert notice["confidentiality"] == "firm_confidential"
    body = json.loads(output["public-review-body.json"])
    assert set(body) == {"reviewer", "reviewed_at", "decision", "scope", "ontology_sha256", "input_graphs_sha256"}
    assert body["input_graphs_sha256"] == {
        family: preparation.digest(output[f"inputs/{family}.ttl"]) for family in ("structure", "jurisprudence")}
    binding = json.loads(files["binding.json"])
    private = [binding["firm_id"].encode(), binding["operator_id"].encode(), b"PRIVATE "]
    private += [source["source_id"].encode() for source in binding["sources"]]
    private += [raw for name, raw in files.items() if name.startswith("private-evidence/")]
    assert all(secret not in raw for raw in output.values() for secret in private)


def test_signing_cannot_substitute_another_ontology_digest(files):
    with pytest.raises(ValueError):
        promotion.signing_inputs(files, ontology_sha256="f" * 64,
                                 public_reviewer=REVIEWER, reviewed_at=REVIEWED_AT)


def test_identical_public_copies_deduplicate_without_dropping_distinct_source_checks(set_preparation):
    first, second = set_preparation["sources"]
    replace_package(second, raw=first["snapshot"]["package"].raw, text=first["snapshot"]["package"].text)
    refresh_set(set_preparation)
    files, _ = compile_fixture(set_preparation)
    public = promotion.public_evidence(files)
    assert len(public) == 3
    assert set(public.values()) == {raw for name, raw in files.items() if name.startswith("candidate/sources/")}
    assert promote(files)["structure"]


@pytest.mark.parametrize("family", ["structure", "jurisprudence"])
@pytest.mark.parametrize("change", ["missing", "extra", "forged", "false", "second_value"])
def test_both_graphs_need_exact_true_marker_subjects_for_every_bound_source(files, family, change):
    name = f"candidate/{family}.ttl"
    graph = Graph().parse(data=files[name], format="turtle")
    marker = next(graph.triples((None, LA.reviewPreparationOnly, None)))
    forged = URIRef("urn:la:review-preparation:" + "f" * 64)
    if change in {"missing", "forged", "false"}:
        graph.remove(marker)
    if change in {"extra", "forged"}:
        graph.add((forged, LA.reviewPreparationOnly, Literal(True)))
    elif change in {"false", "second_value"}:
        graph.add((marker[0], LA.reviewPreparationOnly, Literal(False)))
    files[name] = graph.serialize(format="nt").encode()
    with pytest.raises(ValueError):
        promote(files)


@pytest.mark.parametrize("change", [
    "missing_file", "extra_file", "private_alias", "changed_bytes", "forged_digest", "boolean_bytes", "locator_binding",
])
def test_public_candidate_manifest_is_an_exact_hash_verified_allowlist(files, change):
    manifest = json.loads(files["candidate/sources.json"])
    name = next(path for path in manifest["files"] if path.endswith("raw.bin"))
    if change == "missing_file":
        del files[name]
    elif change == "extra_file":
        files["candidate/private-notes.txt"] = b"PRIVATE EXTRA NOTES"
    elif change == "private_alias":
        private_name = next(path for path in files if path.startswith("private-evidence/"))
        manifest["files"][private_name] = {
            "sha256": preparation.digest(files[private_name]), "bytes": len(files[private_name])}
    elif change == "changed_bytes":
        files[name] += b" conflicting source bytes"
    elif change == "forged_digest":
        manifest["files"][name]["sha256"] = "f" * 64
    elif change == "boolean_bytes":
        manifest["files"][name]["bytes"] = True
    elif change == "locator_binding":
        name = name.removesuffix("raw.bin") + "locators.json"
        locators = json.loads(files[name])
        locators["artifact_sha256"] = "f" * 64
        files[name] = preparation.canonical(locators)
        manifest["files"][name] = {"sha256": preparation.digest(files[name]), "bytes": len(files[name])}
    files["candidate/sources.json"] = preparation.canonical(manifest)
    with pytest.raises(ValueError):
        promotion.public_evidence(files)


@pytest.mark.parametrize("change", ["one_source", "duplicate_source", "unknown_schema", "foreign_firm", "unbound_report"])
def test_source_set_binding_contract_cannot_be_forged(files, change):
    binding = json.loads(files["binding.json"])
    if change == "one_source":
        binding["sources"].pop()
    elif change == "duplicate_source":
        binding["sources"][1] = binding["sources"][0]
    elif change == "unknown_schema":
        binding["schema_version"] = "legal-review-snapshot-v1"
    elif change == "foreign_firm":
        binding["sources"][1]["firm_id"] = "foreign-firm"
    else:
        binding["sources"][0]["mapping_revision"] += 1
    files["binding.json"] = preparation.canonical(binding)
    if change != "unbound_report":
        report = json.loads(files["review-report.json"])
        report["input_digests"]["binding_sha256"] = preparation.digest(files["binding.json"])
        files["review-report.json"] = preparation.canonical(report)
    with pytest.raises(ValueError):
        promote(files)


@pytest.mark.parametrize("change", [
    "missing_graph", "malformed_graph", "blocked_report", "already_reviewed", "unsupported_effect", "review_time",
])
def test_incomplete_or_unsupported_review_conversion_is_rejected(files, change):
    if change == "missing_graph":
        del files["candidate/structure.ttl"]
    elif change == "malformed_graph":
        files["candidate/structure.ttl"] = b"PRIVATE malformed graph CANARY !"
    elif change == "blocked_report":
        report = json.loads(files["review-report.json"])
        report["blockers"] = [{"code": "unresolved_identity"}]
        report["rdf_generated"] = False
        files["review-report.json"] = preparation.canonical(report)
    else:
        graph = Graph().parse(data=files["candidate/structure.ttl"], format="turtle")
        assertion = next(graph.subjects(RDF.type, LA.Assertion))
        if change == "already_reviewed":
            graph.set((assertion, LA.claimStatus, Literal("legally_reviewed")))
        elif change == "unsupported_effect":
            graph.set((assertion, LA.predicate, LA.applies))
        else:
            graph.set((assertion, LA.recordedAt, Literal("2099-01-01T00:00:00Z", datatype=XSD.dateTime)))
        files["candidate/structure.ttl"] = graph.serialize(format="nt").encode()
    with pytest.raises(ValueError) as error:
        promote(files)
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("bound", ["MAX_PACKET_BYTES", "MAX_FILE_BYTES"])
def test_input_budgets_precede_rdf_parsing(files, monkeypatch, bound):
    monkeypatch.setattr(promotion, bound, 1)
    monkeypatch.setattr(promotion, "_promoted_graphs", lambda *args, **kwargs: pytest.fail("Over-budget graph parse"))
    with pytest.raises(ValueError):
        promote(files)


def test_v1_public_api_stays_single_source_and_set_api_rejects_v1(files, tmp_path):
    with pytest.raises(ValueError):
        single.promoted_graphs(files, REVIEWER, REVIEWED_AT)
    directory = tmp_path / "single"
    directory.mkdir()
    source = single_preparation.__wrapped__(directory)
    old_files, _ = preparation.compile_review(**{key: source[key] for key in (
        "snapshot", "registry", "resolutions", "evidence", "ontology_root")})
    assert single.promoted_graphs(old_files, REVIEWER, REVIEWED_AT)
    with pytest.raises(ValueError):
        promote(old_files)
