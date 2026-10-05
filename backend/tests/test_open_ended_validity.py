"""Synthetic temporal-review fixtures only; no legal review or live data writes."""

import copy
import json

import pytest
from pydantic import ValidationError
from rdflib import RDF, XSD, Graph, Literal, URIRef
from sqlalchemy import select, update
from test_provision_mappings import TEXT, counts, propose, ready, review
from test_provision_mappings import mapping as mapping_fixture
from test_provision_mappings import source as source_fixture
from test_provision_mappings import workspace as workspace_fixture
from test_release_preparation import compile_fixture, refresh_fixture_binding, replace_source, sha
from test_release_preparation import preparation as preparation_fixture
from test_source_reviews import assess

from app import provision_mappings
from app import release_preparation as compiler
from app.provision_mapping_models import ProvisionMappingEvent, ProvisionMappingHead
from app.provision_mappings import Resolution
from app.release_promotion import promoted_graphs

mapping = mapping_fixture
source = source_fixture
workspace = workspace_fixture
preparation = preparation_fixture
LA = compiler.LA


def open_resolution(mapping):
    candidate = mapping[1].get(mapping[4] + "/provision-candidates").json()["items"][0]
    return {
        "start": candidate["proposed_span"]["start"], "end": candidate["proposed_span"]["end"],
        "instrument_ref": "Engineering test instrument", "provision_ref": "Engineering test provision",
        "provision_version_ref": "Engineering test version", "text_role": "operative_text",
        "valid_from": "2011-01-01", "valid_until": None,
        "open_ended_validity": {"checked_through": "2024-12-31", "evidence_start": 0, "evidence_end": 18},
    }


def open_preparation(preparation, *, support_index=1, checked="2025-02-01"):
    item = preparation["snapshot"]["state"]["items"][0]
    support = preparation["snapshot"]["package"].locators.passages[support_index]
    item["resolution"]["valid_until"] = None
    item["resolution"]["open_ended_validity"] = {
        "checked_through": checked, "evidence_start": support.start, "evidence_end": support.end,
    }
    refresh_fixture_binding(preparation)
    return item


def test_explicit_open_review_preserves_unknown_end_and_separate_exact_support(mapping):
    app, client, sources, source_id, base = mapping
    ready(mapping)
    item = propose(mapping, source_revision=5).json()["items"][0]
    resolution = open_resolution(mapping)
    assert resolution["open_ended_validity"]["evidence_end"] < item["span"]["start"]
    result = review(mapping, item["id"], resolution=resolution)
    assert result.status_code == 200, result.text
    saved = result.json()["items"][0]
    assert saved["resolution"] == resolution and saved["resolution"]["valid_until"] is None
    assert result.json()["handoff_ready"] and not result.json()["publication_eligible"]
    assert client.get(base + "/provision-mappings").json() == result.json()
    dossier = client.get(base + "/provision-mappings/export").json()
    assert dossier["mappings"] == result.json() and dossier["signed"] is False
    assert sources.detail(source_id)["publication_status"] == "staged"
    assert counts(app) == (1, 2)
    assert assess(client, base + "/review", 5, "legal").status_code == 200
    stale = client.get(base + "/provision-mappings").json()
    assert stale["items"][0]["stale"] and not stale["handoff_ready"]
    assert stale["items"][0]["resolution"] == resolution
    assert review(mapping, item["id"], revision=2, resolution=resolution).status_code == 409


