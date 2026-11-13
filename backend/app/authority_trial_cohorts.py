"""Confidential human authority-trial inventories, never pooled legal scoring."""

import json
from collections import defaultdict
from contextlib import ExitStack, contextmanager

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import Field, model_validator
from sqlalchemy import func, select

from . import analysis_authorities as authorities
from . import authority_adjudications as adjudications
from . import authority_comparisons as comparisons
from . import authority_findings as findings
from . import authority_trials as trials
from .auth import authenticate, require_child, require_matter
from .content_scope import has_case_scope
from .db import Record, User, digest, now
from .evidence_prompt import canonical
from .firm_rbac import permissions_for
from .practice import StrictInput, _audit

RECIPE = "human-authority-trial-cohort-v1"
SUPPORTED_RECIPES = {"human-authority-trial-cohort-v1"}
KIND = "authority_trial_cohort"
ADMISSION = "authority_cohort_admission"
MAX_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 60
MAX_TRIALS = 12


class Selection(StrictInput):
    trial_id: str = Field(pattern=r"^atr-[a-f0-9]{24}-[a-f0-9]{32}$")


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
    return "aca-" + digest(ident)[:32]


def _route(store, session, matter_id, ident, user):
    row = require_child(session, ident, trials.KIND, matter_id, user)
    data = store.decode(row)
    route = data.get("route")
    if (
        not isinstance(route, list)
        or len(route) != 4
        or route[0] != matter_id
        or any(not isinstance(part, str) or not 1 <= len(part) <= 64 for part in route)
    ):
        raise HTTPException(409, "Deneme üst kayıtları doğrulanamadı.")
    trials._require(store, session, tuple(route), ident, user)
    return tuple(route)


@contextmanager
def _guards(app, session, matter_id, selections, user):
    # Check private membership and sealed routes before opening any public join.
    routes = sorted({_route(app.state.store, session, matter_id, item.trial_id, user) for item in selections})
    with ExitStack() as stack:
        for route in routes:
            stack.enter_context(
                authorities._guard(app, findings._public_data(app, session, *route[:3], user))
            )
        yield
    require_matter(session, matter_id, user)


def _record_ids(value):
    result = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if (key == "id" or key.endswith("_id")) and isinstance(item, str) and 1 <= len(item) <= 64:
                result.add(item)
            result.update(_record_ids(item))
    elif isinstance(value, list):
        for item in value:
            result.update(_record_ids(item))
    return result


def _entry(app, session, matter_id, selection, user):
    store = app.state.store
    route = _route(store, session, matter_id, selection.trial_id, user)
    value = trials._view(app, session, route, selection.trial_id, user)
    if not value["public_source_access"] or not value["protocol"]:
        raise HTTPException(409, "Seçilen denemenin kaynakları bekletiliyor; grup içeriği açıklanamaz.")
    capture = {key: item for key, item in value.items() if key != "can_record"}
    plan, event = capture["protocol"], capture["snapshot"]
    ids = _record_ids(capture) | set(route[1:])
    ids.discard(matter_id)  # Workspace authorization/status are pinned separately.
    ids.update(
        {
            trials._head_id(selection.trial_id),
            trials._admission_id(selection.trial_id),
            findings._head_id(route[2]),
            comparisons._head_id(route[3]),
        }
    )
    if event:
        ids.add(trials._admission_id(capture["capture_id"]))
        ids.update(
            adjudications._head_id(event["basis"]["comparison_id"], ident) for ident in plan["reviewer_ids"]
        )
    if len(ids) > 2048:
        raise HTTPException(409, "Denemenin dayanak envanteri çalışma sınırını aşıyor.")
    records = []
    for ident in sorted(ids):
        row = session.get(Record, ident, populate_existing=True)
        if row and (row.firm_id != user.firm_id or row.matter_id != matter_id):
            raise HTTPException(403, "Deneme dayanağının özel çalışma alanı kapsamı değişti.")
        records.append(
            {
                "id": ident,
                "kind": row.kind if row else None,
                "sha256": digest(canonical(store.view(row))) if row else None,
            }
        )
    people = {
        plan["owner_id"],
        plan["basis"]["baseline_author_id"],
        plan["basis"]["review"]["reviewer_id"],
        *plan["reviewer_ids"],
    }
    if event:
        people.add(event["basis"]["comparison"]["reviewer_id"])
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
        "recipes": [RECIPE, trials.RECIPE, findings.RECIPE, comparisons.RECIPE, adjudications.RECIPE],
        "semantic_dimensions_sha256": digest(canonical(adjudications.DIMENSIONS)),
        "finding_dimensions_sha256": digest(canonical(findings.DIMENSIONS)),
        "input_keys": list(trials.INPUT_KEYS),
        "matter_status": store.decode(require_matter(session, matter_id, user)).get("status"),
    }
    result = {"trial_id": selection.trial_id, "route": list(route), "capture": capture, "live_basis": live}
    result["entry_sha256"] = digest(canonical(result))
    return _bounded(result)


def _profile(capture):
    plan = capture["protocol"]
    basis = plan["basis"]
    return {
        "recipe": plan["recipe"],
        "sample_kind": plan["sample_kind"],
        "recipes": {
            key: basis[key] for key in ("recipe", "review_recipe", "comparison_recipe", "adjudication_recipe")
        },
        "semantic_dimensions_sha256": digest(canonical(basis["rubric"])),
        "finding_dimensions_sha256": digest(canonical(basis["finding_dimensions"])),
        "workflow": plan["workflow"],
        "registration_before_baseline": plan["registration_before_baseline"],
        "registration_before_revision": plan["registration_before_revision"],
        "blind_review": plan["blind_review"],
        "account_separation_only": plan["account_separation_only"],
        "model_use": plan["model_use"],
        "effort_phase_limit_seconds": 28800,
        "shared_case_input_keys": list(trials.INPUT_KEYS),
    }


