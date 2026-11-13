#!/usr/bin/env python3
"""Validate the roadmap audit against a public tracker snapshot and its Git baseline."""

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from graphlib import CycleError, TopologicalSorter
from hashlib import sha256
from pathlib import Path, PurePosixPath

from roadmap_backlog import project as project_backlog
from roadmap_delivery import readiness
from roadmap_progress import distribution, inventory

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs/quality/roadmap-sanity-catalog.json"
ITEM_FIELDS = ("title", "status", "milestone", "dependencies", "source_path")
MILESTONE_FIELDS = ("title", "status", "task_ids", "dependencies", "legal_qualified")
SCOPES = {
    "engineering", "synthetic", "synthetic_navigation", "historical_runtime",
    "partial", "plan", "deferred",
}
COMPLETED_SCOPES = SCOPES - {"partial", "plan", "deferred"}
PHASE_GATE_ITEMS = {
    "F00-04", "F00-06", "R03-07", "R03-08", "R04-05",
    "R05-03", "R05A-04", "R05A-05", "R06-04", "R06-05", "R07-03",
}
RESERVE_FIELDS = ("kind", "name", "cap", "required_margin")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def index(rows):
    indexed = {}
    for row in rows:
        ident = row["id"]
        require(isinstance(ident, str) and re.fullmatch(r"[A-Z0-9-]+", ident), "Invalid roadmap ID")
        require(ident not in indexed, f"Duplicate roadmap ID {ident}")
        indexed[ident] = row
    return indexed


def unique_strings(values):
    return isinstance(values, list) and all(isinstance(value, str) for value in values) and len(values) == len(set(values))


def check_dependencies(rows):
    graph = {}
    for ident, row in rows.items():
        dependencies = row["dependencies"]
        require(unique_strings(dependencies) and set(dependencies) <= rows.keys(), f"Invalid dependency for {ident}")
        graph[ident] = dependencies
    try:
        tuple(TopologicalSorter(graph).static_order())
    except CycleError as error:
        raise ValueError("Roadmap dependency cycle") from error


def tracked_sources(root, commit, pins):
    def git(*args, **kwargs):
        return subprocess.run(
            ["git", "-C", str(root), *args],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True, **kwargs
        ).stdout

    require(re.fullmatch(r"[0-9a-f]{40}", commit), "Expected a full reviewed Git commit")
    paths = set(git("ls-tree", "-r", "--name-only", commit).decode().splitlines())
    require("docs/ROADMAP.md" in pins, "Expected the canonical roadmap source pin")
    for path, digest in pins.items():
        name = PurePosixPath(path)
        allowed_path = path == "README.md" or bool(name.parts and name.parts[0] in {"docs", "qualification", "scripts"})
        require(
            allowed_path and name.as_posix() == path and ".." not in name.parts
            and all(not part.startswith(".") for part in name.parts) and path in paths,
            "Invalid roadmap source pin path",
        )
        require(re.fullmatch(r"[0-9a-f]{64}", digest), "Invalid roadmap source digest")
        require(sha256(git("show", f"{commit}:{path}")).hexdigest() == digest,
                f"Reviewed Git source digest differs for {path}")
    return paths


def validate_catalog(catalog, tracked_paths):
    require(catalog["schema"] == "lawyer-assistant-roadmap-sanity-v1", "Unsupported audit catalog")
    items = index(catalog["items"])
    milestones = index(catalog["milestones"])
    inventory(catalog["items"])
    readiness(catalog["milestones"])
    check_dependencies(items)
    check_dependencies(milestones)
    require(items and milestones, "Expected checklist items and milestones")

    for ident, item in items.items():
        require(item["scope"] in SCOPES and item["remaining_gate"].strip(), f"Incomplete mapping for {ident}")
        require(item["source_path"] in catalog["source_pins"], f"Missing source pin for {ident}")
        for field in ("code", "tests", "evidence"):
            paths = item[field]
            require(unique_strings(paths) and set(paths) <= tracked_paths, f"Invalid {field} links for {ident}")
        if item["status"] == "done":
            require(item["scope"] in COMPLETED_SCOPES and item["code"] and item["tests"],
                    f"Done item {ident} needs scoped code and test evidence")
        if item["status"] == "deferred":
            require(item["milestone"] == "LATER" and item["scope"] == "deferred", f"Invalid deferred scope for {ident}")
        else:
            require(item["milestone"] in milestones, f"Missing milestone for {ident}")

    for ident, milestone in milestones.items():
        expected = {key for key, item in items.items() if item["milestone"] == ident}
        children = milestone["task_ids"]
        require(unique_strings(children) and set(children) == expected and expected,
                f"Checklist coverage differs for milestone {ident}")
        require(type(milestone["legal_qualified"]) is bool and milestone["remaining_gate"].strip(),
                f"Incomplete milestone exit for {ident}")
        if milestone["status"] == "done":
            require(all(items[child]["status"] == "done" for child in children),
                    f"Ready milestone {ident} has unfinished checklist work")

    cross_scope = {
        (ident, dependency)
        for ident, item in items.items() if item["status"] == "done"
        for dependency in item["dependencies"] if items[dependency]["status"] != "done"
    }
    documented = {
        (ident, dependency)
        for ident, dependencies in catalog["engineering_completion_dependencies"].items()
        for dependency, explanation in dependencies.items()
        if isinstance(explanation, str) and explanation.strip()
    }
    require(cross_scope == documented, "Completed items with unfinished prerequisites need a scoped explanation")


