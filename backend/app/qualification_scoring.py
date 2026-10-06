"""Offline scoring of supplied adjudications; no provider access or approval.

A digest binds declared evidence, not its truth or independent legal review.
Protocols may retain unknown sample minima; those gates then remain unpassed.
"""

import hashlib
import json
from collections import Counter
from datetime import datetime
from statistics import median
from typing import Literal

from pydantic import Field, model_validator

from .evaluation import TaskScore, evaluate_release, fraction
from .research_qualification import Digest, Practice, Provider, RecordId, StrictRecord

LOCAL_SLICES = {
    "citation_temporal": {"correct_version", "correct_institution", "transition_basis"},
    "adverse_authority": {"independent_adverse_search", "material_fact_comparison"},
    "evidence_roles": {"allegation_finding_separated", "majority_dissent_separated"},
    "correction": {"bounded_revision", "evidence_driven_repair", "critical_defects_withheld"},
    "standard_deep": {"bounded_depth", "same_tool_permissions"},
    "disconnected_operations": {"no_external_traffic", "cancellation_timeout", "revocation",
                                "partial_output_outage", "retention_deletion", "five_job_contention",
                                "matter_isolation", "source_rights", "export_authorization"},
}
CONNECTED_SLICES = {
    "privacy_direct": {"turkish_identifiers", "ocr_encoded_identifiers", "documents_and_secrets"},
    "privacy_contextual": {"rare_fact_combinations", "cumulative_disclosure"},
    "legal_fidelity": {"facts_dates_thresholds", "roles_and_uncertainty", "issues_and_authorities"},
    "key_authorization_spend": {"cross_user_key_isolation", "exact_approval", "replay_retry",
                                "revoked_access", "spend_bounds", "allowed_tools", "no_hidden_fallback"},
    "returned_evidence": {"original_citations", "exact_passage_version", "source_roles",
                          "injection_rejection", "unavailable_originals_explicit"},
}
PAIR_MODES = {"correction": ("single_pass", "bounded_correction"),
              "standard_deep": ("standard", "deep"),
              "privacy_fidelity": ("original_private_local", "sanitized_scenario_local")}
METRIC_DENOMINATORS = {"retrieval_tasks", "exact_identifier_tasks", "abstention_tasks", "answerable_tasks",
                       "sensitive_tasks", "timed_tasks_including_verification"}
