"""Confidential local-model authority-trial inventories; no inference or pooled scoring."""

import json
from collections import defaultdict
from contextlib import ExitStack, contextmanager

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import Field, model_validator
from sqlalchemy import func, select

from . import analysis_authorities as authorities
from . import authority_findings as findings
from . import authority_model_inputs as inputs
from . import authority_model_trials as trials
from . import authority_proposals as proposals
from . import authority_trial_cohorts as human_cohorts
from .auth import authenticate, require_child, require_matter
from .content_scope import has_case_scope
from .db import Record, User, digest, now
from .evidence_prompt import canonical
from .firm_rbac import permissions_for
from .practice import StrictInput, _audit

RECIPE = "local-model-authority-trial-cohort-v1"
SUPPORTED_RECIPES = {"local-model-authority-trial-cohort-v1"}
KIND = "authority_model_cohort"
ADMISSION = "authority_model_cohort_admission"
MAX_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 60
MAX_TRIALS = 12


class Selection(StrictInput):
    trial_id: str = Field(pattern=r"^amt-[a-f0-9]{20}-[a-f0-9]{32}$")


class Specification(StrictInput):
    title: str = Field(min_length=3, max_length=200)
    purpose: str = Field(min_length=3, max_length=2000)
    selections: list[Selection] = Field(min_length=2, max_length=MAX_TRIALS)
    reserved_family_sha256: list[str] = Field(default_factory=list, max_length=60)

    @model_validator(mode="after")
    def distinct(self):
        if (
            len(self.title.strip()) < 3
            or len(self.purpose.strip()) < 3
            or len({item.trial_id for item in self.selections}) != len(self.selections)
            or len(set(self.reserved_family_sha256)) != len(self.reserved_family_sha256)
            or any(
                len(item) != 64 or any(c not in "0123456789abcdef" for c in item)
                for item in self.reserved_family_sha256
            )
            or len(canonical(self.model_dump()).encode()) > 16 * 1024
        ):
            raise ValueError("Explicit distinct trials, explained purpose and bounded family hashes required")
        return self


class Freeze(Specification):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    expected_preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def _bounded(value):
    if len(canonical(value).encode()) + 2048 > MAX_BYTES:
        raise HTTPException(409, "Özel dayanak deneme grubu 16 MiB sınırını aşıyor; kayıtlar atlanamaz.")
    return value


def _admission_id(ident):
    return "amca-" + digest(ident)[:32]


def _route(store, session, matter_id, ident, user):
    row = require_child(session, ident, trials.KIND, matter_id, user)
    analysis_id = store.decode(row).get("analysis_id")
    if not isinstance(analysis_id, str) or not 1 <= len(analysis_id) <= 64:
        raise HTTPException(409, "Model denemesinin üst kaydı doğrulanamadı.")
    _, plan, proof = trials._require(store, session, matter_id, analysis_id, ident, user)
    return analysis_id, plan, proof


@contextmanager
def _guards(app, session, matter_id, selections, user):
    # Resolve every private parent first; never traverse a public join for a foreign trial.
    plans = [
        _route(app.state.store, session, matter_id, item.trial_id, user)[1]
        for item in sorted(selections, key=lambda item: item.trial_id)
    ]
    with ExitStack() as stack:
        for plan in plans:
            stack.enter_context(proposals.scope(app, session, matter_id, user, plan))
        yield
    require_matter(session, matter_id, user)


