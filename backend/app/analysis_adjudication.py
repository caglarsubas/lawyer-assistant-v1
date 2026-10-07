"""Source-linked human observations about two exact private draft versions.

Checks establish bindings and declared dispositions, never semantic/legal truth.
There is no model invocation, public-authority approval or benefit calculation.
"""

from typing import Literal

from fastapi import HTTPException
from pydantic import Field, StrictInt, model_validator

from .analysis_workbench import _freshness
from .db import digest
from .evidence_prompt import canonical
from .practice import StrictInput

RECIPE = "private-revision-adjudication-v1"
DIMENSIONS = {
    "entailment": "Seçilen pasajın anlamı uygulama ve sonucu gerçekten destekliyor mu?",
    "fact_roles": "Beyan, olgu, varsayım, olumsuzluk ve aktör ayrımları korunuyor mu?",
    "conditions": "Maddi koşullar, istisnalar ve eksik unsurlar ele alınıyor mu?",
    "chronology": "Olay sırası, tarih ve miktar sınırları doğru korunuyor mu?",
    "counterevidence": "Seçilen özel belgelerdeki karşı dayanaklar ve maddi ayrımlar ele alınıyor mu?",
    "certainty": "Sonuç ve belirsizlikler dayanakların gücünü aşıyor mu?",
}
Dimension = Literal["entailment", "fact_roles", "conditions", "chronology", "counterevidence", "certainty"]


class LinkedObservation(StrictInput):
    note: str = Field(min_length=3, max_length=2000)
    target_ids: list[str] = Field(min_length=1, max_length=20)
    source_refs: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.target_ids)) != len(self.target_ids) or len(set(self.source_refs)) != len(self.source_refs):
            raise ValueError("Repeated adjudication references")
        return self


class SemanticObservation(LinkedObservation):
    dimension: Dimension
    outcome: Literal["confirmed", "needs_change", "not_assessed"]


class FindingDisposition(LinkedObservation):
    finding_index: StrictInt = Field(ge=0, le=19)
    outcome: Literal["repaired", "withheld", "unresolved"]


class RevisionAssessment(StrictInput):
    comparison_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    observations: list[SemanticObservation] = Field(min_length=6, max_length=6)
    finding_dispositions: list[FindingDisposition] = Field(default_factory=list, max_length=20)
    review_seconds: StrictInt | None = Field(default=None, ge=1, le=28800)

    @model_validator(mode="after")
    def complete(self):
        if {item.dimension for item in self.observations} != set(DIMENSIONS):
            raise ValueError("All six semantic dimensions require a distinct observation")
        indices = [item.finding_index for item in self.finding_dispositions]
        if len(set(indices)) != len(indices):
            raise ValueError("Repeated finding dispositions")
        return self


def target_values(content):
    """Typed nodes retain fact roles and source selection, not inferred causality."""
    facts = {item["id"]: item for item in content["fact_snapshots"]}
    result = {"analysis": {key: content[key] for key in ("title", "issue", "posture", "event_date")},
              "conclusion": content["conclusion"]}
    for group, kind in (("premises", "premise"), ("rules", "rule"), ("applications", "application"),
                        ("alternatives", "alternative")):
        for item in content[group]:
            result[kind + ":" + item["id"]] = ({**item, "fact_snapshot": facts.get(item["fact_id"])}
                                                   if kind == "premise" and item["kind"] == "fact" else item)
    for rule in content["rules"]:
        for item in rule["conditions"]:
            result["condition:" + item["id"]] = {**item, "rule_id": rule["id"]}
    return result


