"""Immutable, workspace-private development inventories; never legal scoring."""

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import Field, model_validator
from sqlalchemy import select

from . import analysis_adjudication, analysis_reviews, analysis_suggestions, analysis_workbench
from . import analysis_comparisons as comparisons
from .analysis_adjudication import DIMENSIONS
from .auth import authenticate, require_child, require_matter
from .content_scope import has_case_scope
from .db import Record, User, digest, now
from .evidence_prompt import canonical
from .practice import StrictInput, _audit

RECIPE = "private-analysis-cohort-v1"
SUPPORTED_RECIPES = {"private-analysis-cohort-v1"}
KIND = "analysis_cohort"
MAX_CAPTURES = 12
MAX_BYTES = 16 * 1024 * 1024
VOLATILE = {"exported_at", "can_run", "can_observe", "can_record_effort", "previous_observation_id", "previous_effort_id"}


class Selection(StrictInput):
    analysis_id: str = Field(min_length=1, max_length=64)
    comparison_id: str = Field(min_length=1, max_length=64)


class Specification(StrictInput):
    title: str = Field(min_length=3, max_length=200)
    purpose: str = Field(min_length=3, max_length=2000)
    selections: list[Selection] = Field(min_length=2, max_length=MAX_CAPTURES)
    reserved_family_sha256: list[str] = Field(default_factory=list, max_length=60)

    @model_validator(mode="after")
    def unique(self):
        if len({item.comparison_id for item in self.selections}) != len(self.selections):
            raise ValueError("Select each comparison exactly once")
        if (len(set(self.reserved_family_sha256)) != len(self.reserved_family_sha256)
                or any(len(item) != 64 or any(char not in "0123456789abcdef" for char in item)
                       for item in self.reserved_family_sha256)):
            raise ValueError("Reserved family digests must be distinct lowercase SHA-256 values")
        return self


class Freeze(Specification):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    expected_preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def _bounded(value):
    if len(canonical(value).encode()) > MAX_BYTES:
        raise HTTPException(409, "Özel karşılaştırma grubu 16 MiB sınırını aşıyor; kayıtlar atlanamaz.")
    return value


def _snapshot(value):
    # A clock or the reading account's capabilities must not change content pins.
    return {key: item for key, item in value.items() if key not in VOLATILE}


def _lock_inputs(app, session, matter_id, selections, user, *, allow_missing=False):
    """Caller holds the matter lock; job checkpoints also lock their own row."""
    store, jobs = app.state.store, {}
    for item in selections:
        try:
            row, plan = comparisons._require(store, session, matter_id, item.analysis_id, item.comparison_id, user)
        except HTTPException as exc:
            if allow_missing and exc.status_code == 404:
                continue
            raise
        for spec in plan["arms"].values():
            ident = item.analysis_id + "-" + digest(row.owner_id + ":" + spec["request_id"])[:30]
            receipt = session.get(Record, ident)
            if receipt:
                receipt = require_child(session, ident, analysis_suggestions.RECEIPT, matter_id, user)
                job = analysis_suggestions._require_job(
                    store, session, matter_id, item.analysis_id, store.decode(receipt)["job_id"], user)
                jobs[job.id] = job
    for ident in sorted(jobs):
        session.refresh(jobs[ident], with_for_update=True)


