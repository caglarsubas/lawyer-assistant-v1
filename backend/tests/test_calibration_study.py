"""Study metrics are recomputed from bounded artifacts, never promoted to approval."""

import copy
import hashlib
import json

import pytest
from pydantic import ValidationError

from app.calibration_study import (
    MAX_SAMPLE_BYTES,
    MAX_SAMPLES,
    StudyError,
    StudyManifest,
    artifact_specifications,
    evaluate_study,
)

DOSSIER_HASH = hashlib.sha256(b"synthetic five-component dossier inventory").hexdigest()
DOSSIER = {"schema_version": "r01-inspection-v1", "structurally_valid": True,
           "dossier_sha256": DOSSIER_HASH}
SOURCE_FAMILIES = {"synthetic-test-catalog-family"}


def _json(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _case(tag, *, kind="synthetic", practice="contracts", count=1, wrong=False,
          coverage="complete", extraction_seconds=None, **entry_updates):
    passages, reference_passages = [], []
    for index in range(count):
        text = f"İcat edilmiş test {tag}/{index}: ödeme yapılmadı."
        start = text.index("yapılmadı")
        locator = f"SECRET_LOCATOR_{tag}_{index}"
        passages.append({"locator": locator, "text": text.replace("yapılmadı", "yapıldıxx") if wrong else text})
        reference_passages.append({"ordinal": index, "locator": locator, "text": text,
                                   "critical_spans": [{"start": start, "end": start + len("yapılmadı"),
                                                       "category": "negation"}]})
    raw = _json({"original": tag, "text": [item["text"] for item in reference_passages]})
    extraction = _json({"passages": passages, "warnings": ["SECRET_WARNING"], "page_count": None,
                        "passage_count": len(passages)})
    reference = _json({"schema_version": "reference-transcription-v1", "raw_sha256": _sha(raw),
                       "coverage": coverage, "reference_status": "unreviewed", "passages": reference_passages})
    sample = _json({"schema_version": "extraction-calibration-sample-v1", "sample_kind": kind,
                    "data_classification": "synthetic_fixture" if kind == "synthetic" else "public_source",
                    "practice": practice, "recorded_on": "2026-10-05", "source_suffix": ".txt",
                    "raw_sha256": _sha(raw), "extraction_sha256": _sha(extraction),
                    "reference_sha256": _sha(reference), "extractor_id": "SECRET_EXTRACTOR",
                    "extractor_version": "SECRET_VERSION", "extraction_elapsed_seconds": extraction_seconds})
    entry = {"sample_sha256": _sha(sample), "raw_sha256": _sha(raw), "extraction_sha256": _sha(extraction),
             "reference_sha256": _sha(reference), "source_identity_sha256": _sha(tag.encode()),
             "sample_kind": kind, "practice": practice,
             "source_family_id": "synthetic-test-catalog-family" if kind == "real" else None,
             "layout": "born_digital", "unit": "documents", "observed_units": 1,
             "reviewer_seconds": None, "assessed_items": None, "disagreements": None}
    entry.update(entry_updates)
    return entry, {f"{_sha(content)}.bin": content for content in (raw, extraction, reference, sample)}


def _study(*cases, **updates):
    data = {"schema_version": "extraction-calibration-study-v1", "dossier_sha256": DOSSIER_HASH,
            "recorded_on": "2026-10-05", "entries": [item[0] for item in cases]}
    data.update(updates)
    artifacts = {}
    for _, values in cases:
        artifacts.update(values)
    return StudyManifest.model_validate(data), artifacts


def _evaluate(*cases, **updates):
    manifest, artifacts = _study(*cases, **updates)
    return evaluate_study(manifest, artifacts, DOSSIER, SOURCE_FAMILIES)


def _replace_artifact(case, role, transform):
    """Change a JSON artifact and truthfully update all enclosing digests."""
    entry, artifacts = case
    old_name = f"{entry[role]}.bin"
    value = json.loads(artifacts.pop(old_name))
    transform(value)
    content = _json(value)
    entry[role] = _sha(content)
    artifacts[f"{entry[role]}.bin"] = content
    if role != "sample_sha256":
        _replace_artifact(case, "sample_sha256", lambda sample: sample.update({role: entry[role]}))
    return case


def test_exact_study_is_reproducible_non_authorizing_and_does_not_modify_inputs():
    manifest, artifacts = _study(_case("A"), _case("B", practice="employment"))
    before = copy.deepcopy((manifest.model_dump(), artifacts, DOSSIER, SOURCE_FAMILIES))
    report = evaluate_study(manifest, artifacts, DOSSIER, SOURCE_FAMILIES)
    assert report == evaluate_study(manifest, artifacts, DOSSIER, SOURCE_FAMILIES)
    assert before == (manifest.model_dump(), artifacts, DOSSIER, SOURCE_FAMILIES)
    assert report["sample_count"] == 2
    assert report["artifact_file_count"] == 8
    assert report["all_declared_checks_passed"] is True
    assert report["all_full_reference_comparisons_passed"] is True
    assert report["raw_duplicate_check"] == report["declared_source_identity_check"] == "passed"
    assert report["sample_independence"] == "not_established"
    assert report["runtime_authorization"] == "none"
    assert report["r01_exit_gate"] == "independent_review_and_evidence_required"
    assert report["measured_delivery_estimate_weeks"] is None
    assert report["population_coverage"] is None
    for key in ("source_authenticity_verified", "reference_independence_authenticated",
                "source_faithfulness_established", "declarations_authenticated", "timing_measured_by_evaluator",
                "review_authenticated", "source_use_authorized", "legal_review_granted", "privacy_evaluated",
                "parser_executed", "authorizes_admission", "production_qualified"):
        assert report[key] is False


def test_input_order_does_not_change_deterministic_report():
    first, second = _case("A", extraction_seconds=1.1), _case("B", extraction_seconds=2.2)
    assert _evaluate(first, second) == _evaluate(second, first)


def test_real_and_synthetic_counts_and_timings_never_mix():
    report = _evaluate(_case("A", kind="real", practice="employment", extraction_seconds=2.0,
                            reviewer_seconds=5.0, unit="pages", observed_units=3),
                       _case("B", extraction_seconds=1.0, reviewer_seconds=2.0))
    real, synthetic = (report["cohorts"][kind]["totals"] for kind in ("real", "synthetic"))
    assert real["sample_count"] == synthetic["sample_count"] == 1
    assert real["declared_units"] == {"documents": 0, "pages": 3, "amendment_chains": 0, "decisions": 0}
    assert synthetic["declared_units"] == {"documents": 1, "pages": 0, "amendment_chains": 0, "decisions": 0}
    assert real["reported_extraction_seconds"] == 2.0
    assert real["reported_reviewer_seconds"] == 5.0
    assert synthetic["reported_extraction_seconds"] == 1.0
    assert synthetic["reported_reviewer_seconds"] == 2.0


def test_missing_cohort_is_explicit_and_has_no_vacuous_rates():
    real = _evaluate(_case("A"))["cohorts"]["real"]
    assert real["totals"]["sample_count"] == 0
    assert real["totals"]["exact_passage_match_rate"] is None
    assert real["totals"]["critical_span_match_rate"] is None
    assert real["totals"]["reported_extraction_seconds"] is None
    assert real["totals"]["reported_reviewer_seconds"] is None
    assert real["coverage_gaps"]["unrepresented_practices"] == ["contracts", "commercial", "employment"]


def test_weighted_counts_do_not_average_sample_percentages():
    report = _evaluate(_case("A", count=1, wrong=True), _case("B", count=3))
    totals = report["cohorts"]["synthetic"]["totals"]
    assert totals["reference_passages"] == totals["critical_spans"] == 4
    assert totals["exact_passage_matches"] == totals["critical_span_matches"] == 3
    assert totals["exact_passage_match_rate"] == totals["critical_span_match_rate"] == 0.75
    assert totals["critical_categories"]["negation"] == {"expected": 4, "matched": 3, "match_rate": 0.75}
    assert totals["critical_categories"]["date"]["match_rate"] is None
    assert totals["passed_sample_count"] == totals["failed_sample_count"] == 1
    assert report["all_declared_checks_passed"] is False


def test_partial_reference_pass_does_not_establish_full_pass():
    case = _case("A", count=2, coverage="partial")
    _replace_artifact(case, "reference_sha256", lambda reference: reference["passages"].pop())
    report = _evaluate(case)
    totals = report["cohorts"]["synthetic"]["totals"]
    assert report["all_declared_checks_passed"] is True
    assert report["all_full_reference_comparisons_passed"] is False
    assert totals["partial_reference_samples"] == totals["uncovered_passages"] == 1
    assert totals["extra_passages_in_complete_references"] == 0


def test_empty_reference_and_empty_extraction_cannot_become_success():
    report = _evaluate(_case("A", count=0))
    totals = report["cohorts"]["synthetic"]["totals"]
    assert report["all_declared_checks_passed"] is False
    assert report["all_full_reference_comparisons_passed"] is False
    assert totals["empty_reference_samples"] == totals["empty_extraction_samples"] == 1
    assert totals["exact_passage_match_rate"] is None


def test_missing_timing_and_disagreement_counts_remain_unknown():
    report = _evaluate(_case("A", extraction_seconds=2.0, reviewer_seconds=3.0, assessed_items=3, disagreements=1),
                       _case("B"))
    totals = report["cohorts"]["synthetic"]["totals"]
    for key in ("reported_extraction_seconds", "reported_reviewer_seconds", "reported_assessed_items",
                "reported_disagreements", "reported_disagreement_fraction"):
        assert totals[key] is None
    for key in ("unreported_extraction_timings", "unreported_reviewer_timings", "unreported_assessment_counts",
                "unreported_disagreement_counts"):
        assert totals[key] == 1


def test_declared_reviewer_disagreements_are_distinct_from_parser_failures():
    report = _evaluate(_case("A", wrong=True, extraction_seconds=0.0, reviewer_seconds=0.0,
                            assessed_items=5, disagreements=1),
                       _case("B", extraction_seconds=0.0, reviewer_seconds=0.0,
                             assessed_items=10, disagreements=0))
    totals = report["cohorts"]["synthetic"]["totals"]
    assert totals["text_mismatches"] == 1
    assert totals["reported_disagreement_fraction"] == 1 / 15
    assert totals["reported_assessed_items"] == 15
    assert totals["reported_extraction_seconds"] == totals["reported_reviewer_seconds"] == 0.0


def test_layout_practice_unit_and_format_slices_report_missing_strata():
    report = _evaluate(_case("A", kind="real", practice="commercial", layout="scanned", unit="decisions"))
    cohort = report["cohorts"]["real"]
    assert cohort["by_practice"]["commercial"]["sample_count"] == 1
    assert cohort["by_layout"]["scanned"]["sample_count"] == 1
    assert cohort["by_format"][".txt"]["sample_count"] == 1
    assert cohort["by_unit"]["decisions"]["sample_count"] == 1
    gaps = cohort["coverage_gaps"]
    assert gaps["unrepresented_practices"] == ["contracts", "employment"]
    assert gaps["unrepresented_target_units"] == ["pages", "amendment_chains"]
    assert gaps["unrepresented_known_layouts"] == ["born_digital", "mixed"]
    assert gaps["unannotated_critical_categories"] == ["date", "amount", "identifier", "exception"]
    assert gaps["representativeness_established"] is False


def test_unknown_layout_does_not_satisfy_known_layout_coverage():
    gaps = _evaluate(_case("A", layout="unknown"))["cohorts"]["synthetic"]["coverage_gaps"]
    assert gaps["unknown_layout_samples"] == 1
    assert gaps["unrepresented_known_layouts"] == ["born_digital", "scanned", "mixed"]


def test_declared_page_count_conflict_is_visible_without_authenticating_either_count():
    case = _case("A", unit="pages", observed_units=3)
    _replace_artifact(case, "extraction_sha256", lambda extraction: extraction.update(page_count=2))
    report = _evaluate(case)
    assert report["cohorts"]["synthetic"]["totals"]["declared_page_count_disagreements"] == 1
    assert report["declarations_authenticated"] is False


@pytest.mark.parametrize("field", ["sample_sha256", "raw_sha256", "source_identity_sha256"])
def test_duplicate_bindings_are_rejected_before_comparison(field):
    first, second = _case("A"), _case("B")
    second[0][field] = first[0][field]
    with pytest.raises(ValidationError, match="duplicate_study_source"):
        _study(first, second)


def test_duplicate_raw_bytes_cannot_be_counted_under_real_and_synthetic_labels():
    first, second = _case("A"), _case("B", kind="real")
    second[0]["raw_sha256"] = first[0]["raw_sha256"]
    with pytest.raises(ValidationError, match="duplicate_study_source"):
        _study(first, second)


def test_a_new_metadata_serialization_does_not_hide_a_duplicate_source():
    first = _case("A")
    second = copy.deepcopy(first)
    _replace_artifact(second, "sample_sha256", lambda sample: sample.update(extractor_version="new-version"))
    second[0]["source_identity_sha256"] = _sha(b"disguised identity")
    assert first[0]["sample_sha256"] != second[0]["sample_sha256"]
    with pytest.raises(ValidationError, match="duplicate_study_source"):
        _study(first, second)


@pytest.mark.parametrize("updates", [{"entries": []}, {"recorded_on": "2026-02-30"},
                                     {"recorded_on": "2026-1-05"}, {"dossier_sha256": "bad"},
                                     {"schema_version": "future"}, {"approved": True}])
def test_invalid_manifest_contract(updates):
    with pytest.raises(ValidationError):
        _study(_case("A"), **updates)


@pytest.mark.parametrize("field,value", [
    ("sample_kind", "private"), ("sample_kind", "real"), ("source_family_id", "claimed-family"),
    ("practice", "criminal"), ("layout", "image"), ("unit", "bytes"), ("observed_units", 0),
    ("observed_units", True), ("observed_units", 1_000_001), ("reviewer_seconds", -1.0),
    ("reviewer_seconds", float("nan")), ("reviewer_seconds", float("inf")), ("reviewer_seconds", True),
    ("reviewer_seconds", 1_000_000_001.0), ("assessed_items", -1), ("disagreements", 1),
    ("source_identity_sha256", "SECRET_BAD_ID"), ("extra_review_permission", True),
])
def test_invalid_entry_contract(field, value):
    case = _case("A")
    case[0][field] = value
    with pytest.raises(ValidationError):
        _study(case)


def test_disagreements_cannot_exceed_declared_assessed_items():
    with pytest.raises(ValidationError):
        _study(_case("A", assessed_items=1, disagreements=2))


def test_maximum_entry_budget_is_enforced():
    with pytest.raises(ValidationError):
        _study(*(_case(str(index)) for index in range(MAX_SAMPLES + 1)))


@pytest.mark.parametrize("field,value", [("practice", "employment"), ("sample_kind", "real"),
                                         ("raw_sha256", _sha(b"other raw")),
                                         ("extraction_sha256", _sha(b"other extraction")),
                                         ("reference_sha256", _sha(b"other reference"))])
def test_sample_inner_bindings_and_declarations_must_match_study(field, value):
    case = _case("A")
    def alter(sample):
        sample[field] = value
        if field == "sample_kind":
            sample["data_classification"] = "public_source"
    _replace_artifact(case, "sample_sha256", alter)
    manifest, artifacts = _study(case)
    with pytest.raises(StudyError, match="study_sample_declaration_mismatch"):
        evaluate_study(manifest, artifacts, DOSSIER, SOURCE_FAMILIES)


def test_sample_cannot_postdate_the_study():
    manifest, artifacts = _study(_case("A"), recorded_on="2026-10-04")
    with pytest.raises(StudyError, match="study_sample_postdates_manifest"):
        evaluate_study(manifest, artifacts, DOSSIER, SOURCE_FAMILIES)


def test_unknown_source_family_is_rejected_without_echoing_it():
    manifest, artifacts = _study(_case("A", kind="real", source_family_id="secret-unknown-family"))
    with pytest.raises(StudyError) as error:
        evaluate_study(manifest, artifacts, DOSSIER, SOURCE_FAMILIES)
    assert str(error.value) == "unknown_study_source_family"


@pytest.mark.parametrize("dossier", [{}, {**DOSSIER, "schema_version": "other"},
                                     {**DOSSIER, "structurally_valid": 1},
                                     {**DOSSIER, "dossier_sha256": _sha(b"changed dossier")}])
def test_dossier_report_must_be_valid_and_bound(dossier):
    manifest, artifacts = _study(_case("A"))
    with pytest.raises(StudyError, match="study_dossier_binding_mismatch"):
        evaluate_study(manifest, artifacts, dossier, SOURCE_FAMILIES)


@pytest.mark.parametrize("ids", [[], {123}, None])
def test_source_family_inventory_requires_exact_set_type(ids):
    manifest, artifacts = _study(_case("A"))
    with pytest.raises(StudyError, match="invalid_study_source_catalog"):
        evaluate_study(manifest, artifacts, DOSSIER, ids)


@pytest.mark.parametrize("mutation", ["missing", "extra", "report", "not_bytes", "corrupt"])
def test_exact_artifact_inventory_and_hashes_required(mutation):
    manifest, artifacts = _study(_case("A"))
    key = next(iter(artifacts))
    if mutation == "missing":
        artifacts.pop(key)
    elif mutation == "extra":
        artifacts["secret.bin"] = b"SECRET"
    elif mutation == "report":
        artifacts["report.json"] = b'{"all_declared_checks_passed":true}'
    elif mutation == "not_bytes":
        artifacts[key] = "SECRET_VALUE"
    elif mutation == "corrupt":
        artifacts[key] = b"SECRET_CHANGED_BYTES"
    with pytest.raises(StudyError) as error:
        evaluate_study(manifest, artifacts, DOSSIER, SOURCE_FAMILIES)
    assert "SECRET" not in str(error.value)


def test_sample_metadata_has_stricter_byte_budget_than_other_artifacts():
    manifest, artifacts = _study(_case("A"))
    key = f"{manifest.entries[0].sample_sha256}.bin"
    artifacts[key] = b" " * (MAX_SAMPLE_BYTES + 1)
    with pytest.raises(StudyError, match="invalid_study_artifact_size"):
        evaluate_study(manifest, artifacts, DOSSIER, SOURCE_FAMILIES)


def test_total_byte_budget_is_checked_in_addition_to_per_file_budgets(monkeypatch):
    manifest, artifacts = _study(_case("A"))
    monkeypatch.setattr("app.calibration_study.MAX_TOTAL_BYTES", sum(map(len, artifacts.values())) - 1)
    with pytest.raises(StudyError, match="study_artifact_budget_exceeded"):
        evaluate_study(manifest, artifacts, DOSSIER, SOURCE_FAMILIES)


def test_revalidation_rejects_mutated_nested_models_and_constructed_empty_models():
    manifest, artifacts = _study(_case("A"))
    manifest.entries.append(manifest.entries[0])
    with pytest.raises(StudyError, match="invalid_study_manifest"):
        evaluate_study(manifest, artifacts, DOSSIER, SOURCE_FAMILIES)
    empty = StudyManifest.model_construct(schema_version="extraction-calibration-study-v1",
                                          dossier_sha256=DOSSIER_HASH, recorded_on="2026-10-05", entries=[])
    with pytest.raises(StudyError, match="invalid_study_manifest"):
        artifact_specifications(empty)


def test_reports_never_echo_source_ids_original_text_warnings_locators_or_extractor_ids():
    report = _evaluate(_case("SECRET_RAW_SOURCE", kind="real"))
    encoded = json.dumps(report)
    assert "SECRET" not in encoded
    assert "synthetic-test-catalog-family" not in encoded
    assert "İcat" not in encoded


def test_artifact_inventory_uses_exact_hash_filenames_and_roles():
    manifest, artifacts = _study(_case("A"))
    specification = artifact_specifications(manifest)
    assert set(specification) == set(artifacts)
    assert specification[f"{manifest.entries[0].sample_sha256}.bin"] == MAX_SAMPLE_BYTES
    assert all(name.endswith(".bin") and len(name) == 68 for name in specification)


def test_study_schema_is_closed_and_carries_no_approval_fields():
    schema = StudyManifest.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["entries"]["minItems"] == 1
    assert schema["properties"]["entries"]["maxItems"] == 100
    assert schema["$defs"]["StudyEntry"]["additionalProperties"] is False
    assert "reviewed" not in json.dumps(schema)