def _entry(app, session, matter_id, selection, user):
    store = app.state.store
    analysis_id, _, _ = _route(store, session, matter_id, selection.trial_id, user)
    value = trials._read(app, session, matter_id, analysis_id, selection.trial_id, user)
    if not value["public_source_access"] or not value["protocol"]:
        raise HTTPException(409, "Seçilen model denemesinin kaynak veya kayıt kabulü bekletiliyor.")
    # Remove per-viewer actions and read time; persisted jobs, histories and seals remain.
    capture = {
        key: item
        for key, item in value.items()
        if key
        not in {"can_run", "can_observe", "can_record_effort", "previous_observation_id", "exported_at"}
    }
    plan = capture["protocol"]
    ids = human_cohorts._record_ids(capture) | {analysis_id, trials._proof_id(selection.trial_id)}
    ids.discard(matter_id)
    for event in [*capture["observations"], *capture["effort_history"]]:
        ids.add(trials._proof_id(event["id"]))
    if len(ids) > 2048:
        raise HTTPException(409, "Model denemesinin dayanak envanteri çalışma sınırını aşıyor.")
    records = []
    for ident in sorted(ids):
        row = session.get(Record, ident, populate_existing=True)
        if row and (row.firm_id != user.firm_id or row.matter_id != matter_id):
            raise HTTPException(403, "Model denemesi dayanağının özel çalışma alanı kapsamı değişti.")
        records.append(
            {
                "id": ident,
                "kind": row.kind if row else None,
                "sha256": digest(canonical(store.view(row))) if row else None,
            }
        )
    people = {plan["registered_by"], plan["authority_basis"]["reviewer_id"], *plan["reviewer_ids"]}
    version = require_child(session, plan["source_version_id"], "practice_version", matter_id, user)
    people.add(version.owner_id)
    participants = []
    for ident in sorted(people):
        member = session.get(User, ident, populate_existing=True)
        authorized = bool(
            member
            and member.active
            and member.firm_id == user.firm_id
            and member.role in {"lawyer", "admin"}
            and "matter.review" in permissions_for(session, member)
            and has_case_scope(session, matter_id, member)
        )
        participants.append({"id": ident, "authorized": authorized, "role": member.role if member else None})
    live = {
        "records": records,
        "participants": participants,
        "recipes": [RECIPE, trials.RECIPE, inputs.RECIPE, proposals.RECIPE],
        "semantic_dimensions_sha256": digest(canonical(trials.semantic.DIMENSIONS)),
        "finding_dimensions_sha256": digest(canonical(findings.DIMENSIONS)),
        "matter_status": store.decode(require_matter(session, matter_id, user)).get("status"),
    }
    result = {
        "trial_id": selection.trial_id,
        "analysis_id": analysis_id,
        "capture": capture,
        "live_basis": live,
    }
    result["entry_sha256"] = digest(canonical(result))
    return _bounded(result)


def _profile(capture):
    plan = capture["protocol"]
    return {
        "recipe": plan["recipe"],
        "recipes": plan["recipes"],
        "sample_kind": plan["sample_kind"],
        "input_kind": plan["authority_basis"]["input_ref"]["kind"],
        "rubric_sha256": plan["rubric_sha256"],
        "semantic_dimensions_sha256": digest(canonical(plan["dimensions"])),
        "finding_dimensions_sha256": digest(canonical(plan["authority_basis"]["authority_dimensions"])),
        "provider_pin": plan["provider_pin"],
        "research_budget_seconds": plan["research_budget_seconds"],
        "arms": {
            arm: {key: spec[key] for key in ("mode", "max_passes", "budget_seconds")}
            for arm, spec in plan["arms"].items()
        },
        "feedback_recipe": plan["authority_feedback"]["recipe"],
        "registration_before_calls": True,
        "account_separation_only": True,
        "blind_review": False,
        "effort_phase_limit_seconds": 28800,
        "effort_policy": "declared_active_nonoverlapping_with_shared_setup_and_full_review",
    }


