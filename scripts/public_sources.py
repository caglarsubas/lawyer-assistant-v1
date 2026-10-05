#!/usr/bin/env python3
"""Stage public legal source packages entirely offline; never approve, publish or index them."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.public_sources import PublicSourceError, PublicSourceStore  # noqa: E402


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid public source arguments; use --help.\n")


def main(argv=None):
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True,
                        help="Dedicated public staging directory; never a private matter store")
    commands = parser.add_subparsers(dest="operation", required=True)
    importing = commands.add_parser("import")
    for name in ("metadata", "raw", "text", "locators"):
        importing.add_argument(f"--{name}", type=Path, required=True)
    importing.add_argument("--rights-review", type=Path)
    importing.add_argument("--identity-review", type=Path)
    listing = commands.add_parser("list")
    listing.add_argument("--limit", type=int, default=50)
    listing.add_argument("--after")
    detail = commands.add_parser("verify")
    detail.add_argument("identifier")
    args = parser.parse_args(argv)
    try:
        store = PublicSourceStore(args.store)
        if args.operation == "import":
            result = store.import_package(metadata_path=args.metadata, raw_path=args.raw, text_path=args.text,
                                          locators_path=args.locators, rights_review_path=args.rights_review,
                                          identity_review_path=args.identity_review)
        elif args.operation == "list":
            result = store.list_packages(limit=args.limit, after=args.after)
        else:
            result = store.detail(args.identifier)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (PublicSourceError, OSError):
        parser.exit(1, "Public source operation stopped: invalid input, integrity failure or unavailable store.\n")


if __name__ == "__main__":
    main()
