"""Disposable synthetic HTTP acceptance; real handlers, no real inference."""

import hashlib
import io
import json
import os
import socket
from contextlib import ExitStack
from copy import deepcopy

import pytest
from docx import Document
from fastapi.testclient import TestClient
from http_test_clients import attach_case_transport, peer_client
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from test_analysis_reviews import review_request
from test_analysis_suggestions import adopt, finished
from test_content_scope import assignments, team
from test_firm_admin import PASSWORD, create_employee, login
from test_human_workflow import create as create_work
from test_human_workflow import path as work_path
from test_human_workflow import response_for
from test_portfolio import customer, workspace

from app.analysis_proposals import proposal_messages
from app.config import Settings
from app.db import Record
from app.main import create_app
from app.provider import ProviderError

API = "/api/v1"
SOURCE = "UAT kurgu: Ödeme için imzalı teslim tutanağı gerekir."
CLAUSE = "Ödeme için imzalı teslim tutanağı gerekir."


def sha(value):
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def checked(response, status=200):
    assert response.status_code == status, response.text[:1000]
    return response


@pytest.fixture
def uat(tmp_path, monkeypatch):
    # Exclude every product configuration input inherited from the host. No
    # repo .env, existing database, network service or real credential is used.
    for name in list(os.environ):
        if name.startswith(("LA_", "LLM_PROVIDER_")):
            monkeypatch.delenv(name)
    for method in ("connect", "connect_ex"):
        original = getattr(socket.socket, method)

        def local_only(sock, address, original=original):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                pytest.fail("IP socket connection attempted in disposable UAT")
            return original(sock, address)

        monkeypatch.setattr(socket.socket, method, local_only)

    app = create_app(Settings(
        _env_file=None, demo_mode=True, cookie_secure=False, data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'acceptance.db'}", public_source_dir=tmp_path / "public",
    ))
    with ExitStack() as stack:
        owner = stack.enter_context(TestClient(app))
        attach_case_transport(app, owner)
        login(owner)

        def actor(username=None, password=PASSWORD):
            client = peer_client(app)
            stack.callback(client.close)
            if username:
                login(client, username, password)
            return client

        yield app, owner, actor


def upload(client, base, name, content):
    return checked(client.post(base + "/documents", files={
        "file": (name, content, "application/octet-stream"),
    }), 201).json()


def document(client, base, name, content):
    receipt = upload(client, base, name, content)
    assert receipt["status"] == "needs_review" and receipt["sha256"] == sha(content)
    assert "original_path" not in receipt and "passages" not in receipt
    path = base + "/documents/" + receipt["id"]
    source = checked(client.get(path)).json()
    assert checked(client.get(path + "/original")).content == content
    return source, path


def test_buat_01_password_and_session_lifecycle_keeps_case_content(uat):
    _, owner, actor = uat
    guest = actor()
    assert guest.get(API + "/workspaces").status_code == 401
    assert guest.post(API + "/auth/login", json={"username": "demo", "password": "wrong-uat"}).status_code == 401
    peer_record = create_employee(owner, "uat-account-peer")
    peer = actor("uat-account-peer")
    sibling = actor("demo", "demo-local-only")
    case = workspace(owner, "UAT password case")
    base = API + "/matters/" + case["id"]
    _, source_path = document(owner, base, "uat-account.txt", SOURCE.encode())
    assert checked(sibling.get(source_path + "/original")).content == SOURCE.encode()

    path = API + "/auth/password"
    new = "  UAT yeni geçici parola 2026  "
    request = {"current_password": "demo-local-only", "new_password": new, "confirm_password": new}
    assert owner.post(path, json=request, headers={"Origin": "https://wrong-origin.invalid"}).status_code == 403
    csrf = owner.headers.pop("X-CSRF-Token")
    assert owner.post(path, json=request).status_code == 403
    owner.headers["X-CSRF-Token"] = csrf
    wrong = checked(owner.post(path, json={**request, "current_password": "incorrect-uat"}), 400)
    assert new not in wrong.text and "incorrect-uat" not in wrong.text
    checked(sibling.get(source_path))
    response = checked(owner.post(path, json=request))
    assert response.json()["reauthentication_required"] and response.headers["cache-control"] == "no-store"
    cookie = response.headers["set-cookie"].lower()
    assert all(flag in cookie for flag in ("httponly", "samesite=strict", "max-age=0"))
    assert owner.get(source_path).status_code == sibling.get(source_path + "/original").status_code == 401
    assert checked(peer.get(API + "/auth/me")).json()["user"]["id"] == peer_record["id"]
    for password in (request["current_password"], new.strip()):
        assert owner.post(API + "/auth/login", json={"username": "demo", "password": password}).status_code == 401
    login(owner, password=new)
    assert checked(owner.get(source_path + "/original")).content == SOURCE.encode()
    session_token = owner.cookies.get("la_session")
    assert session_token
    checked(owner.post(API + "/auth/logout"))
    # Replay the exact old cookie rather than merely relying on cookie deletion.
    assert guest.get(source_path, headers={"Cookie": f"la_session={session_token}"}).status_code == 401


