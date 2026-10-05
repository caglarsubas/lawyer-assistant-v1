"""Exact exported-artifact comparisons, not parser/rights/legal qualification."""

import copy
import hashlib
import json

import pytest
from pydantic import ValidationError

from app.extraction_calibration import (
    MAX_ARTIFACT_BYTES,
    MAX_JSON_NODES,
    MAX_RAW_BYTES,
    CalibrationError,
    CalibrationSample,
    ReferenceTranscription,
    evaluate_calibration,
)


def _json(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def artifacts():
    text = "İşçi 14.06.2020 tarihinde 1.234,56 TL ödeme yapmadı; istisna uygulanmaz."
    raw = text.encode("utf-8")
    spans = []
    for value, category in (("14.06.2020", "date"), ("1.234,56 TL", "amount"),
                            ("yapmadı", "negation"), ("istisna uygulanmaz", "exception")):
        start = text.index(value)
        spans.append({"start": start, "end": start + len(value), "category": category})
    extraction = {"passages": [{"locator": "Paragraph 1", "text": text}], "warnings": [],
                  "page_count": None, "passage_count": 1}
    reference = {"schema_version": "reference-transcription-v1", "raw_sha256": _sha(raw),
                 "coverage": "complete", "reference_status": "unreviewed",
                 "passages": [{"ordinal": 0, "locator": "Paragraph 1", "text": text, "critical_spans": spans}]}
    return raw, extraction, reference


def _sample(raw, extraction, reference, **updates):
    data = {"schema_version": "extraction-calibration-sample-v1", "sample_kind": "synthetic",
            "data_classification": "synthetic_fixture", "practice": "employment", "recorded_on": "2026-10-05",
            "source_suffix": ".txt", "raw_sha256": _sha(raw), "extraction_sha256": _sha(extraction),
            "reference_sha256": _sha(reference), "extractor_id": "synthetic-extractor", "extractor_version": "v1",
            "extraction_elapsed_seconds": None}
    data.update(updates)
    return CalibrationSample.model_validate(data)


def _evaluate(artifacts):
    raw, extraction, reference = artifacts
    extraction_bytes, reference_bytes = _json(extraction), _json(reference)
    return evaluate_calibration(_sample(raw, extraction_bytes, reference_bytes), raw, extraction_bytes, reference_bytes)


def test_exact_unicode_match_is_non_authorizing(artifacts):
    report = _evaluate(artifacts)
    comparison = report["comparison"]
    assert comparison["all_declared_checks_passed"] is True
    assert comparison["full_reference_comparison_passed"] is True
    assert comparison["exact_passage_match_rate"] == 1
    assert comparison["critical_span_match_rate"] == 1
    assert comparison["critical_categories"]["identifier"]["match_rate"] is None
    for key in ("source_authenticity_verified", "extractor_metadata_authenticated", "source_faithfulness_established",
                "legal_review_granted", "privacy_evaluated", "parser_executed", "authorizes_admission"):
        assert report[key] is False
    assert report["source_identity_deduplication"] == "not_evaluated"
    assert report["sample_independence"] == "not_established"
    assert report["runtime_authorization"] == "none"
    assert report["production_qualified"] is False


@pytest.mark.parametrize("old,new,category", [("2020", "2021", "date"), ("1.234,56", "1.334,56", "amount"),
                                             ("yapmadı", "yaptıxx", "negation"),
                                             ("uygulanmaz", "uygulanırx", "exception")])
def test_wrong_material_text_fails_its_exact_span(artifacts, old, new, category):
    artifacts[1]["passages"][0]["text"] = artifacts[1]["passages"][0]["text"].replace(old, new)
    comparison = _evaluate(artifacts)["comparison"]
    assert comparison["all_declared_checks_passed"] is False
    assert comparison["critical_categories"][category]["matched"] == 0
    assert comparison["text_mismatches"] == 1


def test_correct_text_at_another_position_does_not_repair_a_critical_span(artifacts):
    text = artifacts[1]["passages"][0]["text"]
    artifacts[1]["passages"][0]["text"] = text.replace("2020", "2021") + " Correct date: 14.06.2020"
    assert _evaluate(artifacts)["comparison"]["critical_categories"]["date"]["matched"] == 0


def test_correct_text_at_another_passage_does_not_receive_credit(artifacts):
    extraction = artifacts[1]
    correct = extraction["passages"][0]["text"]
    extraction["passages"][0]["text"] = "Wrong synthetic passage."
    extraction["passages"].append({"locator": "Paragraph 2", "text": correct})
    extraction["passage_count"] = 2
    comparison = _evaluate(artifacts)["comparison"]
    assert comparison["critical_span_matches"] == 0
    assert comparison["extra_passages"] == 1


def test_wrong_locator_disqualifies_otherwise_matching_critical_spans(artifacts):
    artifacts[1]["passages"][0]["locator"] = "Wrong page"
    comparison = _evaluate(artifacts)["comparison"]
    assert comparison["locator_mismatches"] == 1
    assert comparison["text_matches"] == 1
    assert comparison["critical_span_matches"] == 0
    assert comparison["exact_passage_matches"] == 0


def test_reordered_passages_fail_ordinal_and_locator_contract(artifacts):
    extraction, reference = artifacts[1:]
    extraction["passages"].append({"locator": "Paragraph 2", "text": "Different invented second passage."})
    extraction["passage_count"] = 2
    reference["passages"].append({"ordinal": 1, **extraction["passages"][1], "critical_spans": []})
    extraction["passages"].reverse()
    comparison = _evaluate(artifacts)["comparison"]
    assert comparison["exact_passage_matches"] == 0
    assert comparison["locator_mismatches"] == 2
    assert comparison["critical_span_matches"] == 0


def test_partial_gold_cannot_claim_full_coverage(artifacts):
    artifacts[2]["coverage"] = "partial"
    artifacts[1]["passages"].append({"locator": "Paragraph 2", "text": "Unscored synthetic passage."})
    artifacts[1]["passage_count"] = 2
    comparison = _evaluate(artifacts)["comparison"]
    assert comparison["all_declared_checks_passed"] is True
    assert comparison["full_reference_comparison_passed"] is False
    assert comparison["uncovered_passages"] == 1
    assert comparison["extra_passages"] is None


def test_missing_referenced_passage_is_counted_even_for_partial_gold(artifacts):
    artifacts[2]["coverage"] = "partial"
    artifacts[2]["passages"][0]["ordinal"] = 3
    comparison = _evaluate(artifacts)["comparison"]
    assert comparison["missing_passages"] == 1
    assert comparison["uncovered_passages"] == 1
    assert comparison["critical_span_match_rate"] == 0
    assert comparison["all_declared_checks_passed"] is False


def test_empty_extraction_and_empty_gold_remain_visible_failures(artifacts):
    artifacts[1].update({"passages": [], "passage_count": 0})
    comparison = _evaluate(artifacts)["comparison"]
    assert comparison["extraction_empty"] is True
    assert comparison["missing_passages"] == 1
    assert comparison["all_declared_checks_passed"] is False
    artifacts[2]["passages"] = []
    comparison = _evaluate(artifacts)["comparison"]
    assert comparison["exact_passage_match_rate"] is None
    assert comparison["critical_span_match_rate"] is None
    assert comparison["all_declared_checks_passed"] is False


def test_offsets_are_unicode_codepoints_not_utf8_bytes(artifacts):
    text = artifacts[2]["passages"][0]["text"]
    span = artifacts[2]["passages"][0]["critical_spans"][0]
    assert span["start"] == 5
    assert len(text[:span["start"]].encode("utf-8")) == 8
    artifacts[1]["passages"][0]["text"] = text[:5] + "X" + text[6:]
    comparison = _evaluate(artifacts)["comparison"]
    assert comparison["critical_categories"]["date"]["matched"] == 0


@pytest.mark.parametrize("expected,actual", [("İşçi\r\nödemedi", "İşçi\nödemedi"),
                                             ("İşçi", "Işçi"), ("é", "e\u0301")])
def test_no_line_ending_case_or_unicode_normalization(artifacts, expected, actual):
    artifacts[1]["passages"][0]["text"] = actual
    artifacts[2]["passages"][0].update({"text": expected, "critical_spans": []})
    assert _evaluate(artifacts)["comparison"]["exact_passage_matches"] == 0


@pytest.mark.parametrize("kind", ["raw", "extraction", "reference"])
def test_wrong_digest_rejected_without_comparison(artifacts, kind):
    raw, extraction, reference = artifacts
    extraction, reference = _json(extraction), _json(reference)
    sample = _sample(raw, extraction, reference, **{f"{kind}_sha256": "0" * 64})
    with pytest.raises(CalibrationError, match=f"^{kind}_digest_mismatch$"):
        evaluate_calibration(sample, raw, extraction, reference)


def test_gold_is_bound_to_its_raw_source(artifacts):
    artifacts[2]["raw_sha256"] = "0" * 64
    with pytest.raises(CalibrationError, match="^reference_raw_digest_mismatch$"):
        _evaluate(artifacts)


@pytest.mark.parametrize("field,value", [("passage_count", True), ("passage_count", "1"), ("page_count", 0),
                                        ("page_count", True), ("page_count", 501), ("passage_count", 2),
                                        ("warnings", ["\x00"]), ("warnings", [" " * 2])])
def test_extraction_counts_and_text_are_strict(artifacts, field, value):
    artifacts[1][field] = value
    with pytest.raises(CalibrationError, match="^invalid_extraction_artifact$"):
        _evaluate(artifacts)


@pytest.mark.parametrize("field,value", [("source_suffix", ".exe"), ("recorded_on", "2026-02-30"),
                                        ("extraction_elapsed_seconds", float("nan")),
                                        ("extraction_elapsed_seconds", float("inf")),
                                        ("extraction_elapsed_seconds", True),
                                        ("extraction_elapsed_seconds", -1.0),
                                        ("sample_kind", "private"), ("data_classification", "matter_private"),
                                        ("data_classification", "public_source")])
def test_sample_metadata_is_bounded_and_cannot_admit_private_inputs(artifacts, field, value):
    raw, extraction, reference = artifacts
    with pytest.raises(ValidationError):
        _sample(raw, _json(extraction), _json(reference), **{field: value})


def test_declared_real_source_status_is_not_authenticated(artifacts):
    raw, extraction, reference = artifacts
    extraction, reference = _json(extraction), _json(reference)
    sample = _sample(raw, extraction, reference, sample_kind="real", data_classification="public_source",
                     extraction_elapsed_seconds=0.5)
    report = evaluate_calibration(sample, raw, extraction, reference)
    assert report["source_authenticity_verified"] is False
    assert report["reported_extraction_elapsed_seconds"] == 0.5
    assert report["timing_measured_by_evaluator"] is False


@pytest.mark.parametrize("target", ["extraction", "reference"])
def test_duplicate_passages_rejected(artifacts, target):
    collection = artifacts[1 if target == "extraction" else 2]
    collection["passages"].append(copy.deepcopy(collection["passages"][0]))
    if target == "extraction":
        collection["passage_count"] += 1
    with pytest.raises(CalibrationError, match=f"^invalid_{target}_artifact$"):
        _evaluate(artifacts)


@pytest.mark.parametrize("start,end", [(0, 0), (9, 8), (True, 5), (0, 99999)])
def test_critical_span_bounds_are_strict(artifacts, start, end):
    artifacts[2]["passages"][0]["critical_spans"][0].update({"start": start, "end": end})
    with pytest.raises(CalibrationError, match="^invalid_reference_artifact$"):
        _evaluate(artifacts)


def test_complete_reference_cannot_hide_ordinal_gaps(artifacts):
    artifacts[2]["passages"][0]["ordinal"] = 2
    with pytest.raises(ValidationError, match="contiguous"):
        ReferenceTranscription.model_validate(artifacts[2])


def test_overlapping_span_comparison_work_is_bounded(artifacts):
    passage = artifacts[2]["passages"][0]
    passage["text"] = "x" * 2000
    passage["critical_spans"] = [{"start": index, "end": 2000, "category": "identifier"}
                                for index in range(2000)]
    with pytest.raises(ValidationError, match="work_limit"):
        ReferenceTranscription.model_validate(artifacts[2])


@pytest.mark.parametrize("bad_json,code", [(b'{"passages":[],"passages":[]}', "duplicate_json_field"),
                                         (b'{"unexpected":NaN}', "nonfinite_json_number"),
                                         (b'{"unexpected":1e9999}', "nonfinite_json_number"),
                                         (b'\xff', "invalid_extraction_artifact"),
                                         (b'[' * 25 + b'0' + b']' * 25, "json_depth_exceeded")])
def test_unsafe_json_fails_with_closed_diagnostic(artifacts, bad_json, code):
    raw, _, reference = artifacts
    reference = _json(reference)
    sample = _sample(raw, bad_json, reference)
    with pytest.raises(CalibrationError, match=f"^{code}$"):
        evaluate_calibration(sample, raw, bad_json, reference)


def test_shallow_wide_json_is_rejected_before_expanding_child_work(artifacts):
    raw, _, reference = artifacts
    reference = _json(reference)
    wide = b'{"unexpected":[' + b"0," * MAX_JSON_NODES + b"0]}"
    assert len(wide) < MAX_ARTIFACT_BYTES
    sample = _sample(raw, wide, reference)
    with pytest.raises(CalibrationError, match="^json_node_budget_exceeded$"):
        evaluate_calibration(sample, raw, wide, reference)


@pytest.mark.parametrize("which,maximum", [("raw", MAX_RAW_BYTES), ("extraction", MAX_ARTIFACT_BYTES),
                                         ("reference", MAX_ARTIFACT_BYTES)])
def test_byte_budgets_precede_parsing(artifacts, which, maximum):
    raw, extraction, reference = artifacts
    values = {"raw": raw, "extraction": _json(extraction), "reference": _json(reference)}
    values[which] = b"x" * (maximum + 1)
    sample = _sample(values["raw"], values["extraction"], values["reference"])
    with pytest.raises(CalibrationError, match=f"^invalid_{which}_size$"):
        evaluate_calibration(sample, values["raw"], values["extraction"], values["reference"])


def test_reports_and_errors_never_include_raw_text_locators_or_declared_ids(artifacts):
    raw, extraction, reference = artifacts
    extraction["warnings"] = ["PRIVATE-WARNING-MARKER"]
    extraction, reference = _json(extraction), _json(reference)
    sample = _sample(raw, extraction, reference, extractor_id="PRIVATE-ID-MARKER", extractor_version="PRIVATE-VERSION")
    report = json.dumps(evaluate_calibration(sample, raw, extraction, reference), ensure_ascii=False)
    for forbidden in ("PRIVATE-WARNING-MARKER", "PRIVATE-ID-MARKER", "PRIVATE-VERSION", "Paragraph 1", "İşçi"):
        assert forbidden not in report
    malformed = b'{"raw_client_text":"PRIVATE-ERROR-MARKER"}'
    sample = _sample(raw, malformed, reference)
    with pytest.raises(CalibrationError) as error:
        evaluate_calibration(sample, raw, malformed, reference)
    assert str(error.value) == "invalid_extraction_artifact"


def test_provenance_or_review_claims_are_rejected_as_extra_fields(artifacts):
    artifacts[2]["legally_reviewed"] = True
    with pytest.raises(CalibrationError, match="^invalid_reference_artifact$"):
        _evaluate(artifacts)
