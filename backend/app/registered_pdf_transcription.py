"""Text-only PDF transcription, called only inside the disconnected parser worker.

Page locators describe extracted text, never raw-byte offsets or legal provisions.
This deliberately narrow adapter supplies no OCR, rendering or glyph correction.
"""

import io
import math
import time
import unicodedata

from .public_sources import _validate
from .registered_source_preparation import PREPARATION_FILES, PreparationError, encode, sha
from .source_gateway import PDF_LIMITATION

ADAPTER_VERSION = "registered-pdf-pages-v1"
PARSER_VERSION = "6.19.0"  # Existing evaluated lock/runtime; upgrades require reevaluation.
MAX_PAGES = 50
MAX_PAGE_CHARACTERS = 20_000
MAX_PAGE_STREAM_BYTES = 4 * 1024 * 1024
MAX_TOTAL_STREAM_BYTES = 20 * 1024 * 1024
WARNINGS = [
    PDF_LIMITATION,
    "PDF text-layer reading order, glyph mappings, visual fidelity and completeness need review.",
    "No OCR, rendering, spelling repair, Unicode normalization or legal provision resolution is performed.",
    "Outer page whitespace is trimmed; two newlines separate pages; internal text and glyphs are retained.",
    "Page locators refer to extracted page code points, not PDF byte ranges or rendered coordinates.",
    "A clean malware scan and exact digests establish neither privacy, usage rights nor legal applicability.",
]


def extract_pages(raw):
    # Parsing/decompression can allocate before these checks; the caller's 256 MiB
    # disconnected container and 45-second deadline are mandatory outer limits.
    import pypdf
    from pypdf.generic import DictionaryObject

    if pypdf.__version__ != PARSER_VERSION:
        raise PreparationError("PDF parser version requires evaluation")
    if not raw.startswith(b"%PDF-") or not raw.rstrip().endswith(b"%%EOF"):
        raise PreparationError("Invalid PDF representation")
    try:
        reader = pypdf.PdfReader(io.BytesIO(raw), strict=True)
        if reader.is_encrypted:
            raise PreparationError("Encrypted PDFs are not supported")
        root = reader.root_object
        names = root.get("/Names", DictionaryObject()).get_object()
        if (any(key in root for key in ("/OpenAction", "/AA", "/AcroForm", "/Collection", "/OCProperties"))
                or any(key in names for key in ("/JavaScript", "/EmbeddedFiles"))):
            raise PreparationError("Interactive PDF features are not supported")
        count = len(reader.pages)
        if not 1 <= count <= MAX_PAGES:
            raise PreparationError("PDF page budget exceeded")
        pages, stream_bytes = [], 0
        for page in reader.pages:
            resources = page.get("/Resources", DictionaryObject()).get_object()
            if any(key in page for key in ("/AA", "/Annots")) or resources.get("/XObject"):
                raise PreparationError("PDF annotations, images and forms are not supported")
            content = page.get_contents()
            size = len(content.get_data()) if content is not None else 0
            stream_bytes += size
            if size > MAX_PAGE_STREAM_BYTES or stream_bytes > MAX_TOTAL_STREAM_BYTES:
                raise PreparationError("PDF content stream budget exceeded")
            text = page.extract_text(extraction_mode="plain").strip()
            if not text:
                raise PreparationError("PDF page requires OCR or contains no usable text")
            if len(text) > MAX_PAGE_CHARACTERS:
                raise PreparationError("PDF page text budget exceeded")
            if any(unicodedata.category(char) in ("Cc", "Cf", "Cs") and char not in "\n\r\t"
                   for char in text):
                raise PreparationError("PDF text contains unsupported control characters")
            pages.append(text)
        return pages
    except PreparationError:
        raise
    except Exception:
        # Library diagnostics may contain paths, dictionaries or source text.
        raise PreparationError("PDF could not be transcribed exactly") from None


