"""Exact private receipt selection followed by fresh, read-only destination checks.

Trusted wiring supplies prebound readers; receipts confer no access or authority.
No route, cache, import, enrollment, file discovery or write is introduced here.
"""

import asyncio
import json
from collections import Counter

import operator_enrollment_evidence as e
import operator_recovery_inventory as inventory

MAX_BYTES = 131072
OBSERVED = {"changed_between_reads", "source_changed", "context_changed", "pending_anchors", "reconciled_metadata"}
ERRORS = {"unavailable", "denied", "conflict", "unverifiable", "partial", "budget_exhausted"}
ROW_FIELDS = {"context_id", "change_id", "expected_context_sha256", "state", "first_read_completed", "observations", "review_validity"}
ENVELOPE = {"schema", "actor_sha256", "metadata_only", "atomic_snapshot", "current_authority_assessed", "counts", "rows", "inventory_sha256"}


def _decode(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        e.reject()
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                e.reject()
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: e.reject())
    except (ValueError, UnicodeError, RecursionError):
        e.reject()


def _selection(request):
    if not isinstance(request, dict) or set(request) != {"context_id", "change_id", "expected_context_sha256"}:
        e.reject()
    for key in request:
        e.token(request[key], 64 if key == "expected_context_sha256" else 32)


def _state(views, request):
    latest = views[-1]
    return ("changed_between_reads" if views[0] != latest else
            "source_changed" if not latest["current_source_matches"] else
            "context_changed" if latest["context_sha256"] != request["expected_context_sha256"] else
            "pending_anchors" if latest["pending"] else "reconciled_metadata")


def _source(raw, expected, request, reader):
    if e.sha(raw) != e.token(expected):
        e.reject()
    value = _decode(raw)
    if (not isinstance(value, dict) or set(value) != ENVELOPE | inventory.FLAGS
            or value["schema"] != "operator-recovery-inventory-v1" or value["metadata_only"] is not True
            or value["atomic_snapshot"] is not False or value["current_authority_assessed"] is not False
            or any(value[k] is not False for k in inventory.FLAGS)):
        e.reject()
    e.token(value["actor_sha256"])
    if (not isinstance(value["rows"], list) or not 1 <= len(value["rows"]) <= inventory.MAX_ITEMS
            or not isinstance(value["counts"], dict)
            or any(type(v) is not int or v < 1 for v in value["counts"].values())
            or value["inventory_sha256"] != e.sha(e.encode({k: v for k, v in value.items() if k != "inventory_sha256"}))):
        e.reject()
    seen, selected = set(), None
    for row in value["rows"]:
        if not isinstance(row, dict) or set(row) != ROW_FIELDS:
            e.reject()
        selection = {k: row[k] for k in request}
        _selection(selection)
        key = (row["context_id"], row["change_id"])
        if (key in seen or row["review_validity"] != "unassessed"
                or type(row["first_read_completed"]) is not bool or not isinstance(row["observations"], list)
                or not isinstance(row["state"], str) or row["state"] not in OBSERVED | ERRORS):
            e.reject()
        seen.add(key)
        views = row["observations"]
        if row["state"] in OBSERVED:
            if len(views) != 2 or row["first_read_completed"] is not True:
                e.reject()
            for index, view in enumerate(views):
                if not isinstance(view, dict) or set(view) != inventory.FIELDS:
                    e.reject()
                scope = e.token(view.get("scope_sha256"))
                if scope != views[0]["scope_sha256"]:
                    e.reject()
                bound = inventory.BoundReader(scope_sha256=scope, authorize=reader.authorize, read=reader.read)
                status = "joint_context_observed" if index == 0 else "joint_finish_reconciled_readonly"
                inventory.observation(e.encode({**view, "status": status, **dict.fromkeys(inventory.FLAGS, False)}),
                                      status, bound, value["actor_sha256"], row["change_id"])
            if row["state"] != _state(views, selection):
                e.reject()
        elif views:
            e.reject()
        if selection == request:
            selected = row
    if (dict(Counter(row["state"] for row in value["rows"])) != value["counts"]
            or selected is None or selected["state"] not in OBSERVED
            or any(v["scope_sha256"] != reader.scope_sha256 for v in selected["observations"])):
        e.reject()
    return value, selected


async def handoff(raw, expected_receipt_sha256, request, contexts, *, actor_sha256):
    """Reconcile one exact selected receipt without transferring source authority.

    Destination scope is independently prebound; actor/context pins are explicit.
    Source and destination observations remain distinct and confidential. At most
    two reads occur, under the existing two-second/20-second cooperative limits.
    Adapters must honor cancellation and preserve authentication/no-store policy.
    """
    _selection(request)
    request = dict(request)
    e.token(actor_sha256)
    e.token(expected_receipt_sha256)
    if not isinstance(contexts, dict) or not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        e.reject()
    result = {"schema": "operator-inventory-handoff-v1", "receipt_sha256": expected_receipt_sha256,
              "selection": dict(request), "state": "unavailable", "metadata_only": True,
              "atomic_snapshot": False, "current_authority_assessed": False, "review_validity": "unassessed",
              "source": None, "destination": None, "comparison": None, **dict.fromkeys(inventory.FLAGS, False)}
    reader = contexts.get(request["context_id"])
    if reader is None:
        return result
    if not isinstance(reader, inventory.BoundReader) or not callable(reader.authorize) or not callable(reader.read):
        e.reject()
    e.token(reader.scope_sha256)
    try:
        source, selected = _source(raw, expected_receipt_sha256, request, reader)
    except (ValueError, TypeError, KeyError, RecursionError):
        e.reject()
    async def authorize():
        async with asyncio.timeout(inventory.READ_SECONDS):
            if await reader.authorize() != actor_sha256:
                raise PermissionError
    try:
        async with asyncio.timeout(inventory.TOTAL_SECONDS):
            await authorize()
            current = await inventory.collect({request["context_id"]: reader}, [dict(request)], actor_sha256=actor_sha256)
            destination = current["rows"][0]
            result["state"] = destination["state"]
            if destination["state"] not in OBSERVED:
                return result
            # Compare both retained reads, without merging or correcting either.
            fields = sorted({key for a, b in zip(selected["observations"], destination["observations"], strict=True)
                             for key in inventory.FIELDS if a[key] != b[key]})
            staged = {"source": {"receipt_sha256": expected_receipt_sha256, "inventory_sha256": source["inventory_sha256"],
                                  "actor_sha256": source["actor_sha256"], "row": selected},
                      "destination": {"inventory_sha256": current["inventory_sha256"], "actor_sha256": actor_sha256,
                                      "scope_sha256": reader.scope_sha256, "row": destination},
                      "comparison": {"outcome": "changed_metadata" if fields else "unchanged_metadata", "changed_fields": fields}}
            await authorize()  # No source or destination body survives failed final authorization.
            result.update(staged)
    except PermissionError:
        result["state"] = "denied"
    except TimeoutError:
        result["state"] = "budget_exhausted"
    except Exception:
        result["state"] = "unavailable"  # Never expose adapter errors; cancellation propagates.
    return result
