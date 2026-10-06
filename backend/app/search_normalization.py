"""Derived retrieval terms and exact Python-codepoint spans, never legal identities.

No stemming, stop-word removal, OCR repair, number coercion or compatibility
normalization. The deliberately lossy folded channel only nominates candidates.
"""

import unicodedata
from dataclasses import dataclass

PROFILE = "turkish-lexical-v1"
MAX_TEXT = 12000
VARIANTS = ("original", "normalized", "folded")
APOSTROPHES = "'’‘ʼ＇"
JOINERS = ".,/-:"


def normalization_metadata():
    return {"profile": PROFILE, "unicode_version": unicodedata.unidata_version}


@dataclass(frozen=True)
class Token:
    start: int
    end: int
    original: str
    normalized: str
    folded: str


def tokens(text):
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise ValueError("Retrieval text exceeds its bounded character limit")
    result, start, index = [], None, 0
    while index < len(text):
        char = text[index]
        category = unicodedata.category(char)[0]
        following = text[index + 1] if index + 1 < len(text) else ""
        previous = text[index - 1] if index else ""
        word = category in "LN" or (category == "M" and start is not None)
        apostrophe = start is not None and char in APOSTROPHES and following.isalnum()
        number_join = start is not None and char in JOINERS and previous.isdecimal() and following.isdecimal()
        sign = start is None and char in "+-−" and following.isdecimal()
        if word or apostrophe or number_join or sign:
            if start is None:
                start = index
        elif start is not None:
            result.append(_token(text, start, index))
            start = None
        index += 1
    if start is not None:
        result.append(_token(text, start, index))
    return result


def _token(text, start, end):
    original = text[start:end]
    normalized = unicodedata.normalize("NFC", original)
    normalized = normalized.translate(str.maketrans({char: "'" for char in APOSTROPHES}))
    normalized = normalized.replace("İ", "i").replace("I", "ı").lower()
    normalized = unicodedata.normalize("NFC", normalized)
    folded = "".join(char for char in unicodedata.normalize("NFD", normalized)
                     if unicodedata.category(char)[0] != "M").replace("ı", "i")
    return Token(start, end, original, normalized, folded)


def terms(text):
    parsed = tokens(text)
    return {variant: " ".join(getattr(token, variant) for token in parsed) for variant in VARIANTS}


def derived_fields(source):
    return {f"{field}_{variant}": value for field in ("text", "title")
            for variant, value in terms(source[field]).items()}


def match_spans(source, query, limit=32):
    """Explain literal/normalized token matches against already verified text.

    These are not OpenSearch score explanations or evidence of applicability.
    Return no HTML or rewritten quote; offsets address the exact returned fields.
    """
    if type(limit) is not int or not 1 <= limit <= 32:
        raise ValueError("Match span limit must be 1–32")
    query_tokens = tokens(query)
    wanted = {variant: {getattr(token, variant) for token in query_tokens} for variant in VARIANTS}
    matches = []
    for field in ("text", "title"):
        for token in tokens(source[field]):
            channels = ["lexical_" + variant for variant in VARIANTS if getattr(token, variant) in wanted[variant]]
            if channels:
                if len(matches) == limit:
                    return {"offset_unit": "unicode_codepoint", "spans": matches, "truncated": True}
                matches.append({"field": field, "start": token.start, "end": token.end, "channels": channels})
    return {"offset_unit": "unicode_codepoint", "spans": matches, "truncated": False}