def comparison_context(store, session, matter_id, analysis_id, version_id, user, content):
    from .analysis_reviews import RECIPE as review_recipe
    from .analysis_reviews import _version, review_pin
    from .auth import require_child

    previous_id = content["revision_comparison"]["previous_version_id"]
    if not previous_id:
        return None
    version, previous = _version(store, session, matter_id, analysis_id, previous_id, user)
    current_version, current = _version(store, session, matter_id, analysis_id, version_id, user)
    if previous["version"] + 1 != current["version"] or version.id == current_version.id:
        raise HTTPException(409, "Önceki sürüm sırası doğrulanamadı.")
    before = previous["content"]
    review_id = review_pin(store, session, matter_id, analysis_id, previous_id, user)
    review = None
    if review_id:
        review = store.view(require_child(session, review_id, "analysis_review", matter_id, user))
        if (review.get("analysis_id") != analysis_id or review.get("version_id") != previous_id
                or review.get("content_sha256") != digest(canonical(before))):
            raise HTTPException(409, "Önceki sürümün inceleme bağı doğrulanamadı.")
    left, right = target_values(before), target_values(content)
    snapshot = {
        "recipe": RECIPE, "scope": "selected_private_evidence_only", "review_recipe": review_recipe,
        "base_version_id": previous_id, "base_version": previous["version"],
        "base_content_sha256": digest(canonical(before)), "base_review_id": review_id,
        "base_review_sha256": digest(canonical(review)) if review else None,
        "candidate_version_id": version_id, "candidate_version": current["version"],
        "candidate_content_sha256": digest(canonical(content)),
        "candidate_disposition": content["checks"]["effective_disposition"],
        "targets": sorted(left.keys() | right.keys()),
        "changes": [{"target_id": key, "before": left.get(key), "after": right.get(key)}
                    for key in sorted(left.keys() | right.keys()) if left.get(key) != right.get(key)],
        "findings": [{**item, "finding_index": index} for index, item in enumerate(review["findings"] if review else [])],
        "sources": [{"source_ref": side + ":" + item["evidence_id"], **{key: item[key] for key in (
            "evidence_id", "document_id", "document_revision", "document_sha256", "name", "locator", "start", "end",
            "passage_sha256", "quote_sha256", "text")}} for side, draft in (("before", before), ("after", content))
                    for item in draft["evidence"]],
        "dimensions": DIMENSIONS,
        "public_adverse_authority_qualified": False,
        "benefit_established": False,
    }
    reasons = _freshness(store, session, matter_id, user, before)["reasons"]
    reasons = list(dict.fromkeys([*reasons, *_freshness(store, session, matter_id, user, content)["reasons"]]))
    if review and review["recipe"] != review_recipe:
        reasons.append("Önceki incelemenin ölçütleri değişti; karşılaştırma güncel değil.")
    return {**snapshot, "comparison_sha256": digest(canonical(snapshot)),
            "freshness": {"status": "stale" if reasons else "current", "reasons": reasons}}


