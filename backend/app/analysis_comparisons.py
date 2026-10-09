"""Registered private development comparisons; capture is never qualification.

Run existing bounded proposal jobs, retain every outcome, and separate measured
provider round trips from declared effort and unreported compute/quality metrics.
"""

from datetime import datetime
from math import isfinite
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import Field, StrictBool, StrictInt, model_validator
from sqlalchemy import select

from . import analysis_adjudication as adjudication
from . import analysis_reviews, analysis_suggestions
from .analysis_feedback import FeedbackSelection, resolve_feedback
from .auth import authenticate, require_child, require_matter
from .db import Record, User, digest, now
from .evidence_prompt import canonical
from .firm_rbac import require_permission
from .practice import StrictInput, _audit

RECIPE = "private-analysis-comparison-v1"
KIND = "analysis_comparison"
JUDGMENT = "analysis_cmp_observation"
EFFORT = "analysis_cmp_effort"
MAX_EVENTS = 60
CAPTURE_BYTES = 8 * 1024 * 1024
ARMS = {"single_pass": "single", "bounded_correction": "repair"}
Arm = Literal["single_pass", "bounded_correction"]


class Registration(StrictInput):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    expected_revision: StrictInt = Field(ge=1)
    version_id: str = Field(min_length=1, max_length=64)
    context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str = Field(min_length=3, max_length=200)
    question: str = Field(min_length=3, max_length=2000)
    rubric_text: str = Field(min_length=3, max_length=12000)
    split_family_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sample_kind: Literal["real", "synthetic"]
    reviewer_ids: list[str] = Field(min_length=2, max_length=2)
    review_feedback: FeedbackSelection | None = None

    @model_validator(mode="after")
    def distinct_reviewers(self):
        if len(set(self.reviewer_ids)) != 2 or any(not 1 <= len(item) <= 64 for item in self.reviewer_ids):
            raise ValueError("Two distinct existing reviewer identities required")
        return self


class ArmObservation(StrictInput):
    arm: Arm
    assessment: adjudication.RevisionAssessment


class ArmEffort(StrictInput):
    arm: Arm
    preparation_seconds: StrictInt | None = Field(default=None, ge=0, le=28800)
    verification_seconds: StrictInt | None = Field(default=None, ge=0, le=28800)
    correction_seconds: StrictInt | None = Field(default=None, ge=0, le=28800)


class Observation(StrictInput):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    execution_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_previous_id: str | None = Field(default=None, min_length=1, max_length=64)
    note: str = Field(min_length=3, max_length=2000)
    arms: list[ArmObservation] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def distinct_arms(self):
        if {item.arm for item in self.arms} != set(ARMS) or len(canonical(self.model_dump()).encode()) > 200000:
            raise ValueError("Both distinct comparison arms required within byte budget")
        return self


class Effort(Observation):
    arms: list[ArmEffort] = Field(min_length=2, max_length=2)
    shared_setup_included: StrictBool
    verification_and_correction_included: StrictBool


class Run(StrictInput):
    """Registered runs accept no budget, mode, provider or input override."""


def _prefix(kind, parent):
    return {KIND: "acp-", JUDGMENT: "aco-", EFFORT: "ace-"}[kind] + digest(parent)[:20] + "-"


