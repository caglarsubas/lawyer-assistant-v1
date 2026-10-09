"""Invented confidential inventories; no Turkish legal or benefit qualification."""

import copy
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from test_analysis_authorities import mutate, payload
from test_analysis_comparisons import login
from test_authority_adjudications import saved as saved_adjudication
from test_authority_comparisons import revise, saved_comparison
from test_authority_findings import count
from test_authority_trials import capture, setup
from test_authority_trials import workbench as workbench_fixture

from app import authority_trial_cohorts as cohorts
from app import authority_trials as trials
from app.db import Membership, Record, User

workbench = workbench_fixture


def pair(workbench, monkeypatch, *, complete=True):
    app, client, base, *_ = workbench
    endpoint, registration, analysis, reader, permit, *_ = setup(workbench, monkeypatch)
    plans = []
    for index in range(2):
        body = {
            **registration,
            "request_id": uuid4().hex,
            "title": f"SYNTHETIC human trial {index}",
            "split_family_sha256": str(index + 1) * 64,
        }
        response = client.post(endpoint, json=body)
        assert response.status_code == 201, response.text
        plans.append(response.json())
    if complete:
        revise(workbench, analysis)
        comp_endpoint = endpoint.rsplit("/trials", 1)[0] + "/comparisons"
        comp, _ = saved_comparison(client, comp_endpoint)
        observations = []
        for name in ("reviewer", "reviewer2"):
            login(client, name)
            observations.append(
                saved_adjudication(client, comp_endpoint + "/" + comp["id"] + "/adjudications")[0]
            )
        login(client)
        for plan in plans:
            selected = {
                "comparison_id": comp["id"],
                "adjudication_ids": [item["id"] for item in observations],
            }
            detail = endpoint + "/" + plan["id"]
            preview = client.post(detail + "/capture-context", json=selected).json()
            capture(
                client,
                detail,
                {
                    **selected,
                    "request_id": uuid4().hex,
                    "expected_basis_sha256": preview["basis_sha256"],
                    "expected_capture_id": None,
                    "note": "SYNTHETIC unknown active effort",
                    "arms": [
                        {
                            "arm": arm,
                            "preparation_seconds": None,
                            "verification_seconds": None,
                            "correction_seconds": 0,
                        }
                        for arm in ("original", "revised")
                    ],
                    "shared_setup_included": False,
                    "verification_and_correction_included": False,
                    "non_overlapping_active_time": False,
                },
            )
    spec = {
        "title": "SYNTHETIC confidential trial group",
        "purpose": "SYNTHETIC assess declared gaps only",
        "selections": [{"trial_id": item["id"]} for item in plans],
        "reserved_family_sha256": ["1" * 64],
    }
    return base + "/authority-trial-cohorts", spec, endpoint, plans, permit


def freeze(client, endpoint, spec):
    preview = client.post(endpoint + "/preview", json=spec)
    assert preview.status_code == 200, preview.text
    body = {**spec, "expected_preview_sha256": preview.json()["preview_sha256"], "request_id": uuid4().hex}
    result = client.post(endpoint, json=body)
    assert result.status_code == 201, result.text
    return result.json(), body


