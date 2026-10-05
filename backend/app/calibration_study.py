"""Recompute a bounded offline calibration study without filesystem or provider access.

Artifact hashes bind bytes. Source identities, labels, workload units and timings
remain declarations; exact-byte deduplication cannot establish sample independence.
Only comparison counts are measured here. No result grants source or legal approval.
"""

import hashlib
import math
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .extraction_calibration import (
    CRITICAL_CATEGORIES,
    MAX_ARTIFACT_BYTES,
    MAX_RAW_BYTES,
    CalibrationSample,
    _artifact,
    evaluate_calibration,
)

MAX_STUDY_BYTES = 256 * 1024
MAX_SAMPLE_BYTES = 64 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_SAMPLES = 100
PRACTICES = ("contracts", "commercial", "employment")
LAYOUTS = ("born_digital", "scanned", "mixed", "unknown")
UNITS = ("documents", "pages", "amendment_chains", "decisions")
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
SourceFamilyId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,79}$")]
Count = Annotated[int, Field(ge=0, le=1_000_000)]


class StudyError(ValueError):
    """Closed diagnostics; never interpolate an input identifier, text or path."""


class StrictStudyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, frozen=True)


class StudyEntry(StrictStudyInput):
    sample_sha256: Digest
    raw_sha256: Digest
    extraction_sha256: Digest
    reference_sha256: Digest
    source_identity_sha256: Digest
    sample_kind: Literal["real", "synthetic"]
    practice: Literal["contracts", "commercial", "employment"]
    source_family_id: SourceFamilyId | None
    layout: Literal["born_digital", "scanned", "mixed", "unknown"]
    unit: Literal["documents", "pages", "amendment_chains", "decisions"]
    observed_units: int = Field(ge=1, le=1_000_000)
    reviewer_seconds: float | None = Field(ge=0, le=1_000_000_000)
    assessed_items: Count | None
    disagreements: Count | None

    @model_validator(mode="after")
    def declarations(self):
        if (self.sample_kind == "real") != (self.source_family_id is not None):
            raise ValueError("study_source_family_classification_mismatch")
        if self.disagreements is not None and (
            self.assessed_items is None or self.disagreements > self.assessed_items
        ):
            raise ValueError("study_disagreements_require_denominator")
        return self


class StudyManifest(StrictStudyInput):
    schema_version: Literal["extraction-calibration-study-v1"]
    dossier_sha256: Digest
    recorded_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    entries: list[StudyEntry] = Field(min_length=1, max_length=MAX_SAMPLES)

    @field_validator("recorded_on")
    @classmethod
    def calendar_day(cls, value):
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("invalid_study_day")
        return value

    @model_validator(mode="after")
    def distinct_sources(self):
        for field in ("sample_sha256", "raw_sha256", "source_identity_sha256"):
            values = [getattr(entry, field) for entry in self.entries]
            if len(values) != len(set(values)):
                raise ValueError("duplicate_study_source")
        return self


def _manifest(manifest):
    if not isinstance(manifest, StudyManifest):
        raise StudyError("invalid_study_manifest")
    try:
        return StudyManifest.model_validate(manifest.model_dump(warnings=False))
    except (ValidationError, TypeError, ValueError, AttributeError):
        raise StudyError("invalid_study_manifest") from None


def artifact_specifications(manifest: StudyManifest) -> dict[str, int]:
    """Return the exact flat inventory, with the strictest limit for shared bytes."""
    manifest = _manifest(manifest)
    result = {}
    for entry in manifest.entries:
        for field, limit in (("sample_sha256", MAX_SAMPLE_BYTES), ("raw_sha256", MAX_RAW_BYTES),
                             ("extraction_sha256", MAX_ARTIFACT_BYTES),
                             ("reference_sha256", MAX_ARTIFACT_BYTES)):
            name = f"{getattr(entry, field)}.bin"
            result[name] = min(result.get(name, limit), limit)
    return dict(sorted(result.items()))


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _reported_total(values, *, integer=False):
    if not values or any(value is None for value in values):
        return None
    return sum(values) if integer else math.fsum(values)


