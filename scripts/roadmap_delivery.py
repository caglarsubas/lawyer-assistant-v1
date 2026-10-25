"""Evidence-linked PR delivery records, separate from product readiness."""

import re
from datetime import datetime

from roadmap_progress import distribution

REPOSITORY = "caglarsubas/lawyer-assistant-v1"
BLOCKED_LABELS = {"blocked", "status:blocked"}


def records(rows, ancestors, items):
    if not isinstance(rows, list) or len(rows) > 5000:
        raise ValueError("Bounded repository PR inventory required")
    result, seen = [], set()
    for row in rows:
        number = row["number"]
        if (type(number) is not int or number <= 0 or number in seen or row["state"] not in {"open", "closed"}
                or not isinstance(row["title"], str) or not 0 < len(row["title"]) <= 512
                or any(ord(c) < 32 for c in row["title"])
                or not isinstance(row["labels"], list) or len(row["labels"]) > 100
                or any(not isinstance(label, str) or not 0 < len(label) <= 100 for label in row["labels"])
                or row["html_url"] != f"https://github.com/{REPOSITORY}/pull/{number}"):
            raise ValueError("Distinct repository-bound PR metadata required")
        seen.add(number)
        if row["merged_at"]:
            if (row["state"] != "closed" or not isinstance(row["merged_at"], str)
                    or not re.fullmatch(r"[0-9a-f]{40}", row["merge_commit_sha"] or "")):
                raise ValueError("Merged PR identity required")
            if datetime.fromisoformat(row["merged_at"].replace("Z", "+00:00")).tzinfo is None:
                raise ValueError("Timestamped merge evidence required")
            if row["merge_commit_sha"] not in ancestors:
                continue
            status = "done"
        elif row["state"] == "open":
            status = "waiting" if BLOCKED_LABELS & {label.casefold() for label in row["labels"]} else "in_progress"
        else:
            continue  # Closed without merge is not delivered or an open task.
        mentions = re.compile(r"\bPR\s*#" + str(number) + r"\b", re.I)
        parents = sorted(item["id"] for item in items if mentions.search(item.get("delivered", "")))
        result.append({"id": f"ENG-PR-{number}", "number": number, "title": row["title"], "status": status,
                       "url": row["html_url"], "merged_at": row["merged_at"], "merge_commit": row["merge_commit_sha"] if status == "done" else None,
                       "referenced_items": parents})
    return sorted(result, key=lambda r: r["number"], reverse=True)


def snapshot(rows, source, *, pr=None, observed_at, historical=False):
    values = distribution(rows)
    counts = {key: values["counts"][key] for key in ("done", "open", "blocked_waiting")}
    if historical:
        counts.update(open=None, blocked_waiting=None)
    return {"source_commit": source, "pr": pr, "observed_at": observed_at,
            "scope": "historical_merged_only" if historical else "observed_repository_PRs", "counts": counts,
            "items": sorted(({"id": r["id"], "status": r["status"]} for r in rows), key=lambda r: r["id"])}


def project(history, current, baseline_source, *, verified):
    rows = list(history)
    if len(rows) > 512 or len({r["source_commit"] for r in rows}) != len(rows):
        raise ValueError("Bounded unique delivery snapshots required")
    for row in [*rows, current]:
        expected = distribution(row["items"])["counts"]
        expected = {key: expected[key] for key in ("done", "open", "blocked_waiting")}
        if row["scope"] == "historical_merged_only":
            if any(item["status"] != "done" for item in row["items"]):
                raise ValueError("Historical unmerged states were not observed")
            expected.update(open=None, blocked_waiting=None)
        elif row["scope"] != "observed_repository_PRs":
            raise ValueError("Explicit delivery observation scope required")
        if row["counts"] != expected:
            raise ValueError("Delivery totals must match retained individual records")
    if verified:
        existing = next((r for r in rows if r["source_commit"] == current["source_commit"]), None)
        if existing:
            if existing["counts"] != current["counts"] or existing["items"] != current["items"] or rows[-1] is not existing:
                raise ValueError("Do not rewrite or rewind verified engineering history")
        else:
            if len(rows) == 512:
                raise ValueError("Retained delivery history limit reached")
            rows.append(current)
    baseline = next((r for r in rows if r["source_commit"] == baseline_source), None)
    before = baseline["counts"] if baseline else dict.fromkeys(current["counts"], None)
    delta = {key: current["counts"][key] - value if value is not None and current["counts"][key] is not None else None
             for key, value in before.items()}
    done = {r["id"] for r in current["items"] if r["status"] == "done"}
    previous = {r["id"] for r in baseline["items"] if r["status"] == "done"} if baseline else None
    return {"before": before, "after": current["counts"], "delta": delta,
            "baseline_pr": baseline["pr"] if baseline else None, "baseline_source": baseline_source,
            "current_pr": current["pr"], "current_source": current["source_commit"], "verified": verified,
            "newly_completed": sorted(done - previous) if previous is not None else [],
            "baseline_scope": baseline["scope"] if baseline else "not_recorded"}, rows


def readiness(milestones):
    allowed = {"done": "ready", "partial": "partial", "waiting": "waiting", "planned": "planned"}
    result = dict.fromkeys(allowed.values(), 0)
    ids = set()
    for milestone in milestones:
        if milestone["id"] in ids or milestone["status"] not in allowed:
            raise ValueError("Distinct milestones with declared readiness required")
        ids.add(milestone["id"])
        result[allowed[milestone["status"]]] += 1
    return {"total": len(ids), "counts": result}
