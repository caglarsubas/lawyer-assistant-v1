"""Read-only confidential source-selection handoff; never sample qualification."""

from collections import Counter, defaultdict
from itertools import combinations
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field, field_validator
from sqlalchemy import func, select

from . import source_relationships as relationships
from . import source_reviews as reviews
from .db import digest
from .public_sources import SHA256
from .source_review_models import SourceRelationshipEvent, SourceReviewEvent

MAX_SOURCES = 6
MAX_TOTAL_EVENTS = 200
MAX_RECEIPT_BYTES = 512 * 1024
MAX_INSPECTION_SECONDS = 20
STATUSES = ("missing", "unresolved", "stale", "resolved")
LIMITATIONS = [
    "Seçim, tüm derlemin veya bağımsız çalışma örneklerinin kapsamı değildir.",
    "Doğrudan insan görüşleri gösterilir; geçişli kimlik gruplaması veya otomatik birleştirme yapılmaz.",
    "Tam ilişki kapsamı ve tutarlı beyanlar bağımsızlık, haklar, hukuki doğruluk veya yayımlama onayı değildir.",
    "Geçmiş görüşlerin tam kayıtları ayrı çift dosyalarında korunur; burada özetleri ve içerik bağları bulunur.",
    "İmzalanmamış anlık kayıt, dışarı aktarıldıktan sonraki değişiklikleri veya güncel yetkiyi doğrulamaz.",
]


class SelectionInput(reviews.StrictInput):
    source_ids: list[str] = Field(min_length=2, max_length=MAX_SOURCES)

    @field_validator("source_ids")
    @classmethod
    def distinct_sources(cls, values):
        if any(not SHA256.fullmatch(value) for value in values) or len(set(values)) != len(values):
            raise ValueError("İki ile altı farklı tam kaynak paketi seçin")
        return sorted(values)


def _error():
    return HTTPException(409, "Seçili kaynaklar veya incelemeler değişti ya da doğrulanamadı; yeniden açın")


def _pins(session, firm_id, packages):
    """Re-read encrypted head bytes as well as revisions; no permission/result cache."""
    sources = {}
    for package in packages:
        ident = package.detail["id"]
        head = reviews._head(session, firm_id, ident)
        sources[ident] = [head.id, head.revision, digest(head.payload)] if head else None
    pairs = {}
    for left, right in combinations(packages, 2):
        pair_id = digest(relationships._canonical([left.detail["id"], right.detail["id"]]))
        head = relationships._head(session, firm_id, pair_id)
        pairs[pair_id] = [head.id, head.revision, digest(head.payload)] if head else None
    def events(model, heads, limit):
        rows = list(session.scalars(select(model).where(model.firm_id == firm_id, model.head_id.in_(heads))
                                   .order_by(model.head_id, model.revision).limit(limit + 1)))
        if len(rows) > limit:
            raise _error()
        return [[row.id, row.head_id, row.revision, row.created_at, digest(row.payload)] for row in rows]
    return {"sources": sources, "pairs": pairs,
            "source_events": events(SourceReviewEvent, [pin[0] for pin in sources.values() if pin],
                                    MAX_SOURCES * reviews.MAX_EVENTS),
            "pair_events": events(SourceRelationshipEvent, [pin[0] for pin in pairs.values() if pin], MAX_TOTAL_EVENTS)}


def _pair_summary(pair_id, source_ids, revision, source_states, history):
    latest = history[0] if history else None
    stale = latest is not None and latest["source_reviews"] != source_states
    status = ("missing" if latest is None else "stale" if stale else
              "unresolved" if latest["input"]["classification"] == "unresolved" else "resolved")
    # Summarize every verified historical opinion, including those outside the pair
    # screen's visible 50-record window. No source prose or comparison text copied.
    classifications = dict(sorted(Counter(item["input"]["classification"] for item in history).items()))
    return {"pair_id": pair_id, "source_ids": source_ids, "revision": revision, "status": status,
            "history_count": len(history), "history_sha256": digest(relationships._canonical(history)),
            "historical_classifications": classifications,
            "historical_classification_changes": sum(a["input"]["classification"] != b["input"]["classification"]
                                                     for a, b in zip(history, history[1:])),
            "latest": None if latest is None else {
                **{key: latest[key] for key in ("id", "revision", "reviewer", "created_at", "input", "source_reviews")},
                "event_sha256": digest(relationships._canonical(latest)),
                "comparison_sha256": latest["comparison_evidence"]["evidence_sha256"]}}


def _identity_conflicts(pairs):
    declarations = defaultdict(list)
    for pair in pairs:
        if pair["status"] != "resolved":
            continue
        for item in pair["latest"]["input"]["identities"]:
            declarations[item["source_id"]].append({"pair_id": pair["pair_id"],
                                                   "work_ref": item["work_ref"], "version_ref": item["version_ref"]})
    return [{"source_id": source_id, "declarations": values}
            for source_id, values in sorted(declarations.items())
            if len({(value["work_ref"], value["version_ref"]) for value in values}) > 1]


