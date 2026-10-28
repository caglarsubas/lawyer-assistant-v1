"""Bounded private metadata reads over explicitly selected, prebound contexts.

The registry and callbacks are trusted operator wiring, never request fields.
Callbacks retain existing session authentication and call only the two named
read operations. This module adds no route, enrollment, repair or authority.
"""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import operator_enrollment_evidence as e

MAX_ITEMS, READ_SECONDS, TOTAL_SECONDS = 8, 2, 20
FLAGS = e.FLAGS | {"authority_renewed", "atomic_joint_write"}
DIGESTS = {
    "window_head_sha256", "window_tip_sha256", "destination_head_sha256", "destination_tip_sha256",
    "namespace_head_sha256", "legacy_head_sha256", "revocation_head_sha256", "context_sha256",
    "history_sha256", "scope_sha256", "actor_sha256", "finish_sha256", "plan_sha256", "view_sha256",
}
PLAN = {
    "change_id", "window_tip_sha256", "destination_tip_sha256", "namespace_head_sha256",
    "legacy_head_sha256", "revocation_head_sha256", "context_sha256", "history_sha256",
    "scope_sha256", "actor_sha256", "finish_sha256",
}
FIELDS = DIGESTS | {
    "target", "change_id", "phase", "finish_state", "pending", "current_source_matches", "next_target", "progress",
}


@dataclass(frozen=True, kw_only=True)
class BoundReader:
    scope_sha256: str
    authorize: Callable[[], Awaitable[str]]
    read: Callable[[str, dict], Awaitable[tuple[int, bytes]]]


def observation(raw, status, reader, actor, change):
    value = e.decode(raw)
    if (not isinstance(value, dict) or set(value) != FIELDS | FLAGS | {"status"}
            or value["status"] != status or any(value[k] is not False for k in FLAGS)):
        raise ValueError("Closed read-only metadata required")
    for key in DIGESTS:
        e.token(value[key])
    if (value["change_id"] != change or value["actor_sha256"] != actor
            or value["scope_sha256"] != reader.scope_sha256 or value["target"] != "window"
            or value["phase"] != "finished" or type(value["current_source_matches"]) is not bool
            or not isinstance(value["pending"], dict) or not set(value["pending"]) <= {"window", "destination"}):
        raise ValueError("Exact authorized metadata binding required")
    pending = value["pending"]
    for name, row in pending.items():
        if (not isinstance(row, dict) or set(row) != {"kind", "event_sha256"}
                or row["kind"] not in ({"finished"} if name == "window" else {"selected", "retired"})):
            raise ValueError("Closed pending-anchor evidence required")
        e.token(row["event_sha256"])
    for name in ("window", "destination"):
        if (value[name + "_head_sha256"] != value[name + "_tip_sha256"]) != (name in pending):
            raise ValueError("Exact pending-anchor heads required")
    next_target = "destination" if "destination" in pending else "window" if "window" in pending else None
    progress = "destination_pending" if "destination" in pending else "window_pending" if pending else "reconciled"
    if (value["next_target"] != next_target or value["progress"] != progress
            or value["finish_state"] != ("pending_anchor" if "window" in pending else "anchored")):
        raise ValueError("Consistent metadata progress required")
    view = {k: value[k] for k in FIELDS}
    plan = {"schema": "joint-recovery-plan-v1", **{k: view[k] for k in PLAN}}
    if (e.sha(e.encode(plan)) != view["plan_sha256"]
            or e.sha(e.encode({k: v for k, v in view.items() if k != "view_sha256"})) != view["view_sha256"]):
        raise ValueError("Exact plan and view evidence required")
    return view


async def _authorize(reader, actor, seconds):
    async with asyncio.timeout(seconds):
        if await reader.authorize() != actor:
            raise PermissionError("Actor changed")


