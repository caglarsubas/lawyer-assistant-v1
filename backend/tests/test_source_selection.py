"""Invented selection/review inputs only; no independent originals or legal review."""

import json

import pytest
from sqlalchemy import delete, select, update
from test_public_sources import source as source_fixture
from test_source_comparison import pair as pair_fixture
from test_source_relationships import counts, prepare
from test_source_relationships import relationship as relationship_fixture
from test_source_reviews import another_client, assess, assign
from test_workspace import workspace as workspace_fixture

from app import source_selection
from app.db import User, digest
from app.source_review_models import SourceRelationshipEvent, SourceRelationshipHead

source = source_fixture
workspace = workspace_fixture
pair = pair_fixture
relationship = relationship_fixture
BASE = "/api/v1/public-sources/selection-review"


def inspect(value, *, ids=None, export=False):
    _, client, _, left, right, _, _ = value
    return client.post(BASE + ("/export" if export else ""), json={"source_ids": ids or [left, right]})


def receipt(response):
    assert response.status_code == 200, response.text
    envelope = response.json()
    assert digest(envelope["evidence_json"]) == envelope["evidence_sha256"]
    return json.loads(envelope["evidence_json"])


def record(value, classification="same_work_same_version", revision=0):
    _, client, _, _, _, base, body = value
    body = {**body, "expected_revision": revision, "classification": classification}
    if classification == "unresolved":
        body["identities"] = []
    elif classification == "different_work":
        body["identities"] = [{**item, "work_ref": f"work-{index}"} for index, item in enumerate(body["identities"])]
    result = client.post(base, json=body)
    assert result.status_code == 200, result.text


def test_missing_reviews_explicit_unknown_no_writes_no_provider(relationship, monkeypatch):
    app, client, store, left, right, _, _ = relationship
    monkeypatch.setattr("httpx.HTTPTransport.handle_request", lambda *_: pytest.fail("network forbidden"))
    monkeypatch.setattr("pypdf.PdfReader", lambda *_: pytest.fail("no parsing"))
    originals = {ident: (store.root / ident / "source.json").read_bytes() for ident in (left, right)}
    body = receipt(inspect(relationship))
    assert body["source_ids"] == sorted([left, right])
    assert body["coverage"]["pair_status_counts"] == {"missing": 1, "resolved": 0, "stale": 0, "unresolved": 0}
    assert body["pairs"][0]["latest"] is None
    assert len(body["source_review_gaps"]) == 2 and body["identity_conflicts"] == []
    assert body["independent_original_count"] is None
    for flag in ("independent_originals_verified", "study_qualified", "publication_eligible", "current_law_verified", "signed"):
        assert body[flag] is False
    assert inspect(relationship).content == inspect(relationship, ids=[right, left]).content
    assert counts(app) == [0, 0]
    for ident in (left, right):
        assert originals[ident] == (store.root / ident / "source.json").read_bytes()
    assert client.get(BASE).status_code in {404, 405}


def test_complete_pair_is_still_no_study_independence_and_export_rechecks(relationship):
    prepare(relationship)
    record(relationship)
    body = receipt(inspect(relationship))
    pair = body["pairs"][0]
    assert body["coverage"]["all_pairs_current_resolved"]
    assert pair["status"] == "resolved" and pair["history_count"] == 1
    assert pair["latest"]["input"]["classification"] == "same_work_same_version"
    assert pair["latest"]["comparison_sha256"] == relationship[-1]["comparison"]["evidence_sha256"]
    assert "comparison_evidence" not in pair["latest"]
    assert body["independent_original_count"] is None and not body["study_qualified"]
    assert all(set(gap["categories"]) == {"rights", "extraction", "legal"} for gap in body["source_review_gaps"])
    exported = inspect(relationship, export=True)
    assert receipt(exported) == body
    assert exported.json()["schema_version"] == "source-selection-dossier-v1"
    assert exported.headers["cache-control"] == "no-store"
    assert exported.headers["x-content-type-options"] == "nosniff"
    _, client, _, left, _, _, _ = relationship
    assert assess(client, f"/api/v1/public-sources/{left}/review", revision=2, category="legal").status_code == 200
    fresh = receipt(inspect(relationship, export=True))
    assert fresh["pairs"][0]["status"] == "stale" and not fresh["coverage"]["all_pairs_current_resolved"]
    assert fresh["pairs"][0]["latest"] == pair["latest"]


