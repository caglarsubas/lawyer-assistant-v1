"""Offline R01 planning records, not provider credentials or runtime authorization.

This module deliberately imports no settings, database, network or provider client.
Evidence references describe operator-supplied records; parsing never authenticates
their contents or grants legal, privacy, billing or production approval.
"""

from collections import Counter
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

RecordId = Annotated[str, StringConstraints(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Day = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
Count = Annotated[int, Field(ge=0, le=1_000_000)]
Seconds = Annotated[float, Field(ge=0, le=1_000_000_000)]
Provider = Literal["openai", "anthropic", "gemini"]
Practice = Literal["contracts", "commercial", "employment"]
Unit = Literal["pages", "amendment_chains", "decisions"]
SampleKind = Literal["real", "synthetic"]
OwnerRole = Literal[
    "legal_ontology_owner", "source_rights_owner", "privacy_legal_owner",
    "security_owner", "application_owner", "evaluation_owner", "operations_owner", "product_owner",
]
Gate = Literal[
    "account_entitlement", "privacy_transfer", "retention_deletion", "tools",
    "key_isolation", "legal_fidelity", "spend_retry", "returned_evidence",
    "training_terms", "region_processors", "attribution", "incident_handling",
]
Slice = Literal[
    "citation_temporal", "adverse_authority", "evidence_roles", "correction",
    "standard_deep", "privacy_direct", "privacy_contextual", "legal_fidelity",
    "key_authorization_spend", "returned_evidence", "disconnected_operations",
]
Comparison = Literal["correction", "standard_deep", "privacy_fidelity"]

PROVIDERS = {"openai", "anthropic", "gemini"}
PRACTICES = {"contracts", "commercial", "employment"}
UNITS = {"pages", "amendment_chains", "decisions"}
GATES = {
    "account_entitlement", "privacy_transfer", "retention_deletion", "tools",
    "key_isolation", "legal_fidelity", "spend_retry", "returned_evidence",
    "training_terms", "region_processors", "attribution", "incident_handling",
}
SLICES = {
    "citation_temporal", "adverse_authority", "evidence_roles", "correction",
    "standard_deep", "privacy_direct", "privacy_contextual", "legal_fidelity",
    "key_authorization_spend", "returned_evidence", "disconnected_operations",
}
PROVIDER_SLICES = {
    "privacy_direct", "privacy_contextual", "legal_fidelity",
    "key_authorization_spend", "returned_evidence",
}
OFFICIAL_DOCUMENTATION = {
    "openai": {
        "https://developers.openai.com/api/docs/guides/tools-web-search",
        "https://developers.openai.com/api/docs/guides/deep-research",
        "https://developers.openai.com/api/docs/guides/your-data",
    },
    "anthropic": {
        "https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool",
        "https://platform.claude.com/docs/en/manage-claude/api-and-data-retention",
    },
    "gemini": {
        "https://ai.google.dev/gemini-api/docs/deep-research",
        "https://ai.google.dev/gemini-api/docs/zdr",
    },
}
PAIR_MODES = {
    "correction": ("single_pass", "bounded_correction"),
    "standard_deep": ("standard", "deep"),
    "privacy_fidelity": ("original_private_local", "sanitized_scenario_local"),
}


def _unique(values, label):
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label}")


def _day(value: str) -> date:
    return date.fromisoformat(value)


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, frozen=True)


class DocumentationReference(StrictRecord):
    url: Annotated[str, StringConstraints(min_length=1, max_length=240)]
    checked_on: Day
    evidence_scope: Literal["documentary_only"]

    @model_validator(mode="after")
    def valid_day(self):
        _day(self.checked_on)
        return self


class QualificationGate(StrictRecord):
    gate: Gate
    owner_role: OwnerRole
    status: Literal["pending", "blocked", "evidence_recorded"]
    evidence_ids: list[RecordId] = Field(max_length=20)

    @model_validator(mode="after")
    def evidence_state(self):
        _unique(self.evidence_ids, "gate evidence references")
        if self.status == "evidence_recorded" and not self.evidence_ids:
            raise ValueError("Recorded gate evidence requires an evidence reference")
        return self


