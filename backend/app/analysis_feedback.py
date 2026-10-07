"""Opt-in immutable review selections; declared dependency paths are not legal proof."""

from typing import Annotated

from fastapi import HTTPException
from pydantic import Field, model_validator

from .analysis_reviews import _context
from .db import digest
from .evidence_prompt import canonical
from .practice import StrictInput


class FeedbackSelection(StrictInput):
    review_id: str = Field(min_length=1, max_length=64)
    finding_indices: list[Annotated[int, Field(strict=True, ge=0, le=19)]] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.finding_indices)) != len(self.finding_indices):
            raise ValueError("Duplicate selected review findings")
        return self


def editable_targets(content, target):
    """Follow only saved, declared links to existing editable nodes."""
    apps = content["applications"]
    if target == "analysis":
        return [*("application:" + item["id"] for item in apps), "conclusion"]
    if target == "conclusion":
        return ["conclusion"]
    kind, _, ident = target.partition(":")
    if kind == "application":
        selected = {item["id"] for item in apps if item["id"] == ident}
    elif kind == "premise":
        selected = {item["id"] for item in apps if ident in item["premise_ids"]}
    elif kind in {"rule", "condition"}:
        rules = {rule["id"] for rule in content["rules"] if (rule["id"] == ident if kind == "rule"
                 else any(condition["id"] == ident for condition in rule["conditions"]))}
        selected = {item["id"] for item in apps if item["rule_id"] in rules}
    else:
        selected = set()
    result = ["application:" + item["id"] for item in apps if item["id"] in selected]
    conclusion = content["conclusion"]
    if selected.intersection(conclusion["application_ids"]) or (
            kind == "alternative" and ident in conclusion["alternative_ids"]):
        result.append("conclusion")
    return result


def resolve_feedback(store, session, matter_id, analysis_id, version_id, user, selection):
    """Load authorized server-owned findings, never caller-supplied review text."""
    _, _, content, context = _context(store, session, matter_id, analysis_id, version_id, user)
    review = context["review"]
    event = review["latest"]
    if (not context["current_version"] or context["freshness"]["status"] != "current"
            or review["effective_state"] != "changes_requested" or not event or event["id"] != selection.review_id):
        raise HTTPException(409, "Seçilen bulgular güncel sürümün son değişiklik isteğine bağlı olmalıdır.")
    if any(index >= len(event["findings"]) for index in selection.finding_indices):
        raise HTTPException(422, "Seçilen inceleme bulgusu bu kayıtta bulunamadı.")
    findings = [{**event["findings"][index], "finding_id": "finding:" + str(index), "index": index,
                 "editable_targets": editable_targets(content, event["findings"][index]["target_id"])}
                for index in sorted(selection.finding_indices)]
    snapshot = {"review_id": event["id"], "source_version_id": version_id,
                "content_sha256": context["content_sha256"], "review_recipe": context["recipe"],
                "scope": "selected_private_review_findings_not_resolution", "findings": findings}
    return snapshot, digest(canonical(snapshot))