def registration_context(app, session, matter_id, analysis_id, user):
    store = app.state.store
    row = require_child(session, analysis_id, "practice_analysis", matter_id, user)
    content = store.view(row)
    _, version = analysis_reviews._version(store, session, matter_id, analysis_id, content["latest_version_id"], user)
    review_id = analysis_reviews.review_pin(store, session, matter_id, analysis_id, content["latest_version_id"], user)
    review = store.view(require_child(session, review_id, analysis_reviews.KIND, matter_id, user)) if review_id else None
    excluded = {user.id, version["authored_by"], (review or {}).get("reviewer_id")}
    from .db import Membership

    reviewers = session.scalars(select(User).join(Membership, Membership.user_id == User.id).where(
        Membership.matter_id == matter_id, User.firm_id == user.firm_id, User.active.is_(True), User.id.not_in(excluded - {None}))
        .order_by(User.name, User.id))
    members = [{"id": item.id, "name": item.name} for item in reviewers]
    from .analysis_workbench import _freshness

    current = _freshness(store, session, matter_id, user, version["content"])["status"] == "current"
    matter = require_matter(session, matter_id, user)
    value = {"version_id": content["latest_version_id"], "expected_revision": row.revision,
        "task_input_sha256": digest(canonical(content)), "source_version_sha256": digest(canonical(version["content"])),
        "source_review_id": review_id, "source_review_sha256": digest(canonical(review)) if review else None,
        "eligible_reviewers": members, "provider_pin_sha256": digest(canonical(analysis_suggestions.provider_pin(app))),
        "provider_model": app.state.settings.provider_model, "recipe": RECIPE,
        "dimensions_sha256": digest(canonical(adjudication.DIMENSIONS)), "review_recipe": analysis_reviews.RECIPE,
        "adjudication_recipe": adjudication.RECIPE, "research_budget_seconds": app.state.settings.research_budget_seconds,
        "synthetic_only": app.state.settings.demo_mode or bool(store.decode(matter).get("synthetic")),
        "can_register": current and (not review or review["recipe"] == analysis_reviews.RECIPE)
            and store.decode(matter).get("status") != "archived" and len(members) >= 2
            and bool(content["evidence"] and content["applications"]) and not app.state.provider.configuration_issues()}
    return {**value, "context_sha256": digest(canonical(value))}


def _require(store, session, matter_id, analysis_id, ident, user):
    require_child(session, analysis_id, "practice_analysis", matter_id, user)
    row = require_child(session, ident, KIND, matter_id, user)
    data = store.decode(row)
    if data.get("analysis_id") != analysis_id:
        raise HTTPException(404, "Bu analize ait karşılaştırma bulunamadı.")
    if data["protocol_sha256"] != digest(canonical({key: value for key, value in data.items() if key != "protocol_sha256"})):
        raise HTTPException(409, "Karşılaştırma protokolünün bütünlüğü doğrulanamadı.")
    return row, data


def _current(app, session, matter_id, user, plan):
    if (plan["recipe"] != RECIPE or plan["review_recipe"] != analysis_reviews.RECIPE
            or plan["adjudication_recipe"] != adjudication.RECIPE
            or plan["dimensions_sha256"] != digest(canonical(adjudication.DIMENSIONS))
            or plan["research_budget_seconds"] != app.state.settings.research_budget_seconds):
        raise HTTPException(409, "Karşılaştırmanın ölçütleri veya bütçesi değişti.")
    analysis_suggestions._source(app, session, matter_id, user, plan)
    store = app.state.store
    analysis = require_child(session, plan["analysis_id"], "practice_analysis", matter_id, user)
    _, version = analysis_reviews._version(store, session, matter_id, plan["analysis_id"], plan["source_version_id"], user)
    review = (store.view(require_child(session, plan["source_review_id"], analysis_reviews.KIND, matter_id, user))
              if plan["source_review_id"] else None)
    if (digest(canonical(store.view(analysis))) != plan["task_input_sha256"]
            or digest(canonical(version["content"])) != plan["source_version_sha256"] or review != plan["source_review"]):
        raise HTTPException(409, "Protokolün sabit taslak veya inceleme içeriği değişti.")
    for ident in [plan["registered_by"], *plan["reviewer_ids"]]:
        reviewer = session.get(User, ident, populate_existing=True)
        try:
            if not reviewer or not reviewer.active or reviewer.firm_id != user.firm_id:
                raise HTTPException(404)
            require_matter(session, matter_id, reviewer)
            require_permission(session, reviewer, "matter.review")
        except HTTPException:
            raise HTTPException(409, "Atanmış inceleyenlerin dosya erişimi değişti.") from None