SNAPSHOT_KEYS = {"ontology", "graphs", "corpus", "model", "policy", "index", "workflow"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Evaluation timestamps require a timezone")
    return parsed


def unique(values):
    if len(values) != len(set(values)):
        raise ValueError("Repeated evaluation identities are not independent evidence")


class Protocol(StrictRecord):
    schema_version: Literal["legal-evaluation-protocol-v1"]
    protocol_id: RecordId
    registered_at: str = Field(min_length=1, max_length=80)
    mode: Literal["local", "connected"]
    provider: Provider | None
    provider_configuration_sha256: Digest | None
    snapshot_sha256: Digest
    rubric_sha256: Digest
    task_target: int = Field(ge=1000, le=100_000)
    claim_target: int = Field(ge=3000, le=1_000_000)
    practice_minimums: dict[Practice, int | None]
    slice_minimums: dict[str, int | None]
    pair_minimums: dict[str, int | None]
    metric_minimums: dict[str, int | None]
    independent_family_minimum: int | None = Field(ge=1, le=100_000)
    development_family_sha256: list[Digest] = Field(max_length=100_000)

    @model_validator(mode="after")
    def complete_scope(self):
        instant(self.registered_at)
        if (self.mode == "local") != (self.provider is None and self.provider_configuration_sha256 is None):
            raise ValueError("Local and provider-specific evaluation scopes are separate")
        if self.mode == "connected" and (self.provider is None or self.provider_configuration_sha256 is None):
            raise ValueError("Connected scoring requires one exact provider configuration")
        slices = set(LOCAL_SLICES) | (set(CONNECTED_SLICES) if self.mode == "connected" else set())
        pairs = {"correction", "standard_deep"} | ({"privacy_fidelity"} if self.mode == "connected" else set())
        if (set(self.metric_minimums) != METRIC_DENOMINATORS or set(self.slice_minimums) != slices or set(self.pair_minimums) != pairs
                or set(self.practice_minimums) != {"contracts", "commercial", "employment"}):
            raise ValueError("All mandatory scope-specific sample minima must be declared")
        for mapping in (self.practice_minimums, self.slice_minimums, self.pair_minimums, self.metric_minimums):
            if any(value is not None and (type(value) is not int or not 1 <= value <= self.task_target)
                   for value in mapping.values()):
                raise ValueError("Sample minima must be positive bounded integers or explicitly unknown")
        if sum(value or 0 for value in self.practice_minimums.values()) > self.task_target:
            raise ValueError("Practice minima exceed the task target")
        unique(self.development_family_sha256)
        return self


class AnalysisScore(StrictRecord):
    consequential_steps: int = Field(ge=0, le=1000)
    grounded_steps: int = Field(ge=0, le=1000)
    critical_unsupported_inferences: int = Field(ge=0, le=1000)
    critical_fact_substitutions: int = Field(ge=0, le=1000)
    critical_omissions: int = Field(ge=0, le=1000)
    critical_role_errors: int = Field(ge=0, le=1000)
    gold_adverse_authorities: list[RecordId] = Field(max_length=1000)
    retrieved_adverse_authorities: list[RecordId] = Field(max_length=20)

    @model_validator(mode="after")
    def bounds(self):
        if self.grounded_steps > self.consequential_steps:
            raise ValueError("Grounded steps exceed assessed steps")
        unique(self.gold_adverse_authorities)
        unique(self.retrieved_adverse_authorities)
        return self


class Trial(StrictRecord):
    mode: Literal["single_pass", "bounded_correction", "standard", "deep", "original_private_local", "sanitized_scenario_local"]
    task_input_sha256: Digest
    snapshot_sha256: Digest
    substantive_claims: int = Field(ge=1, le=10000)
    supported_claims: int = Field(ge=0, le=10000)
    claims_with_resolvable_citations: int = Field(ge=0, le=10000)
    adverse_found: list[RecordId] = Field(max_length=20)
    argument_quality: float = Field(ge=0, le=1)
    critical_errors: int = Field(ge=0, le=10000)
    elapsed_seconds: float = Field(ge=0, le=1e9)
    compute_seconds: float = Field(ge=0, le=1e9)
    external_cost_usd: float = Field(ge=0, le=1e9)
    preparation_seconds: float = Field(gt=0, le=1e9)
    review_seconds: float = Field(ge=0, le=1e9)
    verification_and_correction_included: bool

    @model_validator(mode="after")
    def coherent_counts(self):
        if (max(self.supported_claims, self.claims_with_resolvable_citations) > self.substantive_claims
                or self.review_seconds > self.preparation_seconds):
            raise ValueError("Invalid paired denominators or time accounting")
        unique(self.adverse_found)
        return self


class Pair(StrictRecord):
    kind: Literal["correction", "standard_deep", "privacy_fidelity"]
    baseline: Trial
    candidate: Trial
    seeded_defects: int = Field(ge=0, le=10000)
    repaired_with_evidence: int = Field(ge=0, le=10000)
    explicitly_withheld: int = Field(ge=0, le=10000)
    unresolved_defects: int = Field(ge=0, le=10000)
    introduced_regressions: int = Field(ge=0, le=10000)

    @model_validator(mode="after")
    def paired_modes(self):
        if (self.baseline.mode, self.candidate.mode) != PAIR_MODES[self.kind]:
            raise ValueError("Invalid comparison modes")
        if self.repaired_with_evidence + self.explicitly_withheld + self.unresolved_defects != self.seeded_defects:
            raise ValueError("Every seeded defect requires an explicit disposition")
        if self.kind == "correction" and self.seeded_defects == 0:
            raise ValueError("Correction cases need seeded defects")
        if self.kind != "correction" and self.seeded_defects:
            raise ValueError("Defect counts belong to correction comparisons")
        return self


class AdjudicatedTask(StrictRecord):
    schema_version: Literal["legal-evaluation-task-v1"]
    protocol_sha256: Digest
    snapshot_sha256: Digest
    rubric_sha256: Digest
    mode: Literal["local", "connected"]
    provider: Provider | None
    provider_configuration_sha256: Digest | None
    sample_kind: Literal["real", "synthetic"]
    measured_at: str = Field(min_length=1, max_length=80)
    task_input_sha256: Digest
    split_family_sha256: Digest
    adjudication_evidence_sha256: Digest
    annotators: list[RecordId] = Field(min_length=2, max_length=10)
    disagreements_resolved: bool
    score: TaskScore
    analysis: AnalysisScore
    slices: list[str] = Field(max_length=11)
    checks: dict[str, bool | None]
    pairs: list[Pair] = Field(max_length=3)

    @model_validator(mode="after")
    def validate_declared_evidence(self):
        instant(self.measured_at)
        unique(self.annotators)
        unique(self.slices)
        unique([pair.kind for pair in self.pairs])
        if self.score.domain not in {"contracts", "commercial", "employment"}:
            raise ValueError("Unknown launch practice")
        catalog = LOCAL_SLICES | (CONNECTED_SLICES if self.mode == "connected" else {})
        if set(self.slices) - set(catalog):
            raise ValueError("Unknown or out-of-scope evaluation slice")
        permitted_checks = set().union(*(catalog[name] for name in self.slices))
        if set(self.checks) - permitted_checks:
            raise ValueError("Checks must belong to the declared slices")
        expected_pairs = set(self.slices) & {"correction", "standard_deep"}
        if "legal_fidelity" in self.slices:
            expected_pairs.add("privacy_fidelity")
        if {pair.kind for pair in self.pairs} != expected_pairs:
            raise ValueError("Comparison slices require the matching paired observations")
        for pair in self.pairs:
            for trial in (pair.baseline, pair.candidate):
                if trial.task_input_sha256 != self.task_input_sha256 or trial.snapshot_sha256 != self.snapshot_sha256:
                    raise ValueError("Paired runs must use the same frozen task and snapshot")
                if (self.mode == "local" or pair.kind == "privacy_fidelity") and trial.external_cost_usd:
                    raise ValueError("Local trials cannot incur external research charges")
                if set(trial.adverse_found) - set(self.analysis.gold_adverse_authorities):
                    raise ValueError("Adverse successes must be in the adjudicated gold set")
        return self


def _pairs_report(rows, kind):
    observations = [(row, pair) for row in rows for pair in row.pairs if pair.kind == kind]
    regressions, gains = 0, 0
    deltas = {name: [] for name in ("claim_support", "citation_resolvability", "adverse_recall", "argument_quality", "elapsed_seconds",
                                   "compute_seconds", "external_cost_usd", "preparation_seconds", "review_seconds")}
    for row, pair in observations:
        before, after = pair.baseline, pair.candidate
        support = after.supported_claims / after.substantive_claims - before.supported_claims / before.substantive_claims
        citations = after.claims_with_resolvable_citations / after.substantive_claims - before.claims_with_resolvable_citations / before.substantive_claims
        adverse = ((len(after.adverse_found) - len(before.adverse_found)) / len(row.analysis.gold_adverse_authorities)
                   if row.analysis.gold_adverse_authorities else None)
        quality = after.argument_quality - before.argument_quality
        regression = support < 0 or citations < 0 or (adverse is not None and adverse < 0) or quality < 0 or after.critical_errors > 0 or pair.introduced_regressions > 0
        regressions += regression
        gains += not regression and (support > 0 or citations > 0 or (adverse is not None and adverse > 0) or quality > 0)
        for name, value in (("claim_support", support), ("citation_resolvability", citations), ("adverse_recall", adverse), ("argument_quality", quality)):
            if value is not None:
                deltas[name].append(value)
        for name in set(deltas) - {"claim_support", "citation_resolvability", "adverse_recall", "argument_quality"}:
            deltas[name].append(getattr(after, name) - getattr(before, name))
    return {"pairs": len(observations), "candidate_quality_floor_met": bool(observations) and all(
                pair.candidate.supported_claims / pair.candidate.substantive_claims >= 0.999
                and pair.candidate.claims_with_resolvable_citations == pair.candidate.substantive_claims
                and bool(row.analysis.gold_adverse_authorities)
                and len(pair.candidate.adverse_found) / len(row.analysis.gold_adverse_authorities) >= 0.95
                for row, pair in observations), "regressing_pairs": regressions, "improved_pairs_without_regression": gains,
            "introduced_regressions": sum(pair.introduced_regressions for _, pair in observations),
            "unresolved_defects": sum(pair.unresolved_defects for _, pair in observations),
            "repaired_with_evidence": sum(pair.repaired_with_evidence for _, pair in observations),
            "explicitly_withheld": sum(pair.explicitly_withheld for _, pair in observations),
            "complete_time_accounting": bool(observations) and all(
                pair.baseline.verification_and_correction_included and pair.candidate.verification_and_correction_included
                for _, pair in observations),
            "median_candidate_minus_baseline": {name: median(values) if values else None for name, values in deltas.items()},
            "statistical_improvement_established": False}


def evaluate_qualification(rows, snapshot, protocol):
    protocol = Protocol.model_validate(protocol)
    if (type(snapshot) is not dict or set(snapshot) != SNAPSHOT_KEYS
            or any(type(value) is not str or not 1 <= len(value) <= 200 or value != value.strip()
                   or any(ord(char) < 32 for char in value) for value in snapshot.values())
            or digest(snapshot) != protocol.snapshot_sha256):
        raise ValueError("Complete frozen evaluation snapshot required")
    protocol_hash = digest(protocol.model_dump(mode="json"))
    if not isinstance(rows, list) or len(rows) > 100_000:
        raise ValueError("Evaluation exceeds bounded task count")
    tasks = [AdjudicatedTask.model_validate(row) for row in rows]
    development_families = set(protocol.development_family_sha256)
    unique([row.score.task_id for row in tasks])
    unique([row.task_input_sha256 for row in tasks])
    for row in tasks:
        if (row.protocol_sha256 != protocol_hash or row.snapshot_sha256 != protocol.snapshot_sha256
                or row.rubric_sha256 != protocol.rubric_sha256 or row.mode != protocol.mode
                or row.provider != protocol.provider or row.provider_configuration_sha256 != protocol.provider_configuration_sha256
                or instant(row.measured_at) < instant(protocol.registered_at)
                or row.split_family_sha256 in development_families):
            raise ValueError("Mixed, unregistered or development-contaminated evaluation evidence")
    core = evaluate_release([row.score.model_dump() for row in tasks], {key: snapshot[key] for key in ("ontology", "graphs", "corpus", "model", "policy")})
    catalog = LOCAL_SLICES | (CONNECTED_SLICES if protocol.mode == "connected" else {})
    slices = {}
    for name, checks in sorted(catalog.items()):
        selected = [row for row in tasks if name in row.slices]
        minimum = protocol.slice_minimums[name]
        slices[name] = {"tasks": len(selected), "minimum": minimum,
                        "checks": {check: {"assessed": sum(row.checks.get(check) is not None for row in selected),
                                           "failed": sum(row.checks.get(check) is False for row in selected)} for check in sorted(checks)}}
        slices[name]["pass"] = bool(minimum and len(selected) >= minimum and all(
            row.checks.get(check) is True for row in selected for check in checks))
        if name == "adverse_authority":
            slices[name]["pass"] = slices[name]["pass"] and all(row.analysis.gold_adverse_authorities for row in selected)
    pairs = {kind: _pairs_report(tasks, kind) for kind in sorted(protocol.pair_minimums)}
    steps = sum(row.analysis.consequential_steps for row in tasks)
    grounded = sum(row.analysis.grounded_steps for row in tasks)
    critical = {field: sum(getattr(row.analysis, field) for row in tasks)
                for field in AnalysisScore.model_fields if field.startswith("critical_")}
    adverse = [len(set(row.analysis.gold_adverse_authorities) & set(row.analysis.retrieved_adverse_authorities)) /
               len(row.analysis.gold_adverse_authorities) for row in tasks if row.analysis.gold_adverse_authorities]
    practices = Counter(row.score.domain for row in tasks)
    gates = {**core["gates"], "task_sample": len(tasks) >= protocol.task_target,
             "claim_sample": core["metrics"]["substantive_claims"] >= protocol.claim_target,
             "real_held_out_evidence": bool(tasks) and all(row.sample_kind == "real" for row in tasks),
             "adjudication_resolved": bool(tasks) and all(row.disagreements_resolved for row in tasks),
             "practice_samples": all(minimum and practices[name] >= minimum for name, minimum in protocol.practice_minimums.items()),
             "family_sample": bool(protocol.independent_family_minimum and len({row.split_family_sha256 for row in tasks}) >= protocol.independent_family_minimum),
             **{"sample_" + name: bool(minimum and core["metrics"][name] >= minimum)
                for name, minimum in protocol.metric_minimums.items()},
             "argument_grounding": steps > 0 and grounded == steps and all(
                 not row.score.answerable or row.analysis.consequential_steps > 0 for row in tasks),
             "zero_critical_analysis_errors": not any(critical.values()),
             "adverse_recall_at_20": bool(adverse) and fraction(adverse) >= 0.95,
             **{"slice_" + name: value["pass"] for name, value in slices.items()}}
    for kind, result in pairs.items():
        minimum = protocol.pair_minimums[kind]
        gates["paired_" + kind] = bool(minimum and result["pairs"] >= minimum and result["complete_time_accounting"]
                                      and result["candidate_quality_floor_met"]
                                      and result["regressing_pairs"] == 0 and result["unresolved_defects"] == 0)
    return {"schema_version": "legal-evaluation-report-v1", "mode": protocol.mode, "provider": protocol.provider,
            "protocol_sha256": protocol_hash, "snapshot_sha256": protocol.snapshot_sha256,
            "provider_configuration_sha256": protocol.provider_configuration_sha256,
            "core_metrics": core["metrics"], "core_thresholds": core["thresholds"],
            "core_by_practice": core["breakdown"]["domain"],
            "analysis": {"consequential_steps": steps, "grounded_steps": grounded, **critical,
                         "adverse_recall_at_20": fraction(adverse), "adverse_tasks": len(adverse)},
            "sample_kinds": dict(Counter(row.sample_kind for row in tasks)),
            "practices": {name: practices[name] for name in sorted(protocol.practice_minimums)},
            "slices": slices, "paired_comparisons": pairs, "gates": gates,
            "quantitative_gates_pass": all(gates.values()), "production_qualified": False,
            "runtime_authorization": "none", "limitations": [
                "Supplied judgments, timestamps, split families and digests are not authenticated legal evidence.",
                "Sample minima need independent prior approval; passing counts does not prove representativeness.",
                "Paired medians are descriptive, not a statistical or causal improvement claim.",
                "A connected result covers only its declared provider/configuration; other providers are not qualified.",
                "Operational, legal, privacy, provider-readiness and customer acceptance remain independent."]}