def validate_assessment(assessment, comparison, content, decision):
    if not comparison or assessment.comparison_sha256 != comparison["comparison_sha256"]:
        raise HTTPException(409, "Sürüm karşılaştırması değişti; özgün dayanakları yeniden açın.")
    if comparison["freshness"]["status"] != "current":
        raise HTTPException(409, "Karşılaştırmanın özel dayanakları veya inceleme ölçütleri değişti.")
    targets = set(comparison["targets"])
    sources = {item["source_ref"] for item in comparison["sources"]}
    after_sources = {item["source_ref"] for item in comparison["sources"] if item["source_ref"].startswith("after:")}
    changes = {item["target_id"] for item in comparison["changes"] if item["after"] is not None}
    findings = {item["finding_index"]: item for item in comparison["findings"]}
    if {item.finding_index for item in assessment.finding_dispositions} != set(findings):
        raise HTTPException(422, "Önceki incelemedeki her bulgu ayrı değerlendirilmelidir.")
    for item in [*assessment.observations, *assessment.finding_dispositions]:
        if not set(item.target_ids) <= targets or not set(item.source_refs) <= sources:
            raise HTTPException(422, "Değerlendirme yalnız sabit sürüm adımlarına ve alıntılarına bağlanabilir.")
    for item in assessment.observations:
        if item.outcome == "confirmed" and not set(item.source_refs) & after_sources:
            raise HTTPException(422, "Olumlu anlamsal gözlem güncel sürümün alıntısına bağlanmalıdır.")
        if item.outcome == "needs_change" and decision == "reviewed_conditional":
            raise HTTPException(422, "Anlamsal değişiklik gereksinimi varken olumlu inceleme kaydedilemez.")
    for item in assessment.finding_dispositions:
        if item.outcome == "repaired" and (not set(item.target_ids) & changes or not set(item.source_refs) & after_sources):
            raise HTTPException(422, "Giderildi beyanı gerçek bir düzenlemeye ve güncel alıntıya bağlanmalıdır.")
        if item.outcome == "repaired":
            common = set(item.target_ids) & changes
            for dimension in ("entailment", "certainty"):
                common &= {target for observation in assessment.observations
                           if observation.dimension == dimension and observation.outcome == "confirmed"
                           for target in observation.target_ids}
            if not common:
                raise HTTPException(422, "Giderildi beyanı aynı düzenlemenin anlamı ve sonuç gücü için olumlu gözlem gerektirir.")
        if item.outcome == "withheld" and content["checks"]["effective_disposition"] != "withheld":
            raise HTTPException(422, "Bekletildi beyanı için taslağın sonucu gerçekten bekletilmelidir.")
        if item.outcome == "unresolved" and findings[item.finding_index]["severity"] != "note" and decision == "reviewed_conditional":
            raise HTTPException(422, "Çözülmemiş kritik veya esaslı bulgu varken olumlu inceleme kaydedilemez.")


def assessment_lines(event):
    assessment = event.get("revision_assessment")
    comparison = event.get("revision_comparison_snapshot")
    if not assessment or not comparison:
        return []
    lines = ["Kaynak bağlı sürüm değerlendirmesi — avukat beyanı, anlamsal doğruluk veya fayda garantisi değildir.",
             f"Önceki sürüm: {comparison['base_version_id']} / içerik: {comparison['base_content_sha256']}",
             f"Karşılaştırma SHA-256: {assessment['comparison_sha256']} / kapsam: {comparison['scope']}",
             "Kamu/karşı içtihat doğrulanmadı; zaman kazanımı ölçülmedi.",
             "Beyan edilen inceleme süresi (saniye): " + str(assessment['review_seconds'] or "Ölçülmedi")]
    for item in assessment["observations"]:
        lines.append(f"Anlamsal gözlem {item['dimension']} / {item['outcome']}: {item['note']} / "
                     f"adımlar: {', '.join(item['target_ids'])} / alıntılar: {', '.join(item['source_refs'])}")
    for item in assessment["finding_dispositions"]:
        finding = comparison["findings"][item["finding_index"]]
        lines.append(f"Önceki bulgu {item['finding_index']} / {finding['target_id']}: {finding['text']} / "
                     f"{item['outcome']}: {item['note']} / adımlar: {', '.join(item['target_ids'])} / "
                     f"alıntılar: {', '.join(item['source_refs'])}")
    targets = {target for item in [*assessment['observations'], *assessment['finding_dispositions']] for target in item['target_ids']}
    for change in comparison["changes"]:
        if change["target_id"] in targets:
            lines.append(f"Değerlendirilen değişiklik {change['target_id']} / önceki: {canonical(change['before'])} / "
                         f"gösterilen: {canonical(change['after'])}")
    used = {ref for item in [*assessment['observations'], *assessment['finding_dispositions']] for ref in item['source_refs']}
    for source in comparison["sources"]:
        if source["source_ref"] in used:
            lines.append(f"Değerlendirme alıntısı {source['source_ref']} / {source['name']} / "
                         f"[{source['start']}, {source['end']}) / SHA-256: {source['quote_sha256']}: {source['text']}")
    return lines
