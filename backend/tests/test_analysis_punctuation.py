"""Immutable punctuation histories over disposable, version-pinned saved sources."""

from copy import deepcopy
from io import BytesIO

import pytest
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import select
from test_analysis_original_source import saved_source as saved_source

from app import analysis_punctuation as punctuation
from app.db import Audit, Record, User, digest
from app.evidence_prompt import canonical
from app.punctuation_capture import PRODUCER_RECIPE, PRODUCER_SHA256


@pytest.fixture
def retained_source(saved_source):
    app, client, matter, document, analysis, payload, original_link, headers, original = saved_source
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == "demo"))
    evidence = payload["evidence"][0]["evidence_id"]
    pins = {"matter_id": matter, "analysis_id": analysis["id"], "version_id": analysis["latest_version_id"],
            "evidence_id": evidence, "page": "2", "content_sha256": headers["X-Analysis-Content-SHA256"],
            "quote_sha256": headers["X-Quote-SHA256"]}
    image = BytesIO()
    with Image.new("L", (1415, 2000), 250) as raster:
        raster.save(image, "PNG")
    event = {"status": "punctuation_disagreement", "field_bounds": [10, 10, 90, 60],
             "crop_bounds": [5, 5, 100, 65], "coordinate_frame": "original_raster_top_left_half_open",
             "canonical_usable": False, "missing_readers": [], "readings": [
                 {"reader": "raw", "text": "8.", "glyphs": [["8", [20, 20, 35, 45]], [".", [36, 40, 40, 44]]]},
                 {"reader": "locally_leveled", "text": "8", "glyphs": [["8", [20, 20, 35, 45]]]},
             ]}
    capture = {"source_sha256": digest(original), "page": 2, "page_count": 2, "png": image.getvalue(),
               "producer_sha256": PRODUCER_SHA256, "producer_recipe": PRODUCER_RECIPE, "events": [event]}
    capture["run_sha256"] = punctuation.capture_run_sha256(capture)

    def retain(value=None):
        return punctuation.retain_capture(app.state.store, app.state.settings, user, **pins,
                                           capture=value if value is not None else capture)

    return {"app": app, "client": client, "matter": matter, "document": document, "analysis": analysis,
            "payload": payload, "headers": headers, "original": original, "capture": capture, "retain": retain,
            "url": original_link.replace("/original/", "/punctuation-observations/") + "2", "pins": pins}


def test_literal_event_run_and_raster_history_round_trip_without_source_mutation(retained_source):
    case = retained_source
    app, client = case["app"], case["client"]
    ids = (case["matter"], case["document"]["id"], case["analysis"]["id"], case["analysis"]["latest_version_id"])
    with app.state.store.session() as session:
        before = {ident: session.get(Record, ident).payload for ident in ids}
    original_path = app.state.settings.data_dir / "documents" / (case["document"]["id"] + ".enc")
    encrypted_original = original_path.read_bytes()
    history_url = f"/api/v1/matters/{case['matter']}/analyses/{case['analysis']['id']}/reviews"
    history = client.get(history_url, params={"version_id": case["pins"]["version_id"]}).json()
    [saved] = case["retain"]()
    [retry] = case["retain"]()
    assert retry == saved
    listed = client.get(case["url"], headers=case["headers"])
    assert listed.status_code == 200 and listed.headers["cache-control"] == "no-store"
    data = listed.json()
    assert data["items"] == [saved] and not data["has_more"] and not data["runs_has_more"]
    [receipt] = data["runs"]
    assert receipt["id"] == saved["run_id"] and receipt["event_count"] == 1
    assert receipt["scope"] == "source_page_context" and receipt["status"] == "captured_review_observations"
    assert saved["event"] == case["capture"]["events"][0] and saved["canonical_usable"] is False
    for value, hash_key in ((saved, "observation_sha256"), (receipt, "receipt_sha256")):
        payload = {key: item for key, item in value.items() if key not in {"id", "created_at", hash_key}}
        assert digest(canonical(payload)) == value[hash_key]
    detail = client.get(case["url"] + "/" + saved["id"], headers=case["headers"])
    assert detail.status_code == 200 and detail.json() == saved
    raster = client.get(case["url"] + "/" + saved["id"] + "/raster", headers=case["headers"])
    assert raster.status_code == 200 and raster.content == case["capture"]["png"]
    assert raster.headers["x-source-raster-sha256"] == digest(raster.content)
    assert raster.headers["x-punctuation-observation-sha256"] == saved["observation_sha256"]
    assert raster.headers["x-source-page"] == "2" and raster.headers["x-source-page-count"] == "2"
    assert raster.headers["x-source-sha256"] == case["document"]["sha256"]
    assert raster.headers["x-source-revision"] == str(case["document"]["revision"])
    with app.state.store.session() as session:
        assert {ident: session.get(Record, ident).payload for ident in ids} == before
        rows = session.scalars(select(Record).where(Record.kind.in_((punctuation.KIND, punctuation.RUN_KIND)))).all()
        assert len(rows) == 2 and all(row.revision == 1 and "punctuation_disagreement" not in row.payload for row in rows)
        audits = session.scalars(select(Audit).where(Audit.action.in_(
            ("analysis_punctuation_retained", "analysis_punctuation_capture_retained")))).all()
        assert len(audits) == 2
    assert original_path.read_bytes() == encrypted_original
    assert client.get(history_url, params={"version_id": case["pins"]["version_id"]}).json() == history


