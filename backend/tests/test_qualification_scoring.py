"""Invented labels exercise scoring mathematics, never real legal qualification."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from app.evaluation import evaluate_release
from app.qualification_scoring import digest, evaluate_qualification

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


fixture = module("build_evaluation_fixture").fixture
cli = module("evaluate_release")


def planned(provider=None):
    protocol, snapshot, rows = fixture(provider)
    for key in ("practice_minimums", "slice_minimums", "pair_minimums", "metric_minimums"):
        protocol[key] = dict.fromkeys(protocol[key], 1)  # Test-only small slice targets.
    protocol["independent_family_minimum"] = 1
    for row in rows:
        row["protocol_sha256"] = digest(protocol)
    return protocol, snapshot, rows


def enough(provider=None):
    protocol, snapshot, seeds = planned(provider)
    rows = []
    for index in range(1000):
        row = copy.deepcopy(seeds[index % 4])
        row["sample_kind"] = "real"  # In-memory simulation of adjudication; never exported as evidence.
        row["score"]["task_id"] = f"fixture-{index}"
        row["task_input_sha256"] = digest(index)
        row["split_family_sha256"] = digest(f"family-{index}")
        for pair in row["pairs"]:
            for trial in (pair["baseline"], pair["candidate"]):
                trial["task_input_sha256"] = row["task_input_sha256"]
        rows.append(row)
    return protocol, snapshot, rows


@pytest.mark.parametrize("provider", [None, "openai", "anthropic", "gemini"])
def test_complete_quantitative_scoring_is_separate_per_scope_and_never_approval(provider):
    protocol, snapshot, rows = enough(provider)
    result = evaluate_qualification(rows, snapshot, protocol)
    assert result["quantitative_gates_pass"]
    assert result["runtime_authorization"] == "none" and not result["production_qualified"]
    assert result["provider"] == provider
    assert all(not pair["statistical_improvement_established"] for pair in result["paired_comparisons"].values())
    assert set(result["slices"]) == set(protocol["slice_minimums"])
    # The legacy API may report perfect core metrics but cannot claim that it
    # scored the new gates, or return the complete-qualification success flag.
    legacy = evaluate_release([row["score"] for row in rows], snapshot)
    assert legacy["core_quantitative_gates_pass"] and not legacy["quantitative_gates_pass"]


def test_unknown_minima_synthetic_rows_and_empty_samples_cannot_pass():
    protocol, snapshot, rows = fixture("openai")
    result = evaluate_qualification(rows, snapshot, protocol)
    assert not result["gates"]["real_held_out_evidence"]
    assert not any(value["pass"] for value in result["slices"].values())
    assert not result["gates"]["paired_standard_deep"]
    empty = evaluate_qualification([], snapshot, protocol)
    assert empty["core_metrics"]["claim_support"] is None
    assert empty["analysis"]["adverse_recall_at_20"] is None
    assert not empty["quantitative_gates_pass"]


@pytest.mark.parametrize("change", ["protocol", "snapshot", "rubric", "provider", "provider_configuration", "mode", "before_registration", "development", "duplicate_input", "duplicate_task", "not_held_out", "pair_input", "pair_snapshot", "pair_mode", "annotators"])
def test_mixed_or_unmatched_evidence_is_rejected(change):
    protocol, snapshot, rows = planned("openai")
    row = rows[0]
    if change in {"protocol", "snapshot", "rubric"}:
        row[change + "_sha256"] = "f" * 64
    elif change == "provider_configuration":
        row["provider_configuration_sha256"] = "f" * 64
    elif change == "provider":
        row["provider"] = "gemini"
    elif change == "mode":
        row["mode"] = "local"
    elif change == "before_registration":
        row["measured_at"] = "2025-01-01T00:00:00Z"
    elif change == "development":
        row["split_family_sha256"] = protocol["development_family_sha256"][0]
    elif change == "duplicate_input":
        rows[1]["task_input_sha256"] = row["task_input_sha256"]
        for pair in rows[1]["pairs"]:
            for trial in (pair["baseline"], pair["candidate"]):
                trial["task_input_sha256"] = row["task_input_sha256"]
    elif change == "duplicate_task":
        rows[1]["score"]["task_id"] = row["score"]["task_id"]
    elif change == "not_held_out":
        row["score"]["held_out"] = False
    elif change == "pair_input":
        row["pairs"][0]["candidate"]["task_input_sha256"] = "f" * 64
    elif change == "pair_snapshot":
        row["pairs"][0]["candidate"]["snapshot_sha256"] = "f" * 64
    elif change == "pair_mode":
        row["pairs"][0]["candidate"]["mode"] = "deep"
    else:
        row["annotators"] = ["same", "same"]
    with pytest.raises(ValueError):
        evaluate_qualification(rows, snapshot, protocol)


@pytest.mark.parametrize("category", ["privacy_direct", "privacy_contextual", "legal_fidelity", "key_authorization_spend", "returned_evidence", "disconnected_operations"])
@pytest.mark.parametrize("verdict", [False, None, "missing"])
def test_a_single_failure_or_unmeasured_check_cannot_be_averaged_away(category, verdict):
    from app.qualification_scoring import CONNECTED_SLICES, LOCAL_SLICES
    protocol, snapshot, rows = planned("anthropic")
    check = sorted((LOCAL_SLICES | CONNECTED_SLICES)[category])[0]
    if verdict == "missing":
        rows[0]["checks"].pop(check)
    else:
        rows[0]["checks"][check] = verdict
    result = evaluate_qualification(rows, snapshot, protocol)
    assert not result["gates"]["slice_" + category]
    assert result["slices"][category]["checks"][check]["assessed"] == (4 if verdict is False else 3)
    assert result["slices"][category]["checks"][check]["failed"] == int(verdict is False)


@pytest.mark.parametrize("field", ["critical_unsupported_inferences", "critical_fact_substitutions", "critical_omissions", "critical_role_errors"])
def test_analysis_errors_are_independent_of_core_claim_labels(field):
    protocol, snapshot, rows = planned()
    rows[0]["analysis"][field] = 1
    result = evaluate_qualification(rows, snapshot, protocol)
    assert result["core_metrics"]["claim_support"] == 1
    assert not result["gates"]["zero_critical_analysis_errors"]


@pytest.mark.parametrize("change", ["grounding", "adverse", "missing_gold", "missing_argument", "unresolved_adjudication", "metric_minimum", "family_minimum"])
def test_missing_coverage_or_quality_fails_its_own_gate(change):
    protocol, snapshot, rows = planned()
    if change == "grounding":
        rows[0]["analysis"]["grounded_steps"] = 2
        gate = "argument_grounding"
    elif change == "adverse":
        rows[0]["analysis"]["retrieved_adverse_authorities"] = []
        gate = "adverse_recall_at_20"
    elif change == "missing_gold":
        rows[0]["analysis"]["gold_adverse_authorities"] = []
        for pair in rows[0]["pairs"]:
            pair["candidate"]["adverse_found"] = pair["baseline"]["adverse_found"] = []
        gate = "slice_adverse_authority"
    elif change == "missing_argument":
        rows[0]["analysis"]["consequential_steps"] = rows[0]["analysis"]["grounded_steps"] = 0
        gate = "argument_grounding"
    elif change == "unresolved_adjudication":
        rows[0]["disagreements_resolved"] = False
        gate = "adjudication_resolved"
    else:
        if change == "metric_minimum":
            protocol["metric_minimums"]["exact_identifier_tasks"] = 5
            gate = "sample_exact_identifier_tasks"
        else:
            protocol["independent_family_minimum"] = 5
            gate = "family_sample"
        for row in rows:
            row["protocol_sha256"] = digest(protocol)
    assert not evaluate_qualification(rows, snapshot, protocol)["gates"][gate]


@pytest.mark.parametrize("change", ["support", "citations", "adverse", "quality", "critical", "time", "introduced", "unresolved", "floor"])
def test_pairs_do_not_hide_regressions_or_missing_measurement(change):
    protocol, snapshot, rows = planned()
    pair = rows[0]["pairs"][0]
    if change == "support":
        pair["candidate"]["supported_claims"] = 2
    elif change == "citations":
        pair["candidate"]["claims_with_resolvable_citations"] = 2
    elif change == "adverse":
        pair["candidate"]["adverse_found"] = []
    elif change == "quality":
        pair["candidate"]["argument_quality"] = 0.7
    elif change == "critical":
        pair["candidate"]["critical_errors"] = 1
    elif change == "time":
        pair["candidate"]["verification_and_correction_included"] = False
    elif change == "introduced":
        pair["introduced_regressions"] = 1
    elif change == "unresolved":
        pair["repaired_with_evidence"] = 0
        pair["unresolved_defects"] = 1
    else:
        pair["candidate"]["supported_claims"] = pair["baseline"]["supported_claims"] = 2
    assert not evaluate_qualification(rows, snapshot, protocol)["gates"]["paired_correction"]


def test_comparison_metrics_report_actual_tradeoffs_and_safe_local_sensitive_completion():
    protocol, snapshot, rows = planned("gemini")
    pair = rows[0]["pairs"][1]
    pair["candidate"].update(elapsed_seconds=12.0, compute_seconds=15.0, external_cost_usd=0.2,
                             preparation_seconds=8.0, review_seconds=6.0, argument_quality=0.9)
    result = evaluate_qualification(rows, snapshot, protocol)
    assert result["core_metrics"]["legitimate_sensitive_passage"] == 1
    assert result["paired_comparisons"]["standard_deep"]["improved_pairs_without_regression"] == 1
    # Remaining pairs unchanged: a single gain is counted but the median stays zero.
    assert result["paired_comparisons"]["standard_deep"]["median_candidate_minus_baseline"]["external_cost_usd"] == 0
    assert not result["paired_comparisons"]["standard_deep"]["statistical_improvement_established"]


@pytest.mark.parametrize("provider", [None, "openai"])
@pytest.mark.parametrize("trial", ["baseline", "candidate"])
def test_local_trials_cannot_report_external_charges_even_in_connected_evaluations(provider, trial):
    protocol, snapshot, rows = planned(provider)
    pair = rows[0]["pairs"][-1]  # Connected privacy-fidelity pairs are also local.
    pair[trial]["external_cost_usd"] = 0.1
    with pytest.raises(ValueError):
        evaluate_qualification(rows, snapshot, protocol)


@pytest.mark.parametrize("value", [True, "1", -1, float("inf"), float("nan")])
def test_counts_are_strict_and_finite(value):
    protocol, snapshot, rows = planned()
    rows[0]["score"]["critical_errors"] = value
    with pytest.raises(ValueError):
        evaluate_qualification(rows, snapshot, protocol)


def write_files(tmp_path, provider=None):
    protocol, snapshot, rows = fixture(provider)
    tasks, pin, plan = (tmp_path / name for name in ("tasks.jsonl", "snapshot.json", "protocol.json"))
    tasks.write_text("".join(json.dumps(row) + "\n" for row in rows))
    pin.write_text(json.dumps(snapshot))
    plan.write_text(json.dumps(protocol))
    return tasks, pin, plan


def test_cli_keeps_examples_unqualified_and_emits_only_aggregate_evidence(tmp_path, capsys):
    tasks, snapshot, protocol = write_files(tmp_path, "openai")
    assert cli.main([str(tasks), "--snapshot", str(snapshot), "--protocol", str(protocol)]) == 1
    raw = capsys.readouterr().out
    report = json.loads(raw)
    assert report["sample_kinds"] == {"synthetic": 4}
    assert report["runtime_authorization"] == "none"
    assert "synthetic-arbiter" not in raw and "synthetic-adverse" not in raw and str(tmp_path) not in raw
    assert set(report["input_files"]) == {"tasks", "snapshot", "protocol"}
    assert cli.main(["--schemas"]) == 0
    assert "protocol" in json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("change", ["duplicate_json", "symlink", "oversize", "nonfinite", "unknown_args", "bad_root", "changed_input"])
def test_cli_denies_bad_or_changing_files_without_leaking_values(tmp_path, monkeypatch, capsys, change):
    tasks, snapshot, protocol = write_files(tmp_path)
    args = [str(tasks), "--snapshot", str(snapshot), "--protocol", str(protocol)]
    if change == "duplicate_json":
        tasks.write_text('{"PRIVATE":"secret", "PRIVATE":"second"}\n')
    elif change == "symlink":
        link = tmp_path / "link.jsonl"
        link.symlink_to(tasks)
        args[0] = str(link)
    elif change == "oversize":
        monkeypatch.setattr(cli, "MAX_TASK_BYTES", 1)
    elif change == "nonfinite":
        tasks.write_text('{"PRIVATE":NaN}\n')
    elif change == "unknown_args":
        args.append("--PRIVATE")
    elif change == "bad_root":
        snapshot.write_text('null')
    else:
        original = cli.evaluate_qualification
        def evaluate(*args):
            result = original(*args)
            tasks.write_text("PRIVATE changed")
            return result
        monkeypatch.setattr(cli, "evaluate_qualification", evaluate)
    assert cli.main(args) == 2
    output = capsys.readouterr()
    assert not output.out and "PRIVATE" not in output.err and str(tmp_path) not in output.err


@pytest.mark.parametrize("change", ["missing_slice", "missing_metric", "missing_pair", "missing_practice", "zero_minimum", "boolean_minimum", "weaker_task_target", "weaker_claim_target", "local_provider", "missing_provider", "unknown_provider", "naive_time"])
def test_protocol_cannot_omit_mandatory_dimensions_or_weaken_core_gates(change):
    protocol, snapshot, rows = planned()
    if change.startswith("missing_") and change != "missing_provider":
        field = {"missing_slice": "slice_minimums", "missing_metric": "metric_minimums",
                 "missing_pair": "pair_minimums", "missing_practice": "practice_minimums"}[change]
        protocol[field].pop(next(iter(protocol[field])))
    elif change in {"zero_minimum", "boolean_minimum"}:
        protocol["metric_minimums"]["retrieval_tasks"] = 0 if change == "zero_minimum" else True
    elif change == "weaker_task_target":
        protocol["task_target"] = 999
    elif change == "weaker_claim_target":
        protocol["claim_target"] = 2999
    elif change == "local_provider":
        protocol["provider"] = "openai"
    elif change == "missing_provider":
        protocol["mode"] = "connected"
    elif change == "unknown_provider":
        protocol["provider"] = "unreviewed-provider"
    else:
        protocol["registered_at"] = "2026-01-01"
    with pytest.raises(ValueError):
        evaluate_qualification(rows, snapshot, protocol)


def test_synthetic_evidence_cannot_top_up_a_real_cohort():
    protocol, snapshot, rows = enough()
    rows[-1]["sample_kind"] = "synthetic"
    result = evaluate_qualification(rows, snapshot, protocol)
    assert result["gates"]["task_sample"]
    assert not result["gates"]["real_held_out_evidence"] and not result["quantitative_gates_pass"]


def test_row_and_file_limits_are_checked_before_parsing(tmp_path, monkeypatch, capsys):
    tasks, snapshot, protocol = write_files(tmp_path)
    monkeypatch.setattr(cli, "MAX_ROWS", 1)
    assert cli.main([str(tasks), "--snapshot", str(snapshot), "--protocol", str(protocol)]) == 2
    assert not capsys.readouterr().out
