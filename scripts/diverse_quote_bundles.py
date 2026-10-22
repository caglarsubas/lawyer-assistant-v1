"""Offline source-version round robin and labeled unmatched-source fallback.

No inference, application hook, synonym knowledge or legal association. This
separately versioned candidate never changes the retained v1/production recipes.
"""

import json
import re
import unicodedata
from collections import Counter, defaultdict

from budgeted_quote_bundles import MAX_BUNDLES, MAX_PART_BYTES, MAX_PARTS, SYSTEM, words
from offline_quotation_boundaries import LINE, sha

from app.context_packing import (
    MAX_CANDIDATES,
    MAX_PASSAGE_BYTES,
    MAX_PASSAGES,
    MAX_SCANNED_CODE_POINTS,
    STOP_WORDS,
    TEXT_BYTE_BUDGET,
)
from app.evidence_prompt import COMPLETION_RESERVE, FRAMING_RESERVE, canonical, quote_messages

RECIPE = "offline-diverse-source-bundles-v2"
MAX_LINES = 20_000
SYSTEM_V2 = SYSTEM + (" unmatched_source_fallback sözcük eşleşmesi olmadan seçilmiş kaynak başlangıcıdır; "
                     "ilgili olduğu varsayılmaz. Farklı source_version değerlerini birleştirme.")


