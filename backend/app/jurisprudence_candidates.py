"""Bounded literal occurrences for curator inspection, never resolved legal facts.

Input is one selected passage from an integrity-verified public source. No raw
parser, model, network, party matching, mutation or graph update is performed.
"""

import hashlib
import json
import re
from datetime import date

EXTRACTION_VERSION = "tr-jurisprudence-occurrences-v1"
MAX_PASSAGE = 20_000
MAX_OCCURRENCES = 200
MAX_RECEIPT = 256 * 1024
H = r"[ \t\u00a0]{1,8}"
GAP = r"[ \t\u00a0]{0,8}(?:\r?\n)?[ \t\u00a0]{0,8}"
LABEL_END = GAP + r"[:：]?" + GAP
NUMBER = r"(?P<value>[0-9]{4}[ \t\u00a0]{0,8}/[ \t\u00a0]{0,8}[0-9]{1,7})(?![\w/]|[.,][0-9]|[ \t\u00a0]{0,8}/)"
DATE = r"(?P<value>[0-9]{1,2}(?P<separator>[/\.])[0-9]{1,2}(?P=separator)[0-9]{4})(?![\w/\.])"
RULES = tuple((kind, rule, re.compile(r"(?<![\w./])" + pattern, re.IGNORECASE)) for kind, rule, pattern in (
    ("application_number", "application_label", r"(?:Başvuru" + H + r"Numarası|B\." + GAP + r"No\.?)" + LABEL_END + NUMBER),
    ("case_number", "case_label", r"Esas" + H + r"(?:No\.?|Numarası)" + LABEL_END + NUMBER),
    ("decision_number", "decision_label", r"Karar" + H + r"(?:No\.?|Numarası)" + LABEL_END + NUMBER),
    ("decision_date", "decision_date_label", r"Karar" + H + r"Tarihi" + LABEL_END + DATE),
    ("publication_date", "publication_date_label", r"(?:Resm[îi]" + H + r"Gazete" + H + r"Tarihi|Yayın" + H + r"Tarihi)" + LABEL_END + DATE),
    ("instrument_number_reference", "number_sayili", r"(?P<value>[0-9]{1,5})" + H + r"sayılı(?!\w)"),
    ("article_number_reference", "article_prefix", r"(?:MADDE|m\.|md\.)" + H + r"(?P<value>[0-9]{1,4})(?![\w/]|\.[0-9])"),
    ("article_number_reference", "article_suffix", r"(?P<value>[0-9]{1,4})\." + H + r"(?:maddesi|maddesinin|madde)(?!\w)"),
))
LIMITATIONS = [
    "Yalnızca seçili pasajdaki sınırlı yazım biçimleri aranır; sonuç tüm kararın veya külliyatın taraması değildir.",
    "Numara ve tarih bir alıntıya, önceki karara veya editoryal kayda ait olabilir; belge kimliği ve olay rolü bilinmiyor.",
    "Geçerli takvim biçimi kararın yayımlanmasını, kesinleşmesini veya hukuki etkisini doğrulamaz.",
    "Madde ve sayılı belge anmaları atıf adayıdır; kanun/sürüm kimliği, uygulama ve bağlayıcılık çözümlenmemiştir.",
    "Eksik veya farklı biçimli anmalar bulunamayabilir; kişisel veri, haklar ve aslına uygunluk ayrı inceleme gerektirir.",
]


class JurisprudenceCandidatesUnavailable(ValueError):
    """Fixed diagnostics; never interpolate source prose or operator paths."""


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _parsed(kind, value):
    if kind.endswith("_date"):
        parts = re.split(r"[/\.]", value)
        try:
            return date(int(parts[2]), int(parts[1]), int(parts[0])).isoformat(), "calendar_valid_only"
        except ValueError:
            return None, "invalid_calendar_date"
    # Only a separate syntax hint is compacted; the evidence spelling is intact.
    return re.sub(r"[ \t\u00a0]", "", value), "syntax_only"


def find_occurrences(package, passage_id):
    if not isinstance(passage_id, str) or re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}", passage_id) is None:
        raise JurisprudenceCandidatesUnavailable("Invalid selected passage")
    passage = next((item for item in package.locators.passages if item.id == passage_id), None)
    if passage is None or passage.end - passage.start > MAX_PASSAGE:
        raise JurisprudenceCandidatesUnavailable("Selected passage unavailable or exceeds work budget")
    text = package.text[passage.start:passage.end]
    if _sha(text.encode("utf-8")) != passage.text_sha256:
        raise JurisprudenceCandidatesUnavailable("Selected passage integrity failed")
    items = []
    for kind, rule, pattern in RULES:
        for match in pattern.finditer(text):
            if len(items) >= MAX_OCCURRENCES:
                raise JurisprudenceCandidatesUnavailable("Occurrence work budget exceeded")
            start, end = passage.start + match.start(), passage.start + match.end()
            exact = text[match.start():match.end()]
            value = match.group("value")
            parsed, parse_status = _parsed(kind, value)
            identity = [package.detail["id"], package.metadata.source_version_id,
                        package.locators.raw_sha256, package.locators.text_sha256,
                        passage_id, passage.text_sha256, EXTRACTION_VERSION, rule, start, end]
            items.append({
                "id": _sha(encode(identity)), "kind": kind, "rule": rule,
                "start": start, "end": end, "passage_start": match.start(), "passage_end": match.end(),
                "text": exact, "sha256": _sha(exact.encode("utf-8")),
                "value_start": passage.start + match.start("value"),
                "value_end": passage.start + match.end("value"), "value_text": value,
                "parsed_value": parsed, "parse_status": parse_status,
                "status": "machine_proposed", "identity_status": "unresolved",
                "event_role": "unknown", "authority_treatment": "unknown",
            })
    items.sort(key=lambda item: (item["start"], item["end"], item["rule"]))
    result = {
        "schema_version": "jurisprudence-occurrences-v1", "extraction_version": EXTRACTION_VERSION,
        "source_id": package.detail["id"], "source_version_id": package.metadata.source_version_id,
        "raw_sha256": package.locators.raw_sha256, "text_sha256": package.locators.text_sha256,
        "passage_id": passage_id, "passage_sha256": passage.text_sha256,
        "passage_start": passage.start, "passage_end": passage.end, "locator": passage.locator,
        "offset_unit": "unicode_code_points", "scope": "selected_passage_only",
        "integrity_scope": "all_artifacts_verified", "items": items, "count": len(items),
        "truncated": False, "legal_identity_resolved": False, "dates_promoted": False,
        "human_review_recorded": False, "graph_updated": False, "limitations": LIMITATIONS,
    }
    if len(encode(result)) > MAX_RECEIPT:
        raise JurisprudenceCandidatesUnavailable("Occurrence receipt budget exceeded")
    return result
