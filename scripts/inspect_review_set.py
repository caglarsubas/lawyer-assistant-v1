#!/usr/bin/env python3
"""Inspect an exact reviewed source set locally; never prepare or publish a release."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.qualification import parse_component  # noqa: E402
from app.qualification_evidence import read_exact_directory  # noqa: E402
from app.release_snapshot_set import SnapshotSetRequest  # noqa: E402

MAX_REQUEST_BYTES = 64 * 1024


def read_request(directory):
    return read_exact_directory(directory, {"sources.json": MAX_REQUEST_BYTES}, MAX_REQUEST_BYTES)["sources.json"]


def inspect_set(directory, operator_id):
    # Validate the bounded input before loading deployment configuration. Schema
    # inspection never imports the settings loader or opens application storage.
    original = read_request(directory)
    request = SnapshotSetRequest.model_validate(parse_component(original))
    from app.config import load_settings
    from app.public_sources import PublicSourceStore
    from app.release_snapshot import readonly_store
    from app.release_snapshot_set import locked_snapshot_set

    settings = load_settings()
    with readonly_store(settings) as store:
        with locked_snapshot_set(store, PublicSourceStore(settings.public_source_dir),
                                 operator_id=operator_id, request=request) as snapshot:
            # Only counts and a digest may leave the inspection. The digest and
            # source selection remain firm-confidential, even for public sources.
            summary = dict(snapshot["summary"])
            if read_request(directory) != original:
                raise ValueError("Request changed during inspection")
    # All source and account revalidation on context exit must succeed before a
    # caller receives even a summary. No partial output or packet is persisted.
    return summary


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("Invalid command arguments")


def main(argv=None):
    try:
        parser = Parser(description=__doc__)
        commands = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
        commands.add_parser("schema", help="Print the request schema without loading deployment settings")
        inspect = commands.add_parser("inspect", help="Check existing reviews and print a confidential summary")
        inspect.add_argument("--request-dir", type=Path, required=True)
        inspect.add_argument("--operator-id", required=True)
        args = parser.parse_args(argv)
        result = (SnapshotSetRequest.model_json_schema() if args.command == "schema"
                  else inspect_set(args.request_dir, args.operator_id))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except (Exception, KeyboardInterrupt):
        # Input, storage and traceback details can include private reviews or
        # credentials. Emit the same fixed diagnostic for every inspection failure.
        print(json.dumps({"error": "review_source_set_inspection_failed", "publication_eligible": False}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
