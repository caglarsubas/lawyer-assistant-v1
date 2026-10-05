#!/usr/bin/env python3
"""Inspect an offline R01 dossier, its evidence bytes or an extraction sample.

Exit 0 never grants legal/production/egress approval. Calibration mismatches exit
1; invalid inputs exit 2. No network, .env, database or deployment state is used.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.qualification import (  # noqa: E402
    COMPONENTS,
    MAX_COMPONENT_BYTES,
    contract_schemas,
    inspect_components,
    inspect_dossier,
    parse_component,
)

CALIBRATION_FILES = {
    "sample.json": 64 * 1024,
    "raw.bin": 20 * 1024 * 1024,
    "extraction.json": 9 * 1024 * 1024,
    "reference.json": 9 * 1024 * 1024,
}


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid R01 arguments; use --help.\n")


def inspect_evidence(directory, evidence_directory):
    from app.qualification_evidence import read_exact_directory, verify_research_evidence
    from app.research_qualification import ResearchDossier

    specifications = dict.fromkeys(COMPONENTS, MAX_COMPONENT_BYTES)
    captured = read_exact_directory(directory, specifications, MAX_COMPONENT_BYTES * len(COMPONENTS))
    report = inspect_components(captured)
    dossier = ResearchDossier.model_validate(parse_component(captured["research-dossier.json"]))
    report["research_evidence_integrity"] = verify_research_evidence(dossier, evidence_directory)
    if read_exact_directory(directory, specifications, MAX_COMPONENT_BYTES * len(COMPONENTS)) != captured:
        raise ValueError("Dossier changed during evidence inspection")
    return report


def calibrate(directory):
    from app.extraction_calibration import CalibrationSample, evaluate_calibration
    from app.qualification_evidence import read_exact_directory

    raw = read_exact_directory(directory, CALIBRATION_FILES, 40 * 1024 * 1024)
    sample = CalibrationSample.model_validate(parse_component(raw["sample.json"]))
    report = evaluate_calibration(sample, raw["raw.bin"], raw["extraction.json"], raw["reference.json"])
    report["sample_sha256"] = hashlib.sha256(raw["sample.json"]).hexdigest()
    if read_exact_directory(directory, CALIBRATION_FILES, 40 * 1024 * 1024) != raw:
        raise ValueError("Calibration inputs changed during comparison")
    return report


def calibration_schemas():
    from app.extraction_calibration import CalibrationSample, ReferenceTranscription

    return {
        "schema_version": "extraction-calibration-schemas-v1",
        "runtime_authorization": "none",
        "validation_note": "Python cross-record and physical hash checks are also required.",
        "components": {"sample.json": CalibrationSample.model_json_schema(),
                       "reference.json": ReferenceTranscription.model_json_schema()},
    }


def main(argv=None):
    parser = SafeArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Check five fixed dossier components; report gaps")
    check.add_argument("directory", type=Path)
    commands.add_parser("schemas", help="Print schemas; no filesystem writes")
    evidence = commands.add_parser("evidence", help="Check dossier and exact evidence-file hashes")
    evidence.add_argument("directory", type=Path)
    evidence.add_argument("--evidence-dir", type=Path, required=True)
    comparison = commands.add_parser("calibrate", help="Compare exported extraction with independent reference")
    comparison.add_argument("directory", type=Path)
    commands.add_parser("calibration-schemas", help="Print calibration input schemas")
    args = parser.parse_args(argv)
    try:
        if args.command == "schemas":
            result = contract_schemas()
        elif args.command == "calibration-schemas":
            result = calibration_schemas()
        elif args.command == "evidence":
            result = inspect_evidence(args.directory, args.evidence_dir)
        elif args.command == "calibrate":
            result = calibrate(args.directory)
        else:
            result = inspect_dossier(args.directory)
        output = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    except (ValueError, OSError, RecursionError, OverflowError):
        # Validation/filesystem errors can contain secrets or local paths.
        # Never emit exception details or partially validated records.
        print(json.dumps({"structurally_valid": False, "error": "invalid_r01_dossier",
                          "runtime_authorization": "none", "production_qualified": False}), file=sys.stderr)
        return 2
    print(output)
    if args.command == "calibrate" and not result["comparison"]["all_declared_checks_passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
