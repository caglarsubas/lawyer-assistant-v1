"""Invented local-model trials and fixture accounts; no legal or model benefit claim."""

from contextlib import contextmanager
from threading import Event
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session
from test_analysis_authorities import mutate, payload
from test_analysis_comparisons import effort, login
from test_authority_findings import count
from test_authority_model_trials import observation, register, run
from test_authority_model_trials import workbench as workbench_fixture
from test_firm_admin import PASSWORD
from test_firm_admin import login as authority_login

from app import authority_model_cohorts as cohorts
from app.db import Record, User

workbench = workbench_fixture


def pair(workbench, monkeypatch, *, complete=False, renewal=False, incompatible=False):
    app, client, base, *_ = workbench
    path, first, body, calls, permit, reader, record = register(workbench, monkeypatch, renewal=renewal)
    second = {
        **body,
        "request_id": uuid4().hex,
        "title": "SYNTHETIC second model trial",
        "split_family_sha256": "b" * 64,
    }
    if incompatible:
        second["rubric_text"] = "SYNTHETIC different declared review rubric"
    result = client.post(path, json=second)
    assert result.status_code == 201, result.text
    plans = [first, result.json()]
    if complete:
        for plan in plans:
            run(client, path, plan)
        for index in range(2):
            login(client, f"SYNTHETIC-model-reviewer-{index}")
            for plan in plans:
                detail = path + "/" + plan["id"]
                value = client.get(detail).json()
                response = client.post(
                    detail + "/observations",
                    json=observation(value, outcome="unresolved" if index == 0 else "not_assessed"),
                )
                assert response.status_code == 201, response.text
        if renewal:
            authority_login(client, "synthetic-renewal-lawyer", PASSWORD)
        else:
            login(client)
        for plan in plans:
            detail = path + "/" + plan["id"]
            value = client.get(detail).json()
            response = client.post(
                detail + "/effort", json={**effort(value), "active_phases_nonoverlapping": True}
            )
            assert response.status_code == 201, response.text
    spec = {
        "title": "SYNTHETIC confidential model group",
        "purpose": "SYNTHETIC inventory selected gaps only",
        "selections": [{"trial_id": plan["id"]} for plan in plans],
        "reserved_family_sha256": ["a" * 64],
    }
    return base + "/authority-model-cohorts", spec, path, plans, calls, permit, reader, record


def freeze(client, path, spec):
    preview = client.post(path + "/preview", json=spec)
    assert preview.status_code == 200, preview.text
    body = {**spec, "expected_preview_sha256": preview.json()["preview_sha256"], "request_id": uuid4().hex}
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


@pytest.mark.parametrize("renewal", [False, True])
def test_freezes_both_arms_original_or_renewal_with_unknowns_overlap_and_no_new_calls(
    workbench, monkeypatch, renewal
):
    app, client, base, *_ = workbench
    path, spec, trial_path, plans, calls, *_ = pair(workbench, monkeypatch, complete=True, renewal=renewal)
    originals = [payload(app, plan["id"]) for plan in plans]
    before_calls = len(calls)
    value, body = freeze(client, path, spec)
    assert value["freshness"]["status"] == "current" and value["public_source_access"]
    report = value["manifest"]["reconciliation"]
    assert report["counts"]["selected_records"] == report["counts"]["current_reviewer_pairs"] == 2
    assert report["counts"]["profile_groups"] == 1 and report["counts"]["complete_capture_records"] == 2
    assert (
        report["counts"]["accounted_effort_records"]
        == report["counts"]["records_with_outcome_differences"]
        == 2
    )
    assert report["counts"]["records_with_unknown_observations"] == 2
    assert len(report["duplicate_inputs"]) == len(report["repeated_versions"]) == 1
    assert len(report["cross_family_private_sources"]) == len(report["repeated_public_passages"]) == 1
    assert report["reserved_overlaps"] == ["a" * 64]
    for row in report["rows"]:
        for arm in row["arms"].values():
            assert arm["unknown_semantic_observations"] == arm["semantic_observation_slots"] == 12
            assert arm["unknown_finding_observations"] == arm["finding_observation_slots"] == 12
            assert arm["active_effort_accounted"] and arm["adverse_recall"] is None
            assert arm["semantic"][0]["outcome_difference"] is True
            assert arm["gpu_compute_seconds"] is None and arm["preparation_time_gain"] is None
    assert not report["qualification_granted"] and not report["benefit_established"]
    assert client.post(path, json=body).json()["id"] == value["id"]
    assert count(app, cohorts.KIND) == count(app, cohorts.ADMISSION) == 1
    assert [payload(app, plan["id"]) for plan in plans] == originals and len(calls) == before_calls
    exported = client.get(path + "/" + value["id"] + "/export")
    assert exported.status_code == 200 and exported.json()["manifest"] == value["manifest"]
    assert (
        exported.headers["cache-control"] == "no-store"
        and exported.headers["x-content-type-options"] == "nosniff"
    )
    erasure = client.post(base + "/erasure-plan")
    if renewal:
        assert erasure.status_code in {403, 404}  # The replacement lawyer has no erasure grant.
    else:
        assert {"id": value["id"], "kind": cohorts.KIND} in erasure.json()["records"]
    assert client.get(trial_path + "/" + plans[0]["id"]).json()["capture_complete"]