def _outcomes(capture):
    plan, event = capture["protocol"], capture["snapshot"]
    current = capture["freshness"]["status"] == "current"
    observations = event["basis"]["observations"] if event and current else []
    semantic, judgments = [], []

    def values(group, dimension, source_index=None):
        return [
            {"reviewer_id": observation["reviewer_id"], "reviewer_name": observation["reviewer_name"], **item}
            for observation in observations
            for item in observation["assessment"][group]
            if item["dimension"] == dimension
            and (source_index is None or item["source_index"] == source_index)
        ]

    for key, label in plan["basis"]["rubric"].items():
        items = values("observations", key)
        semantic.append(
            {
                "dimension": key,
                "label": label,
                "observations": items,
                "outcome_difference": len({item["outcome"] for item in items}) > 1
                if len(items) == 2
                else None,
                "unknown_observations": 2
                - sum(item["outcome"] not in {"not_assessed", "unresolved"} for item in items),
            }
        )
    sources = plan["basis"]["review"]["context_snapshot"]["manifest"]["sources"]
    for index, source in enumerate(sources):
        for key, label in plan["basis"]["finding_dimensions"].items():
            items = values("judgments", key, index)
            judgments.append(
                {
                    "source_index": index,
                    "dimension": key,
                    "label": label,
                    "target_ids": source["selection"]["target_ids"],
                    "observations": items,
                    "outcome_difference": len({item["outcome"] for item in items}) > 1
                    if len(items) == 2
                    else None,
                    "unknown_observations": 2
                    - sum(item["outcome"] not in {"not_assessed", "unresolved"} for item in items),
                }
            )
    effort = event["assessment"] if event else None
    return {
        "current_reviewer_count": len(observations),
        "semantic": semantic,
        "findings": judgments,
        "semantic_observation_slots": len(semantic) * 2,
        "finding_observation_slots": len(judgments) * 2,
        "unknown_semantic_observations": sum(item["unknown_observations"] for item in semantic),
        "unknown_finding_observations": sum(item["unknown_observations"] for item in judgments),
        "outcome_difference_count": sum(
            item["outcome_difference"] is True for item in [*semantic, *judgments]
        )
        if len(observations) == 2
        else None,
        "recorded_effort": effort,
        "effort_accounted": bool(current and event and event["effort_accounted"]),
        "assessment_times": [
            {"reviewer_id": item["reviewer_id"], "review_seconds": item["assessment"]["review_seconds"]}
            for item in observations
        ],
        "adverse_scopes": [
            {"reviewer_id": item["reviewer_id"], "scope": item["assessment"]["adverse_scope"]}
            for item in observations
        ],
        "adverse_recall": None,
        "preparation_time_gain": None,
        "gpu_compute_seconds": None,
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
        inputs[plan["basis"]["input_sha256"]].append(ident)
        baseline = plan["basis"]["baseline_content"]
        versions[(plan["basis"]["baseline_version_id"], digest(canonical(baseline)))].append(ident)
        for document in {item["document_id"] for item in baseline["source_snapshots"]}:
            private_sources[document].append({"trial_id": ident, "family_sha256": family})
        sources = plan["basis"]["review"]["context_snapshot"]["manifest"]["sources"]
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
                "capture_present": bool(capture["snapshot"]),
                "capture_complete": capture["capture_complete"],
                "capture_id": capture["capture_id"],
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
        "scope": "same_workspace_private_human_authority_trials",
        "matter_id": matter_id,
        **spec.model_dump(),
        "entries": entries,
        "reconciliation": reconcile(entries, spec.reserved_family_sha256),
        "model_use": "none",
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
    ident = "atc-" + digest(matter_id)[:20] + "-" + digest(user.id + ":" + body.request_id)[:32]
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
                _audit(session, user, "authority_trial_cohort_frozen", ident, matter_id)
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


def authority_trial_cohorts_router():
    router = APIRouter(
        prefix="/api/v1/matters/{matter_id}/authority-trial-cohorts",
        tags=["private-human-authority-trial-cohorts"],
    )

    @router.get("/candidates")
    def candidates(
        matter_id: str,
        request: Request,
        limit: int = Query(default=10, ge=1, le=20),
        offset: int = Query(default=0, ge=0),
        user=Depends(authenticate),
    ):
        app, store = request.app, request.app.state.store
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            rows = session.scalars(
                select(Record)
                .where(
                    Record.kind == trials.KIND, Record.matter_id == matter_id, Record.firm_id == user.firm_id
                )
                .order_by(Record.created_at.desc(), Record.id)
                .limit(limit)
                .offset(offset)
            )
            rows = list(rows)
            results = []
            with _guards(app, session, matter_id, [Selection(trial_id=row.id) for row in rows], user):
                for row in rows:
                    route = _route(store, session, matter_id, row.id, user)
                    view = trials._view(app, session, route, row.id, user)
                    results.append(
                        {
                            "trial_id": row.id,
                            "registered_at": view["registered_at"],
                            "title": view["protocol"]["title"] if view["protocol"] else None,
                            "freshness": view["freshness"],
                            "capture_present": bool(view["snapshot"]),
                            "capture_id": view["capture_id"],
                        }
                    )
            require_matter(session, matter_id, user)
            return results

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
                    "Content-Disposition": f'attachment; filename="private-authority-cohort-{cohort_id}.json"',
                },
            )

    return router
