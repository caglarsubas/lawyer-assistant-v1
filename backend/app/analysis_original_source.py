"""Open a saved private-analysis source at its exact document version and page."""

import os
import re
import stat
from dataclasses import dataclass
from typing import Annotated

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, Response

from .analysis_reviews import _version
from .auth import authenticate, require_child
from .db import digest
from .evidence_prompt import canonical
from .practice import _audit

PREFIX = "/api/v1/matters/{matter_id}/analyses/{analysis_id}/versions/{version_id}"
PAGE_NUMBER = r"^[1-9][0-9]{0,5}$"
PDF_LOCATOR = re.compile(r"Sayfa ([1-9][0-9]{0,5})")
SHA256 = r"^[a-f0-9]{64}$"
DOCUMENT_ID = re.compile(r"^[a-f0-9]{32}$")
NO_CACHE = {"Cache-Control": "no-store"}
SOURCE_KEYS = ("document_id", "document_revision", "document_sha256", "name", "locator", "passage_sha256")

router = APIRouter(prefix=PREFIX, tags=["private-analysis-original"])


@dataclass(frozen=True, slots=True)
class PageBinding:
    document_id: str
    document_revision: int
    document_sha256: str
    page: int
    page_count: int


def _unavailable():
    return HTTPException(409, "Kaydedilmiş özgün sayfa bağı doğrulanamadı.", headers=NO_CACHE)


def _select(entries, id_key, selected_id, *, absent_status=409):
    if not isinstance(entries, list):
        raise _unavailable()
    matches = [item for item in entries if isinstance(item, dict) and item.get(id_key) == selected_id]
    if not matches and absent_status == 404:
        raise HTTPException(404, "Bu analiz sürümünde dayanak bulunamadı.", headers=NO_CACHE)
    if len(matches) != 1:
        raise _unavailable()
    return matches[0]


def _bind(store, session, user, matter_id, analysis_id, version_id, evidence_id, page,
          version_sha256, quote_sha256):
    require_child(session, analysis_id, "practice_analysis", matter_id, user)
    _, snapshot = _version(store, session, matter_id, analysis_id, version_id, user)
    content = snapshot.get("content")
    if not isinstance(content, dict) or digest(canonical(content)) != version_sha256:
        raise _unavailable()
    selected = _select(content.get("evidence"), "evidence_id", evidence_id, absent_status=404)
    source = _select(content.get("source_snapshots"), "evidence_id", evidence_id)
    if any(not isinstance(selected.get(key), (int if key == "document_revision" else str))
           or selected[key] != source.get(key) for key in SOURCE_KEYS):
        raise _unavailable()

    document_id, revision, source_sha = (selected[key] for key in SOURCE_KEYS[:3])
    locator = PDF_LOCATOR.fullmatch(selected["locator"])
    if (not DOCUMENT_ID.fullmatch(document_id) or type(revision) is not int or revision < 1
            or not re.fullmatch(SHA256, source_sha)
            or not locator or locator[1] != page or selected.get("quote_sha256") != quote_sha256):
        raise _unavailable()
    record = require_child(session, document_id, "document", matter_id, user)
    document = store.decode(record)
    page_count = document.get("page_count")
    if (record.revision != revision or document.get("sha256") != source_sha
            or document.get("name") != selected["name"] or document.get("media_type") != "application/pdf"
            or document.get("original_path") != f"{document_id}.enc"
            or type(page_count) is not int or not 1 <= int(page) <= page_count <= 999999):
        raise _unavailable()
    current = _select(document.get("passages"), "id", evidence_id)
    text = current.get("text")
    start, end = selected.get("start"), selected.get("end")
    if (not isinstance(text, str) or current.get("locator") != selected["locator"]
            or digest(text) != selected["passage_sha256"] or selected.get("full_passage_length") != len(text)
            or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)
            or text[start:end] != selected.get("text") or digest(text[start:end]) != quote_sha256):
        raise _unavailable()
    return PageBinding(document_id, revision, source_sha, int(page), page_count)


def _read_original(store, settings, binding):
    # Fernet's envelope uses 57 fixed bytes, up to 16 bytes of padding, then base64.
    limit = 4 * ((settings.upload_max_bytes + 75) // 3)
    path = settings.data_dir / "documents" / (binding.document_id + ".enc")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise _unavailable()
        encrypted = stream.read(before.st_size + 1)
        after = os.fstat(stream.fileno())
        if (len(encrypted) != before.st_size or after.st_size != before.st_size
                or after.st_mtime_ns != before.st_mtime_ns or after.st_ctime_ns != before.st_ctime_ns):
            raise _unavailable()
    raw = store.cipher.decrypt(encrypted)
    if (not raw.startswith(b"%PDF-") or len(raw) > settings.upload_max_bytes
            or digest(raw) != binding.document_sha256):
        raise _unavailable()
    return raw


@router.get("/evidence/{evidence_id}/original/{page}")
def original_page(
    matter_id: str,
    analysis_id: str,
    version_id: str,
    evidence_id: Annotated[str, Path(min_length=1, max_length=500)],
    page: Annotated[str, Path(pattern=PAGE_NUMBER)],
    version_sha256: Annotated[str, Header(alias="X-Analysis-Content-SHA256", pattern=SHA256)],
    quote_sha256: Annotated[str, Header(alias="X-Quote-SHA256", pattern=SHA256)],
    request: Request,
    user=Depends(authenticate),
):
    if request.query_params or any(len(request.headers.getlist(name)) != 1
                                   for name in ("X-Analysis-Content-SHA256", "X-Quote-SHA256")):
        raise HTTPException(422, "Kaynak bağlantısı tek bir sürüm ve alıntı gerektirir.", headers=NO_CACHE)
    store = request.app.state.store
    try:
        with store.session() as session:
            binding = _bind(store, session, user, matter_id, analysis_id, version_id, evidence_id,
                            page, version_sha256, quote_sha256)
        original = _read_original(store, request.app.state.settings, binding)
        user = authenticate(request)
        with store.session() as session:
            if _bind(store, session, user, matter_id, analysis_id, version_id, evidence_id,
                     page, version_sha256, quote_sha256) != binding:
                raise _unavailable()
            _audit(session, user, "analysis_original_opened", binding.document_id, matter_id)
            session.commit()
    except (InvalidToken, OSError) as exc:
        raise _unavailable() from exc
    return Response(original, media_type="application/pdf", headers={
        **NO_CACHE, "Accept-Ranges": "none", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="source-{binding.document_id}.pdf"',
        "X-Analysis-Content-SHA256": version_sha256,
        "X-Quote-SHA256": quote_sha256,
        "X-Source-SHA256": binding.document_sha256,
        "X-Source-Revision": str(binding.document_revision),
        "X-Source-Page": str(binding.page),
        "X-Source-Page-Count": str(binding.page_count),
    })