def test_empty_run_is_retained_without_inventing_an_observation(retained_source):
    case = retained_source
    capture = {**case["capture"], "events": []}
    capture["run_sha256"] = punctuation.capture_run_sha256(capture)
    assert case["retain"](capture) == [] and case["retain"](capture) == []
    response = case["client"].get(case["url"], headers=case["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == [] and not data["has_more"]
    [receipt] = data["runs"]
    assert receipt["event_count"] == 0 and receipt["status"] == "captured_no_alternatives"
    assert receipt["canonical_usable"] is False and "event" not in receipt
    with case["app"].state.store.session() as session:
        assert session.scalars(select(Record).where(Record.kind == punctuation.KIND)).all() == []
        assert len(session.scalars(select(Record).where(Record.kind == punctuation.RUN_KIND)).all()) == 1


def test_unrelated_private_history_is_not_decrypted_for_a_selected_page(retained_source, monkeypatch):
    case = retained_source
    [saved] = case["retain"]()
    store = case["app"].state.store
    with store.session() as session:
        user = session.scalar(select(User).where(User.username == "demo"))
        for index in range(30):
            store.add(session, punctuation.KIND, user, {"private_other_context": index}, case["matter"],
                      record_id="pco-" + f"{index:060x}")
        session.commit()
    decode = store.decode

    def selected_scope_only(row):
        if row.kind == punctuation.KIND:
            assert row.id == saved["id"], "Unrelated encrypted histories must not be scanned"
        return decode(row)

    monkeypatch.setattr(store, "decode", selected_scope_only)
    response = case["client"].get(case["url"], headers=case["headers"], params={"limit": 1, "run_limit": 1})
    assert response.status_code == 200 and response.json()["items"] == [saved]


def test_run_and_observation_pagination_are_independent_and_append_stable(retained_source):
    case = retained_source
    retained = []
    for digit in "876":
        capture = deepcopy(case["capture"])
        for reading in capture["events"][0]["readings"]:
            reading["text"] = digit + reading["text"][1:]
            reading["glyphs"][0][0] = digit
        capture["run_sha256"] = punctuation.capture_run_sha256(capture)
        retained.extend(case["retain"](capture))
    first = case["client"].get(case["url"], headers=case["headers"],
                               params={"limit": 1, "run_limit": 2}).json()
    second = case["client"].get(case["url"], headers=case["headers"],
                                params={"limit": 2, "offset": 1, "run_offset": 2, "run_limit": 2}).json()
    assert first["has_more"] and first["runs_has_more"]
    assert not second["has_more"] and not second["runs_has_more"]
    assert first["items"] + second["items"] == retained
    assert [row["id"] for row in first["runs"] + second["runs"]] == [row["run_id"] for row in retained]
    # A later publication does not reorder the already observed prefix.
    empty = {**case["capture"], "events": []}
    empty["run_sha256"] = punctuation.capture_run_sha256(empty)
    case["retain"](empty)
    repeated = case["client"].get(case["url"], headers=case["headers"],
                                  params={"limit": 1, "run_limit": 2}).json()
    assert repeated == first


def test_saved_historical_scope_never_silently_substitutes_latest_analysis(retained_source):
    case = retained_source
    [saved] = case["retain"]()
    base = f"/api/v1/matters/{case['matter']}/analyses/{case['analysis']['id']}"
    revised = case["client"].post(base + "/versions", json={
        **case["payload"], "title": "SYNTHETIC changed draft", "expected_revision": case["analysis"]["revision"],
        "change_note": "SYNTHETIC history remains pinned.",
    })
    assert revised.status_code == 201
    latest = revised.json()["latest_version_id"]
    old = case["client"].get(case["url"], headers=case["headers"])
    assert old.status_code == 200 and old.json()["items"] == [saved]
    assert case["client"].get(case["url"].replace(case["pins"]["version_id"], latest),
                               headers=case["headers"]).status_code == 409
    context = case["client"].get(base + "/reviews/context", params={"version_id": latest}).json()
    headers = {**case["headers"], "X-Analysis-Content-SHA256": context["content_sha256"]}
    current = case["client"].get(case["url"].replace(case["pins"]["version_id"], latest), headers=headers)
    assert current.status_code == 200 and current.json()["items"] == [] and current.json()["runs"] == []


@pytest.mark.parametrize("mutation", ["bool_coordinate", "text", "agreement", "outside_crop", "unknown_status", "duplicate"])
def test_invalid_native_observation_cannot_become_a_saved_assertion(retained_source, mutation):
    case = retained_source
    capture = deepcopy(case["capture"])
    event = capture["events"][0]
    if mutation == "bool_coordinate":
        event["field_bounds"][0] = True
    elif mutation == "text":
        event["readings"][0]["text"] = "9."
    elif mutation == "agreement":
        event["readings"][1] = {**deepcopy(event["readings"][0]), "reader": "locally_leveled"}
    elif mutation == "outside_crop":
        event["readings"][0]["glyphs"][1][1] = [200, 200, 205, 205]
    elif mutation == "unknown_status":
        event["status"] = "approved"
    else:
        capture["events"].append(deepcopy(event))
    capture["run_sha256"] = punctuation.capture_run_sha256(capture)
    with pytest.raises(HTTPException) as refused:
        case["retain"](capture)
    assert refused.value.status_code == 409
    assert case["client"].get(case["url"], headers=case["headers"]).json()["runs"] == []
