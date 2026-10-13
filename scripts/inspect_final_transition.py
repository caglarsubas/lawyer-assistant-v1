#!/usr/bin/env python3
"""Observe an uncertain whole-release transition; never retry, repair or publish."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.final_release_inspection import TransitionExpectation, inspect_transition  # noqa: E402
from app.release_authorization import _packet_tools  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--expectation", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        from app.config import load_settings
        io = _packet_tools()
        request = TransitionExpectation.model_validate(io.parse_json(io.read_file(args.expectation, 64 * 1024)))
        print(json.dumps(inspect_transition(load_settings(), request), sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"error": "whole_release_observation_unavailable", "retry_authorized": False,
                          "repair_performed": False, "activation_performed": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