@pytest.mark.parametrize("changes", [
    {"valid_from": None}, {"valid_until": "2025-01-01"}, {"open_ended_validity": None},
    {"open_ended_validity": {}},
    {"open_ended_validity": {"checked_through": "2010-12-31", "evidence_start": 0, "evidence_end": 18}},
    {"open_ended_validity": {"checked_through": "2099-01-01", "evidence_start": 0, "evidence_end": 18}},
    {"open_ended_validity": {"checked_through": "20250101", "evidence_start": 0, "evidence_end": 18}},
    {"open_ended_validity": {"checked_through": "2025-02-30", "evidence_start": 0, "evidence_end": 18}},
    {"open_ended_validity": {"checked_through": "2025-01-01", "evidence_start": True, "evidence_end": 18}},
    {"open_ended_validity": {"checked_through": "2025-01-01", "evidence_start": 18, "evidence_end": 18}},
    {"open_ended_validity": {"checked_through": "2025-01-01", "evidence_start": 0, "evidence_end": len(TEXT) + 1}},
    {"open_ended_validity": {"checked_through": "2025-01-01", "evidence_start": len(TEXT) - 2, "evidence_end": len(TEXT)}},
    {"open_ended_validity": {"checked_through": "2025-01-01", "evidence_start": 0, "evidence_end": 20001}},
    {"open_ended_validity": {"checked_through": "2025-01-01", "evidence_start": 0, "evidence_end": 18, "automatic": True}},
])
def test_api_rejects_unknown_inconsistent_or_ungrounded_open_review(mapping, changes):
    ready(mapping)
    identifier = propose(mapping, source_revision=5).json()["items"][0]["id"]
    assert review(mapping, identifier, resolution={**open_resolution(mapping), **changes}).status_code == 422
    assert counts(mapping[0]) == (1, 1)


@pytest.mark.parametrize("checked,status", [("2024-12-31", 200), ("2025-01-01", 422)])
def test_api_bounds_horizon_by_immutable_event_utc_day(mapping, monkeypatch, checked, status):
    ready(mapping)
    identifier = propose(mapping, source_revision=5).json()["items"][0]["id"]
    monkeypatch.setattr(provision_mappings, "now", lambda: "2025-01-01T00:30:00+02:00")
    resolution = open_resolution(mapping)
    resolution["open_ended_validity"]["checked_through"] = checked
    assert review(mapping, identifier, resolution=resolution).status_code == status
    assert counts(mapping[0]) == (1, 2 if status == 200 else 1)
    if status == 200:
        assert mapping[1].get(mapping[4] + "/provision-mappings").status_code == 200


def test_support_gap_outside_fully_covered_provision_blocks_acceptance(mapping):
    app, client, sources, source_id, _ = mapping
    package = sources.verified_package(source_id)
    locators = package.locators.model_dump()
    # A gap in the introductory support passage leaves the provision body intact.
    gap = 2
    locators["passages"] = [
        {"id": "p1", "start": 0, "end": gap, "text_sha256": sha(TEXT[:gap].encode()), "locator": "Test 1"},
        {"id": "p2", "start": gap + 1, "end": len(TEXT), "text_sha256": sha(TEXT[gap + 1:].encode()), "locator": "Test 2"},
    ]
    locator_path = app.state.settings.data_dir / "gapped-support.json"
    locator_path.write_text(json.dumps(locators), encoding="utf-8")
    original = sources.root / source_id
    source_id = sources.import_package(metadata_path=original / "source.json", raw_path=original / "raw.bin",
                                        text_path=original / "text.txt", locators_path=locator_path)["id"]
    own = (app, client, sources, source_id, f"/api/v1/public-sources/{source_id}")
    ready(own)
    proposed = propose(own, source_revision=5).json()["items"][0]
    assert proposed["non_whitespace_covered"] is True
    assert review(own, proposed["id"], resolution=open_resolution(own)).status_code == 422
    assert counts(app) == (1, 1)


def test_missing_optional_field_preserves_legacy_event_and_null_date_bytes(mapping):
    ready(mapping)
    identifier = propose(mapping, source_revision=5).json()["items"][0]["id"]
    saved = review(mapping, identifier).json()["items"][0]
    old = saved["resolution"]
    assert "open_ended_validity" not in old and old["valid_from"] is None and old["valid_until"] is None
    assert compiler.canonical(Resolution.model_validate(old).model_dump()) == compiler.canonical(old)
    assert saved == mapping[1].get(mapping[4] + "/provision-mappings").json()["items"][0]
    with pytest.raises(ValidationError):
        Resolution.model_validate({**old, "open_ended_validity": None})


