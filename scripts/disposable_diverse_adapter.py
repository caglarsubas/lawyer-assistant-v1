"""Explicit disposable adapter for frozen v2 plans and versioned D-ID wire JSON.

No app hook, configuration activation, CLI inference or persistence. Native
qualification requires a separate declared trial; mock protocol success is limited.
"""

import json

from disposable_bundle_adapter import selection_ids
from diverse_quote_bundles import RECIPE, SYSTEM_V2, envelope, plan_diverse, resolve_diverse
from offline_quotation_boundaries import sha

from app.evidence_prompt import COMPLETION_RESERVE, FRAMING_RESERVE, canonical
from app.provider import Provider

MARKER = "disposable-diverse-source-selection-v1"
WIRE_RECIPE = "disposable-diverse-D-selector-wire-v1"
OLD_EXAMPLE, NEW_EXAMPLE = '{"bundle_ids":["B1"]}', '{"bundle_ids":["D1"]}'


def prepared_context(question, sources, plan, limit):
    rebuilt = plan_diverse(question, sources, context_limit=limit)
    if canonical(plan) != canonical(rebuilt):
        raise ValueError("Stale or modified diverse selection plan")
    messages, original_measurement = envelope(question, rebuilt["bundles"], limit)
    if (canonical(original_measurement) != canonical(rebuilt["measurement"])
            or messages[0]["content"] != SYSTEM_V2 or SYSTEM_V2.count(OLD_EXAMPLE) != 1):
        raise ValueError("Frozen diverse envelope differs")
    # Explicit new wire recipe: the old planner prompt remains reproducible. No
    # returned ID translation, hidden prompt mutation or byte-budget relaxation.
    messages[0]["content"] = SYSTEM_V2.replace(OLD_EXAMPLE, NEW_EXAMPLE)
    size = sum(len(m["content"].encode()) for m in messages)
    units = size + FRAMING_RESERVE + COMPLETION_RESERVE
    if size != original_measurement["utf8_bytes"] or units != original_measurement["total_upper_bound_units"]:
        raise ValueError("Diverse wire byte budget changed")
    measurement = {**original_measurement, "recipe": WIRE_RECIPE, "messages_sha256": sha(canonical(messages))}
    manifest = {"recipe": MARKER, "planner_recipe": RECIPE, "planner_plan_sha256": rebuilt["plan_sha256"],
        "source_inventory_sha256": rebuilt["source_inventory_sha256"], "question_sha256": rebuilt["question_sha256"],
        "context_limit_units": limit, "planner_messages_sha256": original_measurement["messages_sha256"],
        "measurement": measurement, "bundle_ids": [b["id"] for b in rebuilt["bundles"]],
        "admission": "prepared_only" if measurement["within_budget"] else "blocked_envelope",
        "not_execution_authorization": True}
    manifest["wire_sha256"] = sha(canonical(manifest))
    return manifest, messages


def prepare_diverse_selection(question, sources, plan, *, context_limit=8192):
    """Read-only preview; caller must retain the entire manifest before selection."""
    return prepared_context(question, sources, plan, context_limit)[0]


class DisposableDiverseAdapter:
    def __init__(self, provider, *, mode):
        if mode != MARKER or not isinstance(provider, Provider):
            raise ValueError("Explicit disposable diverse mode required")
        self.provider = provider

    def select(self, question, originals, plan, wire, *, context_limit=8192):
        def unchanged():
            if (canonical(originals) != sealed_sources or canonical(plan) != sealed_plan or canonical(wire) != sealed_wire
                    or type(self.provider.settings.provider_context_limit) is not int
                    or self.provider.settings.provider_context_limit != context_limit):
                raise ValueError("Diverse selection context changed")

        sealed_sources, sealed_plan, sealed_wire = canonical(originals), canonical(plan), canonical(wire)
        sources, frozen = json.loads(sealed_sources), json.loads(sealed_plan)
        expected_wire, messages = prepared_context(question, sources, frozen, context_limit)
        if canonical(expected_wire) != sealed_wire or not expected_wire["measurement"]["within_budget"]:
            raise ValueError("Stale, modified or over-budget diverse wire manifest")
        unchanged()
        if frozen["bundles"]:
            content = self.provider._complete(messages, 1000, expected_wire["measurement"]["total_upper_bound_units"],
                                              response_bytes=8192)
            try:
                ids = selection_ids(content)
            except (ValueError, TypeError, RecursionError, UnicodeError):
                raise ValueError("Invalid diverse bundle selection") from None
            state = "selection_returned" if ids else "empty_selection_unqualified"
        else:
            ids, state = [], "no_candidates_no_call"
        unchanged()
        resolved = resolve_diverse(ids, frozen, question, sources, context_limit=context_limit)
        selected = set(ids)
        selected_versions = {b["source_version"] for b in resolved}
        available_versions = {b["source_version"] for b in frozen["bundles"]}
        return {"recipe": MARKER, "wire_sha256": expected_wire["wire_sha256"], "planner_plan_sha256": frozen["plan_sha256"],
                "source_inventory_sha256": frozen["source_inventory_sha256"], "state": state, "bundles": resolved,
                "selection_coverage": {"selected_bundle_ids": ids,
                    "omitted_nominated_bundle_ids": [b["id"] for b in frozen["bundles"] if b["id"] not in selected],
                    "available_source_versions": sorted(available_versions), "selected_source_versions": sorted(selected_versions),
                    "all_nominated_bundles_selected": len(ids) == len(frozen["bundles"])},
                "model_relevance_abstention_or_legal_qualification": False, "production_activation": False}