def test_buat_02_portfolio_comments_and_explicit_access_are_scoped(uat):
    app, owner, actor = uat
    admin = checked(owner.get(API + "/auth/me")).json()["user"]["id"]
    peer_record = create_employee(owner, "uat-scope-peer")
    peer = actor("uat-scope-peer")
    a, b = customer(owner, "UAT client A"), customer(owner, "UAT client B")
    shared = workspace(owner, "UAT shared file", [a["id"], b["id"], a["id"]], relevant_date="2026-10-04")
    past = workspace(owner, "UAT earlier A file", [a["id"]], relevant_date="2026-10-03")
    private = workspace(owner, "UAT restricted B file", [b["id"]], relevant_date="2026-10-04")
    assert shared["customer_ids"] == [a["id"], b["id"]]

    def list_cases(client, **params):
        return {row["id"] for row in checked(client.get(API + "/workspaces", params=params)).json()}

    both = {"customer_ids": f"{a['id']},{b['id']}"}
    scoped = {"customer_ids": a["id"], "date_from": "2026-10-04", "date_to": "2026-10-04",
              "date_field": "relevant_date"}
    assert list_cases(owner, **both) == {shared["id"], past["id"], private["id"]}
    assert list_cases(owner, **scoped) == {shared["id"]}
    assert owner.get(API + "/workspaces", params={**scoped, "date_from": "2026-10-05"}).status_code == 422
    base = API + "/workspaces/" + shared["id"]
    matter = API + "/matters/" + shared["id"]
    doc, source = document(owner, matter, "uat-scope.txt", SOURCE.encode())
    assert checked(owner.get(base)).json()["documents"][0]["id"] == doc["id"]
    comments = base + "/comments"
    for value in ("UAT müşteri beyanı, doğrulanmadı.", "UAT dosya takibi."):
        row = checked(owner.post(comments, json={"text": value}), 201).json()
        assert row["text"] == value and row["author_name"] and row["created_at"]
        with app.state.store.session() as session:
            assert value not in session.get(Record, row["id"]).payload
    assert [row["text"] for row in checked(owner.get(comments)).json()] == [
        "UAT müşteri beyanı, doğrulanmadı.", "UAT dosya takibi.",
    ]
    assert owner.delete(comments + "/" + row["id"]).status_code in (404, 405)
    assert checked(owner.get(matter)).json()["facts"] == []

    assignments(owner, a["id"], [{"user_id": admin, "scope": "details"},
                                 {"user_id": peer_record["id"], "scope": "details"}])
    assert peer.get(API + "/auth/me").status_code == 401
    login(owner)
    login(peer, "uat-scope-peer", PASSWORD)
    a_visible = checked(peer.get(API + "/customers")).json()
    assert [(row["id"], row["workspace_count"]) for row in a_visible] == [(a["id"], 0)]
    assert list_cases(peer, **both) == set()
    for path in (base, comments, source + "/original"):
        assert peer.get(path).status_code == 404
    assistant = API + "/assistant/respond"
    scoped_assistant = {"mode": "monthly", "context": {**scoped, "customer_ids": [a["id"]]}}
    assert checked(peer.post(assistant, json=scoped_assistant)).json()["sources"] == []

    assignments(owner, a["id"], [{"user_id": admin, "scope": "details"},
                                 {"user_id": peer_record["id"], "scope": "all_cases"}])
    login(owner)
    login(peer, "uat-scope-peer", PASSWORD)
    assert list_cases(peer, **both) == {shared["id"], past["id"]}
    assert peer.get(API + "/workspaces/" + private["id"]).status_code == 404
    allowed = checked(peer.get(source + "/original"))
    assert allowed.content == SOURCE.encode() and allowed.headers["cache-control"] == "no-store"
    assert checked(peer.get(base + "/access")).json()["client_all_cases_origins"] == [a["id"]]
    summary = checked(peer.post(assistant, json=scoped_assistant)).json()
    assert not summary["provider_used"] and {row["workspace_id"] for row in summary["sources"]} == {shared["id"]}
    assert private["title"] not in summary["answer"] and past["title"] not in summary["answer"]

    revision = checked(owner.get(base)).json()["revision"]
    tags = base + "/customers"
    assert owner.put(tags, json={"customer_ids": [b["id"]], "revision": revision - 1}).status_code == 409
    changed = checked(owner.put(tags, json={"customer_ids": [b["id"]], "revision": revision})).json()
    assert changed["customer_ids"] == [b["id"]]
    assert peer.get(source + "/original").status_code == 401
    login(peer, "uat-scope-peer", PASSWORD)
    assert list_cases(peer, **both) == {past["id"]}
    assert peer.get(comments).status_code == peer.get(source).status_code == 404
    assert checked(owner.get(source + "/original")).content == SOURCE.encode()


