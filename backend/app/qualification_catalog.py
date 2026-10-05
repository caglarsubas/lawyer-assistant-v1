"""Offline R01 planning catalogs. No observation here authorizes acquisition or publication.

These models deliberately do not import application configuration, credentials, database,
network clients or the live review/publication contracts. A reported review remains an
unverified planning observation; the existing authenticated and signed pathways apply.
"""

import ipaddress
import re
from collections import Counter
from datetime import date
from typing import Annotated, Literal
from urllib.parse import unquote, urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator


def _clean(value):
    if value != value.strip() or any(ord(char) < 32 for char in value):
        raise ValueError("Catalog text must be trimmed and contain no control characters")
    return value


Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,79}$"), AfterValidator(_clean)]
Text = Annotated[str, Field(min_length=1, max_length=2000), AfterValidator(_clean)]
ReferenceIds = Annotated[list[Identifier], Field(max_length=40)]
OwnerRole = Literal["source_lead", "legal_editor", "ontology_owner", "security_owner",
                    "platform_engineer", "retrieval_engineer", "data_steward"]
Use = Literal["storage", "local_processing", "internal_display", "indexing", "local_inference",
              "export", "embedding", "offline_distribution", "external_research", "training"]
USES = frozenset({"storage", "local_processing", "internal_display", "indexing", "local_inference",
                  "export", "embedding", "offline_distribution", "external_research", "training"})


def _unique(values, label):
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label}")


def _links(values, known):
    if not set(values).issubset(known):
        raise ValueError("Dangling catalog reference")


def _date(value):
    if value is not None:
        if date.fromisoformat(value).isoformat() != value or date.fromisoformat(value) > date.today():
            raise ValueError("Review date must be a past or current YYYY-MM-DD date")
    return value


def _public_url(value):
    decoded = unquote(value)
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid public reference URL") from None
    if (parsed.scheme != "https" or not host or parsed.username or parsed.password
            or parsed.query or parsed.fragment or port not in (None, 443)
            or any(ord(c) < 33 or ord(c) > 126 for c in value) or any(ord(c) < 33 for c in decoded)
            or "%25" in value.lower()
            or "\\" in decoded or "?" in decoded or "#" in decoded or "@" in decoded
            or not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host) or "." not in host
            or any(not part or len(part) > 63 or part.startswith("-") or part.endswith("-") for part in host.split("."))
            or host.split(".")[-1].isdigit()
            or host.endswith((".local", ".localhost", ".internal", ".invalid", ".test", ".example"))
            or host in {"example.com", "example.org", "example.net"}
            or re.search(r"(?i)(?:api[-_]?key|access[-_]?token|password|secret|credential|bearer)[=/]", decoded)
            or re.search(r"(?:sk-|ghp_|AIza)[A-Za-z0-9_-]{10,}", decoded)):
        raise ValueError("A public credential-free HTTPS reference without query or fragment is required")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return value
    raise ValueError("IP address reference URLs are not admitted")


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*", mode="before")
    @classmethod
    def clean_strings(cls, value):
        if isinstance(value, str):
            return _clean(value)
        return value


class Reference(CatalogModel):
    id: Identifier
    kind: Literal["candidate_url", "repository_document"]
    locator: Text
    description: Text
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None

    @model_validator(mode="after")
    def safe_locator(self):
        if self.kind == "candidate_url":
            _public_url(self.locator)
        elif (not re.fullmatch(r"docs/[A-Za-z0-9_./-]+\.md(?:#[a-z0-9_-]+)?", self.locator)
              or any(not part or part.startswith(".") for part in self.locator.split("/"))):
            raise ValueError("A repository-relative documentation reference is required")
        return self


class Observation(CatalogModel):
    """Self-reported metadata only; never accepted by the live review/publication APIs."""

    reviewer_id: Identifier | None
    reviewed_on: Annotated[str, Field(min_length=10, max_length=10)] | None
    evidence_reference_ids: ReferenceIds
    rationale: Text

    @field_validator("reviewed_on")
    @classmethod
    def review_date(cls, value):
        return _date(value)

    def validate_observation(self, pending):
        _unique(self.evidence_reference_ids, "evidence references")
        if pending:
            if self.reviewer_id is not None or self.reviewed_on is not None or self.evidence_reference_ids:
                raise ValueError("Pending observations cannot claim a reviewer, review date or review evidence")
        elif self.reviewer_id is None or self.reviewed_on is None or not self.evidence_reference_ids:
            raise ValueError("Reported decisions require reviewer, date and evidence references")


class UseObservation(Observation):
    status: Literal["pending", "blocked", "permitted"]

    @model_validator(mode="after")
    def coherent(self):
        self.validate_observation(self.status == "pending")
        return self


class ReviewObservation(Observation):
    status: Literal["pending", "reported_reviewed", "reported_disputed", "reported_rejected"]

    @model_validator(mode="after")
    def coherent(self):
        self.validate_observation(self.status == "pending")
        return self


class Candidate(CatalogModel):
    id: Identifier
    label: Annotated[str, Field(min_length=1, max_length=200)]
    owner_roles: Annotated[list[OwnerRole], Field(min_length=1, max_length=7)]
    reference_ids: Annotated[list[Identifier], Field(min_length=1, max_length=40)]
    use_observations: dict[Use, UseObservation]
    qualification_gaps: Annotated[list[Text], Field(min_length=1, max_length=30)]

    @model_validator(mode="after")
    def coherent_candidate(self):
        _unique(self.owner_roles, "owner roles")
        _unique(self.reference_ids, "candidate references")
        if set(self.use_observations) != USES:
            raise ValueError("Every catalog use must have exactly one observation")
        return self

    def all_reference_ids(self):
        return [*self.reference_ids, *(ref for observation in self.use_observations.values()
                                      for ref in observation.evidence_reference_ids)]


