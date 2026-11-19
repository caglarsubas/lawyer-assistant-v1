"""Append-only source-bound OCR observations for exact saved analysis versions."""

import json
import re
from base64 import b64decode, b64encode
from io import BytesIO
from typing import Annotated

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .analysis_original_source import NO_CACHE, PAGE_NUMBER, PREFIX, SHA256, _bind, _read_original
from .auth import authenticate, require_child, require_matter
from .db import Record, digest
from .evidence_prompt import canonical
from .firm_rbac import require_permission
from .practice import _audit
from .punctuation_assessment import valid_assessment

KIND = "punctuation_observation"
RUN_KIND = "punctuation_capture"
SCHEMA = "private-analysis-punctuation-v1"
MAX_PNG_BYTES = 4_000_000
MAX_PIXELS = 4_000_000
MAX_EVENTS = 8
READER_NAMES = ("raw", "locally_leveled")
EVENT_KEYS = {"status", "field_bounds", "crop_bounds", "coordinate_frame", "readings", "missing_readers",
              "canonical_usable", "region"}
DIAGNOSTICS = {"field_unavailable", "raw_unavailable", "contrast_unavailable", "page_budget", "reader_error",
               "invalid_glyph_vector", "source_ink_unverified"}
META_KEYS = {"analysis_id", "version_id", "evidence_id", "content_sha256", "quote_sha256", "document_id",
             "document_revision", "document_sha256", "page", "page_count", "raster_sha256", "width", "height",
             "event", "event_sha256", "producer_sha256", "producer_recipe", "run_sha256", "status",
             "canonical_usable", "immutable", "run_id", "scope"}
router = APIRouter(prefix=PREFIX, tags=["private-analysis-punctuation"])


def _unavailable():
    return HTTPException(409, "Kaydedilen noktalama gözleminin kaynak bağı doğrulanamadı.", headers=NO_CACHE)


def _require(condition):
    if not condition:
        raise _unavailable()


def _sha(value):
    return isinstance(value, str) and re.fullmatch(SHA256, value) is not None


def _box(value, width, height):
    return (isinstance(value, list) and len(value) == 4 and all(type(item) is int for item in value)
            and 0 <= value[0] < value[2] <= width and 0 <= value[1] < value[3] <= height)


def _contains(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def validate_event(event, width, height):
    """Validate the literal native callback representation without changing its text."""
    _require(isinstance(event, dict) and set(event) <= EVENT_KEYS
             and event.get("canonical_usable") is False
             and event.get("coordinate_frame") == "original_raster_top_left_half_open")
    status, readings, missing = (event.get(key) for key in ("status", "readings", "missing_readers"))
    _require(isinstance(status, str) and isinstance(readings, list) and len(readings) <= 2)
    if "region" in event:
        _require(_box(event["region"], width, height))
    if status == "field_unavailable":
        _require(event.get("field_bounds") is None and event.get("crop_bounds") is None
                 and not readings and missing == list(READER_NAMES))
        return
    field, crop = event.get("field_bounds"), event.get("crop_bounds")
    _require(_box(field, width, height) and _box(crop, width, height) and _contains(crop, field)
             and crop[2] - crop[0] <= 640 and crop[3] - crop[1] <= 150)
    seen = []
    for reading in readings:
        _require(isinstance(reading, dict) and set(reading) == {"reader", "text", "glyphs"}
                 and reading["reader"] in READER_NAMES and reading["reader"] not in seen)
        glyphs = reading["glyphs"]
        _require(isinstance(glyphs, list) and 0 < len(glyphs) <= 20)
        for glyph in glyphs:
            _require(isinstance(glyph, list) and len(glyph) == 2 and isinstance(glyph[0], str)
                     and len(glyph[0]) == 1 and glyph[0] in "0123456789.,-−–"
                     and _box(glyph[1], width, height) and _contains(crop, glyph[1]))
        _require(reading["text"] == "".join(glyph[0] for glyph in glyphs))
        seen.append(reading["reader"])
    _require(missing == [reader for reader in READER_NAMES if reader not in seen])
    if status == "punctuation_disagreement":
        _require(len(readings) == 2 and all(re.fullmatch(r"[-−–]?[0-9][0-9.,]*", reading["text"])
                                          for reading in readings))
        marks = [[(index, char) for index, char in enumerate(reading["text"].lstrip("-−–")) if char in ".,"]
                 for reading in readings]
        _require(marks[0] != marks[1])
    else:
        _require(status in DIAGNOSTICS)


def _png(raw):
    _require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_PNG_BYTES and raw.startswith(b"\x89PNG\r\n\x1a\n"))
    try:
        with Image.open(BytesIO(raw)) as image:
            _require(image.format == "PNG" and 0 < image.width * image.height <= MAX_PIXELS
                     and image.mode in ("L", "RGB", "RGBA") and getattr(image, "n_frames", 1) == 1)
            width, height = image.size
            image.verify()
        return width, height
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as error:
        raise _unavailable() from error