def validate_job(app, session, matter_id, user, state):
    """Lazy-called by proposal checkpoints; no new tool or provider permission."""
    ref = state["comparison_ref"]
    row, plan = _require(app.state.store, session, matter_id, state["analysis_id"], ref["id"], user)
    _current(app, session, matter_id, user, plan)
    arm = ref["arm"]
    if (row.owner_id != user.id or ref["protocol_sha256"] != plan["protocol_sha256"]
            or state.get("comparison_request_id") != plan["arms"][arm]["request_id"]
            or state["mode"] != ARMS[arm] or state["max_passes"] != plan["arms"][arm]["max_passes"]
            or digest(canonical(state["source_content"])) != plan["task_input_sha256"]
            or state.get("review_feedback_sha256") != plan.get("review_feedback_sha256")
            or ("budget_seconds" in state and state["budget_seconds"] != plan["arms"][arm]["budget_seconds"])):
        raise HTTPException(409, "Deneme kolu sabit protokol ve girdilerle eşleşmiyor.")


def _events(store, session, matter_id, ident, kind):
    rows = session.scalars(select(Record).where(Record.kind == kind, Record.matter_id == matter_id,
        Record.id.startswith(_prefix(kind, ident), autoescape=True)).order_by(Record.created_at, Record.id).limit(MAX_EVENTS + 1))
    events = [store.view(row) for row in rows if store.decode(row).get("comparison_id") == ident]
    if len(events) > MAX_EVENTS:
        raise HTTPException(409, "Deneme geçmişi kayıt sınırını aşıyor; kayıtlar sessizce atlanamaz.")
    return sorted(events, key=lambda item: item["sequence"])


def _comparison(plan, job, arm):
    before, after = plan["source_version_content"], job["candidate"]
    left, right = adjudication.target_values(before), adjudication.target_values(after)
    review = plan["source_review"]
    value = {"recipe": adjudication.RECIPE, "scope": "selected_private_evidence_only",
        "review_recipe": plan["review_recipe"], "base_version_id": plan["source_version_id"],
        "base_version": plan["source_version"], "base_content_sha256": plan["source_version_sha256"],
        "base_review_id": plan["source_review_id"], "base_review_sha256": digest(canonical(review)) if review else None,
        "candidate_version_id": "proposal:" + job["id"], "candidate_version": None,
        "candidate_content_sha256": job["candidate_sha256"], "candidate_disposition": after["checks"]["effective_disposition"],
        "targets": sorted(left.keys() | right.keys()),
        "changes": [{"target_id": key, "before": left.get(key), "after": right.get(key)}
                    for key in sorted(left.keys() | right.keys()) if left.get(key) != right.get(key)],
        "findings": [{**item, "finding_index": i} for i, item in enumerate(review["findings"] if review else [])],
        "sources": [{"source_ref": side + ":" + item["evidence_id"], **{key: item[key] for key in (
            "evidence_id", "document_id", "document_revision", "document_sha256", "name", "locator", "start", "end",
            "passage_sha256", "quote_sha256", "text")}} for side, content in (("before", before), ("after", after))
                    for item in content["evidence"]],
        "dimensions": adjudication.DIMENSIONS, "public_adverse_authority_qualified": False, "benefit_established": False,
        "candidate_kind": "unadopted_model_proposal", "arm": arm}
    return {**value, "comparison_sha256": digest(canonical(value)), "freshness": {"status": "current", "reasons": []}}


