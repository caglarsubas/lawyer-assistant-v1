"""Synthetic PDF engineering checks; no real legal review or parser accuracy score."""

import importlib.util
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pypdf
import pytest
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject

from app import registered_pdf_transcription as pdf
from app.public_sources import PublicSourceStore, _json, _validate
from app.registered_source_preparation import (
    PreparationError,
    capture_acquisition,
    encode,
    prepare,
    sha,
)
from app.source_gateway import HTML_REGISTRY_VERSION, REGISTRY_VERSION, registered


def fixture_pdf(*, count=2, content=b"SYNTHETIC fixture", root_key=None, page_key=None, encrypted=False):
    writer = pypdf.PdfWriter()
    for _ in range(count):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        if content:
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 50 700 Td (" + content + b") Tj ET")
            page[NameObject("/Contents")] = writer._add_object(stream)
        if page_key:
            page[NameObject(page_key)] = ArrayObject()
    if root_key:
        writer.root_object[NameObject(root_key)] = DictionaryObject()
    if encrypted:
        writer.encrypt("synthetic password")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def acquisition(raw=None):
    raw = fixture_pdf() if raw is None else raw
    source_id = "adalet-6101-pdf"
    source = registered(source_id)
    now = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    manifest = {
        "schema_version": "registered-source-acquisition-v1", "registry_version": REGISTRY_VERSION,
        "registry_id": source_id, "title": source.title, "source_url": source.url,
        "source_version_id": f"{source_id}:sha256:{sha(raw)}", "domain": source.domain,
        "started_at": now, "acquired_at": now, "raw_sha256": sha(raw), "byte_count": len(raw),
        "raw_media_type": source.media_type, "rights_status": "rights_pending", "review_status": "legal_review_pending",
        "publication_status": "quarantined", "content_status": "untrusted_unscanned",
        "extraction_status": "not_processed", "representation": source.representation, "current_consolidation": False,
        "limitations": [source.limitation,
            "Public availability does not establish permitted use, source identity review or legal applicability.",
            "This acquisition is unscanned and unparsed; admission and legal review are separate steps."],
    }
    return {"raw.pdf": raw, "acquisition.json": encode(manifest)}


