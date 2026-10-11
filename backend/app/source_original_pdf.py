"""PDF page bindings from verified artifacts; never parse/render original bytes here."""

import re

from .source_original_text import MAX_ORIGINAL_BYTES, OriginalTextUnavailable

MAX_PAGES = 50
MAX_PAGE_CHARACTERS = 20_000
PDF_LOCATOR = re.compile(r"PDF page ([1-9][0-9]?); extracted page code points \[0,([1-9][0-9]{0,4})\)")


def original_pdf_page(package, identifier, passage_id):
    if (package.metadata.raw_media_type != "application/pdf"
            or not 0 < len(package.raw) <= MAX_ORIGINAL_BYTES):
        raise OriginalTextUnavailable("Original PDF preview is unavailable")
    passages = package.locators.passages
    if not 1 <= len(passages) <= MAX_PAGES:
        raise OriginalTextUnavailable("Original PDF page mapping is unavailable")
    selected = None
    previous_end = 0
    for number, passage in enumerate(passages, 1):
        match = PDF_LOCATOR.fullmatch(passage.locator)
        if (not match or passage.id != f"pdf_page_{number:04d}"
                or int(match[1]) != number or not 1 <= int(match[2]) <= MAX_PAGE_CHARACTERS
                or passage.end - passage.start != int(match[2])
                or passage.start != previous_end + (2 if number > 1 else 0)
                or (number > 1 and package.text[previous_end:passage.start] != "\n\n")):
            raise OriginalTextUnavailable("Original PDF page mapping is inconsistent")
        if passage.id == passage_id:
            selected = number
        previous_end = passage.end
    if selected is None or previous_end != len(package.text):
        raise OriginalTextUnavailable("Original PDF page mapping is unavailable")
    # Operator-provided locators are checked for consistency, not correspondence
    # with actual PDF pages. The local viewer also checks the parsed page count.
    return {
        "source_id": identifier, "source_version_id": package.metadata.source_version_id,
        "passage_id": passage_id, "raw_sha256": package.locators.raw_sha256,
        "text_sha256": package.locators.text_sha256, "raw_bytes": len(package.raw),
        "raw_media_type": "application/pdf", "page": selected, "page_count": len(passages),
        "integrity_scope": "all_artifacts_verified",
        "locator_coordinate_status": "consistent_not_fidelity_reviewed",
        "extraction_fidelity_verified": False,
    }