def test_freezes_explicit_human_captures_overlap_unknowns_and_no_inference(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, spec, trial_endpoint, plans, *_ = pair(workbench, monkeypatch)
    originals = [payload(app, item["id"]) for item in plans]
    view, body = freeze(client, endpoint, spec)
    assert view["freshness"]["status"] == "current" and view["public_source_access"]
    report = view["manifest"]["reconciliation"]
    assert report["counts"] == {
        "selected_records": 2,
        "profile_groups": 1,
        "declared_families": 2,
        "current_source_records": 2,
        "captures_present": 2,
        "complete_capture_records": 0,
        "current_reviewer_pairs": 2,
        "accounted_effort_records": 0,
        "records_with_outcome_differences": 0,
        "records_with_unknown_observations": 2,
    }
    assert len(report["duplicate_inputs"]) == len(report["repeated_versions"]) == 1
    assert len(report["cross_family_private_sources"]) == len(report["repeated_public_passages"]) == 1
    assert report["reserved_overlaps"] == ["1" * 64]
    for row in report["rows"]:
        assert row["unknown_semantic_observations"] == row["semantic_observation_slots"] == 12
        assert row["unknown_finding_observations"] == row["finding_observation_slots"] == 12
        assert row["recorded_effort"]["arms"][0]["correction_seconds"] == 0
        assert row["recorded_effort"]["arms"][0]["preparation_seconds"] is None
    assert report["preparation_time_gain"] is None and not report["benefit_established"]
    assert not report["model_benchmark"] and not report["held_out_qualified"]
    assert client.post(endpoint, json=body).json()["id"] == view["id"]
    assert count(app, cohorts.KIND) == count(app, cohorts.ADMISSION) == 1
    assert [payload(app, item["id"]) for item in plans] == originals
    assert client.get(endpoint + "/candidates?limit=1").json()[0]["capture_present"]
    assert len(client.get(endpoint + "/candidates?limit=1&offset=1").json()) == 1
    listed = client.get(endpoint).json()
    assert len(listed) == 1 and "title" not in listed[0]
    exported = client.get(endpoint + "/" + view["id"] + "/export")
    assert exported.status_code == 200 and exported.json()["manifest"] == view["manifest"]
    assert (
        exported.headers["cache-control"] == "no-store"
        and exported.headers["x-content-type-options"] == "nosniff"
    )
    assert {"id": view["id"], "kind": cohorts.KIND} in client.post(base + "/erasure-plan").json()["records"]


def test_missing_captures_have_unknown_pairs_and_explicit_denominators(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, spec, *_ = pair(workbench, monkeypatch, complete=False)
    result, _ = freeze(client, endpoint, spec)
    report = result["manifest"]["reconciliation"]
    assert report["counts"]["captures_present"] == report["counts"]["current_reviewer_pairs"] == 0
    for row in report["rows"]:
        assert row["outcome_difference_count"] is None and row["recorded_effort"] is None
        assert all(item["outcome_difference"] is None for item in row["semantic"])


@pytest.mark.parametrize(
    "bad", ["one", "duplicate", "too_many", "foreign", "extra", "space", "family", "reserved_duplicate"]
)
def test_rejects_bad_or_foreign_selections_without_writes(workbench, monkeypatch, bad):
    app, client, *_ = workbench
    endpoint, spec, *_ = pair(workbench, monkeypatch, complete=False)
    if bad == "one":
        spec["selections"].pop()
    if bad == "duplicate":
        spec["selections"][1] = spec["selections"][0]
    if bad == "too_many":
        spec["selections"] *= 7
    if bad == "foreign":
        spec["selections"][1]["trial_id"] = "atr-" + "f" * 24 + "-" + "e" * 32
    if bad == "extra":
        spec["captures"] = ["untrusted pasted JSON"]
    if bad == "space":
        spec["purpose"] = "   "
    if bad == "family":
        spec["reserved_family_sha256"] = ["not a hash"]
    if bad == "reserved_duplicate":
        spec["reserved_family_sha256"] *= 2
    assert client.post(endpoint + "/preview", json=spec).status_code in {404, 422}
    assert count(app, cohorts.KIND) == 0


@pytest.mark.parametrize("change", ["private", "reviewer", "recipe", "head", "missing", "scope"])
def test_changes_preserve_snapshot_but_close_current_export(workbench, monkeypatch, change):
    app, client, *_ = workbench
    endpoint, spec, trial_endpoint, plans, _ = pair(workbench, monkeypatch)
    result, _ = freeze(client, endpoint, spec)
    immutable = payload(app, result["id"])
    plan = client.get(trial_endpoint + "/" + plans[0]["id"]).json()
    if change == "private":
        mutate(app, workbench[5], lambda data: data.update(title="SYNTHETIC changed private metadata"))
    if change == "reviewer":
        with app.state.store.session() as session:
            session.get(User, plan["protocol"]["reviewer_ids"][0]).active = False
            session.commit()
    if change == "recipe":
        monkeypatch.setattr(cohorts, "RECIPE", "human-authority-trial-cohort-v2")
    if change == "head":
        mutate(app, trials._head_id(plans[0]["id"]), lambda data: data.update(sequence=999))
    if change == "missing":
        with app.state.store.session() as session:
            session.delete(session.get(Record, plans[0]["id"]))
            session.commit()
    if change == "scope":
        with app.state.store.session() as session:
            session.get(Record, plans[0]["id"]).matter_id = "foreign-workspace"
            session.commit()
    inspected = client.get(endpoint + "/" + result["id"])
    assert inspected.status_code == 200, inspected.text
    view = inspected.json()
    assert view["freshness"]["status"] in {"stale", "withheld"}
    if view["freshness"]["status"] == "withheld":
        assert view["manifest"] is None
    else:
        assert view["manifest"] == result["manifest"]
    assert client.get(endpoint + "/" + result["id"] + "/export").status_code in {404, 409}
    assert payload(app, result["id"]) == immutable


def test_permission_failure_hides_all_copied_notes_title_and_quotes(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, spec, _, _, permit = pair(workbench, monkeypatch)
    result, _ = freeze(client, endpoint, spec)
    permit.active = False
    denied = client.get(endpoint + "/" + result["id"])
    assert denied.status_code == 200, denied.text
    assert denied.json()["manifest"] is None and not denied.json()["public_source_access"]
    assert "SYNTHETIC" not in denied.text
    assert client.post(endpoint + "/preview", json=spec).status_code == 409
    assert client.get(endpoint + "/" + result["id"] + "/export").status_code == 409


def test_precommit_revalidation_packet_limit_and_nonce_conflict(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, *_ = pair(workbench, monkeypatch, complete=False)
    preview = client.post(endpoint + "/preview", json=spec).json()
    body = {**spec, "request_id": uuid4().hex, "expected_preview_sha256": preview["preview_sha256"]}
    real = cohorts.preview
    calls = 0

    def changed(*args):
        nonlocal calls
        calls += 1
        result = real(*args)
        if calls == 2:
            result["preview_sha256"] = "0" * 64
        return result

    monkeypatch.setattr(cohorts, "preview", changed)
    assert client.post(endpoint, json=body).status_code == 409
    assert count(app, cohorts.KIND) == count(app, cohorts.ADMISSION) == 0
    monkeypatch.setattr(cohorts, "preview", real)
    monkeypatch.setattr(cohorts, "MAX_BYTES", 1)
    assert client.post(endpoint, json=body).status_code == 409
    assert count(app, cohorts.KIND) == 0
    monkeypatch.setattr(cohorts, "MAX_BYTES", 16 * 1024 * 1024)
    assert client.post(endpoint, json=body).status_code == 201
    assert client.post(endpoint, json={**body, "purpose": "SYNTHETIC changed purpose"}).status_code == 409


def test_late_committed_guard_failure_is_pending_never_admitted_by_retry(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, *_ = pair(workbench, monkeypatch, complete=False)
    preview = client.post(endpoint + "/preview", json=spec).json()
    body = {**spec, "request_id": uuid4().hex, "expected_preview_sha256": preview["preview_sha256"]}
    original = app.state.graph.release.current_guard

    @contextmanager
    def late():
        with original() as info:
            yield info
            if count(app, cohorts.KIND):
                raise HTTPException(409, "SYNTHETIC late guard denial")

    monkeypatch.setattr(app.state.graph.release, "current_guard", late)
    saved = client.post(endpoint, json=body)
    assert saved.status_code == 409 and saved.json()["outcome"] == "committed_needs_revalidation"
    assert "SYNTHETIC" not in saved.text
    monkeypatch.setattr(app.state.graph.release, "current_guard", original)
    retry = client.post(endpoint, json=body).json()
    assert retry["manifest"] is None and retry["freshness"]["status"] == "withheld"
    assert count(app, cohorts.KIND) == 1


def test_nonmember_and_revoked_operator_cannot_use_private_group(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, *_ = pair(workbench, monkeypatch, complete=False)
    view, _ = freeze(client, endpoint, spec)
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == "demo"))
        session.delete(session.get(Membership, (view["manifest"]["matter_id"], user.id)))
        session.commit()
    for suffix in ("", "/candidates", "/" + view["id"], "/" + view["id"] + "/export"):
        assert client.get(endpoint + suffix).status_code in {403, 404}


def test_second_mutation_to_already_stale_evidence_invalidates_preview(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, *_ = pair(workbench, monkeypatch)
    document = workbench[5]
    mutate(app, document, lambda data: data.update(title="SYNTHETIC first change"))
    preview = client.post(endpoint + "/preview", json=spec)
    assert preview.status_code == 200, preview.text
    mutate(app, document, lambda data: data.update(title="SYNTHETIC second change"))
    response = client.post(
        endpoint,
        json={**spec, "request_id": uuid4().hex, "expected_preview_sha256": preview.json()["preview_sha256"]},
    )
    assert response.status_code == 409 and count(app, cohorts.KIND) == 0


def test_exact_profiles_do_not_pool_origin_or_rubric_and_preserve_conflicting_labels(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, spec, *_ = pair(workbench, monkeypatch)
    entries = copy.deepcopy(client.post(endpoint + "/preview", json=spec).json()["manifest"]["entries"])
    entries[1]["capture"]["protocol"]["sample_kind"] = "real"
    event = entries[1]["capture"]["snapshot"]
    event["basis"]["observations"][0]["assessment"]["observations"][0]["outcome"] = "unresolved"
    report = cohorts.reconcile(entries, [])
    assert len(report["profiles"]) == 2
    assert report["rows"][1]["outcome_difference_count"] == 1
    assert report["rows"][1]["unknown_semantic_observations"] == 12
    assert report["legal_verdict"] is None and not report["benefit_established"]


def test_new_capture_preserves_group_history_and_requires_new_preview(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, trial_endpoint, plans, *_ = pair(workbench, monkeypatch)
    frozen, _ = freeze(client, endpoint, spec)
    detail = trial_endpoint + "/" + plans[0]["id"]
    trial = client.get(detail).json()
    assessment = trial["snapshot"]["assessment"]
    preview = client.post(
        detail + "/capture-context",
        json={key: assessment[key] for key in ("comparison_id", "adjudication_ids")},
    ).json()
    newer = capture(
        client,
        detail,
        {
            **assessment,
            "request_id": uuid4().hex,
            "expected_capture_id": preview["expected_capture_id"],
            "expected_basis_sha256": preview["basis_sha256"],
            "note": "SYNTHETIC successor capture; earlier immutable records retained",
        },
    )
    view = client.get(endpoint + "/" + frozen["id"]).json()
    assert view["freshness"]["status"] == "stale" and view["manifest"] == frozen["manifest"]
    assert view["manifest"]["entries"][0]["capture"]["capture_id"] != newer["capture_id"]
    assert client.get(endpoint + "/" + frozen["id"] + "/export").status_code == 409
    refreshed, _ = freeze(client, endpoint, spec)
    assert refreshed["id"] != frozen["id"] and refreshed["freshness"]["status"] == "current"
    assert count(app, cohorts.KIND) == 2


@pytest.mark.parametrize("change", ["source", "private", "member"])
def test_export_rechecks_after_serialization_and_discards_payload(workbench, monkeypatch, change):
    app, client, *_ = workbench
    endpoint, spec, _, _, permit = pair(workbench, monkeypatch)
    frozen, _ = freeze(client, endpoint, spec)
    original = cohorts.canonical
    calls = 0

    def serialize(value):
        nonlocal calls
        text = original(value)
        if isinstance(value, dict) and value.get("id") == frozen["id"] and "live_sha256" in value:
            calls += 1
            if calls == 2:
                if change == "source":
                    permit.active = False
                elif change == "private":
                    mutate(
                        app,
                        workbench[5],
                        lambda data: data.update(title="SYNTHETIC changed during serialization"),
                    )
                else:
                    with app.state.store.session() as session:
                        user = session.scalar(select(User).where(User.username == "demo"))
                        session.delete(session.get(Membership, (frozen["manifest"]["matter_id"], user.id)))
                        session.commit()
        return text

    monkeypatch.setattr(cohorts, "canonical", serialize)
    response = client.get(endpoint + "/" + frozen["id"] + "/export")
    assert response.status_code in {403, 404, 409} and "SYNTHETIC" not in response.text


def test_group_cap_archival_and_access_checks_cannot_grant_a_write(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, spec, *_ = pair(workbench, monkeypatch, complete=False)
    frozen, body = freeze(client, endpoint, spec)
    monkeypatch.setattr(cohorts, "MAX_RECORDS", 1)
    assert client.post(endpoint, json=body).json()["id"] == frozen["id"]
    assert client.post(endpoint, json={**body, "request_id": uuid4().hex}).status_code == 409
    monkeypatch.setattr(cohorts, "MAX_RECORDS", 60)
    matter = base.rsplit("/", 1)[-1]
    mutate(app, matter, lambda data: data.update(status="archived"))
    assert client.post(endpoint, json={**body, "request_id": uuid4().hex}).status_code == 409
