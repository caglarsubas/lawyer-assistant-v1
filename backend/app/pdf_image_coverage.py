"""Disclose raster and annotation limitations on pages with extracted text."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, replace
from itertools import islice

from pypdf import PdfReader, apply_configuration
from pypdf.generic import ArrayObject, ContentStream, DictionaryObject, NameObject, StreamObject

_IMAGE_UNPROCESSED = "Görsel içerik OCR ile işlenmedi."
_IMAGE_UNKNOWN = "Görsel içerik denetlenemedi."
_ANNOTATIONS_UNVERIFIED = "PDF ek açıklamaları ve form alanları çıkarımda doğrulanmadı."
_ANNOTATIONS_UNKNOWN = "PDF ek açıklamaları ve form alanları denetlenemedi."
_REVIEW_ORIGINAL = "Özgün sayfayı kontrol edin."
UNPROCESSED_IMAGE = f"Sayfa {{page}}: {_IMAGE_UNPROCESSED} {_REVIEW_ORIGINAL}"
INSPECTION_UNKNOWN = f"Sayfa {{page}}: {_IMAGE_UNKNOWN} {_REVIEW_ORIGINAL}"
_OCR_USED = "Sayfa {page}: OCR kullanıldı; görüntüyle doğrulayın."
_PAGE = re.compile(r"Sayfa ([1-9][0-9]{0,2})")

MAX_CONTENT_BYTES = 512_000
MAX_CONTENT_PARTS = 64
MAX_FORM_DEPTH = 8
MAX_FILTERS = 4
MAX_ANNOTATIONS_PER_PAGE = 256
MAX_ANNOTATIONS_PER_DOCUMENT = 4_096
_INSPECTION_SECONDS = 2
_CONTENT_FILTERS = {"/FlateDecode", "/LZWDecode", "/ASCII85Decode", "/ASCIIHexDecode", "/RunLengthDecode",
                    "/Fl", "/LZW", "/A85", "/AHx", "/RL"}
_DEVICE_COLORS = {"/DeviceGray", "/DeviceRGB", "/DeviceCMYK"}
_FILL_PATH = {b"f", b"F", b"f*"}
_STROKE_PATH = {b"S", b"s"}
_FILL_STROKE_PATH = {b"B", b"B*", b"b", b"b*"}
_PAINT_PATH = _FILL_PATH | _STROKE_PATH | _FILL_STROKE_PATH
_DRAW_SEGMENT = {b"l", b"c", b"v", b"y", b"re"}
_SHOW_TEXT = {b"Tj", b"TJ", b"'", b'"'}
_LINK_NAVIGATION_KEYS = {
    "/Type", "/Subtype", "/Rect", "/Border", "/BS", "/C", "/H", "/A", "/Dest",
    "/F", "/P", "/StructParent", "/QuadPoints", "/NM", "/M",
}


@dataclass
class _InspectionBudget:
    bytes_left: int = 16_000_000
    operations_left: int = 200_000
    streams_left: int = 2_000
    annotations_left: int = field(default_factory=lambda: MAX_ANNOTATIONS_PER_DOCUMENT)
    deadline: float = field(default_factory=lambda: time.monotonic() + _INSPECTION_SECONDS)

    def check_time(self):
        if time.monotonic() >= self.deadline:
            raise ValueError("PDF inspection time budget reached")

    def take_streams(self, count):
        self.streams_left -= count
        if self.streams_left < 0 or self.bytes_left <= 0 or self.operations_left <= 0:
            raise ValueError("PDF inspection stream budget reached")
        self.check_time()

    def take_bytes(self, count):
        self.bytes_left -= count
        if count > MAX_CONTENT_BYTES or self.bytes_left < 0:
            raise ValueError("PDF inspection content budget reached")

    def take_operations(self, count):
        self.operations_left -= count
        if self.operations_left < 0:
            raise ValueError("PDF inspection operation budget reached")

    def take_annotation(self):
        self.check_time()
        if self.annotations_left <= 0:
            raise ValueError("PDF inspection annotation budget reached")
        self.annotations_left -= 1


@dataclass(frozen=True)
class _SelectedPattern:
    name: NameObject
    resources: DictionaryObject | None
    parent_initial: _PaintState


@dataclass(frozen=True)
class _PaintColor:
    # A colored pattern takes just its name. An uncolored one takes color
    # components followed by its name.
    space: str | None = None
    pattern: _SelectedPattern | None = None


@dataclass(frozen=True)
class _PaintState:
    fill: _PaintColor = _PaintColor()
    stroke: _PaintColor = _PaintColor()
    text_mode: int = 0


def _operations(content, reader, budget):
    parts = content if isinstance(content, ArrayObject) else (content,)
    if len(parts) > MAX_CONTENT_PARTS:
        raise ValueError("PDF inspection content array limit reached")
    budget.take_streams(max(1, len(parts)))
    for part in parts:
        stream = part.get_object()
        if not isinstance(stream, StreamObject):
            raise ValueError("PDF content is not a stream")
        if "/Filter" in stream:
            filters = stream["/Filter"]
            names = filters if isinstance(filters, ArrayObject) else (filters,)
            if (len(names) > MAX_FILTERS
                    or any(not isinstance(name, NameObject) or name not in _CONTENT_FILTERS for name in names)):
                raise ValueError("Unsupported PDF content filter")
    try:
        stream = ContentStream(content, reader)
    except Exception:
        # A failing decompression may still use the full per-stream allowance.
        budget.take_bytes(MAX_CONTENT_BYTES)
        raise
    budget.take_bytes(len(stream.get_data()))
    operations = stream.operations
    budget.take_operations(len(operations))
    return operations


def _resource(resources, kind, name):
    if resources is None or not isinstance(resources[kind], DictionaryObject):
        raise ValueError("Invalid PDF named resource dictionary")
    return resources[kind][name]


def _pattern_space(operands, resources):
    if len(operands) != 1 or not isinstance(operands[0], NameObject):
        raise ValueError("Invalid PDF color space selection")
    name = operands[0]
    if name == "/Pattern":
        return "colored"
    if name in _DEVICE_COLORS:
        return None
    space = _resource(resources, "/ColorSpace", name)
    if space == "/Pattern":
        return "colored"
    if isinstance(space, ArrayObject) and space and space[0] == "/Pattern":
        if len(space) != 2:
            raise ValueError("Invalid PDF uncolored pattern space")
        return "uncolored"
    return None


def _select_pattern(color, operands, resources, initial):
    named = operands and isinstance(operands[-1], NameObject)
    if color.space is None:
        if named:
            raise ValueError("PDF pattern selected outside a pattern color space")
        return color
    if (not named or (len(operands) == 1) != (color.space == "colored")
            or any(not isinstance(value, (int, float)) for value in operands[:-1])):
        raise ValueError("Invalid PDF pattern color")
    return replace(color, pattern=_SelectedPattern(operands[-1], resources, initial))


def _painted_colors(operator, state):
    if operator in _FILL_PATH or (operator in _SHOW_TEXT and state.text_mode in (0, 4)):
        return (state.fill,)
    if operator in _STROKE_PATH or (operator in _SHOW_TEXT and state.text_mode in (1, 5)):
        return (state.stroke,)
    if operator in _FILL_STROKE_PATH or (operator in _SHOW_TEXT and state.text_mode in (2, 6)):
        return (state.fill, state.stroke)
    return ()


def _follow_content(invoked, resources, reader, budget, path, initial):
    if id(invoked) in path or len(path) >= MAX_FORM_DEPTH:
        raise ValueError("PDF content nesting or cycle limit reached")
    return _has_raster(invoked, resources, reader, budget, path | {id(invoked)}, initial)


def _pattern_has_raster(color, reader, budget, path):
    selection = color.pattern
    budget.check_time()
    pattern = _resource(selection.resources, "/Pattern", selection.name)
    if not isinstance(pattern, DictionaryObject):
        raise ValueError("Invalid PDF pattern dictionary")
    pattern_type = pattern["/PatternType"]
    if pattern_type == 2 and color.space == "colored" and not isinstance(pattern, StreamObject):
        if not isinstance(pattern["/Shading"], DictionaryObject):
            raise ValueError("Invalid PDF shading pattern")
        return False
    paint_type = 1 if color.space == "colored" else 2
    if pattern_type != 1 or not isinstance(pattern, StreamObject) or pattern["/PaintType"] != paint_type:
        raise ValueError("Invalid PDF tiling pattern")
    # Cells start with the initial state of the content that declared the
    # selection, rather than the state that is using the pattern as a color.
    initial = selection.parent_initial if paint_type == 1 else _PaintState()
    return _follow_content(pattern, pattern["/Resources"], reader, budget, path, initial)


def _has_raster(content, resources, reader, budget, path, initial=_PaintState()):
    if resources is not None and not isinstance(resources, DictionaryObject):
        raise ValueError("Invalid PDF resource dictionary")
    state = initial
    stack = []
    has_segments = False
    for operands, operator in _operations(content, reader, budget):
        if operator in _DRAW_SEGMENT:
            has_segments = True
            continue
        if operator == b"n":
            has_segments = False
            continue
        if operator in _PAINT_PATH:
            if not has_segments:
                continue
            has_segments = False
        if operator == b"INLINE IMAGE":
            return True
        if operator == b"Do":
            budget.check_time()
            if len(operands) != 1 or not isinstance(operands[0], NameObject):
                raise ValueError("Invalid PDF object invocation")
            invoked = _resource(resources, "/XObject", operands[0])
            if not isinstance(invoked, StreamObject):
                raise ValueError("Invoked PDF object is not a stream")
            subtype = invoked["/Subtype"]
            if subtype == "/Image":
                # Recognition needs only the object type. Do not decode its samples.
                return True
            if subtype != "/Form":
                raise ValueError("Unsupported PDF object invocation")
            child_resources = invoked["/Resources"] if "/Resources" in invoked else resources
            if _follow_content(invoked, child_resources, reader, budget, path, state):
                return True
        elif operator == b"q":
            stack.append(state)
        elif operator == b"Q":
            state = stack.pop()
        elif operator == b"cs":
            state = replace(state, fill=_PaintColor(_pattern_space(operands, resources)))
        elif operator == b"CS":
            state = replace(state, stroke=_PaintColor(_pattern_space(operands, resources)))
        elif operator == b"scn":
            state = replace(state, fill=_select_pattern(state.fill, operands, resources, initial))
        elif operator == b"SCN":
            state = replace(state, stroke=_select_pattern(state.stroke, operands, resources, initial))
        elif operator in (b"g", b"rg", b"k"):
            state = replace(state, fill=_PaintColor())
        elif operator in (b"G", b"RG", b"K"):
            state = replace(state, stroke=_PaintColor())
        elif operator in (b"sc", b"SC"):
            if (state.fill if operator == b"sc" else state.stroke).space is not None:
                raise ValueError("Invalid PDF operator for a pattern color")
        elif operator == b"Tr":
            if len(operands) != 1 or not isinstance(operands[0], int) or not 0 <= operands[0] <= 7:
                raise ValueError("Invalid PDF text rendering mode")
            state = replace(state, text_mode=operands[0])
        elif any(color.pattern is not None and _pattern_has_raster(color, reader, budget, path)
                 for color in _painted_colors(operator, state)):
            return True
    budget.check_time()
    return False


def _image_limitation(page, reader, budget):
    try:
        content = page["/Contents"]
        resources = page.get_inherited("/Resources")
        return _IMAGE_UNPROCESSED if _has_raster(content, resources, reader, budget, set()) else None
    except Exception:
        # Secondary inspection cannot erase good baseline text. A damaged or
        # over-budget stream must leave an explicit page-specific limitation.
        return _IMAGE_UNKNOWN


def _annotation_limitation(page, budget):
    if "/Annots" not in page:
        return None
    try:
        budget.check_time()
        if budget.annotations_left <= 0:
            return _ANNOTATIONS_UNKNOWN
        annotations = page["/Annots"]
        if not isinstance(annotations, ArrayObject):
            return _ANNOTATIONS_UNKNOWN
        incomplete = len(annotations) > MAX_ANNOTATIONS_PER_PAGE
        for reference in islice(annotations, MAX_ANNOTATIONS_PER_PAGE):
            budget.take_annotation()
            try:
                annotation = reference.get_object()
            except Exception:
                incomplete = True
                continue
            subtype = annotation.get("/Subtype") if isinstance(annotation, DictionaryObject) else None
            if not isinstance(subtype, NameObject):
                incomplete = True
            elif subtype != "/Link" or not annotation.keys() <= _LINK_NAVIGATION_KEYS:
                # A confirmed entry is enough to ask the reader to review the
                # original page. Keep the inspection metadata-only.
                return _ANNOTATIONS_UNVERIFIED
        if incomplete:
            return _ANNOTATIONS_UNKNOWN
    except Exception:
        return _ANNOTATIONS_UNKNOWN
    return None


def add_pdf_coverage_warnings(path, result):
    """Augment a successful baseline extraction without changing its passages."""
    recorded = set(result["warnings"])
    candidates = sorted({
        int(match[1]) for passage in result["passages"]
        if (match := _PAGE.fullmatch(passage["locator"]))
    })
    if not candidates:
        return result

    needs_image_check = {page for page in candidates if _OCR_USED.format(page=page) not in recorded}
    findings = {page: (_IMAGE_UNKNOWN,) if page in needs_image_check else () for page in candidates}
    budget = _InspectionBudget()
    try:
        with apply_configuration(
            array_based_stream_maximum_output_length=MAX_CONTENT_BYTES,
            zlib_maximum_output_length=MAX_CONTENT_BYTES,
            zlib_maximum_recovery_input_length=MAX_CONTENT_BYTES,
            lzw_maximum_output_length=MAX_CONTENT_BYTES,
            run_length_maximum_output_length=MAX_CONTENT_BYTES,
            page_tree_maximum_entries=2_000,
            jbig2dec_binary=None,
        ), PdfReader(path, strict=True) as reader:
            if result["page_count"] == len(reader.pages) and candidates[-1] <= len(reader.pages):
                for number in candidates:
                    page = reader.pages[number - 1]
                    annotations = _annotation_limitation(page, budget)
                    image = _image_limitation(page, reader, budget) if number in needs_image_check else None
                    findings[number] = tuple(limitation for limitation in (image, annotations) if limitation)
    except Exception:
        # Keep completed findings. The others retain the unknown warning.
        pass

    # Coalesce findings so a 500-page PDF cannot generate two new warnings per page.
    added = [f"Sayfa {page}: {' '.join(limits)} {_REVIEW_ORIGINAL}"
             for page, limits in findings.items() if limits]
    warnings = [warning for warning in added if warning not in recorded]
    return {**result, "warnings": [*result["warnings"], *warnings]} if warnings else result
