"""Synthetic fixed-input human trials, not legal or model-benefit qualification."""

from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from test_analysis_authorities import mutate, payload
from test_analysis_comparisons import login
from test_authority_adjudications import reviewer
from test_authority_adjudications import saved as saved_adjudication
from test_authority_comparisons import revise, saved_comparison
from test_authority_findings import count, saved
from test_authority_findings import setup as findings_setup
from test_authority_findings import workbench as workbench_fixture

from app import authority_trials as trials
from app.db import Membership, Record, User

workbench = workbench_fixture


def setup(workbench, monkeypatch):
    app, client, *_ = workbench
    reviews, context, analysis, reader, permit = findings_setup(workbench, monkeypatch)
    review, _ = saved(client, reviews)
    reviewers = [reviewer(workbench, name) for name in ("reviewer", "reviewer2")]
    login(client)
    endpoint = reviews + "/" + review["id"] + "/trials"
    inputs = client.get(endpoint + "/registration-context")
    assert inputs.status_code == 200, inputs.text
    context_value = inputs.json()
    body = {
        "request_id": uuid4().hex,
        "context_sha256": context_value["context_sha256"],
        "title": "SYNTHETIC registered human revision",
        "question": "SYNTHETIC semantic uncertainty persists?",
        "sample_kind": "synthetic",
        "split_family_sha256": "a" * 64,
        "reviewer_ids": reviewers,
    }
    assert context_value["can_register"], context_value
    return endpoint, body, analysis, reader, permit, review, context


def register(workbench, monkeypatch):
    endpoint, body, analysis, reader, permit, review, context = setup(workbench, monkeypatch)
    response = workbench[1].post(endpoint, json=body)
    assert response.status_code == 201, response.text
    return endpoint, response.json(), analysis, reader, permit, review, context, body


def prepared(workbench, monkeypatch):
    endpoint, plan, analysis, reader, permit, review, context, registration = register(workbench, monkeypatch)
    candidate = revise(workbench, analysis)
    comparison_endpoint = endpoint.rsplit("/trials", 1)[0] + "/comparisons"
    comparison, _ = saved_comparison(workbench[1], comparison_endpoint)
    adjud_endpoint = comparison_endpoint + "/" + comparison["id"] + "/adjudications"
    observations = []
    for account in ("reviewer", "reviewer2"):
        login(workbench[1], account)
        observations.append(saved_adjudication(workbench[1], adjud_endpoint)[0])
    login(workbench[1])
    trial_endpoint = endpoint + "/" + plan["id"]
    selected = {"comparison_id": comparison["id"], "adjudication_ids": [row["id"] for row in observations]}
    preview = workbench[1].post(trial_endpoint + "/capture-context", json=selected)
    assert preview.status_code == 200, preview.text
    value = preview.json()
    body = {
        **selected,
        "request_id": uuid4().hex,
        "expected_basis_sha256": value["basis_sha256"],
        "expected_capture_id": value["expected_capture_id"],
        "note": "SYNTHETIC explicit unknown effort.",
        "arms": [
            {
                "arm": arm,
                "preparation_seconds": None,
                "verification_seconds": None,
                "correction_seconds": None,
            }
            for arm in ("original", "revised")
        ],
        "shared_setup_included": False,
        "verification_and_correction_included": False,
        "non_overlapping_active_time": False,
    }
    return trial_endpoint, body, plan, comparison, observations, permit, candidate, registration


