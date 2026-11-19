"""Normal app intake and private history with disposable synthetic originals."""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select

from app import analysis_original_source
from app.config import Settings
from app.db import Audit, LoginSession, Record, digest
from app.runtime import create_app


def synthetic_pdf():
    buffer = BytesIO()
    writer = Canvas(buffer, invariant=1)
    for text in ("SYNTHETIC first original page.", "SYNTHETIC frozen source on the second original page."):
        writer.drawString(72, 720, text)
        writer.showPage()
    writer.save()
    return buffer.getvalue()


def count_opened(app, matter_id):
    with app.state.store.session() as session:
        return len(session.scalars(select(Audit).where(
            Audit.matter_id == matter_id, Audit.action == "analysis_original_opened",
        )).all())


@pytest.fixture
def saved_source(tmp_path):
    app = create_app(Settings(
        _env_file=None, demo_mode=True, cookie_secure=False, data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'synthetic.db'}", public_source_dir=tmp_path / "public",
        graph_url="", graph_release_dir="", opensearch_url="", gateway_enabled=False,
        gateway_url="", gateway_token="", encryption_key="", clamav_host="",
        extraction_url="", extraction_token="", LLM_PROVIDER_BASE_URL="",
        LLM_PROVIDER_API_KEY="", LLM_PROVIDER_MODEL="", LLM_PROVIDER_TUNNEL_URL="",
        LLM_PROVIDER_TUNNEL_APPROVED=False,
    ))
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/login", json={"username": "demo", "password": "demo-local-only"})
        assert login.status_code == 200
        client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        matter = client.get("/api/v1/matters").json()[0]["id"]
        base = f"/api/v1/matters/{matter}"
        original = synthetic_pdf()
        upload = client.post(base + "/documents", files={"file": ("synthetic.pdf", original, "application/pdf")})
        assert upload.status_code == 201
        document = client.get(base + "/documents/" + upload.json()["id"]).json()
        assert document["sha256"] == digest(original) and document["page_count"] == 2
        [passage] = [p for p in document["passages"] if p["locator"] == "Sayfa 2"]
        assert "second original page" in passage["text"]
        selection = {
            "evidence_id": passage["id"], "passage_sha256": passage["text_sha256"],
            "document_revision": document["revision"], "start": 10, "end": len(passage["text"]),
        }
        payload = {
            "title": "SYNTHETIC exact original review", "issue": "SYNTHETIC source page and version.",
            "evidence": [selection],
            "conclusion": {"text": "SYNTHETIC draft", "next_step": "Inspect the preserved source."},
        }
        created = client.post(base + "/analyses", json=payload)
        assert created.status_code == 201
        analysis = created.json()
        version = analysis["latest_version_id"]
        scope = base + f"/analyses/{analysis['id']}"
        context = client.get(scope + "/reviews/context", params={"version_id": version}).json()
        assert context["sources"][0]["quote_sha256"] == digest(passage["text"][10:])
        headers = {"X-Analysis-Content-SHA256": context["content_sha256"],
                   "X-Quote-SHA256": context["sources"][0]["quote_sha256"]}
        link = f"{scope}/versions/{version}/evidence/{passage['id']}/original/"
        yield app, client, matter, document, analysis, payload, link, headers, original