class ProviderPlan(StrictRecord):
    provider: Provider
    dispatch_enabled: bool
    runtime_qualification: Literal["unqualified"]
    account_configuration: Literal["not_supplied"]
    documentation: list[DocumentationReference] = Field(min_length=1, max_length=3)
    gates: list[QualificationGate] = Field(min_length=12, max_length=12)

    @model_validator(mode="after")
    def disabled_and_complete(self):
        if self.dispatch_enabled:
            raise ValueError("An R01 dossier cannot enable provider dispatch")
        urls = [entry.url for entry in self.documentation]
        _unique(urls, "provider documentation URLs")
        if not set(urls).issubset(OFFICIAL_DOCUMENTATION[self.provider]):
            raise ValueError("Documentation must use registered official reference URLs")
        gates = [entry.gate for entry in self.gates]
        _unique(gates, "provider gates")
        if set(gates) != GATES:
            raise ValueError("Every provider requires the complete qualification gate catalog")
        return self


class DatasetPlan(StrictRecord):
    dataset_id: RecordId
    purpose: Literal["development", "held_out_release"]
    target_tasks: Annotated[int, Field(ge=1, le=100_000)]
    target_substantive_claims: Count | None
    practice_task_targets: dict[Practice, Count]
    task_inventory_status: Literal["not_populated", "planning_only"]

    @model_validator(mode="after")
    def separated_samples(self):
        if set(self.practice_task_targets) != PRACTICES:
            raise ValueError("Plan every launch practice explicitly")
        if sum(self.practice_task_targets.values()) != self.target_tasks:
            raise ValueError("Practice targets must sum to the planned task count")
        if self.purpose == "development":
            if self.target_tasks < 360 or min(self.practice_task_targets.values()) < 120:
                raise ValueError("Development planning requires at least 360 tasks and 120 per practice")
        elif self.target_tasks < 1000 or (self.target_substantive_claims or 0) < 3000:
            raise ValueError("Held-out planning retains at least 1000 tasks and 3000 claims")
        if any(value == 0 for value in self.practice_task_targets.values()):
            raise ValueError("Each practice needs planned task coverage")
        return self


class EvaluationSlice(StrictRecord):
    slice_id: RecordId
    category: Slice
    owner_role: OwnerRole
    development_target: Count | None
    held_out_target: Count | None
    provider_ids: list[Provider] = Field(max_length=3)
    minimum_per_provider: Count | None
    sample_size_status: Literal["pending", "planned"]

    @model_validator(mode="after")
    def declared_unknowns(self):
        _unique(self.provider_ids, "slice providers")
        if self.category in PROVIDER_SLICES and set(self.provider_ids) != PROVIDERS:
            raise ValueError("Provider qualification slices must plan all three choices")
        if self.sample_size_status == "planned":
            if not self.development_target or not self.held_out_target:
                raise ValueError("Planned slice sizes require positive development and held-out targets")
            if self.provider_ids and not self.minimum_per_provider:
                raise ValueError("Planned provider slices need an explicit per-provider minimum")
        if not self.provider_ids and self.minimum_per_provider is not None:
            raise ValueError("A per-provider minimum needs a provider scope")
        return self


class PairedComparisonPlan(StrictRecord):
    comparison_id: RecordId
    kind: Comparison
    baseline: Literal["single_pass", "standard", "original_private_local"]
    candidate: Literal["bounded_correction", "deep", "sanitized_scenario_local"]
    same_tasks: bool
    pinned_inputs_and_snapshot: bool
    includes_verification_and_correction_time: bool
    target_pairs: Count | None
    owner_role: OwnerRole

    @model_validator(mode="after")
    def paired_not_uncontrolled(self):
        if (self.baseline, self.candidate) != PAIR_MODES[self.kind]:
            raise ValueError("Comparison modes do not match the declared experiment")
        if not (self.same_tasks and self.pinned_inputs_and_snapshot
                and self.includes_verification_and_correction_time):
            raise ValueError("Paired plans require frozen tasks/inputs and complete preparation timing")
        return self