def capture(app, session, matter_id, analysis_id, ident, user):
    store = app.state.store
    row, plan = _require(store, session, matter_id, analysis_id, ident, user)
    reasons, arms = [], {}
    try:
        _current(app, session, matter_id, user, plan)
    except HTTPException as exc:
        if exc.status_code in {401, 404}:
            raise
        reasons.append(exc.detail)
    for arm, spec in plan["arms"].items():
        receipt_id = analysis_id + "-" + digest(row.owner_id + ":" + spec["request_id"])[:30]
        receipt = session.get(Record, receipt_id)
        if not receipt:
            arms[arm] = {"status": "not_started", "job": None, "comparison": None, "elapsed_seconds": None,
                         "provider_round_trip_seconds": None, "gpu_compute_seconds": None}
            continue
        receipt = require_child(session, receipt_id, analysis_suggestions.RECEIPT, matter_id, user)
        job_row = analysis_suggestions._require_job(store, session, matter_id, analysis_id, store.decode(receipt)["job_id"], user)
        job = store.view(job_row)
        if job.get("comparison_ref") != {"id": ident, "protocol_sha256": plan["protocol_sha256"], "arm": arm}:
            raise HTTPException(409, "Deneme kaydının protokol bağı doğrulanamadı.")
        operator = session.get(User, row.owner_id, populate_existing=True)
        try:
            if not operator or not operator.active:
                raise HTTPException(409, "Deneme sahibinin erişimi değişti.")
            analysis_suggestions._source(app, session, matter_id, operator, job)
        except HTTPException as exc:
            reasons.append(exc.detail if exc.status_code not in {401, 404} else "Deneme sahibinin dosya erişimi değişti.")
        complete = job["status"] == "completed" and bool(job.get("candidate"))
        if job.get("candidate") and digest(canonical(job["candidate"])) != job.get("candidate_sha256"):
            reasons.append("Saklanan deneme adayının içerik özeti değişti.")
        iterations = job.get("iterations", [])
        if len(iterations) > spec["max_passes"]:
            reasons.append("Deneme geçiş sayısı protokol bütçesini aşıyor.")
        elapsed = None
        try:
            created, registered = datetime.fromisoformat(job["created_at"]), datetime.fromisoformat(plan["registered_at"])
            if created.tzinfo is None or registered.tzinfo is None or created < registered:
                raise ValueError
            if job.get("finished_at"):
                finished_at = datetime.fromisoformat(job["finished_at"])
                if finished_at.tzinfo is None or finished_at < created:
                    raise ValueError
                elapsed = (finished_at - created).total_seconds()
        except (ValueError, TypeError, KeyError):
            reasons.append("Denemenin kayıt/başlangıç/bitiş sırası doğrulanamadı.")
        measured = bool(iterations) and all(
            type(item.get("provider_seconds")) in {int, float} and isfinite(item["provider_seconds"])
            and item["provider_seconds"] >= 0 for item in iterations)
        if complete and (elapsed is None or not measured):
            reasons.append("Tamamlanan denemenin süre veya geçiş kaydı eksik.")
            complete = False
        arms[arm] = {"status": job["status"], "job": job, "comparison": _comparison(plan, job, arm) if complete else None,
                     "elapsed_seconds": elapsed,
                     "provider_round_trip_seconds": sum(item["provider_seconds"] for item in iterations) if complete else None,
                     "gpu_compute_seconds": None}
    execution = {"recipe": RECIPE, "protocol_sha256": plan["protocol_sha256"],
                 "jobs": {arm: item["job"] for arm, item in arms.items()}}
    checksum = digest(canonical(execution))
    observations = _events(store, session, matter_id, ident, JUDGMENT)
    latest = {item["reviewer_id"]: item for item in observations}
    effort_history = _events(store, session, matter_id, ident, EFFORT)
    effort = effort_history[-1] if effort_history else None
    finished = all(item["comparison"] is not None for item in arms.values())
    current_observations = [item for reviewer, item in latest.items()
        if reviewer in plan["reviewer_ids"] and item["execution_sha256"] == checksum and finished
        and item["comparison_snapshots"] == {arm: result["comparison"] for arm, result in arms.items()}
        and all(observed["assessment"]["comparison_sha256"] == arms[observed["arm"]]["comparison"]["comparison_sha256"]
                for observed in item["arms"])]
    effort_current = bool(effort and effort["execution_sha256"] == checksum)
    accounted = bool(effort_current and effort["shared_setup_included"] and effort["verification_and_correction_included"]
        and all(all(item[key] is not None for key in ("preparation_seconds", "verification_seconds", "correction_seconds"))
                and sum(item[key] for key in ("preparation_seconds", "verification_seconds", "correction_seconds")) > 0
                for item in effort["arms"]))
    result = {"id": row.id, "protocol": plan, "execution_sha256": checksum, "arms": arms,
            "freshness": {"status": "stale" if reasons else "current", "reasons": list(dict.fromkeys(reasons))},
            "observations": observations, "effort_history": effort_history,
            "current_reviewer_count": len(current_observations), "effort_accounted": accounted,
            "capture_complete": not reasons and finished and len(current_observations) == 2 and accounted,
            "can_run": row.owner_id == user.id and not reasons and any(item["status"] == "not_started" for item in arms.values()),
            "can_observe": user.id in plan["reviewer_ids"] and not reasons and finished,
            "can_record_effort": row.owner_id == user.id and not reasons and finished,
            "previous_observation_id": latest.get(user.id, {}).get("id"), "previous_effort_id": effort["id"] if effort else None,
            "sample_kind": plan["sample_kind"], "qualification_granted": False, "benefit_established": False,
            "exported_at": now()}
    if len(canonical(result).encode()) > CAPTURE_BYTES:
        raise HTTPException(409, "Özel deneme paketi 8 MiB sınırını aşıyor; kayıtlar sessizce atlanamaz.")
    return result


