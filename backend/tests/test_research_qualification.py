"""Offline qualification records must not become permission or invented evidence."""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.research_qualification import ResearchDossier, summarize_research_dossier

SEED = Path(__file__).resolve().parents[2] / "qualification" / "research-dossier.json"


@pytest.fixture
def payload():
    return json.loads(SEED.read_bytes())


def parse(payload):
    return ResearchDossier.model_validate_json(json.dumps(payload))


def add_sample(payload, *, kind="real", unit="pages", practice="contracts", count=10,
               elapsed=120.0, reviewer=240.0, assessed=10, disagreements=2, suffix="a"):
    evidence_id = f"evidence-{kind}-{suffix}"
    payload["evidence_records"].append({
        "evidence_id": evidence_id, "sha256": suffix * 64, "sample_kind": kind,
        "recorded_on": "2026-10-05", "owner_role": "evaluation_owner",
    })
    payload["measurements"].append({
        "measurement_id": f"measurement-{kind}-{suffix}", "evidence_id": evidence_id,
        "sample_kind": kind, "practice": practice, "unit": unit, "observed_units": count,
        "elapsed_seconds": elapsed, "reviewer_seconds": reviewer,
        "assessed_items": assessed, "disagreements": disagreements,
    })


def test_seed_is_only_a_plan_with_three_disabled_unqualified_providers(payload):
    result = summarize_research_dossier(parse(payload))
    assert result["production_qualified"] is False
    assert result["external_dispatch_authorized"] is False
    assert result["evidence_authenticated"] is False
    assert {entry["provider"] for entry in result["provider_plans"]} == {"openai", "anthropic", "gemini"}
    for entry in result["provider_plans"]:
        assert entry["dispatch_enabled"] is False
        assert entry["runtime_qualification"] == "unqualified"
        assert entry["account_configuration"] == "not_supplied"
        assert entry["gate_counts"] == {"pending": 12, "blocked": 0, "evidence_recorded": 0}
    assert result["evaluation"]["development_target_tasks"] == 360
    assert result["evaluation"]["held_out_target_tasks"] == 1000
    assert result["evaluation"]["held_out_target_substantive_claims"] == 3000
    assert result["evaluation"]["observed_task_results"] is None
    assert result["evaluation"]["slice_sample_size_counts"] == {"pending": 11}
    assert result["evaluation"]["unknown_provider_sample_minima"] == 5
    assert result["evaluation"]["comparison_plans"] == ["correction", "privacy_fidelity", "standard_deep"]
    assert result["capacity"]["baseline_weeks"] == [30, 36]
    assert result["capacity"]["measured_delivery_estimate_weeks"] is None
    assert result["calibration"]["real_sample_count_targets_met"] is False
    for group in ("real", "synthetic"):
        for unit in result["calibration"][group]["units"].values():
            assert unit["observed_units"] == 0
            assert unit["population_denominator"] is None
            assert unit["population_fraction"] is None
            assert unit["elapsed_seconds"] is None
            assert unit["reviewer_seconds"] is None
            assert unit["elapsed_seconds_per_unit"] is None


def test_unknown_measurement_denominators_and_timings_stay_unknown(payload):
    add_sample(payload, elapsed=None, reviewer=None, assessed=None, disagreements=None)
    result = summarize_research_dossier(parse(payload))
    real = result["calibration"]["real"]
    assert real["units"]["pages"]["observed_units"] == 10
    assert real["units"]["pages"]["untimed_measurements"] == 1
    assert real["units"]["pages"]["unreviewed_timing_measurements"] == 1
    assert real["units"]["pages"]["population_fraction"] is None
    assert real["units"]["pages"]["elapsed_seconds"] is None
    assert real["assessed_items"] is None
    assert real["disagreement_fraction"] is None
    assert result["capacity"]["real_timing_measurements"] == 0


