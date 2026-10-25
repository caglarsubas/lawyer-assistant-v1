"""Metadata-only, read-only snapshots of the bounded disposable catalog."""

import operator_enrollment_evidence as e
from authenticated_operator_review import conflict
from operator_review_journal import reject
from restore_control_log import fold as restore_fold
from restore_key_custody import file_id
from restore_lifecycle_log import fold as lifecycle_fold


def revocation_scope(inner):
    return {**inner.lifecycle.scope, "lifecycle_id": inner.lifecycle.identity, "enrollments": sorted(inner.children),
            "lifecycle_root_sha256": e.sha(e.encode(file_id(inner.lifecycle.root)))}


def descendants(target, parents):
    result = {target}
    for _ in range(8):
        fresh = result | {child for child, parent in parents.items() if parent in result}
        if fresh == result:
            return result
        result = fresh
    reject()


def capture(inner, withdrawn, now):
    with inner.lifecycle.locked() as (_, fence, events, _):
        current, used, requests, retired = lifecycle_fold(events, inner.lifecycle.scope)
        if now < (events[-1]["payload"]["created_at"] if events else inner.lifecycle.scope["created_at"]):
            conflict()
        heads = {e.sha(e.read(inner.lifecycle.root / "metadata.json")), *(event["head"] for event in events)}
        if any(record["lifecycle_head_sha256"] not in heads for record in withdrawn.values()):
            conflict()  # A withdrawn lineage cannot disappear through inner rollback.
        parents = {}
        for state in requests.values():
            proposal = state["proposal"]["payload"]
            if proposal["kind"] == "renewal" and state.get("decision", {}).get("payload", {}).get("decision") == "approve":
                s = proposal["subject"]
                parents[s["candidate_generation"]] = s["previous_generation"]
        effective = set().union(*(descendants(target, parents) for target in withdrawn)) if withdrawn else set()
        rows = []
        for digest, child in sorted(inner.children.items()):
            validity = "integrity_unavailable"
            try:
                enrollment = child.custody.check(0)
                validity = "not_yet_valid" if now < enrollment["created_at"] else "expired" if now >= enrollment["expires_at"] else "current"
            except Exception:
                pass  # Withdrawal must remain possible after key integrity is lost.
            with child.controls.locked() as (_, control, controls, _):
                grants, selections = restore_fold(controls, child.controls.scope)
                rows.append({"enrollment_sha256": digest, "state": "active" if digest == current else "historical" if digest in used else "candidate",
                             "validity": validity, "parent_enrollment_sha256": parents.get(digest), "access_withdrawn": digest in effective,
                             "restore_control_head_sha256": control["head"], "retained_grants": len(grants),
                             "retained_consumptions": sum("consumed" in state for state in grants.values()), "retained_selections": len(selections),
                             "retired_targets": sum(generation == digest for generation, _ in retired)})
        basis = {"catalog_sha256": inner.lifecycle.scope["catalog_sha256"], "lifecycle_head_sha256": fence["head"],
                 "active_enrollment_sha256": current, "rows": rows, "withdrawals": withdrawn}
        return {"basis": basis, "basis_sha256": e.sha(e.encode(basis)), "parents": parents, "effective": effective, "requests": requests}


def subject(snapshot, target):
    e.token(target)
    if target not in {row["enrollment_sha256"] for row in snapshot["basis"]["rows"]} or target in snapshot["effective"]:
        conflict()
    return {"target_enrollment_sha256": target, "basis_sha256": snapshot["basis_sha256"],
            "lifecycle_head_sha256": snapshot["basis"]["lifecycle_head_sha256"],
            "affected_enrollments": sorted(descendants(target, snapshot["parents"]))}


def page(snapshot, head, actor, value):
    if (set(value) != {"snapshot_sha256", "offset", "limit", "cursor"} or type(value["offset"]) is not int or type(value["limit"]) is not int
            or not 1 <= value["limit"] <= 8 or not 0 <= value["offset"] < len(snapshot["basis"]["rows"])):
        reject()
    digest = e.sha(e.encode({"basis_sha256": snapshot["basis_sha256"], "revocation_head_sha256": head}))
    def token(offset):
        return e.sha(e.encode({"snapshot_sha256": digest, "offset": offset, "limit": value["limit"], "actor": actor}))
    if value["offset"] == 0 and value["snapshot_sha256"] is None and value["cursor"] is None:
        pass
    elif value["snapshot_sha256"] != digest or value["cursor"] != token(value["offset"]):
        conflict()
    end = min(value["offset"] + value["limit"], len(snapshot["basis"]["rows"]))
    return {"status": "lifecycle_inventory_observed", "snapshot_sha256": digest, "revocation_head_sha256": head,
            "lifecycle_head_sha256": snapshot["basis"]["lifecycle_head_sha256"], "enrollment_sha256": snapshot["basis"]["active_enrollment_sha256"],
            "catalog_size": len(snapshot["basis"]["rows"]), "rows": snapshot["basis"]["rows"][value["offset"]:end],
            "next_offset": end if end < len(snapshot["basis"]["rows"]) else None,
            "next_cursor": token(end) if end < len(snapshot["basis"]["rows"]) else None, **dict.fromkeys(e.FLAGS, False)}
