#!/usr/bin/env python3
"""Inspect bounded offline source-linked reference cases, never authorize ingestion."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.reference_cases import Casebook, Passages, Reference, inspect_casebook  # noqa: E402


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('Invalid reference-case arguments')


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=Path)
    parser.add_argument('--artifacts-dir', type=Path)
    parser.add_argument('--source-catalog-dir', type=Path)
    parser.add_argument('--schemas', action='store_true')
    try:
        args = parser.parse_args(argv)
        if args.schemas:
            if args.directory or args.artifacts_dir or args.source_catalog_dir:
                raise ValueError('Schemas accept no files')
            report = {'schema_version': 'legal-reference-case-schemas-v1', 'runtime_authorization': 'none',
                      'production_qualified': False, 'casebook': Casebook.model_json_schema(),
                      'reference': Reference.model_json_schema(), 'passages': Passages.model_json_schema()}
        else:
            if args.directory is None or args.artifacts_dir is None or args.source_catalog_dir is None:
                raise ValueError('All reference-case directories are required')
            report = inspect_casebook(args.directory, args.artifacts_dir, args.source_catalog_dir)
        output = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
    except (ValueError, OSError, TypeError, AttributeError, RecursionError, OverflowError):
        print('Invalid reference-case input; no partial report or authorization.', file=sys.stderr)
        return 2
    print(output)
    return 0 if args.schemas or report['intake_checks_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