def test_synthetic_measurements_cannot_complete_real_calibration(payload):
    for unit, practice, count, suffix in [
        ("pages", "contracts", 100, "a"),
        ("amendment_chains", "commercial", 10, "b"),
        ("decisions", "employment", 30, "c"),
    ]:
        add_sample(payload, kind="synthetic", unit=unit, practice=practice, count=count, suffix=suffix)
    result = summarize_research_dossier(parse(payload))
    assert result["calibration"]["synthetic"]["measurement_count"] == 3
    assert result["calibration"]["real"]["measurement_count"] == 0
    assert result["calibration"]["real_sample_count_targets_met"] is False
    assert result["calibration"]["all_launch_practices_observed_in_real_samples"] is False
    assert result["capacity"]["real_timing_measurements"] == 0
    assert result["capacity"]["measured_delivery_estimate_weeks"] is None


def test_real_samples_aggregate_by_unit_without_promoting_qualification(payload):
    add_sample(payload, count=100, elapsed=1000.0, reviewer=2000.0, assessed=100, disagreements=5)
    add_sample(payload, unit="amendment_chains", practice="commercial", count=10, suffix="b")
    add_sample(payload, unit="decisions", practice="employment", count=30, suffix="c")
    add_sample(payload, kind="synthetic", count=500, elapsed=1.0, reviewer=1.0, suffix="d")
    payload["calibration_plan"]["population_denominators"]["pages"] = 1000
    result = summarize_research_dossier(parse(payload))
    real = result["calibration"]["real"]
    assert real["units"]["pages"]["observed_units"] == 100
    assert real["units"]["pages"]["population_fraction"] == 0.1
    assert real["units"]["pages"]["elapsed_seconds_per_unit"] == 10.0
    assert real["units"]["pages"]["reviewer_seconds_per_unit"] == 20.0
    assert real["assessed_items"] == 120
    assert real["disagreements"] == 9
    assert real["disagreement_fraction"] == 9 / 120
    assert result["calibration"]["real_sample_count_targets_met"] is True
    assert result["calibration"]["all_launch_practices_observed_in_real_samples"] is True
    assert result["capacity"]["real_timing_measurements"] == 3
    assert result["capacity"]["measured_delivery_estimate_weeks"] is None
    assert result["production_qualified"] is False


def test_partial_timings_do_not_understate_total_work(payload):
    add_sample(payload)
    add_sample(payload, elapsed=None, reviewer=None, assessed=None, disagreements=None, suffix="b")
    real = summarize_research_dossier(parse(payload))["calibration"]["real"]
    assert real["units"]["pages"]["observed_units"] == 20
    assert real["units"]["pages"]["elapsed_seconds"] is None
    assert real["units"]["pages"]["elapsed_seconds_per_unit"] is None
    assert real["units"]["pages"]["reviewer_seconds"] is None
    assert real["disagreement_fraction"] is None


def test_evidence_recorded_is_not_runtime_or_legal_approval(payload):
    add_sample(payload, kind="synthetic")
    gate = payload["providers"][0]["gates"][0]
    gate.update(status="evidence_recorded", evidence_ids=[payload["evidence_records"][0]["evidence_id"]])
    result = summarize_research_dossier(parse(payload))
    assert result["provider_plans"][0]["gate_counts"]["evidence_recorded"] == 1
    assert result["provider_plans"][0]["runtime_qualification"] == "unqualified"
    assert result["production_qualified"] is False
    assert result["external_dispatch_authorized"] is False
    assert result["evidence_authenticated"] is False


def test_summary_does_not_echo_private_record_references_or_documentation_urls(payload):
    add_sample(payload)
    payload["dossier_id"] = "confidential-dossier-identifier"
    payload["evidence_records"][0]["evidence_id"] = "confidential-evidence-identifier"
    payload["measurements"][0]["evidence_id"] = "confidential-evidence-identifier"
    payload["measurements"][0]["measurement_id"] = "confidential-measurement-identifier"
    encoded = json.dumps(summarize_research_dossier(parse(payload)))
    assert "confidential" not in encoded
    assert "a" * 64 not in encoded
    assert "https://" not in encoded
    assert "checked_on" not in encoded


