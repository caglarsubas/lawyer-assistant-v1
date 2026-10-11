"""Synthetic human declarations; no actual legal identity or approval."""

import json

import pytest
from sqlalchemy import func, select
from test_public_sources import source as source_fixture
from test_source_comparison import pair as pair_fixture
from test_source_reviews import another_client, assess, assign
from test_workspace import workspace as workspace_fixture

from app import source_relationships
from app.db import User
from app.source_review_models import SourceRelationshipEvent, SourceRelationshipHead

source = source_fixture
workspace = workspace_fixture
pair = pair_fixture


@pytest.fixture
def relationship(pair):
    app, client, store, left, right, params, _ = pair
    base = f"/api/v1/public-sources/{left}/relationship?other_source_id={right}"
    comparison = client.get(f"/api/v1/public-sources/{left}/comparison", params=params).json()
    body = {
        "expected_revision": 0,
        "expected_source_revisions": {left: 2, right: 2},
        "classification": "same_work_same_version",
        "rationale": "Synthetic reviewer inspected separate evidence",
        "identities": [
            {"source_id": ident, "work_ref": "synthetic-work", "version_ref": "synthetic-v1"}
            for ident in (left, right)
        ],
        "comparison": {key: value for key, value in params.items() if key != "other_source_id"}
        | {"offset": 0, "other_offset": 0, "evidence_sha256": comparison["evidence_sha256"]},
        "evidence_refs": [{"reference": "synthetic independent identity evidence", "sha256": "d" * 64}],
        "effort": None,
    }
    return app, client, store, left, right, base, body


def prepare(value):
    _, client, _, left, right, _, _ = value
    for ident in (left, right):
        base = f"/api/v1/public-sources/{ident}/review"
        assert assign(client, base).status_code == 200
        assert assess(client, base).status_code == 200


def counts(app):
    with app.state.store.session() as session:
        return [
            session.scalar(select(func.count()).select_from(model))
            for model in (SourceRelationshipHead, SourceRelationshipEvent)
        ]


def test_virtual_pair_reads_canonical_order_no_records_or_inference(relationship, monkeypatch):
    app, client, _, left, right, base, _ = relationship
    monkeypatch.setattr("httpx.HTTPTransport.handle_request", lambda *_: pytest.fail("network forbidden"))
    state = client.get(base).json()
    reverse = client.get(
        f"/api/v1/public-sources/{right}/relationship", params={"other_source_id": left}
    ).json()
    assert state == reverse and state["revision"] == 0 and state["history"] == []
    assert state["source_ids"] == sorted([left, right]) and counts(app) == [0, 0]
    assert not any(
        state[key]
        for key in (
            "resolved_for_handoff",
            "independent_originals_verified",
            "current_law_verified",
            "publication_eligible",
        )
    )


def test_encrypted_history_exact_evidence_export_and_disagreement(relationship):
    app, client, store, left, right, base, body = relationship
    prepare(relationship)
    originals = {
        ident: {path.name: path.read_bytes() for path in (store.root / ident).iterdir()}
        for ident in (left, right)
    }
    result = client.post(base, json=body)
    assert result.status_code == 200, result.text
    state = result.json()
    assert state["resolved_for_handoff"] and state["revision"] == 1 and not state["stale"]
    event = state["latest"]
    assert event["reviewer"]["name"] == "Demo Avukat"
    assert event["input"] == body
    evidence = event["comparison_evidence"]
    assert json.loads(evidence["evidence_json"])["legal_identity_status"] == "unresolved"
    assert evidence["evidence_sha256"] == body["comparison"]["evidence_sha256"]
    update = {
        **body,
        "expected_revision": 1,
        "classification": "unresolved",
        "identities": [],
        "rationale": "Conflicting interpretation still unresolved",
    }
    result = client.post(base, json=update)
    assert result.status_code == 200, result.text
    assert result.json()["history"][1] == event and not result.json()["resolved_for_handoff"]
    assert client.post(base, json=update).status_code == 409 and counts(app) == [1, 2]
    exported = client.get(base.replace("/relationship?", "/relationship/export?"))
    assert exported.status_code == 200
    assert exported.headers["cache-control"] == "no-store"
    assert exported.json()["review"]["latest"]["input"]["classification"] == "unresolved"
    assert not exported.json()["review"]["signed"]
    with app.state.store.session() as session:
        rows = list(session.scalars(select(SourceRelationshipEvent)))
        assert all("Conflicting" not in row.payload and "synthetic-work" not in row.payload for row in rows)
    for ident in (left, right):
        assert originals[ident] == {path.name: path.read_bytes() for path in (store.root / ident).iterdir()}
        assert store.detail(ident)["publication_status"] == "staged"


