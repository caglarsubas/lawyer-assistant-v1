"""Disclose raster content on PDF pages where native text skipped OCR."""

import re
import time
from dataclasses import dataclass, field

from pypdf import PdfReader, apply_configuration
from pypdf.generic import ArrayObject, ContentStream, DictionaryObject, NameObject, StreamObject

UNPROCESSED_IMAGE = "Sayfa {page}: Görsel içerik OCR ile işlenmedi. Özgün sayfayı kontrol edin."
INSPECTION_UNKNOWN = "Sayfa {page}: Görsel içerik denetlenemedi. Özgün sayfayı kontrol edin."
_OCR_USED = "Sayfa {page}: OCR kullanıldı; görüntüyle doğrulayın."
_PAGE = re.compile(r"Sayfa ([1-9][0-9]{0,2})")

MAX_CONTENT_BYTES = 512_000
MAX_CONTENT_PARTS = 64
MAX_FORM_DEPTH = 8
MAX_FILTERS = 4
_INSPECTION_SECONDS = 2
_CONTENT_FILTERS = {"/FlateDecode", "/LZWDecode", "/ASCII85Decode", "/ASCIIHexDecode", "/RunLengthDecode",
                    "/Fl", "/LZW", "/A85", "/AHx", "/RL"}


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


def _inspect_page(page, reader, budget):
    try:
        content = page["/Contents"]
        resources = page.get_inherited("/Resources")
        return UNPROCESSED_IMAGE if _has_raster(content, resources, reader, budget, set()) else None
    except Exception:
        # Secondary inspection cannot erase good baseline text. A damaged or
        # over-budget stream must leave an explicit page-specific limitation.
        return INSPECTION_UNKNOWN


def add_pdf_coverage_warnings(path, result):
    """Augment a successful baseline extraction without changing its passages."""
    recorded = set(result["warnings"])
    candidates = sorted({
        int(match[1]) for passage in result["passages"]
        if (match := _PAGE.fullmatch(passage["locator"])) and _OCR_USED.format(page=match[1]) not in recorded
    })
    if not candidates:
        return result

    findings = dict.fromkeys(candidates, INSPECTION_UNKNOWN)
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
                    findings[number] = _inspect_page(reader.pages[number - 1], reader, budget)
    except Exception:
        # Keep completed findings. The others retain the unknown warning.
        pass

    added = [message.format(page=page) for page, message in findings.items() if message]
    warnings = [warning for warning in added if warning not in recorded]
    return {**result, "warnings": [*result["warnings"], *warnings]} if warnings else result
