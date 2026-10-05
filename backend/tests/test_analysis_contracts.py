"""Adversarial offline contracts; no provider, privacy or legal truth claims."""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.analysis_contracts import (
    AnalysisContract,
    ScenarioContract,
    summarize_analysis,
    summarize_scenario,
)

FIXTURES = Path(__file__).resolve().parents[2] / "qualification"


@pytest.fixture
def analysis():
    return json.loads((FIXTURES / "analysis-fixture.json").read_text())


@pytest.fixture
def scenario():
    return json.loads((FIXTURES / "scenario-fixture.json").read_text())


def test_synthetic_fixtures_validate_and_never_authorize(analysis, scenario):
    a = AnalysisContract.model_validate(analysis)
    s = ScenarioContract.model_validate_json(json.dumps(scenario))
    assert a.data_classification == s.data_classification == "synthetic_fixture"
    assert summarize_analysis(a)["legal_approval"] == "not_granted"
    assert summarize_scenario(s)["dispatchable"] is False
    assert summarize_scenario(s)["privacy_assessment"] == "not_performed"


@pytest.mark.parametrize("field,value", [("artifact_state", "Reviewed"), ("legal_approval", "granted"),
                                        ("schema_version", "analysis-contract.v2")])
def test_analysis_cannot_self_confer_approval(analysis, field, value):
    analysis[field] = value
    with pytest.raises(ValidationError):
        AnalysisContract.model_validate(analysis)


def test_strict_types_and_extra_fields(analysis, scenario):
    analysis["limits"]["max_revisions"] = "2"
    with pytest.raises(ValidationError):
        AnalysisContract.model_validate(analysis)
    scenario["outbound_candidate"]["provider_api_key"] = "synthetic-key-not-secret"
    with pytest.raises(ValidationError):
        ScenarioContract.model_validate(scenario)


@pytest.mark.parametrize("family", ["actors", "issues", "evidence", "premises", "rules", "applications",
                                     "alternatives", "conclusions", "defects"])
def test_duplicate_analysis_identifiers_rejected(analysis, family):
    analysis[family].append(copy.deepcopy(analysis[family][0]))
    with pytest.raises(ValidationError, match="Duplicate"):
        AnalysisContract.model_validate(analysis)


@pytest.mark.parametrize("family,field", [("premises", "actor_ids"), ("premises", "evidence_ids"),
                                         ("rules", "evidence_ids"), ("applications", "premise_ids"),
                                         ("conclusions", "application_ids"), ("conclusions", "alternative_ids")])
def test_missing_analysis_dependencies_rejected(analysis, family, field):
    analysis[family][0][field] = ["missing-reference"]
    with pytest.raises(ValidationError, match="Unresolved"):
        AnalysisContract.model_validate(analysis)


def test_allegation_cannot_be_relabelled_as_finding(analysis):
    analysis["premises"][0]["role"] = "judicial_finding"
    with pytest.raises(ValidationError, match="finding-role"):
        AnalysisContract.model_validate(analysis)


def test_editorial_summary_cannot_stand_in_for_a_provision(analysis):
    analysis["evidence"][1]["role"] = "editorial_summary"
    with pytest.raises(ValidationError, match="norm-role"):
        AnalysisContract.model_validate(analysis)


@pytest.mark.parametrize("disposition", ["conditional", "supported_candidate"])
def test_critical_defect_withholds_dependent_conclusion(analysis, disposition):
    analysis["conclusions"][0]["disposition"] = disposition
    with pytest.raises(ValidationError):
        AnalysisContract.model_validate(analysis)


def test_support_cannot_promote_an_allegation_after_a_defect_is_removed(analysis):
    analysis["defects"] = []
    analysis["conclusions"][0]["disposition"] = "supported_candidate"
    analysis["applications"][0]["conditions"][0]["status"] = "met"
    with pytest.raises(ValidationError, match="disputed application"):
        AnalysisContract.model_validate(analysis)


