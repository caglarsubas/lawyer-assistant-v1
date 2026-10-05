"""Bounded comparison of exported extraction artifacts against supplied gold.

This module performs no parsing of source documents, filesystem access, network
access or legal review. Hashes bind bytes, not their origin or truth. Passage
ordinals and exact Unicode codepoint offsets deliberately receive no alignment,
normalization or semantic repair. Parsing success never authorizes admission.
"""

import hashlib
import json
import math
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

MAX_RAW_BYTES = 20 * 1024 * 1024
MAX_ARTIFACT_BYTES = 9 * 1024 * 1024
MAX_TEXT_CHARACTERS = 2_000_000
MAX_PASSAGES = 20_000
MAX_CRITICAL_SPANS = 20_000
MAX_JSON_DEPTH = 20
MAX_JSON_NODES = 250_000
CRITICAL_CATEGORIES = ("date", "amount", "identifier", "negation", "exception")
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
DeclaredVersion = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}$")]
SourceSuffix = Literal[
    ".txt", ".md", ".csv", ".docx", ".xlsx", ".pdf", ".png", ".jpg", ".jpeg",
    ".tiff", ".tif", ".bmp", ".webp", ".gif", ".pptx", ".odt", ".ods", ".odp",
    ".html", ".htm", ".eml", ".rtf", ".xls", ".msg", ".doc",
]


class CalibrationError(ValueError):
    """Closed diagnostic code, never source text, identifiers or parse details."""


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


def _safe_text(value: str) -> str:
    if not value.strip() or any(
        (ord(character) < 32 and character not in "\t\n\r")
        or 0xD800 <= ord(character) <= 0xDFFF or ord(character) in (0xFFFE, 0xFFFF)
        for character in value
    ):
        raise ValueError("invalid_text")
    return value


class CalibrationSample(StrictInput):
    schema_version: Literal["extraction-calibration-sample-v1"]
    sample_kind: Literal["real", "synthetic"]
    data_classification: Literal["public_source", "synthetic_fixture"]
    practice: Literal["contracts", "commercial", "employment"]
    recorded_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    source_suffix: SourceSuffix
    raw_sha256: Digest
    extraction_sha256: Digest
    reference_sha256: Digest
    extractor_id: DeclaredVersion
    extractor_version: DeclaredVersion
    extraction_elapsed_seconds: float | None = Field(ge=0, le=86400)

    @field_validator("recorded_on")
    @classmethod
    def calendar_day(cls, value):
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("invalid_recorded_day")
        return value

    @model_validator(mode="after")
    def classification(self):
        expected = "public_source" if self.sample_kind == "real" else "synthetic_fixture"
        if self.data_classification != expected:
            raise ValueError("sample_classification_mismatch")
        return self


class ExtractedPassage(StrictInput):
    locator: str = Field(min_length=1, max_length=400)
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARACTERS)

    _validate_text = field_validator("locator", "text")(_safe_text)


class ExportedExtraction(StrictInput):
    """Standalone mirror of the worker response, without transport imports.

    Exact duplicate (locator, text) pairs are rejected as ambiguous accidental
    duplicate exports. Same text at different locators remains comparable.
    """

    passages: list[ExtractedPassage] = Field(max_length=MAX_PASSAGES)
    warnings: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(max_length=1000)
    page_count: int | None = Field(ge=1, le=500)
    passage_count: int = Field(ge=0, le=MAX_PASSAGES)

    @model_validator(mode="after")
    def bounded_result(self):
        if self.passage_count != len(self.passages):
            raise ValueError("passage_count_mismatch")
        if sum(len(passage.text) for passage in self.passages) > MAX_TEXT_CHARACTERS:
            raise ValueError("extraction_text_limit")
        if sum(len(warning) for warning in self.warnings) > 100000:
            raise ValueError("warnings_text_limit")
        for warning in self.warnings:
            _safe_text(warning)
        if len({(passage.locator, passage.text) for passage in self.passages}) != len(self.passages):
            raise ValueError("duplicate_extraction_passage")
        return self