def _entry(app, session, matter_id, selected, user):
    store = app.state.store
    capture = _snapshot(comparisons.capture(app, session, matter_id, selected.analysis_id, selected.comparison_id, user))
    plan = capture["protocol"]
    identities = {selected.analysis_id: "practice_analysis", plan["source_version_id"]: "practice_version"}
    identities.update({item["id"]: "fact" for item in plan["source_content"]["fact_snapshots"]})
    identities.update({item["document_id"]: "document" for item in plan["source_content"]["source_snapshots"]})
    latest_review = analysis_reviews.review_pin(store, session, matter_id, selected.analysis_id, plan["source_version_id"], user)
    for ident in (plan["source_review_id"], latest_review):
        if ident:
            identities[ident] = analysis_reviews.KIND
    records = []
    for ident, kind in sorted(identities.items()):
        row = session.get(Record, ident, populate_existing=True)
        if row and (row.matter_id != matter_id or row.firm_id != user.firm_id):
            raise HTTPException(403, "Dayanak kaydının çalışma alanı kapsamı değişti.")
        if row and row.kind != kind:
            raise HTTPException(409, "Seçilen dayanağın kayıt türü değişti.")
        records.append({"id": ident, "kind": kind, "content_sha256": digest(canonical(store.view(row))) if row else None})
    participants = []
    for ident in [plan["registered_by"], *plan["reviewer_ids"]]:
        member = session.get(User, ident, populate_existing=True)
        participants.append({"id": ident, "authorized": bool(member and member.active and member.firm_id == user.firm_id
            and has_case_scope(session, matter_id, member))})
    facts = {item["id"] for item in plan["source_content"]["fact_snapshots"]}
    basis = {"records": records, "participants": participants, "latest_review_id": latest_review,
        "contradictions_sha256": digest(canonical(analysis_workbench._contradictions(store, session, matter_id, user.firm_id, facts))),
        "current_provider_sha256": digest(canonical(analysis_suggestions.provider_pin(app))),
        "current_recipes": [RECIPE, comparisons.RECIPE, analysis_adjudication.RECIPE, analysis_reviews.RECIPE, analysis_workbench.RECIPE],
        "current_dimensions_sha256": digest(canonical(DIMENSIONS)),
        "matter_status": store.decode(require_matter(session, matter_id, user)).get("status")}
    # Even an already-stale reason can conceal another change. Pin the live basis
    # separately from the original protocol; neither substitutes today's evidence.
    value = {"capture": capture, "live_basis": basis}
    return {**selected.model_dump(), "capture_sha256": digest(canonical(value)), **value}


def _profile(capture):
    plan = capture["protocol"]
    value = {key: plan[key] for key in ("recipe", "review_recipe", "adjudication_recipe", "dimensions_sha256",
                                       "rubric_sha256", "provider_pin", "research_budget_seconds", "sample_kind")}
    value["arms"] = {arm: {key: spec[key] for key in ("mode", "max_passes", "budget_seconds")}
                     for arm, spec in plan["arms"].items()}
    value["feedback_policy"] = {"selected": bool(plan.get("review_feedback")),
                                "recipe": plan.get("review_feedback", {}).get("recipe")}
    return value


def _reviewers(capture):
    latest = {item["reviewer_id"]: item for item in capture["observations"]}
    pair = {arm: item["comparison"] for arm, item in capture["arms"].items()}
    if capture["freshness"]["status"] != "current" or not all(pair.values()):
        return []
    return [latest[ident] for ident in capture["protocol"]["reviewer_ids"] if ident in latest
            and latest[ident]["execution_sha256"] == capture["execution_sha256"]
            and latest[ident]["comparison_snapshots"] == pair
            and all(item["assessment"]["comparison_sha256"] == pair[item["arm"]]["comparison_sha256"]
                    for item in latest[ident]["arms"])]


def _outcomes(capture):
    reviewers, arms = _reviewers(capture), {}
    for arm in comparisons.ARMS:
        assessments = [(event, next(item["assessment"] for item in event["arms"] if item["arm"] == arm))
                       for event in reviewers]
        dimensions, findings = [], []
        for dimension, label in DIMENSIONS.items():
            values = [{"reviewer_id": event["reviewer_id"], "reviewer_name": event["reviewer_name"], **item}
                      for event, assessment in assessments for item in assessment["observations"]
                      if item["dimension"] == dimension]
            dimensions.append({"dimension": dimension, "label": label, "observations": values,
                "outcome_difference": len({item["outcome"] for item in values}) > 1,
                "unknown_observations": 2 - sum(item["outcome"] != "not_assessed" for item in values)})
        review = capture["protocol"]["source_review"]
        for index, finding in enumerate(review["findings"] if review else []):
            values = [{"reviewer_id": event["reviewer_id"], "reviewer_name": event["reviewer_name"], **item}
                      for event, assessment in assessments for item in assessment["finding_dispositions"]
                      if item["finding_index"] == index]
            findings.append({"finding_index": index, "target_id": finding["target_id"], "observations": values,
                "outcome_difference": len({item["outcome"] for item in values}) > 1,
                "unresolved_or_missing": len(values) < 2 or any(item["outcome"] == "unresolved" for item in values)})
        item = capture["arms"][arm]
        effort = capture["effort_history"][-1] if capture["effort_history"] else None
        effort_current = bool(effort and effort["execution_sha256"] == capture["execution_sha256"]
                              and capture["freshness"]["status"] == "current")
        arms[arm] = {"status": item["status"], "retained_passes": len((item["job"] or {}).get("iterations", [])),
            "elapsed_seconds": item["elapsed_seconds"], "provider_round_trip_seconds": item["provider_round_trip_seconds"],
            "gpu_compute_seconds": None, "dimensions": dimensions, "findings": findings,
            "active_effort": next(entry for entry in effort["arms"] if entry["arm"] == arm) if effort_current else None,
            "active_effort_accounted": effort_current and capture["effort_accounted"],
            "assessment_times": [{"reviewer_id": event["reviewer_id"], "review_seconds": assessment["review_seconds"]}
                                 for event, assessment in assessments],
            "unknown_assessment_observations": sum(item["unknown_observations"] for item in dimensions),
            "outcome_difference_count": sum(item["outcome_difference"] for item in [*dimensions, *findings]),
            "unresolved_finding_count": sum(item["unresolved_or_missing"] for item in findings)}
    return {"current_reviewer_count": len(reviewers), "arms": arms}