class EvaluationPlan(StrictRecord):
    development: DatasetPlan
    held_out: DatasetPlan
    split_by_source_proceeding_and_duplicate_family: bool
    independent_annotators: Annotated[int, Field(ge=2, le=10)]
    adjudication_required: bool
    slices: list[EvaluationSlice] = Field(min_length=11, max_length=30)
    comparisons: list[PairedComparisonPlan] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def qualification_design(self):
        if (self.development.purpose, self.held_out.purpose) != ("development", "held_out_release"):
            raise ValueError("Development and held-out plans have different purposes")
        if self.development.dataset_id == self.held_out.dataset_id:
            raise ValueError("Development and held-out inventories must be distinct")
        if not self.split_by_source_proceeding_and_duplicate_family or not self.adjudication_required:
            raise ValueError("Leakage-resistant splitting and adjudication are mandatory")
        _unique([entry.slice_id for entry in self.slices], "evaluation slice identifiers")
        _unique([entry.category for entry in self.slices], "evaluation slice categories")
        if {entry.category for entry in self.slices} != SLICES:
            raise ValueError("All legal, correction, privacy, fidelity and operational slices are required")
        for entry in self.slices:
            if (entry.development_target or 0) > self.development.target_tasks:
                raise ValueError("Slice exceeds its development inventory target")
            if (entry.held_out_target or 0) > self.held_out.target_tasks:
                raise ValueError("Slice exceeds its held-out inventory target")
            if entry.provider_ids and entry.minimum_per_provider is not None:
                # The same paired task may exercise each provider; counts need not be disjoint.
                if any(entry.minimum_per_provider > target for target in
                       (entry.development_target, entry.held_out_target) if target is not None):
                    raise ValueError("Provider minimum exceeds its slice target")
        _unique([entry.comparison_id for entry in self.comparisons], "comparison identifiers")
        _unique([entry.kind for entry in self.comparisons], "comparison kinds")
        if {entry.kind for entry in self.comparisons} != set(PAIR_MODES):
            raise ValueError("Correction, Standard/Deep and abstraction comparisons are required")
        if any((entry.target_pairs or 0) > self.development.target_tasks for entry in self.comparisons):
            raise ValueError("Comparison pairs exceed the development task target")
        return self


class CalibrationPlan(StrictRecord):
    target_units: dict[Unit, Count]
    population_denominators: dict[Unit, Count | None]
    practices: list[Practice] = Field(min_length=3, max_length=3)
    owner_role: OwnerRole

    @model_validator(mode="after")
    def explicit_population(self):
        if set(self.target_units) != UNITS or set(self.population_denominators) != UNITS:
            raise ValueError("All calibration units require a target and explicit population denominator")
        if any(self.target_units[unit] < minimum for unit, minimum in
               {"pages": 100, "amendment_chains": 10, "decisions": 30}.items()):
            raise ValueError("Calibration retains the 100-page, 10-chain and 30-decision starting sample")
        _unique(self.practices, "calibration practices")
        if set(self.practices) != PRACTICES:
            raise ValueError("Calibration must span all launch practices")
        return self


class EvidenceRecord(StrictRecord):
    evidence_id: RecordId
    sha256: Digest
    sample_kind: SampleKind
    recorded_on: Day
    owner_role: OwnerRole

    @model_validator(mode="after")
    def valid_day(self):
        _day(self.recorded_on)
        return self


class CalibrationMeasurement(StrictRecord):
    measurement_id: RecordId
    evidence_id: RecordId
    sample_kind: SampleKind
    practice: Practice
    unit: Unit
    observed_units: Annotated[int, Field(ge=1, le=1_000_000)]
    elapsed_seconds: Seconds | None
    reviewer_seconds: Seconds | None
    assessed_items: Count | None
    disagreements: Count | None

    @model_validator(mode="after")
    def disagreement_denominator(self):
        if self.assessed_items is None and self.disagreements is not None:
            raise ValueError("Disagreements require an explicit assessed-item denominator")
        if self.disagreements is not None and self.disagreements > self.assessed_items:
            raise ValueError("Disagreements cannot exceed assessed items")
        return self