def _aggregate(rows):
    comparisons = [row["comparison"] for row in rows]
    count = len(rows)

    def total(field):
        return sum(comparison[field] for comparison in comparisons)

    reference_passages = total("reference_passages")
    exact = total("exact_passage_matches")
    critical = {}
    for category in CRITICAL_CATEGORIES:
        expected = sum(item["critical_categories"][category]["expected"] for item in comparisons)
        matched = sum(item["critical_categories"][category]["matched"] for item in comparisons)
        critical[category] = {"expected": expected, "matched": matched,
                              "match_rate": _ratio(matched, expected)}
    spans, matches = total("critical_spans"), total("critical_span_matches")
    assessed = _reported_total([row["entry"].assessed_items for row in rows], integer=True)
    disagreements = _reported_total([row["entry"].disagreements for row in rows], integer=True)
    return {
        "sample_count": count,
        "passed_sample_count": sum(item["all_declared_checks_passed"] for item in comparisons),
        "failed_sample_count": sum(not item["all_declared_checks_passed"] for item in comparisons),
        "complete_reference_samples": sum(item["reference_coverage"] == "complete" for item in comparisons),
        "partial_reference_samples": sum(item["reference_coverage"] == "partial" for item in comparisons),
        "full_reference_passed_samples": sum(item["full_reference_comparison_passed"] for item in comparisons),
        "empty_reference_samples": sum(item["reference_passages"] == 0 for item in comparisons),
        "empty_extraction_samples": sum(item["extraction_empty"] for item in comparisons),
        "extraction_passages": total("extraction_passages"),
        "reference_passages": reference_passages,
        "exact_passage_matches": exact,
        "exact_passage_match_rate": _ratio(exact, reference_passages),
        "text_matches": total("text_matches"),
        "text_mismatches": total("text_mismatches"),
        "locator_matches": total("locator_matches"),
        "locator_mismatches": total("locator_mismatches"),
        "missing_passages": total("missing_passages"),
        "extra_passages_in_complete_references": sum(item["extra_passages"] for item in comparisons
                                                    if item["extra_passages"] is not None),
        "uncovered_passages": total("uncovered_passages"),
        "critical_spans": spans,
        "critical_span_matches": matches,
        "critical_span_match_rate": _ratio(matches, spans),
        "critical_categories": critical,
        "warning_count": total("warning_count"),
        "samples_with_warnings": sum(item["warning_count"] > 0 for item in comparisons),
        "declared_units": {unit: sum(row["entry"].observed_units for row in rows
                                    if row["entry"].unit == unit) for unit in UNITS},
        "declared_page_count_disagreements": sum(
            row["entry"].unit == "pages" and row["comparison"]["page_count"] is not None
            and row["entry"].observed_units != row["comparison"]["page_count"] for row in rows
        ),
        "reported_extraction_seconds": _reported_total([row["extraction_seconds"] for row in rows]),
        "unreported_extraction_timings": sum(row["extraction_seconds"] is None for row in rows),
        "reported_reviewer_seconds": _reported_total([row["entry"].reviewer_seconds for row in rows]),
        "unreported_reviewer_timings": sum(row["entry"].reviewer_seconds is None for row in rows),
        "reported_assessed_items": assessed,
        "reported_disagreements": disagreements,
        "reported_disagreement_fraction": _ratio(disagreements, assessed)
        if disagreements is not None and assessed is not None else None,
        "unreported_assessment_counts": sum(row["entry"].assessed_items is None for row in rows),
        "unreported_disagreement_counts": sum(row["entry"].disagreements is None for row in rows),
    }


def _cohort(rows):
    practices = {row["entry"].practice for row in rows}
    layouts = {row["entry"].layout for row in rows}
    units = {row["entry"].unit for row in rows}
    formats = sorted({row["source_suffix"] for row in rows})
    return {
        "totals": _aggregate(rows),
        "by_practice": {practice: _aggregate([row for row in rows if row["entry"].practice == practice])
                        for practice in PRACTICES},
        "by_format": {suffix: _aggregate([row for row in rows if row["source_suffix"] == suffix])
                      for suffix in formats},
        "by_layout": {layout: _aggregate([row for row in rows if row["entry"].layout == layout])
                      for layout in LAYOUTS},
        "by_unit": {unit: _aggregate([row for row in rows if row["entry"].unit == unit]) for unit in UNITS},
        "coverage_gaps": {
            "unrepresented_practices": [practice for practice in PRACTICES if practice not in practices],
            "unrepresented_known_layouts": [layout for layout in LAYOUTS if layout != "unknown"
                                            and layout not in layouts],
            "unrepresented_target_units": [unit for unit in UNITS if unit != "documents" and unit not in units],
            "unknown_layout_samples": sum(row["entry"].layout == "unknown" for row in rows),
            "unannotated_critical_categories": [category for category in CRITICAL_CATEGORIES
                                                if not any(row["comparison"]["critical_categories"][category]
                                                           ["expected"] for row in rows)],
            "representativeness_established": False,
        },
    }