async def _item(reader, request, actor, deadline):
    row = {"context_id": request["context_id"], "change_id": request["change_id"],
           "expected_context_sha256": request["expected_context_sha256"], "state": "unavailable",
           "first_read_completed": False, "observations": [], "review_validity": "unassessed"}
    if reader is None:
        return row
    observed = []
    try:
        for action in ("joint_observe", "joint_finish_observe"):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                row["state"] = "budget_exhausted"
                return row
            async with asyncio.timeout(min(READ_SECONDS, remaining)):
                await _authorize(reader, actor, min(READ_SECONDS, remaining))
                pins = {"change_id": request["change_id"]}
                if observed:
                    pins.update({"expected_" + k: observed[0][k] for k in ("plan_sha256", "view_sha256", "finish_sha256")})
                status, raw = await reader.read(action, pins)
                if type(status) is not int or status != 200:
                    row["state"] = "denied" if status in (401, 403) else "conflict" if status == 409 else "unavailable"
                    return row  # Never expose error bodies or cached metadata after failed authorization.
                observed.append(observation(raw, "joint_context_observed" if not observed else
                                            "joint_finish_reconciled_readonly", reader, actor, request["change_id"]))
                row["first_read_completed"] = True
        await _authorize(reader, actor, min(READ_SECONDS, max(0, deadline - asyncio.get_running_loop().time())))
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError
    except PermissionError:
        row["state"] = "denied"
        return row
    except TimeoutError:
        row["state"] = "partial" if observed else "budget_exhausted"
        return row
    except (ValueError, TypeError, KeyError, RecursionError):
        row["state"] = "unverifiable"
        return row
    except Exception:
        return row  # Adapter errors stay private; cancellation propagates.
    row["observations"] = observed
    latest = observed[-1]
    row["state"] = ("changed_between_reads" if observed[0] != latest else
                    "source_changed" if not latest["current_source_matches"] else
                    "context_changed" if latest["context_sha256"] != request["expected_context_sha256"] else
                    "pending_anchors" if latest["pending"] else "reconciled_metadata")
    return row


async def collect(contexts, requests, *, actor_sha256):
    """At most eight selections, sixteen reads and twenty elapsed seconds; no retry.

Each callback must preserve the controller's authentication and no-store policy.
Observations are confidential, time-of-read metadata, never an atomic snapshot
or a verdict on current review validity, authority, readability or legal effect.
"""
    e.token(actor_sha256)
    if not isinstance(contexts, dict) or not isinstance(requests, list) or not 1 <= len(requests) <= MAX_ITEMS:
        raise ValueError("Bounded explicit selections required")
    selected, seen = [], set()
    for request in requests:
        if not isinstance(request, dict) or set(request) != {"context_id", "change_id", "expected_context_sha256"}:
            raise ValueError("Closed explicit selection required")
        e.token(request["context_id"], 32)
        e.token(request["change_id"], 32)
        e.token(request["expected_context_sha256"])
        key = (request["context_id"], request["change_id"])
        if key in seen:
            raise ValueError("Unique selections required")
        seen.add(key)
        reader = contexts.get(request["context_id"])
        if reader is not None:
            if not isinstance(reader, BoundReader) or not callable(reader.read) or not callable(reader.authorize):
                raise ValueError("Prebound reader required")
            e.token(reader.scope_sha256)
        selected.append((reader, dict(request)))
    deadline = asyncio.get_running_loop().time() + TOTAL_SECONDS
    rows = []
    for reader, request in selected:
        if asyncio.get_running_loop().time() >= deadline:
            row = {**request, "state": "budget_exhausted", "first_read_completed": False,
                   "observations": [], "review_validity": "unassessed"}
        else:
            row = await _item(reader, request, actor_sha256, deadline)
        rows.append(row)
    result = {"schema": "operator-recovery-inventory-v1", "actor_sha256": actor_sha256,
              "metadata_only": True, "atomic_snapshot": False, "current_authority_assessed": False,
              "counts": dict(Counter(row["state"] for row in rows)), "rows": rows,
              **dict.fromkeys(FLAGS, False)}
    result["inventory_sha256"] = e.sha(e.encode(result))
    return result
