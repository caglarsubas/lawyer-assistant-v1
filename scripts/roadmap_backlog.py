"""Actual unfinished checklist scope, independent of the PR delivery inventory."""

from roadmap_progress import distribution


def project(items):
    counts = distribution(items)
    remaining = [item for item in items if item["status"] != "done"]
    return {"total": len(remaining), "catalog_total": counts["total"],
            "counts": {"open": counts["counts"]["open"], "waiting": counts["counts"]["blocked_waiting"],
                       "deferred": counts["counts"]["deferred"]},
            "ids": [item["id"] for item in remaining]}