def reconcile(entries, reserved):
    """Count retained records/outcome labels, not legal correctness or benefit."""
    profiles, families, inputs, versions, sources = (defaultdict(list) for _ in range(5))
    rows = []
    for entry in entries:
        value, ident = entry["capture"], entry["comparison_id"]
        plan, profile = value["protocol"], _profile(value)
        profile_sha = digest(canonical(profile))
        profiles[profile_sha].append({"id": ident, "profile": profile})
        families[plan["split_family_sha256"]].append(ident)
        inputs[plan["task_input_sha256"]].append(ident)
        versions[(plan["source_version_id"], plan["source_version_sha256"])].append(ident)
        for document in {item["document_id"] for item in plan["source_content"]["evidence"]}:
            sources[document].append({"comparison_id": ident, "family_sha256": plan["split_family_sha256"]})
        row = {"comparison_id": ident, "analysis_id": entry["analysis_id"], "title": plan["title"],
            "capture_sha256": entry["capture_sha256"], "profile_sha256": profile_sha,
            "family_sha256": plan["split_family_sha256"], "sample_kind": plan["sample_kind"],
            "source_freshness": value["freshness"], "capture_complete": value["capture_complete"], **_outcomes(value)}
        row["unknown_assessment_observations"] = sum(item["unknown_assessment_observations"] for item in row["arms"].values())
        row["outcome_difference_count"] = sum(item["outcome_difference_count"] for item in row["arms"].values())
        row["unresolved_finding_count"] = sum(item["unresolved_finding_count"] for item in row["arms"].values())
        rows.append(row)
    return {"counts": {"selected_records": len(entries), "profile_groups": len(profiles),
            "declared_families": len(families), "current_source_records": sum(row["source_freshness"]["status"] == "current" for row in rows),
            "complete_capture_records": sum(row["capture_complete"] for row in rows),
            "current_reviewer_pairs": sum(row["current_reviewer_count"] == 2 for row in rows),
            "accounted_effort_records": sum(all(item["active_effort_accounted"] for item in row["arms"].values()) for row in rows),
            "records_with_outcome_differences": sum(row["outcome_difference_count"] > 0 for row in rows),
            "records_with_unknown_assessments": sum(row["unknown_assessment_observations"] > 0 for row in rows),
            "records_with_unresolved_findings": sum(row["unresolved_finding_count"] > 0 for row in rows)},
        "profiles": [{"profile_sha256": key, "profile": values[0]["profile"], "comparison_ids": [item["id"] for item in values]}
                     for key, values in sorted(profiles.items())],
        "families": [{"family_sha256": key, "comparison_ids": values, "reserved_overlap": key in reserved}
                     for key, values in sorted(families.items())],
        "duplicate_inputs": [{"task_input_sha256": key, "comparison_ids": values}
                             for key, values in sorted(inputs.items()) if len(values) > 1],
        "repeated_versions": [{"version_id": key[0], "content_sha256": key[1], "comparison_ids": values}
                              for key, values in sorted(versions.items()) if len(values) > 1],
        "cross_family_sources": [{"document_id": key, "selections": values} for key, values in sorted(sources.items())
                                 if len({item["family_sha256"] for item in values}) > 1],
        "reserved_overlaps": sorted(set(families) & set(reserved)), "rows": rows,
        "selection_is_exhaustive": False, "held_out_qualified": False, "reviewer_expertise_verified": False,
        "legal_verdict": None, "preparation_time_gain": None, "qualification_granted": False,
        "production_qualified": False, "benefit_established": False}


