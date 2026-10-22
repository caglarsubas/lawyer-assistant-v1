"""Offline candidate only: neighboring whole lines, exact spans, explicit omissions.

No provider, source acquisition, application hook or semantic/legal inference.
Windows express proximity, never a legally sufficient condition or complete context.
"""

import hashlib
import json
import re

from app.evidence_prompt import COMPLETION_RESERVE, FRAMING_RESERVE, canonical, quote_messages

RECIPE = "offline-neighbor-line-quotes-v1"
MAX_QUOTES = 64
MAX_QUOTE_BYTES = 768
LINE = re.compile(r"[^\r\n]+")


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def candidate_catalog(evidence, originals):
    # Reuse the existing envelope's strict identity/UTF8/size bounds, without
    # changing its production catalog or importing any provider implementation.
    quote_messages("SYNTHETIC offline validation", evidence)
    if not isinstance(originals, list) or len(originals) > 2000:
        raise ValueError("Invalid frozen original inventory")
    if any(not isinstance(p, dict) or not isinstance(p.get("id"), str) or not 1 <= len(p["id"]) <= 128
           or not isinstance(p.get("text"), str) for p in originals):
        raise ValueError("Invalid frozen original record")
    if sum(len(p["text"]) for p in originals) > 2_000_000:
        raise ValueError("Frozen source scan budget exceeded")
    source = {p["id"]: p for p in originals}
    if len(source) != len(originals):
        raise ValueError("Ambiguous frozen original")
    catalog, omitted, pins = {}, [], []
    for p in evidence:
        if p["id"] not in source:
            raise ValueError("Frozen original missing")
        original = source[p["id"]]
        text, full = p["text"], original["text"]
        start, end = p["excerpt_start"], p["excerpt_end"]
        if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(full)
                or text != full[start:end] or p["full_passage_length"] != len(full)
                or original["text_sha256"] != sha(full)
                or any(p[k] != original[k] for k in ("document_id", "document_revision", "document_sha256"))):
            raise ValueError("Frozen source span or identity differs")
        pins.append({"evidence_id": p["id"], "document_id": original["document_id"],
                     "document_revision": original["document_revision"], "document_sha256": original["document_sha256"],
                     "original_text_sha256": sha(full), "excerpt_text_sha256": sha(text),
                     "excerpt_start": start, "excerpt_end": end, "full_passage_length": len(full)})
        rows = list(LINE.finditer(text))
        seen = set()
        for index, row in enumerate(rows):
            if not row.group().strip():
                continue
            reason = None
            left = right = index
            if index and text[rows[index - 1].end():row.start()] in {"\n", "\r", "\r\n"}:
                left -= 1
            if index + 1 < len(rows) and text[row.end():rows[index + 1].start()] in {"\n", "\r", "\r\n"}:
                right += 1
            a, b = rows[left].start(), rows[right].end()
            span = (a, b)
            if span in seen:
                continue
            seen.add(span)
            absolute_a, absolute_b = start + a, start + b
            if ((absolute_a and full[absolute_a - 1] not in "\r\n")
                    or (absolute_b < len(full) and full[absolute_b] not in "\r\n")):
                reason = "partial_physical_line"
            elif len(text[a:b].encode()) > MAX_QUOTE_BYTES:
                reason = "whole_window_byte_limit"
            elif len(catalog) >= MAX_QUOTES:
                reason = "catalog_count_limit"
            if reason:
                omitted.append({"evidence_id": p["id"], "start": a, "end": b, "reason": reason})
            else:
                catalog["Q" + str(len(catalog) + 1)] = {"evidence_id": p["id"], "start": a, "end": b,
                    "original_start": absolute_a, "original_end": absolute_b, "text": text[a:b], "text_sha256": sha(text[a:b])}
    return {"recipe": RECIPE, "offset_unit": "unicode_code_points", "catalog": catalog,
            "omitted_windows": omitted, "source_pins": pins,
            "limits": {"max_quotes": MAX_QUOTES, "max_quote_utf8_bytes": MAX_QUOTE_BYTES, "neighbor_lines": 1},
            "limitations": ["proximity_not_legal_association", "partial_evidence_not_complete_context"]}


def candidate_prompt(question, evidence, plan, context_limit):
    if type(context_limit) is not int or context_limit <= 0:
        raise ValueError("Invalid candidate context budget")
    messages = quote_messages(question, evidence)
    value = json.loads(messages[1]["content"])
    for item in value["evidence"]:
        item["quotes"] = [{"id": identity, "start": q["start"], "end": q["end"]}
                          for identity, q in plan["catalog"].items() if q["evidence_id"] == item["id"]]
    messages[1]["content"] = canonical(value)
    size = sum(len(m["content"].encode()) for m in messages)
    units = size + FRAMING_RESERVE + COMPLETION_RESERVE
    return {"recipe": RECIPE, "messages_sha256": sha(canonical(messages)), "utf8_bytes": size,
            "total_upper_bound_units": units, "context_limit_units": context_limit,
            "within_budget": units <= context_limit, "accounting": "utf8_bytes_plus_fixed_reserves"}


def resolve_offline(ids, plan, evidence, originals):
    # Rebuild from current frozen inputs. A reused identity from another version,
    # forged text/offset or edited plan must not authorize a quotation.
    if plan != candidate_catalog(evidence, originals):
        raise ValueError("Stale or modified offline catalog")
    catalog = plan["catalog"]
    if (not isinstance(ids, list) or len(ids) > 20 or any(not isinstance(i, str) or i not in catalog for i in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("Unverified offline quotation selection")
    return [{"text": catalog[i]["text"], "evidence_ids": [catalog[i]["evidence_id"]]} for i in ids]
