"""Offline preparation contracts, not legal adjudication, sanitization or dispatch.

References and declared structured attributes are checked for consistency. Their
truth, passage support and narrative meaning require independent future checks.
Never use successful parsing (or these summaries) as a release capability.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
Text = Annotated[str, Field(min_length=1, max_length=4000)]
References = Annotated[list[Identifier], Field(max_length=100)]
NonemptyReferences = Annotated[list[Identifier], Field(min_length=1, max_length=100)]


def _iso_date(value: str) -> str:
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError("Dates must use YYYY-MM-DD")
    return value


ISODate = Annotated[str, AfterValidator(_iso_date)]
FactRole = Literal["established_fact", "allegation", "judicial_finding", "disputed_fact", "assumption", "unknown"]
ActorRole = Literal["claimant", "respondent", "supplier", "buyer", "employer", "worker", "guarantor", "authority", "other"]


class ContractInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


def _unique(values: list[str], label: str) -> set[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label}")
    return set(values)


def _refs(values: list[str], known: set[str] | dict, label: str) -> None:
    _unique(values, label)
    if any(value not in known for value in values):
        raise ValueError(f"Unresolved {label}")


def _index(items: list, label: str) -> dict:
    _unique([item.id for item in items], label)
    return {item.id: item for item in items}


class Actor(ContractInput):
    id: Identifier
    role: ActorRole


class EvidenceReference(ContractInput):
    id: Identifier
    source_id: Identifier
    source_version: Identifier
    passage_id: Identifier
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    role: Literal["private_document", "norm_passage", "judicial_finding", "majority_reasoning",
                  "dissent_reasoning", "operative_result", "editorial_summary"]

    @model_validator(mode="after")
    def span(self):
        if self.end <= self.start:
            raise ValueError("Evidence span must have positive length")
        return self


class Issue(ContractInput):
    id: Identifier
    question: Text
    posture: Text


class Premise(ContractInput):
    id: Identifier
    text: Text
    role: FactRole
    actor_ids: NonemptyReferences
    evidence_ids: References


class Condition(ContractInput):
    id: Identifier
    text: Text
    kind: Literal["element", "exception", "jurisdiction", "burden"]
    # Declared by the draft's author for its particular proposition. Never infer
    # this polarity from "exception" or a presumed positive legal outcome.
    required_status: Literal["met", "not_met"]


class Rule(ContractInput):
    id: Identifier
    authority_id: Identifier
    provision_version_id: Identifier
    text: Text
    evidence_ids: NonemptyReferences
    conditions: list[Condition] = Field(min_length=1, max_length=100)
    valid_from: ISODate | None
    valid_to: ISODate | None
    checked_through: ISODate | None

    @model_validator(mode="after")
    def interval(self):
        _index(self.conditions, "rule conditions")
        if self.valid_to is not None and self.checked_through is not None:
            raise ValueError("Legal end and reviewed-open cutoff are distinct alternatives")
        if self.valid_to is not None and (self.valid_from is None or self.valid_to <= self.valid_from):
            raise ValueError("Legal interval must be nonempty with a known start")
        if self.checked_through is not None and (
            self.valid_from is None or self.checked_through < self.valid_from
        ):
            raise ValueError("Reviewed-open cutoff requires an ordered known start")
        return self


class ConditionAssessment(ContractInput):
    condition_id: Identifier
    status: Literal["met", "not_met", "unknown"]
    premise_ids: References


class Application(ContractInput):
    id: Identifier
    issue_id: Identifier
    rule_id: Identifier
    premise_ids: NonemptyReferences
    rationale: Text
    event_date: ISODate | None
    temporal_status: Literal["within_recorded_interval", "unknown", "outside_recorded_interval"]
    conditions: list[ConditionAssessment] = Field(min_length=1, max_length=100)


class Alternative(ContractInput):
    id: Identifier
    issue_id: Identifier
    kind: Literal["adverse_argument", "alternative_classification", "material_distinction", "search_gap"]
    text: Text
    evidence_ids: References


class Conclusion(ContractInput):
    id: Identifier
    issue_id: Identifier
    application_ids: NonemptyReferences
    alternative_ids: NonemptyReferences
    disposition: Literal["supported_candidate", "conditional", "withheld"]
    text: Text
    uncertainty: list[Text] = Field(max_length=100)
    next_step: Text


class Defect(ContractInput):
    id: Identifier
    target_id: Identifier
    severity: Literal["critical", "major", "minor"]
    status: Literal["unresolved", "resolved_candidate"]
    description: Text


class Correction(ContractInput):
    id: Identifier
    revision: int = Field(ge=1, le=10)
    defect_ids: NonemptyReferences
    conclusion_id: Identifier
    evidence_ids: NonemptyReferences
    change_note: Text
    remaining_uncertainty: list[Text] = Field(max_length=100)


class AnalysisLimits(ContractInput):
    mode: Literal["standard", "deep"]
    max_revisions: int = Field(ge=0, le=10)
    max_retrieval_calls: int = Field(ge=1, le=1000)
    max_context_tokens: int = Field(ge=1, le=2000000)
    max_generated_tokens: int = Field(ge=1, le=1000000)
    max_elapsed_seconds: int = Field(ge=1, le=86400)
    stop_reason: Literal["not_started", "checks_complete", "evidence_exhausted", "budget_exhausted", "cancelled"]


class AnalysisContract(ContractInput):
    schema_version: Literal["analysis-contract.v1"]
    data_classification: Literal["synthetic_fixture", "matter_private"]
    purpose: Literal["offline_preparation"]
    artifact_state: Literal["Draft", "Needs review", "Stale"]
    legal_approval: Literal["not_granted"]
    actors: list[Actor] = Field(min_length=1, max_length=100)
    issues: list[Issue] = Field(min_length=1, max_length=100)
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=1000)
    premises: list[Premise] = Field(min_length=1, max_length=1000)
    rules: list[Rule] = Field(min_length=1, max_length=1000)
    applications: list[Application] = Field(min_length=1, max_length=1000)
    alternatives: list[Alternative] = Field(min_length=1, max_length=1000)
    conclusions: list[Conclusion] = Field(min_length=1, max_length=1000)
    defects: list[Defect] = Field(max_length=1000)
    corrections: list[Correction] = Field(max_length=1000)
    limits: AnalysisLimits

    @model_validator(mode="after")
    def references_and_consistency(self):
        families = (self.actors, self.issues, self.evidence, self.premises, self.rules,
                    self.applications, self.alternatives, self.conclusions, self.defects, self.corrections)
        _unique([item.id for family in families for item in family], "artifact identifiers")
        actors, issues, evidence, premises, rules, applications, alternatives, conclusions, defects, _ = (
            _index(family, "identifiers") for family in families
        )
        for premise in self.premises:
            _refs(premise.actor_ids, actors, "premise actors")
            _refs(premise.evidence_ids, evidence, "premise evidence")
            if premise.role not in {"assumption", "unknown"} and not premise.evidence_ids:
                raise ValueError("Factual premises need passage references")
            if premise.role == "judicial_finding" and not any(
                evidence[ref].role == "judicial_finding" for ref in premise.evidence_ids
            ):
                raise ValueError("A finding requires finding-role evidence, not an allegation or dissent")
        for rule in self.rules:
            _refs(rule.evidence_ids, evidence, "rule evidence")
            if not any(evidence[ref].role == "norm_passage" for ref in rule.evidence_ids):
                raise ValueError("A provision rule requires norm-role evidence")
        for application in self.applications:
            _refs([application.issue_id], issues, "application issue")
            _refs([application.rule_id], rules, "application rule")
            _refs(application.premise_ids, premises, "application premises")
            rule = rules[application.rule_id]
            condition_ids = _unique([item.condition_id for item in application.conditions], "assessments")
            if condition_ids != {item.id for item in rule.conditions}:
                raise ValueError("Application must account for every rule condition and exception")
            for assessment in application.conditions:
                _refs(assessment.premise_ids, set(application.premise_ids), "condition premises")
                if assessment.status != "unknown" and not assessment.premise_ids:
                    raise ValueError("Determinate condition assessments require premise references")
            if application.temporal_status != "unknown":
                end = rule.valid_to or rule.checked_through
                if application.event_date is None or rule.valid_from is None or end is None:
                    raise ValueError("Unknown dates do not establish temporal applicability")
                inside = application.event_date >= rule.valid_from and (
                    application.event_date < end if rule.valid_to else application.event_date <= end
                )
                if inside != (application.temporal_status == "within_recorded_interval"):
                    raise ValueError("Declared applicability conflicts with the recorded interval")
        for alternative in self.alternatives:
            _refs([alternative.issue_id], issues, "alternative issue")
            _refs(alternative.evidence_ids, evidence, "alternative evidence")
            if alternative.kind != "search_gap" and not alternative.evidence_ids:
                raise ValueError("An asserted competing argument requires source references")
        dependency_sets = {}
        for conclusion in self.conclusions:
            _refs([conclusion.issue_id], issues, "conclusion issue")
            _refs(conclusion.application_ids, applications, "conclusion applications")
            _refs(conclusion.alternative_ids, alternatives, "conclusion alternatives")
            dependencies = {conclusion.id, conclusion.issue_id, *conclusion.application_ids, *conclusion.alternative_ids}
            for ref in conclusion.application_ids:
                application = applications[ref]
                dependencies.update((application.rule_id, *application.premise_ids))
                dependencies.update(rules[application.rule_id].evidence_ids)
                for premise_ref in application.premise_ids:
                    dependencies.update(premises[premise_ref].evidence_ids)
            for ref in conclusion.alternative_ids:
                dependencies.update(alternatives[ref].evidence_ids)
            dependency_sets[conclusion.id] = dependencies
        target_ids = (set(premises) | set(rules) | set(applications) | set(conclusions)
                      | set(issues) | set(alternatives) | set(evidence))
        for defect in self.defects:
            _refs([defect.target_id], target_ids, "defect target")
        corrected = set()
        for correction in self.corrections:
            _refs(correction.defect_ids, defects, "correction defects")
            _refs([correction.conclusion_id], conclusions, "corrected conclusion")
            _refs(correction.evidence_ids, evidence, "correction evidence")
            if any(defects[ref].target_id not in dependency_sets[correction.conclusion_id]
                   for ref in correction.defect_ids):
                raise ValueError("Correction cannot resolve a defect outside its conclusion dependencies")
            if correction.revision > self.limits.max_revisions:
                raise ValueError("Correction exceeds the declared revision budget")
            corrected.update(correction.defect_ids)
        if any(defect.status == "resolved_candidate" and defect.id not in corrected for defect in self.defects):
            raise ValueError("Resolved defect candidates require a recorded evidence-linked correction")
        for conclusion in self.conclusions:
            _refs([conclusion.issue_id], issues, "conclusion issue")
            _refs(conclusion.application_ids, applications, "conclusion applications")
            _refs(conclusion.alternative_ids, alternatives, "conclusion alternatives")
            dependencies = dependency_sets[conclusion.id]
            for ref in conclusion.application_ids:
                application = applications[ref]
                if application.issue_id != conclusion.issue_id:
                    raise ValueError("A conclusion cannot silently reuse another issue's application")
                dependencies.update((application.rule_id, *application.premise_ids))
                if conclusion.disposition == "supported_candidate" and (
                    application.temporal_status != "within_recorded_interval"
                    or any(item.status != {condition.id: condition.required_status
                                           for condition in rules[application.rule_id].conditions}[item.condition_id]
                           for item in application.conditions)
                    or any(premises[item].role not in {"established_fact", "judicial_finding"}
                           for item in application.premise_ids)
                ):
                    raise ValueError("Incomplete or disputed application must remain conditional or withheld")
            if any(alternatives[ref].issue_id != conclusion.issue_id for ref in conclusion.alternative_ids):
                raise ValueError("Competing arguments must concern the same issue")
            critical = any(defect.severity == "critical" and defect.status == "unresolved"
                           and defect.target_id in dependencies for defect in self.defects)
            if critical and conclusion.disposition != "withheld":
                raise ValueError("Unresolved critical defects withhold affected conclusions")
            if conclusion.disposition != "supported_candidate" and not conclusion.uncertainty:
                raise ValueError("Conditional or withheld conclusions must expose uncertainty")
        return self


class FactAttributes(ContractInput):
    role: FactRole
    polarity: Literal["affirmed", "negated", "unknown"]
    material_date: ISODate | None
    threshold_comparison: Literal["below", "equal", "above", "unknown"] | None
    event_order: int | None = Field(ge=0, le=10000)


class ScenarioFact(ContractInput):
    id: Identifier
    actor_ids: NonemptyReferences
    text: Text
    attributes: FactAttributes


class Relationship(ContractInput):
    id: Identifier
    from_actor: Identifier
    to_actor: Identifier
    kind: Literal["claims_against", "contracts_with", "employed_by", "supplies_to", "guarantees_for"]


class OutboundScenario(ContractInput):
    jurisdiction: Literal["TR"]
    scenario_kind: Literal["actual_abstraction", "labelled_hypothetical"]
    actors: list[Actor] = Field(min_length=1, max_length=100)
    relationships: list[Relationship] = Field(max_length=100)
    facts: list[ScenarioFact] = Field(min_length=1, max_length=100)
    research_questions: list[Text] = Field(min_length=1, max_length=20)
    uncertainty: list[Text] = Field(max_length=100)
    requested_authority_types: list[Literal["legislation", "decision", "institutional_guidance"]] = Field(
        min_length=1, max_length=3
    )


class PrivateActorMapping(ContractInput):
    actor_id: Identifier
    private_actor_ref: Identifier


class PrivateSourceFact(ContractInput):
    id: Identifier
    private_evidence_ref: Identifier
    private_actor_refs: NonemptyReferences
    is_material: bool
    attributes: FactAttributes


class PrivateTransformation(ContractInput):
    source_fact_id: Identifier
    proposed_fact_id: Identifier
    transformation: Literal["preserved", "generalized"]
    reason: Text
    fidelity_evidence_refs: NonemptyReferences


class PrivateOmission(ContractInput):
    source_fact_id: Identifier
    reason: Text


class PrivatePreparation(ContractInput):
    actor_mappings: list[PrivateActorMapping] = Field(min_length=1, max_length=100)
    source_facts: list[PrivateSourceFact] = Field(min_length=1, max_length=100)
    transformations: list[PrivateTransformation] = Field(min_length=1, max_length=100)
    omissions: list[PrivateOmission] = Field(max_length=100)
    fidelity_reference_ids: NonemptyReferences


class ScenarioContract(ContractInput):
    schema_version: Literal["scenario-contract.v1"]
    data_classification: Literal["synthetic_fixture", "matter_private"]
    purpose: Literal["offline_preparation"]
    release_state: Literal["preparation_only"]
    dispatchable: Literal[False]
    privacy_assessment: Literal["not_performed"]
    fidelity_assessment: Literal["structural_only"]
    outbound_candidate: OutboundScenario
    private_preparation: PrivatePreparation

    @field_validator("dispatchable", mode="before")
    @classmethod
    def strictly_false(cls, value):
        # Literal[False] otherwise accepts numeric zero under Pydantic.
        if value is not False:
            raise ValueError("A preparation contract requires the literal boolean false")
        return value

    @model_validator(mode="after")
    def structural_fidelity(self):
        outbound = self.outbound_candidate
        private = self.private_preparation
        actors = _index(outbound.actors, "scenario actors")
        facts = _index(outbound.facts, "scenario facts")
        _unique([item.id for item in outbound.actors + outbound.facts + outbound.relationships], "scenario identifiers")
        source_facts = _index(private.source_facts, "private source facts")
        actor_map = {item.private_actor_ref: item.actor_id for item in private.actor_mappings}
        _unique([item.private_actor_ref for item in private.actor_mappings], "private actors")
        if _unique([item.actor_id for item in private.actor_mappings], "actor mappings") != set(actors):
            raise ValueError("Each neutral actor needs one distinct private actor mapping")
        _unique(private.fidelity_reference_ids, "fidelity evidence references")
        _unique(outbound.requested_authority_types, "requested authority types")
        for relationship in outbound.relationships:
            _refs([relationship.from_actor, relationship.to_actor], actors, "relationship actors")
            required_roles = {"employed_by": ("worker", "employer"), "supplies_to": ("supplier", "buyer")}
            if relationship.kind in required_roles and (
                actors[relationship.from_actor].role, actors[relationship.to_actor].role
            ) != required_roles[relationship.kind]:
                raise ValueError("Relationship conflicts with the declared actor roles")
        for fact in outbound.facts:
            _refs(fact.actor_ids, actors, "scenario fact actors")
            if outbound.scenario_kind == "actual_abstraction" and fact.attributes.role == "assumption":
                raise ValueError("Hypothetical assumptions must not become actual scenario facts")
        for source in private.source_facts:
            _refs(source.private_actor_refs, actor_map, "private source actors")
        covered = [item.source_fact_id for item in private.transformations + private.omissions]
        if _unique(covered, "source fact dispositions") != set(source_facts):
            raise ValueError("Every private source fact needs exactly one transformation or omission")
        if _unique([item.proposed_fact_id for item in private.transformations], "transformed facts") != set(facts):
            raise ValueError("Every outbound fact must have exactly one private transformation")
        for transformation in private.transformations:
            source = source_facts[transformation.source_fact_id]
            proposed = facts[transformation.proposed_fact_id]
            _refs(transformation.fidelity_evidence_refs, set(private.fidelity_reference_ids), "fidelity references")
            if {actor_map[ref] for ref in source.private_actor_refs} != set(proposed.actor_ids):
                raise ValueError("Transformation must preserve distinct actor relationships")
            if source.attributes != proposed.attributes:
                raise ValueError("Transformation changed declared role, negation, material date, threshold or chronology")
        if any(source_facts[item.source_fact_id].is_material for item in private.omissions):
            raise ValueError("A declared material fact cannot be omitted from the research scenario")
        ordered = [fact.attributes for fact in outbound.facts
                   if fact.attributes.material_date is not None and fact.attributes.event_order is not None]
        for left in ordered:
            for right in ordered:
                if left.event_order < right.event_order and left.material_date > right.material_date:
                    raise ValueError("Material dates contradict declared chronology")
        if any(fact.attributes.role in {"unknown", "disputed_fact", "allegation"} for fact in outbound.facts):
            if not outbound.uncertainty:
                raise ValueError("Uncertain scenario facts require explicit uncertainty")
        return self


def summarize_analysis(contract: AnalysisContract) -> dict:
    """Safe CLI report: no narratives, source identifiers or evidence contents."""
    return {
        "schema_version": contract.schema_version,
        "data_classification": contract.data_classification,
        "artifact_state": contract.artifact_state,
        "legal_approval": "not_granted",
        "validation_scope": "declared_structure_and_references_only",
        "counts": {"issues": len(contract.issues), "premises": len(contract.premises),
                   "rules": len(contract.rules), "applications": len(contract.applications),
                   "conclusions": len(contract.conclusions), "corrections": len(contract.corrections),
                   "unresolved_critical_defects": sum(item.severity == "critical" and item.status == "unresolved"
                                                      for item in contract.defects)},
    }


def summarize_scenario(contract: ScenarioContract) -> dict:
    """Structural success is deliberately incapable of granting dispatch."""
    return {
        "schema_version": contract.schema_version,
        "data_classification": contract.data_classification,
        "release_state": "preparation_only",
        "dispatchable": False,
        "privacy_assessment": "not_performed",
        "fidelity_assessment": "structural_only",
        "counts": {"actors": len(contract.outbound_candidate.actors),
                   "facts": len(contract.outbound_candidate.facts),
                   "research_questions": len(contract.outbound_candidate.research_questions),
                   "transformations": len(contract.private_preparation.transformations),
                   "omissions": len(contract.private_preparation.omissions)},
    }