def test_missing_runs_separate_profiles_and_metadata_without_quoted_titles(workbench, monkeypatch):
    _, client, *_ = workbench
    path, spec, _, _, calls, *_ = pair(workbench, monkeypatch, incompatible=True)
    value, _ = freeze(client, path, spec)
    report = value["manifest"]["reconciliation"]
    assert report["counts"]["profile_groups"] == 2 and report["counts"]["captures_present"] == 0
    for row in report["rows"]:
        assert row["outcome_difference_count"] is None and row["current_reviewer_count"] == 0
        assert all(
            item["outcome_difference"] is None for arm in row["arms"].values() for item in arm["semantic"]
        )
        assert all(arm["active_effort"] is None for arm in row["arms"].values())
    candidates = client.get(path + "/candidates?limit=1").json()
    assert len(candidates) == len(client.get(path + "/candidates?limit=1&offset=1").json()) == 1
    assert set(candidates[0]) == {"trial_id", "analysis_id", "registered_at", "admission_complete"}
    assert set(client.get(path).json()[0]) == {"id", "registered_at"}
    assert not calls


@pytest.mark.parametrize("change", ["private", "reviewer", "model", "recipe", "pending"])
def test_changed_inputs_stale_or_withhold_snapshot_and_close_export(workbench, monkeypatch, change):
    app, client, *_ = workbench
    path, spec, _, plans, *_ = pair(workbench, monkeypatch)
    value, _ = freeze(client, path, spec)
    immutable = payload(app, value["id"])
    if change == "private":
        mutate(app, workbench[4]["id"], lambda data: data.update(text="SYNTHETIC changed fact"))
    elif change == "reviewer":
        with app.state.store.session() as session:
            user = session.get(User, plans[0]["protocol"]["reviewer_ids"][0])
            user.active = False
            session.commit()
    elif change == "model":
        monkeypatch.setattr(app.state.settings, "provider_model", "SYNTHETIC changed pinned model")
    elif change == "recipe":
        monkeypatch.setattr(cohorts, "RECIPE", "SYNTHETIC next unsupported inventory recipe")
    else:
        with app.state.store.session() as session:
            row = session.get(Record, cohorts.trials._proof_id(plans[0]["id"]))
            app.state.store.update(row, {**app.state.store.decode(row), "completed": False})
            session.commit()
    detail = client.get(path + "/" + value["id"])
    assert detail.status_code == 200, detail.text
    assert detail.json()["freshness"]["status"] == ("withheld" if change == "pending" else "stale")
    assert client.get(path + "/" + value["id"] + "/export").status_code == 409
    assert payload(app, value["id"]) == immutable
    if change == "pending":
        assert detail.json()["manifest"] is None and "SYNTHETIC confidential model group" not in detail.text


