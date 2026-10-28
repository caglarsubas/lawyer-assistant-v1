"""Unregistered ASGI adapter over prebound sources, receipt store and host sessions."""

import asyncio
from dataclasses import dataclass, field
from types import MappingProxyType

import operator_enrollment_evidence as e
import operator_inventory_handoff as handoff
import operator_recovery_inventory as inventory
import private_inventory_receipts as receipts
from receipt_provisioning_readiness import Pins, assess

PREFIX, MAX_BODY = "/api/v1/firm-admin/receipt-stage/", 2048


@dataclass(frozen=True, kw_only=True)
class PreparedSource:
    raw: bytes = field(repr=False)
    expected_sha256: str
    selection: dict

    def __post_init__(self):
        handoff._selection(self.selection)
        if (not isinstance(self.raw, bytes) or not 0 < len(self.raw) <= handoff.MAX_BYTES
                or e.sha(self.raw) != e.token(self.expected_sha256)):
            e.reject()
        object.__setattr__(self, "selection", MappingProxyType(dict(self.selection)))


@dataclass(frozen=True, kw_only=True)
class Session:
    actor_sha256: str
    profile_id: str
    reader: inventory.BoundReader


@dataclass(frozen=True, init=False)
class ReceiptAdapter:
    """Host resolver must validate the real cookie, origin, CSRF, RBAC and empty disposable DB.

    Sources, store, independent pins and callbacks are trusted wiring, never HTTP fields.
    No login, provisioning, enumeration, repair or production registration is exposed.
    """
    stage: object
    approved: str
    store: object = field(repr=False)
    profile: object
    pins: Pins
    resolve: object = field(repr=False)
    sources: object = field(repr=False)
    readonly: bool

    def __init__(self, stage, approved_manifest_sha256, store, profile_path, pins, resolve_actor, sources,
                 *, require_readonly=True):
        if (not isinstance(pins, Pins) or not isinstance(store, receipts.ReceiptStore) or not callable(resolve_actor)
                or not isinstance(sources, dict) or len(sources) > inventory.MAX_ITEMS or type(require_readonly) is not bool):
            e.reject()
        for key, source in sources.items():
            e.token(key, 32)
            if not isinstance(source, PreparedSource) or source.selection["context_id"] != pins.context_id:
                e.reject()
        for name, value in zip(("stage", "approved", "store", "profile", "pins", "resolve", "sources", "readonly"),
                (stage, approved_manifest_sha256, store, profile_path, pins, resolve_actor, MappingProxyType(dict(sources)), require_readonly), strict=True):
            object.__setattr__(self, name, value)

    def readiness(self):
        return assess(self.stage, self.approved, self.store, self.profile, self.pins, require_readonly=self.readonly)

    async def actor(self, scope):
        # Host admission is short-lived: nested authenticated controller calls
        # own their separate guards. This stage never claims a joint snapshot.
        admission = {**scope, "state": {}}
        try:
            async with asyncio.timeout(inventory.READ_SECONDS):
                actor = await self.resolve(admission)
        finally:
            guard = admission["state"].get("firm_guard")
            if guard:
                guard.__exit__(None, None, None)
        if (not isinstance(actor, Session) or actor.profile_id != self.pins.profile_id
                or not isinstance(actor.reader, inventory.BoundReader) or actor.reader.scope_sha256 != self.pins.scope_sha256):
            raise PermissionError
        e.token(actor.actor_sha256)
        return actor

    async def body(self, receive):
        raw, frames = b"", 0
        async with asyncio.timeout(inventory.READ_SECONDS):
            while True:
                frame = await receive()
                frames += 1
                if (frame.get("type") != "http.request" or not isinstance(frame.get("body", b""), bytes) or frames > 8
                        or type(frame.get("more_body", False)) is not bool):
                    e.reject()
                raw += frame.get("body", b"")
                if len(raw) > MAX_BODY:
                    e.reject()
                if not frame.get("more_body", False):
                    return e.decode(raw)

    async def __call__(self, scope, receive, send):
        scope = {**scope, "state": {}}
        try:
            await self.respond(scope, receive, send)
        finally:
            guard = scope["state"].get("firm_guard")
            if guard:
                guard.__exit__(None, None, None)

    async def respond(self, scope, receive, send):
        action = scope.get("path", "").removeprefix(PREFIX)
        status, value = 404, {"state": "unavailable", "completion": "unassessed", **dict.fromkeys(inventory.FLAGS, False)}
        try:
            if scope.get("type") != "http" or not scope.get("path", "").startswith(PREFIX) or action not in {"retain", "reobserve", "readiness"}:
                raise LookupError
            if scope.get("method") != "POST":
                status = 405
                raise LookupError
            if scope.get("query_string", b""):
                raise ValueError("Closed endpoint required")
            headers = scope.get("headers", [])
            if len(headers) > 64 or sum(len(k) + len(v) for k, v in headers) > 16384:
                e.reject()
            for name in (b"cookie", b"origin", b"x-csrf-token", b"content-type"):
                if sum(k.lower() == name for k, _ in headers) != 1:
                    e.reject()
            if (next(v for k, v in headers if k.lower() == b"content-type") != b"application/json"
                    or any(k.lower() == b"authorization" for k, _ in headers)):
                e.reject()
            cookie = next(v for k, v in headers if k.lower() == b"cookie").decode("ascii")
            if sum(part.partition("=")[0].strip() == "la_session" for part in cookie.split(";")) != 1:
                e.reject()
            async with asyncio.timeout(25):
                actor = await self.actor(scope)
                ready = self.readiness()
                if ready["state"] != "ready_for_disposable_validation":
                    raise RuntimeError
                body = await self.body(receive)
                if not isinstance(body, dict):
                    e.reject()
                if action == "readiness":
                    if body:
                        e.reject()
                    result = ready
                elif action == "retain":
                    if set(body) != {"source_id", "expected_source_sha256", "record_id"}:
                        e.reject()
                    for key in body:
                        e.token(body[key], 64 if key == "expected_source_sha256" else 32)
                    source = self.sources.get(body["source_id"])
                    if source is None or source.expected_sha256 != body["expected_source_sha256"]:
                        raise LookupError
                    result = await receipts.retain(source.raw, source.expected_sha256, dict(source.selection), self.store,
                                 actor.reader, actor_sha256=actor.actor_sha256, record_id=body["record_id"])
                else:
                    if set(body) != {"record_id", "expected_record_sha256"}:
                        e.reject()
                    result = await receipts.reobserve(self.store, actor.reader, body["record_id"], body["expected_record_sha256"],
                                                     actor_sha256=actor.actor_sha256)
                final = await self.actor(scope)
                if final.actor_sha256 != actor.actor_sha256 or final.profile_id != actor.profile_id:
                    raise PermissionError
                if self.readiness() != ready:
                    raise RuntimeError
                status = {"denied": 403, "conflict": 409, "unverifiable": 409, "unavailable": 503,
                          "partial": 503, "budget_exhausted": 504, "retention_uncertain": 503}.get(result["state"], 200)
                value = result
        except PermissionError:
            status, value = 403, {"state": "denied", "completion": "unassessed", **dict.fromkeys(inventory.FLAGS, False)}
        except TimeoutError:
            status = 504
        except (ValueError, TypeError, KeyError, RecursionError):
            status = 400
        except LookupError:
            pass
        except Exception:
            status = 503  # No error body, private metadata, credential, path or traceback.
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": e.encode(value)})
