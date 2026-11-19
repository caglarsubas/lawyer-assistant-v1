"""Independent persistence boundaries with disposable private-case fixtures.

These tests simulate a trusted producer response. Native OCR accuracy and the
original-to-raster producer are qualified separately.
"""

import json
import signal
import subprocess
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from threading import Barrier, BoundedSemaphore

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import delete, select
from test_analysis_original_source import saved_source as saved_source

from app.db import Audit, Employee, EmployeeRole, FirmRole, LoginSession, Membership, Record, User, digest
from app.evidence_prompt import canonical


def synthetic_capture(original):
    from app.analysis_punctuation import capture_run_sha256
    from app.punctuation_capture import PRODUCER_RECIPE, PRODUCER_SHA256

    with Image.new("L", (1415, 2000), 255) as image:
        canvas = ImageDraw.Draw(image)
        canvas.rectangle((100, 100, 119, 129), outline=0, width=2)
        canvas.rectangle((121, 125, 123, 129), fill=0)
        output = BytesIO()
        image.save(output, format="PNG")
    event = {
        "status": "punctuation_disagreement",
        "field_bounds": [95, 100, 130, 130],
        "crop_bounds": [95, 95, 135, 135],
        "coordinate_frame": "original_raster_top_left_half_open",
        "canonical_usable": False,
        "missing_readers": [],
        "readings": [
            {"reader": "raw", "text": "8.", "glyphs": [["8", [100, 100, 120, 130]],
                                                         [".", [121, 125, 124, 130]]]},
            {"reader": "locally_leveled", "text": "8", "glyphs": [["8", [100, 100, 120, 130]]]},
        ],
    }
    capture = {"source_sha256": digest(original), "page": 2, "page_count": 2,
               "png": output.getvalue(), "producer_sha256": PRODUCER_SHA256,
               "producer_recipe": PRODUCER_RECIPE, "events": [event]}
    capture["run_sha256"] = capture_run_sha256(capture)
    return capture


def _wire(capture):
    return {**capture, "png": b64encode(capture["png"]).decode("ascii")}


@pytest.fixture
def punctuation_case(saved_source):
    from app import analysis_punctuation as persistence

    app, client, matter, document, analysis, _, original_link, headers, original = saved_source
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == "demo"))
    evidence_id = original_link.rsplit("/evidence/", 1)[1].split("/", 1)[0]
    kwargs = {"matter_id": matter, "analysis_id": analysis["id"],
              "version_id": analysis["latest_version_id"], "evidence_id": evidence_id, "page": "2",
              "content_sha256": headers["X-Analysis-Content-SHA256"], "quote_sha256": headers["X-Quote-SHA256"]}
    url = original_link.removesuffix("/original/") + "/punctuation-observations/2"
    capture = synthetic_capture(original)

    def retain(value=None):
        return persistence.retain_capture(app.state.store, app.state.settings, user,
                                          **kwargs, capture=value if value is not None else capture)

    yield {"app": app, "client": client, "matter": matter, "document": document, "analysis": analysis,
           "original": original, "headers": headers, "url": url, "user": user, "capture": capture,
           "retain": retain, "kwargs": kwargs, "module": persistence}


def _records(case):
    with case["app"].state.store.session() as session:
        return session.scalars(select(Record).where(Record.kind == "punctuation_observation")).all()


def _protected(case):
    identifiers = [case["matter"], case["document"]["id"], case["analysis"]["id"], case["analysis"]["latest_version_id"]]
    with case["app"].state.store.session() as session:
        payloads = {identifier: session.get(Record, identifier).payload for identifier in identifiers}
    path = case["app"].state.settings.data_dir / "documents" / (case["document"]["id"] + ".enc")
    return payloads, path.read_bytes()


def _readonly(session, user):
    if session.get(Employee, user.id) is None:
        session.add(Employee(user_id=user.id, firm_id=user.firm_id))
    role = FirmRole(firm_id=user.firm_id, name="SYNTHETIC independent reader", permissions='["matter.read"]')
    session.add(role)
    session.flush()
    session.execute(delete(EmployeeRole).where(EmployeeRole.user_id == user.id))
    session.add(EmployeeRole(user_id=user.id, role_id=role.id))