def preview(app, session, matter_id, spec, user):
    require_matter(session, matter_id, user)
    _lock_inputs(app, session, matter_id, spec.selections, user)
    entries = []
    for item in spec.selections:
        entries.append(_entry(app, session, matter_id, item, user))
    manifest = {"recipe": RECIPE, "scope": "same_workspace_private_development_inventory", "matter_id": matter_id,
        **spec.model_dump(), "captures": entries, "reconciliation": reconcile(entries, spec.reserved_family_sha256),
        "runtime_authorization": "none", "qualification_granted": False, "production_qualified": False,
        "benefit_established": False}
    return _bounded({"manifest": manifest, "preview_sha256": digest(canonical(manifest))})


def _require(store, session, matter_id, ident, user):
    row = require_child(session, ident, KIND, matter_id, user)
    value = store.decode(row)
    if (value["cohort_sha256"] != digest(canonical({key: item for key, item in value.items() if key != "cohort_sha256"}))
            or value["manifest_sha256"] != digest(canonical(value["manifest"]))
            or value["manifest"]["matter_id"] != matter_id or value["manifest"]["recipe"] not in SUPPORTED_RECIPES):
        raise HTTPException(409, "Karşılaştırma grubunun bütünlüğü veya sürümü doğrulanamadı.")
    return row, value


def cohort_view(app, session, matter_id, ident, user):
    store = app.state.store
    row, value = _require(store, session, matter_id, ident, user)
    reasons, live = [], []
    if value["manifest"]["recipe"] != RECIPE:
        reasons.append({"comparison_id": None, "code": "cohort_recipe_changed"})
    _lock_inputs(app, session, matter_id,
                 [Selection.model_validate(item) for item in value["manifest"]["selections"]], user, allow_missing=True)
    for entry in value["manifest"]["captures"]:
        # Never expose a copied snapshot after its selected record is moved across
        # the workspace/firm boundary. Absent records stay explicit and stale.
        for key in ("analysis_id", "comparison_id"):
            selected = session.get(Record, entry[key])
            if selected and (selected.matter_id != matter_id or selected.firm_id != user.firm_id):
                raise HTTPException(404, "Kayıt bulunamadı")
        try:
            current = _entry(app, session, matter_id, Selection.model_validate(
                {key: entry[key] for key in ("analysis_id", "comparison_id")}), user)
            checksum = current["capture_sha256"]
            status = current["capture"]["freshness"]["status"]
            if checksum != entry["capture_sha256"] or status != "current":
                reasons.append({"comparison_id": entry["comparison_id"], "code": "capture_changed_or_stale"})
            live.append({"comparison_id": entry["comparison_id"], "capture_sha256": checksum, "source_status": status})
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            reasons.append({"comparison_id": entry["comparison_id"], "code": "selected_record_unavailable"})
            live.append({"comparison_id": entry["comparison_id"], "capture_sha256": None, "source_status": "unavailable"})
    return _bounded({"id": row.id, "registered_at": value["registered_at"], "registered_by": value["registered_by"],
        "manifest": value["manifest"], "manifest_sha256": value["manifest_sha256"], "cohort_sha256": value["cohort_sha256"],
        "freshness": {"status": "stale" if reasons else "current", "reasons": reasons}, "live_captures": live,
        "qualification_granted": False, "production_qualified": False, "benefit_established": False, "exported_at": now()})