def test_saved_original_binds_page_bytes_and_explicit_historical_version(saved_source):
    app, client, matter, document, analysis, payload, link, headers, original = saved_source
    scope = f"/api/v1/matters/{matter}/analyses/{analysis['id']}"
    original_version = analysis["latest_version_id"]
    # Change the draft so the old version and its exact source can still be opened.
    revised = client.post(scope + "/versions", json={
        **payload, "title": "SYNTHETIC later version", "expected_revision": analysis["revision"],
        "change_note": "SYNTHETIC new title with original evidence.",
    })
    assert revised.status_code == 201
    latest = revised.json()["latest_version_id"]
    assert latest != original_version
    history_url = scope + "/reviews"
    history_before = client.get(history_url, params={"version_id": original_version}).json()
    with app.state.store.session() as session:
        exact_before = {key: session.get(Record, key).payload for key in (document["id"], analysis["id"], original_version)}
    path = app.state.settings.data_dir / "documents" / (document["id"] + ".enc")
    encrypted = path.read_bytes()
    assert count_opened(app, matter) == 0

    verified = client.get(link + "2", headers=headers)
    assert verified.status_code == 200 and verified.content == original
    assert verified.headers["cache-control"] == "no-store"
    assert verified.headers["content-type"] == "application/pdf" and verified.headers["accept-ranges"] == "none"
    assert verified.headers["x-source-page"] == "2" and verified.headers["x-source-page-count"] == "2"
    assert verified.headers["x-source-revision"] == str(document["revision"])
    assert verified.headers["x-source-sha256"] == digest(original)
    assert verified.headers["x-analysis-content-sha256"] == headers["X-Analysis-Content-SHA256"]
    assert verified.headers["x-quote-sha256"] == headers["X-Quote-SHA256"]
    assert count_opened(app, matter) == 1

    for request, pins, status in [
        (link + "1", headers, 409),
        (link + "3", headers, 409),
        (link + "02", headers, 422),
        (link + "0", headers, 422),
        (link + "2", {}, 422),
        (link + "2", {**headers, "X-Quote-SHA256": "0" * 64}, 409),
        (link.replace(original_version, latest) + "2", headers, 409),
        (link.replace(analysis["id"] + "/versions/", "unknown-analysis/versions/") + "2", headers, 404),
        (link.replace("/evidence/" + payload["evidence"][0]["evidence_id"], "/evidence/not-selected") + "2",
         headers, 404),
        (link.replace(f"/matters/{matter}/", "/matters/not-in-scope/") + "2", headers, 404),
    ]:
        denied = client.get(request, headers=pins)
        assert denied.status_code == status
        assert denied.content != original and "x-source-sha256" not in denied.headers
    anonymous = TestClient(app)
    assert anonymous.get(link + "2", headers=headers).status_code == 401
    assert client.get(link + "2", headers=[*headers.items(), ("X-Quote-SHA256", "0" * 64)]).status_code == 422
    assert client.get(link + "2", headers=headers, params={"page": "1"}).status_code == 422
    assert count_opened(app, matter) == 1
    assert path.read_bytes() == encrypted
    assert client.get(history_url, params={"version_id": original_version}).json() == history_before
    with app.state.store.session() as session:
        assert {key: session.get(Record, key).payload for key in exact_before} == exact_before


def test_saved_original_refuses_corruption_and_rechecks_scope_before_return(saved_source, monkeypatch):
    app, client, matter, document, _, _, link, headers, original = saved_source
    path = app.state.settings.data_dir / "documents" / (document["id"] + ".enc")
    ciphertext = path.read_bytes()
    path.write_bytes(app.state.store.cipher.encrypt(original + b"\n% altered synthetic original"))
    assert client.get(link + "2", headers=headers).status_code == 409
    path.write_bytes(b"corrupt synthetic envelope")
    assert client.get(link + "2", headers=headers).status_code == 409
    path.unlink()
    assert client.get(link + "2", headers=headers).status_code == 409
    path.write_bytes(ciphertext)

    read = analysis_original_source._read_original

    def revise_document(*args):
        raw = read(*args)
        with app.state.store.session() as session:
            record = session.get(Record, document["id"])
            app.state.store.update(record, app.state.store.decode(record))
            session.commit()
        return raw

    monkeypatch.setattr(analysis_original_source, "_read_original", revise_document)
    assert client.get(link + "2", headers=headers).status_code == 409
    monkeypatch.setattr(analysis_original_source, "_read_original", read)

    assert count_opened(app, matter) == 0 and path.read_bytes() == ciphertext


def test_saved_original_rechecks_login_after_open(saved_source, monkeypatch):
    app, client, matter, _, _, _, link, headers, _ = saved_source
    token_digest = digest(client.cookies["la_session"])
    read = analysis_original_source._read_original

    def expire_login(*args):
        raw = read(*args)
        with app.state.store.session() as session:
            session.delete(session.get(LoginSession, token_digest))
            session.commit()
        return raw

    monkeypatch.setattr(analysis_original_source, "_read_original", expire_login)
    response = client.get(link + "2", headers=headers)
    assert response.status_code == 401 and "x-source-sha256" not in response.headers
    assert count_opened(app, matter) == 0