def comparison_router():
    router = APIRouter(prefix="/api/v1/matters/{matter_id}/analyses/{analysis_id}/comparisons",
                       tags=["private-analysis-comparisons"])

    @router.post("", status_code=201)
    def register(matter_id: str, analysis_id: str, body: Registration, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        ident = _prefix(KIND, analysis_id) + digest(user.id + ":" + body.request_id)[:32]
        request_sha = digest(canonical(body.model_dump(exclude={"request_id"})))
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            require_child(session, analysis_id, "practice_analysis", matter_id, user)
            old = session.get(Record, ident)
            if old:
                old, data = _require(store, session, matter_id, analysis_id, ident, user)
                if old.owner_id != user.id or data["request_sha256"] != request_sha:
                    raise HTTPException(409, "İstek kimliği farklı bir protokole bağlı.")
                return capture(app, session, matter_id, analysis_id, ident, user)
            context = registration_context(app, session, matter_id, analysis_id, user)
            if not context["can_register"] or body.context_sha256 != context["context_sha256"]:
                raise HTTPException(409, "Deneme bağlamı değişti veya iki uygun inceleyen yok; yeniden açın.")
            analysis = require_child(session, analysis_id, "practice_analysis", matter_id, user)
            content = store.view(analysis)
            version, snapshot = analysis_reviews._version(store, session, matter_id, analysis_id, body.version_id, user)
            review_id = analysis_reviews.review_pin(store, session, matter_id, analysis_id, body.version_id, user)
            review = store.view(require_child(session, review_id, analysis_reviews.KIND, matter_id, user)) if review_id else None
            excluded = {user.id, snapshot["authored_by"], (review or {}).get("reviewer_id")}
            if excluded & set(body.reviewer_ids):
                raise HTTPException(422, "İki inceleyen protokol sahibi, taslak yazarı ve önceki inceleyenden farklı olmalıdır.")
            data = {**body.model_dump(exclude={"request_id", "expected_revision", "version_id", "review_feedback"}),
                    "analysis_id": analysis_id, "recipe": RECIPE, "review_recipe": analysis_reviews.RECIPE,
                    "adjudication_recipe": adjudication.RECIPE, "dimensions_sha256": digest(canonical(adjudication.DIMENSIONS)),
                    "request_sha256": request_sha, "registered_at": now(), "registered_by": user.id,
                    "scope": "private_development_comparison_only", "rubric_sha256": digest(body.rubric_text),
                    "source_revision": body.expected_revision, "source_version_id": version.id,
                    "source_content": content, "task_input_sha256": digest(canonical(content)),
                    "source_version_content": snapshot["content"], "source_version": snapshot["version"],
                    "source_version_sha256": digest(canonical(snapshot["content"])),
                    "source_review_id": review_id, "source_review": review,
                    "source_review_recipe": analysis_reviews.RECIPE,
                    "provider_pin": analysis_suggestions.provider_pin(app),
                    "research_budget_seconds": app.state.settings.research_budget_seconds,
                    "arms": {arm: {"request_id": digest(ident + ":" + arm)[:32], "mode": mode,
                                   "max_passes": 1 if mode == "single" else 2,
                                   "budget_seconds": min(app.state.settings.research_budget_seconds, 120 if mode == "single" else 240)}
                             for arm, mode in ARMS.items()}, "immutable": True}
            if app.state.settings.demo_mode or store.decode(matter).get("synthetic"):
                if body.sample_kind != "synthetic":
                    raise HTTPException(422, "Örnek ortam gerçek örnek olarak kaydedilemez.")
            if body.review_feedback:
                data["review_feedback"], data["review_feedback_sha256"] = resolve_feedback(
                    store, session, matter_id, analysis_id, version.id, user, body.review_feedback)
            _current(app, session, matter_id, user, data)
            if not content["evidence"] or not content["applications"]:
                raise HTTPException(422, "Deneme için özgün pasaj ve uygulama adımı bağlayın.")
            if app.state.provider.configuration_issues():
                raise HTTPException(503, "Yerel model yapılandırması doğrulanmış değil.")
            data["protocol_sha256"] = digest(canonical(data))
            store.add(session, KIND, user, data, matter_id, record_id=ident)
            _audit(session, user, "analysis_comparison_registered", ident, matter_id)
            result = capture(app, session, matter_id, analysis_id, ident, user)
            session.commit()
            return result

    @router.get("")
    def listing(matter_id: str, analysis_id: str, request: Request, user=Depends(authenticate),
                limit: int = Query(default=10, ge=1, le=20), offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            require_child(session, analysis_id, "practice_analysis", matter_id, user)
            rows = session.scalars(select(Record).where(Record.kind == KIND, Record.firm_id == user.firm_id,
                Record.matter_id == matter_id, Record.id.startswith(_prefix(KIND, analysis_id), autoescape=True))
                .order_by(Record.created_at.desc(), Record.id).limit(limit).offset(offset))
            return [{"id": row.id, "title": store.decode(row)["title"], "registered_at": store.decode(row)["registered_at"]}
                    for row in rows if store.decode(row).get("analysis_id") == analysis_id]

    @router.get("/registration-context")
    def context(matter_id: str, analysis_id: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            return registration_context(request.app, session, matter_id, analysis_id, user)

    @router.get("/{comparison_id}")
    def detail(matter_id: str, analysis_id: str, comparison_id: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            return capture(request.app, session, matter_id, analysis_id, comparison_id, user)

    @router.get("/{comparison_id}/export")
    def export(matter_id: str, analysis_id: str, comparison_id: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            value = capture(request.app, session, matter_id, analysis_id, comparison_id, user)
            return Response(canonical(value), media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="private-comparison-{value["id"]}.json"'})

    @router.post("/{comparison_id}/run", status_code=202)
    def run(matter_id: str, analysis_id: str, comparison_id: str, request: Request,
            body: Run = Body(default=Run()), user=Depends(authenticate)):
        app = request.app
        with app.state.store.session() as session:
            row, plan = _require(app.state.store, session, matter_id, analysis_id, comparison_id, user)
            if row.owner_id != user.id:
                raise HTTPException(403, "Denemeyi yalnız protokol sahibi başlatabilir.")
            _current(app, session, matter_id, user, plan)
        # Separate existing reservations; a partial admission is visible and a retry
        # uses the same permanent receipts. Never silently rerun a stopped arm.
        for arm, spec in plan["arms"].items():
            body = {"expected_revision": plan["source_revision"], "version_id": plan["source_version_id"],
                    "request_id": spec["request_id"], "mode": spec["mode"],
                    "comparison_ref": {"id": comparison_id, "protocol_sha256": plan["protocol_sha256"], "arm": arm}}
            if plan.get("review_feedback"):
                body["review_feedback"] = {"review_id": plan["review_feedback"]["review_id"],
                                           "finding_indices": [item["index"] for item in plan["review_feedback"]["findings"]]}
            analysis_suggestions.start_suggestion(matter_id, analysis_id,
                analysis_suggestions.SuggestionInput.model_validate(body), request, user)
        with app.state.store.session() as session:
            return capture(app, session, matter_id, analysis_id, comparison_id, user)

    def append(kind, matter_id, analysis_id, ident, body, request, user):
        app, store = request.app, request.app.state.store
        event_id = _prefix(kind, ident) + digest(user.id + ":" + body.request_id)[:32]
        checksum = digest(canonical(body.model_dump(exclude={"request_id"})))
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            _require(store, session, matter_id, analysis_id, ident, user)
            existing = session.get(Record, event_id)
            if existing:
                existing = require_child(session, event_id, kind, matter_id, user)
                if existing.owner_id != user.id or store.decode(existing)["request_sha256"] != checksum:
                    raise HTTPException(409, "İstek kimliği farklı bir gözleme bağlı.")
                return store.view(existing)
            view = capture(app, session, matter_id, analysis_id, ident, user)
            key = "can_observe" if kind == JUDGMENT else "can_record_effort"
            if not view[key]:
                raise HTTPException(409, "Güncel iki tamamlanmış kol ve atanmış gözlemci gerekli.")
            previous = view["previous_observation_id" if kind == JUDGMENT else "previous_effort_id"]
            if body.expected_previous_id != previous or body.execution_sha256 != view["execution_sha256"]:
                raise HTTPException(409, "Deneme veya önceki gözlem değişti; yeniden açın.")
            if kind == JUDGMENT:
                for item in body.arms:
                    adjudication.validate_assessment(item.assessment, view["arms"][item.arm]["comparison"],
                                                     view["arms"][item.arm]["job"]["candidate"], "changes_requested")
            history = view["observations" if kind == JUDGMENT else "effort_history"]
            if len(history) >= MAX_EVENTS:
                raise HTTPException(409, "Bu denemenin gözlem/süre geçmişi doldu; önceki kayıtlar korunur.")
            own_history = [item for item in history if item["reviewer_id"] == user.id]
            data = {**body.model_dump(exclude={"request_id"}),
                "comparison_id": ident, "reviewer_id": user.id, "reviewer_name": user.name,
                "sequence": max((item["sequence"] for item in own_history), default=0) + 1,
                "request_sha256": checksum, "immutable": True, "qualification_granted": False}
            if kind == JUDGMENT:
                data["comparison_snapshots"] = {arm: item["comparison"] for arm, item in view["arms"].items()}
            event = store.add(session, kind, user, data, matter_id, record_id=event_id)
            _audit(session, user, "analysis_comparison_observation" if kind == JUDGMENT else "analysis_comparison_effort", event_id, matter_id)
            final = capture(app, session, matter_id, analysis_id, ident, user)
            if not final[key] or final["execution_sha256"] != body.execution_sha256:
                raise HTTPException(409, "Gözlem kaydı sırasında denemenin dayanakları değişti.")
            session.commit()
            return store.view(event)

    @router.post("/{comparison_id}/observations", status_code=201)
    def observe(matter_id: str, analysis_id: str, comparison_id: str, body: Observation,
                request: Request, user=Depends(authenticate)):
        return append(JUDGMENT, matter_id, analysis_id, comparison_id, body, request, user)

    @router.post("/{comparison_id}/effort", status_code=201)
    def effort(matter_id: str, analysis_id: str, comparison_id: str, body: Effort,
               request: Request, user=Depends(authenticate)):
        return append(EFFORT, matter_id, analysis_id, comparison_id, body, request, user)

    return router
