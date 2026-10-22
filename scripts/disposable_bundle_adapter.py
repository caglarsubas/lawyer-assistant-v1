"""Explicit disposable bundle adapter; no application hook or CLI execution path.

Provider transport/authentication/model checks stay in Provider._complete. This
module adds only frozen-plan selection, never synthesis or a reviewed answer.
"""

import json

from budgeted_quote_bundles import MAX_BUNDLES, SYSTEM, plan_bundles, resolve_bundles, sha

from app.context_packing import pack_private_context
from app.evidence_prompt import COMPLETION_RESERVE, FRAMING_RESERVE, canonical
from app.provider import Provider

MARKER = "disposable-source-bundle-selection-v1"
MAX_SELECTION_BYTES = 4096


def messages_for_plan(question, originals, plan, limit):
    # Preserve the independently frozen offline recipe. Check both the complete
    # plan and the reconstructed envelope, not just a caller-supplied digest.
    rebuilt = plan_bundles(question, originals, context_limit=limit)
    if canonical(plan) != canonical(rebuilt) or not rebuilt["measurement"]["within_budget"]:
        raise ValueError("Disposable bundle context is stale or over budget")
    evidence = pack_private_context(question, originals, context_limit=limit, candidate_profile=True)["evidence"]
    used = {p["evidence_id"] for b in rebuilt["bundles"] for p in b["parts"]}
    payload = {"question": question, "evidence": [{"id": p["id"], "text": p["text"],
        "partial": p["excerpt_start"] != 0 or p["excerpt_end"] != p["full_passage_length"]}
        for p in evidence if p["id"] in used],
        "bundles": [{"id": b["id"], "parts": [{k: p[k] for k in ("evidence_id", "start", "end", "role")}
            for p in b["parts"]], "boundary_flags": b["boundary_flags"], "fallback": b["fallback"]}
            for b in rebuilt["bundles"]]}
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": canonical(payload)}]
    measured = rebuilt["measurement"]
    size = sum(len(m["content"].encode()) for m in messages)
    if (sha(canonical(messages)) != measured["messages_sha256"] or size != measured["utf8_bytes"]
            or size + FRAMING_RESERVE + COMPLETION_RESERVE != measured["total_upper_bound_units"]):
        raise ValueError("Disposable envelope differs from the frozen recipe")
    return messages


def selection_ids(content):
    def unique_object(pairs):
        value = {}
        for k, v in pairs:
            if k in value:
                raise ValueError("Duplicate selection field")
            value[k] = v
        return value

    if not isinstance(content, str) or len(content.encode()) > MAX_SELECTION_BYTES:
        raise ValueError("Unbounded disposable selection")
    value = json.loads(content, object_pairs_hook=unique_object)
    if (not isinstance(value, dict) or set(value) != {"bundle_ids"}
            or not isinstance(value["bundle_ids"], list) or len(value["bundle_ids"]) > MAX_BUNDLES
            or any(not isinstance(i, str) for i in value["bundle_ids"])
            or len(set(value["bundle_ids"])) != len(value["bundle_ids"])):
        raise ValueError("Invalid disposable selection contract")
    return value["bundle_ids"]


class DisposableBundleAdapter:
    def __init__(self, provider, *, mode):
        if mode != MARKER or not isinstance(provider, Provider):
            raise ValueError("Explicit disposable provider mode required")
        self.provider = provider

    def select(self, question, originals, plan, *, context_limit=8192):
        if self.provider.settings.provider_context_limit != context_limit:
            raise ValueError("Disposable and provider context limits differ")
        sealed_sources, sealed_plan = canonical(originals), canonical(plan)
        sources, frozen = json.loads(sealed_sources), json.loads(sealed_plan)
        messages = messages_for_plan(question, sources, frozen, context_limit)
        if frozen["bundles"]:
            content = self.provider._complete(messages, 1000, frozen["measurement"]["total_upper_bound_units"],
                                              response_bytes=8192)
            ids = selection_ids(content)
            state = "selection_returned" if ids else "empty_selection_unqualified"
        else:
            ids, state = [], "no_candidates_no_call"
        # A source or review-context change while transport was running must not
        # return a seemingly current result. No writes, retries or regeneration.
        if canonical(originals) != sealed_sources or canonical(plan) != sealed_plan:
            raise ValueError("Disposable source context changed during selection")
        bundles = resolve_bundles(ids, frozen, question, sources, context_limit=context_limit)
        return {"recipe": MARKER, "plan_sha256": frozen["plan_sha256"], "state": state,
                "bundles": bundles, "model_relevance_or_legal_qualification": False,
                "production_activation": False}
