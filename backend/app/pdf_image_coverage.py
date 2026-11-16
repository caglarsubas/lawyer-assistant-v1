"""Disclose raster and annotation limitations on pages with extracted text."""

import re
import time
from dataclasses import dataclass, field

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
MAX_ANNOTATIONS_PER_PAGE = 64
_INSPECTION_SECONDS = 2
_CONTENT_FILTERS = {"/FlateDecode", "/LZWDecode", "/ASCII85Decode", "/ASCIIHexDecode", "/RunLengthDecode",
                    "/Fl", "/LZW", "/A85", "/AHx", "/RL"}
_LINK_NAVIGATION_KEYS = {
    "/Type", "/Subtype", "/Rect", "/Border", "/BS", "/C", "/H", "/A", "/Dest",
    "/F", "/P", "/StructParent", "/QuadPoints", "/NM", "/M",
}


@dataclass
class _InspectionBudget:
    bytes_left: int = 16_000_000
    operations_left: int = 200_000
    streams_left: int = 2_000
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


def _has_raster(content, resources, reader, budget, path):
    if resources is not None and not isinstance(resources, DictionaryObject):
        raise ValueError("Invalid PDF resource dictionary")
    for operands, operator in _operations(content, reader, budget):
        if operator == b"INLINE IMAGE":
            return True
        if operator != b"Do":
            continue
        budget.check_time()
        if len(operands) != 1 or not isinstance(operands[0], NameObject) or resources is None:
            raise ValueError("Invalid PDF object invocation")
        objects = resources["/XObject"]
        if not isinstance(objects, DictionaryObject):
            raise ValueError("Invalid PDF object dictionary")
        invoked = objects[operands[0]]
        if not isinstance(invoked, StreamObject):
            raise ValueError("Invoked PDF object is not a stream")
        subtype = invoked["/Subtype"]
        if subtype == "/Image":
            # Recognition needs only the object type. Do not decode its samples.
            return True
        if subtype != "/Form" or id(invoked) in path or len(path) >= MAX_FORM_DEPTH:
            raise ValueError("Unsupported or cyclic PDF form invocation")
        form_resources = invoked["/Resources"] if "/Resources" in invoked else resources
        if _has_raster(invoked, form_resources, reader, budget, path | {id(invoked)}):
            return True
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
        annotations = page["/Annots"]
        if not isinstance(annotations, ArrayObject) or len(annotations) > MAX_ANNOTATIONS_PER_PAGE:
            return _ANNOTATIONS_UNKNOWN
        for reference in annotations:
            budget.check_time()
            annotation = reference.get_object()
            if not isinstance(annotation, DictionaryObject) or not isinstance(annotation.get("/Subtype"), NameObject):
                return _ANNOTATIONS_UNKNOWN
            # Metadata alone discloses the limitation. Never inspect appearance
            # streams, form values, attachments or actions.
            if annotation.get("/Subtype") != "/Link" or not annotation.keys() <= _LINK_NAVIGATION_KEYS:
                return _ANNOTATIONS_UNVERIFIED
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
