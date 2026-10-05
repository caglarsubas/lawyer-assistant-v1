"""Read-only, bounded physical capture for an offline calibration study.

Directories have exact inventories; all metadata and bytes are recaptured before
returning a report. Hashes describe captured inputs and never authorize admission.
"""

import hashlib
from pathlib import Path

from .calibration_study import (
    MAX_STUDY_BYTES,
    MAX_TOTAL_BYTES,
    StudyManifest,
    artifact_specifications,
    evaluate_study,
)
from .qualification import inspect_components, parse_component, read_components
from .qualification_catalog import SourceCatalog
from .qualification_evidence import read_exact_directory


def inspect_study(study_directory: Path, dossier_directory: Path, artifacts_directory: Path) -> dict:
    specifications = {"study.json": MAX_STUDY_BYTES}
    declared = read_exact_directory(study_directory, specifications, MAX_STUDY_BYTES)
    manifest = StudyManifest.model_validate(parse_component(declared["study.json"]))
    dossier = read_components(dossier_directory)
    dossier_report = inspect_components(dossier)
    catalog = SourceCatalog.model_validate(parse_component(dossier["source-catalog.json"]))
    inventory = artifact_specifications(manifest)
    artifacts = read_exact_directory(artifacts_directory, inventory, MAX_TOTAL_BYTES)
    report = evaluate_study(manifest, artifacts, dossier_report, {source.id for source in catalog.sources})
    if (read_components(dossier_directory) != dossier
            or read_exact_directory(study_directory, specifications, MAX_STUDY_BYTES) != declared
            or read_exact_directory(artifacts_directory, inventory, MAX_TOTAL_BYTES) != artifacts):
        raise ValueError("calibration_study_capture_changed")
    report["study_sha256"] = hashlib.sha256(declared["study.json"]).hexdigest()
    return report