def capture_run_sha256(capture):
    identity = {
        "source_sha256": capture["source_sha256"], "page": capture["page"], "page_count": capture["page_count"],
        "producer_sha256": capture["producer_sha256"], "producer_recipe": capture["producer_recipe"],
        "raster_sha256": digest(capture["png"]), "events": capture["events"],
    }
    if "assessment" in capture:
        identity["assessment"] = capture["assessment"]
    return digest(canonical(identity))


def _run_status(events, assessment=None):
    if assessment is not None and assessment["status"] == "incomplete":
        return "captured_incomplete"
    return "captured_review_observations" if events else "captured_no_alternatives"


def _metadata_sha(metadata):
    return digest(canonical(metadata))


def _ident(firm_id, matter_id, metadata):
    return _context_prefix("pco-", firm_id, matter_id, metadata) + digest(canonical({
        "firm_id": firm_id, "matter_id": matter_id, "metadata": metadata,
    }))[:40]


def _context_prefix(prefix, firm_id, matter_id, metadata):
    context = {key: metadata[key] for key in ("analysis_id", "version_id", "evidence_id", "content_sha256",
                                             "quote_sha256", "page")}
    return prefix + digest(canonical({"firm_id": firm_id, "matter_id": matter_id, "context": context}))[:20]


def _validate_common(metadata):
    # Historical receipts retain their exact original metadata, IDs and digests.
    # Completion was not recorded by v1; absence never establishes completion.
    _require(metadata.get("producer_recipe") in {"native-pdf-punctuation-v1", "native-pdf-punctuation-v2"})
    _require(("assessment" in metadata) == (metadata["producer_recipe"] == "native-pdf-punctuation-v2"))
    if "assessment" in metadata:
        _require(valid_assessment(metadata["assessment"]))
    _require(all(_sha(metadata[key]) for key in ("content_sha256", "quote_sha256", "document_sha256",
                                                "raster_sha256", "producer_sha256", "run_sha256")))
    _require(metadata["canonical_usable"] is False and metadata["immutable"] is True
             and metadata["scope"] == "source_page_context"
             and isinstance(metadata["producer_recipe"], str) and 0 < len(metadata["producer_recipe"]) <= 100
             and all(isinstance(metadata[key], str) and 0 < len(metadata[key]) <= 64
                     for key in ("analysis_id", "version_id", "evidence_id", "document_id")))
    _require(all(type(metadata[key]) is int and metadata[key] > 0
                 for key in ("document_revision", "page", "page_count", "width", "height")))
    _require(metadata["page"] <= metadata["page_count"] <= 999999
             and metadata["width"] * metadata["height"] <= MAX_PIXELS)


def _validate_metadata(metadata):
    _require(isinstance(metadata, dict) and set(metadata) in (META_KEYS, META_KEYS | {"assessment"}))
    _validate_common(metadata)
    _require(metadata["status"] == "review_required" and metadata["canonical_usable"] is False
             and _sha(metadata["event_sha256"]) and metadata["event_sha256"] == digest(canonical(metadata["event"]))
             and isinstance(metadata["run_id"], str) and re.fullmatch(r"pcr-[a-f0-9]{60}", metadata["run_id"]))
    validate_event(metadata["event"], metadata["width"], metadata["height"])


