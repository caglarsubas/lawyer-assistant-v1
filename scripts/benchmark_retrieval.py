#!/usr/bin/env python3
"""Score a frozen development benchmark and captured rankings, without services."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_release import SafeParser, capture  # noqa: E402

from app.qualification import MAX_COMPONENT_BYTES, parse_component  # noqa: E402
from app.retrieval_benchmark import RetrievalBenchmark, RetrievalRun, score_run  # noqa: E402


def score_files(benchmark_path, run_path):
    paths = {"benchmark": benchmark_path, "run": run_path}
    raw = {name: capture(path, MAX_COMPONENT_BYTES) for name, path in paths.items()}
    report = score_run(parse_component(raw["benchmark"]), parse_component(raw["run"]))
    if any(capture(path, MAX_COMPONENT_BYTES) != raw[name] for name, path in paths.items()):
        raise ValueError("Benchmark inputs changed")
    report["input_files"] = {name: {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
                             for name, value in raw.items()}
    return report


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("benchmark", type=Path, nargs="?")
    parser.add_argument("--run", type=Path)
    parser.add_argument("--schemas", action="store_true")
    try:
        args = parser.parse_args(argv)
        if args.schemas:
            if args.benchmark or args.run:
                raise ValueError("Schemas take no files")
            report = {"schema_version": "retrieval-development-schemas-v1", "runtime_authorization": "none",
                      "benchmark": RetrievalBenchmark.model_json_schema(), "run": RetrievalRun.model_json_schema()}
        else:
            if args.benchmark is None or args.run is None:
                raise ValueError("Benchmark and run required")
            report = score_files(args.benchmark, args.run)
        output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    except (ValueError, OSError, TypeError, AttributeError, KeyError, RecursionError, OverflowError):
        print("Invalid retrieval benchmark, run or frozen snapshot; no report emitted.", file=sys.stderr)
        return 2
    print(output)
    # Zero means scoring completed, never legal or production qualification.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