def test_concurrent_identical_capture_converges_without_rewriting_source(punctuation_case):
    case = punctuation_case
    protected = _protected(case)
    barrier = Barrier(2)

    def persist():
        barrier.wait(timeout=5)
        return case["retain"]()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: persist(), range(2)))
    assert len(results[0]) == len(results[1]) == 1
    assert results[0][0]["id"] == results[1][0]["id"]
    records = _records(case)
    assert len(records) == 1 and records[0].revision == 1
    assert _protected(case) == protected
    exact_payload = records[0].payload
    assert case["retain"]()[0]["id"] == records[0].id
    assert _records(case)[0].payload == exact_payload


@pytest.mark.parametrize("mutation", ["producer", "source", "page", "run", "canonical", "literal", "missing_reader"])
def test_invalid_capture_never_creates_a_receipt(punctuation_case, mutation):
    case = punctuation_case
    capture = deepcopy(case["capture"])
    if mutation == "producer":
        capture["producer_sha256"] = "0" * 64
    elif mutation == "source":
        capture["source_sha256"] = "0" * 64
    elif mutation == "page":
        capture["page"] = 1
    elif mutation == "run":
        capture["run_sha256"] = "0" * 64
    elif mutation == "canonical":
        capture["events"][0]["canonical_usable"] = True
    elif mutation == "literal":
        capture["events"][0]["readings"][0]["text"] = "9."
    else:
        capture["events"][0]["missing_readers"] = ["raw"]
    if mutation != "run":
        capture["run_sha256"] = case["module"].capture_run_sha256(capture)
    protected = _protected(case)
    with pytest.raises(HTTPException) as refused:
        case["retain"](capture)
    assert refused.value.status_code in {409, 422}
    assert _records(case) == [] and _protected(case) == protected


def test_retain_requires_fresh_write_permission_even_with_case_read_access(punctuation_case):
    case = punctuation_case
    with case["app"].state.store.session() as session:
        _readonly(session, case["user"])
        session.commit()
    with pytest.raises(HTTPException) as refused:
        case["retain"]()
    assert refused.value.status_code == 403 and _records(case) == []
    assert case["client"].get(case["url"], headers=case["headers"]).status_code == 200


def test_no_observation_list_or_raster_discloses_to_anonymous_or_foreign_matter(punctuation_case):
    case = punctuation_case
    saved = case["retain"]()[0]
    raster = case["url"] + "/" + saved["id"] + "/raster"
    for path in (case["url"], case["url"] + "/" + saved["id"], raster):
        anonymous = TestClient(case["app"])
        response = anonymous.get(path, headers=case["headers"])
        assert response.status_code == 401 and response.content != case["capture"]["png"]
        foreign = path.replace("/matters/" + case["matter"] + "/", "/matters/foreign-synthetic-matter/")
        response = case["client"].get(foreign, headers=case["headers"])
        assert response.status_code == 404 and response.content != case["capture"]["png"]


def test_stored_event_cannot_be_rewritten_with_internally_updated_hashes(punctuation_case):
    case = punctuation_case
    saved = case["retain"]()[0]
    store = case["app"].state.store
    with store.session() as session:
        row = session.get(Record, saved["id"])
        state = store.decode(row)
        metadata = state["metadata"]
        metadata["event"]["readings"][0]["text"] = "9."
        metadata["event"]["readings"][0]["glyphs"][0][0] = "9"
        metadata["event_sha256"] = digest(canonical(metadata["event"]))
        row.payload = store.encode(state)
        session.commit()
    response = case["client"].get(case["url"] + "/" + saved["id"], headers=case["headers"])
    assert response.status_code == 409
    response = case["client"].get(case["url"] + "/" + saved["id"] + "/raster", headers=case["headers"])
    assert response.status_code == 409 and response.content != case["capture"]["png"]


