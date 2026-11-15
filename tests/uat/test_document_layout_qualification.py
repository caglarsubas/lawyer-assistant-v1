"""Synthetic layout intake with exact private source and review preservation."""

import json
import subprocess
import sys
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from docx.oxml.ns import qn
from fastapi.testclient import TestClient
from lxml import etree
from sqlalchemy import select
from test_analysis_reviews import review_request
from test_content_scope import team
from test_delivered_workflows import API, SOURCE, analysis_input, checked, document, sha, uat  # noqa: F401
from test_firm_admin import create_employee
from test_portfolio import workspace

from app import main
from app.db import Audit, Record
from app.extraction_client import validate_result
from app.extraction_runtime import create_app
from scripts.document_layout_cases import make_docx_case, make_pdf_case

WORKER_TOKEN = "synthetic-layout-qualification-token-only"

PDF_PARSER_WITH_OCR_STUBS = """
import json
import runpy
import subprocess
import sys
from types import ModuleType

from PIL import Image

expected = {int(page): text for page, text in json.loads(sys.argv.pop()).items()}
attempted = []
transcribed = []

def rasterize(command, *, check, capture_output, timeout):
    page = int(command[2])
    assert page in expected and check and capture_output and timeout == 6
    assert command[:-1] == [
        "pdftoppm", "-f", str(page), "-l", str(page), "-singlefile",
        "-scale-to", "2000", "-png", sys.argv[1],
    ]
    attempted.append(page)
    Image.new("L", (16, 16), color=page).save(command[-1] + ".png")
    return subprocess.CompletedProcess(command, 0, b"", b"")

def transcribe(picture, *, lang, timeout):
    assert lang == "tur+eng" and 0 < timeout <= 6
    page = picture.getpixel((0, 0))
    transcribed.append(page)
    return expected[page]

ocr = ModuleType("pytesseract")
ocr.image_to_string = transcribe
sys.modules["pytesseract"] = ocr
subprocess.run = rasterize
try:
    runpy.run_module("app.pdf_scan_extract", run_name="__main__")
except SystemExit as exc:
    if exc.code not in (None, 0):
        raise
assert attempted == transcribed == sorted(expected)
"""


