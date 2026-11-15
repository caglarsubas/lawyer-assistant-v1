"""Synthetic page-content coverage checks without raster decoding."""

from io import BytesIO

from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    EncodedStreamObject,
    NameObject,
    NullObject,
    NumberObject,
    StreamObject,
)
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app import pdf_image_coverage as coverage


def baseline(count, warnings=None):
    return {"page_count": count, "passage_count": count, "warnings": warnings or [], "passages": [
        {"locator": f"Sayfa {page}", "text": "Sentetik başlık."} for page in range(1, count + 1)
    ]}


def test_detects_used_external_inline_and_nested_form_images(tmp_path, monkeypatch):
    raw = BytesIO()
    pdf = canvas.Canvas(raw)
    with Image.new("RGB", (4, 4)) as picture:
        pdf.drawString(72, 700, "Native text only")
        pdf.showPage()
        pdf.drawString(72, 700, "Native text and a directly invoked image")
        pdf.drawImage(ImageReader(picture), 70, 550, 100, 100)
        pdf.showPage()
        pdf.drawString(72, 700, "Native text and an inline image")
        pdf.drawInlineImage(picture, 70, 550, 100, 100)
        pdf.showPage()
        pdf.beginForm("inner")
        pdf.drawImage(ImageReader(picture), 70, 550, 100, 100)
        pdf.endForm()
        pdf.beginForm("outer")
        pdf.doForm("inner")
        pdf.endForm()
        pdf.drawString(72, 700, "Native text and an image invoked by nested Forms")
        pdf.doForm("outer")
        pdf.showPage()
        pdf.drawImage(ImageReader(picture), 70, 550, 100, 100)
        pdf.showPage()
        pdf.save()

    writer = PdfWriter(clone_from=BytesIO(raw.getvalue()))
    resources = NameObject("/Resources")
    xobjects = NameObject("/XObject")
    # Deliberately make the same image available on page 1 without invoking it.
    writer.pages[0][resources][xobjects] = writer.pages[1][resources][xobjects]
    path = tmp_path / "coverage.pdf"
    writer.write(path)
    original_bytes = path.read_bytes()

    def guard_decode(original):
        def guarded(stream):
            assert stream.get("/Subtype") != "/Image", "Image samples were decoded"
            return original(stream)
        return guarded

    for kind in (StreamObject, EncodedStreamObject):
        monkeypatch.setattr(kind, "get_data", guard_decode(kind.get_data))

    earlier = baseline(5, [coverage._OCR_USED.format(page=5), "Earlier extraction warning"])
    actual = coverage.add_pdf_coverage_warnings(path, earlier)
    assert actual["warnings"] == earlier["warnings"] + [
        coverage.UNPROCESSED_IMAGE.format(page=page) for page in (2, 3, 4)
    ]
    assert {**actual, "warnings": earlier["warnings"]} == earlier
    assert coverage.add_pdf_coverage_warnings(path, actual) == actual
    assert path.read_bytes() == original_bytes


def _stream(data, subtype=None):
    stream = DecodedStreamObject()
    stream.set_data(data)
    if subtype:
        stream[NameObject("/Subtype")] = NameObject(subtype)
    return stream


def _resources(**objects):
    return DictionaryObject({NameObject("/XObject"): DictionaryObject({
        NameObject(f"/{name}"): obj for name, obj in objects.items()
    })})


def test_form_local_namespace_shadows_unused_page_image(tmp_path):
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    wrapper = _stream(b"/Item Do\n", "/Form")
    text_only = _stream(b"0 0 m 10 10 l S\n", "/Form")
    wrapper[NameObject("/Resources")] = _resources(Item=writer._add_object(text_only))
    picture = _stream(b"\x00", "/Image")
    page[NameObject("/Resources")] = _resources(Wrapper=writer._add_object(wrapper), Item=writer._add_object(picture))
    page[NameObject("/Contents")] = writer._add_object(_stream(b"/Wrapper Do\n"))
    path = tmp_path / "shadow.pdf"
    writer.write(path)
    earlier = baseline(1)
    assert coverage.add_pdf_coverage_warnings(path, earlier) == earlier


def test_unverified_objects_budgets_and_cycles_get_page_specific_warning(tmp_path, monkeypatch):
    writer = PdfWriter()
    contents = NameObject("/Contents")
    resources = NameObject("/Resources")
    page = writer.add_blank_page(width=100, height=100)
    page[contents] = writer._add_object(_stream(b"/Missing Do\n"))
    page = writer.add_blank_page(width=100, height=100)
    page[contents] = writer._add_object(_stream(b"q Q\n" * 200))
    page = writer.add_blank_page(width=100, height=100)
    page[contents] = ArrayObject([NumberObject(1)])
    page = writer.add_blank_page(width=100, height=100)
    page[contents] = NullObject()
    page = writer.add_blank_page(width=100, height=100)
    wrapper = _stream(b"/Wrapper Do\n", "/Form")
    page[resources] = _resources(Wrapper=writer._add_object(wrapper))
    page[contents] = writer._add_object(_stream(b"/Wrapper Do\n"))
    page = writer.add_blank_page(width=100, height=100)
    page[contents] = writer._add_object(_stream(b"0 0 m 10 10 l S\n"))
    path = tmp_path / "invalid-bounded.pdf"
    writer.write(path)
    monkeypatch.setattr(coverage, "MAX_CONTENT_BYTES", 512)
    earlier = baseline(6)
    actual = coverage.add_pdf_coverage_warnings(path, earlier)
    assert actual["warnings"] == [coverage.INSPECTION_UNKNOWN.format(page=page) for page in range(1, 6)]
    assert actual["passages"] == earlier["passages"]
    assert earlier["warnings"] == []
