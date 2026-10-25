"""Read GitHub metadata and verify merge ancestry; never read product data."""

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from roadmap_delivery import REPOSITORY, records


def collect(root):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True, timeout=30).strip()
    rows = []
    for page in range(1, 51):
        raw = subprocess.check_output(["gh", "api", f"repos/{REPOSITORY}/pulls?state=all&sort=created&direction=desc&per_page=100&page={page}"],
                                      text=True, timeout=30)
        values = json.loads(raw)
        if not isinstance(values, list) or len(values) > 100:
            raise ValueError("Bounded PR metadata page required")
        for value in values:
            rows.append({key: value[key] for key in ("number", "title", "html_url", "created_at", "closed_at", "merged_at", "merge_commit_sha", "state")}
                        | {"head_ref": value["head"]["ref"], "labels": [label["name"] for label in value["labels"]]})
        if len(values) < 100:
            break
    else:
        raise ValueError("PR inventory limit reached; do not silently truncate")
    source = git("rev-parse", "HEAD")
    ancestors = git("rev-list", source).splitlines()
    records(rows, set(ancestors), [])
    return {"schema": "roadmap-delivery-receipts-v1", "repository": REPOSITORY, "source_commit": source,
            "observed_at": datetime.now(timezone.utc).isoformat(), "ancestor_commits": ancestors, "records": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    result = collect(args.source_root.resolve())
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"source": result["source_commit"], "repository_PR_records": len(result["records"]), "read_only": True}))