def test_disagreements_all_history_and_unknown_effort_retained(relationship):
    prepare(relationship)
    record(relationship)
    record(relationship, "different_work", 1)
    record(relationship, "unresolved", 2)
    pair = receipt(inspect(relationship))["pairs"][0]
    assert pair["status"] == "unresolved"
    assert pair["historical_classification_changes"] == 2
    assert pair["history_count"] == 3 and sum(pair["historical_classifications"].values()) == 3
    assert pair["latest"]["input"]["effort"] is None


@pytest.mark.parametrize("ids", [[], ["a" * 64], ["a" * 64] * 2, ["a" * 64, "BAD"], ["a" * 64, 1],
                                [f"{index:064x}" for index in range(7)]])
def test_selection_bounds_and_duplicates(relationship, ids):
    assert relationship[1].post(BASE, json={"source_ids": ids}).status_code == 422


@pytest.mark.parametrize("extra", ["firm_id", "reviewer", "study_qualified", "expected_revision"])
def test_caller_cannot_supply_authority_or_state(relationship, extra):
    assert relationship[1].post(BASE, json={"source_ids": [relationship[3], relationship[4]], extra: "injected"}).status_code == 422


def test_role_csrf_and_firm_confidentiality(relationship):
    app, client, _, left, right, _, _ = relationship
    prepare(relationship)
    record(relationship)
    foreign = another_client(app, username="selection_other", role="curator", firm="other-firm")
    response = foreign.post(BASE, json={"source_ids": [left, right]})
    other = receipt(response)
    assert other["pairs"][0]["status"] == "missing"
    assert other["scope_sha256"] != receipt(inspect(relationship))["scope_sha256"]
    assert "synthetic-work" not in response.text
    lawyer = another_client(app, username="selection_lawyer", role="lawyer")
    assert lawyer.post(BASE, json={"source_ids": [left, right]}).status_code == 403
    old = client.headers.pop("x-csrf-token")
    assert inspect(relationship).status_code == 403
    client.headers["x-csrf-token"] = old


@pytest.mark.parametrize("which", ["head", "event", "missing_event", "original"])
def test_corrupt_pair_or_original_fails_without_partial_result(relationship, which):
    app, _, store, left, _, _, _ = relationship
    prepare(relationship)
    record(relationship)
    if which == "original":
        original = store.root / left / "raw.bin"
        original.chmod(0o600)
        original.write_bytes(b"replaced")
    else:
        with app.state.store.session() as session:
            if which == "missing_event":
                session.execute(delete(SourceRelationshipEvent))
            else:
                model = SourceRelationshipHead if which == "head" else SourceRelationshipEvent
                session.execute(update(model).values(payload="corrupt ciphertext"))
            session.commit()
    response = inspect(relationship)
    assert response.status_code in {404, 409}
    assert "evidence_json" not in response.json()


@pytest.mark.parametrize("change", ["pair", "source", "authorization", "event_deletion"])
def test_late_changes_discard_snapshot(relationship, monkeypatch, change):
    app, client, _, left, _, _, _ = relationship
    prepare(relationship)
    record(relationship)
    original = source_selection._identity_conflicts

    def changed(pairs):
        if change == "pair":
            record(relationship, "unresolved", 1)
        elif change == "source":
            assert assess(client, f"/api/v1/public-sources/{left}/review", revision=2, category="legal").status_code == 200
        elif change == "event_deletion":
            with app.state.store.session() as session:
                session.execute(delete(SourceRelationshipEvent))
                session.commit()
        else:
            with app.state.store.session() as session:
                session.scalar(select(User).where(User.username == "demo")).active = False
                session.commit()
        return original(pairs)

    monkeypatch.setattr(source_selection, "_identity_conflicts", changed)
    result = inspect(relationship, export=True)
    assert result.status_code in {401, 409} and "evidence_json" not in result.json()


