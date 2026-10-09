"""Private proposal jobs on the shared research queue; adoption is a human write."""

import time
from contextlib import ExitStack
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field, model_validator
from sqlalchemy import select

from . import analysis_reviews, authority_proposals
from .analysis_feedback import FeedbackSelection, resolve_feedback
from .analysis_proposals import (
    RECIPE,
    apply_patch,
    critical_ids,
    draft_input,
    parse_patch,
    prompt_measurement,
    proposal_messages,
)
from .analysis_reviews import review_pin
from .analysis_workbench import _content, _freshness, _view
from .auth import authenticate, require_child, require_matter
from .db import Record, User, digest, now
from .evidence_prompt import canonical
from .firm_rbac import guard_job_write
from .practice import StrictInput, _audit, _invalidate, _write_version
from .research_jobs import (
    JobStopped,
    QueueUnavailable,
    checkpoint,
    ensure_active,
    finish_run,
    request_stop,
    submission,
)

PURPOSE = "private_analysis_suggestion"
RECEIPT = "analysis_suggestion_receipt"


class ComparisonReference(StrictInput):
    id: str = Field(min_length=1, max_length=64)
    protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    arm: Literal["single_pass", "bounded_correction"]


class SuggestionInput(StrictInput):
    expected_revision: int = Field(ge=1)
    version_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    mode: Literal["single", "repair"] = "single"
    review_feedback: FeedbackSelection | None = None
    comparison_ref: ComparisonReference | None = None
    authority_feedback: authority_proposals.AuthorityFeedbackSelection | None = None

    @model_validator(mode="after")
    def separate(self):
        if self.authority_feedback and (self.review_feedback or self.comparison_ref):
            raise ValueError("Authority proposals cannot share a private-feedback or comparison protocol")
        return self


class AdoptInput(StrictInput):
    expected_revision: int = Field(ge=1)
    candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    change_note: str = Field(min_length=3, max_length=1000)


def provider_pin(app):
    settings = app.state.provider.settings
    return {"recipe": RECIPE, "model": settings.provider_model,
            "tenant": settings.provider_tenant_id, "organization": settings.provider_org_id,
            "key_id": settings.provider_key_id, "context_limit": settings.provider_context_limit,
            "identity_verified": settings.provider_identity_verified,
            "cloud_fallback_disabled": settings.provider_cloud_fallback_disabled,
            "route_configuration_sha256": digest(canonical({
                "base": settings.provider_base_url, "plain_http": settings.provider_allow_plain_http,
                "tunnel": settings.provider_tunnel_url, "approved": settings.provider_tunnel_approved,
                "host": settings.provider_tunnel_approved_host})),
            "transport": app.state.provider.transport_metadata()}