def stub_pdf_tools(monkeypatch, case):
    # Keep the real parser subprocess, PDF reader and worker response. Substitute
    # only the two native OCR programs, which are absent on CI hosts.
    popen = subprocess.Popen
    argv = [sys.executable, "-m", "app.pdf_scan_extract"]
    admitted = {page: dict(case.expected_passages)[f"Sayfa {page}"] for page in (3, 4, 5)}

    def with_test_tools(command, **kwargs):
        if command[:3] == argv and command[-1] == ".pdf":
            command = [
                sys.executable, "-c", PDF_PARSER_WITH_OCR_STUBS, *command[3:],
                json.dumps(admitted, ensure_ascii=False),
            ]
        return popen(command, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", with_test_tools)


def with_tracked_opening(case):
    stream = BytesIO()
    with ZipFile(BytesIO(case.content)) as source, ZipFile(stream, "w") as target:
        for member in source.infolist():
            data = source.read(member)
            if member.filename == "word/document.xml":
                body = etree.fromstring(data).find(qn("w:body"))
                paragraph = body.find(qn("w:p"))
                for marker, text_tag, text in (
                    ("w:del", "w:delText", "Silinen sentetik ifade."),
                    ("w:ins", "w:t", "Eklenen sentetik ifade."),
                ):
                    revision = etree.SubElement(paragraph, qn(marker))
                    run = etree.SubElement(revision, qn("w:r"))
                    etree.SubElement(run, qn(text_tag)).text = text
                data = etree.tostring(body.getparent())
            target.writestr(member, data)
    return replace(case, content=stream.getvalue())


@pytest.fixture
def layout_worker():
    with TestClient(create_app(WORKER_TOKEN)) as client:
        def execute(content, suffix):
            response = checked(client.post("/extract", content=content, headers={
                "Authorization": f"Bearer {WORKER_TOKEN}",
                "Content-Type": "application/octet-stream",
                "X-Document-Suffix": suffix,
            }))
            return validate_result(response.json(), suffix)

        yield SimpleNamespace(execute=execute)


def record_snapshot(store, identities):
    with store.session() as session:
        records = session.scalars(select(Record).where(Record.id.in_(identities)))
        return {row.id: (row.revision, row.payload) for row in records}


def review_audits(store):
    with store.session() as session:
        return set(session.scalars(select(Audit.id).where(Audit.action == "analysis_review_recorded")))


def test_mixed_layouts_preserve_exact_originals_and_prior_review(uat, monkeypatch, layout_worker):  # noqa: F811
    app, owner, actor = uat
    owner_id = checked(owner.get(API + "/auth/me")).json()["user"]["id"]
    reviewer_record = create_employee(owner, "layout-independent-reviewer")
    create_employee(owner, "layout-unassigned-lawyer")
    matter = workspace(owner, "Synthetic layout and review")["id"]
    unrelated = workspace(owner, "Synthetic unrelated matter")["id"]
    team(owner, matter, [{"user_id": owner_id}, {"user_id": reviewer_record["id"]}])
    reviewer, outsider = actor("layout-independent-reviewer"), actor("layout-unassigned-lawyer")
    base = API + "/matters/" + matter

    prior, prior_path = document(owner, base, "layout-prior.txt", SOURCE.encode())
    passage = prior["passages"][0]
    fact = checked(owner.post(base + "/facts", json={
        "text": "Sentetik teslim koşulu", "status": "documented", "evidence_id": passage["id"],
    }), 201).json()
    analyses = base + "/analyses"
    draft = checked(owner.post(analyses, json=analysis_input(passage, prior, fact)), 201).json()
    analysis = analyses + "/" + draft["id"]
    version = {"version_id": draft["latest_version_id"]}
    reviews = analysis + "/reviews"
    body, _ = review_request(reviewer, reviews, draft, decision="changes_requested")
    decision = checked(reviewer.post(reviews, json=body), 201).json()
    assert checked(reviewer.get(reviews, params=version)).json() == [decision]
    history = checked(owner.get(analysis + "/versions")).json()
    protected = (prior["id"], fact["id"], draft["id"], version["version_id"], decision["id"])
    frozen = record_snapshot(app.state.store, protected)
    audit_ids = review_audits(app.state.store)
    assert len(frozen) == len(protected) and len(audit_ids) == 1
    vault = app.state.settings.data_dir / "documents"
    prior_bytes = (vault / (prior["id"] + ".enc")).read_bytes()

    # The app bundles this font. No environment fonts or case documents are used.
    font = Path(__file__).resolve().parents[2] / "backend/app/assets/NotoSans-Regular.ttf"
    pdf, docx = make_pdf_case(font), with_tracked_opening(make_docx_case())
    scanned = []

    def scan_synthetic(content, host, **kwargs):
        assert host == "synthetic-layout-scanner"
        scanned.append(content)

    # From this point exercise the app's production upload path. The scanner is
    # synthetic and the extraction transport stays in-process without sockets.
    monkeypatch.setattr(app.state.settings, "demo_mode", False)
    monkeypatch.setattr(app.state.settings, "clamav_host", "synthetic-layout-scanner")
    monkeypatch.setattr(main, "scan_document", scan_synthetic)
    monkeypatch.setattr(app.state, "extractor", layout_worker)
    stub_pdf_tools(monkeypatch, pdf)
    for case in (pdf, docx):
        source, path = document(owner, base, case.filename, case.content)
        actual = [(item["locator"], item["text"]) for item in source["passages"]]
        assert actual == list(case.expected_passages)
        assert all(item["text_sha256"] == sha(item["text"]) for item in source["passages"])
        assert all(text not in "\n".join(value for _, value in actual) for _, text in case.omitted_passages)
        encrypted = (vault / (source["id"] + ".enc")).read_bytes()
        assert encrypted != case.content and app.state.store.cipher.decrypt(encrypted) == case.content
        if case is pdf:
            assert source["page_count"] == 6
            warnings = source["extraction_warnings"]
            assert [warning for warning in warnings if "OCR kullanıldı" in warning] == [
                f"Sayfa {page}: OCR kullanıldı; görüntüyle doğrulayın." for page in (3, 4, 5)
            ]
            assert [warning for warning in warnings if warning.startswith("Sayfa 2:")] == [
                "Sayfa 2: Görsel içerik OCR ile işlenmedi. Özgün sayfayı kontrol edin."
            ]
            assert not any(warning.startswith("Sayfa 1:") for warning in warnings)
            assert "Sayfa 6: içerik işlenemedi; bu çalışmaya dahil edilmedi." in warnings
            assert "PDF okuma sırası ve tablo düzeni insan incelemesi gerektirir." in warnings
            # Page 2's raster body is skipped even with all three OCR slots
            # still available. Its native metadata remains a passage.
            assert {locator for locator, _ in case.omitted_passages} == {"Sayfa 2", "Sayfa 6"}
        else:
            assert source["extraction_profile"] == "docx-textboxes-v5"
            assert [warning for warning in source["extraction_warnings"] if "özgün pasajı" in warning] == [
                "Paragraf 1: İzlenen değişiklik var; özgün pasajı inceleyin.",
            ]
            assert "İzlenen değişiklikler var; kabul edilmiş sürüm doğrulanmadı." in source["extraction_warnings"]
        for suffix in ("", "/original"):
            for denied in (outsider.get(path + suffix), owner.get(path.replace(matter, unrelated) + suffix)):
                assert denied.status_code == 404
                assert case.filename not in denied.text and sha(case.content) not in denied.text
        original = checked(reviewer.get(path + "/original"))
        assert original.content == case.content and original.headers["cache-control"] == "no-store"
        assert checked(reviewer.get(path)).json()["extraction_warnings"] == source["extraction_warnings"]

    assert scanned == [pdf.content, docx.content]
    assert checked(owner.get(prior_path)).json() == prior
    assert checked(owner.get(prior_path + "/original")).content == SOURCE.encode()
    assert (vault / (prior["id"] + ".enc")).read_bytes() == prior_bytes
    assert record_snapshot(app.state.store, protected) == frozen
    assert checked(owner.get(analysis + "/versions")).json() == history
    assert checked(reviewer.get(reviews, params=version)).json() == [decision]
    assert review_audits(app.state.store) == audit_ids
    assert outsider.get(reviews, params=version).status_code == 404
