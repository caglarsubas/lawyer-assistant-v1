"""Revision-guarded research reviews for the current application runtime."""

from typing import Literal

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy.orm.exc import StaleDataError

from .auth import authenticate, require_child
from .db import now
from .graph import GraphBackendError
from .main import Input, audit
from .research import finalize_product_authorization, guard_product_graph, mark_authorization_pending

PRODUCT_REVIEW_PATH = "/api/v1/matters/{matter_id}/products/{product_id}/review"


class ReviewInput(Input):
    expected_revision: int = Field(strict=True, ge=1)
    claim_id: str | None = None
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=2000)


def product_review_conflict(record):
    return JSONResponse(status_code=409, headers={"Cache-Control": "no-store"}, content={
        "detail": "Çıktı başka bir inceleme veya işlemde değişti. Güncel kaydı açın.",
        "outcome": "revision_conflict",
        "product_id": record.id,
        "current_revision": record.revision,
    })


def review_product(matter_id: str, product_id: str, body: ReviewInput, request: Request, user=Depends(authenticate)):
    store = request.app.state.store
    committed = None
    try:
        with store.session() as session:
            record = require_child(session, product_id, "product", matter_id, user)
            if record.revision != body.expected_revision:
                return product_review_conflict(record)
            data = store.decode(record)
            with guard_product_graph(data, request.app.state.graph):
                if data["status"] in ("stale", "reviewed"):
                    raise HTTPException(409, "Bu sürüm değiştirilemez; yeni araştırma başlatın")
                if body.claim_id:
                    claim = next((c for c in data["claims"] if c["id"] == body.claim_id), None)
                    if not claim:
                        raise HTTPException(404, "Bulgu bulunamadı")
                    if claim.get("review_status") in ("approved", "rejected"):
                        prior = {key: claim[key] for key in (
                            "review_status", "review_note", "reviewed_by", "reviewed_at",
                        ) if key in claim}
                        claim.setdefault("review_history", []).append({
                            **prior, "product_revision": record.revision,
                        })
                    claim.update(
                        review_status="approved" if body.decision == "approve" else "rejected",
                        review_note=body.note,
                        reviewed_by=user.id,
                        reviewed_at=now(),
                    )
                elif body.decision == "approve":
                    if (
                        data.get("critical_gaps")
                        or not data["claims"]
                        or any(c["review_status"] != "approved" for c in data["claims"])
                    ):
                        raise HTTPException(409, "Kritik eksikler veya incelenmemiş bulgular var")
                    data["status"] = "reviewed"
                else:
                    data["status"] = "needs_review"
                mark_authorization_pending(data, 'review')
                store.update(record, data)
                audit(session, user, "product_reviewed", record.id, matter_id)
                session.commit()
                committed = {'product_id': record.id, 'revision': record.revision,
                             'recorded_status': data['status']}

        return finalize_product_authorization(store, committed['product_id'], committed['revision'])
    except Exception as exc:
        if committed is None:
            if isinstance(exc, StaleDataError):
                # The ORM compare-and-swap lost after admission. The write and its audit
                # insert rolled back together. Reauthorize before returning metadata.
                with store.session() as session:
                    return product_review_conflict(require_child(session, product_id, "product", matter_id, user))
            if isinstance(exc, GraphBackendError):
                raise HTTPException(409, "Graf sürümünün güncel yayın izni doğrulanamadı; yeniden araştırma gerekli.") from None
            raise
        return JSONResponse(status_code=409, content={
            'detail': 'İnceleme kaydedildi; son yayın izni kontrolü tamamlanamadı. Kaydedilen sürümü inceleyip yeni araştırma başlatın.',
            'outcome': 'committed_needs_revalidation', 'needs_revalidation': True, **committed,
        })