def _source(app, session, matter_id, user, state):
    store = app.state.store
    matter = require_matter(session, matter_id, user)
    if store.decode(matter).get("status") == "archived":
        raise HTTPException(409, "Arşivlenmiş çalışma alanında model önerisi uygulanamaz.")
    row = require_child(session, state["analysis_id"], "practice_analysis", matter_id, user)
    session.refresh(row)
    content = store.view(row)
    if row.revision != state["source_revision"] or content["latest_version_id"] != state["source_version_id"]:
        raise HTTPException(409, "Analiz sürümü değişti; öneri için yeni bir çalışma başlatın.")
    if state.get("source_review_id") != review_pin(store, session, matter_id, row.id, state["source_version_id"], user):
        raise HTTPException(409, "Avukat incelemesi değişti; öneri için yeni bir çalışma başlatın.")
    if state.get("source_review_id") and state.get("source_review_recipe") != analysis_reviews.RECIPE:
        raise HTTPException(409, "İnceleme ölçütleri değişti; yeni bir inceleme ve öneri gerekli.")
    if state.get("source_review_id"):
        reviewed = store.decode(require_child(session, state["source_review_id"], analysis_reviews.KIND, matter_id, user))
        if reviewed.get("revision_assessment"):
            _, version = analysis_reviews._version(store, session, matter_id, row.id, state["source_version_id"], user)
            if analysis_reviews.comparison_reasons(store, session, matter_id, row.id, state["source_version_id"],
                                                  user, version["content"], reviewed):
                raise HTTPException(409, "Kaynak incelemenin sürüm değerlendirmesi değişti; yeni inceleme ve öneri gerekli.")
    freshness = _freshness(store, session, matter_id, user, state["source_content"])
    if freshness["status"] == "stale":
        raise HTTPException(409, "Önerinin özel dayanakları değişti; önce analiz sürümünü yenileyin.")
    if state["provider_pin"] != provider_pin(app):
        raise HTTPException(409, "Model veya öneri politikası değişti; yeni bir öneri başlatın.")
    if state.get("comparison_ref"):
        from .analysis_comparisons import validate_job

        validate_job(app, session, matter_id, user, state)
    if state.get("review_feedback"):
        feedback = state["review_feedback"]
        selection = FeedbackSelection(review_id=feedback["review_id"],
                                      finding_indices=[item["index"] for item in feedback["findings"]])
        snapshot, checksum = resolve_feedback(store, session, matter_id, row.id, state["source_version_id"], user, selection)
        if snapshot != feedback or checksum != state.get("review_feedback_sha256"):
            raise HTTPException(409, "Seçilen inceleme bulgularının sürüm ve içerik bağı doğrulanamadı.")
        candidate = state.get("candidate")
        if candidate:
            selected_pass = state.get("feedback_response_pass")
            iteration = next((item for item in state["iterations"] if item["pass"] == selected_pass), None)
            if (selected_pass is None and candidate["revision_comparison"]["changed_sections"]) or (
                    selected_pass is not None and (not iteration or iteration["outcome"] != "accepted_structural_patch"
                    or iteration["patch"]["feedback_responses"] != state.get("feedback_responses"))):
                raise HTTPException(409, "Bulgu yanıtlarının saklanan aday geçişi doğrulanamadı.")
    if state.get("authority_feedback"):
        feedback = state["authority_feedback"]
        selection = authority_proposals.AuthorityFeedbackSelection(
            **{key: feedback["dependency"][key] for key in ("context_id", "review_id", "review_sha256")},
            findings=[{"source_index": int(item["authority_id"].split(":")[1]), "dimension": item["dimension"]}
                      for item in feedback["findings"]])
        snapshot, checksum = authority_proposals.resolve(
            app, session, matter_id, row.id, state["source_version_id"], user, selection)
        if snapshot != feedback or checksum != state.get("authority_feedback_sha256"):
            raise HTTPException(409, "Seçilen kamu bulgularının tam kaynak bağı değişti.")
        selected_pass = state.get("authority_response_pass")
        iteration = next((item for item in state.get("iterations", []) if item["pass"] == selected_pass), None)
        if (state.get("candidate") and state["candidate"]["revision_comparison"]["changed_sections"]
                and selected_pass is None):
            raise HTTPException(409, "Dayanak yanıtları olmayan düzenleme adaya alınamaz.")
        if selected_pass is not None and (not iteration or iteration["outcome"] != "accepted_structural_patch"
                or iteration["patch"]["authority_responses"] != state.get("authority_responses")):
            raise HTTPException(409, "Dayanak yanıtlarının saklanan aday geçişi doğrulanamadı.")
    return row


def suggestion_view(app, session, matter_id, user, row):
    data = app.state.store.view(row)
    if authority_proposals.dependencies(data):
        try:
            with authority_proposals.scope(app, session, matter_id, user, data):
                authority_proposals.check_admission(app.state.store, session, matter_id, user, data["source_content"])
                if data.get("authority_publication_pending"):
                    raise HTTPException(409)
                return _suggestion_view(app, session, matter_id, user, row)
        except HTTPException as exc:
            if exc.status_code not in {404, 409}:
                raise
            return {key: data[key] for key in ("id", "status", "phase", "mode", "max_passes", "source_version_id",
                    "created_at", "deadline_at", "budget_seconds", "provider_pin")} | {
                "candidate": None, "can_adopt": False, "review_notes": [], "iterations": [],
                "freshness": {"status": "stale", "reasons": ["public_authority_content_withheld"],
                              "scope": "source_bound_authority_proposal"}, "public_source_access": False}
    return _suggestion_view(app, session, matter_id, user, row)