@pytest.mark.parametrize("side", [3, 4])
def test_any_source_revision_stales_opinion_and_renewal_is_explicit(relationship, side):
    _, client, _, _, _, base, body = relationship
    prepare(relationship)
    assert client.post(base, json=body).status_code == 200
    ident = relationship[side]
    assert (
        assess(client, f"/api/v1/public-sources/{ident}/review", revision=2, category="legal").status_code
        == 200
    )
    state = client.get(base).json()
    assert state["stale"] and not state["resolved_for_handoff"]
    assert state["latest"]["input"] == body  # Never rewrite reviewed history.
    assert client.post(base, json={**body, "expected_revision": 1}).status_code == 409
    renewed = {
        **body,
        "expected_revision": 1,
        "expected_source_revisions": {**body["expected_source_revisions"], ident: 3},
    }
    response = client.post(base, json=renewed)
    assert response.status_code == 200, response.text
    assert not response.json()["stale"] and response.json()["history"][1] == state["latest"]


def test_unresolved_can_record_without_identity_acceptance_but_requires_both_owners(relationship):
    app, client, _, left, right, base, body = relationship
    pending = {
        **body,
        "classification": "unresolved",
        "identities": [],
        "expected_source_revisions": {left: 1, right: 1},
        "evidence_refs": [],
    }
    assert client.post(base, json=pending).status_code == 409
    for ident in (left, right):
        assert assign(client, f"/api/v1/public-sources/{ident}/review").status_code == 200
    assert client.post(base, json=pending).status_code == 200
    assert (
        client.post(
            base,
            json={
                **body,
                "expected_revision": 1,
                "expected_source_revisions": pending["expected_source_revisions"],
            },
        ).status_code
        == 409
    )
    other = another_client(app)
    assert other.post(base, json={**pending, "expected_revision": 1}).status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        "no_support",
        "comparison_only",
        "duplicate_support",
        "inconsistent_work",
        "missing_identity",
        "wrong_source",
        "reviewer",
        "time",
        "bad_effort",
        "bool_revision",
        "identity_on_unknown",
    ],
)
def test_malformed_unsubstantiated_or_injected_input_never_writes(relationship, change):
    app, client, _, left, right, base, body = relationship
    prepare(relationship)
    body = json.loads(json.dumps(body))
    if change == "no_support":
        body["evidence_refs"] = []
    elif change == "comparison_only":
        body["evidence_refs"][0]["sha256"] = body["comparison"]["evidence_sha256"]
    elif change == "duplicate_support":
        body["evidence_refs"] *= 2
    elif change == "inconsistent_work":
        body["identities"][1]["work_ref"] = "different-work"
    elif change == "missing_identity":
        body["identities"].pop()
    elif change == "wrong_source":
        body["expected_source_revisions"] = {left: 2, "f" * 64: 2}
    elif change == "reviewer":
        body["reviewer"] = "forged"
    elif change == "time":
        body["created_at"] = "2026-01-01"
    elif change == "bad_effort":
        body["effort"] = {"active_seconds": True, "basis": "estimate"}
    elif change == "bool_revision":
        body["expected_source_revisions"][right] = True
    elif change == "identity_on_unknown":
        body["classification"] = "unresolved"
    assert client.post(base, json=body).status_code == 422
    assert counts(app) == [0, 0]


@pytest.mark.parametrize("change", ["digest", "passage", "offset", "source_revision", "pair_revision"])
def test_wrong_comparison_or_versions_fail_without_writes(relationship, change):
    app, client, _, left, _, base, body = relationship
    prepare(relationship)
    body = json.loads(json.dumps(body))
    if change == "digest":
        body["comparison"]["evidence_sha256"] = "f" * 64
    elif change == "passage":
        body["comparison"]["passage_id"] = "missing"
    elif change == "offset":
        body["comparison"]["offset"] = 20000
    elif change == "source_revision":
        body["expected_source_revisions"][left] = 1
    elif change == "pair_revision":
        body["expected_revision"] = 1
    response = client.post(base, json=body)
    assert response.status_code in {409, 422} and counts(app) == [0, 0]


def test_firm_isolation_role_csrf_and_explicit_zero_effort(relationship):
    app, client, _, _, _, base, body = relationship
    prepare(relationship)
    assert client.post(base, json=body, headers={"X-CSRF-Token": "bad"}).status_code == 403
    body = {**body, "effort": {"active_seconds": 0, "basis": "self_reported_timer"}}
    assert client.post(base, json=body).json()["latest"]["input"]["effort"]["active_seconds"] == 0
    foreign = another_client(app, username="foreign", firm="another-firm")
    assert foreign.get(base).json()["latest"] is None
    assert foreign.post(base, json=body).status_code == 409
    lawyer = another_client(app, username="lawyer", role="lawyer")
    assert lawyer.get(base).status_code == lawyer.post(base, json=body).status_code == 403


