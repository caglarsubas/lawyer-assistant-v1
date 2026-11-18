"""Synthetic page-content and annotation coverage checks without raster decoding."""

from io import BytesIO

from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DecodedStreamObject,
    DictionaryObject,
    EncodedStreamObject,
    IndirectObject,
    NameObject,
    NullObject,
    NumberObject,
    StreamObject,
    TextStringObject,
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


def _patterns(resources, **patterns):
    resources[NameObject("/Pattern")] = DictionaryObject({
        NameObject(f"/{name}"): pattern for name, pattern in patterns.items()
    })
    return resources


def _dictionary(**entries):
    return DictionaryObject({NameObject(f"/{name}"): value for name, value in entries.items()})


def _numbers(*values):
    return ArrayObject([NumberObject(value) for value in values])


def _tiling_pattern(writer, data, resources=None, paint_type=1):
    tile = _stream(data)
    tile.update(_dictionary(
        Type=NameObject("/Pattern"), PatternType=NumberObject(1), PaintType=NumberObject(paint_type),
        TilingType=NumberObject(1), BBox=_numbers(0, 0, 10, 10), XStep=NumberObject(10),
        YStep=NumberObject(10), Resources=resources if resources is not None else DictionaryObject(),
    ))
    return writer._add_object(tile)


def _pattern_page(writer, content, resources):
    page = writer.add_blank_page(width=100, height=100)
    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = writer._add_object(_stream(content))


def _shading_pattern(writer):
    function = _dictionary(
        FunctionType=NumberObject(2), Domain=_numbers(0, 1), C0=_numbers(0, 0, 0),
        C1=_numbers(1, 1, 1), N=NumberObject(1),
    )
    shading = _dictionary(
        ShadingType=NumberObject(2), ColorSpace=NameObject("/DeviceRGB"),
        Coords=_numbers(0, 0, 30, 30), Function=function,
    )
    return writer._add_object(_dictionary(
        Type=NameObject("/Pattern"), PatternType=NumberObject(2), Shading=shading,
    ))


def test_painted_tiling_patterns_detect_raster_without_decoding_images(tmp_path, monkeypatch):
    writer = PdfWriter()
    picture = _stream(b"\x00", "/Image")
    picture.update(_dictionary(Width=NumberObject(1), Height=NumberObject(1),
                               ColorSpace=NameObject("/DeviceGray"), BitsPerComponent=NumberObject(8)))
    raster = writer._add_object(picture)
    vector = writer._add_object(_stream(b"0 0 m 10 10 l S\n", "/Form"))
    raster_tile = _tiling_pattern(writer, b"q 10 0 0 10 0 0 cm /Pixels Do Q\n", _resources(Pixels=raster))
    vector_tile = _tiling_pattern(writer, b"0 0 10 10 re f\n")
    paint = b"/Pattern cs /Tile scn 0 0 30 30 re f\n"
    _pattern_page(writer, paint, _patterns(_resources(Pixels=vector), Tile=raster_tile))
    _pattern_page(writer, paint, _patterns(_resources(Pixels=raster), Tile=vector_tile))

    unused = b"q /Pattern cs /Tile scn 0 0 30 30 re n Q 0 0 40 40 re f\n"
    _pattern_page(writer, unused, _patterns(DictionaryObject(), Tile=raster_tile))

    form = _stream(b"/Pattern CS /Tile SCN 0 0 m 30 30 l S\n", "/Form")
    form.update(_dictionary(BBox=_numbers(0, 0, 40, 40), Resources=_patterns(DictionaryObject(), Tile=raster_tile)))
    _pattern_page(writer, b"/Child Do\n", _patterns(_resources(Child=writer._add_object(form)), Tile=vector_tile))

    mask = _stream(b"\x80", "/Image")
    mask.update(_dictionary(Width=NumberObject(1), Height=NumberObject(1), ImageMask=BooleanObject(True),
                            BitsPerComponent=NumberObject(1)))
    uncolored = _tiling_pattern(
        writer, b"/Mask Do\n", _resources(Mask=writer._add_object(mask)), paint_type=2,
    )
    alias = _patterns(_dictionary(ColorSpace=_dictionary(
        WithGray=ArrayObject([NameObject("/Pattern"), NameObject("/DeviceGray")])
    )), Tile=uncolored)
    _pattern_page(writer, b"/WithGray cs 0 /Tile scn 0 0 30 30 re f*\n", alias)
    _pattern_page(writer, paint, _patterns(DictionaryObject(), Tile=_shading_pattern(writer)))
    _pattern_page(writer, paint, _patterns(DictionaryObject(), Tile=raster_tile))

    path = tmp_path / "raster-tiling.pdf"
    writer.write(path)
    original = path.read_bytes()
    sampled = []
    decode = DecodedStreamObject.get_data

    def observe_decode(stream):
        if stream.get("/Subtype") == "/Image":
            sampled.append(stream)
        return decode(stream)

    monkeypatch.setattr(DecodedStreamObject, "get_data", observe_decode)
    earlier = baseline(7, [coverage._OCR_USED.format(page=7), "Earlier extraction warning"])
    actual = coverage.add_pdf_coverage_warnings(path, earlier)
    assert actual["warnings"] == earlier["warnings"] + [
        coverage.UNPROCESSED_IMAGE.format(page=page) for page in (1, 4, 5)
    ]
    assert {**actual, "warnings": earlier["warnings"]} == earlier
    assert coverage.add_pdf_coverage_warnings(path, actual) == actual
    assert sampled == []
    assert path.read_bytes() == original