def sample_files():
    buffer = io.BytesIO()
    doc = Document()
    doc.add_paragraph("UAT kurgu: metin yalnızca bir taslaktır.")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "UAT teslim tarihi"
    table.rows[0].cells[1].text = "2026-10-04"
    doc.add_paragraph(CLAUSE)
    doc.save(buffer)
    yield "uat-source.docx", buffer.getvalue(), [
        ("Paragraf 1", "UAT kurgu: metin yalnızca bir taslaktır."),
        ("Tablo 1, satır 1", "UAT teslim tarihi | 2026-10-04"),
        ("Paragraf 2", CLAUSE),
    ]
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(60, 700, "UAT synthetic: delivery not established.")
    pdf.showPage()
    pdf.drawString(60, 700, "UAT synthetic: confirm signature separately.")
    pdf.save()
    yield "uat-source.pdf", buffer.getvalue(), [
        ("Sayfa 1", "UAT synthetic: delivery not established."),
        ("Sayfa 2", "UAT synthetic: confirm signature separately."),
    ]
    yield "uat-source.txt", SOURCE.encode(), [("Paragraf 1", SOURCE)]
    yield "uat-source.csv", "Kayıt,Tutar\nUAT örnek,30\n".encode(), [
        ("Satır 1", "Kayıt | Tutar"), ("Satır 2", "UAT örnek | 30"),
    ]


def test_buat_03_originals_locators_extraction_failure_and_fact_roles(uat):
    app, owner, _ = uat
    case = workspace(owner, "UAT intake and fact roles")
    other = workspace(owner, "UAT other intake")
    base, foreign = (API + "/matters/" + item["id"] for item in (case, other))
    for name, content, expected in sample_files():
        result, path = document(owner, base, "../" + name, content)
        assert result["name"] == name
        assert [(p["locator"], p["text"]) for p in result["passages"]] == expected
        assert all(p["text_sha256"] == sha(p["text"]) for p in result["passages"])
        assert owner.get(foreign + "/documents/" + result["id"]).status_code == 404
        assert owner.get(foreign + "/documents/" + result["id"] + "/original").status_code == 404
        encrypted = (app.state.settings.data_dir / "documents" / (result["id"] + ".enc")).read_bytes()
        assert encrypted != content and app.state.store.cipher.decrypt(encrypted) == content
        if name.endswith(".txt"):
            passage_id = result["passages"][0]["id"]

    for name, content, status in (("invalid.pdf", b"not a PDF", 415), ("empty.txt", b"", 413),
                                  ("unexpected.exe", b"unsupported", 415)):
        assert owner.post(base + "/documents", files={"file": (name, content)}).status_code == status
    invalid_bytes = b"\xff\xff invalid UTF-8 for UAT"
    failed = upload(owner, base, "unreadable.txt", invalid_bytes)
    failed_path = base + "/documents/" + failed["id"]
    assert failed["status"] == "failed" and failed["passage_count"] == 0 and failed["extraction_warnings"]
    assert checked(owner.get(failed_path)).json()["passages"] == []
    assert checked(owner.get(failed_path + "/original")).content == invalid_bytes
    assert len(checked(owner.get(base)).json()["documents"]) == 5

    claim = {"text": "UAT teslim edildiği ileri sürüldü.", "status": "documented"}
    assert owner.post(base + "/facts", json=claim).status_code == 422
    assert owner.post(foreign + "/facts", json={**claim, "evidence_id": passage_id}).status_code == 422
    assert owner.post(base + "/facts", json={**claim, "evidence_id": failed["id"]}).status_code == 422
    allegation = checked(owner.post(base + "/facts", json={**claim, "status": "alleged"}), 201).json()
    fact = checked(owner.post(base + "/facts", json={
        "text": "Taslakta imzalı tutanak gerekliliği yazılıdır.", "status": "documented", "evidence_id": passage_id,
    }), 201).json()
    revised = checked(owner.patch(base + "/facts/" + fact["id"], json={
        "text": "UAT gerekliliğin etkisi tartışmalı.", "status": "disputed", "reason": "UAT kayıt düzeltmesi",
    })).json()
    assert allegation["status"] == "alleged" and not allegation["evidence_id"]
    assert revised["status"] == "disputed" and revised["history"][0]["status"] == "documented"
    assert revised["history"][0]["evidence_id"] == passage_id
    assert checked(owner.get(base)).json()["facts"] and not checked(owner.get(foreign)).json()["facts"]


