"""Synthetic inputs only; preview is local accounting, never model/legal approval."""

import copy
import json
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_analysis_feedback import setup_feedback
from test_analysis_reviews import review_request
from test_analysis_suggestions import finished, patch, prepare, start
from test_analysis_workbench import workbench as workbench_fixture

from app.analysis_proposals import FRAMING_RESERVE, prompt_measurement, proposal_messages
from app.db import Audit, Membership, Record
from app.provider import ProviderError


@pytest.fixture
def workbench(tmp_path, synthetic_analysis_workbench_seed):
    yield from workbench_fixture.__wrapped__(tmp_path, synthetic_analysis_workbench_seed)


def request_body(record, **extra):
    return {"expected_revision": record["revision"], "version_id": record["latest_version_id"],
            "request_id": uuid4().hex, **extra}


def storage_snapshot(app):
    with app.state.store.session() as session:
        return ({row.id: (row.revision, row.payload) for row in session.scalars(select(Record))},
                [row.id for row in session.scalars(select(Audit))])


def test_preview_measures_exact_envelope_without_network_queue_or_writes(workbench, monkeypatch):
    app, client, *_ = workbench
    record, endpoint = prepare(workbench, monkeypatch)
    before = storage_snapshot(app)
    for name in ("probe", "suggest_analysis", "generate"):
        monkeypatch.setattr(app.state.provider, name, lambda *_a, **_k: pytest.fail("No provider call"))
    monkeypatch.setattr(app.state.research_jobs, "reserve", lambda: pytest.fail("No queue reservation"))
    body = request_body(record, mode="repair")
    response = client.post(endpoint + "/context-budget", json=body)
    assert response.status_code == 200, response.text
    value = response.json()
    assert response.headers["cache-control"] == "no-store"
    assert value["prompt"] == prompt_measurement(proposal_messages(record))
    assert value["framing_reserve_units"] == FRAMING_RESERVE
    assert value["source_version_id"] == record["latest_version_id"]
    assert value["evidence"] == [{key: item[key] for key in (
        "evidence_id", "document_revision", "passage_sha256", "quote_sha256", "start", "end")}
        for item in record["evidence"]]
    assert value["fits"] and value["can_start"] and value["max_passes"] == 2
    assert value["scope"] == "exact_first_pass_only"
    assert value["remaining_units"] + value["prompt"]["total_upper_bound_units"] == 32768
    assert value["excess_units"] == 0
    for text in (record["issue"], record["evidence"][0]["text"], record["evidence"][0]["name"],
                 "SYNTHETIC-NOT-A-REAL-KEY", "org-lawyer"):
        assert text not in response.text
    repeated = client.post(endpoint + "/context-budget", json={**body, "request_id": uuid4().hex}).json()
    assert repeated == value
    assert storage_snapshot(app) == before


@pytest.mark.parametrize("margin", [-1, 0, 1])
def test_exact_limit_and_overflow_are_checked_before_queue_with_no_truncation(workbench, monkeypatch, margin):
    app, client, *_ = workbench
    record, endpoint = prepare(workbench, monkeypatch)
    app.state.settings.provider_context_limit = prompt_measurement(proposal_messages(record))["total_upper_bound_units"] + margin
    seen = []

    def suggest(content, **_options):
        seen.append(proposal_messages(content))
        return json.dumps(patch())

    monkeypatch.setattr(app.state.provider, "suggest_analysis", suggest)
    body = request_body(record)
    value = client.post(endpoint + "/context-budget", json=body).json()
    assert value["fits"] == (margin >= 0)
    assert value["remaining_units"] == max(0, margin) and value["excess_units"] == max(0, -margin)
    before = storage_snapshot(app)
    if margin < 0:
        monkeypatch.setattr(app.state.research_jobs, "reserve", lambda: pytest.fail("No oversized reservation"))
    response = client.post(endpoint, json={**body, "context_preview_sha256": value["preview_sha256"]})
    if margin < 0:
        assert response.status_code == 422 and "kesilmedi" in response.text
        assert storage_snapshot(app) == before and seen == []
    else:
        assert response.status_code == 202, response.text
        job = finished(client, endpoint, response.json()["id"])
        assert job["status"] == "completed"
        assert job["context_budget"] == value
        assert job["iterations"][0]["prompt"] == value["prompt"] == prompt_measurement(seen[0])
        assert json.loads(seen[0][1]["content"])["evidence"][0]["text"] == record["evidence"][0]["text"]


