"""Declared premise-state checks for model edits, never semantic/legal truth."""


class AssessmentValidationError(ValueError):
    code = "proposal_unsettled_assessment"

    def __init__(self):
        super().__init__("Model assessment lacks selected documented premises")


def validate_patch_assessments(content, patch):
    premises = {item["id"]: item for item in content["premises"]}
    applications = {item["id"]: item for item in content["applications"]}
    selected = {item["evidence_id"] for item in content["evidence"]}
    snapshots = content.get("fact_snapshots", [])
    facts = {item["id"]: item for item in snapshots}

    def documented(identity):
        premise = premises[identity]
        fact = facts.get(premise.get("fact_id"))
        return (premise["kind"] == "fact" and fact is not None
                and sum(item["id"] == fact["id"] for item in snapshots) == 1
                and fact.get("revision") == premise["fact_revision"]
                and fact.get("status") == "documented"
                and fact.get("evidence_id") in selected)

    for update in patch.application_updates:
        previous = {item["condition_id"]: item for item in applications[update.id]["assessments"]}
        for assessment in update.assessments:
            # Preserve a literal no-op without re-endorsing an existing human
            # assessment. Uncertainty and unchanged historical inputs stay valid.
            if assessment.status == "unknown" or previous.get(assessment.condition_id) == assessment.model_dump():
                continue
            if not assessment.premise_ids or not all(documented(identity) for identity in assessment.premise_ids):
                raise AssessmentValidationError()