def _suggestion_view(app, session, matter_id, user, row):
    data = app.state.store.view(row)
    reasons = []
    try:
        _source(app, session, matter_id, user, data)
    except HTTPException as exc:
        if exc.status_code in {401, 404}:
            raise
        reasons.append(exc.detail)
    candidate = data.get("candidate")
    changed = bool(candidate and candidate["revision_comparison"]["changed_sections"])
    # Completed means the proposal job exited. It confers no legal review or
    # permission to apply it after its dependencies or source revision changed.
    return {**data, "freshness": {"status": "stale" if reasons else "current", "reasons": reasons,
                                 "scope": "pinned_private_analysis_and_provider_policy"},
            "can_adopt": data["status"] == "completed" and not reasons and changed
                         and not data.get("adopted_version_id") and not data.get("comparison_ref")}


def _require_job(store, session, matter_id, analysis_id, job_id, user):
    row = require_child(session, job_id, "research", matter_id, user)
    state = store.decode(row)
    if state.get("purpose") != PURPOSE or state.get("analysis_id") != analysis_id:
        raise HTTPException(404, "Bu analize ait öneri bulunamadı.")
    return row


@guard_job_write
def _progress(app, job_id, candidate, iterations, notes, responses, response_pass, authority_responses, authority_pass, *, completed=False):
    app.state.research_owner()
    store = app.state.store
    with store.session() as session, ExitStack() as guards:
        row = session.get(Record, job_id)
        user = session.get(User, row.owner_id)
        matter = require_matter(session, row.matter_id, user)
        session.refresh(matter, with_for_update=True)
        session.refresh(row, with_for_update=True)
        state = store.decode(row)
        ensure_active(state)
        guards.enter_context(authority_proposals.scope(app, session, row.matter_id, user, state))
        _source(app, session, row.matter_id, user, state)
        state.update(authority_responses=authority_responses, authority_response_pass=authority_pass,
                     authority_publication_pending=bool(authority_proposals.dependencies(state)), candidate=candidate, candidate_sha256=digest(canonical(candidate)),
                     iterations=iterations, review_notes=notes,
                     feedback_responses=responses, feedback_response_pass=response_pass)
        if completed and not state["authority_publication_pending"]:
            state.update(status="completed", phase="finished", finished_at=now())
        else:
            state["phase"] = "checked"
        store.update(row, state)
        session.commit()
        guards.close()
        _finalize_job(app, job_id, row.revision, completed=completed)


def _finalize_job(app, job_id, revision, *, completed=False):
    with app.state.store.session() as session:
        row = session.get(Record, job_id, with_for_update=True)
        if row.revision != revision:
            raise HTTPException(409, "Önerinin kayıt sırası değişti.")
        state = app.state.store.decode(row)
        if state.get("authority_publication_pending"):
            state["authority_publication_pending"] = False
            if completed:
                state.update(status="completed", phase="finished", finished_at=now())
            app.state.store.update(row, state)
            session.commit()