@pytest.mark.parametrize("changed", ["run", "observation", "effort"])
def test_new_execution_or_human_event_invalidates_the_frozen_capture(workbench, monkeypatch, changed):
    _, client, *_ = workbench
    path, spec, trial_path, plans, *_ = pair(workbench, monkeypatch, complete=changed != "run")
    value, _ = freeze(client, path, spec)
    detail = trial_path + "/" + plans[0]["id"]
    if changed == "run":
        run(client, trial_path, plans[0])
    elif changed == "observation":
        login(client, "SYNTHETIC-model-reviewer-0")
        current = client.get(detail).json()
        assert client.post(detail + "/observations", json=observation(current)).status_code == 201
        login(client)
    else:
        current = client.get(detail).json()
        assert (
            client.post(
                detail + "/effort", json={**effort(current), "active_phases_nonoverlapping": True}
            ).status_code
            == 201
        )
    assert client.get(path + "/" + value["id"]).json()["freshness"]["status"] == "stale"
    assert client.get(path + "/" + value["id"] + "/export").status_code == 409
    refreshed, _ = freeze(client, path, spec)
    assert refreshed["id"] != value["id"] and refreshed["freshness"]["status"] == "current"


@pytest.mark.parametrize("failure", ["rights", "grant", "private"])
def test_export_checks_after_serialization_and_discards_bytes(workbench, monkeypatch, failure):
    app, client, *_ = workbench
    path, spec, _, _, _, permit, *_ = pair(workbench, monkeypatch)
    value, _ = freeze(client, path, spec)
    original = cohorts.canonical
    armed = [True]

    def altered(data):
        result = original(data)
        if armed[0] and isinstance(data, dict) and data.get("id") == value["id"] and data.get("manifest"):
            armed[0] = False
            if failure == "rights":
                permit.active = False
            elif failure == "private":
                mutate(
                    app, workbench[4]["id"], lambda body: body.update(text="SYNTHETIC changed during export")
                )
            else:
                with app.state.store.session() as session:
                    user = session.get(User, value["owner_id"])
                    user.active = False
                    session.commit()
        return result

    monkeypatch.setattr(cohorts, "canonical", altered)
    response = client.get(path + "/" + value["id"] + "/export")
    assert response.status_code in {401, 403, 404, 409}
    assert "SYNTHETIC confidential model group" not in response.text


def test_pending_after_committed_guard_failure_cannot_be_admitted_by_retry(workbench, monkeypatch):
    app, client, *_ = workbench
    path, spec, _, _, _, permit, reader, _ = pair(workbench, monkeypatch)
    preview = client.post(path + "/preview", json=spec).json()
    body = {**spec, "request_id": uuid4().hex, "expected_preview_sha256": preview["preview_sha256"]}
    armed = Event()
    original_commit = Session.commit
    original_guard = permit.guard
    original_add = app.state.store.add

    def added(session, kind, *args, **kwargs):
        result = original_add(session, kind, *args, **kwargs)
        if kind == cohorts.KIND:
            session.info["cohort_commit_injected_denial"] = True
        return result

    def committed(session):
        result = original_commit(session)
        if session.info.pop("cohort_commit_injected_denial", False):
            armed.set()
        return result

    @contextmanager
    def guard(*args, **kwargs):
        with original_guard(*args, **kwargs) as proof:
            yield proof
        if armed.is_set():
            raise HTTPException(409, "SYNTHETIC late source denial")

    monkeypatch.setattr(Session, "commit", committed)
    monkeypatch.setattr(app.state.store, "add", added)
    monkeypatch.setattr(reader, "current_guard", guard)
    response = client.post(path, json=body)
    assert response.status_code == 409 and response.json()["outcome"] == "committed_needs_revalidation"
    ident = response.json()["id"]
    armed.clear()
    assert count(app, cohorts.KIND) == count(app, cohorts.ADMISSION) == 1
    assert client.get(path + "/" + ident).json()["manifest"] is None
    assert client.post(path, json=body).json()["manifest"] is None
    with app.state.store.session() as session:
        assert not app.state.store.decode(session.get(Record, cohorts._admission_id(ident)))[
            "publication_guard_completed"
        ]