def _outcomes(capture):
    plan = capture["protocol"]
    latest = {item["reviewer_id"]: item for item in capture["observations"]}
    pairs = {arm: item["comparison"] for arm, item in capture["arms"].items()}
    current = capture["freshness"]["status"] == "current"
    reviewers = [
        latest[ident]
        for ident in plan["reviewer_ids"]
        if ident in latest
        and current
        and all(pairs.values())
        and latest[ident]["execution_sha256"] == capture["execution_sha256"]
        and latest[ident]["comparison_hashes"]
        == {arm: item["comparison_sha256"] for arm, item in pairs.items()}
    ]
    arms = {}
    effort = capture["effort_history"][-1] if capture["effort_history"] else None
    effort_current = bool(current and effort and effort["execution_sha256"] == capture["execution_sha256"])
    for arm in trials.ARMS:
        assessments = [
            (event, next(item["assessment"] for item in event["arms"] if item["arm"] == arm))
            for event in reviewers
        ]

        def dimension(group, key, label, source_index=None):
            values = [
                {"reviewer_id": event["reviewer_id"], "reviewer_name": event["reviewer_name"], **item}
                for event, assessment in assessments
                for item in assessment[group]
                if item["dimension"] == key and (source_index is None or item["source_index"] == source_index)
            ]
            return {
                "dimension": key,
                "label": label,
                **({"source_index": source_index} if source_index is not None else {}),
                "observations": values,
                "outcome_difference": len({item["outcome"] for item in values}) > 1
                if len(values) == 2
                else None,
                "unknown_observations": 2
                - sum(item["outcome"] not in {"not_assessed", "unresolved"} for item in values),
            }

        semantic = [dimension("observations", key, label) for key, label in plan["dimensions"].items()]
        judgments = [
            dimension("judgments", key, label, index)
            for index, source in enumerate(plan["authority_basis"]["assessment"]["sources"])
            for key, label in plan["authority_basis"]["authority_dimensions"].items()
        ]
        item = capture["arms"][arm]
        arms[arm] = {
            "status": item["status"],
            "retained_passes": len((item["job"] or {}).get("iterations", [])),
            "elapsed_seconds": item["elapsed_seconds"],
            "provider_round_trip_seconds": item["provider_round_trip_seconds"],
            "gpu_compute_seconds": None,
            "semantic": semantic,
            "findings": judgments,
            "semantic_observation_slots": len(semantic) * 2,
            "finding_observation_slots": len(judgments) * 2,
            "unknown_semantic_observations": sum(row["unknown_observations"] for row in semantic),
            "unknown_finding_observations": sum(row["unknown_observations"] for row in judgments),
            "outcome_difference_count": sum(
                row["outcome_difference"] is True for row in [*semantic, *judgments]
            )
            if len(reviewers) == 2
            else None,
            "active_effort": next(row for row in effort["arms"] if row["arm"] == arm)
            if effort_current
            else None,
            "active_effort_accounted": effort_current and capture["effort_accounted"],
            "assessment_times": [
                {"reviewer_id": event["reviewer_id"], "review_seconds": assessment["review_seconds"]}
                for event, assessment in assessments
            ],
            "adverse_scopes": [
                {"reviewer_id": event["reviewer_id"], "scope": assessment["adverse_scope"]}
                for event, assessment in assessments
            ],
            "adverse_recall": None,
            "preparation_time_gain": None,
        }
    return {
        "current_reviewer_count": len(reviewers),
        "arms": arms,
        "unknown_semantic_observations": sum(item["unknown_semantic_observations"] for item in arms.values()),
        "unknown_finding_observations": sum(item["unknown_finding_observations"] for item in arms.values()),
        "outcome_difference_count": sum(item["outcome_difference_count"] for item in arms.values())
        if len(reviewers) == 2
        else None,
        "effort_accounted": effort_current and capture["effort_accounted"],
    }


