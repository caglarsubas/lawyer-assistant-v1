"""Pure compiler engineering fixtures only; no legal approval or production writes."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from rdflib import RDF, Graph, Literal, Namespace, URIRef

import app.release_preparation as compiler
from app.provision_candidates import find_candidates, span_details
from app.public_sources import PublicSourceStore

ONTOLOGY = Path(__file__).resolve().parents[2] / "ontology"
LA = Namespace("https://lawyer-assistant.local/ontology/")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def preparation(tmp_path):
    """Snapshot-shaped fixture in isolated storage, not an authenticated review."""
    text = "MADDE 1- İşlem ⚖️.\r\nİkinci satır I\u0307.\r\n\r\nGEÇİCİ MADDE 2- Teknik deneme."
    raw = b"ISOLATED UNIT TEST raw bytes; no actual legal authority."
    metadata = {
        "schema_version": "public-source-v1",
        "title": "ISOLATED ENGINEERING TEST",
        "source_url": "https://www.mevzuat.gov.tr/mevzuatmetin/1.5.6098.pdf",
        "source_version_id": "engineering-fixture-v1",
        "domain": "contracts",
        "acquired_at": "2025-01-01T00:00:00Z",
        "published_on": None,
        "effective_from": None,
        "effective_until": None,
        "data_classification": "public",
        "origin": "public_legal_source",
        "contains_private_matter_data": False,
        "synthetic": False,
        "raw_media_type": "application/pdf",
    }
    passages, offset = [], 0
    for index, line in enumerate(text.splitlines(keepends=True)):
        exact = line.rstrip("\r\n")
        if exact:
            passages.append(
                {
                    "id": f"p{index}",
                    "start": offset,
                    "end": offset + len(exact),
                    "locator": f"engineering line {index}",
                    "text_sha256": sha(exact.encode()),
                }
            )
        offset += len(line)
    locators = {
        "schema_version": "public-locators-v1",
        "offset_unit": "unicode_code_points",
        "raw_sha256": sha(raw),
        "text_sha256": sha(text.encode()),
        "passages": passages,
    }
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    for filename, content in (("source.json", metadata), ("locators.json", locators)):
        (incoming / filename).write_bytes(compiler.canonical(content))
    (incoming / "text.txt").write_bytes(text.encode())
    (incoming / "raw.bin").write_bytes(raw)
    public = PublicSourceStore(tmp_path / "public")
    args = {
        "metadata_path": incoming / "source.json",
        "raw_path": incoming / "raw.bin",
        "text_path": incoming / "text.txt",
        "locators_path": incoming / "locators.json",
    }
    record = public.import_package(**args)
    package = public.verified_package(record["id"])
    identity_proof = b"PRIVATE IDENTITY PROOF CANARY, not public candidate material"
    rights_proof = b"PRIVATE RIGHTS PROOF CANARY, not public candidate material"
    evidence = {sha(identity_proof): identity_proof, sha(rights_proof): rights_proof}
    identity_hash, rights_hash = sha(identity_proof), sha(rights_proof)
    reviewer = {"id": "private-reviewer-id", "name": "PRIVATE REVIEWER NAME CANARY"}
    source_review = {
        "source_binding": {"source_id": package.detail["id"], "artifacts": package.detail["artifacts"]},
        "context": {"firm_id": "PRIVATE FIRM CANARY", "head_id": "review-head", "revision": 5},
        "assigned_to": reviewer,
        "assessments": {
            category: {
                "decision": "accepted",
                "reviewer": reviewer,
                "rationale": "PRIVATE RATIONALE CANARY",
                "permitted_uses": sorted(compiler.REQUIRED_USES) if category == "rights" else [],
                "evidence_refs": [{"reference": "PRIVATE REFERENCE CANARY", "sha256": rights_hash}],
            }
            for category in ("rights", "source_identity", "extraction", "legal")
        },
    }
    mappings, entities, resolutions = [], [], []
    instrument = "urn:tr-law:instrument:engineering-fixture"
    entities.append(
        {"id": instrument, "kind": "instrument", "parent_id": None, "evidence_sha256": [identity_hash]}
    )
    for index, candidate in enumerate(find_candidates(package)["items"], start=1):
        mapping_id = f"{index:032x}"
        provision, version = (
            f"urn:tr-law:provision:engineering-{index}",
            f"urn:tr-law:provision-version:engineering-{index}",
        )
        mappings.append(
            {
                "id": mapping_id,
                "candidate_id": candidate["id"],
                "kind": candidate["kind"],
                "label": "PRIVATE FREEFORM LABEL CANARY",
                "span": candidate["proposed_span"],
                "passage_ids": candidate["passage_ids"],
                "non_whitespace_covered": True,
                "status": "accepted",
                "stale": False,
                "reviewed_source_revision": 5,
                "resolution": {
                    "start": candidate["proposed_span"]["start"],
                    "end": candidate["proposed_span"]["end"],
                    "instrument_ref": "PRIVATE INSTRUMENT REF CANARY",
                    "provision_ref": "PRIVATE PROVISION REF CANARY",
                    "provision_version_ref": "PRIVATE VERSION REF CANARY",
                    "valid_from": "2011-01-01",
                    "valid_until": "2012-01-01",
                    "text_role": "operative_text" if index == 1 else "transitional_text",
                },
                "last_event": {
                    "id": f"private-event-{index}",
                    "created_at": "2025-02-01T00:00:00Z",
                    "reviewer": reviewer,
                    "rationale": "PRIVATE MAPPING RATIONALE CANARY",
                },
            }
        )
        entities += [
            {
                "id": provision,
                "kind": "provision",
                "parent_id": instrument,
                "evidence_sha256": [identity_hash],
            },
            {
                "id": version,
                "kind": "provision_version",
                "parent_id": provision,
                "evidence_sha256": [identity_hash],
            },
        ]
        resolutions.append(
            {
                "mapping_id": mapping_id,
                "instrument_id": instrument,
                "provision_id": provision,
                "provision_version_id": version,
            }
        )
    state = {
        "source": package.detail,
        "revision": 4,
        "source_review_revision": 5,
        "source_review_ready": True,
        "handoff_ready": True,
        "publication_eligible": False,
        "items": mappings,
        "assigned_to": reviewer,
        "history": [],
        "history_truncated": False,
    }
    binding = {
        "schema_version": "legal-review-snapshot-v1",
        "source_id": package.detail["id"],
        "source_version_id": package.metadata.source_version_id,
        "source_artifacts": package.detail["artifacts"],
        "firm_id": "PRIVATE FIRM CANARY",
        "operator_id": "private-reviewer-id",
        "source_review_head_id": "review-head",
        "mapping_head_id": "mapping-head",
        "source_review_revision": 5,
        "mapping_revision": 4,
        "projections_sha256": sha(compiler.canonical([source_review, state])),
    }
    fixture = {
        "snapshot": {"package": package, "state": state, "source_review": source_review, "binding": binding},
        "registry": {"schema_version": "legal-identity-registry-v1", "entities": entities},
        "resolutions": {"schema_version": "provision-identity-resolutions-v1", "items": resolutions},
        "evidence": evidence,
        "ontology_root": ONTOLOGY,
        "source_parts": (public, incoming, args, metadata, locators),
    }
    refresh_fixture_binding(fixture)
    return fixture


def refresh_fixture_binding(preparation):
    """Build a coherent isolated snapshot fixture; never write an actual ledger."""
    snapshot = preparation["snapshot"]
    state, review, binding = (snapshot[key] for key in ("state", "source_review", "binding"))
    fields = {
        "candidate_id",
        "kind",
        "label",
        "span",
        "passage_ids",
        "non_whitespace_covered",
        "status",
        "resolution",
        "reviewed_source_revision",
    }
    for item in state["items"]:
        item["last_event"].update(
            mapping_id=item["id"],
            event_type="review",
            decision="accepted",
            source_review_revision=state["source_review_revision"],
            snapshot=copy.deepcopy({key: item[key] for key in fields}),
        )
    projection = {
        "source_binding": review["source_binding"],
        "context": {
            "firm_id": binding["firm_id"],
            "head_id": binding["mapping_head_id"],
            "revision": binding["mapping_revision"],
        },
        "mappings": {item["id"]: item["last_event"] for item in state["items"]},
    }
    binding["projections_sha256"] = sha(
        compiler.canonical({"source_review": review, "provision_mappings": projection})
    )


def compile_fixture(preparation):
    return compiler.compile_review(
        **{
            key: preparation[key]
            for key in ("snapshot", "registry", "resolutions", "evidence", "ontology_root")
        }
    )


def replace_source(preparation, *, acquired="2025-01-01T00:00:00Z", uncovered=False):
    public, incoming, args, metadata, locators = preparation["source_parts"]
    metadata = {**metadata, "acquired_at": acquired}
    locators = copy.deepcopy(locators)
    if uncovered:
        locators["passages"][0]["start"] = 1
        text = preparation["snapshot"]["package"].text
        passage = locators["passages"][0]
        passage["text_sha256"] = sha(text[passage["start"] : passage["end"]].encode())
    (incoming / "source.json").write_bytes(compiler.canonical(metadata))
    (incoming / "locators.json").write_bytes(compiler.canonical(locators))
    package = public.verified_package(public.import_package(**args)["id"])
    snapshot = preparation["snapshot"]
    snapshot["package"] = package
    snapshot["state"]["source"] = package.detail
    snapshot["source_review"]["source_binding"] = {
        "source_id": package.detail["id"],
        "artifacts": package.detail["artifacts"],
    }
    snapshot["binding"]["source_id"] = package.detail["id"]
    snapshot["binding"]["source_artifacts"] = package.detail["artifacts"]
    refresh_fixture_binding(preparation)


def test_compiler_is_deterministic_and_keeps_private_material_out_of_candidate_rdf(preparation):
    before = copy.deepcopy({key: value for key, value in preparation.items() if key != "source_parts"})
    files, summary = compile_fixture(preparation)
    assert compile_fixture(preparation) == (files, summary)
    assert {key: value for key, value in preparation.items() if key != "source_parts"} == before
    assert summary["rdf_generated"] is True and summary["assertion_count"] == 4
    assert summary["signed"] is False and summary["publication_eligible"] is False
    assert summary["confidentiality"] == "firm_confidential" and summary["blocker_codes"] == []
    assert files["binding.json"] == compiler.canonical(preparation["snapshot"]["binding"])
    assert files["registry.json"] == compiler.canonical(preparation["registry"])
    assert files["resolutions.json"] == compiler.canonical(preparation["resolutions"])
    for key, value in files.items():
        if key.startswith("candidate/"):
            assert (
                b"PRIVATE " not in value
                and b"private-reviewer-id" not in value
                and b"private-event" not in value
            )
            assert all(item["id"].encode() not in value for item in preparation["snapshot"]["state"]["items"])
    assert b"PRIVATE " not in compiler.canonical(summary)
    for key, raw in preparation["evidence"].items():
        assert files[f"private-evidence/{key}.bin"] == raw


def test_candidate_rdf_marks_preparation_and_has_only_unreviewed_grounded_assertions(preparation):
    files, _ = compile_fixture(preparation)
    data = Graph().parse(data=files["candidate/structure.ttl"], format="turtle")
    other = Graph().parse(data=files["candidate/jurisprudence.ttl"], format="turtle")
    assert len(list(data.triples((None, LA.reviewPreparationOnly, Literal(True))))) == 1
    assert len(list(other.triples((None, LA.reviewPreparationOnly, Literal(True))))) == 1
    assert set(data.objects(None, LA.claimStatus)) == {Literal("unreviewed")}
    assert set(data.objects(None, LA.predicate)) == {LA.containsProvision, LA.hasProvisionVersion}
    assert not list(data.triples((None, LA.reviewer, None)))
    assert not list(data.triples((None, LA.reviewedAt, None)))
    assert set(data.objects(None, LA.textRole)) == {Literal("operative_text"), Literal("transitional_text")}
    for node in data.subjects(RDF.type, LA.Assertion):
        assert list(data.objects(node, LA.evidence))
    # The existing publication gate must reject candidate graphs, even if signed.
    release = compiler._load_serving()._release
    with pytest.raises(ValueError, match="[Pp]reparation"):
        release.check_data({"structure": data, "jurisprudence": other}, ONTOLOGY, {"verified": True})


def test_exact_split_locator_conversion_preserves_unicode_and_whitespace_gaps(preparation):
    files, _ = compile_fixture(preparation)
    package = preparation["snapshot"]["package"]
    data = Graph().parse(data=files["candidate/structure.ttl"], format="turtle")
    converted = json.loads(files["candidate/locators.json"])
    assert files["candidate/raw.bin"] == package.raw
    assert files["candidate/text.txt"] == package.artifacts["text.txt"]
    assert converted["spans"] == [
        {"locator": p.locator, "start": p.start, "end": p.end} for p in package.locators.passages
    ]
    assert converted["artifact_sha256"] == package.locators.raw_sha256
    assert converted["text_sha256"] == package.locators.text_sha256
    quotes = []
    for node in data.subjects(RDF.type, LA.EvidencePassage):
        start, end = int(data.value(node, LA.startOffset)), int(data.value(node, LA.endOffset))
        quote = str(data.value(node, LA.quotedText))
        quotes.append(quote)
        assert quote == package.text[start:end]
        assert any(
            p.start <= start < end <= p.end and p.locator == str(data.value(node, LA.locator))
            for p in package.locators.passages
        )
    assert len(quotes) == 3
    assert any("I\u0307" in quote for quote in quotes)
    assert all("\r\n\r\n" not in quote for quote in quotes)


@pytest.mark.parametrize(
    "field,code", [("valid_from", "unknown_valid_from"), ("valid_until", "unknown_valid_until")]
)
def test_unknown_dates_remain_unknown_and_block_rdf(preparation, field, code):
    preparation["snapshot"]["state"]["items"][0]["resolution"][field] = None
    refresh_fixture_binding(preparation)
    files, summary = compile_fixture(preparation)
    report = json.loads(files["review-report.json"])
    assert summary["rdf_generated"] is False and code in summary["blocker_codes"]
    assert report["mapping_unknowns"][0][field] is None
    assert "candidate/structure.ttl" not in files and "candidate/jurisprudence.ttl" not in files
    assert summary["ontology_sha256"]


def test_unknown_acquisition_and_omitted_resolution_are_explicit_blockers(preparation):
    replace_source(preparation, acquired=None)
    preparation["resolutions"]["items"].pop()
    files, summary = compile_fixture(preparation)
    assert summary["blocker_codes"] == ["unknown_acquired_at", "unresolved_identity"]
    assert summary["resolved_count"] == 1
    assert json.loads(files["review-report.json"])["source_acquired_at"] is None
    assert "candidate/structure.ttl" not in files


@pytest.mark.parametrize("role", ["unknown", "amendment_text", "quoted_text"])
def test_unsupported_text_roles_never_become_operative_authority(preparation, role):
    preparation["snapshot"]["state"]["items"][0]["resolution"]["text_role"] = role
    refresh_fixture_binding(preparation)
    files, summary = compile_fixture(preparation)
    assert summary["blocker_codes"] == ["unsupported_text_role"]
    assert not summary["rdf_generated"]
    assert json.loads(files["review-report.json"])["mapping_unknowns"][0]["text_role"] == role


@pytest.mark.parametrize(
    "change",
    [
        "extra_field",
        "duplicate",
        "wrong_namespace",
        "wrong_kind",
        "wrong_parent",
        "instrument_parent",
        "missing_proof",
        "duplicate_proof",
        "empty_proof",
        "extra_entity_field",
    ],
)
def test_strict_registry_and_parent_contract(preparation, change):
    registry = preparation["registry"]
    if change == "extra_field":
        registry["private_note"] = "forbidden"
    if change == "duplicate":
        registry["entities"].append(copy.deepcopy(registry["entities"][0]))
    if change == "wrong_namespace":
        registry["entities"][0]["id"] = "https://external.example/identity"
    if change == "wrong_kind":
        registry["entities"][0]["kind"] = "provision"
    if change == "wrong_parent":
        registry["entities"][2]["parent_id"] = registry["entities"][0]["id"]
    if change == "instrument_parent":
        registry["entities"][0]["parent_id"] = registry["entities"][0]["id"]
    if change == "missing_proof":
        registry["entities"][0]["evidence_sha256"] = ["f" * 64]
    if change == "duplicate_proof":
        registry["entities"][0]["evidence_sha256"] *= 2
    if change == "empty_proof":
        registry["entities"][0]["evidence_sha256"] = []
    if change == "extra_entity_field":
        registry["entities"][0]["label"] = "private label"
    with pytest.raises(compiler.PreparationError):
        compile_fixture(preparation)


@pytest.mark.parametrize(
    "change", ["extra_field", "duplicate", "unknown_mapping", "missing_entity", "wrong_chain", "wrong_type"]
)
def test_resolution_schema_and_identity_chain_must_be_explicit(preparation, change):
    plan = preparation["resolutions"]
    if change == "extra_field":
        plan["guess_from_label"] = True
    if change == "duplicate":
        plan["items"].append(copy.deepcopy(plan["items"][0]))
    if change == "unknown_mapping":
        plan["items"][0]["mapping_id"] = "f" * 32
    if change == "missing_entity":
        plan["items"][0]["instrument_id"] = "urn:tr-law:instrument:missing"
    if change == "wrong_chain":
        plan["items"][0]["provision_id"] = plan["items"][1]["provision_id"]
    if change == "wrong_type":
        plan["items"][0]["provision_id"] = plan["items"][0]["instrument_id"]
    with pytest.raises(compiler.PreparationError):
        compile_fixture(preparation)


@pytest.mark.parametrize(
    "change", ["missing", "changed", "unused", "empty", "not_bytes", "oversize", "over_count", "over_total"]
)
def test_physical_evidence_must_be_exact_required_and_bounded(preparation, change, monkeypatch):
    evidence = preparation["evidence"]
    first = next(iter(evidence))
    if change == "missing":
        evidence.pop(first)
    if change == "changed":
        evidence[first] = b"tampered"
    if change == "unused":
        evidence[sha(b"unused")] = b"unused"
    if change == "empty":
        evidence[first] = b""
    if change == "not_bytes":
        evidence[first] = evidence[first].decode()
    if change == "oversize":
        monkeypatch.setattr(compiler, "MAX_EVIDENCE_FILE_BYTES", 1)
    if change == "over_count":
        monkeypatch.setattr(compiler, "MAX_EVIDENCE_FILES", 1)
    if change == "over_total":
        monkeypatch.setattr(compiler, "MAX_EVIDENCE_TOTAL_BYTES", 1)
    with pytest.raises(compiler.PreparationError):
        compile_fixture(preparation)


@pytest.mark.parametrize(
    "change",
    [
        "rights",
        "unaccepted_source",
        "stale",
        "unaccepted_mapping",
        "wrong_revision",
        "tampered_quote",
        "wrong_locator",
        "uncovered",
        "duplicate_mapping",
        "empty",
        "same_dates",
        "reverse_dates",
    ],
)
def test_invalid_snapshots_cannot_compile(preparation, change):
    snapshot = preparation["snapshot"]
    item = snapshot["state"]["items"][0]
    if change == "rights":
        snapshot["source_review"]["assessments"]["rights"]["permitted_uses"].remove("local_inference")
    if change == "unaccepted_source":
        snapshot["source_review"]["assessments"]["legal"]["decision"] = "rejected"
    if change == "stale":
        item["stale"] = True
    if change == "unaccepted_mapping":
        item["status"] = "machine_proposed"
    if change == "wrong_revision":
        item["reviewed_source_revision"] = 4
    if change == "tampered_quote":
        item["span"]["text"] = "invented"
    if change == "wrong_locator":
        item["passage_ids"] = ["wrong"]
    if change == "uncovered":
        replace_source(preparation, uncovered=True)
    if change == "duplicate_mapping":
        snapshot["state"]["items"].append(copy.deepcopy(item))
    if change == "empty":
        snapshot["state"]["items"].clear()
    if change == "same_dates":
        item["resolution"]["valid_until"] = item["resolution"]["valid_from"]
    if change == "reverse_dates":
        item["resolution"]["valid_until"] = "2010-01-01"
    with pytest.raises(compiler.PreparationError):
        compile_fixture(preparation)


def test_distinct_spans_cannot_collapse_to_one_version(preparation):
    plan = preparation["resolutions"]["items"]
    plan[1].update({key: plan[0][key] for key in ("instrument_id", "provision_id", "provision_version_id")})
    with pytest.raises(compiler.PreparationError, match="Distinct provision spans"):
        compile_fixture(preparation)


def test_different_versions_of_same_provision_cannot_claim_overlapping_validity(preparation):
    plan = preparation["resolutions"]["items"]
    plan[1]["provision_id"] = plan[0]["provision_id"]
    preparation["registry"]["entities"][4]["parent_id"] = plan[0]["provision_id"]
    with pytest.raises(compiler.PreparationError, match="intervals conflict"):
        compile_fixture(preparation)


def test_changed_identity_proof_or_plan_changes_private_digests_without_leaking_proof(preparation):
    files, summary = compile_fixture(preparation)
    old = preparation["registry"]["entities"][0]["evidence_sha256"][0]
    new = b"PRIVATE REPLACED IDENTITY PROOF CANARY"
    preparation["evidence"].pop(old)
    preparation["evidence"][sha(new)] = new
    for entity in preparation["registry"]["entities"]:
        entity["evidence_sha256"] = [sha(new)]
    changed, new_summary = compile_fixture(preparation)
    assert changed["registry.json"] != files["registry.json"]
    assert new_summary["report_sha256"] != summary["report_sha256"]
    assert changed["candidate/structure.ttl"] == files["candidate/structure.ttl"]
    assert new not in changed["candidate/structure.ttl"]


def test_exact_partial_span_clips_original_passage_without_inventing_locator(preparation):
    item = preparation["snapshot"]["state"]["items"][0]
    package = preparation["snapshot"]["package"]
    end = package.text.index(" satır")
    item["resolution"]["end"] = end
    details = span_details(package, item["span"]["start"], end)
    item.update({key: details[key] for key in ("span", "passage_ids", "non_whitespace_covered")})
    refresh_fixture_binding(preparation)
    files, _ = compile_fixture(preparation)
    data = Graph().parse(data=files["candidate/structure.ttl"], format="turtle")
    assert Literal("İkinci") in set(data.objects(None, LA.quotedText))
    assert URIRef(preparation["resolutions"]["items"][0]["provision_version_id"]) in set(
        data.subjects(RDF.type, LA.ProvisionVersion)
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema_version", "unknown"),
        ("source_id", "f" * 64),
        ("source_version_id", "another-version"),
        ("source_artifacts", {}),
        ("firm_id", "other-firm"),
        ("operator_id", "other-operator"),
        ("source_review_head_id", "other-head"),
        ("mapping_head_id", "other-head"),
        ("source_review_revision", 4),
        ("mapping_revision", 3),
        ("projections_sha256", "f" * 64),
        ("mapping_revision", True),
        ("private_extra", "forbidden"),
    ],
)
def test_broken_live_binding_never_produces_a_review_packet(preparation, key, value):
    preparation["snapshot"]["binding"][key] = value
    with pytest.raises(compiler.PreparationError):
        compile_fixture(preparation)


def test_current_mapping_cannot_differ_from_immutable_event_snapshot(preparation):
    preparation["snapshot"]["state"]["items"][0]["resolution"]["valid_until"] = "2013-01-01"
    with pytest.raises(compiler.PreparationError):
        compile_fixture(preparation)


def test_evidence_link_expansion_fails_before_rdf_allocation_without_truncation(preparation, monkeypatch):
    # Three real locator spans, two assertions each. Blank line gaps do not count.
    monkeypatch.setattr(compiler, "MAX_ASSERTION_EVIDENCE_LINKS", 6)
    files, summary = compile_fixture(preparation)
    assert summary["assertion_count"] == 4
    assert b"GE" in files["candidate/structure.ttl"]
    monkeypatch.setattr(compiler, "MAX_ASSERTION_EVIDENCE_LINKS", 5)
    monkeypatch.setattr(compiler, "Graph", lambda: pytest.fail("RDF allocated before the capacity gate"))
    with pytest.raises(compiler.PreparationError, match="evidence links exceed"):
        compile_fixture(preparation)