def cohort_router():
    router = APIRouter(prefix="/api/v1/matters/{matter_id}/analysis-cohorts", tags=["private-analysis-cohorts"])

    @router.get("/candidates")
    def candidates(matter_id: str, request: Request, user=Depends(authenticate),
                   limit: int = Query(default=10, ge=1, le=20), offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            require_matter(session, matter_id, user)
            rows = session.scalars(select(Record).where(Record.kind == comparisons.KIND,
                Record.matter_id == matter_id, Record.firm_id == user.firm_id)
                .order_by(Record.created_at.desc(), Record.id).limit(limit).offset(offset))
            results = []
            for row in rows:
                plan = store.decode(row)
                comparisons._require(store, session, matter_id, plan["analysis_id"], row.id, user)
                results.append({"comparison_id": row.id, "analysis_id": plan["analysis_id"], "title": plan["title"],
                    "registered_at": plan["registered_at"], "family_sha256": plan["split_family_sha256"],
                    "sample_kind": plan["sample_kind"], "source_version": plan["source_version"]})
            return results

    @router.post("/preview")
    def inspect(matter_id: str, body: Specification, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            return preview(request.app, session, matter_id, body, user)

    @router.post("", status_code=201)
    def freeze(matter_id: str, body: Freeze, request: Request, user=Depends(authenticate)):
        app, store = request.app, request.app.state.store
        spec = Specification.model_validate(body.model_dump(exclude={"request_id", "expected_preview_sha256"}))
        ident = "ach-" + digest(matter_id)[:20] + "-" + digest(user.id + ":" + body.request_id)[:32]
        request_sha = digest(canonical(body.model_dump(exclude={"request_id"})))
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            existing = session.get(Record, ident)
            if existing:
                _, data = _require(store, session, matter_id, ident, user)
                if existing.owner_id != user.id or data["request_sha256"] != request_sha:
                    raise HTTPException(409, "İstek kimliği farklı bir karşılaştırma grubuna bağlı.")
                return cohort_view(app, session, matter_id, ident, user)
            if store.decode(matter).get("status") == "archived":
                raise HTTPException(409, "Arşivlenmiş çalışma alanında yeni grup kaydedilemez.")
            result = preview(app, session, matter_id, spec, user)
            if result["preview_sha256"] != body.expected_preview_sha256:
                raise HTTPException(409, "Seçilen deneme kayıtları veya grup beyanı değişti; önizlemeyi yenileyin.")
            data = {"manifest": result["manifest"], "manifest_sha256": result["preview_sha256"],
                    "request_sha256": request_sha, "registered_at": now(), "registered_by": user.id, "immutable": True}
            data["cohort_sha256"] = digest(canonical(data))
            store.add(session, KIND, user, data, matter_id, record_id=ident)
            _audit(session, user, "analysis_cohort_frozen", ident, matter_id)
            session.expire_all()
            if preview(app, session, matter_id, spec, user)["preview_sha256"] != body.expected_preview_sha256:
                raise HTTPException(409, "Grup kaydı sırasında denemelerin dayanakları değişti.")
            result = cohort_view(app, session, matter_id, ident, user)
            if store.decode(require_matter(session, matter_id, user)).get("status") == "archived":
                raise HTTPException(409, "Grup kaydı sırasında çalışma alanı arşivlendi.")
            session.commit()
            return result

    @router.get("")
    def listing(matter_id: str, request: Request, user=Depends(authenticate),
                limit: int = Query(default=10, ge=1, le=20), offset: int = Query(default=0, ge=0)):
        store = request.app.state.store
        with store.session() as session:
            require_matter(session, matter_id, user)
            rows = session.scalars(select(Record).where(Record.kind == KIND, Record.matter_id == matter_id,
                Record.firm_id == user.firm_id).order_by(Record.created_at.desc(), Record.id).limit(limit).offset(offset))
            results = []
            for row in rows:
                _, value = _require(store, session, matter_id, row.id, user)
                results.append({"id": row.id, "title": value["manifest"]["title"], "registered_at": value["registered_at"]})
            return results

    @router.get("/{cohort_id}")
    def detail(matter_id: str, cohort_id: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            return cohort_view(request.app, session, matter_id, cohort_id, user)

    @router.get("/{cohort_id}/export")
    def export(matter_id: str, cohort_id: str, request: Request, user=Depends(authenticate)):
        with request.app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            value = cohort_view(request.app, session, matter_id, cohort_id, user)
            return Response(canonical(value), media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="private-cohort-{value["id"]}.json"'})

    return router
