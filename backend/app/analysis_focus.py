"""Explicit, budgeted private sub-analyses; never truncate a parent in place."""

import copy
from typing import Literal

from fastapi import Depends, HTTPException, Request
from pydantic import Field, model_validator

from .analysis_proposals import draft_input
from .analysis_suggestions import SuggestionInput, _context_budget, _prepare_suggestion, _source
from .analysis_workbench import NodeID, Selection, _content, _view
from .auth import authenticate, require_child, require_matter
from .db import digest
from .evidence_prompt import canonical
from .practice import StrictInput, _audit, _invalidate, _write_version

RECIPE = "private-analysis-focus-v1"
LIMITATION = "Dar kapsamlı çalışma; ana analizin tamamı ve karşı dayanaklar incelenmeden genel sonuç çıkarılamaz."


class FocusInput(StrictInput):
    expected_revision: int = Field(ge=1)
    version_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    title: str = Field(min_length=3, max_length=200)
    issue: str = Field(min_length=3, max_length=500)
    application_id: NodeID
    alternative_ids: list[NodeID] = Field(max_length=12)
    evidence: list[Selection] = Field(min_length=1, max_length=20)
    omission_note: str = Field(min_length=10, max_length=500)
    acknowledge_partial: Literal[True]
    context_preview_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def unique(self):
        if (len(set(self.alternative_ids)) != len(self.alternative_ids)
                or len({item.evidence_id for item in self.evidence}) != len(self.evidence)):
            raise ValueError("Repeated focus selection")
        return self


def _prepare(app, session, matter_id, analysis_id, user, body):
    state = _prepare_suggestion(app, session, matter_id, analysis_id, user, SuggestionInput(
        expected_revision=body.expected_revision, version_id=body.version_id, request_id=body.request_id))
    parent = state["source_content"]
    version = app.state.store.decode(require_child(session, body.version_id, "practice_version", matter_id, user))
    if version.get("entity_id") != analysis_id or version.get("entity_kind") != "practice_analysis":
        raise HTTPException(409, "Ana analizin tam sürüm bağı doğrulanamadı.")
    if any(parent.get(key) != value for key, value in version["content"].items()):
        raise HTTPException(409, "Ana analiz ile değiştirilemez tam sürümü uyuşmuyor.")
    # Public contributions have independent grants, reviews and publication state.
    # Do not strip them or their dependencies to make a smaller private prompt.
    if (parent.get("authority_dependencies") or parent.get("authority_contributions")
            or parent.get("ai_assistance", {}).get("authority_feedback") or parent.get("focus_lineage")):
        raise HTTPException(422, "Kamu katkılı veya zaten odaklanmış analiz bu akışta daraltılamaz.")
    application = next((item for item in parent["applications"] if item["id"] == body.application_id), None)
    alternatives = [item for item in parent["alternatives"] if item["id"] in body.alternative_ids]
    if not application or len(alternatives) != len(body.alternative_ids):
        raise HTTPException(422, "Adım ve alternatifler tam kaynak sürümünden seçilmelidir.")
    rule = next(item for item in parent["rules"] if item["id"] == application["rule_id"])
    premises = [item for item in parent["premises"] if item["id"] in application["premise_ids"]]
    fact_ids = {item["fact_id"] for item in premises if item["kind"] == "fact"}
    required = set(rule["evidence_ids"]) | {ref for item in alternatives for ref in item["evidence_ids"]}
    required |= {item["evidence_id"] for item in parent["fact_snapshots"]
                 if item["id"] in fact_ids and item["evidence_id"]}
    selected = {item.evidence_id for item in body.evidence}
    original = {item["evidence_id"]: item for item in parent["evidence"]}
    if not required <= selected or not selected <= original.keys():
        raise HTTPException(422, "Kural, olgu ve seçilen alternatiflerin tüm dayanaklarını koruyun; yeni dayanak önce ana analize bağlanmalıdır.")
    for item in body.evidence:
        source = original[item.evidence_id]
        if (item.passage_sha256 != source["passage_sha256"]
                or item.document_revision != source["document_revision"]
                or not source["start"] <= item.start < item.end <= source["end"]):
            raise HTTPException(409, "Odak alıntısı tam kaynak sürümünün dondurulmuş aralığı içinde olmalıdır.")
    omitted = {key: [item["id"] for item in parent[key] if item["id"] not in kept]
               for key, kept in (("applications", {application["id"]}), ("rules", {rule["id"]}),
                                 ("premises", {item["id"] for item in premises}),
                                 ("alternatives", set(body.alternative_ids)))}
    omitted["evidence"] = [item["evidence_id"] for item in parent["evidence"] if item["evidence_id"] not in selected]
    ranges = [{"evidence_id": item.evidence_id, "parent_start": original[item.evidence_id]["start"],
               "parent_end": original[item.evidence_id]["end"], "start": item.start, "end": item.end}
              for item in body.evidence
              if (item.start, item.end) != (original[item.evidence_id]["start"], original[item.evidence_id]["end"])]
    lineage = {"recipe": RECIPE, "scope": "creation_selection_only", "parent_analysis_id": analysis_id,
               "parent_version_id": body.version_id, "parent_revision": body.expected_revision,
               "parent_content_sha256": digest(canonical(version["content"])), "parent_review_id": state["source_review_id"],
               "parent_review_recipe": state["source_review_recipe"],
               "derived_ai": bool(parent.get("ai_assistance")), "application_id": application["id"],
               "omitted": omitted, "narrowed_ranges": ranges, "omission_note": body.omission_note,
               "replaced_sections": ["issue", "posture", "application_rationale", "conclusion"],
               "limitation": LIMITATION, "review_transferred": False}
    draft = draft_input(parent).model_dump()
    draft.update(title=body.title, issue=body.issue, posture=LIMITATION,
                 evidence=[item.model_dump() for item in body.evidence], premises=premises, rules=[rule],
                 applications=[{**copy.deepcopy(application), "rationale": "Bu adım odak kapsamında yeniden incelenecek."}],
                 alternatives=alternatives, conclusion={"text": "Odak incelemesi tamamlanmadı; sonuç bekletiliyor.",
                     "requested_disposition": "withheld", "application_ids": [application["id"]],
                     "alternative_ids": [item["id"] for item in alternatives],
                     "uncertainty": [LIMITATION, body.omission_note], "next_step": "Ana analizle karşılaştırın; özgün belgeleri ve dışarıda kalanları inceleyin."})
    from .analysis_workbench import AnalysisInput

    content = _content(app.state.store, session, matter_id, user, AnalysisInput.model_validate(draft))
    for key in ("fact_snapshots", "contradiction_snapshots"):
        retained = {item["id"] for item in content[key]}
        omitted[key] = [item["id"] for item in parent[key] if item["id"] not in retained]
    content["focus_lineage"] = lineage
    if lineage["derived_ai"]:
        content["authorship"] = "user_with_ai_assistance"
    focused_state = {**state, "source_content": content}
    budget = _context_budget(app, session, matter_id, user, body, focused_state)
    _source(app, session, matter_id, user, state)
    require_matter(session, matter_id, user)
    return content, budget