def test_scope_revoked_during_original_read_prevents_new_receipt(punctuation_case, monkeypatch):
    case = punctuation_case
    original_read = case["module"]._read_original

    def revoked(*args):
        data = original_read(*args)
        with case["app"].state.store.session() as session:
            session.execute(delete(Membership).where(Membership.matter_id == case["matter"],
                                                     Membership.user_id == case["user"].id))
            session.commit()
        return data

    monkeypatch.setattr(case["module"], "_read_original", revoked)
    with pytest.raises(HTTPException) as refused:
        case["retain"]()
    assert refused.value.status_code == 404 and _records(case) == []


def test_session_revoked_during_retrieval_never_returns_raster(punctuation_case, monkeypatch):
    case = punctuation_case
    saved = case["retain"]()[0]
    original_read = case["module"]._read_original
    token = digest(case["client"].cookies["la_session"])

    def revoked(*args):
        data = original_read(*args)
        with case["app"].state.store.session() as session:
            session.delete(session.get(LoginSession, token))
            session.commit()
        return data

    monkeypatch.setattr(case["module"], "_read_original", revoked)
    response = case["client"].get(case["url"] + "/" + saved["id"] + "/raster", headers=case["headers"])
    assert response.status_code == 401 and response.content != case["capture"]["png"]


def test_write_revoked_during_original_read_prevents_new_receipt(punctuation_case, monkeypatch):
    case = punctuation_case
    original_read = case["module"]._read_original
    changed = False

    def revoked(*args):
        nonlocal changed
        data = original_read(*args)
        if not changed:
            changed = True
            with case["app"].state.store.session() as session:
                _readonly(session, case["user"])
                session.commit()
        return data

    monkeypatch.setattr(case["module"], "_read_original", revoked)
    with pytest.raises(HTTPException) as refused:
        case["retain"]()
    assert refused.value.status_code == 403 and _records(case) == []


@pytest.mark.parametrize("header", ["X-Analysis-Content-SHA256", "X-Quote-SHA256"])
def test_stale_version_or_quote_pin_blocks_all_saved_observation_reads(punctuation_case, header):
    case = punctuation_case
    saved = case["retain"]()[0]
    headers = {**case["headers"], header: "0" * 64}
    paths = (case["url"], case["url"] + "/" + saved["id"], case["url"] + "/" + saved["id"] + "/raster")
    for path in paths:
        response = case["client"].get(path, headers=headers)
        assert response.status_code == 409 and response.content != case["capture"]["png"]


@pytest.mark.parametrize("corruption", ["ciphertext", "png", "provenance"])
def test_corrupt_run_never_exposes_partial_metadata_or_raster(punctuation_case, corruption):
    case = punctuation_case
    saved = case["retain"]()[0]
    store = case["app"].state.store
    with store.session() as session:
        row = session.get(Record, saved["run_id"])
        state = store.decode(row)
        if corruption == "ciphertext":
            row.payload = "corrupt-synthetic-ciphertext"
        else:
            if corruption == "png":
                state["raster_base64"] = "bm90IGEgcG5n"
            else:
                state["metadata"]["producer_sha256"] = "0" * 64
            row.payload = store.encode(state)
        session.commit()
    for path in (case["url"], case["url"] + "/" + saved["id"], case["url"] + "/" + saved["id"] + "/raster"):
        response = case["client"].get(path, headers=case["headers"])
        assert response.status_code == 409 and response.content != case["capture"]["png"]
        assert saved["id"].encode() not in response.content


def test_empty_capture_is_an_immutable_run_not_verified_canonical_evidence(punctuation_case):
    case = punctuation_case
    capture = deepcopy(case["capture"])
    capture["events"] = []
    capture["run_sha256"] = case["module"].capture_run_sha256(capture)
    assert case["retain"](capture) == []
    assert case["retain"](capture) == []
    response = case["client"].get(case["url"], headers=case["headers"])
    assert response.status_code == 200
    listing = response.json()
    assert listing["items"] == [] and len(listing["runs"]) == 1
    receipt = listing["runs"][0]
    assert receipt["status"] == "captured_no_alternatives" and receipt["canonical_usable"] is False
    assert receipt["immutable"] is True and receipt["event_count"] == 0


