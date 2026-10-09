"""Registration-before-revision, fixed-evidence human trials; never a model benchmark."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import Field, StrictBool, model_validator
from sqlalchemy import func, select

from . import analysis_authorities as authorities
from . import analysis_reviews, analysis_workbench
from . import authority_adjudications as adjudications
from . import authority_comparisons as comparisons
from . import authority_findings as findings
from .analysis_comparisons import ArmEffort
from .auth import authenticate, require_child, require_matter
from .db import Membership, Record, User, digest, now
from .evidence_prompt import canonical
from .firm_rbac import require_permission
from .practice import StrictInput, _audit

RECIPE = "registered-human-authority-revision-v1"
KIND = "authority_trial"
CAPTURE = "authority_trial_capture"
HEAD = "authority_trial_head"
ADMISSION = "authority_trial_admission"
MAX_BYTES = 12 * 1024 * 1024
MAX_RECORDS = 60
INPUT_KEYS = (
    "issue",
    "posture",
    "event_date",
    "evidence",
    "premises",
    "fact_snapshots",
    "source_snapshots",
    "contradiction_snapshots",
)


class Registration(StrictInput):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str = Field(min_length=3, max_length=200)
    question: str = Field(min_length=3, max_length=2000)
    split_family_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sample_kind: Literal["real", "synthetic"]
    reviewer_ids: list[str] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def distinct(self):
        if (
            len(self.title.strip()) < 3
            or len(self.question.strip()) < 3
            or len(set(self.reviewer_ids)) != 2
            or any(not 1 <= len(item) <= 64 for item in self.reviewer_ids)
        ):
            raise ValueError("Explain the question and select two distinct existing accounts")
        return self


class TrialEffort(ArmEffort):
    arm: Literal["original", "revised"]


class CaptureInput(StrictInput):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    expected_basis_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_capture_id: str | None = Field(default=None, min_length=1, max_length=64)
    comparison_id: str = Field(min_length=1, max_length=64)
    adjudication_ids: list[str] = Field(default_factory=list, max_length=2)
    note: str = Field(min_length=3, max_length=2000)
    arms: list[TrialEffort] = Field(min_length=2, max_length=2)
    shared_setup_included: StrictBool
    verification_and_correction_included: StrictBool
    non_overlapping_active_time: StrictBool

    @model_validator(mode="after")
    def bounded(self):
        if (
            len(self.note.strip()) < 3
            or {item.arm for item in self.arms} != {"original", "revised"}
            or len(set(self.adjudication_ids)) != len(self.adjudication_ids)
            or any(not 1 <= len(item) <= 64 for item in self.adjudication_ids)
            or len(canonical(self.model_dump()).encode()) > 16 * 1024
        ):
            raise ValueError("Distinct bounded records and both explicit effort arms required")
        return self


class Preview(StrictInput):
    comparison_id: str = Field(min_length=1, max_length=64)
    adjudication_ids: list[str] = Field(default_factory=list, max_length=2)


def _bounded(value):
    if len(canonical(value).encode()) + 2048 > MAX_BYTES:
        raise HTTPException(409, "Deneme paketi 12 MiB sınırını aşıyor; kayıtlar atlanamaz.")
    return value


def _prefix(parent):
    return "atr-" + digest(parent)[:24] + "-"


def _head_id(ident):
    return "ath-" + digest(ident)[:32]


def _admission_id(ident):
    return "ata-" + digest(ident)[:32]


def _inputs(content):
    return {key: content[key] for key in INPUT_KEYS}


def _basis(app, session, route, user):
    store = app.state.store
    matter, analysis, context, review = route
    value = findings._view(app, session, *route, user)
    if not value["public_source_access"] or not value["snapshot"]:
        raise HTTPException(409, "Özgün dayanak incelemesi bekletiliyor.")
    source = value["snapshot"]
    manifest = source["context_snapshot"]["manifest"]
    version, data = analysis_reviews._version(store, session, matter, analysis, manifest["version_id"], user)
    pin = analysis_reviews.review_pin(store, session, matter, analysis, version.id, user)
    private = authorities._basis(store, session, matter, analysis, data["content"], user, pin)
    current_context = authorities._view(app, session, *route[:3], user)
    if not current_context["public_source_access"]:
        raise HTTPException(409, "Kamu kaynakları bekletiliyor.")
    reasons = [reason for reason in value["freshness"]["reasons"] if reason != "authority_context_changed"]
    reasons += [
        reason
        for reason in current_context["freshness"]["reasons"]
        if reason not in {"private_analysis_changed", "research_record_changed"}
    ]
    if (
        comparisons._without_analysis(private, analysis)
        != comparisons._without_analysis(manifest["private_basis"], analysis)
        or pin != manifest["analysis_review_id"]
        or digest(canonical(data["content"])) != manifest["analysis_content_sha256"]
        or analysis_workbench._freshness(store, session, matter, user, data["content"])["status"] != "current"
    ):
        reasons.append("registered_private_inputs_changed")
    public = findings._public_data(app, session, *route[:3], user)
    # Saving a private analysis marks its preparation product stale. Only this exact
    # existing transition is expected; all other product changes remain in the seal.
    if public.get("status") == "stale" and public.get("stale_reason") == (
        "Avukatın yapılandırılmış analizi değişti; hazırlık bağlamını inceleyin."
    ):
        public = {**public, "status": "needs_review"}
        public.pop("stale_reason")
    basis = {
        "recipe": RECIPE,
        "review_recipe": findings.RECIPE,
        "comparison_recipe": comparisons.RECIPE,
        "adjudication_recipe": adjudications.RECIPE,
        "rubric": adjudications.DIMENSIONS,
        "finding_dimensions": findings.DIMENSIONS,
        "review": source,
        "baseline_version_id": version.id,
        "baseline_author_id": version.owner_id,
        "baseline_content": data["content"],
        "input_sha256": digest(canonical(_inputs(data["content"]))),
        "public_product_sha256": digest(canonical(public)),
    }
    return _bounded(basis), sorted(set(reasons))


def registration_context(app, session, route, user):
    store = app.state.store
    basis, reasons = _basis(app, session, route, user)
    analysis = require_child(session, route[1], "practice_analysis", route[0], user)
    excluded = {user.id, basis["baseline_author_id"], basis["review"]["reviewer_id"]}
    members = session.scalars(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.matter_id == route[0],
            User.firm_id == user.firm_id,
            User.active.is_(True),
            User.role.in_(["lawyer", "admin"]),
            User.id.not_in(excluded),
        )
        .order_by(User.name, User.id)
    )
    reviewers = [{"id": item.id, "name": item.name} for item in members]
    original_current = (
        store.decode(analysis)["latest_version_id"] == basis["baseline_version_id"]
        and findings._view(app, session, *route, user)["freshness"]["status"] == "current"
    )
    matter = store.decode(require_matter(session, route[0], user))
    value = {
        "basis": basis,
        "eligible_reviewers": reviewers,
        "excluded_account_ids": sorted(excluded),
        "synthetic_only": app.state.settings.demo_mode or bool(matter.get("synthetic")),
        "can_register": original_current
        and not reasons
        and len(reviewers) >= 2
        and matter.get("status") != "archived"
        and not basis["baseline_content"].get("ai_assistance"),
        "reasons": reasons,
        "registration_before_revision": True,
        "model_benchmark": False,
    }
    return _bounded({**value, "context_sha256": digest(canonical(value))})


def _require(store, session, route, ident, user, kind=KIND, plan_id=None):
    require_child(session, route[1], "practice_analysis", route[0], user)
    row = require_child(session, ident, kind, route[0], user)
    data = store.decode(row)
    proof_row = require_child(session, _admission_id(ident), ADMISSION, route[0], user)
    proof = store.decode(proof_row)
    if (
        data.get("route") != list(route)
        or data.get("recipe") != RECIPE
        or data.get("sha256") != digest(canonical({k: v for k, v in data.items() if k != "sha256"}))
        or data.get("owner_id") != row.owner_id
        or proof_row.owner_id != row.owner_id
        or proof.get("id") != ident
        or proof.get("sha256") != data["sha256"]
        or (plan_id is not None and data.get("trial_id") != plan_id)
    ):
        raise HTTPException(409, "Deneme kaydının bütünlüğü doğrulanamadı.")
    return row, data, proof


def _head(store, session, route, ident, user):
    row = session.get(Record, _head_id(ident), populate_existing=True)
    if not row:
        return None
    require_child(session, row.id, HEAD, route[0], user)
    value = store.decode(row)
    if value.get("trial_id") != ident:
        raise HTTPException(409, "Deneme sırası doğrulanamadı.")
    _, latest, _ = _require(store, session, route, value["latest_id"], user, CAPTURE, ident)
    if latest["sequence"] != value.get("sequence"):
        raise HTTPException(409, "Deneme sırası eşleşmiyor.")
    return value


def _current(app, session, route, plan, user):
    basis, reasons = _basis(app, session, route, user)
    if basis != plan["basis"]:
        reasons.append("registered_basis_changed")
    for ident in [
        plan["owner_id"],
        plan["basis"]["baseline_author_id"],
        plan["basis"]["review"]["reviewer_id"],
        *plan["reviewer_ids"],
    ]:
        member = session.get(User, ident, populate_existing=True)
        try:
            if not member or member.role not in {"lawyer", "admin"}:
                raise HTTPException(403)
            require_matter(session, route[0], member)
            require_permission(session, member, "matter.review")
        except HTTPException:
            reasons.append("participant_access_changed")
    return sorted(set(reasons))


def _later(value, registered):
    try:
        stamp, start = datetime.fromisoformat(value), datetime.fromisoformat(registered)
        return stamp.tzinfo is not None and start.tzinfo is not None and stamp >= start
    except (TypeError, ValueError):
        return False


def capture_basis(app, session, route, ident, selected, user):
    store = app.state.store
    _, plan, proof = _require(store, session, route, ident, user)
    reasons = _current(app, session, route, plan, user)
    if not proof.get("publication_guard_completed") or reasons:
        raise HTTPException(
            409, {"reason": "Protokol bağları güncel değil veya kayıt tamamlanmadı.", "changes": reasons}
        )
    view = comparisons._view(app, session, *route, selected.comparison_id, user)
    if not view["public_source_access"] or view["freshness"]["status"] != "current":
        raise HTTPException(409, "Güncel, izinli bir karşılaştırma gerekli.")
    comp = view["snapshot"]
    candidate_row, candidate = analysis_reviews._version(
        store, session, route[0], route[1], comp["comparison_snapshot"]["candidate_version_id"], user
    )
    if (
        not _later(candidate_row.created_at, plan["registered_at"])
        or not _later(comp["recorded_at"], plan["registered_at"])
        or comp["comparison_snapshot"]["base_version_id"] != plan["basis"]["baseline_version_id"]
        or candidate.get("content", {}).get("ai_assistance")
        or digest(canonical(_inputs(candidate["content"]))) != plan["basis"]["input_sha256"]
    ):
        raise HTTPException(409, "Aday kayıt sonrası oluşturulmalı; aynı olgu, öncül ve alıntılar korunmalı.")
    if {candidate_row.owner_id, comp["reviewer_id"]} & set(plan["reviewer_ids"]):
        raise HTTPException(409, "Atanmış inceleyen aday veya karşılaştırma yazarı olamaz.")
    observed = []
    for key in selected.adjudication_ids:
        item = adjudications._view(app, session, (*route, selected.comparison_id), key, user)
        if not item["public_source_access"] or item["freshness"]["status"] != "current":
            raise HTTPException(409, "Seçilen ayrı görüş güncel değil veya bekletiliyor.")
        data = item["snapshot"]
        if data["reviewer_id"] not in plan["reviewer_ids"] or not _later(
            data["recorded_at"], comp["recorded_at"]
        ):
            raise HTTPException(
                422, "Yalnız iki atanmış hesaptan bu karşılaştırmaya ait ayrı görüşler seçilebilir."
            )
        # The shared comparison is stored once; explicit seals retain the full upstream basis identity.
        observed.append(
            {
                "id": key,
                **{
                    k: data[k]
                    for k in (
                        "reviewer_id",
                        "reviewer_name",
                        "sequence",
                        "recorded_at",
                        "adjudication_sha256",
                        "basis_sha256",
                        "assessment",
                        "coverage",
                    )
                },
            }
        )
    if len({item["reviewer_id"] for item in observed}) != len(observed):
        raise HTTPException(422, "Her atanmış hesaptan en fazla bir görüş seçin.")
    observed.sort(key=lambda item: item["reviewer_id"])
    basis = _bounded(
        {
            "trial_sha256": plan["sha256"],
            "comparison_id": selected.comparison_id,
            "comparison": comp,
            "observations": observed,
        }
    )
    head = _head(store, session, route, ident, user)
    return {
        "basis": basis,
        "basis_sha256": digest(canonical(basis)),
        "expected_capture_id": head["latest_id"] if head else None,
        "can_record": plan["owner_id"] == user.id
        and store.decode(require_matter(session, route[0], user)).get("status") != "archived",
    }


def _disagreement(observations):
    if len(observations) != 2:
        return {"semantic_dimensions": None, "finding_dimensions": None}

    def outcomes(item, group):
        return {
            (row.get("source_index"), row["dimension"]): row["outcome"] for row in item["assessment"][group]
        }

    left, right = observations
    return {
        label: sum(value != outcomes(right, group).get(key) for key, value in outcomes(left, group).items())
        for label, group in (("semantic_dimensions", "observations"), ("finding_dimensions", "judgments"))
    }


def _view(app, session, route, ident, user, capture_id=None):
    store = app.state.store
    row, plan, proof = _require(store, session, route, ident, user)
    head = _head(store, session, route, ident, user)
    capture_id = capture_id or (head["latest_id"] if head else None)
    event, event_proof = None, None
    if capture_id:
        _, event, event_proof = _require(store, session, route, capture_id, user, CAPTURE, ident)
    result = {
        "id": ident,
        "registered_at": plan["registered_at"],
        "owner_id": row.owner_id,
        "protocol_sha256": plan["sha256"],
        "capture_id": capture_id,
        "protocol": None,
        "snapshot": None,
        "public_source_access": False,
        "freshness": {"status": "withheld", "reasons": ["post_commit_authorization_pending"]},
        "capture_complete": False,
        "qualification_granted": False,
        "benefit_established": False,
        "model_benchmark": False,
        "can_record": False,
        "capture_sha256": event["sha256"] if event else None,
    }
    if not proof.get("publication_guard_completed") or (
        event and not event_proof.get("publication_guard_completed")
    ):
        return result
    try:
        with authorities._guard(app, findings._public_data(app, session, *route[:3], user)):
            reasons = _current(app, session, route, plan, user)
            protocol_reasons = list(reasons)
            if event:
                try:
                    current = capture_basis(
                        app,
                        session,
                        route,
                        ident,
                        Preview(
                            comparison_id=event["basis"]["comparison_id"],
                            adjudication_ids=[item["id"] for item in event["basis"]["observations"]],
                        ),
                        user,
                    )
                    if current["basis_sha256"] != event["basis_sha256"]:
                        reasons.append("capture_dependencies_changed")
                except HTTPException:
                    # Inspect the original sources first; permission denial hides every free-text field.
                    public = comparisons._view(app, session, *route, event["basis"]["comparison_id"], user)
                    if not public["public_source_access"]:
                        raise HTTPException(409)
                    for observation in event["basis"]["observations"]:
                        current_observation = adjudications._view(
                            app, session, (*route, event["basis"]["comparison_id"]), observation["id"], user
                        )
                        if not current_observation["public_source_access"]:
                            raise HTTPException(409)
                    reasons.append("capture_dependencies_changed")
                if not head or head["latest_id"] != capture_id:
                    reasons.append("newer_trial_capture_exists")
            result.update(
                protocol=plan,
                snapshot=event,
                public_source_access=True,
                freshness={"status": "stale" if reasons else "current", "reasons": sorted(set(reasons))},
                capture_complete=bool(event and event["capture_complete"] and not reasons),
                can_record=row.owner_id == user.id
                and not protocol_reasons
                and store.decode(require_matter(session, route[0], user)).get("status") != "archived",
            )
        require_child(session, ident, KIND, route[0], user)
        return _bounded(result)
    except HTTPException as exc:
        if exc.status_code not in {404, 409}:
            raise
        require_child(session, ident, KIND, route[0], user)
        result.update(
            protocol=None,
            snapshot=None,
            public_source_access=False,
            can_record=False,
            capture_complete=False,
            freshness={"status": "withheld", "reasons": ["source_context_unavailable"]},
        )
        return result


def _write(app, route, body, user, trial_id=None):
    store = app.state.store
    kind = CAPTURE if trial_id else KIND
    ident = _prefix(trial_id or route[-1]) + digest(user.id + ":" + body.request_id)[:32]
    request_sha = digest(canonical(body.model_dump(exclude={"request_id"})))
    committed = False
    try:
        with store.session() as session:
            matter = require_matter(session, route[0], user)
            session.refresh(matter, with_for_update=True)
            findings._lawyer(session, route[0], user)
            if session.get(Record, ident):
                _, old, _ = _require(store, session, route, ident, user, kind, trial_id)
                if old["owner_id"] != user.id or old["request_sha256"] != request_sha:
                    raise HTTPException(409, "İstek kimliği farklı içeriğe bağlı.")
                return _view(app, session, route, trial_id or ident, user, ident if trial_id else None)
            with authorities._guard(app, findings._public_data(app, session, *route[:3], user)):
                if trial_id:
                    current = capture_basis(app, session, route, trial_id, body, user)
                    if not current["can_record"]:
                        raise HTTPException(403, "Yalnız protokol sahibi kayıt oluşturabilir.")
                    if (
                        current["basis_sha256"] != body.expected_basis_sha256
                        or current["expected_capture_id"] != body.expected_capture_id
                    ):
                        raise HTTPException(409, "Girdiler veya kayıt sırası değişti; yeniden açın.")
                    accounted = (
                        body.shared_setup_included
                        and body.verification_and_correction_included
                        and body.non_overlapping_active_time
                        and all(
                            all(
                                getattr(arm, k) is not None
                                for k in ("preparation_seconds", "verification_seconds", "correction_seconds")
                            )
                            and sum(
                                getattr(arm, k)
                                for k in ("preparation_seconds", "verification_seconds", "correction_seconds")
                            )
                            > 0
                            for arm in body.arms
                        )
                    )
                    head = _head(store, session, route, trial_id, user)
                    data = {
                        "trial_id": trial_id,
                        "basis": current["basis"],
                        "basis_sha256": current["basis_sha256"],
                        "assessment": body.model_dump(
                            exclude={"request_id", "expected_basis_sha256", "expected_capture_id"}
                        ),
                        "sequence": head["sequence"] + 1 if head else 1,
                        "previous_capture_id": body.expected_capture_id,
                        "effort_accounted": bool(accounted),
                        "capture_complete": bool(accounted and len(current["basis"]["observations"]) == 2),
                        "disagreement": _disagreement(current["basis"]["observations"]),
                    }
                else:
                    current = registration_context(app, session, route, user)
                    if not current["can_register"] or body.context_sha256 != current["context_sha256"]:
                        raise HTTPException(
                            409, "Kayıt öncesi girdileri yenileyin; revizyondan önce kayıt gerekli."
                        )
                    if not set(body.reviewer_ids) <= {item["id"] for item in current["eligible_reviewers"]}:
                        raise HTTPException(422, "İki uygun ve ayrı avukat hesabı seçin.")
                    if current["synthetic_only"] and body.sample_kind != "synthetic":
                        raise HTTPException(422, "Örnek ortam gerçek örnek olarak kaydedilemez.")
                    data = {
                        **body.model_dump(exclude={"request_id", "context_sha256"}),
                        "basis": current["basis"],
                        "registered_at": now(),
                        "registration_before_revision": True,
                        "registration_before_baseline": False,
                        "workflow": "human_revision_fixed_evidence",
                        "blind_review": False,
                        "account_separation_only": True,
                        "model_benchmark": False,
                    }
                count = session.scalar(
                    select(func.count())
                    .select_from(Record)
                    .where(
                        Record.kind == kind,
                        Record.matter_id == route[0],
                        Record.id.startswith(_prefix(trial_id or route[-1])),
                    )
                )
                if count >= MAX_RECORDS:
                    raise HTTPException(409, "Bu girdinin 60 kayıt sınırına ulaşıldı.")
                data.update(
                    route=list(route),
                    recipe=RECIPE,
                    owner_id=user.id,
                    recorded_at=now(),
                    request_sha256=request_sha,
                    immutable=True,
                    qualification_granted=False,
                    benefit_established=False,
                    legal_approval="not_granted",
                    model_use="none",
                )
                data["sha256"] = digest(canonical(data))
                _bounded(data)
                if trial_id:
                    _, plan, _ = _require(store, session, route, trial_id, user)
                    _bounded({"protocol": plan, "snapshot": data})
                store.add(session, kind, user, data, route[0], record_id=ident)
                store.add(
                    session,
                    ADMISSION,
                    user,
                    {"id": ident, "sha256": data["sha256"], "publication_guard_completed": False},
                    route[0],
                    record_id=_admission_id(ident),
                )
                if trial_id:
                    pointer = {"trial_id": trial_id, "latest_id": ident, "sequence": data["sequence"]}
                    existing = session.get(Record, _head_id(trial_id))
                    if existing:
                        store.update(existing, pointer)
                    else:
                        store.add(session, HEAD, user, pointer, route[0], record_id=_head_id(trial_id))
                _audit(
                    session,
                    user,
                    "authority_trial_" + ("captured" if trial_id else "registered"),
                    ident,
                    route[0],
                )
                session.flush()
                session.expire_all()
                final = (
                    capture_basis(app, session, route, trial_id, body, user)
                    if trial_id
                    else registration_context(app, session, route, user)
                )
                if (
                    trial_id
                    and (
                        not final["can_record"]
                        or final["basis_sha256"] != body.expected_basis_sha256
                        or final["expected_capture_id"] != ident
                    )
                ) or (not trial_id and final != current):
                    raise HTTPException(409, "Kayıt sırasında girdiler değişti.")
                findings._lawyer(session, route[0], user)
                session.commit()
                committed = True
        with store.session() as session:
            matter = require_matter(session, route[0], user)
            session.refresh(matter, with_for_update=True)
            _, _, proof = _require(store, session, route, ident, user, kind, trial_id)
            findings._lawyer(session, route[0], user)
            row = session.get(Record, _admission_id(ident))
            store.update(row, {**proof, "publication_guard_completed": True})
            session.commit()
        with store.session() as session:
            return _view(app, session, route, trial_id or ident, user, ident if trial_id else None)
    except Exception:
        if not committed:
            raise
        return JSONResponse(
            status_code=409,
            content={"outcome": "committed_needs_revalidation", "id": ident, "needs_revalidation": True},
        )


def authority_trials_router():
    router = APIRouter(
        prefix="/api/v1/matters/{matter_id}/analyses/{analysis_id}/authority-contexts/{context_id}/reviews/{review_id}/trials",
        tags=["registered-human-authority-trials"],
    )

    def route(matter_id, analysis_id, context_id, review_id):
        return matter_id, analysis_id, context_id, review_id

    @router.get("/registration-context")
    def registration(
        matter_id: str,
        analysis_id: str,
        context_id: str,
        review_id: str,
        request: Request,
        user=Depends(authenticate),
    ):
        app = request.app
        values = route(matter_id, analysis_id, context_id, review_id)
        with app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            findings._lawyer(session, matter_id, user)
            with authorities._guard(app, findings._public_data(app, session, *values[:3], user)):
                result = registration_context(app, session, values, user)
            findings._lawyer(session, matter_id, user)
            return result

    @router.post("", status_code=201)
    def register(
        matter_id: str,
        analysis_id: str,
        context_id: str,
        review_id: str,
        body: Registration,
        request: Request,
        user=Depends(authenticate),
    ):
        return _write(request.app, route(matter_id, analysis_id, context_id, review_id), body, user)

    @router.get("")
    def listing(
        matter_id: str,
        analysis_id: str,
        context_id: str,
        review_id: str,
        request: Request,
        limit: int = Query(default=10, ge=1, le=20),
        offset: int = Query(default=0, ge=0),
        user=Depends(authenticate),
    ):
        store = request.app.state.store
        values = route(matter_id, analysis_id, context_id, review_id)
        with store.session() as session:
            findings._require(store, session, *values, user)
            rows = session.scalars(
                select(Record)
                .where(
                    Record.kind == KIND,
                    Record.matter_id == matter_id,
                    Record.firm_id == user.firm_id,
                    Record.id.startswith(_prefix(review_id)),
                )
                .order_by(Record.created_at.desc(), Record.id)
                .limit(limit)
                .offset(offset)
            )
            return [
                {"id": row.id, "registered_at": data["registered_at"], "owner_id": row.owner_id}
                for row in rows
                for _, data, _ in [_require(store, session, values, row.id, user)]
            ]

    @router.get("/{trial_id}")
    def detail(
        matter_id: str,
        analysis_id: str,
        context_id: str,
        review_id: str,
        trial_id: str,
        request: Request,
        capture_id: str | None = Query(default=None, max_length=64),
        user=Depends(authenticate),
    ):
        with request.app.state.store.session() as session:
            return _view(
                request.app,
                session,
                route(matter_id, analysis_id, context_id, review_id),
                trial_id,
                user,
                capture_id,
            )

    @router.get("/{trial_id}/captures")
    def history(
        matter_id: str,
        analysis_id: str,
        context_id: str,
        review_id: str,
        trial_id: str,
        request: Request,
        limit: int = Query(default=10, ge=1, le=20),
        offset: int = Query(default=0, ge=0),
        user=Depends(authenticate),
    ):
        store = request.app.state.store
        values = route(matter_id, analysis_id, context_id, review_id)
        with store.session() as session:
            _require(store, session, values, trial_id, user)
            rows = session.scalars(
                select(Record)
                .where(
                    Record.kind == CAPTURE,
                    Record.matter_id == matter_id,
                    Record.firm_id == user.firm_id,
                    Record.id.startswith(_prefix(trial_id)),
                )
                .order_by(Record.created_at.desc(), Record.id)
                .limit(limit)
                .offset(offset)
            )
            return [
                {"id": row.id, "recorded_at": data["recorded_at"], "sequence": data["sequence"]}
                for row in rows
                for _, data, _ in [_require(store, session, values, row.id, user, CAPTURE, trial_id)]
            ]

    @router.post("/{trial_id}/capture-context")
    def preview(
        matter_id: str,
        analysis_id: str,
        context_id: str,
        review_id: str,
        trial_id: str,
        body: Preview,
        request: Request,
        user=Depends(authenticate),
    ):
        app = request.app
        values = route(matter_id, analysis_id, context_id, review_id)
        with app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            with authorities._guard(app, findings._public_data(app, session, *values[:3], user)):
                result = capture_basis(app, session, values, trial_id, body, user)
            require_matter(session, matter_id, user)
            return result

    @router.post("/{trial_id}/captures", status_code=201)
    def save(
        matter_id: str,
        analysis_id: str,
        context_id: str,
        review_id: str,
        trial_id: str,
        body: CaptureInput,
        request: Request,
        user=Depends(authenticate),
    ):
        return _write(request.app, route(matter_id, analysis_id, context_id, review_id), body, user, trial_id)

    @router.get("/{trial_id}/export")
    def export(
        matter_id: str,
        analysis_id: str,
        context_id: str,
        review_id: str,
        trial_id: str,
        request: Request,
        user=Depends(authenticate),
    ):
        app = request.app
        values = route(matter_id, analysis_id, context_id, review_id)
        with app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            with authorities._guard(app, findings._public_data(app, session, *values[:3], user)):
                value = _view(app, session, values, trial_id, user)
                if value["freshness"]["status"] != "current" or not value["snapshot"]:
                    raise HTTPException(409, "Yalnız güncel deneme kaydı aktarılabilir.")
                payload = canonical(value)
                session.expire_all()
                final = _view(app, session, values, trial_id, user)
                if (
                    final["freshness"]["status"] != "current"
                    or final["capture_sha256"] != value["capture_sha256"]
                    or final["protocol_sha256"] != value["protocol_sha256"]
                ):
                    raise HTTPException(409, "Aktarım sırasında deneme bağları değişti.")
            require_matter(session, matter_id, user)
            return Response(
                payload,
                media_type="application/json",
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Disposition": f'attachment; filename="private-authority-trial-{trial_id}.json"',
                },
            )

    return router