def lineage_reasons(store, session, matter_id, user, content):
    origin = content.get("focus_lineage")
    if not origin:
        return []
    try:
        require_child(session, origin["parent_analysis_id"], "practice_analysis", matter_id, user)
        snapshot = store.decode(require_child(session, origin["parent_version_id"], "practice_version", matter_id, user))
        if (origin["recipe"] == RECIPE and snapshot["entity_id"] == origin["parent_analysis_id"]
                and snapshot["entity_kind"] == "practice_analysis"
                and digest(canonical(snapshot["content"])) == origin["parent_content_sha256"]):
            return []
    except HTTPException:
        pass
    return ["Odak analizinin özgün ana sürüm bağı artık doğrulanamıyor."]


def register(router):
    @router.post("/{record_id}/focus/preview")
    def preview(matter_id: str, record_id: str, body: FocusInput, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            content, budget = _prepare(request.app, session, matter_id, record_id, user, body)
            return {"content": content, "budget": budget}

    @router.post("/{record_id}/focus", status_code=201)
    def create(matter_id: str, record_id: str, body: FocusInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        ident = record_id + "-focus-" + digest(user.id + ":" + body.request_id)[:24]
        request_hash = digest(canonical(body.model_dump(exclude={"request_id"})))
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            require_child(session, record_id, "practice_analysis", matter_id, user)
            from .db import Record

            receipt = session.get(Record, ident)
            if receipt:
                saved = store.decode(require_child(session, ident, "analysis_focus_receipt", matter_id, user))
                if saved["request_sha256"] != request_hash:
                    raise HTTPException(409, "İstek kimliği başka bir odak seçimi için kullanılmış.")
                row = require_child(session, saved["analysis_id"], "practice_analysis", matter_id, user)
                return _view(store, session, matter_id, user, row)
            content, budget = _prepare(request.app, session, matter_id, record_id, user, body)
            if not body.context_preview_sha256 or body.context_preview_sha256 != budget["preview_sha256"]:
                raise HTTPException(409, "Odak kapsamı veya kaynak bağlamı değişti; önizlemeyi yenileyin.")
            if not budget["fits"]:
                raise HTTPException(422, "Odak hâlâ bağlama sığmıyor; metin kesilmedi. Kapsamı açıkça yeniden seçin.")
            from .analysis_workbench import AnalysisInput

            new_body = AnalysisInput(**draft_input(content).model_dump(exclude={"expected_revision", "change_note"}),
                                     change_note="Ayrı odak analizi; ana sürüm korunur.")
            row = _write_version(store, session, user, "practice_analysis", new_body, content, matter_id)
            store.add(session, "analysis_focus_receipt", user,
                      {"request_sha256": request_hash, "analysis_id": row.id}, matter_id, ident)
            _invalidate(store, session, matter, "Ayrı odak analizi eklendi; inceleme gerekli.")
            _audit(session, user, "analysis_focus_created", row.id, matter_id)
            require_matter(session, matter_id, user)
            session.commit()
            return _view(store, session, matter_id, user, row)
