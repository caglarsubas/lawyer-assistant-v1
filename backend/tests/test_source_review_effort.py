"""Invented curator records; these are not actual review or productivity results."""

import pytest
from pydantic import ValidationError
from sqlalchemy import select, update
from test_source_reviews import (
    another_client,
    assess,
    assign,
    counts,
)
from test_source_reviews import (
    review as review_fixture,
)
from test_source_reviews import (
    source as source_fixture,
)
from test_source_reviews import (
    workspace as workspace_fixture,
)

from app import source_reviews
from app.source_review_models import SourceReviewEvent, SourceReviewHead

review = review_fixture
source = source_fixture
workspace = workspace_fixture


def effort(seconds, basis="self_reported_timer"):
    return {"active_seconds": seconds, "basis": basis}


@pytest.mark.parametrize("value", [
    effort(-1), effort(86401), effort(True), effort(False), effort(1.5), effort("12"),
    effort(None), effort(10, "wall_clock"), effort(10, "verified_timer"),
    {"active_seconds": 10}, {"basis": "estimate"}, {}, [], "12",
    {**effort(10), "reviewer_id": "forged"}, {**effort(10), "started_at": "2020-01-01"},
])
def test_effort_is_strict_bounded_and_cannot_claim_verification(value):
    with pytest.raises(ValidationError):
        source_reviews.AssessmentInput.model_validate({
            "expected_revision": 0, "rationale": "Invented assessment", "category": "legal",
            "decision": "needs_changes", "effort": value,
        })


@pytest.mark.parametrize("seconds", [0, 1, 86400])
@pytest.mark.parametrize("basis", ["self_reported_timer", "estimate"])
def test_explicit_zero_and_upper_bound_are_valid_declarations(seconds, basis):
    assert source_reviews.ReviewEffort.model_validate(effort(seconds, basis)).model_dump() == effort(seconds, basis)


def test_absent_and_null_effort_remain_unknown_without_guessing_assignment_time(review):
    app, client, _, _, base = review
    empty = client.get(base).json()["effort_summary"]
    assert empty["total_assessments"] == empty["unknown_assessments"] == 0
    assert counts(app) == (0, 0)
    assert assign(client, base).status_code == 200
    assert assess(client, base, 1).status_code == 200
    state = assess(client, base, 2, effort=None).json()
    assert state["effort_summary"]["unknown_assessments"] == 2
    assert state["effort_summary"]["timer_reported_active_seconds"] == 0
    assert state["effort_summary"]["estimated_active_seconds"] == 0
    assert all("effort" not in event for event in state["history"])
    assert client.get(base + "/export").json()["review"] == state
    assert counts(app) == (1, 3)  # Reads do not backfill legacy time records.


def test_complete_verified_ledger_totals_survive_visible_history_truncation(review, monkeypatch):
    app, client, _, _, base = review
    monkeypatch.setattr(source_reviews, "HISTORY_LIMIT", 2)
    assign(client, base)
    for revision, duration in enumerate((None, effort(0), effort(120, "estimate"), effort(42)), start=1):
        response = assess(client, base, revision, "legal", "needs_changes", effort=duration)
        assert response.status_code == 200, response.text
    state = response.json()
    expected = {"scope": "all_assessment_events", "declaration_only": True,
                "includes_superseded_assessments": True, "total_assessments": 4,
                "timer_reported_assessments": 2, "estimated_assessments": 1,
                "unknown_assessments": 1, "timer_reported_active_seconds": 42,
                "estimated_active_seconds": 120}
    assert state["effort_summary"] == expected
    assert len(state["history"]) == 2 and state["history_truncated"]
    assert len(state["assessments"]) == 1  # Previous decisions still incurred effort.
    assert client.get(base).json() == state
    exported = client.get(base + "/export").json()
    assert exported["review"]["effort_summary"] == expected
    assert len(exported["review"]["history"]) == 2
    assert not exported["signed"] and not state["publication_eligible"]
    assert counts(app) == (1, 5)