def test_normal_post_uses_exact_server_pdf_and_retains_review_only_context(punctuation_case, monkeypatch):
    from app import analysis_punctuation_capture as coordinator

    case = punctuation_case
    case["app"].state.settings.extraction_url = "http://extractor"
    case["app"].state.settings.extraction_token = "disposable-not-live-" + "x" * 32
    invoked = []

    def execute_capture(self, content, page):
        invoked.append((self.base_url, content, page))
        return deepcopy(case["capture"])

    monkeypatch.setattr(coordinator.PunctuationClient, "execute_capture", execute_capture)
    protected = _protected(case)
    response = case["client"].post(case["url"], headers=case["headers"])
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert invoked == [("http://extractor", case["original"], 2)]
    assert len(_records(case)) == 1 and _protected(case) == protected
    listing = case["client"].get(case["url"], headers=case["headers"]).json()
    assert listing["items"][0]["event"] == case["capture"]["events"][0]
    assert listing["items"][0]["scope"] == "source_page_context"
    assert listing["items"][0]["canonical_usable"] is False


@pytest.mark.parametrize("change", ["session", "membership", "write"])
def test_post_reauthenticates_after_isolated_worker_before_retention(punctuation_case, monkeypatch, change):
    from app import analysis_punctuation_capture as coordinator

    case = punctuation_case
    case["app"].state.settings.extraction_url = "http://extractor"
    case["app"].state.settings.extraction_token = "disposable-not-live-" + "x" * 32
    token = digest(case["client"].cookies["la_session"])

    def execute_capture(self, content, page):
        assert content == case["original"] and page == 2
        with case["app"].state.store.session() as session:
            if change == "session":
                session.delete(session.get(LoginSession, token))
            elif change == "membership":
                session.execute(delete(Membership).where(Membership.matter_id == case["matter"],
                                                         Membership.user_id == case["user"].id))
            else:
                _readonly(session, case["user"])
            session.commit()
        return deepcopy(case["capture"])

    monkeypatch.setattr(coordinator.PunctuationClient, "execute_capture", execute_capture)
    response = case["client"].post(case["url"], headers=case["headers"])
    assert response.status_code == {"session": 401, "membership": 404, "write": 403}[change]
    assert _records(case) == []


def test_public_capture_cannot_submit_event_png_or_source_path(punctuation_case, monkeypatch):
    from app import analysis_punctuation_capture as coordinator

    case = punctuation_case

    def unavailable(*args, **kwargs):
        pytest.fail("Untrusted request body reached the isolated worker")

    monkeypatch.setattr(coordinator.PunctuationClient, "execute_capture", unavailable)
    response = case["client"].post(case["url"], headers=case["headers"], json={
        "png": "untrusted", "events": [], "path": "/untrusted/other-case.pdf",
    })
    assert response.status_code == 422 and _records(case) == []


@pytest.mark.parametrize("read_index", [1, 2])
@pytest.mark.parametrize("change", ["revoked", "reassigned"])
def test_post_session_revoked_during_retention_io_cannot_append(punctuation_case, monkeypatch, read_index, change):
    from app import analysis_punctuation_capture as coordinator

    case = punctuation_case
    case["app"].state.settings.extraction_url = "http://extractor"
    case["app"].state.settings.extraction_token = "disposable-not-live-" + "x" * 32
    token = digest(case["client"].cookies["la_session"])
    original_read = case["module"]._read_original
    read_count = 0

    def execute_capture(self, content, page):
        return deepcopy(case["capture"])

    def read_then_revoke(*args):
        nonlocal read_count
        original = original_read(*args)
        read_count += 1
        if read_count == read_index:
            with case["app"].state.store.session() as session:
                login = session.get(LoginSession, token)
                if change == "revoked":
                    session.delete(login)
                else:
                    replacement = User(username="synthetic-reassigned-session", name="Synthetic replacement",
                                       firm_id=case["user"].firm_id, role=case["user"].role,
                                       password_hash=case["user"].password_hash)
                    session.add(replacement)
                    session.flush()
                    session.add(Membership(matter_id=case["matter"], user_id=replacement.id))
                    login.user_id = replacement.id
                session.commit()
        return original

    monkeypatch.setattr(coordinator.PunctuationClient, "execute_capture", execute_capture)
    monkeypatch.setattr(case["module"], "_read_original", read_then_revoke)
    response = case["client"].post(case["url"], headers=case["headers"])
    assert response.status_code == 401 and _records(case) == []
    with case["app"].state.store.session() as session:
        assert session.scalar(select(Record.id).where(
            Record.kind.in_((case["module"].KIND, case["module"].RUN_KIND)),
        )) is None
        assert session.scalar(select(Audit.id).where(
            Audit.action.in_(("analysis_punctuation_capture_retained", "analysis_punctuation_retained")),
        )) is None