def reconcile(entries, reserved):
    profiles, families, inputs, versions, private_sources, public_sources = (
        defaultdict(list) for _ in range(6)
    )
    rows = []
    for entry in entries:
        capture, ident = entry["capture"], entry["trial_id"]
        plan, profile = capture["protocol"], _profile(capture)
        key = digest(canonical(profile))
        profiles[key].append({"id": ident, "profile": profile})
        family = plan["split_family_sha256"]
        families[family].append(ident)
        input_sha = digest(
            canonical(
                {
                    "private": plan["task_input_sha256"],
                    "selected_feedback": plan["authority_feedback_sha256"],
                    "authority_basis": plan["authority_basis"],
                }
            )
        )
        inputs[input_sha].append(ident)
        baseline = plan["source_content"]
        versions[(plan["source_version_id"], digest(canonical(baseline)))].append(ident)
        for document in {item["document_id"] for item in baseline["source_snapshots"]}:
            private_sources[document].append({"trial_id": ident, "family_sha256": family})
        sources = plan["authority_basis"]["manifest"]["sources"]
        for source in sources:
            selected = source["selection"]
            source_key = canonical(
                {
                    **{key: selected[key] for key in authorities.IDENTITY},
                    **{
                        key: source["evidence"][key]
                        for key in ("source_version_id", "source_sha256", "text_sha256", "locator_map_sha256")
                    },
                }
            )
            public_sources[source_key].append({"trial_id": ident, "family_sha256": family})
        rows.append(
            {
                "trial_id": ident,
                "title": plan["title"],
                "profile_sha256": key,
                "entry_sha256": entry["entry_sha256"],
                "family_sha256": family,
                "sample_kind": plan["sample_kind"],
                "source_freshness": capture["freshness"],
                "capture_present": any(item["job"] is not None for item in capture["arms"].values()),
                "capture_complete": capture["capture_complete"],
                "execution_sha256": capture["execution_sha256"],
                **_outcomes(capture),
            }
        )
    return {
        "counts": {
            "selected_records": len(entries),
            "profile_groups": len(profiles),
            "declared_families": len(families),
            "current_source_records": sum(row["source_freshness"]["status"] == "current" for row in rows),
            "captures_present": sum(row["capture_present"] for row in rows),
            "complete_capture_records": sum(row["capture_complete"] for row in rows),
            "current_reviewer_pairs": sum(row["current_reviewer_count"] == 2 for row in rows),
            "accounted_effort_records": sum(row["effort_accounted"] for row in rows),
            "records_with_outcome_differences": sum(bool(row["outcome_difference_count"]) for row in rows),
            "records_with_unknown_observations": sum(
                bool(row["unknown_semantic_observations"] or row["unknown_finding_observations"])
                for row in rows
            ),
        },
        "profiles": [
            {
                "profile_sha256": key,
                "profile": items[0]["profile"],
                "trial_ids": [item["id"] for item in items],
            }
            for key, items in sorted(profiles.items())
        ],
        "families": [
            {"family_sha256": key, "trial_ids": items, "reserved_overlap": key in reserved}
            for key, items in sorted(families.items())
        ],
        "duplicate_inputs": [
            {"input_sha256": key, "trial_ids": items}
            for key, items in sorted(inputs.items())
            if len(items) > 1
        ],
        "repeated_versions": [
            {"version_id": key[0], "sha256": key[1], "trial_ids": items}
            for key, items in sorted(versions.items())
            if len(items) > 1
        ],
        "cross_family_private_sources": [
            {"document_id": key, "selections": items}
            for key, items in sorted(private_sources.items())
            if len({item["family_sha256"] for item in items}) > 1
        ],
        "repeated_public_passages": [
            {"selection": json.loads(key), "selections": items}
            for key, items in sorted(public_sources.items())
            if len(items) > 1
        ],
        "reserved_overlaps": sorted(set(families) & set(reserved)),
        "rows": rows,
        "selection_is_exhaustive": False,
        "held_out_qualified": False,
        "reviewer_expertise_verified": False,
        "legal_verdict": None,
        "preparation_time_gain": None,
        "qualification_granted": False,
        "production_qualified": False,
        "benefit_established": False,
        "model_benchmark": False,
    }


def preview(app, session, matter_id, spec, user):
    entries = [_entry(app, session, matter_id, item, user) for item in spec.selections]
    manifest = {
        "recipe": RECIPE,
        "scope": "same_workspace_private_model_authority_trials",
        "matter_id": matter_id,
        **spec.model_dump(),
        "entries": entries,
        "reconciliation": reconcile(entries, spec.reserved_family_sha256),
        "model_use": "existing_frozen_runs_only",
        "qualification_granted": False,
        "benefit_established": False,
        "production_qualified": False,
    }
    return _bounded({"manifest": manifest, "preview_sha256": digest(canonical(manifest))})


def _require(store, session, matter_id, ident, user):
    row = require_child(session, ident, KIND, matter_id, user)
    value = store.decode(row)
    proof_row = require_child(session, _admission_id(ident), ADMISSION, matter_id, user)
    proof = store.decode(proof_row)
    if (
        value.get("sha256")
        != digest(canonical({key: item for key, item in value.items() if key != "sha256"}))
        or value.get("manifest_sha256") != digest(canonical(value["manifest"]))
        or value["manifest"].get("matter_id") != matter_id
        or value["manifest"].get("recipe") not in SUPPORTED_RECIPES
        or value.get("owner_id") != row.owner_id
        or proof_row.owner_id != row.owner_id
        or proof.get("id") != ident
        or proof.get("sha256") != value["sha256"]
    ):
        raise HTTPException(409, "Dayanak deneme grubunun bütünlüğü doğrulanamadı.")
    return row, value, proof