class CapacityPlan(StrictRecord):
    status: Literal["provisional"]
    baseline_weeks_min: Annotated[int, Field(ge=1, le=260)]
    baseline_weeks_max: Annotated[int, Field(ge=1, le=260)]
    baseline_fte: Annotated[float, Field(gt=0, le=100)]
    reestimate_owner_role: OwnerRole
    added_workstreams: list[Literal[
        "local_analysis", "sanitizer_fidelity", "provider_adapters", "evaluation", "operations",
    ]] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def bounded_envelope(self):
        if self.baseline_weeks_min > self.baseline_weeks_max:
            raise ValueError("Planning interval is reversed")
        _unique(self.added_workstreams, "capacity workstreams")
        return self


class ResearchDossier(StrictRecord):
    schema_version: Literal["research-qualification-v1"]
    dossier_id: RecordId
    recorded_on: Day
    owner_role: OwnerRole
    providers: list[ProviderPlan] = Field(min_length=3, max_length=3)
    evaluation: EvaluationPlan
    calibration_plan: CalibrationPlan
    evidence_records: list[EvidenceRecord] = Field(max_length=2000)
    measurements: list[CalibrationMeasurement] = Field(max_length=2000)
    capacity: CapacityPlan

    @model_validator(mode="after")
    def references_and_dates(self):
        recorded = _day(self.recorded_on)
        _unique([entry.provider for entry in self.providers], "providers")
        if {entry.provider for entry in self.providers} != PROVIDERS:
            raise ValueError("All three planned provider choices must remain explicit")
        _unique([entry.evidence_id for entry in self.evidence_records], "evidence identifiers")
        _unique([entry.sha256 for entry in self.evidence_records], "evidence digests")
        _unique([entry.measurement_id for entry in self.measurements], "measurement identifiers")
        _unique([entry.evidence_id for entry in self.measurements], "measurement evidence references")
        evidence = {entry.evidence_id: entry for entry in self.evidence_records}
        if any(_day(entry.recorded_on) > recorded for entry in self.evidence_records):
            raise ValueError("Evidence cannot postdate the dossier record")
        for provider in self.providers:
            if any(_day(entry.checked_on) > recorded for entry in provider.documentation):
                raise ValueError("Documentation checks cannot postdate the dossier")
            for gate in provider.gates:
                if any(reference not in evidence for reference in gate.evidence_ids):
                    raise ValueError("Unknown provider-gate evidence reference")
        for measurement in self.measurements:
            support = evidence.get(measurement.evidence_id)
            if support is None:
                raise ValueError("Unknown calibration evidence reference")
            if support.sample_kind != measurement.sample_kind:
                raise ValueError("Measurement and evidence real/synthetic classification disagree")
        for unit, denominator in self.calibration_plan.population_denominators.items():
            observed = sum(entry.observed_units for entry in self.measurements
                           if entry.unit == unit and entry.sample_kind == "real")
            if denominator is not None and observed > denominator:
                raise ValueError("Real samples exceed the declared population denominator")
        return self


def _calibration_summary(dossier: ResearchDossier, kind: SampleKind) -> dict:
    selected = [entry for entry in dossier.measurements if entry.sample_kind == kind]
    units = {}
    for unit in sorted(UNITS):
        samples = [entry for entry in selected if entry.unit == unit]
        observed = sum(entry.observed_units for entry in samples)
        elapsed = (sum(entry.elapsed_seconds for entry in samples)
                   if samples and all(entry.elapsed_seconds is not None for entry in samples) else None)
        reviewer = (sum(entry.reviewer_seconds for entry in samples)
                    if samples and all(entry.reviewer_seconds is not None for entry in samples) else None)
        population = dossier.calibration_plan.population_denominators[unit] if kind == "real" else None
        units[unit] = {
            "measurement_count": len(samples), "observed_units": observed,
            "population_denominator": population,
            "population_fraction": observed / population if population else None,
            "elapsed_seconds": elapsed, "reviewer_seconds": reviewer,
            "elapsed_seconds_per_unit": elapsed / observed if observed and elapsed is not None else None,
            "reviewer_seconds_per_unit": reviewer / observed if observed and reviewer is not None else None,
            "untimed_measurements": sum(entry.elapsed_seconds is None for entry in samples),
            "unreviewed_timing_measurements": sum(entry.reviewer_seconds is None for entry in samples),
        }
    assessed = (sum(entry.assessed_items for entry in selected)
                if selected and all(entry.assessed_items is not None for entry in selected) else None)
    disagreement = (sum(entry.disagreements for entry in selected)
                    if selected and all(entry.disagreements is not None for entry in selected) else None)
    return {
        "measurement_count": len(selected), "units": units,
        "practices_observed": sorted({entry.practice for entry in selected}),
        "assessed_items": assessed, "disagreements": disagreement,
        "disagreement_fraction": disagreement / assessed if assessed and disagreement is not None else None,
    }