def analysis_input(passage, doc, fact):
    return {
        "title": "UAT teslim koşulu incelemesi",
        "issue": "Kurgu taslakta ödeme hangi koşula bağlanmış?",
        "posture": "Sözleşme taslağı", "event_date": "2026-10-04",
        "evidence": [{
            "evidence_id": passage["id"], "passage_sha256": passage["text_sha256"],
            "document_revision": doc["revision"], "start": len("UAT kurgu: "), "end": len(SOURCE),
        }],
        "premises": [{"id": "p1", "kind": "fact", "fact_id": fact["id"], "fact_revision": fact["revision"]}],
        "rules": [{
            "id": "r1", "kind": "contract_clause", "text": "Taslak, imzalı teslim tutanağı arıyor.",
            "evidence_ids": [passage["id"]], "conditions": [{
                "id": "c1", "text": "İmzalı teslim tutanağı", "kind": "element", "required_status": "met",
            }],
        }],
        "applications": [{
            "id": "a1", "rule_id": "r1", "premise_ids": ["p1"],
            "rationale": "Teslim kaydı kontrol edilmelidir.",
            "assessments": [{"condition_id": "c1", "status": "unknown", "premise_ids": ["p1"]}],
        }],
        "alternatives": [{"id": "alt1", "kind": "search_gap", "text": "Karşı belge aranmalıdır."}],
        "conclusion": {
            "text": "Ödeme koşulu ayrıca incelenmelidir.", "application_ids": ["a1"], "alternative_ids": ["alt1"],
            "uncertainty": ["İmzalı tutanak doğrulanmadı."], "next_step": "Özgün kaydı inceleyin.",
        },
    }


def configure_fixture_provider(app, monkeypatch, suggest):
    settings = app.state.settings
    settings.provider_base_url = "https://10.20.0.55/v1"
    settings.provider_api_key = "UAT-FIXTURE-NOT-A-SECRET"
    settings.provider_model = "UAT-DETERMINISTIC-FIXTURE"
    settings.provider_context_limit = 32768
    settings.provider_identity_verified = True
    settings.provider_cloud_fallback_disabled = True
    monkeypatch.setattr(app.state.provider, "probe", lambda: {"ready": True})
    monkeypatch.setattr(app.state.provider, "suggest_analysis", suggest)
    monkeypatch.setattr(app.state.provider, "generate",
                        lambda *_a, **_k: pytest.fail("Unexpected quotation inference in structured workflow"))


