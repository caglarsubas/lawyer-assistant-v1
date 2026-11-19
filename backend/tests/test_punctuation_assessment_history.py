"""Synthetic exact-source histories distinguish incomplete OCR from timely absence."""

from base64 import b64encode
from copy import deepcopy

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_analysis_original_source import saved_source as saved_source
from test_analysis_punctuation import retained_source as retained_source

from app import analysis_punctuation as punctuation
from app.db import Record, User, digest
from app.evidence_prompt import canonical
from app.extraction_client import ExtractionError
from app.punctuation_client import validate_capture_wire


def snapshot(case):
    ids = (case["matter"], case["document"]["id"], case["analysis"]["id"], case["pins"]["version_id"])
    with case["app"].state.store.session() as session:
        records = {ident: (session.get(Record, ident).payload, session.get(Record, ident).revision) for ident in ids}
    path = case["app"].state.settings.data_dir / "documents" / (case["document"]["id"] + ".enc")
    history = case["client"].get(
        f"/api/v1/matters/{case['matter']}/analyses/{case['analysis']['id']}/reviews",
        params={"version_id": case["pins"]["version_id"]},
    )
    assert history.status_code == 200
    return records, path.read_bytes(), history.json()


def capture_with(case, assessment, events):
    capture = {**deepcopy(case["capture"]), "assessment": assessment, "events": events}
    capture["run_sha256"] = punctuation.capture_run_sha256(capture)
    return capture


def listed(case):
    response = case["client"].get(case["url"], headers=case["headers"])
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    return response.json()


@pytest.mark.parametrize("reason,stage", [
    ("page_budget", "nomination_raw"),
    ("reader_error", "nomination_contrast"),
    ("source_scope_unverified", "currency_fields"),
])
def test_zero_event_incomplete_runs_reopen_without_fabricating_success_or_readings(retained_source, reason, stage):
    case = retained_source
    before = snapshot(case)
    assessment = {"status": "incomplete", "reason": reason, "stage": stage}
    capture = capture_with(case, assessment, [])
    assert case["retain"](capture) == [] and case["retain"](deepcopy(capture)) == []
    result = listed(case)
    assert result["items"] == [] and len(result["runs"]) == 1
    receipt = result["runs"][0]
    assert receipt["assessment"] == assessment and receipt["event_count"] == 0
    assert receipt["status"] == "captured_incomplete" and receipt["canonical_usable"] is False
    assert receipt["run_sha256"] == capture["run_sha256"]
    assert receipt["document_sha256"] == digest(case["original"])
    assert receipt["version_id"] == case["pins"]["version_id"]
    assert receipt["quote_sha256"] == case["pins"]["quote_sha256"]
    assert listed(case) == result
    anonymous = TestClient(case["app"])
    assert anonymous.get(case["url"], headers=case["headers"]).status_code == 401
    assert snapshot(case) == before


def test_completed_raw_reader_survives_incomplete_capture_as_one_literal_reading(retained_source):
    case = retained_source
    review_url = f"/api/v1/matters/{case['matter']}/analyses/{case['analysis']['id']}/reviews"
    context = case["client"].get(review_url + "/context", params={"version_id": case["pins"]["version_id"]}).json()
    review = case["client"].post(review_url, json={
        **{key: context[key] for key in ("version_id", "expected_revision", "content_sha256", "expected_review_id")},
        "request_id": "d" * 32, "decision": "changes_requested", "note": "SYNTHETIC source punctuation remains pending.",
        "criteria": [{"criterion": "sources", "outcome": "needs_change", "note": "SYNTHETIC incomplete source readers."}],
        "findings": [],
    })
    assert review.status_code == 201
    before = snapshot(case)
    assert len(before[-1]) == 1
    event = deepcopy(case["capture"]["events"][0])
    event.update(status="page_budget", readings=event["readings"][:1], missing_readers=["locally_leveled"])
    assessment = {"status": "incomplete", "reason": "page_budget", "stage": "currency_fields"}
    capture = capture_with(case, assessment, [event])
    wire = {**capture, "png": b64encode(capture["png"]).decode("ascii")}
    assert validate_capture_wire(wire, capture["source_sha256"], capture["page"]) == capture
    [saved] = case["retain"](capture)
    assert case["retain"](deepcopy(capture)) == [saved]
    result = listed(case)
    assert result["items"] == [saved] and result["runs"][0]["status"] == "captured_incomplete"
    assert result["runs"][0]["assessment"] == saved["assessment"] == assessment
    assert saved["event"] == event and saved["event"]["readings"][0]["text"] == "8."
    assert saved["event"]["missing_readers"] == ["locally_leveled"]
    detail = case["client"].get(case["url"] + "/" + saved["id"], headers=case["headers"])
    assert detail.status_code == 200 and detail.json() == saved
    raster = case["client"].get(case["url"] + "/" + saved["id"] + "/raster", headers=case["headers"])
    assert raster.status_code == 200 and raster.content == capture["png"]
    assert raster.headers["x-punctuation-observation-sha256"] == saved["observation_sha256"]
    assert snapshot(case) == before