def test_pattern_colors_follow_fill_stroke_and_saved_state(tmp_path):
    writer = PdfWriter()
    image = writer._add_object(_stream(b"\x00", "/Image"))
    raster = _tiling_pattern(writer, b"/Image Do\n", _resources(Image=image))
    vector = _tiling_pattern(writer, b"0 0 10 10 re f\n")
    form = _stream(b"0 0 30 30 re f\n", "/Form")
    form.update(_dictionary(BBox=_numbers(0, 0, 40, 40), Resources=_patterns(DictionaryObject(), Tile=vector)))
    child = writer._add_object(form)
    resources = _patterns(_resources(Child=child), Tile=raster)
    _pattern_page(writer, b"/Pattern cs /Tile scn /Child Do\n", resources)
    _pattern_page(writer, b"/Pattern cs /Tile scn 0 0 m 30 30 l S\n", resources)
    _pattern_page(writer, b"/Pattern CS /Tile SCN 0 0 30 30 re f\n", resources)
    _pattern_page(writer, b"/Pattern cs /Tile scn q 0 g Q 0 0 30 30 re f\n", resources)
    _pattern_page(writer, b"/Pattern cs /Tile scn 0 g 0 0 30 30 re f\n", resources)

    font = writer._add_object(_dictionary(Type=NameObject("/Font"), Subtype=NameObject("/Type1"),
                                          BaseFont=NameObject("/Helvetica")))
    text_resources = _patterns(_dictionary(Font=_dictionary(F1=font)), Tile=raster)
    text_start = b"/Pattern cs /Tile scn BT /F1 10 Tf 10 20 Td "
    _pattern_page(writer, text_start + b"0 Tr (Synthetic) Tj ET\n", text_resources)
    _pattern_page(writer, text_start + b"3 Tr (Synthetic) Tj ET\n", text_resources)
    path = tmp_path / "pattern-state.pdf"
    writer.write(path)
    earlier = baseline(7)
    actual = coverage.add_pdf_coverage_warnings(path, earlier)
    assert actual["warnings"] == [coverage.UNPROCESSED_IMAGE.format(page=page) for page in (1, 4, 6)]
    assert actual["passages"] == earlier["passages"]


def test_painted_patterns_report_missing_malformed_recursive_and_over_budget_streams(tmp_path, monkeypatch):
    writer = PdfWriter()
    content = b"/Pattern cs /Tile scn 0 0 30 30 re f\n"
    _pattern_page(writer, content, _patterns(DictionaryObject()))
    malformed = writer._add_object(_dictionary(PatternType=NumberObject(1), PaintType=NumberObject(1)))
    _pattern_page(writer, content, _patterns(DictionaryObject(), Tile=malformed))
    recursive = _tiling_pattern(writer, content)
    recursive.get_object()[NameObject("/Resources")] = _patterns(DictionaryObject(), Tile=recursive)
    _pattern_page(writer, content, _patterns(DictionaryObject(), Tile=recursive))
    larger = _tiling_pattern(writer, b"q Q\n" * 130)
    _pattern_page(writer, content, _patterns(DictionaryObject(), Tile=larger))
    _pattern_page(writer, b"0 0 30 30 re f\n", _patterns(DictionaryObject(), Tile=larger))
    path = tmp_path / "unsafe-patterns.pdf"
    writer.write(path)
    monkeypatch.setattr(coverage, "MAX_CONTENT_BYTES", 512)
    earlier = baseline(5)
    actual = coverage.add_pdf_coverage_warnings(path, earlier)
    assert actual["warnings"] == [coverage.INSPECTION_UNKNOWN.format(page=page) for page in (1, 2, 3, 4)]
    assert actual["passages"] == earlier["passages"]


def _annotation(writer, subtype, **properties):
    return writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject(subtype),
        **{NameObject(f"/{name}"): value for name, value in properties.items()},
    }))


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


