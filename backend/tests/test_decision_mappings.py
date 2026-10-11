"""Synthetic decision review accountability, not legal qualification."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select
from test_jurisprudence_candidates import incoming as incoming_fixture
from test_public_sources import source as source_fixture
from test_source_reviews import another_client, assess, assign
from test_workspace import workspace as workspace_fixture

from app import decision_mappings
from app.decision_mapping_models import DecisionMappingEvent, DecisionMappingHead

incoming = incoming_fixture
source = source_fixture
workspace = workspace_fixture


@pytest.fixture
def mapping(workspace, incoming):
    app, client, _ = workspace
    store, make = incoming
    source_id, package = make("Başvuru Numarası: 2020/5\nKarar Tarihi: 12/1/2021\n4857 sayılı Kanun.\n")
    app.state.settings.public_source_dir = store.root
    base = f"/api/v1/public-sources/{source_id}"
    candidates = json.loads(client.get(base + "/jurisprudence-candidates?passage_id=p2").json()["evidence_json"])["items"]
    return app, client, store, source_id, base, candidates, package


def ready(mapping):
    client, base = mapping[1], mapping[4]
    assert assign(client, base + "/review").status_code == 200
    for revision, category in enumerate(("rights", "source_identity", "extraction", "legal"), 1):
        options = {"permitted_uses": ["local_processing", "internal_display"]} if category == "rights" else {}
        if category == "extraction":
            options["passage_ids"] = ["p1", "p2"]
        assert assess(client, base + "/review", revision, category, **options).status_code == 200


def propose(mapping, revision=0, source_revision=5, index=0, **changes):
    return mapping[1].post(mapping[4] + "/decision-mappings", json={
        "expected_revision": revision, "expected_source_review_revision": source_revision,
        "passage_id": "p2", "candidate_id": mapping[5][index]["id"],
        "rationale": "Synthetic proposed occurrence", **changes})


def resolution(mapping, **changes):
    c = mapping[5][0]
    return {"start": c["start"], "end": c["end"], "occurrence_role": "own_decision",
            "proceeding_ref": "synthetic-proceeding", "decision_ref": "synthetic-decision",
            "institution_ref": "synthetic-institution", "target_ref": None, "target_version_ref": None,
            "event_role": "unknown", "event_date": None, "authority_treatment": "unknown", **changes}


def review(mapping, identifier, revision=1, source_revision=5, **changes):
    return mapping[1].post(mapping[4] + f"/decision-mappings/{identifier}/review", json={
        "expected_revision": revision, "expected_source_review_revision": source_revision,
        "decision": "accepted", "resolution": resolution(mapping), "rationale": "Synthetic review evidence",
        "evidence_refs": [{"reference": "Synthetic support", "sha256": "a" * 64}], **changes})


def test_accountable_encrypted_history_never_changes_public_source(mapping):
    app, client, store, identifier, base, _, _ = mapping
    original = {p.name: p.read_bytes() for p in (store.root / identifier).iterdir()}
    assert client.get(base + "/decision-mappings").json()["revision"] == 0
    ready(mapping)
    item = propose(mapping).json()["items"][0]
    response = review(mapping, item["id"])
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["handoff_ready"] and not state["publication_eligible"]
    assert state["items"][0]["resolution"]["event_date"] is None
    assert state["history"][0]["reviewer"]["id"] == state["assigned_to"]["id"]
    assert client.get(base + "/decision-mappings").json() == state
    with app.state.store.session() as session:
        for row in [session.scalar(select(DecisionMappingHead)), *session.scalars(select(DecisionMappingEvent))]:
            assert "synthetic-decision" not in row.payload
            assert app.state.store.decode(row)["source_binding"]["source_id"] == identifier
    assert original == {p.name: p.read_bytes() for p in (store.root / identifier).iterdir()}


def test_owner_both_revisions_and_source_readiness(mapping):
    assert propose(mapping, source_revision=0).status_code == 409
    assert assign(mapping[1], mapping[4] + "/review").status_code == 200
    assert propose(mapping, source_revision=0).status_code == 409
    other = another_client(mapping[0])
    assert propose((mapping[0], other, *mapping[2:]), source_revision=1).status_code == 409
    item = propose(mapping, source_revision=1).json()["items"][0]
    assert review(mapping, item["id"], source_revision=1).status_code == 409
    assert review(mapping, item["id"], revision=0, source_revision=1).status_code == 409


def test_rejection_disagreement_and_stale_reaffirmation_preserved(mapping):
    ready(mapping)
    item = propose(mapping).json()["items"][0]
    assert review(mapping, item["id"]).status_code == 200
    assert assess(mapping[1], mapping[4] + "/review", 5, "legal").status_code == 200
    state = mapping[1].get(mapping[4] + "/decision-mappings").json()
    assert state["items"][0]["stale"] and not state["handoff_ready"]
    assert review(mapping, item["id"], 2, 5).status_code == 409
    rejected = review(mapping, item["id"], 2, 6, decision="needs_changes", resolution=None, evidence_refs=[])
    assert rejected.status_code == 200
    assert rejected.json()["items"][0]["resolution"] is None
    assert rejected.json()["history"][1]["snapshot"]["resolution"]["decision_ref"] == "synthetic-decision"


@pytest.mark.parametrize("changes", [
    {"candidate_id": "b" * 64}, {"passage_id": "p1"}, {"start": 0}, {"passage_id": "../p2"},
])
def test_candidate_binding_and_closed_inputs(mapping, changes):
    ready(mapping)
    assert propose(mapping, **changes).status_code in {422, 409}


@pytest.mark.parametrize("changes", [
    {"decision_ref": None}, {"institution_ref": None}, {"proceeding_ref": None},
    {"event_role": "publication", "event_date": "2021-01-12"},
    {"event_role": "decision", "event_date": "2021-01-12"},
    {"authority_treatment": "applies"}, {"start": 0, "end": 1},
    {"event_date": "2021-02-30"}, {"legal_effect": "binding"},
])
def test_invalid_or_unevidenced_resolutions_withheld(mapping, changes):
    ready(mapping)
    item = propose(mapping).json()["items"][0]
    assert review(mapping, item["id"], resolution=resolution(mapping, **changes)).status_code == 422
    assert mapping[1].get(mapping[4] + "/decision-mappings").json()["revision"] == 1


def test_date_roles_are_literal_unknown_finality_not_promoted(mapping):
    ready(mapping)
    item = propose(mapping, index=1).json()["items"][0]
    c = mapping[5][1]
    value = resolution(mapping, start=c["start"], end=c["end"], event_role="decision", event_date="2021-01-12")
    assert review(mapping, item["id"], resolution={**value, "event_date": "2021-01-13"}).status_code == 422
    result = review(mapping, item["id"], resolution=value)
    assert result.status_code == 200, result.text
    assert mapping[6].metadata.published_on is None
    assert "finality" not in result.json()["items"][0]["resolution"]


def test_duplicate_proposals_and_two_competing_writes(mapping):
    ready(mapping)
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda _: propose(mapping), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert propose(mapping, revision=1).status_code == 409


def test_cross_firm_and_noncurator_no_disclosure(mapping):
    ready(mapping)
    propose(mapping)
    other = another_client(mapping[0], firm="other-firm")
    assert other.get(mapping[4] + "/decision-mappings").json()["items"] == []
    assert propose((mapping[0], other, *mapping[2:]), source_revision=0).status_code == 409
    lawyer = another_client(mapping[0], username="lawyer", role="lawyer")
    assert lawyer.get(mapping[4] + "/decision-mappings").status_code == 403


def test_corrupted_or_old_projection_fails_closed(mapping):
    ready(mapping)
    item = propose(mapping).json()["items"][0]
    review(mapping, item["id"])
    with mapping[0].state.store.session() as session:
        head = session.scalar(select(DecisionMappingHead))
        data = mapping[0].state.store.decode(head)
        data["mappings"][item["id"]]["snapshot"]["resolution"]["decision_ref"] = "forged-decision"
        head.payload = mapping[0].state.store.encode(data)
        session.commit()
    assert mapping[1].get(mapping[4] + "/decision-mappings").status_code == 409


def test_csrf_required(mapping):
    ready(mapping)
    mapping[1].headers.pop("X-CSRF-Token")
    assert propose(mapping).status_code == 403


def test_concurrent_identity_change_rolls_back(mapping, monkeypatch):
    ready(mapping)
    original = decision_mappings.reviews._lock_identity
    calls = 0
    def change(session, request, user):
        nonlocal calls
        current = original(session, request, user)
        calls += 1
        if calls == 2:
            current.role = "lawyer"
        return current
    monkeypatch.setattr(decision_mappings.reviews, "_lock_identity", change)
    assert propose(mapping).status_code == 403
    assert mapping[1].get(mapping[4] + "/decision-mappings").json()["items"] == []


def test_acceptance_requires_exact_support_passages_in_extraction_review(mapping):
    ready(mapping)
    assert assess(mapping[1], mapping[4] + "/review", 5, "extraction", passage_ids=["p1"]).status_code == 200
    item = propose(mapping, source_revision=6).json()["items"][0]
    assert review(mapping, item["id"], source_revision=6).status_code == 409
    assert mapping[1].get(mapping[4] + "/decision-mappings").json()["revision"] == 1
