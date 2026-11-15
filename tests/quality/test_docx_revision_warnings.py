"""Passage annotations on synthetic Word revisions preserve frozen text."""

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.parts.hdrftr import HeaderPart
from docx.text.paragraph import Paragraph
from docx_textbox_fixtures import alternate_textbox

from app import docx_extract
from app.extract import extract
from app.extraction_client import validate_result


def _text_change(paragraph, kind, text):
    wrapper = OxmlElement("w:" + kind)
    run = OxmlElement("w:r")
    token = OxmlElement("w:delText" if kind == "del" else "w:t")
    token.text = text
    run.append(token)
    wrapper.append(run)
    paragraph._p.append(wrapper)


def _observe(doc, tmp_path):
    source = tmp_path / "synthetic.docx"
    doc.save(source)
    original = source.read_bytes()
    baseline = validate_result(extract(source, ".docx"), ".docx")
    enriched = validate_result(docx_extract.add_docx_revision_warnings(source, baseline), ".docx")
    assert source.read_bytes() == original
    assert {k: v for k, v in enriched.items() if k != "warnings"} == {
        k: v for k, v in baseline.items() if k != "warnings"
    }
    assert enriched["warnings"][:len(baseline["warnings"])] == baseline["warnings"]
    return baseline, enriched["warnings"][len(baseline["warnings"]):]


def test_exact_paragraph_binding_and_omitted_revision_context(tmp_path):
    doc = Document()
    changed = doc.add_paragraph("Ödeme süresi:  iş günü.")
    _text_change(changed, "del", "15")
    _text_change(changed, "ins", "30")
    doc.add_paragraph("Ödeme süresi:  iş günü.")
    _text_change(doc.add_paragraph(), "moveTo", "Yeni ve tamamen izlenen paragraf.")
    wrapped = doc.add_paragraph("Tamamı silinen blok.")
    wrapper = OxmlElement("w:del")
    wrapped._p.addprevious(wrapper)
    wrapper.append(wrapped._p)
    baseline, warnings = _observe(doc, tmp_path)
    assert baseline["passages"] == [
        {"locator": "Paragraf 1", "text": "Ödeme süresi:  iş günü."},
        {"locator": "Paragraf 2", "text": "Ödeme süresi:  iş günü."},
    ]
    assert docx_extract.DOCUMENT_WARNING in baseline["warnings"]
    assert warnings == ["Paragraf 1: İzlenen değişiklik var; özgün pasajı inceleyin.", docx_extract.UNBOUND_WARNING]


def test_collapsed_row_and_inherited_formatted_headers_keep_exact_context(tmp_path):
    doc = Document()
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Tutar"
    amount = table.cell(0, 1).paragraphs[0]
    amount.text = "TL"
    _text_change(amount, "ins", "500")
    story = doc.sections[0].header.paragraphs[0]
    story.text = "Örnek kayıt"
    story._p.get_or_add_pPr().append(OxmlElement("w:pPrChange"))
    doc.add_section(WD_SECTION_START.NEW_PAGE)
    baseline, warnings = _observe(doc, tmp_path)
    assert baseline["passages"][0]["locator"] == "Tablo 1, satır 1"
    assert warnings == [
        "Tablo 1, satır 1: İzlenen değişiklik var; özgün pasajı inceleyin.",
        "Bölüm 1, üstbilgi tanımı (varsayılan; kaynak bölüm 1), paragraf 1: "
        "İzlenen değişiklik var; özgün pasajı inceleyin.",
        "Bölüm 2, üstbilgi tanımı (varsayılan; kaynak bölüm 1), paragraf 1: "
        "İzlenen değişiklik var; özgün pasajı inceleyin.",
    ]


def test_clean_baseline_and_probe_failure_preserve_original_output(tmp_path, monkeypatch):
    doc = Document()
    paragraph = doc.add_paragraph("Vade tarihi.")
    assert _observe(doc, tmp_path)[1] == []
    _text_change(paragraph, "ins", "30.09.2026")
    monkeypatch.setattr(docx_extract, "_MAX_PROBE_BYTES", 1)
    assert _observe(doc, tmp_path)[1] == [docx_extract.UNKNOWN_WARNING]


def test_unvisited_source_keeps_warning_even_with_bound_body_revision(tmp_path):
    doc = Document()
    body = doc.add_paragraph("Gövde koşulu.")
    _text_change(body, "del", "Eski koşul.")
    orphan_header = HeaderPart.new(doc.part.package)
    doc.part.relate_to(orphan_header, RT.HEADER)
    header = Paragraph(orphan_header.element[0], orphan_header)
    header.text = "Bağlanmamış üstbilgi."
    _text_change(header, "ins", "Bu koşul gövdeye ait değildir.")
    _, warnings = _observe(doc, tmp_path)
    assert warnings == [
        "Paragraf 1: İzlenen değişiklik var; özgün pasajı inceleyin.",
        docx_extract.UNBOUND_WARNING,
    ]


def test_equivalent_textbox_branches_bind_one_passage_without_marking_host(tmp_path):
    doc = Document()
    box = Document()
    clause = box.add_paragraph("Kutudaki koşul.")
    clause._p.get_or_add_pPr().append(OxmlElement("w:pPrChange"))
    alternate_textbox(doc.add_paragraph("Bağlayıcı paragraf."), box)
    _, warnings = _observe(doc, tmp_path)
    assert warnings == [
        docx_extract.DOCUMENT_WARNING,
        "Paragraf 1, metin kutusu 1, paragraf 1: İzlenen değişiklik var; özgün pasajı inceleyin.",
    ]
