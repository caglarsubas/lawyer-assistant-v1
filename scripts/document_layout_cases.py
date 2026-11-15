"""Fresh invented legal-layout fixtures with independently declared text and locations."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


@dataclass(frozen=True)
class LayoutCase:
    filename: str
    content: bytes
    expected_passages: tuple[tuple[str, str], ...]
    omitted_passages: tuple[tuple[str, str], ...] = ()


def make_pdf_case(font_path: Path) -> LayoutCase:
    """Build six PDF pages with native text, one mixed page and a bounded scan sequence."""
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    pdf_stream = BytesIO()
    pdf = canvas.Canvas(pdf_stream, pagesize=A4, invariant=1, pageCompression=1)
    pdf.setTitle("Sentetik dosya eki")
    width, height = A4
    font = ImageFont.truetype(str(font_path), 52)
    native_clause = "SENTETIK DOSYA A-42. Tutar: 1.234,56 TL."
    native_header = "SENTETIK DOSYA A-42. Ek tarih: 18.02.2024."
    admitted_scan_text = (
        "Borç kabul edilmedi.",
        "Ödeme şartı kesinleşmedi.",
        "İtiraz süresi başlamadı.",
    )
    omitted_scan_text = "Dördüncü tarama ekidir."
    mixed_scan_text = "Tarama metninde imza yok."

    def raster_clause(sentence):
        with Image.new("RGB", (1200, 1697), "white") as image:
            ImageDraw.Draw(image).text((125, 306), sentence, font=font, fill="black")
            pdf.drawImage(ImageReader(image), 0, 0, width=width, height=height)

    pdf.drawString(52, height - 65, native_clause)
    pdf.showPage()
    raster_clause(mixed_scan_text)
    pdf.drawString(52, height - 65, native_header)
    pdf.showPage()
    for sentence in (*admitted_scan_text, omitted_scan_text):
        raster_clause(sentence)
        pdf.showPage()
    pdf.save()
    return LayoutCase(
        "sentetik-karisik-tarama.pdf",
        pdf_stream.getvalue(),
        (
            ("Sayfa 1", native_clause),
            ("Sayfa 2", native_header),
            ("Sayfa 3", admitted_scan_text[0]),
            ("Sayfa 4", admitted_scan_text[1]),
            ("Sayfa 5", admitted_scan_text[2]),
        ),
        (("Sayfa 2", mixed_scan_text), ("Sayfa 6", omitted_scan_text)),
    )


def make_docx_case() -> LayoutCase:
    """Build a synthetic schedule with a merged heading, nested table and linked footnote."""
    from docx import Document
    from docx.opc.constants import CONTENT_TYPE, RELATIONSHIP_TYPE
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from lxml import etree

    source = Document()
    opening = "Sentetik sözleşme eki."
    merged_heading = "Ek çizelge"
    nested_prefix = "Tutar ihtilaflıdır."
    nested_amount, nested_date = "1.234,56 TL", "14.06.2020"
    nested_suffix = "Ödeme emri tebliğ edilmedi."
    signature_clause = "İmza doğrulanmadı."
    closing = "Uyuşmazlık saklıdır."
    header, footer = "Sentetik eğitim belgesi.", "İnceleme nüshası."
    footnote = "Ön koşulun gerçekleştiği kabul edilmedi."
    source.add_paragraph(opening)
    table = source.add_table(rows=2, cols=2)
    table.style = "Table Grid"
    table.cell(0, 0).merge(table.cell(0, 1)).text = merged_heading
    cell = table.cell(1, 0)
    cell.text = nested_prefix
    nested = cell.add_table(rows=1, cols=2)
    nested.style = "Table Grid"
    nested.cell(0, 0).text, nested.cell(0, 1).text = nested_amount, nested_date
    cell.add_paragraph(nested_suffix)
    reference = OxmlElement("w:footnoteReference")
    reference.set(qn("w:id"), "7")
    cell.paragraphs[-1].add_run()._r.append(reference)
    table.cell(1, 1).text = signature_clause
    source.add_paragraph(closing)
    source.sections[0].header.paragraphs[0].text = header
    source.sections[0].footer.paragraphs[0].text = footer

    footnotes = OxmlElement("w:footnotes")
    defined_note = OxmlElement("w:footnote")
    defined_note.set(qn("w:id"), "7")
    note_doc = Document()
    note_paragraph = note_doc.add_paragraph(footnote)
    marker = OxmlElement("w:r")
    marker.append(OxmlElement("w:footnoteRef"))
    note_paragraph._p.insert(0, marker)
    defined_note.append(note_paragraph._p)
    footnotes.append(defined_note)
    note_part = Part(
        PackURI("/word/footnotes.xml"),
        CONTENT_TYPE.WML_FOOTNOTES,
        etree.tostring(footnotes),
        source.part.package,
    )
    source.part.relate_to(note_part, RELATIONSHIP_TYPE.FOOTNOTES)

    package = BytesIO()
    source.save(package)
    docx_stream = BytesIO()
    # Archive member timestamps otherwise vary by second and runner.
    with ZipFile(package) as original, ZipFile(docx_stream, "w") as fixed:
        for member in sorted(original.namelist()):
            entry = ZipInfo(member, date_time=(2026, 1, 1, 0, 0, 0))
            fixed.writestr(entry, original.read(member), compress_type=ZIP_DEFLATED)

    source_cell = "Tablo 1, satır 2, hücre 1"
    note_origin = f"{source_cell}, paragraf 3"
    return LayoutCase(
        "sentetik-sozlesme-eki.docx",
        docx_stream.getvalue(),
        (
            ("Paragraf 1", opening),
            ("Tablo 1, satır 1", merged_heading),
            (f"{source_cell}, paragraf 1", nested_prefix),
            (f"{source_cell}, tablo 1, satır 1", f"{nested_amount} | {nested_date}"),
            (note_origin, nested_suffix),
            ("Tablo 1, satır 2, hücre 2, paragraf 1", signature_clause),
            ("Paragraf 2", closing),
            ("Bölüm 1, üstbilgi tanımı (varsayılan; kaynak bölüm 1), paragraf 1", header),
            ("Bölüm 1, altbilgi tanımı (varsayılan; kaynak bölüm 1), paragraf 1", footer),
            (f"Dipnot kimlik 7, başvuru 1 ({note_origin}), paragraf 1", footnote),
        ),
    )