def cohort_view(app, session, matter_id, ident, user):
    store = app.state.store
    row, data, proof = _require(store, session, matter_id, ident, user)
    result = {
        "id": row.id,
        "registered_at": data["registered_at"],
        "owner_id": row.owner_id,
        "manifest_sha256": data["manifest_sha256"],
        "sha256": data["sha256"],
        "manifest": None,
        "public_source_access": False,
        "freshness": {"status": "withheld", "reasons": ["post_commit_authorization_pending"]},
        "live_sha256": None,
        "qualification_granted": False,
        "benefit_established": False,
        "production_qualified": False,
    }
    if not proof.get("publication_guard_completed"):
        return result
    spec = Specification.model_validate({key: data["manifest"][key] for key in Specification.model_fields})
    try:
        with _guards(app, session, matter_id, spec.selections, user):
            live = [_entry(app, session, matter_id, item, user) for item in spec.selections]
            reasons = [
                {"trial_id": item["trial_id"], "code": "selected_trial_changed_or_stale"}
                for item, old in zip(live, data["manifest"]["entries"], strict=True)
                if item["entry_sha256"] != old["entry_sha256"]
                or item["capture"]["freshness"]["status"] != "current"
            ]
            if data["manifest"]["recipe"] != RECIPE:
                reasons.append({"trial_id": None, "code": "cohort_recipe_changed"})
            result.update(
                manifest=data["manifest"],
                public_source_access=True,
                freshness={"status": "stale" if reasons else "current", "reasons": reasons},
                live_sha256=digest(canonical([item["entry_sha256"] for item in live])),
            )
        require_child(session, ident, KIND, matter_id, user)
        return _bounded(result)
    except HTTPException as exc:
        if exc.status_code not in {404, 409}:
            raise
        require_child(session, ident, KIND, matter_id, user)
        result.update(
            manifest=None,
            public_source_access=False,
            live_sha256=None,
            freshness={"status": "withheld", "reasons": ["selected_source_or_record_unavailable"]},
        )
        return result


def _freeze(app, matter_id, body, user):
    store = app.state.store
    ident = "amc-" + digest(matter_id)[:20] + "-" + digest(user.id + ":" + body.request_id)[:32]
    request_sha = digest(canonical(body.model_dump(exclude={"request_id"})))
    spec = Specification.model_validate(body.model_dump(exclude={"request_id", "expected_preview_sha256"}))
    committed = False
    try:
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            findings._lawyer(session, matter_id, user)
            if session.get(Record, ident):
                row, old, _ = _require(store, session, matter_id, ident, user)
                if row.owner_id != user.id or old["request_sha256"] != request_sha:
                    raise HTTPException(409, "İstek kimliği farklı bir gruba bağlı.")
                return cohort_view(app, session, matter_id, ident, user)
            if (
                session.scalar(
                    select(func.count())
                    .select_from(Record)
                    .where(Record.kind == KIND, Record.matter_id == matter_id)
                )
                >= MAX_RECORDS
            ):
                raise HTTPException(409, "Çalışma alanının 60 dayanak grup kaydı sınırına ulaşıldı.")
            with _guards(app, session, matter_id, spec.selections, user):
                current = preview(app, session, matter_id, spec, user)
                if current["preview_sha256"] != body.expected_preview_sha256:
                    raise HTTPException(409, "Denemeler veya grup beyanı değişti; önizlemeyi yenileyin.")
                data = {
                    "manifest": current["manifest"],
                    "manifest_sha256": current["preview_sha256"],
                    "request_sha256": request_sha,
                    "registered_at": now(),
                    "owner_id": user.id,
                    "immutable": True,
                }
                data["sha256"] = digest(canonical(data))
                _bounded(data)
                store.add(session, KIND, user, data, matter_id, record_id=ident)
                store.add(
                    session,
                    ADMISSION,
                    user,
                    {"id": ident, "sha256": data["sha256"], "publication_guard_completed": False},
                    matter_id,
                    record_id=_admission_id(ident),
                )
                _audit(session, user, "authority_model_cohort_frozen", ident, matter_id)
                session.flush()
                session.expire_all()
                if (
                    preview(app, session, matter_id, spec, user)["preview_sha256"]
                    != body.expected_preview_sha256
                ):
                    raise HTTPException(409, "Grup kaydı sırasında deneme dayanakları değişti.")
                findings._lawyer(session, matter_id, user)
                session.commit()
                committed = True
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            findings._lawyer(session, matter_id, user)
            _, _, proof = _require(store, session, matter_id, ident, user)
            with _guards(app, session, matter_id, spec.selections, user):
                if (
                    preview(app, session, matter_id, spec, user)["preview_sha256"]
                    != body.expected_preview_sha256
                ):
                    raise HTTPException(409, "Son kayıt kabulünde deneme dayanakları değişti.")
            findings._lawyer(session, matter_id, user)
            store.update(
                session.get(Record, _admission_id(ident)), {**proof, "publication_guard_completed": True}
            )
            session.commit()
        with store.session() as session:
            return cohort_view(app, session, matter_id, ident, user)
    except Exception:
        if not committed:
            raise
        return JSONResponse(
            status_code=409,
            content={"outcome": "committed_needs_revalidation", "id": ident, "needs_revalidation": True},
        )