def test_private_client_binds_returned_producer_page_pdf_and_raster_without_private_metadata(punctuation_case,
                                                                                         monkeypatch):
    from app import punctuation_client

    case = punctuation_case
    real_client = httpx.Client
    seen = []

    def receive(request):
        seen.append(request)
        return httpx.Response(200, json=_wire(case["capture"]))

    def transport_client(**kwargs):
        assert kwargs["follow_redirects"] is False and kwargs["trust_env"] is False
        return real_client(**kwargs, transport=httpx.MockTransport(receive))

    monkeypatch.setattr(punctuation_client.httpx, "Client", transport_client)
    client = punctuation_client.PunctuationClient("http://extractor", "disposable-" + "x" * 32)
    result = client.execute_capture(case["original"], 2)
    assert result == case["capture"]
    [request] = seen
    assert request.url.path == "/punctuation-capture/2" and not request.url.query
    assert request.content == case["original"]
    assert request.headers["authorization"] == "Bearer disposable-" + "x" * 32
    assert request.headers["content-type"] == "application/octet-stream"
    assert request.headers["accept-encoding"] == "identity"
    assert all(case[key] not in str(request.headers) for key in ("matter",))
    assert case["analysis"]["id"] not in str(request.headers)


@pytest.mark.parametrize("mutation", ["source", "producer", "page", "run", "base64", "extra"])
def test_private_wire_rejects_wrong_identity_or_encoding(punctuation_case, mutation):
    from app.extraction_client import ExtractionError
    from app.punctuation_client import validate_capture_wire

    case = punctuation_case
    payload = _wire(case["capture"])
    if mutation == "source":
        payload["source_sha256"] = "0" * 64
    elif mutation == "producer":
        payload["producer_sha256"] = "0" * 64
    elif mutation == "page":
        payload["page"] = True
    elif mutation == "run":
        payload["run_sha256"] = "0" * 64
    elif mutation == "base64":
        payload["png"] = "invalid!?"
    else:
        payload["private_path"] = "/untrusted/other-case.pdf"
    with pytest.raises(ExtractionError):
        validate_capture_wire(payload, digest(case["original"]), 2)


def test_private_worker_authentication_admission_slots_and_release(monkeypatch):
    from app import punctuation_service

    app = FastAPI()
    app.state.extraction_slots = BoundedSemaphore(2)
    token = "synthetic-token-" + "x" * 32
    punctuation_service.install_capture_route(app, token)
    seen = []

    def parse(content, page):
        seen.append((content, page))
        return {"synthetic": True}

    monkeypatch.setattr(punctuation_service, "parse_capture", parse)
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/octet-stream"}
    with TestClient(app) as client:
        assert client.post("/punctuation-capture/1", content=b"%PDF-synthetic").status_code == 401
        assert client.post("/punctuation-capture/1", headers=headers,
                           content=b"not-pdf").status_code == 422
        assert client.post("/punctuation-capture/01", headers=headers,
                           content=b"%PDF-synthetic").status_code == 415
        assert client.post("/punctuation-capture/1?path=untrusted", headers=headers,
                           content=b"%PDF-synthetic").status_code == 415
        app.state.extraction_slots.acquire()
        app.state.extraction_slots.acquire()
        try:
            assert client.post("/punctuation-capture/1", headers=headers,
                               content=b"%PDF-synthetic").status_code == 429
        finally:
            app.state.extraction_slots.release()
            app.state.extraction_slots.release()
        assert client.post("/punctuation-capture/1", headers=headers,
                           content=b"%PDF-synthetic").status_code == 200
    assert seen == [(b"%PDF-synthetic", 1)]
    assert app.state.extraction_slots.acquire(blocking=False)
    assert app.state.extraction_slots.acquire(blocking=False)
    assert not app.state.extraction_slots.acquire(blocking=False)
    app.state.extraction_slots.release()
    app.state.extraction_slots.release()


