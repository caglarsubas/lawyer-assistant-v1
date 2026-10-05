"""Bounded, deterministic heading proposals from an already verified source.

These are textual candidates, not legal identities or authoritative provision
boundaries. No source text is normalized and no dates or legal effects are inferred.
"""

import hashlib
import json
import re
from collections import Counter

from .public_sources import VerifiedPublicSource

EXTRACTION_VERSION = "tr-article-headings-v1"
MAX_CANDIDATES = 500
MAX_SPAN = 20_000

# Only explicit line-start headings. Horizontal whitespace is admitted without
# rewriting it; quoted headings remain proposals with a separate warning. A word
# after the number is not a heading delimiter (e.g. "Madde 1 gereğince...").
_HEADING = re.compile(
    r"^[ \t\u00a0]*(?P<quote>[\"“‘«']?)[ \t\u00a0]*"
    r"(?P<heading>(?:(?P<prefix>GEÇİCİ|EK)[ \t\u00a0]+)?"
    r"MADDE[ \t\u00a0]+(?P<number>[0-9]{1,6}(?:[ \t\u00a0]*/[ \t\u00a0]*[A-ZÇĞİÖŞÜ])?))"
    r"(?!\.[0-9])(?=[ \t\u00a0]*(?:[-–—:.()\r\n\u2028\u2029]|$))",
    re.IGNORECASE,
)

LIMITATIONS = [
    "Öneriler yalnızca açık satır başı madde başlıklarına dayanır; eksik veya farklı biçimli başlıklar bulunamayabilir.",
    "Başlıklar alıntı, değişiklik metni veya içindekiler kaydı olabilir; önerilen sınırlar hukuki inceleme gerektirir.",
    "Kanun, madde ve sürüm kimlikleri ile yürürlük tarihleri çözümlenmemiştir; güncel hukuk varsayılmaz.",
    "Pasaj kapsamı metnin okuma sırasını, aslına uygunluğunu veya hukuki sınırlarını doğrulamaz.",
]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _candidate_id(package: VerifiedPublicSource, heading: dict) -> str:
    identity = json.dumps([package.detail["id"], EXTRACTION_VERSION, heading["start"], heading["end"]],
                          ensure_ascii=False, separators=(",", ":"))
    return _sha(identity)


def span_details(package: VerifiedPublicSource, start: int, end: int) -> dict:
    """Describe an exact Unicode slice and admitted locator coverage, without IO."""
    if (type(start) is not int or type(end) is not int
            or not 0 <= start < end <= len(package.text) or end - start > MAX_SPAN):
        raise ValueError("Invalid provision span")
    passage_ids = []
    cursor, has_gaps, covered = start, False, True
    for passage in package.locators.passages:
        if passage.end <= start:
            continue
        if passage.start >= end:
            break
        passage_ids.append(passage.id)
        if passage.start > cursor:
            has_gaps = True
            covered = covered and not package.text[cursor:min(passage.start, end)].strip()
        cursor = max(cursor, min(passage.end, end))
    if cursor < end:
        has_gaps = True
        covered = covered and not package.text[cursor:end].strip()
    text = package.text[start:end]
    return {
        "span": {"start": start, "end": end, "text": text, "sha256": _sha(text)},
        "passage_ids": passage_ids,
        "non_whitespace_covered": bool(covered),
        "has_locator_gaps": has_gaps,
    }


def _headings(text: str) -> tuple[list[dict], bool]:
    headings, start = [], 0
    # splitlines preserves CRLF, lone CR and Unicode line separators in offsets.
    for line in text.splitlines(keepends=True):
        match = _HEADING.match(line)
        if match:
            prefix = match.group("prefix")
            kind = ("additional_article" if prefix and prefix.upper() == "EK"
                    else "temporary_article" if prefix else "article")
            number = re.sub(r"[ \t\u00a0]", "", match.group("number"))
            # Normalize only the display label, never the underlying source span.
            number = number.replace("i", "İ").replace("ı", "I").upper()
            label_prefix = {"article": "MADDE", "temporary_article": "GEÇİCİ MADDE",
                            "additional_article": "EK MADDE"}[kind]
            headings.append({"start": start + match.start("heading"),
                             "end": start + match.end("heading"), "kind": kind,
                             "number": number, "label": f"{label_prefix} {number}",
                             "quoted": bool(match.group("quote"))})
            # The extra heading supplies the true next boundary for candidate500.
            if len(headings) > MAX_CANDIDATES:
                return headings, True
        start += len(line)
    return headings, False