def test_buat_04_exact_draft_bounded_revision_and_grounded_review_exports(uat, monkeypatch):
    app, owner, actor = uat
    admin = checked(owner.get(API + "/auth/me")).json()["user"]["id"]
    reviewer_record = create_employee(owner, "uat-draft-reviewer")
    outsider = create_employee(owner, "uat-draft-outsider")
    case = workspace(owner, "UAT exact review case")
    other = workspace(owner, "UAT separate review case")
    team(owner, case["id"], [{"user_id": admin}, {"user_id": reviewer_record["id"]}])
    reviewer, unassigned = actor("uat-draft-reviewer"), actor("uat-draft-outsider")
    base = API + "/matters/" + case["id"]
    analyses = base + "/analyses"
    doc, original = document(owner, base, "uat-grounding.txt", SOURCE.encode())
    passage = doc["passages"][0]
    fact = checked(owner.post(base + "/facts", json={
        "text": "Kurgu metni ödeme için bir teslim kaydı arıyor.",
        "status": "documented", "evidence_id": passage["id"],
    }), 201).json()
    payload = analysis_input(passage, doc, fact)
    invalid = deepcopy(payload)
    invalid["evidence"][0]["passage_sha256"] = "0" * 64
    assert owner.post(analyses, json=invalid).status_code == 409
    checked(owner.post(analyses + "/check", json=payload))
    assert checked(owner.get(analyses)).json() == []
    draft = checked(owner.post(analyses, json=payload), 201).json()
    evidence = draft["evidence"][0]
    assert evidence["text"] == CLAUSE and evidence["quote_sha256"] == sha(CLAUSE)
    assert evidence["document_sha256"] == sha(SOURCE) and evidence["passage_sha256"] == sha(SOURCE)
    assert draft["checks"]["legal_approval"] == "not_granted" and draft["version"] == 1
    current = analyses + "/" + draft["id"]
    reviews, suggestions = current + "/reviews", current + "/suggestions"
    history_query = {"version_id": draft["latest_version_id"]}
    for path in (analyses, original + "/original", reviews + "/context", current + "/export"):
        assert unassigned.get(path, params=history_query).status_code == 404
    assert owner.get(current.replace(case["id"], other["id"]) + "/export").status_code == 404

    body, _ = review_request(reviewer, reviews, draft, decision="changes_requested")
    body.update(request_id="b041" * 8, note="UAT GENEL GEREKÇE: Özgün tutanağın eksikliği sonucu sınırlar.", findings=[
        {"target_id": "analysis", "severity": "major", "text": "UAT AYRI BULGU: Başlığı gözden geçirin.",
         "evidence_ids": [passage["id"]]},
        {"target_id": "conclusion", "severity": "major", "text": "UAT SEÇİLİ BULGU: İmzalı tutanak yokluğunu belirtin.",
         "suggested_change": "Tutanağın doğrulanmadığını açıkça yazın.", "evidence_ids": [passage["id"]]},
    ])
    missing_rationale = {**body, "note": ""}
    assert reviewer.post(reviews, json=missing_rationale).status_code == 422
    bad_pin = {**body, "content_sha256": "0" * 64}
    assert reviewer.post(reviews, json=bad_pin).status_code == 409
    assert checked(reviewer.get(reviews, params=history_query)).json() == []
    event = checked(reviewer.post(reviews, json=body), 201).json()
    assert event["reviewer_id"] == reviewer_record["id"] and event["immutable"]
    assert event["source_selections"][0]["quote_sha256"] == sha(CLAUSE)
    assert event["note"] != event["findings"][1]["text"]
    assert checked(reviewer.post(reviews, json=body), 201).json() == event
    after_review = checked(owner.get(analyses)).json()[0]
    assert after_review["latest_version_id"] == draft["latest_version_id"]
    assert after_review["review"]["effective_state"] == "changes_requested"

    request = {"expected_revision": draft["revision"], "version_id": draft["latest_version_id"],
               "request_id": "b042" * 8, "mode": "single",
               "review_feedback": {"review_id": event["id"], "finding_indices": [1]}}
    context = suggestions + "/context-budget"
    disabled = checked(owner.post(context, json=request)).json()
    assert disabled["fits"] and not disabled["can_start"] and not disabled["configuration_ready"]
    seen = []

    def suggest(content, **options):
        seen.append(proposal_messages(content, repair=options["repair"], review_feedback=options["review_feedback"]))
        if len(seen) == 1:
            raise ProviderError("UAT INTERNAL FAULT", code="provider_output_incomplete")
        return json.dumps({
            "conclusion_update": {
                "text": "UAT: İmzalı tutanak doğrulanmadığı için ödeme koşulu belirsizdir.",
                "uncertainty": ["Tutanak örneği doğrulanmadı."], "next_step": "Özgün tutanağı kontrol edin.",
            },
            "feedback_responses": [{
                "finding_id": "finding:1", "outcome": "proposed_change", "edited_targets": ["conclusion"],
                "text": "UAT: Belirsizlik görünür kılındı.", "evidence_ids": [passage["id"]],
            }],
        }, ensure_ascii=False)

    configure_fixture_provider(app, monkeypatch, suggest)
    limit = checked(owner.post(context, json=request)).json()["prompt"]["total_upper_bound_units"]
    app.state.settings.provider_context_limit = limit - 1
    over = checked(owner.post(context, json=request)).json()
    assert over["excess_units"] == 1 and not over["can_start"]
    assert owner.post(suggestions, json={**request, "context_preview_sha256": over["preview_sha256"]}).status_code == 422
    assert seen == [] and checked(owner.get(suggestions)).json() == []
    app.state.settings.provider_context_limit = limit
    fit = checked(owner.post(context, json=request)).json()
    assert fit["can_start"] and fit["remaining_units"] == 0
    assert fit["evidence"][0]["quote_sha256"] == sha(CLAUSE)
    assert CLAUSE not in json.dumps(fit, ensure_ascii=False)
    assert owner.post(suggestions, json={**request, "context_preview_sha256": over["preview_sha256"]}).status_code == 409

    queued = checked(owner.post(suggestions, json={**request, "context_preview_sha256": fit["preview_sha256"]}), 202)
    failure = finished(owner, suggestions, queued.json()["id"])
    assert failure["status"] == "failed" and failure["error_code"] == "provider_output_incomplete"
    assert "UAT INTERNAL FAULT" not in json.dumps(failure)
    assert not failure.get("candidate")
    assert checked(owner.get(analyses)).json()[0]["latest_version_id"] == draft["latest_version_id"]

    retry = {**request, "request_id": "b043" * 8, "context_preview_sha256": fit["preview_sha256"]}
    queued = checked(owner.post(suggestions, json=retry), 202)
    proposed = finished(owner, suggestions, queued.json()["id"])
    assert proposed["status"] == "completed" and proposed["can_adopt"]
    assert len(seen) == 2 and len(proposed["iterations"]) == 1
    assert proposed["iterations"][0]["prompt"] == fit["prompt"]
    messages = json.loads(seen[-1][-1]["content"])
    assert messages["evidence"][0]["text"] == CLAUSE
    serialized = json.dumps(seen[-1], ensure_ascii=False)
    assert "UAT SEÇİLİ BULGU" in serialized
    for excluded in ("UAT AYRI BULGU", "UAT GENEL GEREKÇE", event["reviewer_name"], "UAT-FIXTURE-NOT-A-SECRET"):
        assert excluded not in serialized
    assert proposed["candidate"]["evidence"] == draft["evidence"]
    assert checked(owner.get(analyses)).json()[0]["version"] == 1

    adopted = checked(adopt(owner, suggestions, draft, proposed), 201).json()
    assert adopted["version"] == 2 and adopted["authorship"] == "user_with_ai_assistance"
    assert adopted["ai_assistance"]["provider"]["model"] == "UAT-DETERMINISTIC-FIXTURE"
    assert adopted["review"]["effective_state"] == "unreviewed" and adopted["checks"]["legal_approval"] == "not_granted"
    assert checked(reviewer.get(reviews, params=history_query)).json() == [event]
    assert adopt(owner, suggestions, draft, proposed).status_code == 409
    assert checked(owner.get(suggestions + "/" + failure["id"])).json()["status"] == "failed"

    confirmation, review_context = review_request(reviewer, reviews, adopted)
    confirmation.update(request_id="b044" * 8, note="UAT: Özgün pasaj ve varsayım sınırı koşullu taslakta kontrol edildi.")
    assert review_context["can_accept"] and review_context["ai_contribution_required"]
    accepted = checked(reviewer.post(reviews, json=confirmation), 201).json()
    assert accepted["scope"] == "conditional_private_draft_only"
    latest = checked(owner.get(analyses)).json()[0]
    assert latest["status"] == "reviewed" and latest["stored_status"] == "needs_review"
    assert latest["checks"]["legal_approval"] == "not_granted"

    def export_text(client, version, format):
        response = checked(client.get(current + "/export", params={"version_id": version, "format": format}))
        assert response.headers["cache-control"] == "no-store"
        reader = io.BytesIO(response.content)
        if format == "docx":
            return "\n".join(p.text for p in Document(reader).paragraphs)
        return "\n".join(p.extract_text() for p in PdfReader(reader).pages)

    docx = export_text(owner, adopted["latest_version_id"], "docx")
    assert all(fragment in docx for fragment in (
        CLAUSE, "uat-grounding.txt", "Paragraf 1", sha(CLAUSE), sha(SOURCE), accepted["content_sha256"],
        confirmation["note"], "reviewed_conditional", "Hukuki onay verilmedi",
    ))
    pdf = export_text(reviewer, draft["latest_version_id"], "pdf")
    assert all(fragment in pdf for fragment in (CLAUSE, "Paragraf 1", "changes_requested", "withheld"))
    versions = checked(owner.get(current + "/versions")).json()
    assert [row["version"] for row in versions] == [2, 1]
    assert [row["review"]["latest"]["id"] for row in versions] == [accepted["id"], event["id"]]

    checked(owner.patch(base + "/facts/" + fact["id"], json={
        "text": "UAT: Tutanak hakkında yeni itiraz.", "status": "disputed", "reason": "UAT kapsam düzeltmesi",
    }))
    stale = checked(owner.get(analyses)).json()[0]
    assert stale["status"] == "stale" and stale["review"]["effective_state"] == "stale"
    stale_body, stale_context = review_request(reviewer, reviews, adopted)
    assert not stale_context["can_accept"] and reviewer.post(reviews, json=stale_body).status_code == 409
    stale_docx = export_text(owner, adopted["latest_version_id"], "docx")
    assert "Güncellik: stale" in stale_docx and "Sonuç değerlendirmesi: withheld" in stale_docx
    assert checked(reviewer.get(reviews, params={"version_id": adopted["latest_version_id"]})).json() == [accepted]
    assert checked(owner.get(original + "/original")).content == SOURCE.encode()
    assert checked(unassigned.get(API + "/auth/me")).json()["user"]["id"] == outsider["id"]


