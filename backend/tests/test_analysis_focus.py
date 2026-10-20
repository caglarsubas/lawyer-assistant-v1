"""Synthetic only: explicit focus, immutable evidence, no model call or review transfer."""

import copy
import io
import json
from uuid import uuid4

import pytest
from docx import Document
from sqlalchemy import select
from test_analysis_context_budget import storage_snapshot
from test_analysis_reviews import review_request
from test_analysis_suggestions import finished, patch, prepare
from test_analysis_workbench import workbench as workbench_fixture

from app.analysis_proposals import prompt_measurement, proposal_messages
from app.db import Membership, Record


@pytest.fixture
def workbench(tmp_path, synthetic_analysis_workbench_seed):
    yield from workbench_fixture.__wrapped__(tmp_path, synthetic_analysis_workbench_seed)


def setup(workbench, monkeypatch):
    app, client, base, *_ = workbench
    parent, _ = prepare(workbench, monkeypatch, incomplete=False)
    body = {
        "expected_revision": parent["revision"],
        "version_id": parent["latest_version_id"],
        "request_id": uuid4().hex,
        "title": "SYNTHETIC odak incelemesi",
        "issue": "SYNTHETIC teslim koşulu?",
        "application_id": "a1",
        "alternative_ids": ["alt1"],
        "evidence": [
            {key: item[key] for key in ("evidence_id", "passage_sha256", "document_revision", "start", "end")}
            for item in parent["evidence"]
        ],
        "omission_note": "SYNTHETIC genel sonuç ve önceki gerekçe kapsam dışı; ayrıca incelenecek.",
        "acknowledge_partial": True,
    }
    return parent, body, base + "/analyses/" + parent["id"] + "/focus"


def preview_and_save(client, endpoint, body):
    response = client.post(endpoint + "/preview", json=body)
    assert response.status_code == 200, response.text
    value = response.json()
    saved_body = {**body, "context_preview_sha256": value["budget"]["preview_sha256"]}
    response = client.post(endpoint, json=saved_body)
    assert response.status_code == 201, response.text
    return value, response.json(), saved_body


def test_local_preview_and_save_preserve_parent_documents_history_and_exact_first_pass(
    workbench, monkeypatch
):
    app, client, base, *_ = workbench
    parent, body, endpoint = setup(workbench, monkeypatch)
    before = storage_snapshot(app)
    for name in ("probe", "suggest_analysis", "generate"):
        monkeypatch.setattr(
            app.state.provider, name, lambda *_a, **_k: pytest.fail("No inference in focus preparation")
        )
    body["evidence"][0]["start"] += 2
    assert client.post(endpoint + "/preview", json=body).status_code == 200
    assert storage_snapshot(app) == before
    value, child, saved_body = preview_and_save(client, endpoint, body)
    assert value["budget"]["prompt"] == prompt_measurement(proposal_messages(child))
    assert child["id"] != parent["id"] and child["version"] == 1
    assert child["review"]["effective_state"] == "unreviewed" and child["review"]["latest"] is None
    assert child["conclusion"]["requested_disposition"] == "withheld"
    assert child["rules"] == parent["rules"] and child["premises"] == parent["premises"]
    assert child["applications"][0]["assessments"] == parent["applications"][0]["assessments"]
    quote = child["evidence"][0]
    assert quote["text"] == parent["evidence"][0]["text"][2:]
    assert quote["passage_sha256"] == parent["evidence"][0]["passage_sha256"]
    assert child["focus_lineage"]["narrowed_ranges"][0]["start"] == quote["start"]
    after = storage_snapshot(app)
    assert all(after[0][ident] == item for ident, item in before[0].items() if ident != base.split("/")[-1])
    assert set(before[1]) <= set(after[1])
    assert client.post(endpoint, json=saved_body).json()["id"] == child["id"]
    assert storage_snapshot(app) == after
    assert client.post(endpoint, json={**saved_body, "title": "Changed SYNTHETIC request"}).status_code == 409
    # Saved focus uses the ordinary exact-budget and proposal pipeline, with scope retained.
    seen = []
    monkeypatch.setattr(
        app.state.provider,
        "suggest_analysis",
        lambda content, **_kw: (seen.append(content), json.dumps(patch()))[1],
    )
    suggestion = base + "/analyses/" + child["id"] + "/suggestions"
    request = {
        "expected_revision": child["revision"],
        "version_id": child["latest_version_id"],
        "request_id": uuid4().hex,
    }
    measured = client.post(suggestion + "/context-budget", json=request).json()
    assert measured["prompt"] == value["budget"]["prompt"]
    response = client.post(suggestion, json={**request, "context_preview_sha256": measured["preview_sha256"]})
    assert response.status_code == 202, response.text
    job = finished(client, suggestion, response.json()["id"])
    assert job["status"] == "completed", job
    assert job["iterations"][0]["prompt"] == measured["prompt"]
    assert seen[0]["focus_lineage"] == child["focus_lineage"]
    assert "focus_scope" in json.loads(proposal_messages(seen[0])[1]["content"])
    # Export and subsequent manual versions keep original scope history, never parent reviews.
    export = client.get(base + "/analyses/" + child["id"] + "/export")
    text = "\n".join(item.text for item in Document(io.BytesIO(export.content)).paragraphs)
    assert "ODAK ANALİZİ" in text and parent["latest_version_id"] in text
    from app.analysis_proposals import draft_input

    change = {
        **draft_input(child).model_dump(),
        "expected_revision": child["revision"],
        "change_note": "SYNTHETIC manual revision",
    }
    change["issue"] = "SYNTHETIC revised focus question"
    revision = client.post(base + "/analyses/" + child["id"] + "/versions", json=change)
    assert revision.status_code == 201, revision.text
    assert revision.json()["focus_lineage"] == child["focus_lineage"]