def test_replay_rejects_horizon_after_immutable_event_even_if_current_clock_later(mapping):
    app, client, _, _, base = mapping
    ready(mapping)
    identifier = propose(mapping, source_revision=5).json()["items"][0]["id"]
    assert review(mapping, identifier, resolution=open_resolution(mapping)).status_code == 200
    with app.state.store.session() as session:
        head = session.scalar(select(ProvisionMappingHead))
        row = session.scalar(select(ProvisionMappingEvent).where(ProvisionMappingEvent.revision == 2))
        projection, payload = app.state.store.decode(head), app.state.store.decode(row)
        event = payload["event"]
        event["created_at"] = "2024-12-30T23:59:59Z"
        projection["mappings"][identifier] = event
        head.payload = app.state.store.encode(projection)
        session.execute(update(ProvisionMappingEvent).where(ProvisionMappingEvent.id == row.id).values(
            created_at=event["created_at"], payload=app.state.store.encode(payload)))
        session.commit()
    for path in ("/provision-mappings", "/provision-mappings/export"):
        assert client.get(base + path).status_code == 409


def test_compiler_emits_explicit_matching_temporal_state_with_independent_public_proof(preparation):
    item = open_preparation(preparation, support_index=2)
    package = preparation["snapshot"]["package"]
    support = item["resolution"]["open_ended_validity"]
    assert support["evidence_start"] >= item["span"]["end"]
    files, summary = compile_fixture(preparation)
    assert summary["rdf_generated"] and not summary["blocker_codes"]
    graph = Graph().parse(data=files["candidate/structure.ttl"], format="turtle")
    version = URIRef(preparation["resolutions"]["items"][0]["provision_version_id"])
    version_proof = set(graph.objects(version, LA.validityEvidence))
    assert version_proof and graph.value(version, LA.validTo) is None
    nodes = [version, *graph.subjects(LA.validityEndStatus, Literal("open_ended"))]
    for node in nodes:
        assert graph.value(node, LA.validityCheckedThrough) == Literal("2025-02-01", datatype=XSD.date)
        assert set(graph.objects(node, LA.validityEvidence)) == version_proof
        assert graph.value(node, LA.validTo) is None
        for passage in version_proof:
            start, end = int(graph.value(passage, LA.startOffset)), int(graph.value(passage, LA.endOffset))
            assert (start, end) == (support["evidence_start"], support["evidence_end"])
            assert str(graph.value(passage, LA.quotedText)) == package.text[start:end]
    assert len(set(nodes)) == 3  # Two structural assertions and their version.
    assert set(graph.objects(None, LA.claimStatus)) == {Literal("unreviewed")}
    assert not any(b"PRIVATE " in value for name, value in files.items() if name.startswith("candidate/"))
    assert json.loads(files["review-report.json"])["mapping_unknowns"][0]["open_ended_validity"] == support
    assert compile_fixture(preparation) == (files, summary)


@pytest.mark.parametrize("change", ["closed_and_open", "unknown_start", "before_start", "future_event",
                                    "gap", "empty", "out_of_bounds", "explicit_null"])
def test_compiler_rechecks_temporal_review_not_only_api_shape(preparation, change):
    item = open_preparation(preparation)
    support = item["resolution"]["open_ended_validity"]
    if change == "closed_and_open":
        item["resolution"]["valid_until"] = "2025-03-01"
    elif change == "unknown_start":
        item["resolution"]["valid_from"] = None
    elif change == "before_start":
        support["checked_through"] = "2010-12-31"
    elif change == "future_event":
        item["last_event"]["created_at"] = "2025-02-01T00:30:00+02:00"
    elif change == "gap":
        first = preparation["snapshot"]["package"].locators.passages[0]
        support.update(evidence_start=first.start, evidence_end=first.end)
        # Body moved to fully covered second article; only the support crosses a gap.
        second = preparation["snapshot"]["state"]["items"][1]
        item.update({key: copy.deepcopy(second[key]) for key in ("span", "passage_ids", "non_whitespace_covered")})
        item["resolution"].update(start=second["span"]["start"], end=second["span"]["end"])
        replace_source(preparation, uncovered=True)
    elif change == "empty":
        text = preparation["snapshot"]["package"].text
        start = text.index("\r\n\r\n")
        support.update(evidence_start=start, evidence_end=start + 4)
    elif change == "out_of_bounds":
        support["evidence_end"] = 20001
    elif change == "explicit_null":
        item["resolution"]["open_ended_validity"] = None
    refresh_fixture_binding(preparation)
    with pytest.raises(compiler.PreparationError):
        compile_fixture(preparation)


