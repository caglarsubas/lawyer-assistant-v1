#!/usr/bin/env python3
"""Private read-only dependency observation; grants no serving or repair power."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.release_authorization import _packet_tools  # noqa: E402
from app.retained_release_inspection import DependencyExpectation, inspect_dependencies  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--expectation", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        from app.config import load_settings
        io = _packet_tools()
        expectation = DependencyExpectation.model_validate(io.parse_json(io.read_file(args.expectation, 65536)))
        print(json.dumps(inspect_dependencies(load_settings(), expectation), sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"error": "retained_dependency_observation_unavailable", "retry_authorized": False,
            "repair_performed": False, "publication_performed": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