@pytest.mark.parametrize("field,value", [
    ("dispatch_enabled", True), ("dispatch_enabled", "false"), ("dispatch_enabled", 0),
    ("runtime_qualification", "qualified"), ("account_configuration", "verified"),
    ("api_key", "never-accept-a-key"), ("account_id", "never-store-an-account"),
    ("model", "not-an-adapter-configuration"), ("endpoint", "https://example.com"),
])
def test_provider_record_cannot_enable_dispatch_or_store_account_configuration(payload, field, value):
    payload["providers"][0][field] = value
    with pytest.raises(ValidationError):
        parse(payload)


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(production_qualified=True),
    lambda p: p["capacity"].update(measured_delivery_estimate_weeks=20),
    lambda p: p["evaluation"].update(observed_results={"accuracy": 1}),
    lambda p: p["providers"][0]["documentation"][0].update(account_retention_verified=True),
    lambda p: p["providers"][0]["gates"][0].update(status="approved"),
    lambda p: p["providers"][0]["gates"][0].update(status="evidence_recorded"),
    lambda p: p["providers"][0]["gates"][0].update(evidence_ids=["missing-evidence"]),
    lambda p: p["providers"].__setitem__(1, copy.deepcopy(p["providers"][0])),
    lambda p: p["providers"][0]["gates"].__setitem__(1, copy.deepcopy(p["providers"][0]["gates"][0])),
    lambda p: p["providers"][0]["documentation"].append(copy.deepcopy(p["providers"][0]["documentation"][0])),
])
def test_unknown_fields_and_fabricated_approval_or_duplicate_provider_records_fail(payload, mutate):
    mutate(payload)
    with pytest.raises(ValidationError):
        parse(payload)


@pytest.mark.parametrize("url", [
    "http://developers.openai.com/api/docs/guides/your-data",
    "https://developers.openai.com.evil.example/api/docs/guides/your-data",
    "https://key@developers.openai.com/api/docs/guides/your-data",
    "https://developers.openai.com/api/docs/guides/your-data?api_key=secret",
    "https://developers.openai.com/api/docs/guides/your-data#secret",
    "https://ai.google.dev/gemini-api/docs/zdr",
    "file:///Users/example/.env", "http://127.0.0.1/", "https://example.com/",
])
def test_reference_catalog_does_not_accept_arbitrary_or_cross_provider_destinations(payload, url):
    payload["providers"][0]["documentation"][0]["url"] = url
    with pytest.raises(ValidationError):
        parse(payload)


@pytest.mark.parametrize("mutate", [
    lambda p: p["evaluation"]["held_out"].update(dataset_id=p["evaluation"]["development"]["dataset_id"]),
    lambda p: p["evaluation"]["held_out"].update(purpose="development"),
    lambda p: p["evaluation"]["held_out"].update(target_substantive_claims=2999),
    lambda p: p["evaluation"]["held_out"].update(target_tasks=999),
    lambda p: p["evaluation"]["development"].update(target_tasks=359),
    lambda p: p["evaluation"]["development"]["practice_task_targets"].update(contracts=119),
    lambda p: p["evaluation"].update(independent_annotators=1),
    lambda p: p["evaluation"].update(adjudication_required=False),
    lambda p: p["evaluation"].update(split_by_source_proceeding_and_duplicate_family=False),
    lambda p: p["evaluation"]["slices"].__setitem__(1, copy.deepcopy(p["evaluation"]["slices"][0])),
    lambda p: p["evaluation"]["slices"][0].update(development_target=361),
    lambda p: p["evaluation"]["slices"][0].update(held_out_target=1001),
    lambda p: p["evaluation"]["slices"][0].update(sample_size_status="planned"),
    lambda p: p["evaluation"]["slices"][0].update(minimum_per_provider=10),
    lambda p: p["evaluation"]["slices"][5].update(provider_ids=["openai"]),
    lambda p: p["evaluation"]["slices"][5].update(provider_ids=["openai", "openai", "gemini"]),
    lambda p: p["evaluation"]["comparisons"][0].update(candidate="deep"),
    lambda p: p["evaluation"]["comparisons"][0].update(same_tasks=False),
    lambda p: p["evaluation"]["comparisons"][0].update(pinned_inputs_and_snapshot=False),
    lambda p: p["evaluation"]["comparisons"][0].update(includes_verification_and_correction_time=False),
    lambda p: p["evaluation"]["comparisons"][0].update(target_pairs=361),
    lambda p: p["evaluation"]["comparisons"].__setitem__(1, copy.deepcopy(p["evaluation"]["comparisons"][0])),
])
def test_evaluation_design_rejects_leakage_weaker_samples_and_uncontrolled_comparisons(payload, mutate):
    mutate(payload)
    with pytest.raises(ValidationError):
        parse(payload)