def _source_matches(metadata, scope, binding):
    _require(all(metadata.get(key) == value for key, value in scope.items()))
    _require(metadata.get("document_id") == binding.document_id
             and metadata.get("document_revision") == binding.document_revision
             and metadata.get("document_sha256") == binding.document_sha256
             and metadata.get("page") == binding.page and metadata.get("page_count") == binding.page_count)


def _run_ident(firm_id, matter_id, metadata):
    return _context_prefix("pcr-", firm_id, matter_id, metadata) + digest(canonical({
        "firm_id": firm_id, "matter_id": matter_id, "metadata": metadata,
    }))[:40]


def _read_run(store, row, scope, binding):
    try:
        data = store.decode(row)
        _require(isinstance(data, dict) and set(data) == {"schema", "metadata", "events", "raster_base64"}
                 and data["schema"] == SCHEMA + "-capture")
        metadata, events = data["metadata"], data["events"]
        _require(isinstance(metadata, dict)
                 and set(metadata) in (((META_KEYS - {"event", "event_sha256", "run_id"}) | {"event_count"}),
                                      ((META_KEYS - {"event", "event_sha256", "run_id"}) | {"event_count", "assessment"})))
        _validate_common(metadata)
        _source_matches(metadata, scope, binding)
        _require(row.id == _run_ident(row.firm_id, row.matter_id, metadata) and row.revision == 1
                 and metadata["scope"] == "source_page_context" and metadata["canonical_usable"] is False
                 and metadata["immutable"] is True and isinstance(events, list)
                 and type(metadata["event_count"]) is int and 0 <= metadata["event_count"] == len(events) <= MAX_EVENTS
                 and metadata["status"] == _run_status(events, metadata.get("assessment")))
        if "assessment" in metadata:
            _require(valid_assessment(metadata["assessment"], events))
        encoded = data["raster_base64"]
        _require(isinstance(encoded, str) and len(encoded) <= 4 * ((MAX_PNG_BYTES + 2) // 3))
        png = b64decode(encoded, validate=True)
        _require(digest(png) == metadata["raster_sha256"] and _png(png) == (metadata["width"], metadata["height"]))
        for event in events:
            validate_event(event, metadata["width"], metadata["height"])
        capture = {"source_sha256": metadata["document_sha256"], "page": metadata["page"],
                                        "page_count": metadata["page_count"], "png": png, "events": events,
                                        "producer_sha256": metadata["producer_sha256"], "producer_recipe": metadata["producer_recipe"]}
        if "assessment" in metadata:
            capture["assessment"] = metadata["assessment"]
        actual_run = capture_run_sha256(capture)
        _require(actual_run == metadata["run_sha256"])
        return {**metadata, "id": row.id, "created_at": row.created_at,
                "receipt_sha256": _metadata_sha(metadata)}, png, events
    except (InvalidToken, KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise _unavailable() from error


def _read_record(store, session, row, scope, binding):
    try:
        data = store.decode(row)
        _require(isinstance(data, dict) and set(data) == {"schema", "metadata"} and data["schema"] == SCHEMA)
        metadata = data["metadata"]
        _validate_metadata(metadata)
        _source_matches(metadata, scope, binding)
        _require(row.id == _ident(row.firm_id, row.matter_id, metadata) and row.revision == 1
                 and metadata["scope"] == "source_page_context")
        run = session.get(Record, metadata["run_id"])
        _require(run is not None and run.kind == RUN_KIND and run.firm_id == row.firm_id and run.matter_id == row.matter_id)
        receipt, png, events = _read_run(store, run, scope, binding)
        _require(metadata["event"] in events and all(metadata[key] == receipt[key]
                 for key in META_KEYS - {"event", "event_sha256", "run_id", "status"}))
        _require(metadata.get("assessment") == receipt.get("assessment"))
        return {**metadata, "id": row.id, "created_at": row.created_at,
                "observation_sha256": _metadata_sha(metadata)}, png
    except (InvalidToken, KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise _unavailable() from error


def _scope(analysis_id, version_id, evidence_id, content_sha256, quote_sha256):
    return {"analysis_id": analysis_id, "version_id": version_id, "evidence_id": evidence_id,
            "content_sha256": content_sha256, "quote_sha256": quote_sha256}


def _binding(store, session, user, matter_id, scope, page):
    return _bind(store, session, user, matter_id, scope["analysis_id"], scope["version_id"], scope["evidence_id"],
                 page, scope["content_sha256"], scope["quote_sha256"])


def _original(store, settings, binding):
    try:
        return _read_original(store, settings, binding)
    except (InvalidToken, OSError) as error:
        raise _unavailable() from error


def _fresh_actor(user, actor_identity, reauthorize):
    current = reauthorize() if reauthorize is not None else user
    if current is None or (current.id, current.firm_id) != actor_identity:
        raise HTTPException(401, "Oturum veya kurum değişti.", headers=NO_CACHE)
    return current


def retain_capture(store, settings, user, *, matter_id, analysis_id, version_id, evidence_id, page,
                   content_sha256, quote_sha256, capture, reauthorize=None):
    """Retain a server-owned producer result after fresh source and write checks."""
    from .punctuation_capture import PRODUCER_RECIPE, PRODUCER_SHA256

    actor_identity = (user.id, user.firm_id)
    user = _fresh_actor(user, actor_identity, reauthorize)
    scope = _scope(analysis_id, version_id, evidence_id, content_sha256, quote_sha256)
    _require(isinstance(page, str) and re.fullmatch(r"[1-9][0-9]{0,5}", page)
             and _sha(content_sha256) and _sha(quote_sha256))
    with store.session() as session:
        require_permission(session, user, "matter.write")
        binding = _binding(store, session, user, matter_id, scope, page)
    original = _original(store, settings, binding)
    user = _fresh_actor(user, actor_identity, reauthorize)
    _require(isinstance(capture, dict) and set(capture) == {
        "source_sha256", "page", "page_count", "png", "producer_sha256", "producer_recipe", "run_sha256", "events", "assessment",
    })
    _require(capture["producer_sha256"] == PRODUCER_SHA256 and capture["producer_recipe"] == PRODUCER_RECIPE
             and capture["source_sha256"] == binding.document_sha256 == digest(original)
             and type(capture["page"]) is int and capture["page"] == binding.page
             and type(capture["page_count"]) is int and capture["page_count"] == binding.page_count)
    width, height = _png(capture["png"])
    _require(isinstance(capture["events"], list) and len(capture["events"]) <= MAX_EVENTS)
    _require(valid_assessment(capture["assessment"], capture["events"]))
    for event in capture["events"]:
        validate_event(event, width, height)
    _require(len({digest(canonical(event)) for event in capture["events"]}) == len(capture["events"]))
    _require(_sha(capture["run_sha256"]) and capture["run_sha256"] == capture_run_sha256(capture))
    # A detached snapshot prevents caller mutation after validation from changing what is committed.
    events = json.loads(canonical(capture["events"]))
    encoded_png = b64encode(capture["png"]).decode("ascii")
    raster_sha256 = digest(capture["png"])
    common = {**scope, "document_id": binding.document_id, "document_revision": binding.document_revision,
              "document_sha256": binding.document_sha256, "page": binding.page, "page_count": binding.page_count,
              "raster_sha256": raster_sha256, "width": width, "height": height,
              "producer_sha256": capture["producer_sha256"], "producer_recipe": capture["producer_recipe"],
              "run_sha256": capture["run_sha256"], "scope": "source_page_context", "canonical_usable": False,
              "immutable": True, "assessment": json.loads(canonical(capture["assessment"]))}
    run_metadata = {**common, "event_count": len(events),
                    "status": _run_status(events, common["assessment"])}
    run_id = _run_ident(user.firm_id, matter_id, run_metadata)
    metadata = [{**common, "event": event, "event_sha256": digest(canonical(event)), "run_id": run_id,
                 "status": "review_required"} for event in events]
    try:
        return _append(store, settings, user, matter_id, scope, page, binding, metadata, run_metadata, events,
                       encoded_png, actor_identity=actor_identity, reauthorize=reauthorize)
    except IntegrityError:
        # A concurrent retry can win the deterministic key before this transaction flushes.
        return _append(store, settings, user, matter_id, scope, page, binding, metadata, run_metadata, events,
                       encoded_png, existing_only=True, actor_identity=actor_identity, reauthorize=reauthorize)


def _append(store, settings, user, matter_id, scope, page, binding, metadata, run_metadata, events, encoded_png,
            *, actor_identity, reauthorize, existing_only=False):
    retained = []
    with store.session() as session:
        matter = require_matter(session, matter_id, user)
        session.refresh(matter, with_for_update=True)
        require_permission(session, user, "matter.write")
        _require(_binding(store, session, user, matter_id, scope, page) == binding)
        _original(store, settings, binding)
        user = _fresh_actor(user, actor_identity, reauthorize)
        require_permission(session, user, "matter.write")
        _require(_binding(store, session, user, matter_id, scope, page) == binding)
        run_id = _run_ident(user.firm_id, matter_id, run_metadata)
        run = session.get(Record, run_id)
        if run is None:
            _require(not existing_only)
            run = store.add(session, RUN_KIND, user, {"schema": SCHEMA + "-capture", "metadata": run_metadata,
                            "events": events, "raster_base64": encoded_png}, matter_id, record_id=run_id)
            _audit(session, user, "analysis_punctuation_capture_retained", run.id, matter_id)
        else:
            require_child(session, run_id, RUN_KIND, matter_id, user)
        receipt, _, _ = _read_run(store, run, scope, binding)
        _require(receipt["receipt_sha256"] == _metadata_sha(run_metadata))
        for value in metadata:
            ident = _ident(user.firm_id, matter_id, value)
            row = session.get(Record, ident)
            if row is not None:
                require_child(session, ident, KIND, matter_id, user)
                saved, _ = _read_record(store, session, row, scope, binding)
                _require(saved["observation_sha256"] == _metadata_sha(value))
            else:
                _require(not existing_only)
                row = store.add(session, KIND, user, {"schema": SCHEMA, "metadata": value}, matter_id, record_id=ident)
                _audit(session, user, "analysis_punctuation_retained", row.id, matter_id)
                saved, _ = _read_record(store, session, row, scope, binding)
            retained.append(saved)
        user = _fresh_actor(user, actor_identity, reauthorize)
        require_permission(session, user, "matter.write")
        _require(_binding(store, session, user, matter_id, scope, page) == binding)
        session.commit()
    return retained


def _read_scope(request, user, matter_id, scope, page):
    store = request.app.state.store
    with store.session() as session:
        binding = _binding(store, session, user, matter_id, scope, page)
    _original(store, request.app.state.settings, binding)
    return binding


def _recheck(request, matter_id, scope, page, binding):
    user = authenticate(request)
    with request.app.state.store.session() as session:
        _require(_binding(request.app.state.store, session, user, matter_id, scope, page) == binding)


def _headers(request):
    _require(not request.query_params or set(request.query_params.keys()) <= {"limit", "offset", "run_offset", "run_limit"})
    _require(all(len(request.query_params.getlist(key)) == 1 for key in request.query_params))
    if any(len(request.headers.getlist(name)) != 1 for name in ("X-Analysis-Content-SHA256", "X-Quote-SHA256")):
        raise HTTPException(422, "Kaynak bağlantısı tek bir sürüm ve alıntı gerektirir.", headers=NO_CACHE)


@router.get("/evidence/{evidence_id}/punctuation-observations/{page}")
def observations(matter_id: str, analysis_id: str, version_id: str, evidence_id: str,
                 page: Annotated[str, Path(pattern=PAGE_NUMBER)],
                 request: Request, user=Depends(authenticate), limit: int = Query(default=20, ge=1, le=20),
                 offset: int = Query(default=0, ge=0, le=1000), run_offset: int = Query(default=0, ge=0, le=1000),
                 run_limit: int = Query(default=20, ge=1, le=20),
                 content_sha256: str = Header(alias="X-Analysis-Content-SHA256", pattern=SHA256),
                 quote_sha256: str = Header(alias="X-Quote-SHA256", pattern=SHA256)):
    _headers(request)
    scope = _scope(analysis_id, version_id, evidence_id, content_sha256, quote_sha256)
    binding = _read_scope(request, user, matter_id, scope, page)
    store = request.app.state.store
    items, runs = [], []
    with store.session() as session:
        # Opaque context prefixes bound SQL work without exposing source selections in plaintext.
        for kind, prefix, start, count, output in ((KIND, "pco-", offset, limit, items),
                                                  (RUN_KIND, "pcr-", run_offset, run_limit, runs)):
            context_prefix = _context_prefix(prefix, user.firm_id, matter_id, {**scope, "page": binding.page})
            rows = session.scalars(select(Record).where(
                Record.kind == kind, Record.firm_id == user.firm_id, Record.matter_id == matter_id,
                Record.id.startswith(context_prefix),
            ).order_by(Record.created_at, Record.id).offset(start).limit(count + 1)).all()
            for row in rows:
                saved = (_read_run(store, row, scope, binding)[0] if kind == RUN_KIND
                         else _read_record(store, session, row, scope, binding)[0])
                output.append(saved)
    _recheck(request, matter_id, scope, page, binding)
    return JSONResponse({"items": items[:limit], "has_more": len(items) > limit,
                         "runs": runs[:run_limit], "runs_has_more": len(runs) > run_limit}, headers=NO_CACHE)


def _selected(request, user, matter_id, scope, page, observation_id):
    binding = _read_scope(request, user, matter_id, scope, page)
    store = request.app.state.store
    with store.session() as session:
        row = require_child(session, observation_id, KIND, matter_id, user)
        metadata, png = _read_record(store, session, row, scope, binding)
    _recheck(request, matter_id, scope, page, binding)
    return metadata, png


@router.get("/evidence/{evidence_id}/punctuation-observations/{page}/{observation_id}")
def observation(matter_id: str, analysis_id: str, version_id: str, evidence_id: str,
                page: Annotated[str, Path(pattern=PAGE_NUMBER)], observation_id: str,
                request: Request, user=Depends(authenticate),
                content_sha256: str = Header(alias="X-Analysis-Content-SHA256", pattern=SHA256),
                quote_sha256: str = Header(alias="X-Quote-SHA256", pattern=SHA256)):
    _headers(request)
    _require(not request.query_params)
    metadata, _ = _selected(request, user, matter_id,
                             _scope(analysis_id, version_id, evidence_id, content_sha256, quote_sha256),
                             page, observation_id)
    return JSONResponse(metadata, headers=NO_CACHE)


@router.get("/evidence/{evidence_id}/punctuation-observations/{page}/{observation_id}/raster")
def raster(matter_id: str, analysis_id: str, version_id: str, evidence_id: str,
           page: Annotated[str, Path(pattern=PAGE_NUMBER)], observation_id: str,
           request: Request, user=Depends(authenticate),
           content_sha256: str = Header(alias="X-Analysis-Content-SHA256", pattern=SHA256),
           quote_sha256: str = Header(alias="X-Quote-SHA256", pattern=SHA256)):
    _headers(request)
    _require(not request.query_params)
    metadata, png = _selected(request, user, matter_id,
                              _scope(analysis_id, version_id, evidence_id, content_sha256, quote_sha256), page,
                              observation_id)
    return Response(png, media_type="image/png", headers={
        **NO_CACHE, "X-Content-Type-Options": "nosniff", "Accept-Ranges": "none",
        "X-Analysis-Content-SHA256": metadata["content_sha256"], "X-Quote-SHA256": metadata["quote_sha256"],
        "X-Source-SHA256": metadata["document_sha256"], "X-Source-Revision": str(metadata["document_revision"]),
        "X-Source-Page": str(metadata["page"]), "X-Source-Page-Count": str(metadata["page_count"]),
        "X-Punctuation-Observation-SHA256": metadata["observation_sha256"],
        "X-Punctuation-Event-SHA256": metadata["event_sha256"], "X-Source-Raster-SHA256": metadata["raster_sha256"],
    })
