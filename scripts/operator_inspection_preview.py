"""Unregistered disposable reviewer preview; never a live login or trust endpoint."""

import asyncio
import base64
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import operator_checksum_handoff as h
import operator_enrollment_evidence as e
import operator_recovery_inventory as inventory
from fastapi import HTTPException

PAGE = "/firm-admin/operator-preview"
SESSION = "/api/v1/firm-admin/disposition-receipt-stage/preview-session"
PREVIEW = "/api/v1/firm-admin/disposition-receipt-stage/preview"
MAX_OUTPUT = 4096
HTML = Path(__file__).with_name("operator_inspection_preview.html").read_bytes()
if len(HTML) > 24576:
    raise ValueError("Preview asset exceeds static budget")
HASHES = {kind: ["'sha256-" + base64.b64encode(hashlib.sha256(raw).digest()).decode() + "'"
                 for raw in re.findall(rb"<" + kind.encode() + rb">(.*?)</" + kind.encode() + rb">", HTML, re.S)]
          for kind in ("style", "script")}
CSP = ("default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; "
       "connect-src 'self'; script-src " + " ".join(HASHES["script"]) + "; style-src " + " ".join(HASHES["style"]))
HEADERS = [(b"cache-control", b"no-store"), (b"vary", b"Cookie"),
           (b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"),
           (b"content-security-policy", CSP.encode())]


def result(state="unavailable", **values):
    return {"schema": "operator-inspection-preview-v1", "state": state, **h.LIMITS,
            "receipt_checksum_disclosed": False, "independent_entry_prefilled": False,
            "preview": None, "preview_sha256": None, **values}


def headers(scope):
    rows = scope.get("headers", [])
    if (scope.get("query_string") or len(rows) > 64 or sum(len(k) + len(v) for k, v in rows) > 16384
            or any(k.lower() in {b"authorization", b"content-encoding", b"transfer-encoding"} for k, _ in rows)):
        e.reject()
    return rows


@dataclass(frozen=True, kw_only=True)
class OperatorInspectionPreview:
    adapter: h.OperatorChecksumAdapter = field(repr=False)
    source_id: str = field(repr=False)
    expected_handoff_sha256: str = field(repr=False)

    def __post_init__(self):
        if not isinstance(self.adapter, h.OperatorChecksumAdapter):
            e.reject()
        source = self.adapter.sources.get(e.token(self.source_id, 32))
        if source is None or source.sha256 != e.token(self.expected_handoff_sha256):
            e.reject()
        # The UI cannot widen its selected source through the existing POST route.
        object.__setattr__(self, "adapter", h.OperatorChecksumAdapter(
            service=self.adapter.service, sources={self.source_id: source}))

    def session(self, scope):
        """Same-origin cookie bootstrap only; CSRF stays in browser memory, never preview metadata."""
        rows = headers(scope)
        p = self.adapter.service.reconciler.disposition.planner
        for key in (b"cookie", b"x-operator-preview"):
            if sum(k.lower() == key for k, _ in rows) != 1:
                raise PermissionError
        if next(v for k, v in rows if k.lower() == b"x-operator-preview") != b"1":
            raise PermissionError
        origins = [v.decode("ascii") for k, v in rows if k.lower() == b"origin"]
        if len(origins) > 1 or origins and origins[0] not in p.authority.app.state.settings.origins:
            raise PermissionError
        cookie = next(v for k, v in rows if k.lower() == b"cookie").decode("ascii")
        if sum(part.partition("=")[0].strip() == "la_session" for part in cookie.split(";")) != 1:
            raise PermissionError
        admission = {**scope, "state": {}}
        try:
            actor = p.authority.resolve(admission, "reviewer", now=p.clock())
            if actor["user_id"] != p.reviewer:
                raise PermissionError
            token = admission["state"]["csrf"]
            if not isinstance(token, str) or not 32 <= len(token) <= 128:
                e.reject()
            p.authority.recheck(actor, now=p.clock())
            return actor, token
        finally:
            guard = admission["state"].get("firm_guard")
            if guard:
                guard.__exit__(None, None, None)

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") == h.PATH:
            return await self.adapter(scope, receive, send)
        status, value, raw = 404, result(), None
        try:
            path = scope.get("path")
            if scope.get("type") != "http" or path not in {PAGE, SESSION, PREVIEW}:
                raise h.NoRoute
            rows = headers(scope)
            method = "POST" if path == PREVIEW else "GET"
            if scope.get("method") != method:
                status = 405
                raise h.NoRoute
            if path == PAGE:
                raw, status = HTML, 200  # Generic instructions only; no actor, pin or source bytes.
            else:
                async with asyncio.timeout(inventory.TOTAL_SECONDS):
                    if path == SESSION:
                        actor, token = self.session(scope)
                        await asyncio.sleep(0)
                        if self.session(scope) != (actor, token):
                            raise PermissionError
                        value, status = {"schema": "disposable-preview-session-v1", "csrf_token": token}, 200
                    else:
                        p = self.adapter.service.reconciler.disposition.planner
                        actor = p.actor({**scope, "state": {}}, "reviewer")
                        if sum(k.lower() == b"content-type" for k, _ in rows) != 1 or next(
                                v for k, v in rows if k.lower() == b"content-type") != b"application/json":
                            e.reject()
                        lengths = [v for k, v in rows if k.lower() == b"content-length"]
                        if len(lengths) > 1 or lengths and (not lengths[0].isdigit() or int(lengths[0]) > h.MAX_BODY):
                            e.reject()
                        request, size = await h.body(receive)
                        if request != {} or lengths and int(lengths[0]) != size:
                            e.reject()
                        source = self.adapter.sources[self.source_id]
                        now = e.stamp(p.clock())
                        h.validate(self.adapter.service, source, now)
                        if source.sha256 != self.expected_handoff_sha256:
                            raise FileExistsError
                        preview = {"source_id": self.source_id, "handoff_sha256": source.sha256,
                                   "provenance_sha256": source.provenance_sha256,
                                   "prepared_at": source.created_at, "expires_at": source.created_at + h.LIFETIME}
                        value = result("prepared_handoff_inspected", preview=preview,
                                       preview_sha256=e.sha(e.encode(preview)))
                        if len(e.encode(value)) > MAX_OUTPUT:
                            raise TimeoutError
                        await asyncio.sleep(0)
                        h.validate(self.adapter.service, source, p.clock())
                        p.authority.recheck(actor, now=p.clock())
                        if p.actor({**scope, "state": {}}, "reviewer") != actor:
                            raise PermissionError
                        finished = e.stamp(p.clock())
                        if (not now <= finished <= source.created_at + h.LIFETIME
                                or source.sha256 != self.expected_handoff_sha256
                                or e.sha(source.receipt_bytes) != source.receipt_sha256
                                or e.sha(source.provenance_bytes) != source.provenance_sha256):
                            raise FileExistsError
                        status = 200
        except (PermissionError, HTTPException):
            status, value = 403, result("denied")
        except TimeoutError:
            status, value = 504, result("budget_exhausted")
        except FileExistsError:
            status, value = 409, result("snapshot_or_publication_conflict")
        except (ValueError, TypeError, KeyError, RecursionError):
            status, value = 400, result("unverifiable")
        except h.NoRoute:
            status, value = (405 if status == 405 else 404), result()
        except Exception:  # noqa: BLE001 - no private diagnostics or partially assembled preview.
            status, value = 503, result()
        raw = raw if status == 200 and raw is not None else e.encode(value)
        await send({"type": "http.response.start", "status": status, "headers": [*HEADERS,
                    (b"content-type", b"text/html; charset=utf-8" if raw is HTML else b"application/json")]})
        await send({"type": "http.response.body", "body": raw})