class CriticalSpan(StrictInput):
    start: int = Field(ge=0, le=MAX_TEXT_CHARACTERS)
    end: int = Field(ge=1, le=MAX_TEXT_CHARACTERS)
    category: Literal["date", "amount", "identifier", "negation", "exception"]

    @model_validator(mode="after")
    def nonempty(self):
        if self.end <= self.start:
            raise ValueError("critical_span_empty")
        return self


class ReferencePassage(ExtractedPassage):
    ordinal: int = Field(ge=0, lt=MAX_PASSAGES)
    critical_spans: list[CriticalSpan] = Field(max_length=MAX_CRITICAL_SPANS)

    @model_validator(mode="after")
    def span_bounds(self):
        if any(span.end > len(self.text) for span in self.critical_spans):
            raise ValueError("critical_span_outside_reference")
        keys = [(span.start, span.end, span.category) for span in self.critical_spans]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate_critical_span")
        return self


class ReferenceTranscription(StrictInput):
    schema_version: Literal["reference-transcription-v1"]
    raw_sha256: Digest
    coverage: Literal["partial", "complete"]
    reference_status: Literal["unreviewed", "operator_supplied"]
    passages: list[ReferencePassage] = Field(max_length=MAX_PASSAGES)

    @model_validator(mode="after")
    def coverage_and_bounds(self):
        ordinals = [passage.ordinal for passage in self.passages]
        if len(ordinals) != len(set(ordinals)):
            raise ValueError("duplicate_reference_ordinal")
        if self.coverage == "complete" and set(ordinals) != set(range(len(ordinals))):
            raise ValueError("complete_reference_requires_contiguous_ordinals")
        if sum(len(passage.text) for passage in self.passages) > MAX_TEXT_CHARACTERS:
            raise ValueError("reference_text_limit")
        if sum(len(passage.critical_spans) for passage in self.passages) > MAX_CRITICAL_SPANS:
            raise ValueError("reference_critical_span_limit")
        if sum(span.end - span.start for passage in self.passages for span in passage.critical_spans) > MAX_TEXT_CHARACTERS:
            raise ValueError("reference_critical_span_work_limit")
        return self


def _unique_pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise CalibrationError("duplicate_json_field")
        result[key] = value
    return result


def _nonfinite(_value):
    raise CalibrationError("nonfinite_json_number")


def _artifact(raw: bytes, model, label: str):
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_ARTIFACT_BYTES:
        raise CalibrationError(f"invalid_{label}_size")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs, parse_constant=_nonfinite)
        pending = [(value, 0)]
        processed = 0
        while pending:
            item, depth = pending.pop()
            processed += 1
            if depth > MAX_JSON_DEPTH:
                raise CalibrationError("json_depth_exceeded")
            if isinstance(item, float) and not math.isfinite(item):
                raise CalibrationError("nonfinite_json_number")
            # Check width before allocating child work items. The byte bound
            # alone permits millions of tiny JSON values in a shallow array.
            if isinstance(item, (dict, list)) and processed + len(pending) + len(item) > MAX_JSON_NODES:
                raise CalibrationError("json_node_budget_exceeded")
            if isinstance(item, dict):
                pending.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list):
                pending.extend((child, depth + 1) for child in item)
        return model.model_validate(value)
    except CalibrationError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise CalibrationError(f"invalid_{label}_artifact") from None


def _rate(matched: int, expected: int) -> float | None:
    return matched / expected if expected else None