def test_new_exception_must_be_accounted_for(analysis):
    analysis["rules"][0]["conditions"].append({"id": "condition-exception", "text": "Synthetic exception.",
                                             "kind": "exception", "required_status": "not_met"})
    with pytest.raises(ValidationError, match="every rule condition"):
        AnalysisContract.model_validate(analysis)


def _supported_candidate(analysis):
    analysis["defects"] = []
    analysis["premises"][0]["role"] = "established_fact"
    analysis["applications"][0]["conditions"][0]["status"] = "met"
    analysis["conclusions"][0]["disposition"] = "supported_candidate"


def test_met_exception_cannot_support_a_rule_declaring_it_must_be_absent(analysis):
    _supported_candidate(analysis)
    analysis["rules"][0]["conditions"].append({"id": "exception-trigger", "text": "Invented exception triggers.",
                                             "kind": "exception", "required_status": "not_met"})
    assessment = {"condition_id": "exception-trigger", "status": "met", "premise_ids": ["premise-delivery"]}
    analysis["applications"][0]["conditions"].append(assessment)
    with pytest.raises(ValidationError, match="conditional or withheld"):
        AnalysisContract.model_validate(analysis)
    assessment["status"] = "not_met"
    candidate = AnalysisContract.model_validate(analysis)
    assert candidate.legal_approval == "not_granted"


def test_negative_conclusion_uses_declared_required_polarity_not_condition_kind(analysis):
    _supported_candidate(analysis)
    condition = analysis["rules"][0]["conditions"][0]
    condition["required_status"] = "not_met"
    analysis["conclusions"][0]["text"] = "Synthetic negative proposition because its declared prerequisite is absent."
    with pytest.raises(ValidationError, match="conditional or withheld"):
        AnalysisContract.model_validate(analysis)
    analysis["applications"][0]["conditions"][0]["status"] = "not_met"
    result = AnalysisContract.model_validate(analysis)
    assert result.rules[0].conditions[0].kind == "element"
    assert result.conclusions[0].disposition == "supported_candidate"
    assert result.legal_approval == "not_granted"


def test_condition_polarity_has_no_implicit_default(analysis):
    del analysis["rules"][0]["conditions"][0]["required_status"]
    with pytest.raises(ValidationError):
        AnalysisContract.model_validate(analysis)


def test_review_cutoff_is_inclusive_but_not_open_ended(analysis):
    analysis["applications"][0]["event_date"] = "2025-01-01"
    AnalysisContract.model_validate(analysis)
    analysis["applications"][0]["event_date"] = "2025-01-02"
    with pytest.raises(ValidationError, match="recorded interval"):
        AnalysisContract.model_validate(analysis)


def test_legal_end_is_exclusive_and_cannot_also_be_a_review_cutoff(analysis):
    analysis["rules"][0]["valid_to"] = "2025-01-01"
    with pytest.raises(ValidationError, match="distinct alternatives"):
        AnalysisContract.model_validate(analysis)
    analysis["rules"][0]["checked_through"] = None
    analysis["applications"][0]["event_date"] = "2025-01-01"
    with pytest.raises(ValidationError, match="recorded interval"):
        AnalysisContract.model_validate(analysis)


def test_unknown_dates_do_not_establish_applicability(analysis):
    analysis["rules"][0]["checked_through"] = None
    with pytest.raises(ValidationError, match="Unknown dates"):
        AnalysisContract.model_validate(analysis)
    analysis["applications"][0]["temporal_status"] = "unknown"
    AnalysisContract.model_validate(analysis)


@pytest.mark.parametrize("bad_date", ["2025-02-30", "20250101", "2025-1-1", "tomorrow"])
def test_invalid_or_noncanonical_dates_rejected(analysis, bad_date):
    analysis["applications"][0]["event_date"] = bad_date
    with pytest.raises(ValidationError):
        AnalysisContract.model_validate(analysis)


