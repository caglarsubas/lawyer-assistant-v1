"""Isolated parser API: no database, matter storage, provider credentials or Internet route."""

import asyncio
import hmac
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from threading import BoundedSemaphore

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from .extraction_client import (
    ALLOWED_SUFFIXES,
    MAX_DOCUMENT_BYTES,
    MAX_RESPONSE_BYTES,
    ExtractionError,
    validate_document,
    validate_result,
)

PARSER_TIMEOUT_SECONDS = 60
UPLOAD_TIMEOUT_SECONDS = 30


def parse_document(content, suffix):
    validate_document(content, suffix)
    with tempfile.TemporaryDirectory(prefix="la-parser-") as directory:
        source = Path(directory) / ("input" + suffix)
        source.write_bytes(content)
        source.chmod(0o600)
        # File output prevents an unbounded subprocess pipe from exhausting the API.
        # app.extract also installs CPU/file-size hard limits before parsing.
        with tempfile.TemporaryFile(dir=directory) as output:
            process = subprocess.Popen(
                [sys.executable, "-m", "app.extract", str(source), suffix],
                cwd=directory,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
                     "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                     "OMP_THREAD_LIMIT": "1", "OPENBLAS_NUM_THREADS": "1"},
                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            try:
                process.wait(timeout=PARSER_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as error:
                raise ExtractionError("Parser exceeded its execution budget") from error
            finally:
                # Kill remaining OCR/parser descendants on success as well as failure.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
            if process.returncode != 0:
                raise ExtractionError("Parser did not produce a valid result")
            output.seek(0)
            raw = output.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ExtractionError("Parser output limit exceeded")
        try:
            return validate_result(json.loads(raw))
        except (ValueError, TypeError, RecursionError) as error:
            raise ExtractionError("Parser result was invalid") from error


def create_app(token=None):
    # Never use the main application's dotenv loader or its secret-bearing Settings.
    token = os.environ.get("LA_EXTRACTION_TOKEN", "") if token is None else token
    if len(token) < 32:
        raise ValueError("LA_EXTRACTION_TOKEN must contain at least 32 characters")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    slots = BoundedSemaphore(2)
    app.state.extraction_slots = slots

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready(request: Request):
        if not hmac.compare_digest(request.headers.get("authorization", "").encode(), ("Bearer " + token).encode()):
            raise HTTPException(401, "Unauthorized")
        return {"status": "ready", "protocol": "isolated-extraction-v1",
                "max_document_bytes": MAX_DOCUMENT_BYTES}

    @app.post("/extract")
    async def extract(request: Request):
        if not hmac.compare_digest(request.headers.get("authorization", "").encode(), ("Bearer " + token).encode()):
            raise HTTPException(401, "Unauthorized")
        suffix = request.headers.get("x-document-suffix", "")
        if (suffix not in ALLOWED_SUFFIXES or request.url.query
                or request.headers.get("content-type", "").lower() != "application/octet-stream"
                or request.headers.get("content-encoding", "identity").lower() != "identity"):
            raise HTTPException(415, "Document transport is not admitted")
        length = request.headers.get("content-length")
        if length is not None and (not re.fullmatch(r"[0-9]{1,8}", length)
                                   or not 1 <= int(length) <= MAX_DOCUMENT_BYTES):
            raise HTTPException(413, "Document size is outside the extraction limit")
        if not slots.acquire(blocking=False):
            raise HTTPException(429, "Extraction capacity is full")
        try:
            async def read_body():
                body = bytearray()
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_DOCUMENT_BYTES:
                        raise HTTPException(413, "Document size is outside the extraction limit")
                    body.extend(chunk)
                if not body:
                    raise HTTPException(413, "Empty document")
                if length is not None and len(body) != int(length):
                    raise HTTPException(422, "Document length mismatch")
                return bytes(body)

            content = await asyncio.wait_for(read_body(), timeout=UPLOAD_TIMEOUT_SECONDS)
            result = await run_in_threadpool(parse_document, content, suffix)
            return validate_result(result)
        except (ExtractionError, OSError, subprocess.SubprocessError, TimeoutError):
            raise HTTPException(422, "Document could not be safely extracted") from None
        finally:
            slots.release()

    return app


if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=8002, access_log=False, limit_concurrency=8,
                timeout_keep_alive=5, h11_max_incomplete_event_size=16384)