def test_planned_provider_slice_still_reports_targets_only(payload):
    entry = payload["evaluation"]["slices"][5]
    entry.update(sample_size_status="planned", development_target=30, held_out_target=40,
                 minimum_per_provider=20)
    result = summarize_research_dossier(parse(payload))
    assert result["evaluation"]["slice_sample_size_counts"] == {"pending": 10, "planned": 1}
    assert result["evaluation"]["observed_task_results"] is None
    entry["minimum_per_provider"] = 31
    with pytest.raises(ValidationError):
        parse(payload)


@pytest.mark.parametrize("field,value", [
    ("evidence_id", "unknown-evidence"), ("sample_kind", "synthetic"),
    ("observed_units", 0), ("observed_units", True), ("observed_units", "10"),
    ("elapsed_seconds", -1.0), ("elapsed_seconds", float("nan")),
    ("elapsed_seconds", float("inf")), ("reviewer_seconds", -1.0),
    ("assessed_items", None), ("disagreements", 11), ("disagreements", -1),
    ("practice", "family"), ("unit", "tasks"), ("legal_approval", True),
])
def test_measurement_requires_typed_bounded_consistent_evidence(payload, field, value):
    add_sample(payload)
    payload["measurements"][0][field] = value
    with pytest.raises(ValidationError):
        parse(payload)


@pytest.mark.parametrize("mutate", [
    lambda p: p["evidence_records"][0].update(sha256="not-a-digest"),
    lambda p: p["evidence_records"][0].update(recorded_on="2026-02-30"),
    lambda p: p["evidence_records"][0].update(recorded_on="2026-10-06"),
    lambda p: p["measurements"].append(copy.deepcopy(p["measurements"][0])),
    lambda p: p["evidence_records"].append(copy.deepcopy(p["evidence_records"][0])),
    lambda p: p["calibration_plan"]["population_denominators"].update(pages=9),
    lambda p: p["calibration_plan"]["target_units"].update(pages=99),
    lambda p: p["calibration_plan"]["target_units"].pop("decisions"),
    lambda p: p["calibration_plan"]["population_denominators"].pop("decisions"),
    lambda p: p["calibration_plan"].update(practices=["contracts", "contracts", "employment"]),
    lambda p: p.update(recorded_on="2026-02-30"),
    lambda p: p["providers"][0]["documentation"][0].update(checked_on="2026-10-06"),
    lambda p: p["capacity"].update(baseline_weeks_min=37),
    lambda p: p["capacity"].update(baseline_fte=0.0),
    lambda p: p["capacity"]["added_workstreams"].__setitem__(1, "local_analysis"),
    lambda p: p.update(dossier_id="a" * 81),
    lambda p: p.update(dossier_id="../private/.env"),
])
def test_calibration_and_capacity_fail_closed_on_integrity_errors(payload, mutate):
    add_sample(payload)
    mutate(payload)
    with pytest.raises(ValidationError):
        parse(payload)


def test_relabeling_same_artifact_or_reusing_measurement_evidence_does_not_double_count(payload):
    add_sample(payload)
    add_sample(payload, suffix="b")
    payload["evidence_records"][1]["sha256"] = payload["evidence_records"][0]["sha256"]
    with pytest.raises(ValidationError):
        parse(payload)
    payload["evidence_records"][1]["sha256"] = "b" * 64
    payload["measurements"][1]["evidence_id"] = payload["measurements"][0]["evidence_id"]
    with pytest.raises(ValidationError):
        parse(payload)


def test_summary_revalidates_mutated_models_instead_of_trusting_constructed_objects(payload):
    dossier = parse(payload)
    dossier.providers.clear()
    with pytest.raises(ValidationError):
        summarize_research_dossier(dossier)


def test_roundtrip_matches_json_and_python_validation(payload):
    dossier = parse(payload)
    assert ResearchDossier.model_validate(dossier.model_dump()) == dossier
    assert ResearchDossier.model_validate_json(dossier.model_dump_json()) == dossier
