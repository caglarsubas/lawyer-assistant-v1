"""Immutable human review decisions for exact private-analysis versions.

Human attestation is separate from machine checks, authority approval and model
qualification. A decision never changes the saved text or its structural checks.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field, model_validator
from sqlalchemy import select

from .analysis_workbench import _freshness
from .auth import authenticate, require_child, require_matter
from .db import Record, digest
from .evidence_prompt import canonical
from .practice import StrictInput, _audit, _invalidate

RECIPE = "private-lawyer-review-v1"
HEAD_KIND = "analysis_review_head"
KIND = "analysis_review"
SCOPE = "conditional_private_draft_only"
CRITERIA = {
    "sources": "Özgün belgeleri, saklanan alıntıları ve seçimin kapsamını karşılaştırdım.",
    "reasoning": "Öncül, kural adayı, koşul/istisna, uygulama ve sonuç bağlantılarını değerlendirdim.",
    "fact_roles": "Olgu, taraf beyanı, varsayım, çıkarım ve bilinmeyen rollerini ve çelişkileri değerlendirdim.",
    "limits": "Belirsizlikleri, alternatifleri ve kamu/historik/karşı otorite araştırmasının sınırlarını açık tuttum.",
    "ai_contribution": "Model katkısını ve doğrulanmamış notlarını özgün dayanaklarla ayrıca değerlendirdim.",
}
Criterion = Literal["sources", "reasoning", "fact_roles", "limits", "ai_contribution"]


class ReviewCriterion(StrictInput):
    criterion: Criterion
    outcome: Literal["confirmed", "needs_change", "not_applicable"]
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def explained(self):
        if self.outcome != "confirmed" and len(self.note) < 3:
            raise ValueError("An unresolved or inapplicable criterion requires an explanation")
        return self


class ReviewFinding(StrictInput):
    target_id: str = Field(min_length=1, max_length=129)
    severity: Literal["critical", "major", "note"]
    text: str = Field(min_length=3, max_length=2000)
    suggested_change: str = Field(default="", max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class ReviewInput(StrictInput):
    expected_revision: int = Field(ge=1)
    version_id: str = Field(min_length=1, max_length=64)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_review_id: str | None = Field(default=None, min_length=1, max_length=64)
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    decision: Literal["reviewed_conditional", "changes_requested"]
    note: str = Field(min_length=3, max_length=2000)
    criteria: list[ReviewCriterion] = Field(min_length=1, max_length=5)
    findings: list[ReviewFinding] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def bounded(self):
        if len({item.criterion for item in self.criteria}) != len(self.criteria):
            raise ValueError("Duplicate review criteria")
        if self.decision == "changes_requested" and not self.findings and not any(
                item.outcome == "needs_change" for item in self.criteria):
            raise ValueError("A request for changes must identify a finding or unresolved criterion")
        if len(canonical(self.model_dump()).encode()) > 100000:
            raise ValueError("Review input exceeds its byte budget")
        return self


def _head_id(version_id):
    return "arh-" + digest(version_id)[:24]


def _version(store, session, matter_id, analysis_id, version_id, user):
    row = require_child(session, version_id, "practice_version", matter_id, user)
    data = store.decode(row)
    if data.get("entity_id") != analysis_id or data.get("entity_kind") != "practice_analysis":
        raise HTTPException(404, "Analiz sürümü bulunamadı.")
    return row, data


def _head(store, session, matter_id, analysis_id, version_id, user):
    row = session.get(Record, _head_id(version_id), populate_existing=True)
    if row:
        require_child(session, row.id, HEAD_KIND, matter_id, user)
        data = store.decode(row)
        if data.get("analysis_id") != analysis_id or data.get("version_id") != version_id:
            raise HTTPException(409, "İnceleme bağlantısı doğrulanamadı.")
    return row


def review_pin(store, session, matter_id, analysis_id, version_id, user):
    head = _head(store, session, matter_id, analysis_id, version_id, user)
    return store.decode(head)["latest_review_id"] if head else None


def projection(store, session, matter_id, analysis_id, version_id, user, content, freshness):
    ident = review_pin(store, session, matter_id, analysis_id, version_id, user)
    if not ident:
        return {"effective_state": "unreviewed", "scope": SCOPE, "latest": None, "reasons": []}
    row = require_child(session, ident, KIND, matter_id, user)
    data = store.view(row)
    if data.get("analysis_id") != analysis_id or data.get("version_id") != version_id:
        raise HTTPException(409, "İnceleme kaydı doğrulanamadı.")
    reasons = list(freshness["reasons"])
    if data["recipe"] != RECIPE:
        reasons.append("İnceleme ölçütleri değişti; yeni bir avukat incelemesi gerekli.")
    if data["content_sha256"] != digest(canonical(content)):
        reasons.append("İncelenen içerik özeti bu sürümle eşleşmiyor.")
    effective = "stale" if reasons else data["decision"]
    return {"effective_state": effective, "scope": SCOPE, "latest": data, "reasons": reasons}


def _context(store, session, matter_id, analysis_id, version_id, user):
    row = require_child(session, analysis_id, "practice_analysis", matter_id, user)
    session.refresh(row)
    version, snapshot = _version(store, session, matter_id, analysis_id, version_id, user)
    content = snapshot["content"]
    freshness = _freshness(store, session, matter_id, user, content)
    current_version = store.decode(row)["latest_version_id"] == version.id
    current = projection(store, session, matter_id, analysis_id, version.id, user, content, freshness)
    return row, version, content, {
        "version_id": version.id, "expected_revision": row.revision,
        "content_sha256": digest(canonical(content)), "expected_review_id": current["latest"]["id"] if current["latest"] else None,
        "recipe": RECIPE, "scope": SCOPE, "criteria": CRITERIA,
        "ai_contribution_required": bool(content.get("ai_assistance")),
        "current_version": current_version, "freshness": freshness,
        "critical_count": content["checks"]["critical_count"],
        "can_record": current_version,
        "can_accept": current_version and freshness["status"] == "current" and not content["checks"]["critical_count"],
        "review": current,
        "sources": [{key: item[key] for key in ("evidence_id", "document_id", "name", "locator", "start", "end", "quote_sha256")}
                    for item in content["evidence"]],
        "targets": ["analysis", "conclusion", *(kind + ":" + item["id"] for group, kind in (
            ("premises", "premise"), ("rules", "rule"), ("applications", "application"), ("alternatives", "alternative"))
            for item in content[group]), *("condition:" + item["id"] for rule in content["rules"] for item in rule["conditions"])],
    }


def _validate_decision(body, context, content):
    sources = {item["evidence_id"] for item in content["evidence"]}
    for finding in body.findings:
        if (finding.target_id not in context["targets"] or len(set(finding.evidence_ids)) != len(finding.evidence_ids)
                or not set(finding.evidence_ids) <= sources):
            raise HTTPException(422, "İnceleme bulgusu sabit analizdeki adım ve kaynaklara bağlanmalıdır.")
    for criterion in body.criteria:
        if criterion.outcome == "not_applicable" and (
                criterion.criterion != "ai_contribution" or context["ai_contribution_required"]):
            raise HTTPException(422, "Bu inceleme ölçütü uygulanamaz olarak atlanamaz.")
    if body.decision == "reviewed_conditional":
        if not context["can_accept"]:
            raise HTTPException(409, "Değişen dayanaklar veya kritik yapısal kontroller varken inceleme tamamlanamaz.")
        if (set(item.criterion for item in body.criteria) != set(CRITERIA)
                or any(item.outcome == "needs_change" for item in body.criteria)
                or any(item.severity != "note" for item in body.findings)):
            raise HTTPException(422, "Koşullu taslak incelemesi tüm ölçütleri ve çözülmemiş esaslı bulguları ele almalıdır.")


def review_router():
    router = APIRouter(prefix="/api/v1/matters/{matter_id}/analyses/{analysis_id}/reviews", tags=["lawyer-analysis-review"])

    @router.get("/context")
    def context(matter_id: str, analysis_id: str, version_id: str, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            return _context(store, session, matter_id, analysis_id, version_id, user)[3]

    @router.get("")
    def history(matter_id: str, analysis_id: str, version_id: str, request: Request, user=Depends(authenticate),
                limit: int = Query(default=10, ge=1, le=20), offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            require_child(session, analysis_id, "practice_analysis", matter_id, user)
            _version(store, session, matter_id, analysis_id, version_id, user)
            rows = session.scalars(select(Record).where(
                Record.kind == KIND, Record.firm_id == user.firm_id, Record.matter_id == matter_id,
                Record.id.startswith(_head_id(version_id) + "-", autoescape=True)
            ).order_by(Record.created_at.desc(), Record.id).limit(limit).offset(offset))
            return [store.view(row) for row in rows if store.decode(row).get("analysis_id") == analysis_id
                    and store.decode(row).get("version_id") == version_id]

    @router.post("", status_code=201)
    def record(matter_id: str, analysis_id: str, body: ReviewInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        request_hash = digest(canonical(body.model_dump(exclude={"request_id"})))
        ident = _head_id(body.version_id) + "-" + digest(user.id + ":" + body.request_id)[:32]
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            require_child(session, analysis_id, "practice_analysis", matter_id, user)
            _version(store, session, matter_id, analysis_id, body.version_id, user)
            existing = session.get(Record, ident)
            if existing:
                require_child(session, ident, KIND, matter_id, user)
                saved = store.view(existing)
                if saved.get("request_sha256") != request_hash or existing.owner_id != user.id or saved.get("analysis_id") != analysis_id:
                    raise HTTPException(409, "İstek kimliği farklı bir inceleme kararına bağlı.")
                return saved
            row, version, content, context = _context(store, session, matter_id, analysis_id, body.version_id, user)
            if (not context["can_record"] or body.expected_revision != row.revision
                    or body.content_sha256 != context["content_sha256"] or body.expected_review_id != context["expected_review_id"]):
                raise HTTPException(409, "Analiz veya inceleme sırası değişti; gösterilen sürümü yeniden açın.")
            _validate_decision(body, context, content)
            head = _head(store, session, matter_id, analysis_id, version.id, user)
            sequence = store.decode(head)["sequence"] + 1 if head else 1
            data = {**body.model_dump(exclude={"request_id", "expected_revision"}),
                    "analysis_id": analysis_id, "recipe": RECIPE, "scope": SCOPE, "sequence": sequence,
                    "request_sha256": request_hash, "reviewer_id": user.id, "reviewer_name": user.name,
                    "immutable": True, "source_freshness_at_review": context["freshness"],
                    "source_selections": context["sources"], "machine_legal_approval": "not_granted"}
            event = store.add(session, KIND, user, data, matter_id, record_id=ident)
            pointer = {"analysis_id": analysis_id, "version_id": version.id, "latest_review_id": ident, "sequence": sequence}
            if head:
                store.update(head, pointer)
            else:
                store.add(session, HEAD_KIND, user, pointer, matter_id, record_id=_head_id(version.id))
            _invalidate(store, session, matter, "Analizin avukat incelemesi değişti; hazırlık bağlamını yeniden inceleyin.")
            _audit(session, user, "analysis_review_recorded", event.id, matter_id)
            require_matter(session, matter_id, user)
            if body.decision == "reviewed_conditional" and _freshness(store, session, matter_id, user, content)["status"] != "current":
                raise HTTPException(409, "İnceleme sırasında özel dayanaklar değişti.")
            session.commit()
            return store.view(event)

    return router
