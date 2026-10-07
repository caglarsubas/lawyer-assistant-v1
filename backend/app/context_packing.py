"""Bounded, exact-span packing of already-authorized private document passages.

Relevance and document diversity choose review candidates, not legal truth.
Punctuation/line boundaries are heuristics, never proof of complete legal context.
No retrieval, authorization, inference, public graph mutation or source acquisition
occurs here. The caller owns those boundaries.
"""

import hashlib
import re
from bisect import bisect_right
from collections import Counter, defaultdict

from .evidence_prompt import measure_prompt

PACK_RECIPE = "private-evidence-pack-v1"
MAX_CANDIDATES = 2000
MAX_SCANNED_CODE_POINTS = 2_000_000
MAX_PASSAGES = 8
MAX_PASSAGE_BYTES = 1800
TEXT_BYTE_BUDGET = 4000
STOP_WORDS = frozenset({"ve", "ile", "için", "bir", "bu", "ne"})
UNIT_END = re.compile(r"(?<=[.!?])(?=\s|$)|(?<=\n)")
TOKEN = re.compile(r"\S+")
WORD = re.compile(r"\w+")


def _word(value):
    return value.replace("I", "ı").replace("İ", "i").casefold()


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _window(text, anchor, budget):
    """Return one contiguous span; never concatenate or split a whitespace token."""
    if len(text.encode("utf-8")) <= budget:
        return 0, len(text), "full_passage"
    boundaries = [0, *[match.start() for match in UNIT_END.finditer(text)]]
    if boundaries[-1] != len(text):
        boundaries.append(len(text))
    position = min(bisect_right(boundaries, anchor) - 1, len(boundaries) - 2)
    left, right = position, position + 1
    size = len(text[boundaries[left]:boundaries[right]].encode("utf-8"))
    if size <= budget:
        # Preserve neighboring context when it fits, with an explicit deterministic
        # preference for preceding text. Failure on one side does not stop the other.
        while True:
            changed = False
            if left > 0:
                extra = len(text[boundaries[left - 1]:boundaries[left]].encode("utf-8"))
                if size + extra <= budget:
                    left -= 1
                    size += extra
                    changed = True
            if right < len(boundaries) - 1:
                extra = len(text[boundaries[right]:boundaries[right + 1]].encode("utf-8"))
                if size + extra <= budget:
                    right += 1
                    size += extra
                    changed = True
            if not changed:
                break
        return boundaries[left], boundaries[right], "punctuation_line_window"
    # A long sentence/line must be labeled as a fragment. Move past a partial
    # initial token and retain complete whitespace-delimited tokens at the end.
    prefix = text[max(0, anchor - 150):anchor].encode("utf-8")
    prefix = prefix[-(budget // 3):].decode("utf-8", errors="ignore") if budget >= 3 else ""
    start = anchor - len(prefix)
    if start and not text[start - 1].isspace():
        match = re.search(r"\s", text[start:anchor + 1])
        if match is None:
            start = anchor
            while start and not text[start - 1].isspace():
                start -= 1
        else:
            start += match.end()
    match = TOKEN.search(text, start)
    if match is None:
        return None
    start = match.start()
    fragment = text[start:start + budget].encode("utf-8")[:budget].decode("utf-8", errors="ignore")
    end = start + len(fragment)
    if end < len(text) and not text[end].isspace() and not text[end - 1].isspace():
        matches = list(TOKEN.finditer(fragment))
        end = start + matches[-1].start() if matches else start
    if end <= start or not text[start:end].strip() or not start <= anchor < end:
        return None
    return start, end, "token_fragment"


def pack_private_context(question, passages, *, context_limit=None, text_byte_budget=TEXT_BYTE_BUDGET):
    if (not isinstance(passages, list) or type(text_byte_budget) is not int
            or not 0 <= text_byte_budget <= TEXT_BYTE_BUDGET
            or (context_limit is not None and (type(context_limit) is not int or context_limit <= 0))):
        raise ValueError("Invalid evidence packing limits")
    base_prompt = measure_prompt(question, [])
    query = {_word(match.group()) for match in WORD.finditer(question)} - STOP_WORDS
    buckets, identities = defaultdict(list), set()
    scanned, scanned_points = 0, 0
    for ordinal, passage in enumerate(passages[:MAX_CANDIDATES]):
        if not isinstance(passage, dict):
            raise ValueError("Invalid private passage")
        identity, text = passage.get("id"), passage.get("text")
        if (not isinstance(identity, str) or not 1 <= len(identity) <= 128
                or not isinstance(text, str) or identity in identities):
            raise ValueError("Invalid or ambiguous private passage identity")
        if scanned_points + len(text) > MAX_SCANNED_CODE_POINTS:
            break  # No partial scanning silently replaces a complete original.
        text.encode("utf-8")  # Malformed Unicode cannot reach the model or a saved manifest.
        identities.add(identity)
        scanned += 1
        scanned_points += len(text)
        matches, anchor = set(), None
        for match in WORD.finditer(text):
            word = _word(match.group())
            if word in query:
                matches.add(word)
                if anchor is None:
                    anchor = match.start()
        document = passage.get("document_id", identity)
        if not isinstance(document, str) or not 1 <= len(document) <= 128:
            raise ValueError("Invalid private document identity")
        first_token = TOKEN.search(text)
        if anchor is None:
            anchor = first_token.start() if first_token else 0
        candidate = (len(matches), ordinal, anchor, passage)
        buckets[document].append(candidate)
    # Equal scores preserve input order. First visit each document's best candidate;
    # subsequent rounds visit its next candidate. This is diversity, not adverse-law
    # discovery or an assertion that every document received model attention.
    for bucket in buckets.values():
        bucket.sort(key=lambda item: (-item[0], item[1]))
    documents = sorted(buckets, key=lambda identity: (-buckets[identity][0][0], buckets[identity][0][1]))
    selected, selection_records, omissions = [], [], []
    reasons = Counter()
    used = 0
    base_fits = context_limit is None or base_prompt["total_upper_bound_units"] <= context_limit
    for depth in range(max((len(bucket) for bucket in buckets.values()), default=0)):
        for document in documents:
            if depth >= len(buckets[document]):
                continue
            score, _, anchor, original = buckets[document][depth]
            text = original["text"]
            reason = None
            if not text.strip():
                reason = "empty_text"
            elif not base_fits:
                reason = "question_exceeds_context"
            elif len(selected) >= MAX_PASSAGES:
                reason = "passage_limit"
            elif used >= text_byte_budget:
                reason = "text_budget"
            else:
                budget = min(MAX_PASSAGE_BYTES, text_byte_budget - used)
                while budget > 0:
                    span = _window(text, anchor, budget)
                    if span is None:
                        reason = reason or "no_complete_token"
                        break
                    start, end, boundary = span
                    excerpt = {**original, "text": text[start:end], "excerpt_start": start,
                               "excerpt_end": end, "full_passage_length": len(text)}
                    measured = measure_prompt(question, selected + [excerpt])
                    excess = 0 if context_limit is None else measured["total_upper_bound_units"] - context_limit
                    if excess <= 0:
                        selected.append(excerpt)
                        size = len(excerpt["text"].encode("utf-8"))
                        used += size
                        selection_records.append({
                            "passage_id": original["id"], "document_id": document,
                            "document_name": original.get("document_name"),
                            "document_revision": original.get("document_revision"),
                            "document_sha256": original.get("document_sha256"),
                            "original_text_sha256": _digest(text),
                            "excerpt_text_sha256": _digest(excerpt["text"]),
                            "excerpt_start": start, "excerpt_end": end,
                            "full_passage_length": len(text), "boundary": boundary,
                            "utf8_bytes": size, "matched_query_terms": score,
                        })
                        break
                    reason = "prompt_budget"
                    # JSON escaping and identity overhead are included in excess;
                    # reduce by at least that amount, then recompute the exact envelope.
                    budget = min(budget - 1, len(excerpt["text"].encode("utf-8")) - excess)
                else:
                    reason = "prompt_budget"
                if selected and selected[-1]["id"] == original["id"]:
                    reason = None
            if reason:
                reasons[reason] += 1
                omissions.append({"passage_id": original["id"], "document_id": document, "reason": reason})
    unexamined = len(passages) - scanned
    if unexamined:
        reasons["scan_budget"] = unexamined
    return {"evidence": selected, "manifest": {
        "recipe": PACK_RECIPE, "scope": "private_document_quotes",
        "offset_unit": "unicode_code_points",
        "limits": {
            "max_candidates": MAX_CANDIDATES, "max_scanned_code_points": MAX_SCANNED_CODE_POINTS,
            "max_passages": MAX_PASSAGES, "max_passage_utf8_bytes": MAX_PASSAGE_BYTES,
            "max_evidence_utf8_bytes": text_byte_budget, "context_limit_units": context_limit,
        },
        "inventory": {
            "input_passages": len(passages), "examined_passages": scanned, "unexamined_passages": unexamined,
            "selected_passages": len(selected), "omitted_passages": len(passages) - len(selected),
            "shortened_passages": sum(item["boundary"] != "full_passage" for item in selection_records),
            "selected_documents": len({item["document_id"] for item in selection_records}),
            "examined_documents": len(documents), "scanned_code_points": scanned_points,
            "evidence_utf8_bytes": used,
        },
        "selected": selection_records, "omitted": omissions, "omission_counts": dict(sorted(reasons.items())),
        "prompt": measure_prompt(question, selected), "provider_use": "prepared_only",
    }}


def context_export_lines(manifest):
    """A compact human-readable record; old work remains valid without this field."""
    inventory = manifest["inventory"]
    uses = {
        "validated_quote_response": "Model yanıtı seçilmiş alıntılarla karşılaştırıldı.",
        "not_configured": "Model yapılandırılmadı; model çağrısı yapılmadı.",
        "no_selected_evidence": "Uygun belge bağlamı seçilemedi; model çağrısı yapılmadı.",
        "prepared_only": "Yalnızca bağlam hazırlandı; model kullanımı doğrulanmadı.",
    }
    reasons = {
        "empty_text": "Boş metin", "question_exceeds_context": "Soru model bağlam sınırını aşıyor",
        "passage_limit": "Pasaj sayısı sınırı", "text_budget": "Toplam metin sınırı",
        "prompt_budget": "Model bağlam sınırı", "no_complete_token": "Tam metin parçası seçilemedi",
        "scan_budget": "Tarama sınırı nedeniyle incelenmedi",
    }
    boundaries = {"full_passage": "Tam pasaj", "punctuation_line_window": "Kısmi pasaj",
                  "token_fragment": "Cümle veya satır parçası"}
    lines = [
        "Belge bağlamı ve seçim sınırları",
        f"Seçilen pasaj: {inventory['selected_passages']}/{inventory['input_passages']}; "
        f"kısaltılan: {inventory['shortened_passages']}; dışarıda kalan: {inventory['omitted_passages']}.",
        "Bu seçim tam dosya incelemesi veya hukuki uygulanabilirlik kanıtı değildir.",
        uses[manifest["provider_use"]],
        f"Seçim sürümü: {manifest['recipe']}.",
        "Seçilen özel belge metni kamu kaynaklarından ayrı tutuldu; kamu adayları bu model bağlamına alınmadı.",
        "Dışarıda kalma nedenleri: " + (
            "; ".join(f"{reasons[key]}: {count}" for key, count in manifest["omission_counts"].items())
            or "Bildirilen neden yok."),
        "Hazırlanan mesajların SHA-256 özeti: " + manifest["prompt"]["messages_sha256"],
    ]
    for item in manifest["selected"]:
        lines.append(
            f"Bağlam pasajı: {item['passage_id']}; Unicode aralığı "
            f"[{item['excerpt_start']}, {item['excerpt_end']}) / {item['full_passage_length']}; "
            f"pencere: {boundaries[item['boundary']]}; alıntı SHA-256: {item['excerpt_text_sha256']}."
        )
    return lines