def evaluate_study(
    manifest: StudyManifest, artifacts: dict[str, bytes], dossier_report: dict, source_family_ids: set[str],
) -> dict:
    """Recompute comparisons from exact bytes; the caller captures dossier/files safely.

    ``dossier_report`` must come from inspection of the same captured five dossier
    components that produced ``source_family_ids``. This pure function does not
    authenticate that caller or the dossier's declarations.
    """
    manifest = _manifest(manifest)
    if (type(dossier_report) is not dict or dossier_report.get("schema_version") != "r01-inspection-v1"
            or dossier_report.get("structurally_valid") is not True
            or dossier_report.get("dossier_sha256") != manifest.dossier_sha256):
        raise StudyError("study_dossier_binding_mismatch")
    if type(source_family_ids) is not set or any(type(item) is not str for item in source_family_ids):
        raise StudyError("invalid_study_source_catalog")
    specifications = artifact_specifications(manifest)
    if type(artifacts) is not dict or set(artifacts) != set(specifications):
        raise StudyError("invalid_study_artifact_inventory")
    consumed = 0
    for name, limit in specifications.items():
        raw = artifacts[name]
        if type(raw) is not bytes or not 1 <= len(raw) <= limit:
            raise StudyError("invalid_study_artifact_size")
        consumed += len(raw)
        if consumed > MAX_TOTAL_BYTES:
            raise StudyError("study_artifact_budget_exceeded")
        if hashlib.sha256(raw).hexdigest() != name[:-4]:
            raise StudyError("study_artifact_digest_mismatch")

    rows = []
    for entry in sorted(manifest.entries, key=lambda item: item.sample_sha256):
        sample = _artifact(artifacts[f"{entry.sample_sha256}.bin"], CalibrationSample, "sample")
        if any(getattr(entry, field) != getattr(sample, field)
               for field in ("raw_sha256", "extraction_sha256", "reference_sha256", "sample_kind", "practice")):
            raise StudyError("study_sample_declaration_mismatch")
        if sample.recorded_on > manifest.recorded_on:
            raise StudyError("study_sample_postdates_manifest")
        if entry.source_family_id is not None and entry.source_family_id not in source_family_ids:
            raise StudyError("unknown_study_source_family")
        result = evaluate_calibration(sample, artifacts[f"{entry.raw_sha256}.bin"],
                                      artifacts[f"{entry.extraction_sha256}.bin"],
                                      artifacts[f"{entry.reference_sha256}.bin"])
        rows.append({"entry": entry, "source_suffix": sample.source_suffix,
                     "comparison": result["comparison"],
                     "extraction_seconds": result["reported_extraction_elapsed_seconds"]})

    return {
        "schema_version": "extraction-calibration-study-report-v1",
        "dossier_sha256": manifest.dossier_sha256,
        "sample_count": len(rows),
        "artifact_file_count": len(artifacts),
        "artifact_bytes": consumed,
        "all_declared_checks_passed": all(row["comparison"]["all_declared_checks_passed"] for row in rows),
        "all_full_reference_comparisons_passed": all(row["comparison"]["full_reference_comparison_passed"]
                                                      for row in rows),
        "cohorts": {kind: _cohort([row for row in rows if row["entry"].sample_kind == kind])
                    for kind in ("real", "synthetic")},
        "samples": [{"sample_sha256": row["entry"].sample_sha256, "raw_sha256": row["entry"].raw_sha256,
                     "sample_kind": row["entry"].sample_kind, "practice": row["entry"].practice,
                     "source_suffix": row["source_suffix"], "layout": row["entry"].layout,
                     "unit": row["entry"].unit, "declared_observed_units": row["entry"].observed_units,
                     "comparison": row["comparison"]} for row in rows],
        "raw_duplicate_check": "passed",
        "declared_source_identity_check": "passed",
        "source_identity_deduplication": "declared_identity_and_exact_raw_bytes_only",
        "sample_independence": "not_established",
        "source_authenticity_verified": False,
        "reference_independence_authenticated": False,
        "source_faithfulness_established": False,
        "declarations_authenticated": False,
        "timing_measured_by_evaluator": False,
        "review_authenticated": False,
        "source_use_authorized": False,
        "legal_review_granted": False,
        "privacy_evaluated": False,
        "parser_executed": False,
        "authorizes_admission": False,
        "measured_delivery_estimate_weeks": None,
        "population_coverage": None,
        "r01_exit_gate": "independent_review_and_evidence_required",
        "runtime_authorization": "none",
        "production_qualified": False,
        "limitations": [
            "Hashes bind captured bytes, not source authenticity, rights, reference fidelity or legal truth.",
            "Exact raw duplicates and declared identity duplicates are rejected; source independence is not established.",
            "Real and synthetic labels, source families, layouts, workload units and all timings are declarations.",
            "Comparison counts are recomputed; reviewer disagreements are separately declared and are not parser errors.",
            "Partial references score only their annotated passages; unannotated categories retain null rates.",
            "Documents are a separate unit and never count as pages, amendment chains or decisions.",
            "Absent strata are visible gaps, not minimum-size or representativeness decisions.",
            "No result modifies the dossier, corpus, provider state, review ledger or any runtime permission.",
        ],
    }