def test_resolved_candidate_requires_evidenced_bounded_correction(analysis):
    analysis["defects"][0]["status"] = "resolved_candidate"
    with pytest.raises(ValidationError, match="recorded evidence-linked correction"):
        AnalysisContract.model_validate(analysis)
    analysis["corrections"] = [{"id": "correction-one", "revision": 1, "defect_ids": ["defect-conformity"],
                                "conclusion_id": "conclusion-payment", "evidence_ids": ["evidence-allegation"],
                                "change_note": "Withheld unsupported claim; this is a correction candidate only.",
                                "remaining_uncertainty": ["Conformity remains disputed."]}]
    result = AnalysisContract.model_validate(analysis)
    assert result.legal_approval == "not_granted"
    analysis["corrections"][0]["revision"] = 3
    with pytest.raises(ValidationError, match="revision budget"):
        AnalysisContract.model_validate(analysis)


def test_unrelated_correction_cannot_mark_a_defect_resolved(analysis):
    analysis["premises"].append({"id": "premise-unrelated", "text": "Unrelated synthetic assumption.",
                                 "role": "assumption", "actor_ids": ["actor-supplier"], "evidence_ids": []})
    analysis["defects"][0].update({"status": "resolved_candidate", "target_id": "premise-unrelated"})
    analysis["corrections"] = [{"id": "correction-unrelated", "revision": 1, "defect_ids": ["defect-conformity"],
                                "conclusion_id": "conclusion-payment", "evidence_ids": ["evidence-allegation"],
                                "change_note": "This conclusion does not depend on the defective premise.",
                                "remaining_uncertainty": []}]
    with pytest.raises(ValidationError, match="outside its conclusion dependencies"):
        AnalysisContract.model_validate(analysis)


def test_critical_evidence_defect_propagates_to_dependent_conclusion(analysis):
    _supported_candidate(analysis)
    analysis["defects"] = [{"id": "defect-evidence", "target_id": "evidence-rule", "severity": "critical",
                            "status": "unresolved", "description": "The declared reference is unreliable."}]
    with pytest.raises(ValidationError, match="Unresolved critical defects"):
        AnalysisContract.model_validate(analysis)


def test_competing_arguments_cannot_be_borrowed_from_an_unrelated_issue(analysis):
    analysis["issues"].append({"id": "issue-other", "question": "Synthetic other question.", "posture": "Unknown."})
    analysis["alternatives"][0]["issue_id"] = "issue-other"
    with pytest.raises(ValidationError, match="same issue"):
        AnalysisContract.model_validate(analysis)


@pytest.mark.parametrize("field,value", [("dispatchable", True), ("dispatchable", 0), ("release_state", "approved"),
                                        ("privacy_assessment", "passed"), ("fidelity_assessment", "passed")])
def test_scenario_never_accepts_embedded_release_permission(scenario, field, value):
    scenario[field] = value
    with pytest.raises(ValidationError):
        ScenarioContract.model_validate(scenario)


@pytest.mark.parametrize("field,value", [("role", "established_fact"), ("polarity", "negated"),
                                        ("material_date", "2024-01-01"), ("threshold_comparison", "above"),
                                        ("event_order", 2)])
def test_transformation_cannot_mutate_declared_material_attributes(scenario, field, value):
    scenario["outbound_candidate"]["facts"][0]["attributes"][field] = value
    with pytest.raises(ValidationError, match="changed declared"):
        ScenarioContract.model_validate(scenario)


def test_material_source_fact_cannot_disappear(scenario):
    private = scenario["private_preparation"]
    extra = copy.deepcopy(private["source_facts"][0])
    extra["id"] = "material-other"
    private["source_facts"].append(extra)
    with pytest.raises(ValidationError, match="Every private source fact"):
        ScenarioContract.model_validate(scenario)
    private["omissions"].append({"source_fact_id": "material-other", "reason": "Too identifying."})
    with pytest.raises(ValidationError, match="material fact cannot be omitted"):
        ScenarioContract.model_validate(scenario)
    extra["is_material"] = False
    ScenarioContract.model_validate(scenario)