def test_before_commit_changed_fact_rolls_back_cohort_admission_and_audit(workbench, monkeypatch):
    app, client, *_ = workbench
    path, spec, *_ = pair(workbench, monkeypatch)
    preview = client.post(path + "/preview", json=spec).json()
    original = cohorts._audit

    def changed(session, *args):
        original(session, *args)
        row = session.get(Record, workbench[4]["id"])
        app.state.store.update(
            row, {**app.state.store.decode(row), "text": "SYNTHETIC concurrent fact change"}
        )

    monkeypatch.setattr(cohorts, "_audit", changed)
    body = {**spec, "request_id": uuid4().hex, "expected_preview_sha256": preview["preview_sha256"]}
    assert client.post(path, json=body).status_code == 409
    assert count(app, cohorts.KIND) == count(app, cohorts.ADMISSION) == 0


def test_invalid_selection_receipts_and_budget_are_fail_closed(workbench, monkeypatch):
    app, client, *_ = workbench
    path, spec, *_ = pair(workbench, monkeypatch)
    for changed in (
        {**spec, "selections": spec["selections"][:1]},
        {**spec, "selections": spec["selections"][:1] * 2},
        {**spec, "pasted_captures": []},
        {**spec, "purpose": "   "},
        {**spec, "reserved_family_sha256": ["invalid"]},
        {**spec, "selections": [{"trial_id": "amt-" + "f" * 20 + "-" + "e" * 32}, spec["selections"][0]]},
    ):
        assert client.post(path + "/preview", json=changed).status_code in {404, 422}
    value, body = freeze(client, path, spec)
    assert client.post(path, json={**body, "purpose": "SYNTHETIC nonce conflict"}).status_code == 409
    monkeypatch.setattr(cohorts, "MAX_BYTES", 1024)
    assert client.post(path + "/preview", json=spec).status_code == 409
    assert count(app, cohorts.KIND) == count(app, cohorts.ADMISSION) == 1
    with app.state.store.session() as session:
        assert app.state.store.decode(session.get(Record, value["id"]))["immutable"]


def test_temporary_source_denial_withholds_all_group_text_and_keeps_metadata(workbench, monkeypatch):
    app, client, *_ = workbench
    path, spec, _, _, _, permit, *_ = pair(workbench, monkeypatch)
    value, _ = freeze(client, path, spec)
    original = payload(app, value["id"])
    permit.active = False
    hidden = client.get(path + "/" + value["id"])
    assert hidden.status_code == 200 and hidden.json()["manifest"] is None
    assert "SYNTHETIC confidential model group" not in hidden.text
    assert client.get(path + "/candidates").status_code == 200  # IDs only; no public join.
    assert client.get(path + "/" + value["id"] + "/export").status_code == 409
    permit.active = True
    restored = client.get(path + "/" + value["id"]).json()
    assert restored["freshness"]["status"] == "current" and restored["manifest"] == value["manifest"]
    assert payload(app, value["id"]) == original


def test_cross_workspace_selection_fails_before_any_public_guard(workbench, monkeypatch):
    app, client, base, *_ = workbench
    path, spec, _, plans, *_ = pair(workbench, monkeypatch)
    with app.state.store.session() as session:
        user = session.get(User, plans[0]["protocol"]["registered_by"])
        other = app.state.store.add(session, "matter", user, {"title": "SYNTHETIC other workspace"})
        foreign = app.state.store.add(
            session,
            cohorts.trials.KIND,
            user,
            plans[0]["protocol"],
            other.id,
            record_id="amt-" + "f" * 20 + "-" + "e" * 32,
        )
        session.commit()
    entered = []
    original = cohorts.proposals.scope

    @contextmanager
    def watched(*args, **kwargs):
        entered.append(True)
        with original(*args, **kwargs) as value:
            yield value

    monkeypatch.setattr(cohorts.proposals, "scope", watched)
    response = client.post(
        path + "/preview", json={**spec, "selections": [spec["selections"][0], {"trial_id": foreign.id}]}
    )
    assert response.status_code in {403, 404} and not entered
    assert count(app, cohorts.KIND) == 0
    assert base.split("/")[-1] != other.id