@pytest.mark.parametrize("boundary", ["model", "version", "document", "membership", "review"])
def test_changed_context_or_access_cannot_use_an_earlier_preview(workbench, monkeypatch, boundary):
    app, client, base, payload, _, doc_id, *_ = workbench
    record, endpoint = prepare(workbench, monkeypatch)
    body = request_body(record)
    value = client.post(endpoint + "/context-budget", json=body).json()
    if boundary == "model":
        app.state.settings.provider_model = "SYNTHETIC-changed-model"
    elif boundary == "version":
        update = copy.deepcopy(payload)
        update.update(expected_revision=record["revision"], change_note="SYNTHETIC new version")
        assert client.post(base + "/analyses/" + record["id"] + "/versions", json=update).status_code == 201
    elif boundary == "document":
        with app.state.store.session() as session:
            doc = session.get(Record, doc_id)
            app.state.store.update(doc, app.state.store.decode(doc))
            session.commit()
    elif boundary == "membership":
        with app.state.store.session() as session:
            membership = session.scalar(select(Membership).where(Membership.matter_id == base.rsplit("/", 1)[1]))
            session.delete(membership)
            session.commit()
    else:
        reviews = endpoint.removesuffix("/suggestions") + "/reviews"
        review, _ = review_request(client, reviews, record, decision="changes_requested")
        assert client.post(reviews, json=review).status_code == 201
    monkeypatch.setattr(app.state.research_jobs, "reserve", lambda: pytest.fail("No stale reservation"))
    monkeypatch.setattr(app.state.provider, "suggest_analysis", lambda *_a, **_k: pytest.fail("No stale inference"))
    response = client.post(endpoint, json={**body, "context_preview_sha256": value["preview_sha256"]})
    assert response.status_code == (404 if boundary == "membership" else 409), response.text
    if boundary == "membership":
        assert client.post(endpoint + "/context-budget", json=body).status_code == 404


def test_selected_review_findings_are_measured_and_old_failed_attempt_is_preserved(workbench, monkeypatch):
    app, client, *_ = workbench
    record, endpoint, _, event = setup_feedback(workbench, monkeypatch, targets=("analysis", "conclusion"))
    monkeypatch.setattr(app.state.provider, "suggest_analysis", lambda *_a, **_k: (_ for _ in ()).throw(ProviderError("SYNTHETIC failure")))
    queued, _ = start(client, endpoint, record)
    failed = finished(client, endpoint, queued["id"])
    assert failed["status"] == "failed" and not failed.get("iterations")
    before = storage_snapshot(app)
    body = request_body(record, review_feedback={"review_id": event["id"], "finding_indices": [1]})
    selected = client.post(endpoint + "/context-budget", json=body).json()
    unselected = client.post(endpoint + "/context-budget", json=request_body(record)).json()
    assert selected["source_review_id"] == event["id"]
    assert selected["prompt"]["utf8_bytes"] > unselected["prompt"]["utf8_bytes"]
    assert selected["prompt"]["messages_sha256"] != unselected["prompt"]["messages_sha256"]
    app.state.settings.provider_context_limit = selected["prompt"]["total_upper_bound_units"] - 1
    overflow = client.post(endpoint + "/context-budget", json=body).json()
    assert not overflow["can_start"] and overflow["excess_units"] == 1
    assert storage_snapshot(app) == before
    assert client.get(endpoint + "/" + failed["id"]).json()["error"] == failed["error"]
    other = client.post("/api/v1/matters", json={"title": "Other SYNTHETIC", "domain": "contracts"}).json()["id"]
    foreign = f'/api/v1/matters/{other}/analyses/{record["id"]}/suggestions/context-budget'
    assert client.post(foreign, json=body).status_code == 404
    assert client.post(endpoint + "/context-budget", json={**body, "evidence": []}).status_code == 422


def test_preview_is_available_without_provider_credentials_but_never_authorizes_a_call(workbench, monkeypatch):
    app, client, *_ = workbench
    record, endpoint = prepare(workbench, monkeypatch)
    app.state.settings.provider_api_key = ""
    monkeypatch.setattr(app.state.provider, "probe", lambda: pytest.fail("No probe without configuration"))
    response = client.post(endpoint + "/context-budget", json=request_body(record))
    assert response.status_code == 200
    value = response.json()
    assert value["fits"] and not value["configuration_ready"] and not value["can_start"]