def test_annotations_and_fields_report_their_exact_pages(tmp_path, monkeypatch):
    writer = PdfWriter()
    contents, annots = NameObject("/Contents"), NameObject("/Annots")
    pages = [writer.add_blank_page(width=100, height=100) for _ in range(15)]
    for page in pages:
        page[contents] = writer._add_object(_stream(b"0 0 m 10 10 l S\n"))

    link = _annotation(writer, "/Link", Dest=NameObject("/Navigation"))
    appearance = writer._add_object(_stream(b"0 0 m 15 15 l S\n", "/Form"))
    visible_link = _annotation(writer, "/Link", AP=DictionaryObject({NameObject("/N"): appearance}))
    widget = _annotation(writer, "/Widget", V=TextStringObject("Synthetic field value"))
    stamp = _annotation(writer, "/Stamp", AP=DictionaryObject({NameObject("/N"): appearance}))
    for page, items in zip(pages[1:7], ([], [link], [visible_link], [widget], [stamp], [stamp]), strict=True):
        page[annots] = writer._add_object(ArrayObject(items))
    pages[5][NameObject("/Resources")] = _resources(Image=writer._add_object(_stream(b"\x00", "/Image")))
    pages[5][contents] = writer._add_object(_stream(b"/Image Do\n"))
    pages[7][annots] = ArrayObject([NumberObject(1)])
    cap = coverage.MAX_ANNOTATIONS_PER_PAGE
    pages[8][annots] = ArrayObject([link] * (cap + 1))
    pages[9][annots] = ArrayObject([stamp])
    pages[10][annots] = ArrayObject([link] * 65)
    pages[11][annots] = ArrayObject([link] * cap)
    pages[12][annots] = ArrayObject([link] * (cap - 1) + [stamp, link])
    pages[13][annots] = ArrayObject([link] * cap + [widget])
    pages[14][annots] = ArrayObject([NumberObject(1), widget])
    path = tmp_path / "annotation-coverage.pdf"
    writer.write(path)
    original = path.read_bytes()
    earlier = baseline(15, [coverage._OCR_USED.format(page=7), "Sayfa 10: içerik işlenemedi."])
    earlier["passages"].pop(9)
    earlier["passage_count"] -= 1
    appearance_reads = []
    decode = DecodedStreamObject.get_data

    def observe_decode(stream):
        if stream.get("/Subtype") == "/Form":
            appearance_reads.append(stream)
        return decode(stream)

    monkeypatch.setattr(DecodedStreamObject, "get_data", observe_decode)
    result = coverage.add_pdf_coverage_warnings(path, earlier)
    limited = "PDF ek açıklamaları ve form alanları çıkarımda doğrulanmadı."
    unknown = "PDF ek açıklamaları ve form alanları denetlenemedi."
    expected = {4: limited, 5: limited, 6: f"Görsel içerik OCR ile işlenmedi. {limited}",
                7: limited, 8: unknown, 9: unknown, 13: limited, 14: unknown, 15: limited}
    assert result["warnings"] == earlier["warnings"] + [
        f"Sayfa {page}: {note} Özgün sayfayı kontrol edin." for page, note in expected.items()
    ]
    assert {**result, "warnings": earlier["warnings"]} == earlier
    assert coverage.add_pdf_coverage_warnings(path, result) == result
    assert appearance_reads == []
    assert path.read_bytes() == original


def test_annotation_reference_budget_is_shared_without_consuming_raster_coverage(tmp_path, monkeypatch):
    writer = PdfWriter()
    contents, annots = NameObject("/Contents"), NameObject("/Annots")
    pages = [writer.add_blank_page(width=100, height=100) for _ in range(4)]
    for page in pages:
        page[contents] = writer._add_object(_stream(b"0 0 m 10 10 l S\n"))
    first = _annotation(writer, "/Link", Dest=NameObject("/First"))
    second = _annotation(writer, "/Link", Dest=NameObject("/Second"))
    widget = _annotation(writer, "/Widget")
    deferred = _annotation(writer, "/Stamp")
    pages[0][annots] = ArrayObject([first, second])
    pages[1][annots] = ArrayObject([widget])
    pages[2][annots] = ArrayObject([deferred])
    pages[2][NameObject("/Resources")] = _resources(Image=writer._add_object(_stream(b"\x00", "/Image")))
    pages[2][contents] = writer._add_object(_stream(b"/Image Do\n"))
    path = tmp_path / "annotation-document-budget.pdf"
    writer.write(path)
    original = path.read_bytes()
    monkeypatch.setattr(coverage, "MAX_ANNOTATIONS_PER_DOCUMENT", 3)
    budgeted = {reference.idnum for reference in (first, second, widget, deferred)}
    visited = []
    get_object = IndirectObject.get_object

    def visit(reference):
        if reference.idnum in budgeted:
            visited.append(reference.idnum)
        return get_object(reference)

    monkeypatch.setattr(IndirectObject, "get_object", visit)
    earlier = baseline(4)
    result = coverage.add_pdf_coverage_warnings(path, earlier)
    assert visited == [first.idnum, second.idnum, widget.idnum]
    assert result["warnings"] == [
        "Sayfa 2: PDF ek açıklamaları ve form alanları çıkarımda doğrulanmadı. Özgün sayfayı kontrol edin.",
        "Sayfa 3: Görsel içerik OCR ile işlenmedi. PDF ek açıklamaları ve form alanları denetlenemedi. "
        "Özgün sayfayı kontrol edin.",
    ]
    assert {**result, "warnings": earlier["warnings"]} == earlier
    assert path.read_bytes() == original