@pytest.mark.parametrize("target", ["head", "event", "missing_event", "historical_source_pin"])
def test_corrupt_ledger_or_historical_source_binding_fails_closed(relationship, target):
    app, client, _, left, _, base, body = relationship
    prepare(relationship)
    assert client.post(base, json=body).status_code == 200
    with app.state.store.session() as session:
        row = session.scalar(select(SourceRelationshipHead if target == "head" else SourceRelationshipEvent))
        if target == "missing_event":
            session.connection().exec_driver_sql("DELETE FROM source_relationship_events")
        else:
            value = app.state.store.decode(row)
            if target == "historical_source_pin":
                value["event"]["source_reviews"][left]["identity_assessment"]["rationale"] = (
                    "plausible but never recorded"
                )
            elif target == "head":
                value["latest"]["input"]["classification"] = "unresolved"
            else:
                value["context"]["firm_id"] = "wrong-firm"
            session.connection().exec_driver_sql(
                f"UPDATE {row.__tablename__} SET payload = ? WHERE id = ?",
                (app.state.store.encode(value), row.id),
            )
        session.commit()
    assert client.get(base).status_code == 409
    assert client.get(base.replace("/relationship?", "/relationship/export?")).status_code == 409


@pytest.mark.parametrize("side", [3, 4])
def test_corrupt_either_package_blocks_read_and_mutation(relationship, side):
    app, client, store, _, _, base, body = relationship
    prepare(relationship)
    path = store.root / relationship[side] / "raw.bin"
    path.chmod(0o600)
    path.write_bytes(b"corrupt synthetic original")
    assert client.get(base).status_code == client.post(base, json=body).status_code == 409
    assert counts(app) == [0, 0]


def test_revoked_role_at_final_write_rolls_back(relationship, monkeypatch):
    app, client, _, _, _, base, body = relationship
    prepare(relationship)
    original = source_relationships.reviews._lock_identity
    calls = 0

    def revoked(session, request, expected):
        nonlocal calls
        calls += 1
        if calls == 2:
            session.get(User, expected.id).role = "lawyer"
            session.flush()
        return original(session, request, expected)

    monkeypatch.setattr(source_relationships.reviews, "_lock_identity", revoked)
    assert client.post(base, json=body).status_code == 403 and counts(app) == [0, 0]


@pytest.mark.parametrize("classification", ["same_work_different_version", "different_work"])
def test_explicit_other_identity_classifications_are_not_transitive_merges(relationship, classification):
    _, client, _, _, _, base, body = relationship
    prepare(relationship)
    body["classification"] = classification
    body["identities"][1][
        "version_ref" if classification == "same_work_different_version" else "work_ref"
    ] = "other-synthetic-identity"
    response = client.post(base, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["resolved_for_handoff"] and not response.json()["independent_originals_verified"]


def test_source_change_at_final_boundary_rolls_back(relationship, monkeypatch):
    app, client, _, left, _, base, body = relationship
    prepare(relationship)
    original = source_relationships._source_states
    calls = 0

    def changed(*args, **kwargs):
        nonlocal calls
        value = original(*args, **kwargs)
        calls += 1
        if calls == 2:
            value[left]["revision"] += 1
        return value

    monkeypatch.setattr(source_relationships, "_source_states", changed)
    assert client.post(base, json=body).status_code == 409 and counts(app) == [0, 0]


def test_event_limit_no_silent_loss_or_automatic_retry(relationship, monkeypatch):
    app, client, _, _, _, base, body = relationship
    prepare(relationship)
    monkeypatch.setattr(source_relationships, "MAX_EVENTS", 1)
    assert client.post(base, json=body).status_code == 200
    assert client.post(base, json={**body, "expected_revision": 1}).status_code == 409
    assert counts(app) == [1, 1] and client.get(base).json()["revision"] == 1


@pytest.mark.parametrize("action", ["update", "delete"])
def test_events_are_orm_append_only(relationship, action):
    app, client, _, _, _, base, body = relationship
    prepare(relationship)
    assert client.post(base, json=body).status_code == 200
    with app.state.store.session() as session:
        row = session.scalar(select(SourceRelationshipEvent))
        if action == "delete":
            session.delete(row)
        else:
            row.payload = "overwrite"
        with pytest.raises(ValueError, match="append-only"):
            session.commit()
