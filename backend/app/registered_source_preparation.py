"""Inert, bounded HTML transcription for the closed public-source registry.

This module does not scan or approve content. The operator wrapper scans the exact
snapshot first and runs this worker disconnected, without application data/secrets.
"""

import argparse
import hashlib
import html
import json
import re
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

from .public_sources import _json, _validate
from .qualification_evidence import read_exact_directory
from .source_gateway import HISTORICAL_LIMITATION, MAX_BYTES, REGISTRY_VERSION, registered

ADAPTER_VERSION = "registered-html-blocks-v1"
ACQUISITION_FILES = {"raw.html": MAX_BYTES, "acquisition.json": 64 * 1024}
PREPARATION_FILES = {
    "raw.bin": MAX_BYTES, "text.txt": 2 * 1024 * 1024, "locators.json": 2 * 1024 * 1024,
    "source.json": 64 * 1024, "acquisition.json": 64 * 1024, "preparation.json": 2 * 1024 * 1024,
}
BLOCKS = frozenset({"p", "div", "br", "tr", "td", "th", "li", "h1", "h2", "h3", "h4",
                   "h5", "h6", "section", "article", "blockquote", "pre", "hr"})
SKIP = frozenset({"head", "script", "style", "template", "iframe", "object", "svg", "noscript"})
WARNINGS = [
    HISTORICAL_LIMITATION,
    "CSS visibility, visual reading order, omitted non-text content and extraction fidelity need review.",
    "HTML entities are decoded; block-boundary newlines are inserted and outer block whitespace is trimmed.",
    "HTML locators refer to decoded original source code, not rendered pages or legal provision identities.",
    "A clean malware scan and exact digests establish neither privacy, usage rights nor legal applicability.",
]


class PreparationError(ValueError):
    """Fixed diagnostics only; source prose and local paths must not escape."""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def validate_acquisition(files):
    raw = files["raw.html"]
    manifest = _json(files["acquisition.json"])
    if not isinstance(manifest, dict) or not 0 < len(raw) <= MAX_BYTES:
        raise PreparationError("Invalid registered acquisition")
    source_id = manifest.get("registry_id")
    source = registered(source_id)
    digest = sha(raw)
    expected = {
        "schema_version": "registered-source-acquisition-v1", "registry_version": REGISTRY_VERSION,
        "registry_id": source_id, "title": source.title, "source_url": source.url,
        "source_version_id": f"{source_id}:sha256:{digest}", "domain": "contracts",
        "raw_sha256": digest, "byte_count": len(raw), "raw_media_type": "text/html",
        "rights_status": "rights_pending", "review_status": "legal_review_pending",
        "publication_status": "quarantined", "content_status": "untrusted_unscanned",
        "extraction_status": "not_processed", "representation": "enacted_text", "current_consolidation": False,
        "limitations": [HISTORICAL_LIMITATION,
            "Public availability does not establish permitted use, source identity review or legal applicability.",
            "This acquisition is unscanned and unparsed; admission and legal review are separate steps."],
    }
    if (set(manifest) != set(expected) | {"started_at", "acquired_at"}
            or any(encode(manifest[key]) != encode(value) for key, value in expected.items())):
        raise PreparationError("Invalid registered acquisition")
    try:
        dates = [datetime.fromisoformat(manifest[key]) for key in ("started_at", "acquired_at")]
        if any(date.tzinfo is None or date.utcoffset() is None for date in dates):
            raise ValueError
        if not dates[0] <= dates[1] <= datetime.now(UTC):
            raise ValueError
    except (ValueError, TypeError):
        raise PreparationError("Invalid acquisition dates") from None
    return manifest


def decode_html(raw):
    # No guessing or replacement decoding: a missing declaration admits UTF-8 only.
    declarations = re.findall(rb"charset\s*=\s*[\"']?\s*([A-Za-z0-9_-]+)", raw[:4096], re.I)
    aliases = {"utf-8": "utf-8", "utf8": "utf-8", "windows-1254": "cp1254",
               "iso-8859-9": "iso8859-9"}
    encodings = {aliases.get(item.decode("ascii").lower(), "unsupported") for item in declarations}
    if raw.startswith(b"\xef\xbb\xbf"):
        encodings.add("utf-8")
    if len(encodings) > 1 or "unsupported" in encodings:
        raise PreparationError("Unsupported or conflicting HTML encoding")
    encoding = next(iter(encodings), "utf-8")
    try:
        decoded = raw.removeprefix(b"\xef\xbb\xbf").decode(encoding, errors="strict")
    except UnicodeError:
        raise PreparationError("HTML encoding could not be decoded exactly") from None
    return decoded, encoding


