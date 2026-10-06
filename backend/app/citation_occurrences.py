"""Bounded literal-number discovery, never authority or provision resolution.

The deliberately narrow grammar requires explicit labels. No court, case pairing,
instrument alias, historical version, endorsement or legal effect is inferred.
"""

import re

PROFILE = "tr-literal-citations-v1"
MAX_TEXT = 12000
MAX_OCCURRENCES = 64
MAX_QUERY_KEYS = 16
SPACE = r"[ \t\u00a0]"
NUMBER_LABEL = r"(?:No\.?|Numarası|Sayısı)"
CASE_NUMBER = rf"(?P<year>[0-9]{{4}}){SPACE}*/{SPACE}*(?P<number>[0-9]{{1,9}})(?![\w/]|[.,][0-9]|{SPACE}*/)"


def _pattern(label, number):
    return re.compile(rf"(?<![\w./])(?P<label>{label}){SPACE}*:?{SPACE}*{number}", re.IGNORECASE)


PATTERNS = (
    ("esas", _pattern(rf"(?:E\.|Esas\b(?:{SPACE}+{NUMBER_LABEL})?)", CASE_NUMBER)),
    ("karar", _pattern(rf"(?:K\.|Karar\b(?:{SPACE}+{NUMBER_LABEL})?)", CASE_NUMBER)),
    ("application", _pattern(rf"(?:B\.{SPACE}*No\.?|Başvuru{SPACE}+{NUMBER_LABEL})", CASE_NUMBER)),
    ("law", _pattern(rf"Kanun{SPACE}+{NUMBER_LABEL}", rf"(?P<number>[0-9]{{1,6}})(?![\w/]|[.,][0-9]|{SPACE}*/)")),
    ("law", re.compile(rf"(?<![\w.,/+−-])(?P<number>[0-9]{{1,6}}){SPACE}+sayılı{SPACE}+Kanun(?:u|un)?\b"
                       rf"(?!{SPACE}+Hükmünde)", re.IGNORECASE)),
)
PREVIOUS_CASE = re.compile(rf"[0-9]{{4}}{SPACE}*/{SPACE}*[0-9]{{1,9}}{SPACE}*$")


class CitationQueryLimit(ValueError):
    """Skip this channel without truncating keys or blocking other retrieval."""


def scan(text):
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise ValueError("Citation text exceeds its bounded character limit")
    candidates = sorted(((match.start(), match.end(), kind, match) for kind, pattern in PATTERNS
                         for match in pattern.finditer(text)), key=lambda row: row[:3])
    occurrences = []
    for start, end, kind, match in candidates:
        if occurrences and start < occurrences[-1]["end"]:
            continue
        previous = PREVIOUS_CASE.search(text[:start])
        # Do not read a trailing label in an unsupported suffix-style citation
        # as the prefix of the next number. A preceding recognized prefix is OK.
        if previous and not any(row["start"] <= previous.start() and row["end"] >= len(text[:start].rstrip(" \t\u00a0"))
                                for row in occurrences):
            continue
        if len(occurrences) == MAX_OCCURRENCES:
            return {"occurrences": occurrences, "truncated": True}
        parts = [kind]
        if kind != "law":
            parts.append(match["year"])
        parts.append(match["number"])
        occurrences.append({"kind": kind, "key": ":".join(parts), "start": start, "end": end,
                            "literal": text[start:end]})
    return {"occurrences": occurrences, "truncated": False}


def query_keys(query):
    parsed = scan(query)
    keys = sorted({row["key"] for row in parsed["occurrences"]})
    if parsed["truncated"] or len(keys) > MAX_QUERY_KEYS:
        raise CitationQueryLimit("Split the query into at most 16 distinct labeled citation numbers and 64 occurrences")
    return keys


def source_occurrences(source):
    rows = []
    for field in ("text", "title"):
        parsed = scan(source[field])
        if parsed["truncated"]:
            raise ValueError("Source exceeds the literal citation occurrence budget")
        rows.extend({**row, "field": field} for row in parsed["occurrences"])
    return rows


def derived_fields(source):
    return {"citation_keys": sorted({row["key"] for row in source_occurrences(source)})}


def matching_occurrences(source, keys):
    wanted = set(keys)
    rows, truncated = [], False
    for field in ("text", "title"):
        parsed = scan(source[field])
        truncated = truncated or parsed["truncated"]
        rows.extend({**row, "field": field} for row in parsed["occurrences"] if row["key"] in wanted)
    return {"resolution": "unresolved", "offset_unit": "unicode_codepoint", "occurrences": rows[:32],
            "truncated": truncated or len(rows) > 32}