def test_assessment_is_part_of_run_identity_and_cannot_rewrite_the_previous_receipt(retained_source):
    case = retained_source
    before = snapshot(case)
    pending = capture_with(case, {"status": "incomplete", "reason": "page_budget", "stage": "nomination_raw"}, [])
    checked = capture_with(case, {"status": "complete", "reason": "no_currency_scope", "stage": "currency_fields"}, [])
    assert pending["run_sha256"] != checked["run_sha256"]
    assert case["retain"](pending) == []
    original_receipt = listed(case)["runs"][0]
    assert case["retain"](checked) == []
    runs = listed(case)["runs"]
    assert len(runs) == 2 and runs[0] == original_receipt and runs[0]["id"] != runs[1]["id"]
    assert runs[1]["status"] == "captured_no_alternatives"
    assert runs[1]["assessment"] == checked["assessment"] and runs[1]["canonical_usable"] is False
    assert snapshot(case) == before


@pytest.mark.parametrize("mutation", [
    "missing", "list", "unhashable_stage", "unhashable_reason", "complete_diagnostic", "nomination_with_field_event",
])
def test_current_capture_and_wire_reject_missing_or_malformed_assessment(retained_source, mutation):
    case = retained_source
    before = snapshot(case)
    capture = deepcopy(case["capture"])
    if mutation == "missing":
        capture.pop("assessment")
    elif mutation == "list":
        capture["assessment"] = []
    elif mutation == "unhashable_stage":
        capture["assessment"]["stage"] = ["currency_fields"]
    elif mutation == "unhashable_reason":
        capture["assessment"]["reason"] = {"checked": True}
    elif mutation == "nomination_with_field_event":
        capture["assessment"] = {"status": "incomplete", "reason": "page_budget", "stage": "nomination_raw"}
    else:
        event = capture["events"][0]
        event.update(status="page_budget", readings=event["readings"][:1], missing_readers=["locally_leveled"])
    capture["run_sha256"] = punctuation.capture_run_sha256(capture)
    wire = {**capture, "png": b64encode(capture["png"]).decode("ascii")}
    with pytest.raises(ExtractionError):
        validate_capture_wire(wire, capture["source_sha256"], capture["page"])
    with pytest.raises(HTTPException) as refused:
        case["retain"](capture)
    assert refused.value.status_code == 409
    assert listed(case)["runs"] == [] and listed(case)["items"] == []
    assert snapshot(case) == before


