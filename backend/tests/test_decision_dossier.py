"""Bounded confidential dossier checks; no legal/publication acceptance."""
import hashlib
import json

import pytest
from sqlalchemy import select, update
from test_decision_mappings import mapping as mapping_fixture
from test_decision_mappings import propose, ready, review
from test_jurisprudence_candidates import incoming as incoming_fixture
from test_public_sources import source as source_fixture
from test_source_reviews import another_client, assess
from test_workspace import workspace as workspace_fixture

from app import decision_dossier, decision_mappings
from app.decision_mapping_models import DecisionMappingEvent

mapping = mapping_fixture
incoming = incoming_fixture
source = source_fixture
workspace = workspace_fixture


def export_ready(mapping):
    ready(mapping)
    assert assess(mapping[1], mapping[4] + "/review", 5, "rights",
                  permitted_uses=["local_processing", "internal_display", "export"]).status_code == 200
    identifier = propose(mapping, source_revision=6).json()["items"][0]["id"]
    assert review(mapping, identifier, source_revision=6).status_code == 200
    return identifier


def dossier(mapping, **changes):
    return mapping[1].post(mapping[4] + "/decision-mappings/dossier", json={
        "expected_revision": 2, "expected_source_review_revision": 6, **changes})


def decoded(response):
    assert response.status_code == 200, response.text
    envelope = response.json()
    assert hashlib.sha256(envelope["evidence_json"].encode()).hexdigest() == envelope["evidence_sha256"]
    return json.loads(envelope["evidence_json"])


def test_complete_revision_bound_confidential_export_no_writes(mapping, monkeypatch):
    export_ready(mapping)
    monkeypatch.setattr(decision_mappings, "HISTORY_LIMIT", 1)
    state = mapping[1].get(mapping[4] + "/decision-mappings").json()
    assert state["history_truncated"]
    response = dossier(mapping)
    data = decoded(response)
    assert response.headers["cache-control"] == "no-store"
    assert data["confidentiality"] == "firm_confidential" and data["signed"] is False
    assert data["history_complete"] and not data["mappings"]["history_truncated"]
    assert [event["revision"] for event in data["mappings"]["history"]] == [2, 1]
    assert len(data["source_review"]["history"]) == 6
    assert data["source_review"]["assessments"]["rights"]["permitted_uses"] == ["local_processing", "internal_display", "export"]
    assert data["handoff_checks"]["independent_review_ready"]
    assert not data["publication_eligible"] and not data["handoff_checks"]["canonical_identity_resolved"]
    assert not data["handoff_checks"]["legal_effect_verified"]
    for passage in data["supporting_passages"]:
        assert mapping[6].text[passage["start"]:passage["end"]] == passage["text"]
        assert hashlib.sha256(passage["text"].encode()).hexdigest() == passage["sha256"]
    assert mapping[1].get(mapping[4] + "/decision-mappings").json() == state
    assert mapping[2].detail(mapping[3])["publication_status"] == "staged"


def test_export_requires_explicit_current_rights_use_scope(mapping):
    ready(mapping)
    identifier = propose(mapping).json()["items"][0]["id"]
    review(mapping, identifier)
    response = dossier(mapping, expected_source_review_revision=5)
    assert response.status_code == 409 and "evidence_json" not in response.json()


@pytest.mark.parametrize("changes", [
    {"expected_revision": 1}, {"expected_source_review_revision": 5}, {"expected_revision": True},
    {"expected_revision": 1001}, {"extra": "not accepted"},
])
def test_revision_pins_and_strict_contract(mapping, changes):
    export_ready(mapping)
    response = dossier(mapping, **changes)
    assert response.status_code in {409, 422} and "evidence_json" not in response.json()


def test_draft_preserves_disagreement_and_unknowns_not_handoff(mapping):
    identifier = export_ready(mapping)
    assert review(mapping, identifier, revision=2, source_revision=6, decision="needs_changes", resolution=None).status_code == 200
    data = decoded(dossier(mapping, expected_revision=3))
    assert data["mappings"]["items"][0]["resolution"] is None
    assert data["mappings"]["history"][1]["snapshot"]["resolution"]["event_date"] is None
    assert not data["handoff_checks"]["independent_review_ready"]
    assert data["handoff_checks"]["unresolved_mapping_ids"] == [identifier]