def _candidate(package: VerifiedPublicSource, heading: dict, end: int,
               repeated: bool) -> dict:
    proposed_end = min(end, heading["start"] + MAX_SPAN)
    detail = span_details(package, heading["start"], proposed_end)
    warnings = ["Önerilen metin sınırları bölüm başlıkları veya editoryal metin içerebilir; inceleyin."]
    if repeated:
        warnings.append("Bu başlık kaynakta birden fazla kez geçiyor; her örnek ayrı çözümlenmelidir.")
    if heading["quoted"]:
        warnings.append("Başlık tırnak işaretiyle başlıyor; alıntı veya değişiklik metni olabilir.")
    if proposed_end < end:
        warnings.append("Önerilen metin 20.000 karakter sınırında kesildi; devamı ayrıca incelenmelidir.")
    if detail["has_locator_gaps"]:
        warnings.append("Pasaj konumları arasında boşluklar var; pasaj kapsamı sınır doğrulaması değildir.")
    if not detail["non_whitespace_covered"]:
        warnings.append("Boşluk dışındaki bazı karakterler hiçbir kabul edilmiş pasaj konumuyla kapsanmıyor.")
    heading_text = package.text[heading["start"]:heading["end"]]
    return {
        "id": _candidate_id(package, heading), "kind": heading["kind"], "label": heading["label"],
        "number": heading["number"],
        "heading": {"start": heading["start"], "end": heading["end"],
                    "text": heading_text, "sha256": _sha(heading_text)},
        "proposed_span": detail["span"], "passage_ids": detail["passage_ids"],
        "warnings": warnings, "status": "machine_proposed", "identity_status": "unresolved",
        "non_whitespace_covered": detail["non_whitespace_covered"],
    }


def find_candidates(package: VerifiedPublicSource, *, offset: int = 0, limit: int = 20) -> dict:
    if type(offset) is not int or not 0 <= offset <= MAX_CANDIDATES or type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("Invalid provision candidate page bounds")
    headings, truncated = _headings(package.text)
    total = min(len(headings), MAX_CANDIDATES)
    counts = Counter((heading["kind"], heading["number"]) for heading in headings)
    items = []
    for index in range(offset, min(offset + limit, total)):
        heading = headings[index]
        end = headings[index + 1]["start"] if index + 1 < len(headings) else len(package.text)
        items.append(_candidate(package, heading, end, counts[(heading["kind"], heading["number"])] > 1))
    next_offset = offset + len(items)
    limitations = list(LIMITATIONS)
    if truncated:
        limitations.append("İlk 500 başlık gösteriliyor; kaynakta ek başlıklar var ve bu sonuç tam kapsam değildir.")
    return {"source_id": package.detail["id"], "source_version_id": package.metadata.source_version_id,
            "text_sha256": package.locators.text_sha256, "extraction_version": EXTRACTION_VERSION,
            "items": items, "total": total, "next_offset": next_offset if next_offset < total else None,
            "truncated": truncated, "limitations": limitations}


class CandidateLookup:
    """Request-local heading index; no global cache or eager text materialization."""

    def __init__(self, package: VerifiedPublicSource):
        self._package = package
        self._headings, _ = _headings(package.text)
        self._counts = Counter((heading["kind"], heading["number"]) for heading in self._headings)
        self._indices = {_candidate_id(package, heading): index
                         for index, heading in enumerate(self._headings[:MAX_CANDIDATES])}

    def get(self, identifier: str) -> dict:
        if not isinstance(identifier, str) or identifier not in self._indices:
            raise ValueError("Unknown provision candidate")
        index = self._indices[identifier]
        heading = self._headings[index]
        end = self._headings[index + 1]["start"] if index + 1 < len(self._headings) else len(self._package.text)
        # A fresh result prevents callers from mutating a cached evidence record.
        return _candidate(self._package, heading, end, self._counts[(heading["kind"], heading["number"])] > 1)


def candidate_for_id(package: VerifiedPublicSource, identifier: str) -> dict:
    return CandidateLookup(package).get(identifier)