def test_buat_05_supervisor_revision_and_recipient_revocation(uat):
    _, owner, actor = uat
    admin = checked(owner.get(API + "/auth/me")).json()["user"]["id"]
    first = create_employee(owner, "uat-opinion-first")
    second = create_employee(owner, "uat-opinion-second")
    outsider = create_employee(owner, "uat-opinion-unassigned")
    case = workspace(owner, "UAT independent human opinions")["id"]
    team(owner, case, [{"user_id": admin, "supervisor": True}, {"user_id": first["id"]}, {"user_id": second["id"]}])
    colleague, other = actor("uat-opinion-first"), actor("uat-opinion-second")
    items = f"{API}/workspaces/{case}/work"
    assert owner.post(items, json={
        "kind": "opinion", "title": "UAT unauthorized recipient", "description": "UAT",
        "due_local": "2020-01-01T01:00", "assignee_ids": [outsider["id"]],
    }).status_code == 422
    item = create_work(owner, case, [first["id"], second["id"]], due_local="2020-01-01T01:00",
                       title="UAT ayrı görüş isteği", description="İmzalı tutanak yokluğunun etkisini ayrı değerlendir.")
    assert item["due_at"] == "2019-12-31T22:00:00+00:00" and item["time_zone"] == "Europe/Istanbul"
    endpoint = work_path(case, item)
    queue = checked(colleague.get(API + "/work", params={"bucket": "overdue"})).json()["items"]
    assert {row["id"] for row in queue} == {item["id"]}

    def submit(client, ident, text):
        visible = checked(client.get(endpoint)).json()
        assert [r["user_id"] for r in visible["responses"]] == [ident]
        revision = visible["responses"][0]["revision"]
        result = checked(client.post(endpoint + "/submissions", json={"revision": revision, "text": text})).json()
        response = response_for(result, ident)
        submitted = [entry for entry in response["history"] if entry["action"] == "submitted"][-1]
        assert submitted["actor_id"] == ident and submitted["authorship"] == "human_account"
        return {"revision": response["revision"], "submission_id": submitted["id"]}

    first_original = "UAT birinci avukatın özgün görüşü."
    first_revised = "UAT birinci avukatın düzeltilmiş görüşü."
    before = submit(colleague, first["id"], first_original)
    review = endpoint + "/responses/" + first["id"] + "/review"
    decision = {"decision": "revision_requested", "note": "UAT: Belirsizliği ayrıca yazın."}
    assert first_original not in checked(other.get(endpoint)).text
    assert colleague.post(review, json={**before, **decision}).status_code == 403
    changed = checked(owner.post(review, json={**before, **decision})).json()
    assert response_for(changed, second["id"])["status"] == "pending"
    after = submit(colleague, first["id"], first_revised)
    acceptance = {"decision": "accepted", "note": "UAT: Yeni yanıtın sınırları görüldü."}
    assert owner.post(review, json={**before, **acceptance}).status_code == 409
    accepted = checked(owner.post(review, json={**after, **acceptance})).json()
    first_history = response_for(accepted, first["id"])["history"]
    assert [e["text"] for e in first_history if e["action"] == "submitted"] == [first_original, first_revised]
    assert [e["actor_id"] for e in first_history if e["action"] == "reviewed"] == [admin, admin]
    submit(other, second["id"], "UAT ikinci avukatın bağımsız görüşü.")

    update = {key: accepted[key] for key in ("revision", "kind", "title", "description", "due_local", "status")}
    removed = checked(owner.put(endpoint, json={
        **update, "assignee_ids": [first["id"]], "reason": "UAT ikinci alıcı kaldırıldı.",
    })).json()
    assert not response_for(removed, second["id"])["active"]
    assert other.get(endpoint).status_code == 401
    login(other, "uat-opinion-second", PASSWORD)
    checked(other.get(f"{API}/workspaces/{case}"))  # independent case membership remains
    assert other.get(endpoint).status_code == 404
    assert checked(other.get(API + "/work")).json()["items"] == []