def compare_rows(expected, observed, fields, label):
    expected_rows = index(expected)
    observed_rows = index(observed)
    require(expected_rows.keys() == observed_rows.keys(), f"Audit coverage differs for {label}")
    for ident, row in expected_rows.items():
        require(all(row[field] == observed_rows[ident][field] for field in fields), f"Audit drift at {ident}")


def dependency_closure(items, ident):
    pending = list(items[ident]["dependencies"])
    seen = set()
    while pending:
        dependency = pending.pop()
        if dependency not in seen:
            seen.add(dependency)
            pending.extend(items[dependency]["dependencies"])
    return seen


def reserve_profile(rows):
    keys = [tuple(row[field] for field in RESERVE_FIELDS) for row in rows]
    require(len(keys) == len({key[:2] for key in keys}), "Repeated reserve entry")
    return set(keys)


def ci_summary(receipt, run, reserves, expected_reserves):
    ci = receipt[run]
    require(ci["state"] == "completed" and ci["conclusion"] == "success"
            and ci["successful_jobs"] == ci["observed_jobs"] == ci["total_jobs"] > 0,
            f"Incomplete successful run for {run}")
    entries = receipt[reserves]
    require(reserve_profile(entries) == expected_reserves, f"Reserve profile differs for {run}")
    require(all(
        entry["kind"] in {"job", "step"} and type(entry["margin"]) is int
        and 0 <= entry["seconds"] <= entry["cap"] and entry["cap"] - entry["seconds"] == entry["margin"]
        and entry["margin"] >= entry["required_margin"]
        and (entry["required_margin"] == 30 or
             (entry["kind"] == "step" and entry["cap"] == 60 and entry["required_margin"] == 15))
        for entry in entries
    ), f"Inconsistent reserve receipt or declared floor breached for {run}")
    jobs = [entry["margin"] for entry in entries if entry["kind"] == "job"]
    steps = [entry["margin"] for entry in entries if entry["kind"] == "step" and entry["required_margin"] == 30]
    require(len(jobs) == ci["total_jobs"] and steps, f"Incomplete reserve coverage for {run}")
    return {"run": ci["id"], "jobs": len(jobs), "minimum_job_reserve_seconds": min(jobs),
            "minimum_step_reserve_at_30_second_floor": min(steps)}


