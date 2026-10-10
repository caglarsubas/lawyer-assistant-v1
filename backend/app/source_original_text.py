"""Exact inert HTML source-code windows; no parsing, rendering or fidelity approval."""

import hashlib
import re

MAX_ORIGINAL_BYTES = 1024 * 1024
MAX_WINDOW = 12_000
HTML_LOCATOR = re.compile(
    r"HTML source line ([1-9][0-9]{0,6}), column ([1-9][0-9]{0,6}); "
    r"decoded code points \[([0-9]{1,7}),([0-9]{1,7})\)"
)


class OriginalTextUnavailable(ValueError):
    """Fixed diagnostics only, without raw content or private paths."""


def decode_html_source(raw):
    # Shared with disconnected preparation: no guessing, replacement or HTML parser.
    declarations = re.findall(rb"charset\s*=\s*[\"']?\s*([A-Za-z0-9_-]+)", raw[:4096], re.I)
    aliases = {"utf-8": "utf-8", "utf8": "utf-8", "windows-1254": "cp1254",
               "iso-8859-9": "iso8859-9"}
    encodings = {aliases.get(item.decode("ascii").lower(), "unsupported") for item in declarations}
    if raw.startswith(b"\xef\xbb\xbf"):
        encodings.add("utf-8")
    if len(encodings) > 1 or "unsupported" in encodings:
        raise OriginalTextUnavailable("Unsupported or conflicting HTML encoding")
    encoding = next(iter(encodings), "utf-8")
    try:
        decoded = raw.removeprefix(b"\xef\xbb\xbf").decode(encoding, errors="strict")
    except UnicodeError:
        raise OriginalTextUnavailable("HTML encoding could not be decoded exactly") from None
    return decoded, encoding


def original_text_window(package, identifier, passage_id, *, offset=0, limit=MAX_WINDOW):
    if (type(offset) is not int or not 0 <= offset <= MAX_ORIGINAL_BYTES
            or type(limit) is not int or not 1 <= limit <= MAX_WINDOW):
        raise OriginalTextUnavailable("Invalid original source window bounds")
    if package.metadata.raw_media_type != "text/html" or len(package.raw) > MAX_ORIGINAL_BYTES:
        raise OriginalTextUnavailable("Original source-code preview is unavailable")
    passage = next((item for item in package.locators.passages if item.id == passage_id), None)
    match = HTML_LOCATOR.fullmatch(passage.locator) if passage else None
    if not match:
        raise OriginalTextUnavailable("Original source-code locator is unavailable")
    decoded, encoding = decode_html_source(package.raw)
    line, column, start, end = map(int, match.groups())
    if not 0 <= start < end <= len(decoded) or offset >= end - start:
        raise OriginalTextUnavailable("Original source-code locator is out of bounds")
    # Coordinates can be checked without interpreting any HTML. This does not
    # establish that the operator's selected range supports the extracted text.
    expected_line = decoded.count("\n", 0, start) + 1
    expected_column = start - decoded.rfind("\n", 0, start)
    if (line, column) != (expected_line, expected_column):
        raise OriginalTextUnavailable("Original source-code coordinates disagree")
    window_start = start + offset
    window_end = min(window_start + limit, end)
    content = decoded[window_start:window_end]
    return {
        "source_id": identifier, "source_version_id": package.metadata.source_version_id,
        "passage_id": passage.id, "raw_sha256": package.locators.raw_sha256,
        "text_sha256": package.locators.text_sha256,
        "decoded_original_sha256": hashlib.sha256(decoded.encode("utf-8")).hexdigest(),
        "window_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "encoding": encoding, "offset_unit": "unicode_code_points_excluding_initial_utf8_bom",
        "range_start": start, "range_end": end, "start": window_start, "end": window_end,
        "next_offset": window_end - start if window_end < end else None,
        "text": content, "integrity_scope": "all_artifacts_verified",
        "locator_coordinate_status": "consistent_not_fidelity_reviewed",
        "extraction_fidelity_verified": False,
    }