def test_unknown_fidelity_reference_rejected(scenario):
    scenario["private_preparation"]["transformations"][0]["fidelity_evidence_refs"] = ["missing-reference"]
    with pytest.raises(ValidationError, match="fidelity references"):
        ScenarioContract.model_validate(scenario)


def test_distinct_actors_cannot_be_merged_or_substituted(scenario):
    scenario["private_preparation"]["actor_mappings"][1]["actor_id"] = "actor-supplier"
    with pytest.raises(ValidationError, match="actor mappings"):
        ScenarioContract.model_validate(scenario)


def test_relationship_roles_cannot_reverse(scenario):
    scenario["outbound_candidate"]["relationships"][0]["from_actor"] = "actor-buyer"
    scenario["outbound_candidate"]["relationships"][0]["to_actor"] = "actor-supplier"
    with pytest.raises(ValidationError, match="declared actor roles"):
        ScenarioContract.model_validate(scenario)


def test_assumptions_remain_labelled_hypothetical(scenario):
    scenario["outbound_candidate"]["facts"][0]["attributes"]["role"] = "assumption"
    scenario["private_preparation"]["source_facts"][0]["attributes"]["role"] = "assumption"
    with pytest.raises(ValidationError, match="Hypothetical"):
        ScenarioContract.model_validate(scenario)
    scenario["outbound_candidate"]["scenario_kind"] = "labelled_hypothetical"
    ScenarioContract.model_validate(scenario)


def test_contradictory_chronology_rejected_even_when_transformation_attributes_match(scenario):
    outbound = scenario["outbound_candidate"]
    private = scenario["private_preparation"]
    first = outbound["facts"][0]["attributes"]
    first["material_date"] = "2024-01-02"
    private["source_facts"][0]["attributes"] = copy.deepcopy(first)
    second = copy.deepcopy(outbound["facts"][0])
    second["id"] = "fact-second"
    second["attributes"].update({"event_order": 2, "material_date": "2024-01-01"})
    outbound["facts"].append(second)
    source = copy.deepcopy(private["source_facts"][0])
    source["id"] = "source-second"
    source["attributes"] = copy.deepcopy(second["attributes"])
    private["source_facts"].append(source)
    transformation = copy.deepcopy(private["transformations"][0])
    transformation.update({"source_fact_id": "source-second", "proposed_fact_id": "fact-second"})
    private["transformations"].append(transformation)
    with pytest.raises(ValidationError, match="chronology"):
        ScenarioContract.model_validate(scenario)


def test_schema_does_not_claim_to_detect_pii_or_semantic_mutation(scenario):
    # Deliberately unsafe synthetic text is structurally valid, but NEVER dispatchable.
    # A successful parse cannot substitute for the future local privacy/fidelity gates.
    scenario["outbound_candidate"]["facts"][0]["text"] = "Synthetic Alice Example: alice@example.invalid"
    result = ScenarioContract.model_validate(scenario)
    assert result.dispatchable is False
    assert result.privacy_assessment == "not_performed"
    assert result.fidelity_assessment == "structural_only"


def test_summaries_never_include_narratives_or_private_references(analysis, scenario):
    analysis["premises"][0]["text"] = "SYNTHETIC-PRIVATE-MARKER"
    scenario["private_preparation"]["transformations"][0]["reason"] = "SYNTHETIC-PRIVATE-MARKER"
    output = json.dumps([summarize_analysis(AnalysisContract.model_validate(analysis)),
                         summarize_scenario(ScenarioContract.model_validate(scenario))])
    assert "SYNTHETIC-PRIVATE-MARKER" not in output
    assert "synthetic-private-supplier" not in output
    assert "evidence-allegation" not in output