def test_old_invalid_event_cannot_hide_beyond_display_history(mapping, monkeypatch):
    export_ready(mapping)
    monkeypatch.setattr(decision_mappings, "HISTORY_LIMIT", 1)
    store = mapping[0].state.store
    with store.session() as session:
        row = session.scalar(select(DecisionMappingEvent).where(DecisionMappingEvent.revision == 1))
        payload = store.decode(row)
        payload["event"]["snapshot"]["candidate"]["text"] = "tampered old synthetic text"
        session.execute(update(DecisionMappingEvent).where(DecisionMappingEvent.id == row.id).values(payload=store.encode(payload)))
        session.commit()
    assert mapping[1].get(mapping[4] + "/decision-mappings").status_code == 200
    response = dossier(mapping)
    assert response.status_code == 409 and "evidence_json" not in response.json()


def test_original_corruption_during_export_withholds_all_evidence(mapping, monkeypatch):
    export_ready(mapping)
    original = decision_dossier.handoff_checks
    def corrupt(state):
        (mapping[2].root / mapping[3] / "raw.bin").write_bytes(b"tampered synthetic bytes")
        return original(state)
    monkeypatch.setattr(decision_dossier, "handoff_checks", corrupt)
    response = dossier(mapping)
    assert response.status_code == 409 and "evidence_json" not in response.json()


def test_size_exhaustion_does_not_export_partial_history(mapping, monkeypatch):
    export_ready(mapping)
    monkeypatch.setattr(decision_dossier, "MAX_DOSSIER_BYTES", 256)
    response = dossier(mapping)
    assert response.status_code == 409 and "evidence_json" not in response.json()


def test_other_firm_and_lawyer_cannot_export_private_reviews(mapping):
    export_ready(mapping)
    other = another_client(mapping[0], firm="other-firm")
    response = dossier((mapping[0], other, *mapping[2:]), expected_revision=0, expected_source_review_revision=0)
    assert response.status_code == 409 and "evidence_json" not in response.json()
    lawyer = another_client(mapping[0], username="other-lawyer", role="lawyer")
    assert dossier((mapping[0], lawyer, *mapping[2:])).status_code == 403


def test_changed_source_review_withholds_old_pin_and_marks_stale(mapping):
    export_ready(mapping)
    assert assess(mapping[1], mapping[4] + "/review", 6, "legal").status_code == 200
    assert dossier(mapping).status_code == 409
    result = decoded(dossier(mapping, expected_source_review_revision=7))
    assert result["mappings"]["items"][0]["stale"]
    assert not result["handoff_checks"]["independent_review_ready"]


def test_csrf_required_even_for_confidential_read_export(mapping):
    export_ready(mapping)
    mapping[1].headers.pop("X-CSRF-Token")
    assert dossier(mapping).status_code == 403


def test_literal_conflicts_kept_per_declared_decision_no_identity_merging():
    def item(identifier, value, reference="same-decision", institution="same-institution"):
        return {"id": identifier, "status": "accepted", "stale": False,
                "candidate": {"kind": "decision_number", "parsed_value": value},
                "resolution": {"occurrence_role": "own_decision", "decision_ref": reference,
                               "institution_ref": institution, "proceeding_ref": "same-proceeding", "event_date": None}}
    state = {"items": [item("one", "2020/1"), item("two", "2020/2")], "source_review_ready": True, "handoff_ready": True}
    checks = decision_dossier.handoff_checks(state)
    assert len(checks["identity_conflicts"]) == 1 and not checks["independent_review_ready"]
    assert checks["identity_conflicts"][0]["field"] == "decision_number"
    state["items"][1] = item("two", "2020/2", reference="separate-decision")
    assert decision_dossier.handoff_checks(state)["identity_conflicts"] == []
    state["items"][1] = item("two", "2020/1", institution="another-institution")
    assert decision_dossier.handoff_checks(state)["identity_conflicts"][0]["field"] == "institution_ref"


def test_actual_conflicting_institution_reviews_block_handoff(mapping):
    from test_decision_mappings import resolution
    export_ready(mapping)
    item = propose(mapping, revision=2, source_revision=6, index=1).json()["items"][1]
    candidate = mapping[5][1]
    value = resolution(mapping, start=candidate["start"], end=candidate["end"], institution_ref="different-synthetic-institution",
                       event_role="decision", event_date="2021-01-12")
    response = review(mapping, item["id"], revision=3, source_revision=6, resolution=value)
    assert response.status_code == 200, response.text
    data = decoded(dossier(mapping, expected_revision=4))
    assert data["mappings"]["handoff_ready"]
    assert not data["handoff_checks"]["independent_review_ready"]
    assert data["handoff_checks"]["identity_conflicts"][0]["field"] == "institution_ref"