def test_overflow_preflight_has_no_writes_or_silent_truncation_and_exact_fit_saves(workbench, monkeypatch):
    app, client, *_ = workbench
    _, body, endpoint = setup(workbench, monkeypatch)
    first = client.post(endpoint + "/preview", json=body).json()
    size = first["budget"]["prompt"]["total_upper_bound_units"]
    before = storage_snapshot(app)
    app.state.settings.provider_context_limit = size - 1
    oversized = client.post(endpoint + "/preview", json=body)
    assert oversized.headers["cache-control"] == "no-store"
    assert oversized.json()["content"]["evidence"] == first["content"]["evidence"]
    assert oversized.json()["budget"]["excess_units"] == 1
    assert (
        client.post(
            endpoint, json={**body, "context_preview_sha256": oversized.json()["budget"]["preview_sha256"]}
        ).status_code
        == 422
    )
    assert client.post(endpoint, json=body).status_code == 409
    assert storage_snapshot(app) == before
    app.state.settings.provider_context_limit = size
    value, _, _ = preview_and_save(client, endpoint, body)
    assert value["budget"]["remaining_units"] == 0


def test_full_parent_can_overflow_while_explicit_focus_fits_without_changing_quotes(workbench, monkeypatch):
    app, client, base, payload, *_ = workbench
    _, body, _ = setup(workbench, monkeypatch)
    large = copy.deepcopy(payload)
    large["applications"][0]["rationale"] = "SYNTHETIC " + "x" * 3900
    large["conclusion"]["uncertainty"] = ["SYNTHETIC " + "x" * 3000 for _ in range(5)]
    parent = client.post(base + "/analyses", json=large).json()
    app.state.settings.provider_context_limit = 8192
    assert prompt_measurement(proposal_messages(parent))["total_upper_bound_units"] > 8192
    body.update(expected_revision=parent["revision"], version_id=parent["latest_version_id"])
    value, child, _ = preview_and_save(client, base + "/analyses/" + parent["id"] + "/focus", body)
    assert value["budget"]["fits"]
    assert child["evidence"] == parent["evidence"]
    assert child["focus_lineage"]["narrowed_ranges"] == []
    assert app.state.settings.provider_context_limit == 8192


def test_ai_origin_requires_fresh_contribution_review_and_public_dependencies_cannot_be_stripped(
    workbench, monkeypatch
):
    app, client, base, *_ = workbench
    parent, body, endpoint = setup(workbench, monkeypatch)
    # Test-only historic origin, not a review or real inference.
    with app.state.store.session() as session:
        for ident in (parent["id"], parent["latest_version_id"]):
            row = session.get(Record, ident)
            data = app.state.store.decode(row)
            content = data if ident == parent["id"] else data["content"]
            content["ai_assistance"] = {
                "job_id": "SYNTHETIC-prior",
                "source_version_id": "SYNTHETIC-prior-version",
                "passes": 1,
                "provider": {"model": "SYNTHETIC"},
            }
            app.state.store.update(row, data)
        session.commit()
        body["expected_revision"] = session.get(Record, parent["id"]).revision
    _, child, _ = preview_and_save(client, endpoint, body)
    assert child["focus_lineage"]["derived_ai"] and "ai_assistance" not in child
    context = client.get(
        base + "/analyses/" + child["id"] + "/reviews/context",
        params={"version_id": child["latest_version_id"]},
    ).json()
    assert context["ai_contribution_required"] and context["review"]["latest"] is None
    with app.state.store.session() as session:
        row = session.get(Record, parent["id"])
        data = app.state.store.decode(row)
        data["authority_contributions"] = [{"job_id": "SYNTHETIC-public"}]
        app.state.store.update(row, data)
        session.commit()
        body["expected_revision"] = row.revision
    before = storage_snapshot(app)
    assert client.post(endpoint + "/preview", json=body).status_code in {409, 422}
    assert storage_snapshot(app) == before