def inspect_selection(request, body, user):
    started = monotonic()

    def checkpoint():
        if monotonic() - started > MAX_INSPECTION_SECONDS:
            raise HTTPException(409, "Seçim incelemesinin süre sınırı aşıldı; daha küçük bir seçimle yeniden deneyin")

    packages = []
    for ident in body.source_ids:
        packages.append(reviews._package(request, ident, user))
        checkpoint()
    store = request.app.state.store
    with store.session() as session:
        before = _pins(session, user.firm_id, packages)
        head_ids = [value[0] for value in before["pairs"].values() if value is not None]
        count = session.scalar(select(func.count()).select_from(SourceRelationshipEvent).where(
            SourceRelationshipEvent.firm_id == user.firm_id, SourceRelationshipEvent.head_id.in_(head_ids)))
        if count > MAX_TOTAL_EVENTS:
            raise HTTPException(409, "Seçimin toplam 200 ilişki görüşü sınırı aşıldı; daha küçük bir seçim inceleyin")
        states = relationships._source_states(store, session, packages, user.firm_id)
        sources = []
        for package in packages:
            ident = package.detail["id"]
            projection = reviews._projection(store, reviews._head(session, user.firm_id, ident), package)
            sources.append({**reviews._binding(package), "title": package.detail["title"],
                            "source_version_id": package.detail["source_version_id"],
                            "review_revision": states[ident]["revision"],
                            "assessments": {category: projection["assessments"].get(category, {}).get("decision")
                                            for category in reviews.CATEGORIES}})
        pairs = []
        for left, right in combinations(packages, 2):
            subset = [left, right]
            ids = [package.detail["id"] for package in subset]
            pair_id = digest(relationships._canonical(ids))
            head = relationships._head(session, user.firm_id, pair_id)
            history = relationships._ledger(store, session, head, subset, pair_id)
            pairs.append(_pair_summary(pair_id, ids, head.revision if head else 0,
                                       {ident: states[ident] for ident in ids}, history))
            checkpoint()
        if _pins(session, user.firm_id, packages) != before or sum(pair["history_count"] for pair in pairs) > MAX_TOTAL_EVENTS:
            raise _error()
    conflicts = _identity_conflicts(pairs)
    counts = {status: sum(pair["status"] == status for pair in pairs) for status in STATUSES}
    result = {"schema_version": "source-selection-handoff-v1",
              "scope_sha256": digest("source-selection-firm:" + user.firm_id),
              "source_ids": body.source_ids, "sources": sources, "pairs": pairs,
              "coverage": {"selected_source_count": len(sources), "expected_pair_count": len(pairs),
                           "pair_status_counts": counts, "all_pairs_current_resolved": counts["resolved"] == len(pairs)},
              "identity_conflicts": conflicts,
              "source_review_gaps": [{"source_id": source["source_id"], "categories": [
                  category for category, decision in source["assessments"].items() if decision != "accepted"]}
                  for source in sources if any(decision != "accepted" for decision in source["assessments"].values())],
              "independent_original_count": None, "independent_originals_verified": False,
              "study_qualified": False, "publication_eligible": False, "current_law_verified": False,
              "confidentiality": "firm_confidential", "signed": False, "limitations": LIMITATIONS}
    encoded = relationships._canonical(result)
    if len(encoded.encode("utf-8")) > MAX_RECEIPT_BYTES:
        raise HTTPException(409, "Seçim dosyasının boyut sınırı aşıldı; daha küçük bir seçim inceleyin")
    # Reopen every full original package and both kinds of head after assembling
    # the snapshot. A source, pair, ownership or payload change discards the result.
    fresh = [reviews._package(request, ident, user) for ident in body.source_ids]
    if [reviews._binding(package) for package in fresh] != [reviews._binding(package) for package in packages]:
        raise _error()
    with store.session() as session:
        if _pins(session, user.firm_id, fresh) != before:
            raise _error()
    reviews._authorize(request, user)
    checkpoint()
    return {"evidence_json": encoded, "evidence_sha256": digest(encoded)}


def source_selection_router():
    router = APIRouter(prefix="/api/v1/public-sources/selection-review", tags=["source-selection"])

    def authorize(request: Request):
        return reviews._authorize(request)

    @router.post("")
    def inspect(body: SelectionInput, request: Request, user=Depends(authorize)):
        return inspect_selection(request, body, user)

    @router.post("/export")
    def export(body: SelectionInput, request: Request, user=Depends(authorize)):
        result = inspect_selection(request, body, user)
        payload = relationships._canonical({"schema_version": "source-selection-dossier-v1", **result})
        reviews._authorize(request, user)
        return Response(payload, media_type="application/json", headers={
            "Content-Disposition": f'attachment; filename="source-selection-{result["evidence_sha256"]}.json"',
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    return router
