"""Separate-account observations on exact retained comparisons; never legal approval."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import Field, StrictInt, model_validator
from sqlalchemy import func, select

from . import analysis_authorities as authorities
from . import analysis_reviews
from . import authority_comparisons as comparisons
from . import authority_findings as findings
from .auth import authenticate, require_child, require_matter
from .db import Record, User, digest, now
from .evidence_prompt import canonical
from .exports import render_export
from .firm_rbac import require_permission
from .practice import StrictInput, _audit

RECIPE = "private-authority-independent-adjudication-v1"
SUPPORTED_RECIPES = {RECIPE}
KIND = "authority_adjudication"
HEAD = "authority_adjudication_head"
ADMISSION = "authority_adjudication_admission"
SCOPE = "separate_account_selected_source_semantic_adverse_observations"
MAX_BYTES = 6 * 1024 * 1024
MAX_RECORDS = 100
DIMENSIONS = {
    "meaning": "Pasaj anlamı ve çıkarım desteği",
    "roles": "Olgu, beyan, varsayım, aktör ve olumsuzluk ayrımları",
    "logic": "Öncül, uygulama, sonuç ve mantıksal tutarlılık",
    "conditions": "Koşul, istisna, kronoloji ve eksik unsurlar",
    "adverse": "Seçilen karşı dayanaklar, farklı yorumlar ve kapsam boşlukları",
    "certainty": "Sonuç gücü ve belirsizlik",
}
Dimension = Literal["meaning", "roles", "logic", "conditions", "adverse", "certainty"]


class Links(StrictInput):
    note: str = Field(min_length=3, max_length=2000)
    target_refs: list[str] = Field(default_factory=list, max_length=24)
    private_source_refs: list[str] = Field(default_factory=list, max_length=20)
    public_source_indices: list[StrictInt] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def distinct(self):
        if (
            len(self.note.strip()) < 3
            or any(
                len(set(items)) != len(items)
                for items in (self.target_refs, self.private_source_refs, self.public_source_indices)
            )
            or any(not 1 <= len(key) <= 256 for key in [*self.target_refs, *self.private_source_refs])
        ):
            raise ValueError("Explain every observation using distinct bounded references")
        return self


class Observation(Links):
    dimension: Dimension
    outcome: Literal["supported", "needs_change", "unresolved", "not_assessed"]


class Judgment(Links):
    source_index: StrictInt = Field(ge=0, le=7)
    dimension: findings.Dimension
    outcome: Literal["agree", "disagree", "unresolved", "not_assessed"]


class AdverseScope(StrictInput):
    status: Literal["not_searched", "selected_sources_inspected"]
    inspected_source_indices: list[StrictInt] = Field(default_factory=list, max_length=8)
    limitations: str = Field(min_length=3, max_length=2000)

    @model_validator(mode="after")
    def explained(self):
        if (
            len(self.limitations.strip()) < 3
            or len(set(self.inspected_source_indices)) != len(self.inspected_source_indices)
            or (self.status == "not_searched" and self.inspected_source_indices)
            or (self.status == "selected_sources_inspected" and not self.inspected_source_indices)
        ):
            raise ValueError("Record selected-source inspection or an explicit absence of search")
        return self


class Save(StrictInput):
    expected_basis_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_adjudication_id: str | None = Field(default=None, min_length=1, max_length=64)
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    observations: list[Observation] = Field(min_length=6, max_length=6)
    judgments: list[Judgment] = Field(min_length=6, max_length=48)
    adverse_scope: AdverseScope
    note: str = Field(min_length=3, max_length=2000)
    review_seconds: StrictInt | None = Field(default=None, ge=1, le=28800)

    @model_validator(mode="after")
    def complete(self):
        if (
            len(self.note.strip()) < 3
            or {item.dimension for item in self.observations} != set(DIMENSIONS)
            or len({(item.source_index, item.dimension) for item in self.judgments}) != len(self.judgments)
            or len(canonical(self.model_dump()).encode()) > 128 * 1024
        ):
            raise ValueError("Complete explained distinct observations within 128 KiB")
        return self


def _prefix(comparison_id):
    return "aij-" + digest(comparison_id)[:24] + "-"


def _head_id(comparison_id, reviewer_id):
    return "aih-" + digest(comparison_id + ":" + reviewer_id)[:32]


def _admission_id(ident):
    return "aia-" + digest(ident)[:32]


def _bounded(value):
    if len(canonical(value).encode()) + 2048 > MAX_BYTES:
        raise HTTPException(409, "Değerlendirme 6 MiB sınırını aşıyor; kısmi kayıt oluşturulamaz.")
    return value


def _require(store, session, route, ident, user):
    matter_id, analysis_id, context_id, review_id, comparison_id = route
    require_child(session, analysis_id, "practice_analysis", matter_id, user)
    row = require_child(session, ident, KIND, matter_id, user)
    data = store.decode(row)
    admission = require_child(session, _admission_id(ident), ADMISSION, matter_id, user)
    proof = store.decode(admission)
    try:
        if (
            data["adjudication_sha256"]
            != digest(canonical({key: value for key, value in data.items() if key != "adjudication_sha256"}))
            or tuple(data[key] for key in ("analysis_id", "context_id", "review_id", "comparison_id"))
            != route[1:]
            or data["recipe"] not in SUPPORTED_RECIPES
            or data["scope"] != SCOPE
            or data["basis_sha256"] != digest(canonical(data["basis"]))
            or row.owner_id != data["reviewer_id"]
            or admission.owner_id != row.owner_id
            or proof["id"] != ident
            or proof["sha256"] != data["adjudication_sha256"]
        ):
            raise ValueError("Invalid adjudication binding")
    except (KeyError, TypeError, ValueError):
        raise HTTPException(409, "Değerlendirme bütünlüğü doğrulanamadı.") from None
    return row, data, admission, proof


def _head(store, session, route, reviewer_id, user):
    row = session.get(Record, _head_id(route[-1], reviewer_id), populate_existing=True)
    if not row:
        return None
    row = require_child(session, row.id, HEAD, route[0], user)
    data = store.decode(row)
    if data.get("comparison_id") != route[-1] or data.get("reviewer_id") != reviewer_id:
        raise HTTPException(409, "Değerlendirme sırası doğrulanamadı.")
    _, latest, _, _ = _require(store, session, route, data.get("latest_id"), user)
    if latest["reviewer_id"] != reviewer_id or latest["sequence"] != data.get("sequence"):
        raise HTTPException(409, "Değerlendirme sırası eşleşmiyor.")
    return data


def _capture(app, session, route, user):
    store = app.state.store
    comparison = comparisons._view(app, session, *route, user)
    if not comparison["public_source_access"] or not comparison["snapshot"]:
        raise HTTPException(409, "Karşılaştırma kaynakları bekletiliyor.")
    frozen = comparison["snapshot"]
    comp = frozen["comparison_snapshot"]
    author, _ = analysis_reviews._version(
        store, session, route[0], route[1], comp["candidate_version_id"], user
    )
    excluded = sorted(
        {frozen["reviewer_id"], comp["authority_review_snapshot"]["reviewer_id"], author.owner_id}
    )
    basis = {
        "recipe": RECIPE,
        "scope": SCOPE,
        "dimensions": DIMENSIONS,
        "comparison": frozen,
        "excluded_account_ids": excluded,
        "account_separation_only": True,
    }
    head = _head(store, session, route, user.id, user)
    return _bounded(
        {
            "basis": basis,
            "basis_sha256": digest(canonical(basis)),
            "expected_adjudication_id": head["latest_id"] if head else None,
            "freshness": comparison["freshness"],
            "independent_account": user.id not in excluded,
            "can_record": user.id not in excluded
            and comparison["freshness"]["status"] == "current"
            and store.decode(require_matter(session, route[0], user)).get("status") != "archived",
            "qualification_granted": False,
        }
    )


def _validate(body, capture):
    comp = capture["basis"]["comparison"]["comparison_snapshot"]
    expected = {
        (item["source_index"], item["dimension"])
        for item in capture["basis"]["comparison"]["assessment"]["dispositions"]
    }
    if {(item.source_index, item.dimension) for item in body.judgments} != expected:
        raise HTTPException(422, "Her özgün bulgu beyanını ayrı değerlendirin.")
    public = set(range(len(comp["authority_review_snapshot"]["assessment"]["sources"])))
    targets = {side + ":" + key for side in ("before", "after") for key in comp[side + "_targets"]}
    private = {item["source_ref"] for item in comp["private_sources"]}
    if not set(body.adverse_scope.inspected_source_indices) <= public:
        raise HTTPException(422, "Yalnız saklanan özgün kamu kaynakları kullanılabilir.")
    for item in [*body.observations, *body.judgments]:
        if (
            not set(item.public_source_indices) <= public
            or not set(item.target_refs) <= targets
            or not set(item.private_source_refs) <= private
        ):
            raise HTTPException(422, "Yabancı adım, özel alıntı veya kamu kaynağı kullanılamaz.")
        if item.outcome in {"supported", "agree", "disagree", "needs_change"}:
            if not item.public_source_indices or not item.target_refs or not item.private_source_refs:
                raise HTTPException(422, "Değerlendirilen beyan tam kaynak ve adım bağlantısı gerektirir.")
        if (
            isinstance(item, Judgment)
            and item.outcome in {"agree", "disagree"}
            and item.source_index not in item.public_source_indices
        ):
            raise HTTPException(422, "Bulgu değerlendirmesi kendi özgün kamu kaynağına bağlanmalıdır.")
        if isinstance(item, Observation) and item.outcome == "supported":
            if not any(key.startswith("after:") for key in item.target_refs) or not any(
                key.startswith("after:") for key in item.private_source_refs
            ):
                raise HTTPException(422, "Yeni taslak destek beyanı yeni sürüm adımı ve alıntısı gerektirir.")
        if item.dimension == "adverse" and item.outcome in {"supported", "agree"}:
            if body.adverse_scope.status != "selected_sources_inspected" or not set(
                item.public_source_indices
            ) <= set(body.adverse_scope.inspected_source_indices):
                raise HTTPException(
                    422, "Karşı dayanak beyanının incelenen seçili kaynak kapsamını belirtin."
                )


def _coverage(assessment):
    # Counts describe declared assessment coverage, never correctness or recall.
    return {
        "semantic": {
            "total": len(assessment["observations"]),
            "assessed": sum(
                item["outcome"] in {"supported", "needs_change"} for item in assessment["observations"]
            ),
        },
        "findings": {
            "total": len(assessment["judgments"]),
            "assessed": sum(item["outcome"] in {"agree", "disagree"} for item in assessment["judgments"]),
        },
        "adverse_scope": "selected_sources_only",
        "corpus_completeness": "unknown",
        "adverse_recall": None,
    }


def _view(app, session, route, ident, user):
    store = app.state.store
    row, data, _, proof = _require(store, session, route, ident, user)
    result = {
        key: data[key]
        for key in ("sequence", "reviewer_id", "reviewer_name", "recorded_at", "adjudication_sha256")
    }
    result.update(
        id=row.id,
        snapshot=None,
        public_source_access=False,
        is_latest_for_reviewer=False,
        freshness={"status": "withheld", "reasons": ["post_commit_authorization_pending"]},
        qualification_granted=False,
        legal_approval="not_granted",
    )
    if not proof.get("publication_guard_completed"):
        return result
    try:
        with authorities._guard(app, findings._public_data(app, session, *route[:3], user)):
            capture = _capture(app, session, route, user)
            reasons = list(capture["freshness"]["reasons"])
            if capture["basis_sha256"] != data["basis_sha256"]:
                reasons.append("adjudication_basis_changed")
            head = _head(store, session, route, data["reviewer_id"], user)
            latest = bool(head and head["latest_id"] == ident)
            if not latest:
                reasons.append("newer_reviewer_adjudication_exists")
            reviewer = session.get(User, data["reviewer_id"], populate_existing=True)
            try:
                if not reviewer or reviewer.role not in {"lawyer", "admin"}:
                    raise HTTPException(403)
                require_matter(session, route[0], reviewer)
                require_permission(session, reviewer, "matter.review")
                if reviewer.id in capture["basis"]["excluded_account_ids"]:
                    raise HTTPException(403)
            except HTTPException:
                reasons.append("adjudicator_access_or_separation_changed")
            result.update(
                snapshot=data,
                public_source_access=True,
                is_latest_for_reviewer=latest,
                freshness={"status": "stale" if reasons else "current", "reasons": sorted(set(reasons))},
            )
        require_child(session, ident, KIND, route[0], user)
        return _bounded(result)
    except HTTPException as exc:
        if exc.status_code not in {404, 409}:
            raise
        require_child(session, ident, KIND, route[0], user)
        result.update(
            snapshot=None,
            public_source_access=False,
            freshness={"status": "withheld", "reasons": ["comparison_context_unavailable"]},
        )
        return result


def _finalize(app, route, ident, user):
    store = app.state.store
    with store.session() as session:
        matter = require_matter(session, route[0], user)
        session.refresh(matter, with_for_update=True)
        findings._lawyer(session, route[0], user)
        row, _, admission, proof = _require(store, session, route, ident, user)
        if row.owner_id != user.id:
            raise HTTPException(403)
        proof.update(publication_guard_completed=True, completed_at=now())
        store.update(admission, proof)
        session.commit()


def _lines(value):
    data = value["snapshot"]
    assessment = data["assessment"]
    lines = [
        "GİZLİ — AYRI HESAPTAN ANLAM VE KARŞI DAYANAK DEĞERLENDİRMESİ",
        "Hesap ayrılığı mesleki yeterlilik veya gerçek bağımsızlık belgesi değildir. Hukuki onay verilmez.",
        f"İnceleyen: {data['reviewer_name']} / {data['reviewer_id']}",
        "Değerlendirme SHA-256:",
        data["adjudication_sha256"],
        "Bağlar SHA-256:",
        data["basis_sha256"],
        "Kapsam: " + canonical(data["coverage"]),
        assessment["note"],
        "Beyan edilen inceleme süresi: " + str(assessment["review_seconds"]),
        "Karşı dayanak kapsamı: " + assessment["adverse_scope"]["status"],
        "İncelenen kaynaklar: " + canonical(assessment["adverse_scope"]["inspected_source_indices"]),
        assessment["adverse_scope"]["limitations"],
    ]
    for item in [*assessment["observations"], *assessment["judgments"]]:
        label = str(item.get("source_index", "anlam")) + " / " + item["dimension"]
        lines.extend(
            [
                label + " / " + item["outcome"],
                item["note"],
                "Adımlar: " + ", ".join(item["target_refs"]),
                "Özel alıntılar: " + ", ".join(item["private_source_refs"]),
                "Özgün kamu kaynakları: " + canonical(item["public_source_indices"]),
            ]
        )
    return lines + comparisons._lines({"snapshot": data["basis"]["comparison"]})


def authority_adjudications_router():
    router = APIRouter(
        prefix="/api/v1/matters/{matter_id}/analyses/{analysis_id}/authority-contexts/{context_id}/reviews/{review_id}/comparisons/{comparison_id}/adjudications",
        tags=["private-authority-independent-adjudication"],
    )

    @router.get("/context")
    def context(
        matter_id: str,
        analysis_id: str,
        context_id: str,
        review_id: str,
        comparison_id: str,
        request: Request,
        user=Depends(authenticate),
    ):
        route = (matter_id, analysis_id, context_id, review_id, comparison_id)
        with request.app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            findings._lawyer(session, matter_id, user)
            with authorities._guard(
                request.app, findings._public_data(request.app, session, *route[:3], user)
            ):
                value = _capture(request.app, session, route, user)
            findings._lawyer(session, matter_id, user)
            return value

    @router.get("")
    def listing(
        matter_id: str,
        analysis_id: str,
        context_id: str,
        review_id: str,
        comparison_id: str,
        request: Request,
        limit: int = Query(default=10, ge=1, le=20),
        offset: int = Query(default=0, ge=0),
        user=Depends(authenticate),
    ):
        route = (matter_id, analysis_id, context_id, review_id, comparison_id)
        store = request.app.state.store
        with store.session() as session:
            comparisons._require(store, session, *route, user)
            rows = session.scalars(
                select(Record)
                .where(
                    Record.kind == KIND,
                    Record.matter_id == matter_id,
                    Record.firm_id == user.firm_id,
                    Record.id.startswith(_prefix(comparison_id)),
                )
                .order_by(Record.created_at.desc(), Record.id)
                .limit(limit)
                .offset(offset)
            )
            return [
                {key: data[key] for key in ("sequence", "reviewer_name", "reviewer_id", "recorded_at")}
                | {"id": row.id}
                for row in rows
                for _, data, _, _ in [_require(store, session, route, row.id, user)]
            ]

    @router.post("", status_code=201)
    def save(
        matter_id: str,
        analysis_id: str,
        context_id: str,
        review_id: str,
        comparison_id: str,
        body: Save,
        request: Request,
        user=Depends(authenticate),
    ):
        route = (matter_id, analysis_id, context_id, review_id, comparison_id)
        app, store = request.app, request.app.state.store
        ident = _prefix(comparison_id) + digest(user.id + ":" + body.request_id)[:32]
        request_sha = digest(canonical(body.model_dump(exclude={"request_id"})))
        committed = False
        try:
            with store.session() as session:
                matter = require_matter(session, matter_id, user)
                session.refresh(matter, with_for_update=True)
                current_user = findings._lawyer(session, matter_id, user)
                if session.get(Record, ident):
                    row, data, _, _ = _require(store, session, route, ident, user)
                    if row.owner_id != user.id or data["request_sha256"] != request_sha:
                        raise HTTPException(409, "İstek kimliği farklı beyana bağlı.")
                    return _view(app, session, route, ident, user)
                with authorities._guard(app, findings._public_data(app, session, *route[:3], user)):
                    capture = _capture(app, session, route, user)
                    if not capture["independent_account"]:
                        raise HTTPException(
                            403,
                            "Taslak, özgün inceleme ve karşılaştırma yazarından ayrı avukat hesabı gerekli.",
                        )
                    if (
                        not capture["can_record"]
                        or capture["basis_sha256"] != body.expected_basis_sha256
                        or capture["expected_adjudication_id"] != body.expected_adjudication_id
                    ):
                        raise HTTPException(
                            409, "Bağlar veya bu inceleyenin sırası değişti; girdileri yenileyin."
                        )
                    _validate(body, capture)
                    total = session.scalar(
                        select(func.count())
                        .select_from(Record)
                        .where(
                            Record.kind == KIND,
                            Record.matter_id == matter_id,
                            Record.id.startswith(_prefix(comparison_id)),
                        )
                    )
                    if total >= MAX_RECORDS:
                        raise HTTPException(409, "Bu karşılaştırmanın 100 değerlendirme sınırına ulaşıldı.")
                    head = _head(store, session, route, user.id, user)
                    assessment = body.model_dump(
                        include={"observations", "judgments", "adverse_scope", "note", "review_seconds"}
                    )
                    data = dict(
                        zip(
                            ("analysis_id", "context_id", "review_id", "comparison_id"),
                            route[1:],
                            strict=True,
                        )
                    )
                    data.update(
                        recipe=RECIPE,
                        scope=SCOPE,
                        basis=capture["basis"],
                        basis_sha256=capture["basis_sha256"],
                        assessment=assessment,
                        coverage=_coverage(assessment),
                        previous_adjudication_id=body.expected_adjudication_id,
                        sequence=head["sequence"] + 1 if head else 1,
                        reviewer_id=current_user.id,
                        reviewer_name=current_user.name,
                        recorded_at=now(),
                        request_sha256=request_sha,
                        immutable=True,
                        qualification_granted=False,
                        legal_approval="not_granted",
                        model_use="none",
                        runtime_authorization="none",
                    )
                    data["adjudication_sha256"] = digest(canonical(data))
                    _bounded(data)
                    store.add(session, KIND, user, data, matter_id, record_id=ident)
                    store.add(
                        session,
                        ADMISSION,
                        user,
                        {
                            "id": ident,
                            "sha256": data["adjudication_sha256"],
                            "publication_guard_completed": False,
                        },
                        matter_id,
                        record_id=_admission_id(ident),
                    )
                    pointer = {
                        "comparison_id": comparison_id,
                        "reviewer_id": user.id,
                        "latest_id": ident,
                        "sequence": data["sequence"],
                    }
                    if head:
                        store.update(session.get(Record, _head_id(comparison_id, user.id)), pointer)
                    else:
                        store.add(
                            session,
                            HEAD,
                            user,
                            pointer,
                            matter_id,
                            record_id=_head_id(comparison_id, user.id),
                        )
                    _audit(session, user, "authority_comparison_adjudicated", ident, matter_id)
                    session.flush()
                    session.expire_all()
                    latest = _capture(app, session, route, user)
                    if (
                        not latest["can_record"]
                        or latest["basis_sha256"] != body.expected_basis_sha256
                        or latest["expected_adjudication_id"] != ident
                    ):
                        raise HTTPException(409, "Kayıt sırasında değerlendirme dayanakları değişti.")
                    findings._lawyer(session, matter_id, user)
                    session.commit()
                    committed = True
            _finalize(app, route, ident, user)
            with store.session() as session:
                return _view(app, session, route, ident, user)
        except Exception:
            if not committed:
                raise
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "Değerlendirme kaydedildi; son izin kontrolü tamamlanamadı. Yeni girdilerle ayrı kayıt gerekli.",
                    "outcome": "committed_needs_revalidation",
                    "needs_revalidation": True,
                    "id": ident,
                },
            )

    @router.get("/{adjudication_id}")
    def detail(
        matter_id: str,
        analysis_id: str,
        context_id: str,
        review_id: str,
        comparison_id: str,
        adjudication_id: str,
        request: Request,
        user=Depends(authenticate),
    ):
        route = (matter_id, analysis_id, context_id, review_id, comparison_id)
        with request.app.state.store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            return _view(request.app, session, route, adjudication_id, user)

    @router.get("/{adjudication_id}/export")
    def export(
        matter_id: str,
        analysis_id: str,
        context_id: str,
        review_id: str,
        comparison_id: str,
        adjudication_id: str,
        request: Request,
        format: Literal["json", "docx", "pdf"] = "json",
        user=Depends(authenticate),
    ):
        route = (matter_id, analysis_id, context_id, review_id, comparison_id)
        app, store = request.app, request.app.state.store
        with store.session() as session:
            matter = require_matter(session, matter_id, user)
            session.refresh(matter, with_for_update=True)
            value = _view(app, session, route, adjudication_id, user)
            if not value["public_source_access"] or value["freshness"]["status"] != "current":
                raise HTTPException(409, "Güncel ve izinli değerlendirme gerekli; aktarım kapalı.")
            with authorities._guard(app, findings._public_data(app, session, *route[:3], user)):
                response = (
                    Response(
                        canonical(value),
                        media_type="application/json",
                        headers={
                            "Content-Disposition": f'attachment; filename="private-authority-adjudication-{adjudication_id}.json"'
                        },
                    )
                    if format == "json"
                    else render_export(_lines(value), adjudication_id, format)
                )
                session.expire_all()
                latest = _view(app, session, route, adjudication_id, user)
                if (
                    not latest["public_source_access"]
                    or latest["freshness"]["status"] != "current"
                    or latest["adjudication_sha256"] != value["adjudication_sha256"]
                ):
                    raise HTTPException(409, "Aktarım sırasında değerlendirme dayanakları değişti.")
            require_child(session, adjudication_id, KIND, matter_id, user)
            return response

    return router
