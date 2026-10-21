import zipfile
from email.message import EmailMessage

import pytest
from pptx import Presentation

from app.extract import extract


def write(tmp_path, suffix, content):
    path = tmp_path / ("input" + suffix)
    path.write_bytes(content)
    return path


def test_html_never_returns_script_or_embedded_object(tmp_path):
    path = write(
        tmp_path,
        ".html",
        b"<p>Contract</p><script>steal()</script><style>hide</style><iframe>remote</iframe><p>Term</p>",
    )
    output = extract(path, ".html")
    assert output["passages"][0]["text"] == "Contract\nTerm"
    assert output["warnings"]


def test_email_attachment_is_explicitly_unprocessed(tmp_path):
    mail = EmailMessage()
    mail["Subject"] = "İş sözleşmesi"
    mail["From"] = "example@example.invalid"
    mail.set_content("Ödeme 30 gün içinde yapılır.")
    mail.add_attachment(
        b"Never parse this automatically",
        maintype="application",
        subtype="octet-stream",
        filename="private.bin",
    )
    result = extract(write(tmp_path, ".eml", mail.as_bytes()), ".eml")
    assert any("30 gün" in p["text"] for p in result["passages"])
    assert not any("Never parse" in p["text"] for p in result["passages"])
    assert any("1 ek işlenmedi" in w for w in result["warnings"])


def test_presentation_has_slide_locators_and_omission_warning(tmp_path):
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = "Ticari uyuşmazlık"
    slide.placeholders[1].text = "İddia ile bulgu ayrılır."
    path = tmp_path / "input.pptx"
    deck.save(path)
    result = extract(path, ".pptx")
    assert result["page_count"] == 1
    assert result["passages"][0]["locator"].startswith("Slayt 1")
    assert any("İddia" in p["text"] for p in result["passages"])
    assert result["warnings"]


@pytest.mark.parametrize("suffix", [".odt", ".ods", ".odp"])
def test_opendocument_bounded_paragraphs_and_repeated_cells(tmp_path, suffix):
    path = tmp_path / ("input" + suffix)
    content = """<office xmlns:t="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
        xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0">
        <table:table-row table:number-rows-repeated="999999999"><t:p>İşlem</t:p></table:table-row></office>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("content.xml", content)
    result = extract(path, suffix)
    assert [p["text"] for p in result["passages"]] == ["İşlem"]
    assert any("çoğaltılmadı" in w for w in result["warnings"])


def test_xml_entities_and_office_macros_rejected(tmp_path):
    path = tmp_path / "input.odt"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "content.xml", '<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><x>&secret;</x>'
        )
    from defusedxml.common import DefusedXmlException

    with pytest.raises(DefusedXmlException):
        extract(path, ".odt")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/vbaProject.bin", b"macro")
    with pytest.raises(ValueError, match="Macros"):
        extract(path, ".docx")


def test_rtf_unicode_and_invalid_header(tmp_path):
    result = extract(write(tmp_path, ".rtf", rb"{\rtf1\ansi \u304?\u351? hukuku}"), ".rtf")
    assert result["passages"][0]["text"] == "İş hukuku"
    with pytest.raises(ValueError, match="RTF"):
        extract(write(tmp_path, ".rtf", b"not rtf"), ".rtf")


def test_legacy_failure_and_supplied_udf_remain_visible(tmp_path):
    for suffix in (".doc", ".xls", ".msg", ".udf"):
        with pytest.raises(Exception):
            extract(write(tmp_path, suffix, b"not a valid document"), suffix)


def test_xlsx_formula_is_literal_and_csv_keeps_row_locator(tmp_path):
    from openpyxl import Workbook

    book = Workbook()
    book.active["A1"] = '=WEBSERVICE("https://example.invalid")'
    path = tmp_path / "input.xlsx"
    book.save(path)
    result = extract(path, ".xlsx")
    assert "=WEBSERVICE" in result["passages"][0]["text"]
    assert any("çalıştırılmadı" in w for w in result["warnings"])
    result = extract(write(tmp_path, ".csv", "isim,tutar\nörnek,30".encode()), ".csv")
    assert result["passages"][1] == {"locator": "Satır 2", "text": "örnek | 30"}


def test_docx_interleaves_tables_with_clauses_without_renumbering(tmp_path):
    from docx import Document

    from app.extract import DOCX_BODY_PROFILE

    doc = Document()
    doc.add_paragraph("SENTETİK: Tablodaki tutar kabul edilmedi.")
    doc.add_table(rows=1, cols=2).rows[0].cells[0].text = "1.234,56 TL"
    doc.tables[0].cell(0, 1).text = "14.06.2020"
    doc.add_paragraph("")  # Empty body paragraph still has its own locator.
    doc.add_paragraph("SENTETİK: Önceki tablodaki tarih kesinleşmedi.")
    doc.add_table(rows=1, cols=1).cell(0, 0).text = "İkinci tablo: TEST-0042"
    doc.add_paragraph("SENTETİK: Son hüküm.")
    path = tmp_path / "input.docx"
    doc.save(path)
    original = path.read_bytes()
    result = extract(path, ".docx")
    assert result["passages"] == [
        {"locator": "Paragraf 1", "text": "SENTETİK: Tablodaki tutar kabul edilmedi."},
        {"locator": "Tablo 1, satır 1", "text": "1.234,56 TL | 14.06.2020"},
        {"locator": "Paragraf 3", "text": "SENTETİK: Önceki tablodaki tarih kesinleşmedi."},
        {"locator": "Tablo 2, satır 1", "text": "İkinci tablo: TEST-0042"},
        {"locator": "Paragraf 4", "text": "SENTETİK: Son hüküm."},
    ]
    assert result["extraction_profile"] == DOCX_BODY_PROFILE
    assert result["passage_count"] == 5 and path.read_bytes() == original


def test_docx_nested_tables_remain_explicitly_unprocessed(tmp_path):
    from docx import Document

    doc = Document()
    cell = doc.add_table(rows=1, cols=1).cell(0, 0)
    cell.text = "SENTETİK: Dış hücre."
    cell.add_table(rows=1, cols=1).cell(0, 0).text = "İç tablo: işlenmemiş koşul."
    path = tmp_path / "input.docx"
    doc.save(path)
    result = extract(path, ".docx")
    assert [p["text"] for p in result["passages"]] == ["SENTETİK: Dış hücre."]
    assert any("İç içe tabloların içeriği işlenmedi" in warning for warning in result["warnings"])
    assert any("dipnot" in warning for warning in result["warnings"])