def test_reported_effort_is_encrypted_bound_to_reviewer_source_and_revision(review):
    app, client, public_store, identifier, base = review
    originals = {path.name: path.read_bytes() for path in (public_store.root / identifier).iterdir()}
    assigned = assign(client, base).json()["assigned_to"]
    state = assess(client, base, effort=effort(7319)).json()
    event = state["assessments"][0]
    assert event["revision"] == 2 and event["reviewer"] == assigned
    assert event["effort"] == effort(7319)
    with app.state.store.session() as session:
        head = session.scalar(select(SourceReviewHead))
        row = session.scalar(select(SourceReviewEvent).where(SourceReviewEvent.revision == 2))
        for record in (head, row):
            assert "active_seconds" not in record.payload and "self_reported_timer" not in record.payload
            assert app.state.store.decode(record)["source_binding"]["source_id"] == identifier
    assert originals == {path.name: path.read_bytes() for path in (public_store.root / identifier).iterdir()}
    foreign = another_client(app, role="admin", firm="foreign-firm")
    for endpoint in ("", "/export"):
        response = foreign.get(base + endpoint)
        assert response.status_code == 200
        foreign_state = response.json()["review"] if endpoint else response.json()
        assert foreign_state["effort_summary"]["total_assessments"] == 0
        assert "7319" not in response.text and assigned["id"] not in response.text


def test_effort_does_not_change_acceptance_rights_or_promote_source(review):
    _, client, _, _, base = review
    assign(client, base)
    for revision, category in enumerate(source_reviews.CATEGORIES, start=1):
        response = assess(client, base, revision, category, effort=effort(0, "estimate"))
        assert response.status_code == 200
    state = response.json()
    assert state["handoff_ready"] and not state["publication_eligible"]
    assert state["source"]["publication_status"] == "staged"
    assert state["source"]["rights_status"] == "rights_pending"
    assert state["effort_summary"]["estimated_assessments"] == 4
    assert state["effort_summary"]["estimated_active_seconds"] == 0
    rejected = assess(client, base, 5, "legal", "rejected", effort=effort(86400)).json()
    assert not rejected["handoff_ready"] and not rejected["publication_eligible"]
    assert rejected["effort_summary"]["total_assessments"] == 5


def test_invalid_stale_unowned_or_assignment_effort_cannot_double_count(review):
    app, client, _, _, base = review
    assign(client, base)
    assert assess(client, base, effort=effort(1.25)).status_code == 422
    other = another_client(app)
    assert assess(other, base, effort=effort(2)).status_code == 409
    assert client.post(base + "/assignment", json={"expected_revision": 1, "action": "release",
                                                 "rationale": "Invented release", "effort": effort(10)}).status_code == 422
    assert assess(client, base, effort=effort(50)).status_code == 200
    assert assess(client, base, effort=effort(50)).status_code == 409
    state = client.get(base).json()
    assert state["effort_summary"]["total_assessments"] == 1
    assert state["effort_summary"]["timer_reported_active_seconds"] == 50
    assert counts(app) == (1, 2)


@pytest.mark.parametrize("kind", ["invalid_head", "invalid_event", "valid_but_mismatched", "old_invalid_event"])
def test_corrupt_effort_never_enters_totals_or_export(review, monkeypatch, kind):
    app, client, _, _, base = review
    monkeypatch.setattr(source_reviews, "HISTORY_LIMIT", 1)
    assign(client, base)
    assess(client, base, effort=effort(10))
    if kind == "old_invalid_event":
        assess(client, base, 2, effort=effort(20))
    with app.state.store.session() as session:
        head = session.scalar(select(SourceReviewHead))
        if kind == "invalid_head":
            data = app.state.store.decode(head)
            data["assessments"]["source_identity"]["effort"] = effort(True)
            head.payload = app.state.store.encode(data)
        else:
            row = session.scalar(select(SourceReviewEvent).where(SourceReviewEvent.revision == 2))
            data = app.state.store.decode(row)
            data["event"]["effort"] = effort(11 if kind == "valid_but_mismatched" else -1)
            session.execute(update(SourceReviewEvent).where(SourceReviewEvent.id == row.id)
                            .values(payload=app.state.store.encode(data)))
        session.commit()
    for endpoint in ("", "/export"):
        response = client.get(base + endpoint)
        assert response.status_code == 409
        assert "effort_summary" not in response.text
    assert assign(client, base, 3 if kind == "old_invalid_event" else 2, "release").status_code == 409
