"""Current HTTP entry point over the source-pinned application factory.

Historical staged reports retain main.py's exact bytes. New runtime behavior is
qualified separately rather than changing what those reports originally bound.
"""

from cryptography.fernet import InvalidToken
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from .config import Settings
from .main import create_app as create_baseline_app


def create_app(settings: Settings | None = None):
    app = create_baseline_app(settings)
    originals = [route for route in app.routes if isinstance(route, APIRoute)
                 and route.path == "/api/v1/matters/{matter_id}/documents/{document_id}/original"
                 and route.methods == {"GET"} and route.name == "original_document"]
    if len(originals) != 1:
        raise RuntimeError("Original-download route identity is unavailable")
    original_endpoint = originals[0].endpoint

    async def original_unavailable(request: Request, error: Exception):
        # Other routes must retain their original error semantics. Authorization,
        # original digest verification and successful-export auditing stay inside
        # the unchanged original endpoint; a failure cannot skip those checks.
        if request.scope.get("endpoint") is not original_endpoint:
            raise error
        detail = ("Özgün kaynak bütünlüğü doğrulanamadı" if isinstance(error, InvalidToken)
                  else "Özgün kaynak kullanılamıyor")
        return JSONResponse(status_code=409, content={"detail": detail}, headers={"Cache-Control": "no-store"})

    app.add_exception_handler(InvalidToken, original_unavailable)
    app.add_exception_handler(OSError, original_unavailable)
    return app
