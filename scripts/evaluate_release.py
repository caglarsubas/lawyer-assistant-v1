#!/usr/bin/env python3
"""Score bounded offline adjudications; emit aggregate metrics, never approval."""

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.evaluation import evaluate_release  # noqa: E402
from app.qualification import parse_component  # noqa: E402
from app.qualification_scoring import (  # noqa: E402
    SNAPSHOT_KEYS,
    AdjudicatedTask,
    Protocol,
    evaluate_qualification,
)

MAX_TASK_BYTES = 64 * 1024 * 1024
MAX_ROWS = 100_000


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("Invalid evaluation arguments")


def capture(path, maximum):
    """Read one pinned regular file with a size cap; reject links and replacement."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 <= before.st_size <= maximum:
            raise ValueError("Invalid evaluation file")
        raw = bytearray()
        while len(raw) < before.st_size:
            chunk = os.read(fd, min(65536, before.st_size - len(raw)))
            if not chunk:
                raise ValueError("Evaluation file changed")
            raw.extend(chunk)
        def identity(value):
            return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if identity(before) != identity(os.fstat(fd)) or identity(before) != identity(os.stat(path, follow_symlinks=False)):
            raise ValueError("Evaluation file changed")
        return bytes(raw)
    finally:
        os.close(fd)


def score_files(tasks_path, snapshot_path, protocol_path=None, *, casebook_dir=None,
                case_artifacts_dir=None, source_catalog_dir=None):
    reference_paths = (casebook_dir, case_artifacts_dir, source_catalog_dir)
    if any(path is not None for path in reference_paths) and (protocol_path is None or any(path is None for path in reference_paths)):
        raise ValueError('Reference cases require all directories and an extended protocol')
    specs = {"tasks": (tasks_path, MAX_TASK_BYTES), "snapshot": (snapshot_path, 2 * 1024 * 1024)}
    if protocol_path is not None:
        specs["protocol"] = protocol_path, 2 * 1024 * 1024
    raw = {name: capture(path, maximum) for name, (path, maximum) in specs.items()}
    rows = []
    for line in raw["tasks"].splitlines():
        if not line.strip():
            continue
        if len(rows) >= MAX_ROWS:
            raise ValueError("Too many evaluation rows")
        rows.append(parse_component(line))
    snapshot = parse_component(raw["snapshot"])
    report = (evaluate_qualification(rows, snapshot, parse_component(raw["protocol"])) if protocol_path is not None
              else evaluate_release(rows, snapshot))
    report['reference_cases'] = {'status': 'not_supplied', 'reference_case_binding_pass': False}
    if casebook_dir is not None:
        from app.reference_cases import inspect_casebook

        reference = inspect_casebook(casebook_dir, case_artifacts_dir, source_catalog_dir, rows)
        if any(reference['input_files'][f'{key}.json']['sha256'] != hashlib.sha256(raw[key]).hexdigest()
               for key in ('snapshot', 'protocol')):
            raise ValueError('Scoring and reference intake use different captured files')
        report['reference_cases'] = reference
        report['gates']['reference_case_binding'] = reference['reference_case_binding_pass']
        report['quantitative_gates_pass'] = report['quantitative_gates_pass'] and reference['reference_case_binding_pass']
    if any(capture(path, maximum) != raw[name] for name, (path, maximum) in specs.items()):
        raise ValueError("Evaluation inputs changed during scoring")
    report["input_files"] = {name: {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
                             for name, value in raw.items()}
    return report


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("tasks", type=Path, nargs="?")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--protocol", type=Path, help="Frozen local or single-provider extended evaluation protocol")
    parser.add_argument('--casebook-dir', type=Path, help='Frozen source-linked reference inventory')
    parser.add_argument('--case-artifacts-dir', type=Path, help='Exact digest-named originals, references and adjudications')
    parser.add_argument('--source-catalog-dir', type=Path, help='Directory containing only the pinned source-catalog.json')
    parser.add_argument("--schemas", action="store_true", help="Print extended input schemas without reading files")
    try:
        arguments = parser.parse_args(argv)
        if arguments.schemas:
            if (arguments.tasks or arguments.snapshot or arguments.protocol or arguments.casebook_dir
                    or arguments.case_artifacts_dir or arguments.source_catalog_dir):
                raise ValueError("Schemas do not take evaluation files")
            report = {"schema_version": "legal-evaluation-schemas-v1", "runtime_authorization": "none",
                      "validation_note": "Python cross-record validation and independent evidence review also required.",
                      "protocol": Protocol.model_json_schema(), "task": AdjudicatedTask.model_json_schema(),
                      "snapshot": {"type": "object", "additionalProperties": False, "required": sorted(SNAPSHOT_KEYS),
                                   "properties": {key: {"type": "string", "minLength": 1, "maxLength": 200}
                                                  for key in sorted(SNAPSHOT_KEYS)}}}
        else:
            if arguments.tasks is None or arguments.snapshot is None:
                raise ValueError("Evaluation paths required")
            report = score_files(arguments.tasks, arguments.snapshot, arguments.protocol,
                                 casebook_dir=arguments.casebook_dir, case_artifacts_dir=arguments.case_artifacts_dir,
                                 source_catalog_dir=arguments.source_catalog_dir)
        output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    except (ValueError, OSError, TypeError, AttributeError, RecursionError, OverflowError):
        print("Invalid evaluation input; validate the adjudication schema, protocol and snapshot.", file=sys.stderr)
        return 2
    print(output)
    return 0 if arguments.schemas or report["quantitative_gates_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