def prepare_pdf(files, manifest):
    started = time.monotonic()
    pages = extract_pages(files["raw.pdf"])
    text = "\n\n".join(pages).encode("utf-8")
    if len(text) > PREPARATION_FILES["text.txt"]:
        raise PreparationError("PDF text byte budget exceeded")
    spans, origins, offset = [], [], 0
    for page_number, page_text in enumerate(pages, 1):
        identifier = f"pdf_page_{page_number:04d}"
        digest = sha(page_text.encode("utf-8"))
        end = offset + len(page_text)
        spans.append({"id": identifier, "start": offset, "end": end, "text_sha256": digest,
                      "locator": f"PDF page {page_number}; extracted page code points [0,{len(page_text)})"})
        origins.append({"id": identifier, "page": page_number, "page_text_start": 0,
                        "page_text_end": len(page_text), "page_text_sha256": digest})
        offset = end + 2
    locators = {"schema_version": "public-locators-v1", "offset_unit": "unicode_code_points",
                "raw_sha256": manifest["raw_sha256"], "text_sha256": sha(text), "passages": spans}
    source = {"schema_version": "public-source-v1",
              **{key: manifest[key] for key in ("title", "source_url", "source_version_id", "domain",
                                               "acquired_at", "raw_media_type")},
              "published_on": None, "effective_from": None, "effective_until": None,
              "data_classification": "public", "origin": "public_legal_source",
              "contains_private_matter_data": False, "synthetic": False}
    report = {"schema_version": "registered-source-preparation-v1", "adapter_version": ADAPTER_VERSION,
              "registry_id": manifest["registry_id"], "raw_sha256": manifest["raw_sha256"],
              "text_sha256": sha(text), "passage_count": len(spans), "page_count": len(pages),
              "passage_origins": origins, "parser": "pypdf", "parser_version": PARSER_VERSION,
              "elapsed_seconds": time.monotonic() - started, "representation": manifest["representation"],
              "current_consolidation": False, "rights_status": "rights_pending",
              "review_status": "legal_review_pending", "publication_status": "prepared_for_staging",
              "extraction_fidelity_verified": False, "source_identity_verified": False,
              "sensitivity_reviewed": False, "limitations": WARNINGS}
    artifacts = {"raw.bin": files["raw.pdf"], "text.txt": text, "locators.json": encode(locators),
                 "source.json": encode(source), "acquisition.json": files["acquisition.json"],
                 "preparation.json": encode(report)}
    for name, value in artifacts.items():
        if not 0 < len(value) <= PREPARATION_FILES[name]:
            raise PreparationError("Prepared artifact budget exceeded")
    _validate({name: artifacts[name] for name in ("raw.bin", "text.txt", "locators.json", "source.json")})
    return artifacts


def validate_pdf_report(report, locators, text):
    """Host-side consistency checks without parsing an untrusted PDF."""
    fields = {"schema_version", "adapter_version", "registry_id", "raw_sha256", "text_sha256",
              "passage_count", "page_count", "passage_origins", "parser", "parser_version", "elapsed_seconds",
              "representation", "current_consolidation", "rights_status", "review_status", "publication_status",
              "extraction_fidelity_verified", "source_identity_verified", "sensitivity_reviewed", "limitations"}
    if (set(report) != fields
            or type(report.get("page_count")) is not int or not 1 <= report["page_count"] <= MAX_PAGES
            or report["page_count"] != len(locators.passages)
            or report.get("parser") != "pypdf" or report.get("parser_version") != PARSER_VERSION
            or report.get("limitations") != WARNINGS
            or type(report.get("elapsed_seconds")) not in (int, float)
            or not math.isfinite(report["elapsed_seconds"]) or not 0 <= report["elapsed_seconds"] <= 45):
        raise PreparationError("PDF preparation report failed consistency checks")
    expected, offset = [], 0
    for page_number, span in enumerate(locators.passages, 1):
        size = span.end - span.start
        identifier = f"pdf_page_{page_number:04d}"
        if (span.id != identifier or span.start != offset or not 1 <= size <= MAX_PAGE_CHARACTERS
                or span.locator != f"PDF page {page_number}; extracted page code points [0,{size})"
                or text[span.start:span.end] != text[span.start:span.end].strip()):
            raise PreparationError("PDF page locator failed consistency checks")
        if page_number > 1 and text[offset - 2:offset] != "\n\n":
            raise PreparationError("PDF page separators changed")
        expected.append({"id": identifier, "page": page_number, "page_text_start": 0,
                         "page_text_end": size, "page_text_sha256": span.text_sha256})
        offset = span.end + 2
    if text[offset - 2:] or encode(report.get("passage_origins")) != encode(expected):
        raise PreparationError("PDF page origins failed consistency checks")
