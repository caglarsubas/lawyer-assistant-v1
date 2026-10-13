#!/usr/bin/env python3
"""Accept an externally signed complete declared release grant; never sign or publish."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.final_release_authorization import accept  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        from app.config import load_settings
        print(json.dumps(accept(load_settings(), **vars(args)), sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"error": "whole_release_approval_failed", "publication_performed": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