def evaluate_calibration(
    sample: CalibrationSample, raw_bytes: bytes, extraction_bytes: bytes, reference_bytes: bytes,
) -> dict:
    """Compare bound artifacts; report only closed labels, counts and digests.

    all_declared_checks_passed covers the selected reference passages. Only a
    nonempty complete reference can set full_reference_comparison_passed, and
    neither flag verifies a source, reference author, law or independence.
    """
    if not isinstance(sample, CalibrationSample):
        raise CalibrationError("invalid_sample_model")
    try:
        sample = CalibrationSample.model_validate(sample.model_dump())
    except ValidationError:
        raise CalibrationError("invalid_sample_model") from None
    if type(raw_bytes) is not bytes or not 1 <= len(raw_bytes) <= MAX_RAW_BYTES:
        raise CalibrationError("invalid_raw_size")
    for label, content in (("raw", raw_bytes), ("extraction", extraction_bytes), ("reference", reference_bytes)):
        if type(content) is not bytes or not 1 <= len(content) <= (MAX_RAW_BYTES if label == "raw" else MAX_ARTIFACT_BYTES):
            raise CalibrationError(f"invalid_{label}_size")
        if hashlib.sha256(content).hexdigest() != getattr(sample, f"{label}_sha256"):
            raise CalibrationError(f"{label}_digest_mismatch")
    extraction = _artifact(extraction_bytes, ExportedExtraction, "extraction")
    reference = _artifact(reference_bytes, ReferenceTranscription, "reference")
    if reference.raw_sha256 != sample.raw_sha256:
        raise CalibrationError("reference_raw_digest_mismatch")

    exact_matches = text_matches = locator_matches = missing = 0
    critical = {category: {"expected": 0, "matched": 0} for category in CRITICAL_CATEGORIES}
    for passage in reference.passages:
        actual = extraction.passages[passage.ordinal] if passage.ordinal < len(extraction.passages) else None
        if actual is None:
            missing += 1
        locator_matches_here = actual is not None and actual.locator == passage.locator
        text_matches_here = actual is not None and actual.text == passage.text
        locator_matches += int(locator_matches_here)
        text_matches += int(text_matches_here)
        exact_matches += int(locator_matches_here and text_matches_here)
        for span in passage.critical_spans:
            critical[span.category]["expected"] += 1
            if locator_matches_here and actual.text[span.start:span.end] == passage.text[span.start:span.end]:
                critical[span.category]["matched"] += 1
    expected = len(reference.passages)
    available = expected - missing
    ordinals = {passage.ordinal for passage in reference.passages}
    uncovered = sum(ordinal not in ordinals for ordinal in range(len(extraction.passages)))
    extra = uncovered if reference.coverage == "complete" else None
    span_count = sum(item["expected"] for item in critical.values())
    span_matches = sum(item["matched"] for item in critical.values())
    selected_passed = bool(
        expected and extraction.passages and exact_matches == expected and span_count == span_matches
        and (extra is None or extra == 0)
    )
    return {
        "schema_version": "extraction-calibration-report-v1",
        "sample_kind": sample.sample_kind,
        "data_classification": sample.data_classification,
        "practice": sample.practice,
        "source_suffix": sample.source_suffix,
        "digests": {"raw_sha256": sample.raw_sha256, "extraction_sha256": sample.extraction_sha256,
                    "reference_sha256": sample.reference_sha256},
        "comparison": {
            "all_declared_checks_passed": selected_passed,
            "full_reference_comparison_passed": selected_passed and reference.coverage == "complete",
            "reference_coverage": reference.coverage,
            "reference_status": reference.reference_status,
            "extraction_empty": not extraction.passages,
            "extraction_passages": len(extraction.passages),
            "reference_passages": expected,
            "exact_passage_matches": exact_matches,
            "exact_passage_match_rate": _rate(exact_matches, expected),
            "text_matches": text_matches,
            "text_mismatches": available - text_matches,
            "locator_matches": locator_matches,
            "locator_mismatches": available - locator_matches,
            "missing_passages": missing,
            "extra_passages": extra,
            "uncovered_passages": uncovered,
            "critical_spans": span_count,
            "critical_span_matches": span_matches,
            "critical_span_match_rate": _rate(span_matches, span_count),
            "critical_categories": {category: {**counts, "match_rate": _rate(counts["matched"], counts["expected"])}
                                    for category, counts in critical.items()},
            "warning_count": len(extraction.warnings),
            "page_count": extraction.page_count,
        },
        "reported_extraction_elapsed_seconds": sample.extraction_elapsed_seconds,
        "timing_measured_by_evaluator": False,
        "source_authenticity_verified": False,
        "extractor_metadata_authenticated": False,
        "source_faithfulness_established": False,
        "source_identity_deduplication": "not_evaluated",
        "sample_independence": "not_established",
        "legal_review_granted": False,
        "privacy_evaluated": False,
        "parser_executed": False,
        "authorizes_admission": False,
        "runtime_authorization": "none",
        "production_qualified": False,
    }
