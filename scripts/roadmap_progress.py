"""Count scoped roadmap transitions without treating delivery as acceptance."""

GROUPS = {"done": "done", "in_progress": "open", "planned": "open", "waiting": "blocked_waiting", "deferred": "deferred"}


def inventory(items):
    result = {}
    for item in items:
        ident, status = item["id"], item["status"]
        if not isinstance(ident, str) or not ident or ident in result or status not in GROUPS:
            raise ValueError("Unique roadmap IDs and declared statuses required")
        result[ident] = status
    return result


def distribution(items):
    values = inventory(items)
    counts = dict.fromkeys(GROUPS.values(), 0)
    for status in values.values():
        counts[GROUPS[status]] += 1
    return {"total": len(values), "counts": counts}


def compare(before, after):
    old, new = inventory(before), inventory(after)
    a, b = distribution(before), distribution(after)
    return {"before": a, "after": b, "delta": {k: b["counts"][k] - a["counts"][k] for k in a["counts"]},
            "added": sorted(new.keys() - old.keys()), "removed": sorted(old.keys() - new.keys()),
            "changed": [{"id": k, "before": old[k], "after": new[k]} for k in sorted(old.keys() & new.keys()) if old[k] != new[k]]}


def project(history, items, source, receipt):
    current = [{"id": key, "status": status} for key, status in sorted(inventory(items).items())]
    rows = list(history)
    if len(rows) > 512 or len({r["source_commit"] for r in rows}) != len(rows):
        raise ValueError("Bounded distinct verified progress snapshots required")
    for row in rows:
        inventory(row["items"])
    verified = bool(receipt and not receipt.get("stale") and receipt.get("source_commit") == source
                    and receipt.get("pr", {}).get("merge_commit") == source
                    and receipt.get("pr_ci", {}).get("conclusion") == "success")
    if verified and (not rows or rows[-1]["source_commit"] != source):
        if any(r["source_commit"] == source for r in rows) or len(rows) == 512:
            raise ValueError("Do not rewind or discard progress history")
        rows.append({"source_commit": source, "pr": receipt["pr"]["number"], "items": current})
    if rows and rows[-1]["source_commit"] == source:
        if rows[-1]["items"] != current:
            raise ValueError("Status changes need a new verified source or explicit reconciliation")
        baseline = rows[-2] if len(rows) > 1 else rows[-1]
    else:
        baseline = rows[-1] if rows else {"source_commit": None, "pr": None, "items": current}
    result = {**compare(baseline["items"], current), "baseline_source": baseline["source_commit"], "baseline_pr": baseline["pr"],
              "current_source": source, "current_pr": receipt["pr"]["number"] if verified else None,
              "current_merge_verified": verified, "history_entries": len(rows)}
    return result, rows
