"""Score lawyer-adjudicated, held-out release evidence; never manufacture judgments."""

from collections import defaultdict
from statistics import median

from pydantic import BaseModel, ConfigDict, Field


class ClaimScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supported: bool
    citation_resolves: bool


class TaskScore(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    task_id: str = Field(min_length=1)
    adjudicator: str = Field(min_length=1)
    held_out: bool
    domain: str = Field(min_length=1)
    period: str = Field(min_length=1)
    relationship_types: list[str]
    claims: list[ClaimScore]
    critical_errors: int = Field(ge=0)
    answerable: bool
    satisfactory: bool
    appropriate_abstention: bool | None = None
    gold_authorities: list[str] = Field(default_factory=list)
    retrieved_authorities: list[str] = Field(default_factory=list, max_length=20)
    exact_identifier_success: bool | None = None
    legitimate_sensitive_task_passed: bool | None = None
    baseline_seconds: float | None = Field(default=None, gt=0)
    assisted_seconds: float | None = Field(default=None, ge=0)
    verification_and_correction_included: bool = False


def fraction(values):
    return sum(values) / len(values) if values else None


def metrics(tasks):
    claims = [claim for task in tasks for claim in task.claims]
    recalls = [
        len(set(t.gold_authorities) & set(t.retrieved_authorities)) / len(set(t.gold_authorities))
        for t in tasks
        if t.gold_authorities
    ]
    timings = [
        1 - t.assisted_seconds / t.baseline_seconds
        for t in tasks
        if t.baseline_seconds is not None
        and t.assisted_seconds is not None
        and t.verification_and_correction_included
    ]
    return {
        "tasks": len(tasks),
        "substantive_claims": len(claims),
        "critical_errors": sum(t.critical_errors for t in tasks),
        "citation_resolvability": fraction([c.citation_resolves for c in claims]),
        "claim_support": fraction([c.supported for c in claims]),
        "recall_at_20": fraction(recalls),
        "retrieval_tasks": len(recalls),
        "exact_identifier_retrieval": fraction(
            [t.exact_identifier_success for t in tasks if t.exact_identifier_success is not None]
        ),
        "appropriate_abstention": fraction(
            [t.appropriate_abstention is True for t in tasks if not t.answerable]
        ),
        "satisfactory_completion": fraction([t.satisfactory for t in tasks if t.answerable]),
        "legitimate_sensitive_passage": fraction(
            [
                t.legitimate_sensitive_task_passed
                for t in tasks
                if t.legitimate_sensitive_task_passed is not None
            ]
        ),
        "median_preparation_time_reduction": median(timings) if timings else None,
        "timed_tasks_including_verification": len(timings),
    }


def evaluate_release(rows, snapshot):
    tasks = [TaskScore.model_validate(row) for row in rows]
    if len({t.task_id for t in tasks}) != len(tasks):
        raise ValueError("Duplicate task identifiers are not independent evidence")
    if any(not t.held_out for t in tasks):
        raise ValueError("Release scoring requires held-out tasks")
    if not all(snapshot.get(key) for key in ("ontology", "graphs", "corpus", "model", "policy")):
        raise ValueError("Complete evaluation snapshot identifiers are required")
    result = metrics(tasks)
    requirements = {
        "citation_resolvability": 1,
        "claim_support": 0.999,
        "recall_at_20": 0.95,
        "exact_identifier_retrieval": 0.99,
        "appropriate_abstention": 0.95,
        "satisfactory_completion": 0.8,
        "legitimate_sensitive_passage": 0.98,
        "median_preparation_time_reduction": 0.3,
    }
    gates = {
        key: result[key] is not None and result[key] >= threshold for key, threshold in requirements.items()
    }
    gates.update(
        task_sample=len(tasks) >= 1000,
        claim_sample=result["substantive_claims"] >= 3000,
        zero_critical_errors=result["critical_errors"] == 0,
    )
    breakdown = {}
    for name in ("domain", "period", "relationship_types"):
        buckets = defaultdict(list)
        for task in tasks:
            for key in task.relationship_types if name == "relationship_types" else [getattr(task, name)]:
                buckets[key].append(task)
        breakdown[name] = {key: metrics(value) for key, value in buckets.items()}
    return {
        "snapshot": snapshot,
        "metrics": result,
        "thresholds": requirements,
        "gates": gates,
        "quantitative_gates_pass": all(gates.values()),
        "breakdown": breakdown,
        "production_qualified": False,
        "limitations": [
            "Observed metrics are not a universal negligible-error guarantee.",
            "Adjudicator qualification, sample representativeness, source rights and statistical confidence require separate review.",
            "Legal, graph, confidentiality, operational and pilot gates remain independent.",
        ],
    }