def authority_model_cohorts_router():
    router = APIRouter(
        prefix="/api/v1/matters/{matter_id}/authority-model-cohorts",
        tags=["private-model-authority-trial-cohorts"],
    )

    @router.get("/candidates")
    def candidates(
        matter_id: str,
        request: Request,
        limit: int = Query(default=10, ge=1, le=20),
        offset: int = Query(default=0, ge=0),
        user=Depends(authenticate),
    ):
        store = request.app.state.store
        with store.session() as session:
            require_matter(session, matter_id, user)
            rows = session.scalars(
                select(Record)
                .where(
                    Record.kind == trials.KIND, Record.matter_id == matter_id, Record.firm_id == user.firm_id
                )
                .order_by(Record.created_at.desc(), Record.id)
                .limit(limit)
                .offset(offset)
            )
            return [
                {
                    "trial_id": row.id,
                    "analysis_id": analysis_id,
                    "registered_at": plan["registered_at"],
                    "admission_complete": bool(proof.get("completed")),
                }
                for row in rows
                for analysis_id, plan, proof in [_route(store, session, matter_id, row.id, user)]
            ]

    @router.post("/preview")
    def inspect(matter_id: str, body: Specification, request: Request, user=Depends(authenticate)):
        app = request.app
        with app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            with _guards(app, session, matter_id, body.selections, user):
                result = preview(app, session, matter_id, body, user)
            return result

    @router.post("", status_code=201)
    def freeze(matter_id: str, body: Freeze, request: Request, user=Depends(authenticate)):
        return _freeze(request.app, matter_id, body, user)

    @router.get("")
    def listing(
        matter_id: str,
        request: Request,
        limit: int = Query(default=10, ge=1, le=20),
        offset: int = Query(default=0, ge=0),
        user=Depends(authenticate),
    ):
        store = request.app.state.store
        with store.session() as session:
            require_matter(session, matter_id, user)
            rows = session.scalars(
                select(Record)
                .where(Record.kind == KIND, Record.matter_id == matter_id, Record.firm_id == user.firm_id)
                .order_by(Record.created_at.desc(), Record.id)
                .limit(limit)
                .offset(offset)
            )
            return [
                {"id": row.id, "registered_at": data["registered_at"]}
                for row in rows
                for _, data, _ in [_require(store, session, matter_id, row.id, user)]
            ]

    @router.get("/{cohort_id}")
    def detail(matter_id: str, cohort_id: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            return cohort_view(request.app, session, matter_id, cohort_id, user)

    @router.get("/{cohort_id}/export")
    def export(matter_id: str, cohort_id: str, request: Request, user=Depends(authenticate)):
        app = request.app
        with app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            _, data, _ = _require(app.state.store, session, matter_id, cohort_id, user)
            selected = [Selection.model_validate(item) for item in data["manifest"]["selections"]]
            with _guards(app, session, matter_id, selected, user):
                value = cohort_view(app, session, matter_id, cohort_id, user)
                if not value["public_source_access"] or value["freshness"]["status"] != "current":
                    raise HTTPException(409, "Yalnız güncel ve izinli dayanak grubu aktarılabilir.")
                payload = canonical(value)
                session.expire_all()
                final = cohort_view(app, session, matter_id, cohort_id, user)
                if (
                    not final["public_source_access"]
                    or final["freshness"]["status"] != "current"
                    or final["live_sha256"] != value["live_sha256"]
                    or final["sha256"] != value["sha256"]
                ):
                    raise HTTPException(409, "Aktarım sırasında grup dayanakları değişti.")
            require_matter(session, matter_id, user)
            return Response(
                payload,
                media_type="application/json",
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Disposition": f'attachment; filename="private-model-authority-cohort-{cohort_id}.json"',
                },
            )

    return router