def audit_snapshot(catalog, snapshot):
    commit = catalog["reviewed_source"]
    require(snapshot["schema"] == "lawyer-assistant-roadmap-snapshot-v1", "Unsupported tracker snapshot")
    require(snapshot["source_commit"] == commit and snapshot["source_clean"] is True,
            "Tracker snapshot does not match the reviewed clean source")
    require(snapshot["source_pins"] == catalog["source_pins"], "Tracker source pins differ from reviewed pins")
    compare_rows(catalog["items"], snapshot["items"], ITEM_FIELDS, "checklist")
    compare_rows(catalog["milestones"], snapshot["milestones"], MILESTONE_FIELDS, "milestones")

    items = snapshot["items"]
    checklist = distribution(items)
    milestones = readiness(snapshot["milestones"])
    require(snapshot["progress"]["after"] == checklist, "Tracker checklist count differs from inventory")
    require(snapshot["backlog"] == project_backlog(items), "Tracker backlog differs from unfinished checklist")
    require(snapshot["readiness"] == milestones, "Tracker milestone readiness differs from inventory")

    records = snapshot["delivery"]["records"]
    delivery = distribution(records)
    counts = {key: value for key, value in delivery["counts"].items() if key != "deferred"}
    require(delivery["counts"]["deferred"] == 0 and counts == snapshot["delivery"]["progress"]["after"],
            "Tracker engineering counts differ from repository PR records")
    known_items = inventory(items)
    require(all(unique_strings(record["referenced_items"]) and set(record["referenced_items"]) <= known_items.keys()
                for record in records), "Invalid engineering PR checklist links")
    completed = [record for record in records if record["status"] == "done"]
    linked = Counter(ident for record in completed for ident in record["referenced_items"])

    receipt = snapshot["receipt"]
    pr = receipt["pr"]
    require(
        receipt["source_commit"] == receipt["remote_main"] == pr["merge_commit"] == commit
        and snapshot["progress"]["current_source"] == commit
        and snapshot["progress"]["current_merge_verified"] is True
        and snapshot["delivery"]["progress"]["current_source"] == commit
        and snapshot["delivery"]["progress"]["verified"] is True
        and any(record["number"] == pr["number"] and record["merge_commit"] == commit for record in completed),
        "CI and delivery receipts must bind the reviewed source and merged PR",
    )
    expected_reserves = reserve_profile(catalog["ci_reserve_profile"])
    ci = {
        "pr": ci_summary(receipt, "pr_ci", "PR_CI_reserves", expected_reserves),
        "main": ci_summary(receipt, "main_ci", "main_CI_reserves", expected_reserves),
    }
    require(ci["pr"]["run"] != ci["main"]["run"], "PR and main need independent CI runs")

    warnings = [
        f"{item} has a scoped engineering completion with unfinished prerequisite {dependency}"
        for item, dependencies in catalog["engineering_completion_dependencies"].items()
        for dependency in dependencies
    ]
    focus = snapshot.get("next_engineering_item_id")
    if focus:
        require(focus in known_items, "Unknown next engineering item")
        if linked[focus] and known_items[focus] != "done":
            warnings.append(f"Engineering focus {focus} has {linked[focus]} linked completed PRs and remains unfinished")
    release_gaps = []
    if "R08-05" in known_items:
        required = dependency_closure(index(items), "R08-05")
        release_gaps = sorted(PHASE_GATE_ITEMS - required)
        if release_gaps:
            warnings.append("Declared release-item dependencies omit phase-gate checks: " + ", ".join(release_gaps))
    if milestones["counts"]["ready"] < milestones["total"]:
        warnings.append(f'{milestones["counts"]["ready"]}/{milestones["total"]} milestones ready')
    return {
        "reviewed_source": commit,
        "checklist": checklist,
        "backlog": snapshot["backlog"]["counts"],
        "milestones": milestones,
        "engineering": {
            "counts": counts,
            "completed_without_explicit_checklist_link": sum(not record["referenced_items"] for record in completed),
            "completed_by_checklist_link": dict(sorted(linked.items())),
        },
        "scopes": dict(sorted(Counter(row["scope"] for row in catalog["items"]).items())),
        "ci": ci,
        "release_dependency_gaps": release_gaps,
        "warnings": warnings,
    }


def read_json(path):
    with path.open("rb") as stream:
        data = stream.read(20_000_001)
    require(len(data) <= 20_000_000, "Roadmap JSON exceeds the supported size")
    return json.loads(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path, help="Local copy of the public tracker snapshot")
    parser.add_argument("--json", action="store_true", help="Print the machine-readable audit summary")
    args = parser.parse_args(argv)
    try:
        catalog = read_json(CATALOG)
        paths = tracked_sources(ROOT, catalog["reviewed_source"], catalog["source_pins"])
        validate_catalog(catalog, paths)
        summary = audit_snapshot(catalog, read_json(args.snapshot))
    except (KeyError, TypeError, OSError, json.JSONDecodeError, UnicodeError, subprocess.CalledProcessError):
        print("Roadmap audit failed. Check the public JSON inputs and reviewed Git commit.", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"Roadmap audit failed. {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Roadmap audit matched {summary['reviewed_source']}")
        for label, key in (("checklist items", "checklist"), ("milestones", "milestones")):
            counts = summary[key]
            states = ", ".join(f"{count} {status.replace('_', ' ')}" for status, count in counts["counts"].items())
            print(f"{counts['total']} {label} ({states})")
        for warning in summary["warnings"]:
            print(warning)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
