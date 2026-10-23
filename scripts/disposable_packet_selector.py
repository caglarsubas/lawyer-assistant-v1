"""Explicit in-memory packet selector, with no CLI, app hook or native approval.

The injected authorizer is a trusted acquisition boundary supplied by an operator,
not an authorization claim inferred from caller hashes. Synthetic tests supply a
mock authorizer. This module does not implement production matter permissions.
"""

import json
from dataclasses import dataclass
from threading import Lock

from disposable_bundle_adapter import selection_ids
from offline_quotation_boundaries import sha
from whole_passage_packets import MAX_PACKETS, TEXT_BYTES, plan_packets, resolve_packet

from app.evidence_prompt import canonical
from app.provider import Provider

MARKER = "disposable-whole-passage-selector-v1"


def profile(limit):
    if type(limit) is not int or not 0 < limit <= 8192:
        raise ValueError("Unevaluated packet context profile")


@dataclass(frozen=True)
class Allowance:
    completion_attempts: int
    context_units: int
    copied_text_bytes: int

    def validate(self, plan):
        amounts = (self.completion_attempts, self.context_units, self.copied_text_bytes)
        if any(type(x) is not int or x < 0 for x in amounts) or any(x > cap for x, cap in zip(amounts, (8, 65536, 32000))):
            raise ValueError("Invalid aggregate packet allowance")
        required = (len(plan["packets"]), plan["aggregate_budget"]["planned_upper_bound_units"],
                    plan["aggregate_budget"]["planned_copied_text_utf8_bytes"])
        if any(n > cap for n, cap in zip(required, amounts)):
            raise ValueError("Entire packet plan exceeds aggregate allowance")


class DisposablePacketSelector:
    """One-shot per-packet reservations; failed attempts are never refunded.

    Caller references are checked for change, but execution uses only a validated
    serialized snapshot. An authorizer must check current matter access and exact
    acquired document versions outside this module, before and after each call.
    Its descriptor contains hashes and limits only; never source text or secrets.
    A Python caller able to replace the authorizer is outside this trust boundary.
    """

    def __init__(self, provider, question, originals, plan, allowance, *, authorize, mode, context_limit=8192):
        profile(context_limit)
        if mode != MARKER or not isinstance(provider, Provider) or not callable(authorize) or type(allowance) is not Allowance:
            raise ValueError("Explicit disposable packet mode and trusted authorizer required")
        self._provider, self._authorize = provider, authorize
        self._originals, self._plan = originals, plan
        self._sources_json, self._plan_json = canonical(originals), canonical(plan)
        self._question, self._limit = question, context_limit
        sources = json.loads(self._sources_json)
        rebuilt = plan_packets(question, sources, context_limit=context_limit, max_packets=plan["limits"]["max_packets"])
        if canonical(rebuilt) != self._plan_json or not rebuilt["empty_envelope_measurement"]["within_budget"]:
            raise ValueError("Stale or blocked packet context")
        allowance.validate(rebuilt)
        self._allowance = allowance
        self._descriptor = canonical({"recipe": MARKER, "question_sha256": sha(question),
            "source_inventory_sha256": rebuilt["source_inventory_sha256"], "plan_sha256": rebuilt["plan_sha256"],
            "context_limit_units": context_limit, "allowance": allowance.__dict__,
            "not_native_or_production_authorization": True})
        self._provider_identity = self._identity()
        self._lock, self._attempts = Lock(), {}
        self._check()

    def _identity(self):
        # Never export this identity: settings may contain a runtime credential.
        s = self._provider.settings
        return tuple(getattr(s, name) for name in ("provider_base_url", "provider_api_key", "provider_model",
            "provider_identity_verified", "provider_cloud_fallback_disabled", "provider_allow_plain_http", "provider_context_limit"))

    def _check(self):
        def unchanged():
            return (canonical(self._originals) == self._sources_json and canonical(self._plan) == self._plan_json
                    and self._identity() == self._provider_identity
                    and type(self._provider.settings.provider_context_limit) is int
                    and self._provider.settings.provider_context_limit == self._limit)
        if not unchanged() or self._authorize(json.loads(self._descriptor)) is not True or not unchanged():
            raise ValueError("Packet evidence context or authorization changed")

    def select(self, packet_id):
        self._check()
        frozen, sources = json.loads(self._plan_json), json.loads(self._sources_json)
        packet = next((p for p in frozen["packets"] if p["id"] == packet_id), None)
        if packet is None:
            raise ValueError("Unknown packet; no completion attempted")
        units, size = packet["measurement"]["total_upper_bound_units"], packet["copied_text_utf8_bytes"]
        if not packet["measurement"]["within_budget"] or units > self._limit or size > TEXT_BYTES:
            raise ValueError("Packet exceeds per-request budget")
        with self._lock:
            if packet_id in self._attempts:
                raise ValueError("Packet already reserved; retries prohibited")
            spent = self._spent()
            if (spent[0] + 1 > self._allowance.completion_attempts or spent[1] + units > self._allowance.context_units
                    or spent[2] + size > self._allowance.copied_text_bytes or len(self._attempts) >= MAX_PACKETS):
                raise ValueError("Aggregate packet allowance exhausted")
            self._attempts[packet_id] = {"state": "reserved", "units": units, "copied_text_bytes": size}
        try:
            self._check()
            content = self._provider._complete(packet["messages"], 1000, units, response_bytes=8192)
            ids = selection_ids(content)
            result = resolve_packet(packet_id, ids, frozen, self._question, sources,
                                    context_limit=self._limit, max_packets=frozen["limits"]["max_packets"])
            self._check()
            result.update(selector_recipe=MARKER, context_sha256=sha(self._descriptor),
                          model_relevance_abstention_or_legal_qualification=False)
        except Exception:
            with self._lock:
                self._attempts[packet_id]["state"] = "failed_consumed"
            raise ValueError("Packet selection failed; reserved allowance remains consumed") from None
        with self._lock:
            self._attempts[packet_id]["state"] = "returned_unqualified"
        return result

    def _spent(self):
        return (len(self._attempts), sum(x["units"] for x in self._attempts.values()),
                sum(x["copied_text_bytes"] for x in self._attempts.values()))

    def receipt(self):
        """Metadata only. Reserved cost is conservative, not observed token usage."""
        with self._lock:
            attempts, units, size = self._spent()
            return {"recipe": MARKER, "context_sha256": sha(self._descriptor),
                "consumed_completion_attempts": attempts, "consumed_upper_bound_units": units,
                "consumed_copied_text_bytes": size, "attempts": json.loads(canonical(self._attempts)),
                "state": "no_candidates_no_call" if not json.loads(self._plan_json)["packets"] else "disposable_only",
                "accounting": "reserved_attempt_cost_not_actual_tokens_or_HTTP_request_count",
                "production_activation": False, "native_or_legal_qualification": False}