def validate_sources(question, originals, limit):
    quote_messages(question, [])
    if type(limit) is not int or limit <= 0 or not isinstance(originals, list) or len(originals) > MAX_CANDIDATES:
        raise ValueError("Invalid offline diversity inventory or limit")
    identities, versions, points, lines = set(), {}, 0, 0
    for p in originals:
        if (not isinstance(p, dict) or not isinstance(p.get("id"), str) or not 1 <= len(p["id"]) <= 128
                or p["id"] in identities or not isinstance(p.get("text"), str)
                or not isinstance(p.get("document_id"), str) or not 1 <= len(p["document_id"]) <= 128
                or type(p.get("document_revision")) is not int or p["document_revision"] <= 0
                or not isinstance(p.get("document_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", p["document_sha256"])
                or p.get("text_sha256") != sha(p["text"])):
            raise ValueError("Invalid frozen source identity or hash")
        identities.add(p["id"])
        key = p["document_id"], p["document_revision"]
        if key in versions and versions[key] != p["document_sha256"]:
            raise ValueError("Ambiguous frozen source version")
        versions[key] = p["document_sha256"]
        points += len(p["text"])
        if points > MAX_SCANNED_CODE_POINTS:
            raise ValueError("Offline diversity source scan limit exceeded")
        for m in LINE.finditer(p["text"]):
            lines += bool(m.group().strip())
            if lines > MAX_LINES:
                raise ValueError("Offline diversity physical-line work limit exceeded")
    return points, lines


def version_key(p):
    return p["document_id"], p["document_revision"], p["document_sha256"]


def envelope(question, bundles, limit):
    payload = {"question": question, "bundles": [{k: b[k] for k in
        ("id", "source_version", "nomination", "parts", "boundary_flags", "fallback", "partial_source")} for b in bundles]}
    # Private manifest hashes/ranking/complete source inventory stay outside the
    # prompt. Every copied text still has an exact source ID and absolute span.
    for b in payload["bundles"]:
        b["parts"] = [{k: p[k] for k in ("evidence_id", "original_start", "original_end", "text", "role")} for p in b["parts"]]
    messages = [{"role": "system", "content": SYSTEM_V2}, {"role": "user", "content": canonical(payload)}]
    size = sum(len(m["content"].encode()) for m in messages)
    units = size + FRAMING_RESERVE + COMPLETION_RESERVE
    return messages, {"recipe": RECIPE, "messages_sha256": sha(canonical(messages)), "utf8_bytes": size,
        "total_upper_bound_units": units, "context_limit_units": limit, "within_budget": units <= limit,
        "accounting": "utf8_bytes_plus_fixed_reserves"}


def plan_diverse(question, originals, *, context_limit=8192):
    points, count = validate_sources(question, originals, context_limit)
    query = words(question) - set().union(*(words(w) for w in STOP_WORDS))
    rows = [(p, [m for m in LINE.finditer(p["text"]) if m.group().strip()]) for p in originals]
    freq = Counter(w for _, matches in rows for m in matches for w in words(m.group()) & query)
    buckets, omissions, seen = defaultdict(list), [], set()
    version_order = {key: n for n, key in enumerate(dict.fromkeys(version_key(p) for p in originals))}
    for ordinal, (p, matches) in enumerate(rows):
        nominated = [(i, words(m.group()) & query) for i, m in enumerate(matches) if words(m.group()) & query]
        if not nominated and matches:
            nominated = [(0, set())]
        if not matches:
            omissions.append({"evidence_id": p["id"], "reason": "empty_source_passage"})
        for index, overlap in nominated:
            indices, flags = [index], []
            for other in (index - 1, index + 1):
                if not 0 <= other < len(matches):
                    flags.append("passage_edge_context_not_linked")
                    continue
                left, right = sorted((index, other))
                gap = p["text"][matches[left].end():matches[right].start()]
                distance = gap.replace("\r\n", "\n").replace("\r", "\n").count("\n")
                if gap.isspace() and distance <= 2:
                    indices.append(other)
                    if distance == 2:
                        flags.append("blank_separated_companion")
                else:
                    flags.append("separator_context_not_linked")
            spans = [(matches[i].start(), matches[i].end(), "anchor" if i == index else "companion") for i in sorted(indices)]
            fallback = None
            if any(len(p["text"][a:b].encode()) > MAX_PART_BYTES for a, b, _ in spans):
                if len(p["text"].encode()) <= MAX_PASSAGE_BYTES:
                    spans, fallback = [(0, len(p["text"]), "coarse_anchor_and_context")], "whole_passage"
                else:
                    omissions.append({"evidence_id": p["id"], "anchor_start": matches[index].start(),
                                      "reason": "no_complete_coarse_fallback"})
                    continue
            identity = tuple((p["id"], a, b) for a, b, _ in spans)
            if identity in seen:
                continue
            seen.add(identity)
            key = version_key(p)
            parts = [{"evidence_id": p["id"], "original_start": a, "original_end": b, "text": p["text"][a:b],
                      "text_sha256": sha(p["text"][a:b]), "role": role} for a, b, role in spans]
            buckets[key].append({"score": sum((count + 1) // freq[w] for w in overlap), "ordinal": ordinal,
                "anchor_start": matches[index].start(), "source_version": "S" + str(version_order[key] + 1),
                "nomination": "query_overlap" if overlap else "unmatched_source_fallback", "parts": parts,
                "boundary_flags": sorted(set(flags)), "fallback": fallback,
                "partial_source": sum(b - a for a, b, _ in spans) != len(p["text"])})
    for bucket in buckets.values():
        bucket.sort(key=lambda b: (-b["score"], b["ordinal"], b["anchor_start"]))
    order = sorted(buckets, key=lambda k: (-buckets[k][0]["score"], version_order[k]))
    selected, used_ids, used_bytes, sequence = [], set(), 0, 0
    for depth in range(max((len(b) for b in buckets.values()), default=0)):
        for key in order:
            if depth >= len(buckets[key]):
                continue
            sequence += 1
            bundle = {"id": "D" + str(sequence), **buckets[key][depth]}
            ids = {p["evidence_id"] for p in bundle["parts"]}
            size = sum(len(p["text"].encode()) for p in bundle["parts"])
            reason = None
            if len(selected) >= MAX_BUNDLES or sum(len(b["parts"]) for b in selected) + len(bundle["parts"]) > MAX_PARTS:
                reason = "bundle_or_part_limit"
            elif len(used_ids | ids) > MAX_PASSAGES:
                reason = "evidence_passage_limit"
            elif used_bytes + size > TEXT_BYTE_BUDGET:
                reason = "copied_text_byte_budget"
            elif not envelope(question, selected + [bundle], context_limit)[1]["within_budget"]:
                reason = "whole_bundle_prompt_budget"
            if reason:
                omissions.append({"evidence_id": bundle["parts"][0]["evidence_id"], "bundle_id": bundle["id"], "reason": reason})
            else:
                selected.append(bundle)
                used_ids |= ids
                used_bytes += size
    measured = envelope(question, selected, context_limit)[1]
    value = {"recipe": RECIPE, "question_sha256": sha(question), "unicode_version": unicodedata.unidata_version,
        "source_inventory_sha256": sha(canonical(originals)), "selection_policy": "source_version_round_robin_with_labeled_first_line_fallback",
        "limits": {"bundles": MAX_BUNDLES, "parts": MAX_PARTS, "evidence_passages": MAX_PASSAGES,
            "copied_text_utf8_bytes": TEXT_BYTE_BUDGET, "part_utf8_bytes": MAX_PART_BYTES,
            "coarse_fallback_utf8_bytes": MAX_PASSAGE_BYTES, "source_passages": MAX_CANDIDATES,
            "scanned_code_points": MAX_SCANNED_CODE_POINTS, "nonblank_physical_lines": MAX_LINES},
        "source_pins": [{k: p[k] for k in ("id", "document_id", "document_revision", "document_sha256", "text_sha256")}
                        for p in originals], "bundles": selected, "omitted_candidates": omissions,
        "unrepresented_evidence_ids": [p["id"] for p in originals if p["id"] not in used_ids],
        "unrepresented_source_versions": [{"document_id": k[0], "document_revision": k[1], "document_sha256": k[2]}
            for k in version_order if not any(b["source_version"] == "S" + str(version_order[k] + 1) for b in selected)],
        "inventory": {"source_passages": len(originals), "source_versions": len(version_order), "scanned_code_points": points,
            "nonblank_physical_lines": count, "proposed_bundles": sequence, "selected_bundles": len(selected),
            "selected_evidence_passages": len(used_ids), "copied_text_utf8_bytes": used_bytes},
        "measurement": measured, "limitations": ["unmatched_fallback_not_relevance", "unlinked_context_remains_unknown",
            "source_diversity_not_adverse_authority_recall", "offline_only_not_native_or_legal_qualification"],
        "admission": {"state": "prepared_only" if measured["within_budget"] else "blocked_envelope",
                      "not_execution_authorization": True}}
    value["plan_sha256"] = sha(canonical(value))
    return value


def resolve_diverse(ids, plan, question, originals, *, context_limit=8192):
    rebuilt = plan_diverse(question, originals, context_limit=context_limit)
    if canonical(plan) != canonical(rebuilt) or not rebuilt["measurement"]["within_budget"]:
        raise ValueError("Stale, modified or over-budget diverse bundle plan")
    available = {b["id"]: b for b in rebuilt["bundles"]}
    if (not isinstance(ids, list) or len(ids) > MAX_BUNDLES or any(not isinstance(i, str) or i not in available for i in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("Unverified diverse bundle selection")
    return json.loads(canonical([{k: available[i][k] for k in
        ("id", "source_version", "nomination", "parts", "boundary_flags", "fallback", "partial_source")} for i in ids]))