@pytest.mark.parametrize(
    "change",
    [
        "range",
        "revision",
        "foreign_evidence",
        "required_evidence",
        "application",
        "alternative",
        "duplicate",
        "acknowledgement",
    ],
)
def test_invalid_or_invented_scope_is_rejected_without_writes(workbench, monkeypatch, change):
    app, client, *_ = workbench
    _, body, endpoint = setup(workbench, monkeypatch)
    if change == "range":
        body["evidence"][0]["start"] = 0
    elif change == "revision":
        body["evidence"][0]["document_revision"] += 1
    elif change == "foreign_evidence":
        body["evidence"][0]["evidence_id"] = "FOREIGN"
    elif change == "required_evidence":
        body["evidence"] = []
    elif change == "application":
        body["application_id"] = "unknown"
    elif change == "alternative":
        body["alternative_ids"] = ["unknown"]
    elif change == "duplicate":
        body["evidence"] *= 2
    else:
        body["acknowledge_partial"] = False
    before = storage_snapshot(app)
    assert client.post(endpoint + "/preview", json=body).status_code in {409, 422}
    assert storage_snapshot(app) == before


@pytest.mark.parametrize("change", ["version", "review", "document", "model", "selection", "permission"])
def test_save_resolves_changed_context_and_permission_again(workbench, monkeypatch, change):
    app, client, base, payload, _, document_id, *_ = workbench
    parent, body, endpoint = setup(workbench, monkeypatch)
    value = client.post(endpoint + "/preview", json=body).json()
    if change == "version":
        response = client.post(
            base + "/analyses/" + parent["id"] + "/versions",
            json={
                **payload,
                "expected_revision": parent["revision"],
                "change_note": "SYNTHETIC revised parent",
            },
        )
        assert response.status_code == 201
    elif change == "review":
        reviews = base + "/analyses/" + parent["id"] + "/reviews"
        request, _ = review_request(client, reviews, parent)
        assert client.post(reviews, json=request).status_code == 201
    elif change == "model":
        app.state.settings.provider_model = "SYNTHETIC-changed"
    elif change == "selection":
        body["issue"] = "SYNTHETIC different focus"
    else:
        with app.state.store.session() as session:
            if change == "document":
                row = session.get(Record, document_id)
                app.state.store.update(row, app.state.store.decode(row))
            else:
                session.delete(
                    session.scalar(select(Membership).where(Membership.matter_id == base.split("/")[-1]))
                )
            session.commit()
    before = storage_snapshot(app)
    response = client.post(
        endpoint, json={**body, "context_preview_sha256": value["budget"]["preview_sha256"]}
    )
    assert response.status_code in {404, 409}, response.text
    assert storage_snapshot(app) == before


def test_explicit_omissions_are_counted_and_parent_review_is_not_transferred(workbench, monkeypatch):
    app, client, base, *_ = workbench
    parent, body, endpoint = setup(workbench, monkeypatch)
    reviews = base + "/analyses/" + parent["id"] + "/reviews"
    request, _ = review_request(client, reviews, parent)
    assert client.post(reviews, json=request).status_code == 201
    body["alternative_ids"] = []
    value, child, _ = preview_and_save(client, endpoint, body)
    assert child["focus_lineage"]["omitted"]["alternatives"] == ["alt1"]
    assert child["focus_lineage"]["parent_review_id"]
    assert child["review"]["effective_state"] == "unreviewed"
    assert value["content"]["focus_lineage"]["review_transferred"] is False
    payload = json.loads(proposal_messages(child)[1]["content"])
    assert payload["focus_scope"]["omitted_counts"]["alternatives"] == 1
    assert child["focus_lineage"]["parent_version_id"] not in json.dumps(payload)
    # Nested focus and a corrupted immutable origin both fail closed.
    child_endpoint = base + "/analyses/" + child["id"] + "/focus/preview"
    assert (
        client.post(
            child_endpoint,
            json={**body, "expected_revision": child["revision"], "version_id": child["latest_version_id"]},
        ).status_code
        == 422
    )
    with app.state.store.session() as session:
        version = session.get(Record, parent["latest_version_id"])
        saved = app.state.store.decode(version)
        saved["content"]["issue"] = "SYNTHETIC corrupted origin"
        app.state.store.update(version, saved)
        session.commit()
    records = client.get(base + "/analyses").json()
    assert next(item for item in records if item["id"] == child["id"])["freshness"]["status"] == "stale"
