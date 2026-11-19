"""Capture only exact server-owned originals for private saved-analysis review."""

import asyncio
from typing import Annotated

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from fastapi.responses import JSONResponse

from .analysis_original_source import (
    NO_CACHE,
    PAGE_NUMBER,
    PREFIX,
    SHA256,
    _bind,
    _read_original,
    _unavailable,
)
from .analysis_punctuation import retain_capture
from .auth import authenticate
from .extraction_client import ExtractionError
from .firm_rbac import require_permission
from .punctuation_client import PunctuationClient

router = APIRouter(prefix=PREFIX, tags=["private-analysis-punctuation"])


@router.post("/evidence/{evidence_id}/punctuation-observations/{page}")
async def capture_observations(
    matter_id: str, analysis_id: str, version_id: str,
    evidence_id: Annotated[str, Path(min_length=1, max_length=500)],
    page: Annotated[str, Path(pattern=PAGE_NUMBER)],
    content_sha256: Annotated[str, Header(alias="X-Analysis-Content-SHA256", pattern=SHA256)],
    quote_sha256: Annotated[str, Header(alias="X-Quote-SHA256", pattern=SHA256)],
    request: Request, user=Depends(authenticate),
):
    if (request.query_params or any(len(request.headers.getlist(name)) != 1 for name in
                                  ("X-Analysis-Content-SHA256", "X-Quote-SHA256"))):
        raise HTTPException(422, "Tek bir sürüm ve alıntı bağı gereklidir.", headers=NO_CACHE)
    # The request is a selection, never a client-provided raster, reading, or path.
    async def empty_body():
        async for chunk in request.stream():
            if chunk:
                raise HTTPException(422, "Gözlemler yalnızca özgün kaynaktan üretilir.", headers=NO_CACHE)
    try:
        await asyncio.wait_for(empty_body(), timeout=2)
    except TimeoutError:
        raise HTTPException(408, "Denetim isteği tamamlanmadı.", headers=NO_CACHE) from None
    from fastapi.concurrency import run_in_threadpool
    return await run_in_threadpool(_capture, request, user, matter_id, analysis_id, version_id, evidence_id,
                                  page, content_sha256, quote_sha256)


def _capture(request, user, matter_id, analysis_id, version_id, evidence_id, page, content_sha256, quote_sha256):
    store, settings = request.app.state.store, request.app.state.settings
    actor_identity = (user.id, user.firm_id)

    def fresh_actor():
        current = authenticate(request)
        if (current.id, current.firm_id) != actor_identity:
            raise HTTPException(401, "Oturum veya kurum değişti.", headers=NO_CACHE)
        return current

    def fresh_binding(current_user):
        with store.session() as session:
            require_permission(session, current_user, "matter.write")
            return _bind(store, session, current_user, matter_id, analysis_id, version_id, evidence_id,
                         page, content_sha256, quote_sha256)

    try:
        binding = fresh_binding(user)
        if not settings.extraction_url:
            raise HTTPException(503, "Yalıtılmış noktalama denetimi yapılandırılmamış.", headers=NO_CACHE)
        original = _read_original(store, settings, binding)
        user = fresh_actor()
        if fresh_binding(user) != binding:
            raise _unavailable()
        capture = PunctuationClient(settings.extraction_url, settings.extraction_token).execute_capture(original, binding.page)
        user = fresh_actor()
        if fresh_binding(user) != binding:
            raise _unavailable()
        retained = retain_capture(store, settings, user, matter_id=matter_id, analysis_id=analysis_id,
                                  version_id=version_id, evidence_id=evidence_id, page=page,
                                  content_sha256=content_sha256, quote_sha256=quote_sha256, capture=capture,
                                  reauthorize=fresh_actor)
    except (InvalidToken, OSError):
        raise _unavailable() from None
    except ExtractionError:
        raise HTTPException(503, "Özgün sayfanın noktalama denetimi tamamlanamadı. Yeniden deneyebilirsiniz.",
                            headers=NO_CACHE) from None
    return JSONResponse({"retained": True, "observations": len(retained)}, headers=NO_CACHE)
