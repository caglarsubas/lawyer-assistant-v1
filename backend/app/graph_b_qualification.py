"""Explicit, evidenced historical identity assessments; no inferred court powers."""
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import HTTPException
from pydantic import Field, field_validator, model_validator

from . import decision_equivalence as equivalence
from .source_reviews import StrictInput

RELATIONS = ("decidedIn", "issuedBy", "hasDecisionVersion")


def day(value):
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        raise ValueError("An exact calendar date is required")
    return date.fromisoformat(value)


class TemporalAssessment(StrictInput):
    end_status: Literal["unknown", "closed", "open_ended"]
    valid_from: str | None = Field(max_length=10)
    valid_until: str | None = Field(max_length=10)
    checked_through: str | None = Field(max_length=10)
    evidence: list[equivalence.Proof] = Field(max_length=30)
    rationale: str = Field(min_length=3, max_length=4000)

    @field_validator("valid_from", "valid_until", "checked_through")
    @classmethod
    def exact_date(cls, value):
        if value is not None:
            day(value)
        return value

    @model_validator(mode="after")
    def explicit_bounds(self):
        if self.end_status == "unknown":
            if any(value is not None for value in (self.valid_from, self.valid_until, self.checked_through)):
                raise ValueError("Unknown temporal applicability cannot carry invented bounds")
        else:
            if not self.valid_from or not self.evidence:
                raise ValueError("Known applicability needs a start and physical evidence")
            if self.end_status == "closed":
                if not self.valid_until or self.checked_through is not None or day(self.valid_until) <= day(self.valid_from):
                    raise ValueError("Closed intervals are nonempty and end-exclusive")
            elif self.valid_until is not None or not self.checked_through or day(self.checked_through) < day(self.valid_from):
                raise ValueError("Open intervals require an explicit checked-through horizon")
        if len({(p.source_id, p.passage_id) for p in self.evidence}) != len(self.evidence):
            raise ValueError("Duplicate temporal evidence")
        return self

    def covers(self, value):
        return bool(self.end_status != "unknown" and day(self.valid_from) <= value and (
            value < day(self.valid_until) if self.end_status == "closed" else value <= day(self.checked_through)))


class RelationAssessment(TemporalAssessment):
    source_id: equivalence.SOURCE_ID
    relation: Literal["decidedIn", "issuedBy", "hasDecisionVersion"]


class InstitutionAssessment(StrictInput):
    institution_id: str = Field(pattern="^" + equivalence.identities.ID % "institution" + "$")
    registered_name: str = Field(min_length=3, max_length=300)
    register_record_id: str = Field(min_length=3, max_length=300)
    scope: Literal["historical_identity_only"]
    identity_window: TemporalAssessment


class Qualifications(StrictInput):
    decision_on: str = Field(min_length=10, max_length=10)
    decision_date_evidence: list[equivalence.Proof] = Field(min_length=2, max_length=20)
    institution: InstitutionAssessment
    relations: list[RelationAssessment] = Field(min_length=6, max_length=6)

    @field_validator("decision_on")
    @classmethod
    def exact_date(cls, value):
        day(value)
        return value


class ReviewerAppointment(StrictInput):
    scope: Literal["TR_decision_identity_institution_temporal_review"]
    valid_from: str = Field(min_length=10, max_length=10)
    valid_until: str = Field(min_length=10, max_length=10)
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    statement: str = Field(min_length=3, max_length=4000)

    @model_validator(mode="after")
    def interval(self):
        if day(self.valid_until) <= day(self.valid_from):
            raise ValueError("Reviewer appointment requires a nonempty interval")
        return self


def resolve(proofs, packages, bound, allowed):
    for proof in proofs:
        package = packages.get(proof.source_id)
        passage = next((p for p in package.locators.passages if p.id == proof.passage_id), None) if package else None
        if (proof.source_id not in allowed or passage is None or passage.text_sha256 != proof.sha256
                or passage.id not in bound["sources"][proof.source_id]["reviewed_passage_ids"]):
            raise HTTPException(409, "Qualification evidence must resolve to accepted passages in its designated source")


def validate_qualifications(value, packages, bound, decision_ids, register_id, claims, reviewed_at):
    qualified = Qualifications.model_validate(value)
    timestamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp > datetime.now(timezone.utc):
        raise HTTPException(409, "A nonfuture review timestamp with timezone is required")
    cutoff = timestamp.astimezone(timezone.utc).date()
    decision_date = day(qualified.decision_on)
    if decision_date > cutoff:
        raise HTTPException(409, "A future decision date cannot be approved")
    resolve(qualified.decision_date_evidence, packages, bound, set(decision_ids))
    if {p.source_id for p in qualified.decision_date_evidence} != set(decision_ids):
        raise HTTPException(409, "Both decision representations must support the explicit decision date")
    institution = qualified.institution
    if (institution.institution_id != claims["institution_id"] or institution.registered_name != claims["registered_name"]
            or institution.register_record_id != claims["register_record_id"]
            or not institution.identity_window.covers(decision_date)):
        raise HTTPException(409, "The register identity assessment must match the reviewed institution and cover the decision date")
    resolve(institution.identity_window.evidence, packages, bound, {register_id})
    expected = {(source, relation) for source in decision_ids for relation in RELATIONS}
    if {(entry.source_id, entry.relation) for entry in qualified.relations} != expected:
        raise HTTPException(409, "All six source-specific relationships need explicit separate temporal assessments")
    for entry in [institution.identity_window, *qualified.relations]:
        if entry.checked_through is not None and day(entry.checked_through) > cutoff:
            raise HTTPException(409, "A future checking horizon is not evidence of current verification")
    for entry in qualified.relations:
        allowed = {entry.source_id, register_id} if entry.relation == "issuedBy" else {entry.source_id}
        resolve(entry.evidence, packages, bound, allowed)
        if entry.end_status != "unknown" and entry.source_id not in {p.source_id for p in entry.evidence}:
            raise HTTPException(409, "Known relationship applicability needs evidence from its own decision source")
        if entry.relation == "issuedBy" and entry.end_status != "unknown":
            if register_id not in {p.source_id for p in entry.evidence} or not entry.covers(decision_date):
                raise HTTPException(409, "Known issuing identity needs separate register evidence and must cover the decision date")
    # An institutional identity window is never copied into the other relations.
    # It is not establishment, activation, abolition, competence or finality.
    return qualified.model_dump()