class BlockParser(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.line_starts = [0] + [match.end() for match in re.finditer("\n", source)]
        self.parts, self.passages, self.suppressed = [], [], []
        self.start = self.end = None
        self.start_pos = None
        self.characters = self.block_characters = self.skipped_regions = 0

    def source_offset(self):
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def flush(self):
        text = "".join(self.parts).strip()
        if text:
            if len(self.passages) >= 5000 or len(text) > 20_000:
                raise PreparationError("HTML passage budget exceeded")
            self.passages.append({"text": text, "raw_start": self.start, "raw_end": self.end,
                                  "line": self.start_pos[0], "column": self.start_pos[1] + 1})
        self.parts, self.start, self.end, self.start_pos = [], None, None, None
        self.block_characters = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            if not self.suppressed:
                self.flush()
                self.skipped_regions += 1
            self.suppressed.append(tag)
        elif not self.suppressed and tag in BLOCKS:
            self.flush()

    def handle_startendtag(self, tag, attrs):
        if not self.suppressed and tag in BLOCKS:
            self.flush()
        elif tag in SKIP:
            if tag != "svg":
                raise PreparationError("Ambiguous self-closing omitted region")
            self.skipped_regions += 1

    def handle_endtag(self, tag):
        if self.suppressed:
            if tag in self.suppressed:
                # Matching an outer suppressed region closes any malformed inner regions too.
                last = len(self.suppressed) - 1 - self.suppressed[::-1].index(tag)
                self.suppressed = self.suppressed[:last]
        elif tag in BLOCKS:
            self.flush()

    def add(self, text, raw_length):
        if self.suppressed or not text:
            return
        self.characters += len(text)
        self.block_characters += len(text)
        if self.characters > 2_000_000 or self.block_characters > 20_000:
            raise PreparationError("HTML text budget exceeded")
        if self.start is None:
            self.start, self.start_pos = self.source_offset(), self.getpos()
        self.end = self.source_offset() + raw_length
        self.parts.append(text)

    def handle_data(self, data):
        self.add(data, len(data))

    def entity(self, token):
        # HTMLParser accepts semicolon-less entities. Use the actual consumed spelling.
        if self.source[self.source_offset() + len(token):self.source_offset() + len(token) + 1] == ";":
            token += ";"
        self.add(html.unescape(token), len(token))

    def handle_entityref(self, name):
        self.entity("&" + name)

    def handle_charref(self, name):
        self.entity("&#" + name)


def prepare(files):
    """Pure transcription: it never asserts scanning, approval or complete extraction."""
    started = time.monotonic()
    manifest = validate_acquisition(files)
    decoded, encoding = decode_html(files["raw.html"])
    parser = BlockParser(decoded)
    parser.feed(decoded)
    parser.close()
    parser.flush()
    if not parser.passages or parser.suppressed:
        raise PreparationError("HTML contains no usable text or an unclosed omitted region")
    text = "\n\n".join(passage["text"] for passage in parser.passages)
    encoded_text = text.encode("utf-8")
    if len(encoded_text) > PREPARATION_FILES["text.txt"]:
        raise PreparationError("HTML text byte budget exceeded")
    spans, origins, offset = [], [], 0
    for index, passage in enumerate(parser.passages, 1):
        identifier = f"html_block_{index:04d}"
        end = offset + len(passage["text"])
        locator = (f"HTML source line {passage['line']}, column {passage['column']}; "
                   f"decoded code points [{passage['raw_start']},{passage['raw_end']})")
        spans.append({"id": identifier, "start": offset, "end": end,
                      "text_sha256": sha(passage["text"].encode("utf-8")), "locator": locator})
        origins.append({"id": identifier, **{key: passage[key] for key in ("raw_start", "raw_end")}})
        offset = end + 2
    locators = {"schema_version": "public-locators-v1", "offset_unit": "unicode_code_points",
                "raw_sha256": manifest["raw_sha256"], "text_sha256": sha(encoded_text), "passages": spans}
    source = {"schema_version": "public-source-v1",
              **{key: manifest[key] for key in ("title", "source_url", "source_version_id", "domain",
                                               "acquired_at", "raw_media_type")},
              "published_on": None, "effective_from": None, "effective_until": None,
              "data_classification": "public", "origin": "public_legal_source",
              "contains_private_matter_data": False, "synthetic": False}
    report = {"schema_version": "registered-source-preparation-v1", "adapter_version": ADAPTER_VERSION,
              "registry_id": manifest["registry_id"], "raw_sha256": manifest["raw_sha256"],
              "text_sha256": sha(encoded_text), "decoded_html_sha256": sha(decoded.encode("utf-8")),
              "encoding": encoding, "decoded_offset_unit": "unicode_code_points_excluding_initial_utf8_bom",
              "passage_count": len(spans), "passage_origins": origins,
              "omitted_region_count": parser.skipped_regions, "elapsed_seconds": time.monotonic() - started,
              "representation": "enacted_text", "current_consolidation": False,
              "rights_status": "rights_pending", "review_status": "legal_review_pending",
              "publication_status": "prepared_for_staging", "extraction_fidelity_verified": False,
              "source_identity_verified": False, "sensitivity_reviewed": False, "limitations": WARNINGS}
    artifacts = {"raw.bin": files["raw.html"], "text.txt": encoded_text, "locators.json": encode(locators),
                 "source.json": encode(source), "acquisition.json": files["acquisition.json"],
                 "preparation.json": encode(report)}
    for name, raw in artifacts.items():
        if not 0 < len(raw) <= PREPARATION_FILES[name]:
            raise PreparationError("Prepared artifact budget exceeded")
    _validate({name: artifacts[name] for name in ("raw.bin", "text.txt", "locators.json", "source.json")})
    return artifacts


def main():
    cli = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    cli.add_argument("input", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    try:
        files = read_exact_directory(args.input, ACQUISITION_FILES, sum(ACQUISITION_FILES.values()))
        artifacts = prepare(files)
        if args.output.is_symlink() or not args.output.is_dir() or any(args.output.iterdir()):
            raise PreparationError("Worker output must be empty")
        for name, raw in artifacts.items():
            with (args.output / name).open("xb") as output:
                output.write(raw)
            (args.output / name).chmod(0o600)
    except (OSError, ValueError, TypeError, KeyError):
        cli.exit(1, "Registered preparation stopped.\n")


if __name__ == "__main__":
    main()