@pytest.mark.parametrize("kind,mutation", [
    (punctuation.RUN_KIND, "missing"), (punctuation.RUN_KIND, "unhashable"),
    (punctuation.RUN_KIND, "changed"), (punctuation.KIND, "changed"),
])
def test_current_stored_assessment_tampering_fails_closed_without_raster_disclosure(retained_source, kind, mutation):
    case = retained_source
    before = snapshot(case)
    [saved] = case["retain"]()
    store = case["app"].state.store
    with store.session() as session:
        row = session.get(Record, saved["run_id"] if kind == punctuation.RUN_KIND else saved["id"])
        data = store.decode(row)
        if mutation == "missing":
            data["metadata"].pop("assessment")
        elif mutation == "unhashable":
            data["metadata"]["assessment"]["stage"] = ["currency_fields"]
        else:
            data["metadata"]["assessment"] = {"status": "incomplete", "reason": "reader_error", "stage": "currency_fields"}
        row.payload = store.encode(data)
        session.commit()
    for suffix in ("", "/" + saved["id"], "/" + saved["id"] + "/raster"):
        response = case["client"].get(case["url"] + suffix, headers=case["headers"])
        assert response.status_code == 409 and response.content != case["capture"]["png"]
    assert snapshot(case) == before


def test_encrypted_v1_history_reopens_with_original_identifiers_hashes_and_no_assessment(retained_source):
    case = retained_source
    before = snapshot(case)
    capture = deepcopy(case["capture"])
    capture.pop("assessment")
    capture["producer_recipe"] = "native-pdf-punctuation-v1"
    capture["producer_sha256"] = digest(b"disposable historical v1 producer")
    capture["run_sha256"] = punctuation.capture_run_sha256(capture)
    store = case["app"].state.store
    scope = {key: case["pins"][key] for key in ("analysis_id", "version_id", "evidence_id", "content_sha256", "quote_sha256")}
    common = {**scope, "document_id": case["document"]["id"], "document_revision": case["document"]["revision"],
              "document_sha256": case["document"]["sha256"], "page": 2, "page_count": 2,
              "raster_sha256": digest(capture["png"]), "width": 1415, "height": 2000,
              "producer_recipe": capture["producer_recipe"], "producer_sha256": capture["producer_sha256"],
              "run_sha256": capture["run_sha256"], "scope": "source_page_context", "canonical_usable": False,
              "immutable": True}
    run_metadata = {**common, "event_count": 1, "status": "captured_review_observations"}
    with store.session() as session:
        user = session.scalar(select(User).where(User.username == "demo"))
        run_id = punctuation._run_ident(user.firm_id, case["matter"], run_metadata)
        metadata = {**common, "event": capture["events"][0], "event_sha256": digest(canonical(capture["events"][0])),
                    "run_id": run_id, "status": "review_required"}
        observation_id = punctuation._ident(user.firm_id, case["matter"], metadata)
        store.add(session, punctuation.RUN_KIND, user, {"schema": punctuation.SCHEMA + "-capture",
                  "metadata": run_metadata, "events": capture["events"],
                  "raster_base64": b64encode(capture["png"]).decode("ascii")}, case["matter"], record_id=run_id)
        store.add(session, punctuation.KIND, user, {"schema": punctuation.SCHEMA, "metadata": metadata},
                  case["matter"], record_id=observation_id)
        session.commit()
        encrypted = {ident: session.get(Record, ident).payload for ident in (run_id, observation_id)}
    result = listed(case)
    [receipt], [saved] = result["runs"], result["items"]
    assert receipt["id"] == run_id and saved["id"] == observation_id and saved["run_id"] == run_id
    assert receipt["receipt_sha256"] == digest(canonical(run_metadata))
    assert saved["observation_sha256"] == digest(canonical(metadata))
    assert receipt["run_sha256"] == saved["run_sha256"] == capture["run_sha256"]
    assert "assessment" not in receipt and "assessment" not in saved
    assert case["client"].get(case["url"] + "/" + observation_id, headers=case["headers"]).json() == saved
    raster = case["client"].get(case["url"] + "/" + observation_id + "/raster", headers=case["headers"])
    assert raster.status_code == 200 and raster.content == capture["png"]
    assert raster.headers["x-punctuation-observation-sha256"] == saved["observation_sha256"]
    assert listed(case) == result
    with store.session() as session:
        assert {ident: session.get(Record, ident).payload for ident in encrypted} == encrypted
        assert all(session.get(Record, ident).revision == 1 for ident in encrypted)
    assert snapshot(case) == before