def capture(client, endpoint, body):
    response = client.post(endpoint + "/captures", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_registration_precedes_revision_exact_frozen_inputs_and_unknowns(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, body, plan, comp, observations, _, candidate, _ = prepared(workbench, monkeypatch)
    source = payload(app, comp["id"])
    result = capture(client, endpoint, body)
    assert result["freshness"]["status"] == "current" and result["public_source_access"]
    assert not result["capture_complete"] and not result["snapshot"]["effort_accounted"]
    assert result["snapshot"]["basis"]["comparison"] == comp["snapshot"]
    assert [item["id"] for item in result["snapshot"]["basis"]["observations"]] == [
        item["id"] for item in sorted(observations, key=lambda item: item["reviewer_id"])
    ]
    assert payload(app, comp["id"]) == source
    assert client.get(base + "/analyses").json()[0]["latest_version_id"] == candidate["latest_version_id"]
    assert not plan["protocol"]["blind_review"]


def test_complete_means_presence_not_correctness_and_retains_disagreement(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, body, plan, comp, observations, *_ = prepared(workbench, monkeypatch)
    changed = observations[1]
    adjud_endpoint = endpoint.rsplit("/trials/", 1)[0] + "/comparisons/" + comp["id"] + "/adjudications"
    login(client, "reviewer2")
    from test_authority_adjudications import request

    fresh, _ = request(client, adjud_endpoint)
    fresh["observations"][0]["outcome"] = "unresolved"
    new, _ = saved_adjudication(client, adjud_endpoint, fresh)
    login(client)
    body["adjudication_ids"] = [observations[0]["id"], new["id"]]
    preview = client.post(
        endpoint + "/capture-context", json={k: body[k] for k in ("comparison_id", "adjudication_ids")}
    ).json()
    body.update(
        expected_basis_sha256=preview["basis_sha256"],
        shared_setup_included=True,
        verification_and_correction_included=True,
        non_overlapping_active_time=True,
        arms=[
            {"arm": arm, "preparation_seconds": 10, "verification_seconds": 20, "correction_seconds": 0}
            for arm in ("original", "revised")
        ],
    )
    result = capture(client, endpoint, body)
    assert result["capture_complete"]
    assert result["snapshot"]["disagreement"] == {"semantic_dimensions": 1, "finding_dimensions": 0}
    assert all(
        item["coverage"]["semantic"]["assessed"] == 0 for item in result["snapshot"]["basis"]["observations"]
    )
    assert (
        not result["qualification_granted"]
        and not result["benefit_established"]
        and not result["model_benchmark"]
    )
    assert (
        result["protocol"]["registration_before_revision"]
        and not result["protocol"]["registration_before_baseline"]
    )
    assert changed["snapshot"]["assessment"]["observations"][0]["outcome"] == "not_assessed"


@pytest.mark.parametrize("bad", ["after_revision", "wrong_basis", "same_reviewers", "real", "author", "role"])
def test_registration_rejects_retroactive_or_ineligible_assignments(workbench, monkeypatch, bad):
    app, client, *_ = workbench
    endpoint, body, analysis, *_ = setup(workbench, monkeypatch)
    if bad == "after_revision":
        revise(workbench, analysis)
    if bad == "wrong_basis":
        body["context_sha256"] = "0" * 64
    if bad == "same_reviewers":
        body["reviewer_ids"][1] = body["reviewer_ids"][0]
    if bad == "real":
        body["sample_kind"] = "real"
    if bad == "author":
        with app.state.store.session() as session:
            body["reviewer_ids"][0] = session.scalar(select(User).where(User.username == "demo")).id
    if bad == "role":
        with app.state.store.session() as session:
            session.get(User, body["reviewer_ids"][0]).role = "assistant"
            session.commit()
    assert client.post(endpoint, json=body).status_code in {409, 422}
    assert count(app, trials.KIND) == 0


@pytest.mark.parametrize(
    "bad",
    ["bool", "fraction", "negative", "partial", "duplicate", "extra", "note", "foreign", "basis", "head"],
)
def test_capture_rejects_invalid_bounded_or_foreign_input_without_partial_write(workbench, monkeypatch, bad):
    app, client, *_ = workbench
    endpoint, body, *_ = prepared(workbench, monkeypatch)
    if bad == "bool":
        body["arms"][0]["preparation_seconds"] = True
    if bad == "fraction":
        body["arms"][0]["preparation_seconds"] = 1.5
    if bad == "negative":
        body["arms"][0]["preparation_seconds"] = -1
    if bad == "partial":
        body["arms"].pop()
    if bad == "duplicate":
        body["adjudication_ids"] = [body["adjudication_ids"][0]] * 2
    if bad == "extra":
        body["provider"] = "remote"
    if bad == "note":
        body["note"] = "   "
    if bad == "foreign":
        body["comparison_id"] = "foreign"
    if bad == "basis":
        body["expected_basis_sha256"] = "b" * 64
    if bad == "head":
        body["expected_capture_id"] = "foreign"
    assert client.post(endpoint + "/captures", json=body).status_code in {404, 409, 422}
    assert count(app, trials.CAPTURE) == count(app, trials.HEAD) == 0


def test_retry_head_history_and_encrypted_source_preservation(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, body, plan, comp, *_ = prepared(workbench, monkeypatch)
    ciphertext = payload(app, comp["id"])
    result = capture(client, endpoint, body)
    assert capture(client, endpoint, body)["capture_id"] == result["capture_id"]
    assert (
        client.post(endpoint + "/captures", json={**body, "note": "SYNTHETIC conflicting retry"}).status_code
        == 409
    )
    new = {**body, "request_id": uuid4().hex, "expected_capture_id": result["capture_id"]}
    second = capture(client, endpoint, new)
    old = client.get(endpoint + "?capture_id=" + result["capture_id"]).json()
    assert old["freshness"]["status"] == "stale" and old["snapshot"] == result["snapshot"]
    assert second["snapshot"]["sequence"] == 2
    assert len(client.get(endpoint + "/captures").json()) == 2
    assert payload(app, comp["id"]) == ciphertext
    assert "SYNTHETIC" not in payload(app, result["capture_id"])
    assert client.get(base + "/analyses").json()[0]["version"] == 2


@pytest.mark.parametrize(
    "change", ["new_adjudication", "private_quote", "role", "recipe", "new_draft", "public_product"]
)
def test_dependency_changes_retain_stale_evidence_and_close_export(workbench, monkeypatch, change):
    app, client, base, *_ = workbench
    endpoint, body, plan, comp, observed, _, candidate, _ = prepared(workbench, monkeypatch)
    result = capture(client, endpoint, body)
    if change == "new_adjudication":
        login(client, "reviewer")
        saved_adjudication(
            client, endpoint.rsplit("/trials/", 1)[0] + "/comparisons/" + comp["id"] + "/adjudications"
        )
        login(client)
    if change == "private_quote":
        doc = candidate["evidence"][0]["document_id"]
        mutate(app, doc, lambda data: data["passages"][0].update(text="SYNTHETIC changed quotation"))
    if change == "role":
        with app.state.store.session() as session:
            session.get(User, plan["protocol"]["reviewer_ids"][0]).role = "assistant"
            session.commit()
    if change == "recipe":
        monkeypatch.setattr(trials, "INPUT_KEYS", (*trials.INPUT_KEYS, "title"))
    if change == "new_draft":
        revise(workbench, candidate)
    if change == "public_product":
        # A successor authority finding after returning to the baseline cannot be silently substituted.
        mutate(
            app,
            plan["protocol"]["basis"]["review"]["context_snapshot"]["manifest"]["product_id"],
            lambda data: data.update(extra_dependency="SYNTHETIC changed product"),
        )
    view = client.get(endpoint).json()
    assert view["freshness"]["status"] == "stale" and view["snapshot"] == result["snapshot"]
    assert not view["capture_complete"]
    assert client.get(endpoint + "/export").status_code == 409


def test_public_denial_withholds_all_notes_protocol_and_exports(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, body, _, _, _, permit, *_ = prepared(workbench, monkeypatch)
    capture(client, endpoint, body)
    permit.active = False
    value = client.get(endpoint).json()
    assert value["freshness"]["status"] == "withheld"
    assert value["protocol"] is None and value["snapshot"] is None
    assert "SYNTHETIC" not in str(value)
    assert client.get(endpoint + "/export").status_code == 409
    assert all("title" not in row for row in client.get(endpoint.rsplit("/", 1)[0]).json())


def test_only_operator_can_capture_and_membership_is_required_for_reads(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, body, plan, *_ = prepared(workbench, monkeypatch)
    login(client, "reviewer")
    assert client.post(endpoint + "/captures", json=body).status_code == 403
    with app.state.store.session() as session:
        session.delete(
            session.get(Membership, (plan["protocol"]["route"][0], plan["protocol"]["reviewer_ids"][0]))
        )
        session.commit()
    assert client.get(endpoint).status_code == 404


def test_late_commit_failure_remains_pending_replay_never_admits(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, body, *_ = prepared(workbench, monkeypatch)
    original = app.state.graph.release.current_guard

    @contextmanager
    def late():
        with original() as info:
            yield info
            if count(app, trials.CAPTURE):
                raise HTTPException(409, "SYNTHETIC post-commit rejection")

    monkeypatch.setattr(app.state.graph.release, "current_guard", late)
    value = client.post(endpoint + "/captures", json=body)
    assert value.status_code == 409 and value.json()["outcome"] == "committed_needs_revalidation"
    monkeypatch.setattr(app.state.graph.release, "current_guard", original)
    replay = client.post(endpoint + "/captures", json=body).json()
    assert replay["freshness"]["status"] == "withheld" and replay["snapshot"] is None
    assert count(app, trials.CAPTURE) == 1


def test_precommit_change_and_packet_limit_roll_back_atomically(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, body, *_ = prepared(workbench, monkeypatch)
    original = trials.capture_basis
    calls = 0

    def changed(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = original(*args, **kwargs)
        if calls == 2:
            result["basis_sha256"] = "0" * 64
        return result

    monkeypatch.setattr(trials, "capture_basis", changed)
    assert client.post(endpoint + "/captures", json=body).status_code == 409
    assert count(app, trials.CAPTURE) == count(app, trials.HEAD) == 0
    monkeypatch.setattr(trials, "capture_basis", original)
    monkeypatch.setattr(trials, "MAX_BYTES", 1)
    assert client.post(endpoint + "/captures", json=body).status_code == 409
    assert count(app, trials.CAPTURE) == count(app, trials.HEAD) == 0


def test_export_partial_capture_rechecks_after_serialization(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, body, _, _, _, permit, *_ = prepared(workbench, monkeypatch)
    result = capture(client, endpoint, body)
    response = client.get(endpoint + "/export")
    assert response.status_code == 200 and not response.json()["capture_complete"]
    assert response.json()["capture_sha256"] == result["capture_sha256"]
    assert response.headers["cache-control"] == "no-store"
    original = trials.canonical

    def serialize(value):
        rendered = original(value)
        if isinstance(value, dict) and value.get("capture_sha256") == result["capture_sha256"]:
            permit.active = False
        return rendered

    monkeypatch.setattr(trials, "canonical", serialize)
    assert client.get(endpoint + "/export").status_code == 409


@pytest.mark.parametrize("field", ["issue", "posture", "event_date", "premises"])
def test_changed_case_inputs_need_a_new_registration(workbench, monkeypatch, field):
    import copy

    endpoint, plan, analysis, *_ = register(workbench, monkeypatch)
    _, client, base, original, *_ = workbench
    changed = copy.deepcopy(original)
    changed[field] = "2025-01-01" if field == "event_date" else "SYNTHETIC different input"
    if field == "premises":
        changed[field] = [{"id": "p1", "kind": "assumption", "text": "SYNTHETIC new premise"}]
    response = client.post(
        base + "/analyses/" + analysis["id"] + "/versions",
        json={**changed, "expected_revision": analysis["revision"], "change_note": "SYNTHETIC changed case"},
    )
    assert response.status_code == 201, response.text
    comp, _ = saved_comparison(client, endpoint.rsplit("/trials", 1)[0] + "/comparisons")
    preview = client.post(
        endpoint + "/" + plan["id"] + "/capture-context",
        json={"comparison_id": comp["id"], "adjudication_ids": []},
    )
    assert preview.status_code == 409


def test_pre_registration_candidate_and_capture_cap_are_not_silently_accepted(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, body, plan, comp, _, _, candidate, _ = prepared(workbench, monkeypatch)
    with app.state.store.session() as session:
        row = session.get(Record, candidate["latest_version_id"])
        old = row.created_at
        row.created_at = "2020-01-01T00:00:00+00:00"
        session.commit()
    assert client.post(endpoint + "/captures", json=body).status_code == 409
    with app.state.store.session() as session:
        session.get(Record, candidate["latest_version_id"]).created_at = old
        session.commit()
    monkeypatch.setattr(trials, "MAX_RECORDS", 0)
    assert client.post(endpoint + "/captures", json=body).status_code == 409
    assert count(app, trials.CAPTURE) == 0


def test_newer_reviewer_observation_can_be_recaptured_under_same_current_protocol(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, body, _, comp, observed, *_ = prepared(workbench, monkeypatch)
    first = capture(client, endpoint, body)
    login(client, "reviewer")
    new, _ = saved_adjudication(
        client, endpoint.rsplit("/trials/", 1)[0] + "/comparisons/" + comp["id"] + "/adjudications"
    )
    login(client)
    stale = client.get(endpoint).json()
    assert stale["freshness"]["status"] == "stale" and stale["can_record"]
    selected = {"comparison_id": comp["id"], "adjudication_ids": [new["id"], observed[1]["id"]]}
    preview = client.post(endpoint + "/capture-context", json=selected).json()
    second = capture(
        client,
        endpoint,
        {
            **body,
            **selected,
            "request_id": uuid4().hex,
            "expected_basis_sha256": preview["basis_sha256"],
            "expected_capture_id": first["capture_id"],
        },
    )
    assert second["freshness"]["status"] == "current"
    assert client.get(endpoint + "/export").status_code == 200


def test_registration_retry_and_integrity_and_foreign_routes(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, plan, _, _, _, _, _, body = register(workbench, monkeypatch)
    repeat = client.post(endpoint, json=body)
    assert repeat.status_code == 201 and repeat.json()["id"] == plan["id"]
    assert (
        client.post(endpoint, json={**body, "question": "SYNTHETIC conflicting question"}).status_code == 409
    )
    assert count(app, trials.KIND) == 1
    foreign = endpoint.replace(plan["protocol"]["route"][1], "foreign-analysis")
    assert client.get(foreign + "/" + plan["id"]).status_code == 404
    mutate(app, plan["id"], lambda data: data.update(question="SYNTHETIC tampered sealed protocol"))
    assert client.get(endpoint + "/" + plan["id"]).status_code == 409