def test_buat_06_extractive_research_and_reversible_preservation(uat):
    _, owner, actor = uat
    create_employee(owner, "uat-research-outsider")
    outsider = actor("uat-research-outsider")
    case = workspace(owner, "UAT research and preservation")
    base = API + "/matters/" + case["id"]
    _, path = document(owner, base, "uat-research.txt", SOURCE.encode())
    run = checked(owner.post(base + "/research", json={"question": "Ödeme ve teslim tutanağı"}), 202).json()
    completed = finished(owner, base + "/research", run["id"])
    assert completed["status"] == "completed" and completed["product_id"]
    product = base + "/products/" + completed["product_id"]
    result = checked(owner.get(product)).json()
    assert result["status"] == "needs_review" and "legal_corpus_unqualified" in result["critical_gaps"]
    evidence = {e["id"]: e for e in result["evidence"]}
    assert result["claims"]
    for claim in result["claims"]:
        assert any(claim["text"] in evidence[eid]["text"] for eid in claim["evidence_ids"])
    assert any(e["text"] == SOURCE and e["document_sha256"] == sha(SOURCE) for e in evidence.values())
    assert owner.post(product + "/review", json={"decision": "approve"}).status_code == 409
    assert outsider.get(product).status_code == outsider.get(product + "/export").status_code == 404

    hold = checked(owner.post(base + "/legal-holds", json={
        "reason": "UAT özgün kaynak saklama", "authority_reference": "SYNTHETIC-UAT",
    }), 201).json()
    plan = checked(owner.post(base + "/erasure-plan")).json()
    assert plan["active_hold_ids"] == [hold["id"]] and not plan["archive_allowed"] and not plan["purge_allowed"]

    def archive():
        revision = checked(owner.get(base + "/governance")).json()["matter_revision"]
        return owner.post(base + "/archive", json={"reason": "UAT geçici arşiv", "expected_revision": revision})

    assert archive().status_code == 409
    assert checked(owner.get(path + "/original")).content == SOURCE.encode()
    checked(owner.post(base + "/legal-holds/" + hold["id"] + "/release", json={
        "reason": "UAT saklama kaldırıldı", "authority_reference": "SYNTHETIC-UAT-RELEASE",
    }))
    archived = checked(archive()).json()
    assert archived["restorable"] and not archived["physical_erasure"]
    assert owner.get(product).status_code == owner.get(path + "/original").status_code == 404
    archived_list = API + "/governance/archived-matters"
    assert case["id"] in {row["id"] for row in checked(owner.get(archived_list)).json()}
    restore = archived_list + "/" + case["id"] + "/restore"
    assert owner.post(restore, json={
        "reason": "UAT eski arşiv sürümü", "expected_revision": archived["revision"] + 1,
    }).status_code == 409
    checked(owner.post(restore, json={"reason": "UAT geri yükleme", "expected_revision": archived["revision"]}))
    assert checked(owner.get(path + "/original")).content == SOURCE.encode()
    restored = checked(owner.get(product)).json()
    assert restored["claims"] == result["claims"] and restored["evidence"] == result["evidence"]
    assert outsider.get(path + "/original").status_code == 404


