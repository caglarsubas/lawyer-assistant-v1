"""Isolated authenticated capture endpoint sharing the extractor's two slots."""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from .extraction_client import MAX_DOCUMENT_BYTES, MAX_RESPONSE_BYTES, ExtractionError
from .punctuation_client import validate_capture_wire


def parse_capture(content, page):
    with tempfile.TemporaryDirectory(prefix="la-punctuation-") as directory:
        source = Path(directory) / "input.pdf"
        source.write_bytes(content)
        source.chmod(0o600)
        with tempfile.TemporaryFile(dir=directory) as output:
            process = subprocess.Popen(
                [sys.executable, "-m", "app.punctuation_capture", str(source), str(page)], cwd=directory,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
                     "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                     "OMP_THREAD_LIMIT": "1", "OPENBLAS_NUM_THREADS": "1"},
                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL, start_new_session=True)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired as exc:
                raise ExtractionError("Punctuation capture exceeded its execution budget") from exc
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
            if process.returncode != 0:
                raise ExtractionError("Punctuation capture did not produce a valid result")
            output.seek(0)
            raw = output.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ExtractionError("Punctuation capture output limit exceeded")
    try:
        capture = validate_capture_wire(json.loads(raw), hashlib.sha256(content).hexdigest(), page)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ExtractionError("Punctuation capture output is invalid") from exc
    return {**capture, "png": base64.b64encode(capture["png"]).decode("ascii")}


def install_capture_route(app, token):
    @app.post("/punctuation-capture/{page}")
    async def capture_source(page: str, request: Request):
        if (len(request.headers.getlist("authorization")) != 1
                or not hmac.compare_digest(request.headers.get("authorization", "").encode(),
                                           ("Bearer " + token).encode())):
            raise HTTPException(401, "Unauthorized")
        if (not re.fullmatch(r"[1-9][0-9]{0,2}", page) or int(page) > 500 or request.url.query
                or request.headers.get("content-type", "").lower() != "application/octet-stream"
                or request.headers.get("content-encoding", "identity").lower() != "identity"
                or any(len(request.headers.getlist(name)) > 1 for name in
                       ("content-type", "content-length", "content-encoding"))):
            raise HTTPException(415, "Punctuation transport is not admitted")
        length = request.headers.get("content-length")
        if length is not None and (not re.fullmatch(r"[0-9]{1,8}", length)
                                   or not 1 <= int(length) <= MAX_DOCUMENT_BYTES):
            raise HTTPException(413, "Document size is outside the capture limit")
        slots = app.state.extraction_slots
        if not slots.acquire(blocking=False):
            raise HTTPException(429, "Extraction capacity is full")
        try:
            async def read_body():
                body = bytearray()
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_DOCUMENT_BYTES:
                        raise HTTPException(413, "Document size is outside the capture limit")
                    body.extend(chunk)
                if not body or (length is not None and len(body) != int(length)) or not body.startswith(b"%PDF-"):
                    raise HTTPException(422, "Source document is unavailable")
                return bytes(body)
            content = await asyncio.wait_for(read_body(), timeout=10)
            result = await run_in_threadpool(parse_capture, content, int(page))
            from fastapi.responses import JSONResponse
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        except (ExtractionError, OSError, subprocess.SubprocessError, TimeoutError):
            raise HTTPException(422, "Source page could not be safely captured") from None
        finally:
            slots.release()
