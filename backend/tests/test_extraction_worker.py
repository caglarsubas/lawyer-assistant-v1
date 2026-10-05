"""Synthetic extraction and adversarial transport checks; no live service connections."""

import json
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient

from app import extraction_client, extraction_worker
from app.extraction_client import ExtractionClient, ExtractionError, validate_result
from app.extraction_worker import create_app, parse_document

TOKEN = "synthetic-worker-token-for-tests-only-32"
HEADERS = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/octet-stream",
           "X-Document-Suffix": ".txt"}


def result():
    return {"passages": [{"locator": "Paragraf 1", "text": "Kurgusal belge."}],
            "warnings": [], "page_count": None, "passage_count": 1}


def mock_transport(monkeypatch, payload=None, status=200, headers=None):
    original = httpx.Client
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(status, json=payload if payload is not None else result(), headers=headers)

    def client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return original(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    return seen


def test_real_worker_extracts_only_synthetic_document_content():
    with TestClient(create_app(TOKEN)) as client:
        response = client.post("/extract", content="Kurgusal belge.\n\nİkinci bölüm.".encode(), headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["passage_count"] == 2
        assert data["passages"][1]["text"] == "İkinci bölüm."
        assert set(data["passages"][0]) == {"text", "locator"}
        assert client.get("/health").json() == {"status": "ok"}


def test_unauthorized_worker_call_never_parses(monkeypatch):
    monkeypatch.setattr(extraction_worker, "parse_document", lambda *args: pytest.fail("Parser must not run"))
    with TestClient(create_app(TOKEN)) as client:
        assert client.post("/extract", content=b"fixture", headers={**HEADERS, "Authorization": "wrong"}).status_code == 401


def test_readiness_requires_worker_authentication_without_parsing(monkeypatch):
    monkeypatch.setattr(extraction_worker, "parse_document", lambda *args: pytest.fail("Readiness must not parse"))
    with TestClient(create_app(TOKEN)) as client:
        assert client.get("/ready").status_code == 401
        assert client.get("/ready", headers={"Authorization": "Bearer incorrect"}).status_code == 401
        assert client.get("/ready", headers={"Authorization": "Bearer " + TOKEN}).json() == {
            "status": "ready", "protocol": "isolated-extraction-v1", "max_document_bytes": 20 * 1024 * 1024,
        }


@pytest.mark.parametrize("changes", [
    {"X-Document-Suffix": ".exe"}, {"X-Document-Suffix": "../.txt"},
    {"Content-Type": "text/plain"}, {"Content-Encoding": "gzip"},
])
def test_worker_rejects_unadmitted_document_transports(changes):
    with TestClient(create_app(TOKEN)) as client:
        assert client.post("/extract", content=b"fixture", headers={**HEADERS, **changes}).status_code == 415


@pytest.mark.parametrize("length", ["0", "99999999", "invalid", "9" * 5000])
def test_worker_rejects_unsafe_length_before_reading(length):
    with TestClient(create_app(TOKEN)) as client:
        response = client.post("/extract", content=b"fixture", headers={**HEADERS, "Content-Length": length})
        assert response.status_code == 413


def test_worker_bounds_streamed_body_without_relying_on_length(monkeypatch):
    monkeypatch.setattr(extraction_worker, "MAX_DOCUMENT_BYTES", 10)
    with TestClient(create_app(TOKEN)) as client:
        assert client.post("/extract", content=iter([b"123456", b"123456"]), headers=HEADERS).status_code == 413


def test_worker_rejects_empty_or_mismatched_content():
    with TestClient(create_app(TOKEN)) as client:
        assert client.post("/extract", content=b"", headers=HEADERS).status_code == 413
        response = client.post("/extract", content=b"fixture", headers={**HEADERS, "Content-Length": "1"})
        assert response.status_code == 422
        assert client.post("/extract?matter=private", content=b"fixture", headers=HEADERS).status_code == 415


def test_two_parser_slots_are_enforced_and_failure_releases_capacity(monkeypatch):
    app = create_app(TOKEN)
    app.state.extraction_slots.acquire()
    app.state.extraction_slots.acquire()
    with TestClient(app) as client:
        assert client.post("/extract", content=b"fixture", headers=HEADERS).status_code == 429
        app.state.extraction_slots.release()

        def failed(*args):
            raise ExtractionError("private parser detail must not escape")

        monkeypatch.setattr(extraction_worker, "parse_document", failed)
        response = client.post("/extract", content=b"fixture", headers=HEADERS)
        assert response.status_code == 422
        assert "private parser" not in response.text
        assert app.state.extraction_slots.acquire(blocking=False)
    app.state.extraction_slots.release()
    app.state.extraction_slots.release()


@pytest.mark.parametrize("payload", [
    {**result(), "document_id": "not-admitted"},
    {**result(), "passages": [{"text": "a", "locator": "p", "id": "foreign-id"}]},
    {**result(), "passage_count": 2}, {**result(), "page_count": True},
    {**result(), "page_count": 501}, {**result(), "warnings": ["x" * 1001]},
    {**result(), "passages": [{"text": "a\x00b", "locator": "p"}]},
    {**result(), "passages": [{"text": "a\ud800b", "locator": "p"}]},
    {**result(), "passages": [{"text": "a\uffffb", "locator": "p"}]},
    {**result(), "passages": [{"text": "x" * 2_000_001, "locator": "p"}]},
    {"error": "parser crashed", "message": "internal path"}, [],
])
def test_returned_parser_data_must_match_strict_schema(payload):
    with pytest.raises(ExtractionError):
        validate_result(payload)


def test_worker_rechecks_even_mocked_parser_result(monkeypatch):
    monkeypatch.setattr(extraction_worker, "parse_document", lambda *args: {**result(), "secret": "not allowed"})
    with TestClient(create_app(TOKEN)) as client:
        assert client.post("/extract", content=b"fixture", headers=HEADERS).status_code == 422


def test_parser_process_has_clean_environment_and_group_cleanup(monkeypatch):
    observed = {}

    class Process:
        pid, returncode = 987654321, 0

        def __init__(self, command, **kwargs):
            observed.update(kwargs)
            kwargs["stdout"].write(json.dumps(result()).encode())

        def wait(self, timeout):
            return 0

    monkeypatch.setattr(subprocess, "Popen", Process)
    monkeypatch.setattr(extraction_worker.os, "killpg", lambda pid, sig: observed.update(killed=pid))
    assert parse_document(b"fixture", ".txt") == result()
    assert set(observed["env"]) == {"PATH", "LANG", "PYTHONPATH", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS"}
    assert observed["start_new_session"] is True
    assert observed["killed"] == Process.pid


def test_parser_timeout_kills_process_group(monkeypatch):
    killed = []

    class Process:
        pid, returncode = 987654321, -9

        def __init__(self, *args, **kwargs):
            self.calls = 0

        def wait(self, timeout):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("synthetic-parser", timeout)
            return -9

    monkeypatch.setattr(subprocess, "Popen", Process)
    monkeypatch.setattr(extraction_worker.os, "killpg", lambda pid, sig: killed.append(pid))
    with pytest.raises(ExtractionError, match="execution budget"):
        parse_document(b"fixture", ".txt")
    assert killed == [Process.pid]


@pytest.mark.parametrize("origin", [
    "https://public.example", "http://169.254.169.254", "http://0.0.0.0", "http://[::ffff:127.0.0.1]",
    "http://extractor/other", "http://secret@extractor", "http://extractor?private=x", "http://extractor:bad",
])
def test_client_cannot_connect_to_unqualified_origins(origin):
    with pytest.raises(ExtractionError):
        ExtractionClient(origin, TOKEN)


def test_client_sends_no_document_identity_or_provider_metadata(monkeypatch):
    seen = mock_transport(monkeypatch)
    data = ExtractionClient("http://extractor:8002", TOKEN).execute(b"fixture", ".txt")
    assert data == result()
    assert seen[0].content == b"fixture"
    assert seen[0].url.path == "/extract" and not seen[0].url.query
    assert seen[0].headers["authorization"] == "Bearer " + TOKEN
    assert seen[0].headers["x-document-suffix"] == ".txt"
    assert seen[0].headers["accept-encoding"] == "identity"


@pytest.mark.parametrize("status", [301, 401, 422, 429, 500])
def test_client_fails_closed_on_worker_failure(monkeypatch, status):
    mock_transport(monkeypatch, status=status)
    with pytest.raises(ExtractionError):
        ExtractionClient("http://extractor:8002", TOKEN).execute(b"fixture", ".txt")


def test_client_response_size_and_time_are_bounded(monkeypatch):
    mock_transport(monkeypatch)
    monkeypatch.setattr(extraction_client, "MAX_RESPONSE_BYTES", 10)
    with pytest.raises(ExtractionError, match="size"):
        ExtractionClient("http://extractor:8002", TOKEN).execute(b"fixture", ".txt")
    monkeypatch.setattr(extraction_client, "MAX_RESPONSE_BYTES", 10000)
    clock = iter([0, 81])
    monkeypatch.setattr(extraction_client.time, "monotonic", lambda: next(clock))
    with pytest.raises(ExtractionError, match="time budget"):
        ExtractionClient("http://extractor:8002", TOKEN).execute(b"fixture", ".txt")


def test_missing_short_tokens_are_not_a_default_credential():
    for token in ("", "short"):
        with pytest.raises(ExtractionError):
            ExtractionClient("http://extractor:8002", token)
        with pytest.raises(ValueError):
            create_app(token)