@pytest.fixture
def cli():
    path = Path(__file__).resolve().parents[2] / "scripts/prepare_public_source.py"
    spec = importlib.util.spec_from_file_location("pdf_preparation_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_pages_hashes_offsets_and_pending_states():
    files = acquisition()
    artifacts = prepare(files)
    metadata, locators, text = _validate({name: artifacts[name] for name in (
        "raw.bin", "text.txt", "source.json", "locators.json")})
    report = _json(artifacts["preparation.json"])
    pdf.validate_pdf_report(report, locators, text)
    assert text == "SYNTHETIC fixture\n\nSYNTHETIC fixture"
    assert report["page_count"] == len(locators.passages) == 2
    assert report["parser_version"] == pypdf.__version__ == pdf.PARSER_VERSION
    assert report["adapter_version"] == pdf.ADAPTER_VERSION
    assert report["representation"] == "institution_hosted_text"
    assert report["rights_status"] == "rights_pending" and report["review_status"] == "legal_review_pending"
    assert all(report[key] is False for key in ("current_consolidation", "extraction_fidelity_verified",
                                               "source_identity_verified", "sensitivity_reviewed"))
    assert all(metadata[key] is None for key in ("published_on", "effective_from", "effective_until"))
    assert artifacts["raw.bin"] == files["raw.pdf"]
    assert artifacts["acquisition.json"] == files["acquisition.json"]


def test_glyphs_and_internal_whitespace_are_never_repaired(monkeypatch):
    text = "ĠĢ ġ ı Ş  two  spaces\nMADDE\nnext"
    monkeypatch.setattr(pdf, "extract_pages", lambda _: [text])
    assert prepare(acquisition())["text.txt"].decode() == text


@pytest.mark.parametrize("kwargs,diagnostic", [
    ({"encrypted": True}, "Encrypted"), ({"count": 51}, "page budget"),
    ({"content": b""}, "requires OCR"), ({"page_key": "/Annots"}, "annotations"),
    ({"page_key": "/AA"}, "annotations"),
    *[({"root_key": key}, "Interactive") for key in (
        "/OpenAction", "/AA", "/AcroForm", "/Collection", "/OCProperties")],
])
def test_unsupported_pdf_features_fail_whole_preparation(kwargs, diagnostic):
    with pytest.raises(PreparationError, match=diagnostic):
        prepare(acquisition(fixture_pdf(**kwargs)))


@pytest.mark.parametrize("raw", [b"not a pdf", b"%PDF-1.7\nbroken\n%%EOF", fixture_pdf()[:-10],
                                 fixture_pdf() + b"arbitrary trailing bytes"])
def test_malformed_pdf_is_not_repaired_or_partially_emitted(raw):
    with pytest.raises(PreparationError):
        prepare(acquisition(raw))


@pytest.mark.parametrize("limit,value", [("MAX_PAGES", 1), ("MAX_PAGE_CHARACTERS", 5),
                                       ("MAX_PAGE_STREAM_BYTES", 1), ("MAX_TOTAL_STREAM_BYTES", 1)])
def test_budgets_are_fail_closed(monkeypatch, limit, value):
    monkeypatch.setattr(pdf, limit, value)
    with pytest.raises(PreparationError, match="budget"):
        prepare(acquisition())


def test_unevaluated_parser_and_library_diagnostics_fail_safely(monkeypatch):
    monkeypatch.setattr(pypdf, "__version__", "unevaluated")
    with pytest.raises(PreparationError, match="version requires evaluation"):
        prepare(acquisition())
    monkeypatch.setattr(pypdf, "__version__", pdf.PARSER_VERSION)
    def broken(*args, **kwargs):
        raise RuntimeError("private path and untrusted diagnostic")
    monkeypatch.setattr(pypdf, "PdfReader", broken)
    with pytest.raises(PreparationError) as error:
        prepare(acquisition())
    assert str(error.value) == "PDF could not be transcribed exactly"


@pytest.mark.parametrize("key", ["/JavaScript", "/EmbeddedFiles"])
def test_named_active_or_embedded_content_is_rejected(key):
    writer = pypdf.PdfWriter()
    writer.clone_document_from_reader(pypdf.PdfReader(io.BytesIO(fixture_pdf())))
    writer.root_object[NameObject("/Names")] = writer._add_object(DictionaryObject({
        NameObject(key): DictionaryObject()}))
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(PreparationError, match="Interactive"):
        prepare(acquisition(output.getvalue()))


def test_indirect_resource_dictionary_is_supported_without_extra_features():
    writer = pypdf.PdfWriter()
    writer.clone_document_from_reader(pypdf.PdfReader(io.BytesIO(fixture_pdf())))
    for page in writer.pages:
        page[NameObject("/Resources")] = writer._add_object(page["/Resources"])
    output = io.BytesIO()
    writer.write(output)
    assert prepare(acquisition(output.getvalue()))["text.txt"] == b"SYNTHETIC fixture\n\nSYNTHETIC fixture"


def test_mixed_text_and_empty_page_does_not_silently_omit_a_page():
    writer = pypdf.PdfWriter()
    writer.clone_document_from_reader(pypdf.PdfReader(io.BytesIO(fixture_pdf(count=1))))
    writer.add_blank_page(width=612, height=792)
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(PreparationError, match="requires OCR"):
        prepare(acquisition(output.getvalue()))


@pytest.mark.parametrize("feature", ["image", "control"])
def test_unprocessed_image_and_unsafe_text_fail(monkeypatch, feature):
    if feature == "control":
        from pypdf._page import PageObject
        monkeypatch.setattr(PageObject, "extract_text", lambda *args, **kwargs: "synthetic\u202e text")
        with pytest.raises(PreparationError, match="control characters"):
            prepare(acquisition())
        return
    writer = pypdf.PdfWriter()
    writer.clone_document_from_reader(pypdf.PdfReader(io.BytesIO(fixture_pdf())))
    writer.pages[0]["/Resources"][NameObject("/XObject")] = DictionaryObject({
        NameObject("/Fixture"): DictionaryObject()})
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(PreparationError, match="images and forms"):
        prepare(acquisition(output.getvalue()))


@pytest.mark.parametrize("change", ["wrong_page", "boolean_origin", "wrong_digest", "wrong_locator", "trailing_text"])
def test_page_origins_and_locator_scope_cannot_be_forged(change):
    artifacts = prepare(acquisition())
    _, locators, text = _validate({name: artifacts[name] for name in (
        "raw.bin", "text.txt", "source.json", "locators.json")})
    report = _json(artifacts["preparation.json"])
    if change == "wrong_page":
        report["passage_origins"][0]["page"] = 2
    elif change == "boolean_origin":
        report["passage_origins"][0]["page"] = True
    elif change == "wrong_digest":
        report["passage_origins"][0]["page_text_sha256"] = "0" * 64
    elif change == "wrong_locator":
        locators.passages[0].locator = "PDF page 999"
    else:
        text += "extra"
    with pytest.raises(PreparationError):
        pdf.validate_pdf_report(report, locators, text)


@pytest.mark.parametrize("change", ["filename", "extra", "old_version", "media", "representation"])
def test_inventory_and_manifest_fail_before_pdf_parser(monkeypatch, change):
    files = acquisition()
    if change == "filename":
        files["raw.html"] = files.pop("raw.pdf")
    elif change == "extra":
        files["raw.html"] = b"extra"
    else:
        manifest = _json(files["acquisition.json"])
        manifest[{"old_version": "registry_version", "media": "raw_media_type",
                  "representation": "representation"}[change]] = {
                      "old_version": HTML_REGISTRY_VERSION, "media": "text/html", "representation": "enacted_text"}[change]
        files["acquisition.json"] = encode(manifest)
    monkeypatch.setattr(pdf, "extract_pages", lambda _: pytest.fail("Unexpected PDF parsing"))
    with pytest.raises(PreparationError):
        prepare(files)


@pytest.fixture
def offline_workers(cli, monkeypatch, tmp_path):
    # Scanner observations here are invented; real CVD scanning is recorded separately.
    from test_registered_source_preparation import scan_receipt
    incoming, signatures = tmp_path / "input", tmp_path / "signatures"
    incoming.mkdir()
    signatures.mkdir()
    for name, raw in acquisition().items():
        (incoming / name).write_bytes(raw)
    for name in ("main.cvd", "daily.cvd", "bytecode.cvd"):
        (signatures / name).write_bytes(b"synthetic, unscanned database")
    events = []
    monkeypatch.setattr(cli, "image_id", lambda _: "sha256:" + "1" * 64)
    def execute(image, mounts, *, scanner=False, raw_filename="raw.html"):
        events.append("scan" if scanner else "parse")
        files = capture_acquisition(mounts[0][0])
        if scanner:
            assert raw_filename == "raw.pdf"
            return encode(scan_receipt(sha(files[raw_filename])))
        assert events == ["scan", "parse"]
        for name, raw in prepare(files).items():
            (mounts[1][0] / name).write_bytes(raw)
        return b""
    monkeypatch.setattr(cli, "execute", execute)
    return incoming, signatures, tmp_path / "prepared", events


def test_scan_first_then_parse_import_and_preserve_distinct_source(offline_workers, cli, tmp_path):
    incoming, signatures, destination, events = offline_workers
    before = capture_acquisition(incoming)
    result = cli.prepare_in_containers(incoming, signatures, destination)
    assert events == ["scan", "parse"] and result["passage_count"] == 2
    assert capture_acquisition(incoming) == before
    assert result["rights_approved"] is result["legal_approved"] is False
    store = PublicSourceStore(tmp_path / "separate-public-only")
    imported = store.import_package(metadata_path=destination / "source.json", raw_path=destination / "raw.bin",
                                    text_path=destination / "text.txt", locators_path=destination / "locators.json")
    assert imported["rights_status"] == "rights_pending" and imported["review_status"] == "legal_review_pending"
    assert imported["source_url"] == registered("adalet-6101-pdf").url


@pytest.mark.parametrize("field,value", [("page_count", True), ("page_count", 1), ("parser_version", "unknown"),
                                       ("passage_origins", []), ("elapsed_seconds", -1),
                                       ("limitations", []), ("representation", "enacted_text"),
                                       ("extraction_fidelity_verified", True), ("extra", "unreviewed")])
def test_host_rejects_tampered_pdf_report_before_publication(offline_workers, cli, monkeypatch, field, value):
    incoming, signatures, destination, events = offline_workers
    execute = cli.execute
    def tamper(image, mounts, **kwargs):
        result = execute(image, mounts, **kwargs)
        if not kwargs.get("scanner"):
            path = mounts[1][0] / "preparation.json"
            report = _json(path.read_bytes())
            report[field] = value
            path.write_bytes(encode(report))
        return result
    monkeypatch.setattr(cli, "execute", tamper)
    with pytest.raises(PreparationError):
        cli.prepare_in_containers(incoming, signatures, destination)
    assert events == ["scan", "parse"] and not destination.exists()


def test_failed_pdf_scan_never_reaches_parser(offline_workers, cli, monkeypatch):
    incoming, signatures, destination, events = offline_workers
    def rejected(image, mounts, **kwargs):
        assert kwargs.get("scanner") is True
        events.append("scan_failed")
        raise PreparationError("Offline worker rejected the operation")
    monkeypatch.setattr(cli, "execute", rejected)
    with pytest.raises(PreparationError):
        cli.prepare_in_containers(incoming, signatures, destination)
    assert events == ["scan_failed"] and not destination.exists()


def test_scanner_filename_is_closed_and_worker_stays_disconnected(cli):
    command = cli.worker_command("fixture", "sha256:" + "1" * 64, [], scanner=True, raw_filename="raw.pdf")
    assert command[-1] == "raw.pdf" and command[command.index("--network") + 1] == "none"
    assert "--read-only" in command and "--pull" in command
    assert command[command.index("--entrypoint") + 1] == "/usr/bin/env"
    with pytest.raises(PreparationError):
        cli.worker_command("fixture", "sha256:" + "1" * 64, [], scanner=True, raw_filename="../private")
