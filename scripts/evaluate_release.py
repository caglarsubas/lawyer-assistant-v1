#!/usr/bin/env python3
"""Read an adjudicated JSONL dataset and snapshot JSON; emit aggregate metrics only."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.evaluation import evaluate_release  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", type=Path)
    parser.add_argument("--snapshot", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        rows = [json.loads(line) for line in arguments.tasks.read_text().splitlines() if line.strip()]
        report = evaluate_release(rows, json.loads(arguments.snapshot.read_text()))
    except (ValueError, OSError):
        print("Invalid evaluation input; validate the adjudication schema and snapshot.", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["quantitative_gates_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