@pytest.mark.parametrize("change", ["session", "membership"])
def test_post_reauthenticates_after_original_io_before_worker(punctuation_case, monkeypatch, change):
    from app import analysis_punctuation_capture as coordinator

    case = punctuation_case
    case["app"].state.settings.extraction_url = "http://extractor"
    case["app"].state.settings.extraction_token = "disposable-not-live-" + "x" * 32
    token = digest(case["client"].cookies["la_session"])
    original_read = coordinator._read_original

    def read_then_revoke(*args):
        original = original_read(*args)
        with case["app"].state.store.session() as session:
            if change == "session":
                session.delete(session.get(LoginSession, token))
            else:
                session.execute(delete(Membership).where(Membership.matter_id == case["matter"],
                                                         Membership.user_id == case["user"].id))
            session.commit()
        return original

    def not_authorized(*args, **kwargs):
        pytest.fail("Revoked source selection reached the worker")

    monkeypatch.setattr(coordinator, "_read_original", read_then_revoke)
    monkeypatch.setattr(coordinator.PunctuationClient, "execute_capture", not_authorized)
    response = case["client"].post(case["url"], headers=case["headers"])
    assert response.status_code == {"session": 401, "membership": 404}[change]
    assert _records(case) == []


def test_private_subprocess_uses_disposable_exact_pdf_and_fixed_budget(punctuation_case, monkeypatch):
    from app import punctuation_service

    case = punctuation_case
    captured = {}
    waits = []
    killed = []

    class DisposableProcess:
        pid = 987654321
        returncode = 0

        def __init__(self, args, **kwargs):
            source = Path(args[3])
            captured.update({"source": source, "directory": Path(kwargs["cwd"]), "args": args,
                             "content": source.read_bytes(), "mode": source.stat().st_mode & 0o777,
                             "env": kwargs["env"]})
            assert kwargs["stdin"] == subprocess.DEVNULL and kwargs["stderr"] == subprocess.DEVNULL
            assert kwargs["start_new_session"] is True
            kwargs["stdout"].write(json.dumps(_wire(case["capture"])).encode())

        def wait(self, timeout):
            waits.append(timeout)
            return self.returncode

    monkeypatch.setattr(punctuation_service.subprocess, "Popen", DisposableProcess)
    monkeypatch.setattr(punctuation_service.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    assert punctuation_service.parse_capture(case["original"], 2) == _wire(case["capture"])
    assert captured["content"] == case["original"] and captured["mode"] == 0o600
    assert captured["args"][1:3] == ["-m", "app.punctuation_capture"] and captured["args"][4] == "2"
    assert set(captured["env"]) == {"PATH", "LANG", "PYTHONPATH", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS"}
    assert captured["env"]["OMP_THREAD_LIMIT"] == captured["env"]["OPENBLAS_NUM_THREADS"] == "1"
    assert waits == [20, 5] and killed == [(DisposableProcess.pid, signal.SIGKILL)]
    assert not captured["source"].exists() and not captured["directory"].exists()


def test_private_subprocess_timeout_kills_and_removes_disposable_source(monkeypatch):
    from app import punctuation_service
    from app.extraction_client import ExtractionError

    waits = []
    killed = []
    sources = []

    class TimedOutProcess:
        pid = 987654321
        returncode = -9

        def __init__(self, args, **kwargs):
            sources.append(Path(args[3]))

        def wait(self, timeout):
            waits.append(timeout)
            if timeout == 20:
                raise subprocess.TimeoutExpired("synthetic", timeout)
            return self.returncode

    monkeypatch.setattr(punctuation_service.subprocess, "Popen", TimedOutProcess)
    monkeypatch.setattr(punctuation_service.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    with pytest.raises(ExtractionError):
        punctuation_service.parse_capture(b"%PDF-synthetic", 1)
    assert waits == [20, 5] and killed == [(TimedOutProcess.pid, signal.SIGKILL)]
    assert all(not source.exists() for source in sources)