def test_event_and_receipt_budgets_fail_closed(relationship, monkeypatch):
    prepare(relationship)
    record(relationship)
    monkeypatch.setattr(source_selection, "MAX_TOTAL_EVENTS", 0)
    assert inspect(relationship).status_code == 409
    monkeypatch.setattr(source_selection, "MAX_TOTAL_EVENTS", 200)
    monkeypatch.setattr(source_selection, "MAX_RECEIPT_BYTES", 1)
    assert inspect(relationship).status_code == 409


def test_cooperative_work_deadline_discards_result(relationship, monkeypatch):
    ticks = iter([0, 21])
    monkeypatch.setattr(source_selection, "monotonic", lambda: next(ticks))
    response = inspect(relationship)
    assert response.status_code == 409 and "evidence_json" not in response.json()


def test_identity_conflicts_are_direct_declarations_not_transitive_inference():
    def pair(ident, source, work, version, status="resolved"):
        return {"pair_id": ident, "status": status, "latest": {"input": {"identities": [
            {"source_id": source, "work_ref": work, "version_ref": version}]}}}
    data = [pair("ab", "a", "work", "v1"), pair("ac", "a", "another-work", "v2"),
            pair("bc", "b", "work", "v1"), pair("bd", "b", "ignored", "v9", "stale")]
    conflicts = source_selection._identity_conflicts(data)
    assert [item["source_id"] for item in conflicts] == ["a"]
    assert [item["pair_id"] for item in conflicts[0]["declarations"]] == ["ab", "ac"]


def test_three_sources_surface_missing_edge_and_conflicting_direct_refs(relationship, pair):
    # Both fixtures share the same underlying pair; the third is a new immutable
    # representation. Invented declarations deliberately disagree about A.
    _, client, _, left, right, _, body = relationship
    prepare(relationship)
    record(relationship)
    third = pair[-1](text="Synthetic third representation", raw=b"synthetic third original")
    third_review = f"/api/v1/public-sources/{third}/review"
    assert assign(client, third_review).status_code == 200
    assert assess(client, third_review).status_code == 200
    params = {"other_source_id": third, "passage_id": "p1", "other_passage_id": "other_p1"}
    compared = client.get(f"/api/v1/public-sources/{left}/comparison", params=params).json()
    request = {**body, "expected_source_revisions": {left: 2, third: 2},
               "identities": [{"source_id": ident, "work_ref": "other-work", "version_ref": "other-v1"}
                              for ident in (left, third)],
               "comparison": {"passage_id": "p1", "other_passage_id": "other_p1", "offset": 0,
                              "other_offset": 0, "evidence_sha256": compared["evidence_sha256"]}}
    result = client.post(f"/api/v1/public-sources/{left}/relationship?other_source_id={third}", json=request)
    assert result.status_code == 200, result.text
    state = receipt(inspect(relationship, ids=[third, right, left]))
    assert state["coverage"]["expected_pair_count"] == 3
    assert state["coverage"]["pair_status_counts"] == {"missing": 1, "resolved": 2, "stale": 0, "unresolved": 0}
    assert [item["source_id"] for item in state["identity_conflicts"]] == [left]
    assert state["independent_original_count"] is None


def test_six_source_boundary_reports_all_fifteen_direct_pairs(relationship, pair):
    ids = [relationship[3], relationship[4]]
    for index in range(4):
        ids.append(pair[-1](text=f"Synthetic additional text {index}", raw=f"Synthetic original {index}".encode()))
    state = receipt(inspect(relationship, ids=list(reversed(ids))))
    assert len(state["sources"]) == 6 and len(state["pairs"]) == 15
    assert state["coverage"]["pair_status_counts"]["missing"] == 15
    assert state["identity_conflicts"] == []