def test_unknown_end_still_blocks_and_finite_ids_keep_legacy_fingerprint(preparation):
    files, _ = compile_fixture(preparation)
    graph = Graph().parse(data=files["candidate/structure.ttl"], format="turtle")
    assert not list(graph.triples((None, LA.validityEndStatus, None)))
    assert not list(graph.triples((None, LA.validityCheckedThrough, None)))
    assert not list(graph.triples((None, LA.validityEvidence, None)))
    item, identity = preparation["snapshot"]["state"]["items"][0], preparation["resolutions"]["items"][0]
    resolution = item["resolution"]
    legacy_key = [preparation["snapshot"]["package"].detail["id"], identity["provision_id"],
                  str(LA.hasProvisionVersion), identity["provision_version_id"],
                  item["span"]["start"], item["span"]["end"], resolution["valid_from"],
                  resolution["valid_until"], resolution["text_role"]]
    expected = URIRef("urn:la:assertion-proposal:" + sha(compiler.canonical(legacy_key)))
    assert (expected, RDF.type, LA.Assertion) in graph
    resolution["valid_until"] = None
    refresh_fixture_binding(preparation)
    files, summary = compile_fixture(preparation)
    assert summary["blocker_codes"] == ["unknown_valid_until"] and not summary["rdf_generated"]
    assert "candidate/structure.ttl" not in files


@pytest.mark.parametrize("change", ["horizon", "support"])
def test_open_state_and_proof_bind_assertion_identity_and_snapshot(preparation, change):
    item = open_preparation(preparation)
    files, before = compile_fixture(preparation)
    old = Graph().parse(data=files["candidate/structure.ttl"], format="turtle")
    if change == "horizon":
        item["resolution"]["open_ended_validity"]["checked_through"] = "2025-01-31"
    else:
        support = preparation["snapshot"]["package"].locators.passages[2]
        item["resolution"]["open_ended_validity"].update(evidence_start=support.start, evidence_end=support.end)
    with pytest.raises(compiler.PreparationError):
        compile_fixture(preparation)  # Cannot drift from the immutable event.
    refresh_fixture_binding(preparation)
    changed, after = compile_fixture(preparation)
    new = Graph().parse(data=changed["candidate/structure.ttl"], format="turtle")
    old_open = set(old.subjects(LA.validityEndStatus, Literal("open_ended")))
    new_open = set(new.subjects(LA.validityEndStatus, Literal("open_ended")))
    assert len(old_open ^ new_open) == 4  # Version ID stable; both assertion IDs change.
    assert before["binding_sha256"] != after["binding_sha256"] and before["report_sha256"] != after["report_sha256"]


@pytest.mark.parametrize("change", ["horizon", "support"])
def test_same_version_cannot_hide_different_open_semantics(preparation, change):
    first = open_preparation(preparation)
    second = preparation["snapshot"]["state"]["items"][1]
    for key in ("kind", "span", "passage_ids", "non_whitespace_covered", "resolution"):
        second[key] = copy.deepcopy(first[key])
    plans = preparation["resolutions"]["items"]
    plans[1].update({key: plans[0][key] for key in ("instrument_id", "provision_id", "provision_version_id")})
    support = second["resolution"]["open_ended_validity"]
    if change == "horizon":
        support["checked_through"] = "2025-01-31"
    else:
        support["evidence_start"] += 1
    refresh_fixture_binding(preparation)
    with pytest.raises(compiler.PreparationError, match="Distinct provision spans"):
        compile_fixture(preparation)