def run_suggestion(app, job_id):
    """Called by run_research's existing outcome handler and bounded coordinator."""
    store = app.state.store
    with store.session() as session:
        row = session.get(Record, job_id, with_for_update=True)
        state = store.decode(row)
        ensure_active(state)
        if state["status"] != "queued":
            return
        user = session.get(User, row.owner_id)
        _source(app, session, row.matter_id, user, state)
        best = _content(store, session, row.matter_id, user, draft_input(state["source_content"]), state["source_content"])
        best.update(authorship="model_proposal", authored_by=None, requested_by=user.id)
        state.update(status="running", phase="preparing")
        store.update(row, state)
        session.commit()
        matter_id = row.matter_id
    iterations, notes, responses, response_pass = [], [], [], None
    feedback = state.get("review_feedback")
    authority_feedback = state.get("authority_feedback")
    authority_responses, authority_pass = [], None
    for index in range(state["max_passes"]):
        checkpoint(app, job_id, "suggesting" if index == 0 else "repairing")
        with store.session() as session:
            user = session.get(User, row.owner_id)
            _source(app, session, matter_id, user, state)
        messages = proposal_messages(best, repair=index > 0, review_feedback=feedback, authority_feedback=authority_feedback)
        measured = prompt_measurement(messages)
        remaining = (datetime.fromisoformat(state["deadline_at"]) - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise JobStopped("timed_out")
        started = time.monotonic()
        options = {"review_feedback": feedback} if feedback else {}
        if authority_feedback:
            options["authority_feedback"] = authority_feedback
        with store.session() as session:
            user = session.get(User, row.owner_id)
            with authority_proposals.scope(app, session, matter_id, user, state):
                _source(app, session, matter_id, user, state)
                raw = app.state.provider.suggest_analysis(best, repair=index > 0, budget_seconds=min(120, remaining), **options)
        elapsed = time.monotonic() - started
        checkpoint(app, job_id, "checking")
        patch = parse_patch(raw)
        body = apply_patch(best, patch, review_feedback=feedback, authority_feedback=authority_feedback)
        with store.session() as session:
            user = session.get(User, row.owner_id)
            _source(app, session, matter_id, user, state)
            candidate = _content(store, session, matter_id, user, body, state["source_content"])
            candidate.update(authorship="model_proposal", authored_by=None, requested_by=user.id)
        introduced = sorted(critical_ids(candidate) - critical_ids(best))
        accepted = not introduced
        iterations.append({"pass": index + 1, "prompt": measured, "provider_seconds": round(elapsed, 3), "patch": patch.model_dump(),
                           "outcome": "accepted_structural_patch" if accepted else "rejected_new_critical_checks",
                           "new_critical_check_ids": introduced, "checks": candidate["checks"]})
        notes.extend({**item.model_dump(), "pass": index + 1} for item in patch.review_notes)
        if accepted:
            best = candidate
            responses = [item.model_dump() for item in patch.feedback_responses]
            response_pass = index + 1 if feedback else None
            authority_responses = [item.model_dump() for item in patch.authority_responses]
            authority_pass = index + 1 if authority_feedback else None
        _progress(app, job_id, best, iterations, notes, responses, response_pass, authority_responses, authority_pass)
        if not critical_ids(best):
            break
    _progress(app, job_id, best, iterations, notes, responses, response_pass, authority_responses, authority_pass, completed=True)


def start_suggestion(matter_id: str, analysis_id: str, body: SuggestionInput, request: Request, user=Depends(authenticate)):
    app, store = request.app, request.app.state.store
    request_value = body.model_dump(exclude={"request_id"})
    if request_value.get("comparison_ref") is None:
        request_value.pop("comparison_ref", None)
    if request_value.get("authority_feedback") is None:
        request_value.pop("authority_feedback", None)
    scope = digest(canonical(request_value))
    receipt_id = analysis_id + "-" + digest(user.id + ":" + body.request_id)[:30]
    try:
        with store.session() as session, ExitStack() as guards:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            require_child(session, analysis_id, "practice_analysis", matter_id, user)
            receipt = session.get(Record, receipt_id)
            if receipt:
                receipt = require_child(session, receipt_id, RECEIPT, matter_id, user)
                recorded = store.decode(receipt)
                if recorded["request_sha256"] != scope or receipt.owner_id != user.id:
                    raise HTTPException(409, "İstek kimliği farklı bir öneri yüküne bağlı.")
                job = _require_job(store, session, matter_id, analysis_id, recorded["job_id"], user)
                return suggestion_view(app, session, matter_id, user, job)
            row = require_child(session, analysis_id, "practice_analysis", matter_id, user)
            content = store.view(row)
            state = {"purpose": PURPOSE, "analysis_id": row.id, "source_revision": body.expected_revision,
                     "source_version_id": body.version_id, "source_content": content,
                     "source_review_id": review_pin(store, session, matter_id, row.id, body.version_id, user),
                     "source_review_recipe": analysis_reviews.RECIPE,
                     "provider_pin": provider_pin(app), "mode": body.mode,
                     "max_passes": 2 if body.mode == "repair" else 1}
            _source(app, session, matter_id, user, state)
            if body.review_feedback:
                state["review_feedback"], state["review_feedback_sha256"] = resolve_feedback(
                    store, session, matter_id, row.id, body.version_id, user, body.review_feedback)
            if body.authority_feedback:
                state["authority_feedback"], state["authority_feedback_sha256"] = authority_proposals.resolve(
                    app, session, matter_id, row.id, body.version_id, user, body.authority_feedback)
            guards.enter_context(authority_proposals.scope(app, session, matter_id, user, state))
            state["authority_publication_pending"] = bool(authority_proposals.dependencies(state))
            if body.comparison_ref:
                state.update(comparison_ref=body.comparison_ref.model_dump(), comparison_request_id=body.request_id)
                _source(app, session, matter_id, user, state)
            if not content["evidence"] or not content["applications"]:
                raise HTTPException(422, "Model önerisi için özgün pasaj ve uygulama adımı bağlayın.")
            if app.state.provider.configuration_issues():
                raise HTTPException(503, "Yerel model bağlantısı doğrulanmış değil; elle düzenleme kullanılabilir.")
            with app.state.research_jobs.reserve() as ident:
                state.update(submission(min(app.state.settings.research_budget_seconds, 120 * state["max_passes"])))
                job = store.add(session, "research", user, state, matter_id, record_id=ident)
                store.add(session, RECEIPT, user, {"job_id": ident, "request_sha256": scope,
                          "analysis_id": analysis_id}, matter_id, record_id=receipt_id)
                _audit(session, user, "analysis_suggestion_requested", ident, matter_id)
                require_matter(session, matter_id, user)
                session.commit()
                try:
                    guards.close()
                except HTTPException:
                    finish_run(store, ident, "interrupted")
                    raise HTTPException(409, "Öneri kaydedildi; son kamu izin kontrolü tamamlanamadı. Geçmişi inceleyin.") from None
                _finalize_job(app, ident, job.revision)
                session.refresh(job)
                result = suggestion_view(app, session, matter_id, user, job)
                try:
                    app.state.research_jobs.submit(ident)
                except QueueUnavailable:
                    finish_run(store, ident, "interrupted")
                    raise HTTPException(503, "Öneri hizmeti durduruluyor; saklanan isteği kontrol edin.") from None
                return result
    except QueueUnavailable as exc:
        raise HTTPException(503 if exc.closed else 429, "Araştırma kuyruğu yeni öneri kabul edemiyor.") from None


def suggestion_router():
    router = APIRouter(prefix="/api/v1/matters/{matter_id}/analyses/{analysis_id}/suggestions",
                       tags=["private-analysis-proposals"])

    router.post("", status_code=202)(start_suggestion)

    @router.get("")
    def listing(matter_id: str, analysis_id: str, request: Request, user=Depends(authenticate),
                limit: int = Query(default=10, ge=1, le=20), offset: int = Query(default=0, ge=0)):
        app, store = request.app, request.app.state.store
        with store.session() as session:
            require_child(session, analysis_id, "practice_analysis", matter_id, user)
            receipts = session.scalars(select(Record).where(
                Record.kind == RECEIPT, Record.firm_id == user.firm_id, Record.matter_id == matter_id,
                Record.id.startswith(analysis_id + "-", autoescape=True)
            ).order_by(Record.created_at.desc(), Record.id).limit(limit).offset(offset))
            return [suggestion_view(app, session, matter_id, user,
                                   _require_job(store, session, matter_id, analysis_id, store.decode(item)["job_id"], user))
                    for item in receipts if store.decode(item).get("analysis_id") == analysis_id]

    @router.get("/{job_id}")
    def status(matter_id: str, analysis_id: str, job_id: str, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        with store.session() as session:
            return suggestion_view(app, session, matter_id, user,
                                   _require_job(store, session, matter_id, analysis_id, job_id, user))

    @router.post("/{job_id}/cancel")
    def cancel(matter_id: str, analysis_id: str, job_id: str, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        request_stop(store, job_id, authorize=lambda session: _require_job(
            store, session, matter_id, analysis_id, job_id, user))
        app.state.research_jobs.cancel(job_id)
        with store.session() as session:
            return suggestion_view(app, session, matter_id, user,
                                   _require_job(store, session, matter_id, analysis_id, job_id, user))

    @router.post("/{job_id}/adopt", status_code=201)
    def adopt(matter_id: str, analysis_id: str, job_id: str, body: AdoptInput, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        app.state.research_owner()
        with store.session() as session, ExitStack() as guards:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            job = _require_job(store, session, matter_id, analysis_id, job_id, user)
            session.refresh(job, with_for_update=True)
            state = store.decode(job)
            guards.enter_context(authority_proposals.scope(app, session, matter_id, user, state))
            row = _source(app, session, matter_id, user, state)
            eligible = suggestion_view(app, session, matter_id, user, job)
            if (not eligible["can_adopt"] or body.candidate_sha256 != state.get("candidate_sha256")
                    or body.expected_revision != row.revision):
                raise HTTPException(409, "Öneri yükü veya analiz sürümü değişti; yeniden inceleyin.")
            candidate = state["candidate"]
            if digest(canonical(candidate)) != state["candidate_sha256"]:
                raise HTTPException(409, "Öneri bütünlüğü doğrulanamadı.")
            inputs = draft_input(candidate).model_copy(update={"expected_revision": body.expected_revision,
                                                              "change_note": body.change_note})
            content = _content(store, session, matter_id, user, inputs, store.view(row))
            content.update(authorship="user_with_ai_assistance", ai_assistance={
                "job_id": job.id, "source_version_id": state["source_version_id"], "recipe": RECIPE,
                "provider": state["provider_pin"], "passes": len(state["iterations"]),
                "prompts": [item["prompt"] for item in state["iterations"]],
                "review_notes": state["review_notes"],
                "adopted_by": user.id, "scope": "private_structural_proposal_not_legal_review"})
            if state.get("review_feedback"):
                content["ai_assistance"].update(
                    review_feedback=state["review_feedback"], review_feedback_sha256=state["review_feedback_sha256"],
                    feedback_responses=state["feedback_responses"], feedback_response_pass=state["feedback_response_pass"])
            if state.get("authority_feedback"):
                content["ai_assistance"].update(authority_feedback=state["authority_feedback"],
                    authority_feedback_sha256=state["authority_feedback_sha256"],
                    authority_responses=state["authority_responses"], authority_response_pass=state["authority_response_pass"])
            inherited = authority_proposals.dependencies(state)
            if inherited:
                content["authority_dependencies"] = inherited
                content["authority_contributions"] = authority_proposals.contributions(state, job.id)
                content["authority_revalidations"] = state["source_content"].get("authority_revalidations", [])
            admission = authority_proposals.prepare_admission(store, session, matter_id, user, content)
            row = _write_version(store, session, user, "practice_analysis", inputs, content, matter_id, row)
            state["adopted_version_id"] = store.decode(row)["latest_version_id"]
            store.update(job, state)
            _invalidate(store, session, matter, "Model önerisi avukat tarafından yeni taslağa alındı; yeniden inceleme gerekli.")
            _audit(session, user, "analysis_suggestion_adopted", job.id, matter_id)
            require_matter(session, matter_id, user)
            session.commit()
            guards.close()
            authority_proposals.complete_admission(store, matter_id, user, admission)
            return _view(store, session, matter_id, user, row)

    return router
