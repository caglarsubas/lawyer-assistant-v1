import pytest

from app.evaluation import evaluate_release

SNAPSHOT = {key: "synthetic-test-only" for key in ("ontology", "graphs", "corpus", "model", "policy")}


def row(**changes):
    return {
        "task_id": "test",
        "adjudicator": "fixture",
        "held_out": True,
        "domain": "contracts",
        "period": "historical",
        "relationship_types": ["citation"],
        "claims": [{"supported": True, "citation_resolves": True}],
        "critical_errors": 0,
        "answerable": True,
        "satisfactory": True,
        **changes,
    }


def test_zero_denominators_never_pass():
    result = evaluate_release([], SNAPSHOT)
    assert result["metrics"]["claim_support"] is None
    assert not result["quantitative_gates_pass"]
    assert not result["production_qualified"]


def test_perfect_small_sample_cannot_claim_qualification():
    result = evaluate_release([row()], SNAPSHOT)
    assert result["metrics"]["claim_support"] == 1
    assert not result["gates"]["claim_sample"]
    assert not result["gates"]["task_sample"]
    assert not result["quantitative_gates_pass"]


def test_recall_and_time_include_required_denominators():
    result = evaluate_release(
        [
            row(
                gold_authorities=["a", "b", "c", "d"],
                retrieved_authorities=["a", "b"],
                baseline_seconds=100,
                assisted_seconds=50,
            )
        ],
        SNAPSHOT,
    )
    assert result["metrics"]["recall_at_20"] == 0.5
    assert result["metrics"]["median_preparation_time_reduction"] is None
    result = evaluate_release(
        [row(baseline_seconds=100, assisted_seconds=70, verification_and_correction_included=True)], SNAPSHOT
    )
    assert result["metrics"]["median_preparation_time_reduction"] == pytest.approx(0.3)


def test_nonheldout_duplicate_or_unversioned_evidence_rejected():
    for rows, snapshot in [([row(held_out=False)], SNAPSHOT), ([row(), row()], SNAPSHOT), ([row()], {})]:
        with pytest.raises(ValueError):
            evaluate_release(rows, snapshot)


def test_missing_abstention_judgment_does_not_pass():
    result = evaluate_release([row(answerable=False)], SNAPSHOT)
    assert result["metrics"]["appropriate_abstention"] == 0
    assert not result["gates"]["appropriate_abstention"]


@pytest.mark.parametrize("value", [float("inf"), float("nan"), -float("inf")])
def test_nonfinite_timings_cannot_inflate_time_savings(value):
    with pytest.raises(ValueError):
        evaluate_release([row(baseline_seconds=value, assisted_seconds=10,
                              verification_and_correction_included=True)], SNAPSHOT)