@pytest.mark.parametrize("reverse", [False, True])
def test_open_interval_conflicts_after_checked_through_even_in_reverse_order(preparation, reverse):
    item = open_preparation(preparation, checked="2011-06-01")
    second = preparation["snapshot"]["state"]["items"][1]
    second["resolution"].update(valid_from="2020-01-01", valid_until="2021-01-01")
    plans = preparation["resolutions"]["items"]
    plans[1]["provision_id"] = plans[0]["provision_id"]
    preparation["registry"]["entities"][4]["parent_id"] = plans[0]["provision_id"]
    if reverse:
        item["resolution"], second["resolution"] = second["resolution"], item["resolution"]
        for current in (item, second):
            current["resolution"].update(start=current["span"]["start"], end=current["span"]["end"])
    refresh_fixture_binding(preparation)
    with pytest.raises(compiler.PreparationError, match="intervals conflict"):
        compile_fixture(preparation)


def test_closed_version_can_touch_open_start_without_overlapping(preparation):
    item = open_preparation(preparation)
    item["resolution"]["valid_from"] = "2012-01-01"
    plans = preparation["resolutions"]["items"]
    plans[1]["provision_id"] = plans[0]["provision_id"]
    preparation["registry"]["entities"][4]["parent_id"] = plans[0]["provision_id"]
    refresh_fixture_binding(preparation)
    assert compile_fixture(preparation)[1]["rdf_generated"]


def test_temporal_evidence_counts_before_rdf_allocation(preparation, monkeypatch):
    open_preparation(preparation)
    # Three body passage links to two assertions, one temporal passage to three owners.
    monkeypatch.setattr(compiler, "MAX_ASSERTION_EVIDENCE_LINKS", 9)
    assert compile_fixture(preparation)[1]["rdf_generated"]
    monkeypatch.setattr(compiler, "MAX_ASSERTION_EVIDENCE_LINKS", 8)
    monkeypatch.setattr(compiler, "Graph", lambda: pytest.fail("RDF allocated before temporal evidence limit"))
    with pytest.raises(compiler.PreparationError, match="evidence links exceed"):
        compile_fixture(preparation)


def test_public_promotion_preserves_horizon_and_support_without_inventing_end(preparation):
    open_preparation(preparation)
    files, _ = compile_fixture(preparation)
    result = promoted_graphs(files, "Explicit public engineering reviewer", "2025-02-01T00:00:00Z")
    before = Graph().parse(data=files["candidate/structure.ttl"], format="turtle")
    after = Graph().parse(data=result["structure"], format="turtle")
    for predicate in (LA.validityEndStatus, LA.validityCheckedThrough, LA.validityEvidence, LA.validFrom, LA.validTo):
        assert set(before.triples((None, predicate, None))) == set(after.triples((None, predicate, None)))
    assert set(after.objects(None, LA.claimStatus)) == {Literal("legally_reviewed")}


def test_public_promotion_checks_utc_horizon_even_if_private_timestamp_was_altered(preparation):
    open_preparation(preparation)
    files, _ = compile_fixture(preparation)
    graph = Graph().parse(data=files["candidate/structure.ttl"], format="turtle")
    # Pure promotion must not silently accept a forged old event timestamp that
    # would otherwise let a review precede its horizon. Publication still has its own seal checks.
    for node in graph.subjects(RDF.type, LA.Assertion):
        graph.set((node, LA.recordedAt, Literal("2025-01-01T00:00:00Z", datatype=XSD.dateTime)))
    files["candidate/structure.ttl"] = graph.serialize(format="nt").encode()
    with pytest.raises(ValueError, match="checking date"):
        promoted_graphs(files, "Explicit public engineering reviewer", "2025-02-01T00:30:00+02:00")