def summarize_research_dossier(dossier: ResearchDossier) -> dict:
    """Return metadata-only planning aggregates, never credentials, quotes or permissions."""
    # Revalidate even an instance created via model_construct or mutated nested collections.
    dossier = ResearchDossier.model_validate(dossier.model_dump())
    real = _calibration_summary(dossier, "real")
    synthetic = _calibration_summary(dossier, "synthetic")
    return {
        "schema_version": dossier.schema_version,
        "record_kind": "offline_qualification_plan",
        "production_qualified": False,
        "external_dispatch_authorized": False,
        "evidence_authenticated": False,
        "provider_plans": [
            {
                "provider": entry.provider, "dispatch_enabled": False,
                "runtime_qualification": "unqualified", "account_configuration": "not_supplied",
                "documentary_reference_count": len(entry.documentation),
                "gate_counts": {status: sum(gate.status == status for gate in entry.gates)
                                for status in ("pending", "blocked", "evidence_recorded")},
            } for entry in dossier.providers
        ],
        "evaluation": {
            "development_target_tasks": dossier.evaluation.development.target_tasks,
            "held_out_target_tasks": dossier.evaluation.held_out.target_tasks,
            "held_out_target_substantive_claims": dossier.evaluation.held_out.target_substantive_claims,
            "separate_inventories": True, "observed_task_results": None,
            "planned_slice_count": len(dossier.evaluation.slices),
            "slice_sample_size_counts": dict(Counter(entry.sample_size_status
                                                     for entry in dossier.evaluation.slices)),
            "unknown_provider_sample_minima": sum(bool(entry.provider_ids) and
                                                  entry.minimum_per_provider is None
                                                  for entry in dossier.evaluation.slices),
            "comparison_plans": sorted(entry.kind for entry in dossier.evaluation.comparisons),
            "unknown_comparison_pair_counts": sum(entry.target_pairs is None
                                                  for entry in dossier.evaluation.comparisons),
        },
        "calibration": {
            "real": real, "synthetic": synthetic,
            "planned_real_units": dict(dossier.calibration_plan.target_units),
            "real_sample_count_targets_met": all(real["units"][unit]["observed_units"] >= target
                                                 for unit, target in dossier.calibration_plan.target_units.items()),
            "all_launch_practices_observed_in_real_samples": set(real["practices_observed"]) == PRACTICES,
        },
        "capacity": {
            "status": "provisional",
            "baseline_weeks": [dossier.capacity.baseline_weeks_min, dossier.capacity.baseline_weeks_max],
            "baseline_fte": dossier.capacity.baseline_fte,
            "measured_delivery_estimate_weeks": None,
            "real_timing_measurements": sum(entry.sample_kind == "real" and
                                            entry.elapsed_seconds is not None and
                                            entry.reviewer_seconds is not None for entry in dossier.measurements),
            "reestimate_required": True,
        },
        "limitations": [
            "Documentary references do not verify an account, entitlement, retention arrangement or billing readiness.",
            "Evidence digests and real/synthetic labels are supplied records, not authenticated legal or privacy approvals.",
            "Synthetic measurements never count toward real calibration throughput or population coverage.",
            "Targets and paired experiment plans are not observed evaluation results or production qualification.",
            "Unknown denominators and missing timings remain unknown; samples do not establish corpus completeness.",
            "The staffing/calendar envelope needs human re-estimation including analysis, privacy, providers and operations.",
        ],
    }