class SourceCandidate(Candidate):
    source_class: Literal["core", "domain", "conditional", "enrichment", "core_historical"]
    domains: Annotated[list[Identifier], Field(min_length=1, max_length=40)]
    identity_model: Text
    representations: Annotated[list[Text], Field(min_length=1, max_length=20)]
    access_plan: Text
    acquisition_constraints: Annotated[list[Text], Field(min_length=1, max_length=20)]
    update_policy: Text
    coverage_scope: Text
    coverage_denominator: Annotated[int, Field(ge=1, le=1_000_000_000)] | None
    coverage_gaps: Annotated[list[Text], Field(min_length=1, max_length=30)]
    access_review: ReviewObservation
    identity_review: ReviewObservation
    legal_review: ReviewObservation

    @model_validator(mode="after")
    def coherent_source(self):
        _unique(self.domains, "source domains")
        return self

    def all_reference_ids(self):
        return [*super().all_reference_ids(), *(ref for review in
                (self.access_review, self.identity_review, self.legal_review)
                for ref in review.evidence_reference_ids)]


class AssetCandidate(Candidate):
    asset_type: Literal["parser", "ocr", "embedding", "reranker", "ner", "morphology",
                       "vocabulary", "evaluation_dataset"]
    version: Annotated[str, Field(min_length=1, max_length=200)] | None
    artifact_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None
    licence_identifier: Annotated[str, Field(min_length=1, max_length=200)] | None
    related_source_family_ids: ReferenceIds
    language_scope: Text
    hardware_and_limits: Text
    maintenance_plan: Text
    replacement_plan: Text
    suitability: Literal["unmeasured", "reported_measured"]
    suitability_review: ReviewObservation
    licence_review: ReviewObservation

    @model_validator(mode="after")
    def coherent_asset(self):
        _unique(self.related_source_family_ids, "related source families")
        if ((self.suitability == "unmeasured") != (self.suitability_review.status == "pending")):
            raise ValueError("Suitability status and its review observation disagree")
        if self.suitability == "reported_measured" and (self.version is None or self.artifact_sha256 is None):
            raise ValueError("Reported measurements must identify the exact asset version and hash")
        if self.licence_review.status == "reported_reviewed" and self.licence_identifier is None:
            raise ValueError("Reported licence review must identify the licence")
        return self

    def all_reference_ids(self):
        return [*super().all_reference_ids(), *(ref for review in
                (self.suitability_review, self.licence_review) for ref in review.evidence_reference_ids)]


class Catalog(CatalogModel):
    authority: Literal["none"]
    references: Annotated[list[Reference], Field(min_length=1, max_length=500)]

    def validate_members(self, members):
        _unique([reference.id for reference in self.references], "reference IDs")
        _unique([member.id for member in members], "candidate IDs")
        known = {reference.id for reference in self.references}
        for member in members:
            _links(member.all_reference_ids(), known)


class SourceCatalog(Catalog):
    schema_version: Literal["qualification-source-catalog-v1"]
    sources: Annotated[list[SourceCandidate], Field(min_length=1, max_length=200)]

    @model_validator(mode="after")
    def coherent(self):
        self.validate_members(self.sources)
        return self


class AssetCatalog(Catalog):
    schema_version: Literal["qualification-asset-catalog-v1"]
    assets: Annotated[list[AssetCandidate], Field(min_length=1, max_length=200)]

    @model_validator(mode="after")
    def coherent(self):
        self.validate_members(self.assets)
        return self


def summarize_catalogs(source: SourceCatalog, assets: AssetCatalog) -> dict:
    """Validate cross-catalog links and return safe inventory counts, never authorization.

    Revalidation prevents callers from bypassing checks with model_construct or mutable
    nested data. No submitted free text or identifiers are echoed: even a syntactically
    valid candidate ID may contain confidential information or a credential.
    """
    source = SourceCatalog.model_validate(source.model_dump(mode="python"))
    assets = AssetCatalog.model_validate(assets.model_dump(mode="python"))
    known_sources = {candidate.id for candidate in source.sources}
    for asset in assets.assets:
        _links(asset.related_source_family_ids, known_sources)
    uses = Counter(observation.status for member in [*source.sources, *assets.assets]
                   for observation in member.use_observations.values())
    return {
        "schema_version": "qualification-catalog-summary-v1",
        "authority": "none",
        "source_family_count": len(source.sources),
        "asset_count": len(assets.assets),
        "source_class_counts": dict(sorted(Counter(item.source_class for item in source.sources).items())),
        "asset_type_counts": dict(sorted(Counter(item.asset_type for item in assets.assets).items())),
        "reported_use_observation_counts": {status: uses[status] for status in ("pending", "blocked", "permitted")},
        "source_review_pending_count": sum(review.status == "pending" for item in source.sources
                                           for review in (item.access_review, item.identity_review, item.legal_review)),
        "asset_review_pending_count": sum(review.status == "pending" for item in assets.assets
                                          for review in (item.suitability_review, item.licence_review)),
        "source_gap_count": sum(bool(item.qualification_gaps or item.coverage_gaps) for item in source.sources),
        "asset_gap_count": sum(bool(item.qualification_gaps) for item in assets.assets),
        "source_unknown_coverage_denominator_count": sum(item.coverage_denominator is None for item in source.sources),
        "asset_unknown_version_count": sum(item.version is None for item in assets.assets),
        "asset_unknown_licence_count": sum(item.licence_identifier is None for item in assets.assets),
    }