def test_buat_07_unconfigured_graph_and_intake_fail_closed(uat, monkeypatch):
    from app.extraction_client import ExtractionError
    from app.scanner import MalwareDetected, ScannerUnavailable

    app, owner, actor = uat
    guest = actor()
    graph = API + "/graphs"
    assert guest.get(graph + "/coverage").status_code == 401
    coverage = checked(owner.get(graph + "/coverage")).json()
    assert coverage["corpus"]["status"] == "not_loaded"
    assert coverage["corpus"]["total_expected"] is None
    assert not coverage["ontology"]["national_legal_review_complete"]
    structure = checked(owner.get(graph + "/explore", params={
        "graph": "structure", "query": "Provision", "as_of": "1925-01-01",
    })).json()
    assert structure["mode"] == "catalog" and structure["nodes"]
    assert all(not n["legal_usable"] for n in structure["nodes"])
    assert owner.get(graph + "/explore", params={"as_of": "1925-02-31"}).status_code == 422
    assert owner.post(graph + "/tools/not-allowlisted", json={}).status_code == 422

    case = workspace(owner, "UAT scanner and extraction outage")
    base = API + "/matters/" + case["id"]
    _, path = document(owner, base, "uat-existing.txt", SOURCE.encode())
    # Switch only the disposable handler's admission branch. The existing
    # synthetic store is SQLite, and scanner/extractor results are fixtures.
    app.state.settings.demo_mode = False

    def incoming():
        return owner.post(base + "/documents", files={"file": ("uat-intake.txt", SOURCE.encode(), "text/plain")})

    assert incoming().status_code == 503  # no scanner
    app.state.settings.clamav_host = "uat-scanner-fixture.invalid"
    assert incoming().status_code == 503  # no isolated worker
    extraction_calls = []

    class UnavailableExtractor:
        def execute(self, content, suffix):
            extraction_calls.append((content, suffix))
            raise ExtractionError("UAT worker unavailable")

    def fail_scan(error):
        def scan(*_args, **_kwargs):
            raise error("UAT scanner diagnostic")

        monkeypatch.setattr("app.main.scan_document", scan)

    app.state.extractor = UnavailableExtractor()
    fail_scan(ScannerUnavailable)
    assert incoming().status_code == 503
    fail_scan(MalwareDetected)
    assert incoming().status_code == 422
    assert not extraction_calls
    assert len(checked(owner.get(base)).json()["documents"]) == 1
    assert checked(owner.get(path + "/original")).content == SOURCE.encode()
    monkeypatch.setattr("app.main.scan_document", lambda *_a, **_k: None)
    retained = checked(incoming(), 201).json()
    assert extraction_calls == [(SOURCE.encode(), ".txt")]
    assert retained["status"] == "failed" and not retained["passage_count"]
    assert "UAT worker unavailable" not in json.dumps(retained)
    assert checked(owner.get(base + "/documents/" + retained["id"] + "/original")).content == SOURCE.encode()


class KnownCorruptOriginalFailure(AssertionError):
    """Precisely matches BAUT-08's verified failure; unexpected outcomes fail."""


@pytest.mark.xfail(
    strict=True, raises=KnownCorruptOriginalFailure,
    reason="BAUT-08: corrupt encrypted private original returns generic HTTP 500, not controlled 409",
)
def test_buat_08_corrupt_private_original_returns_controlled_conflict(uat):
    from cryptography.fernet import InvalidToken

    app, owner, _ = uat
    case = workspace(owner, "UAT encrypted original corruption")
    base = API + "/matters/" + case["id"]
    source, path = document(owner, base, "uat-corruption.txt", SOURCE.encode())
    vault_file = app.state.settings.data_dir / "documents" / (source["id"] + ".enc")
    ciphertext = vault_file.read_bytes()
    original = path + "/original"
    vault_file.unlink()
    assert checked(owner.get(original), 409).json()["detail"] == "Özgün kaynak kullanılamıyor"
    vault_file.write_bytes(app.state.store.cipher.encrypt(b"UAT authenticated wrong original"))
    assert checked(owner.get(original), 409).json()["detail"] == "Özgün kaynak bütünlüğü doğrulanamadı"
    vault_file.write_bytes(b"!" + ciphertext[1:])
    try:
        # The already running fixture owns lifespan; this client shares only
        # the ASGI portal and receives the actual serialized HTTP error.
        wire = TestClient(app, raise_server_exceptions=False)
        wire.portal = owner.portal
        try:
            wire.cookies.update(owner.cookies)
            observed = wire.get(original)
        finally:
            wire.close()
        if observed.status_code == 500 and observed.text == "Internal Server Error":
            with pytest.raises(InvalidToken):
                owner.get(original)
            raise KnownCorruptOriginalFailure("expected controlled 409; observed generic 500 caused by InvalidToken")
        assert checked(observed, 409).json()["detail"] == "Özgün kaynak bütünlüğü doğrulanamadı"
        assert SOURCE not in observed.text
    finally:
        vault_file.write_bytes(ciphertext)
