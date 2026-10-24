"""Unregistered V2 controller/ASGI integration. Explicit mock backend only.

No live provider configuration, key loading, installation or native inference.
The trusted controller must bind actual read-only volumes and the independently
retained anchor; request JSON supplies none of these objects or permissions.
"""

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import sealed_control_journal as control
import sealed_volume as volume
from immutable_provider_hook import ENDPOINT, ImmutableExecutionHook
from provider_stage_adapters import ReceiptStore
from signed_provider_contract import decode, encode, nonce, pin, request, sha
from staged_signed_route import COMPLETION_PATH, IDENTITY_PATH, StagedSignedRoute


@dataclass(frozen=True)
class Binding:
    journal_id: str
    operation_id: str
    record_sha256: str
    volume_binding_sha256: str
    pin_bytes: bytes

    def validate(self):
        volume.token(self.journal_id)
        volume.token(self.operation_id)
        volume.digest(self.record_sha256)
        volume.digest(self.volume_binding_sha256)
        actual = pin(decode(self.pin_bytes))
        if encode(actual) != self.pin_bytes:
            volume.reject()
        return actual


@dataclass
class Session:
    credential: str | None = field(default=None, repr=False)
    stage: str = "fresh"
    challenge: str | None = None
    wire_sha256: str | None = None
    native_sha256: str | None = None
    handle: str | None = None


class Controller:
    def __init__(self, journal, binding, *, resolve_identity, clock, checkpoint=None):
        if not isinstance(journal, control.Journal) or journal.journal_id != binding.journal_id:
            volume.reject()
        self.journal, self.binding, self.runtime = journal, binding, binding.validate()
        self.resolve_identity, self.clock, self.checkpoint = resolve_identity, clock, checkpoint
        self.context = ContextVar("staged-controller-session", default=None)
        self.check()

    def session(self):
        session = self.context.get()
        if not isinstance(session, Session):
            volume.reject()
        return session

    def point(self, name):
        if self.checkpoint is not None:
            self.checkpoint(name)

    def checked(self, db, *, nonce_state=None):
        control.eligible(db, self.binding.operation_id, {"sealed"})
        row = db.execute("SELECT record,generation FROM operations WHERE id=?", (self.binding.operation_id,)).fetchone()
        record = volume.validate_record(decode(row[0].encode()))
        if (sha(row[0].encode()) != self.binding.record_sha256
                or record["volume_binding_sha256"] != self.binding.volume_binding_sha256
                or record["manifest_digest"] != "sha256:" + self.runtime["model_digest_sha256"]):
            volume.reject()
        if nonce_state is not None:
            session = self.session()
            found = db.execute("SELECT state,wire_sha FROM nonces WHERE nonce=? AND generation=?", (session.challenge, row[1])).fetchone()
            if found != (nonce_state, session.wire_sha256):
                volume.reject()
        return record

    def check(self, *, nonce_state=None):
        with self.journal.connect(readonly=True) as db:
            return self.checked(db, nonce_state=nonce_state)

    def current_identity(self):
        session = self.session()
        if session.credential is None or encode(pin(self.resolve_identity(
                session.credential, self.runtime["model_id"], self.runtime["route_sha256"]))) != self.binding.pin_bytes:
            volume.reject()

    def identity(self, credential, model, route):
        self.check()
        actual = pin(self.resolve_identity(credential, model, route))
        if encode(actual) != self.binding.pin_bytes:
            volume.reject()
        session = self.session()
        if session.credential is not None and session.credential != credential:
            volume.reject()
        session.credential = credential  # RAM only, never receipts, diagnostics or repr.
        return actual

    def reserve(self, runtime, raw, expectation):
        session = self.session()
        if session.stage != "fresh" or encode(pin(runtime)) != self.binding.pin_bytes:
            volume.reject()
        self.current_identity()
        self.check()
        value = request(raw, runtime)
        session.challenge = nonce(expectation["nonce"])
        session.wire_sha256 = sha(encode({"pin": runtime, "request_sha256": sha(raw), "expectation": expectation}))
        native = {"model": "sha256:" + runtime["model_digest_sha256"], "messages": value["messages"],
                  "stream": False, "think": False, "options": {"num_ctx": runtime["model_context_units"],
                  "num_predict": value["max_completion_tokens"], "temperature": 0}}
        session.native_sha256 = sha(encode(native))
        self.journal.reserve_nonce(self.binding.operation_id, session.challenge, session.wire_sha256)
        session.stage = "reserved"
        self.point("reserved")

    def admit(self, outgoing):
        session = self.session()
        if (session.stage != "reserved" or outgoing.method != "POST" or str(outgoing.url) != ENDPOINT + "/api/chat"
                or sha(outgoing.content) != session.native_sha256 or "authorization" in outgoing.headers):
            volume.reject()
        self.point("before_admission")
        self.current_identity()
        with self.journal.connect() as db:
            self.checked(db, nonce_state="reserved")
            changed = db.execute("UPDATE nonces SET state='consumed' WHERE nonce=? AND state='reserved' AND wire_sha=?",
                                 (session.challenge, session.wire_sha256)).rowcount
            if changed != 1:
                volume.reject()
        session.stage = "admitted"
        self.point("admitted")
        self.current_identity()
        self.check(nonce_state="consumed")

    def release(self, *, completion):
        self.point("before_release")
        self.current_identity()
        session = self.session()
        if completion and session.stage != "receipt_consumed":
            volume.reject()
        self.check(nonce_state="consumed" if completion else None)
        session.stage = "released"  # A local one-use release boundary, not a future execution grant.


class Snapshot:
    def __init__(self, root, controller):
        self.root, self.controller, self.pin = Path(root), controller, controller.binding.pin_bytes
        self.verify()

    def verify(self):
        expected = self.controller.check()
        observed = volume.seal(self.root, self.controller.journal, self.controller.binding.operation_id,
                               self.controller.binding.volume_binding_sha256)
        if observed["record"] != expected or observed["proof"]["content_identity_sha256"] != expected["content_sha256"]:
            volume.reject()
        self.controller.check()
        return expected["manifest_digest"]


class GuardedTransport(httpx.AsyncBaseTransport):
    def __init__(self, controller, delegate):
        self.controller, self.delegate = controller, delegate

    async def handle_async_request(self, outgoing):
        self.controller.admit(outgoing)
        response = None
        try:
            response = await self.delegate.handle_async_request(outgoing)
            self.controller.current_identity()
            self.controller.check(nonce_state="consumed")
            return response
        except BaseException:
            if response is not None:
                await response.aclose()
            raise

    async def aclose(self):
        await self.delegate.aclose()


class GuardedReceipts:
    def __init__(self, controller, store):
        if not isinstance(store, ReceiptStore):
            volume.reject()
        self.controller, self.store = controller, store

    def begin(self, runtime, raw, expectation, *, now):
        self.controller.reserve(runtime, raw, expectation)
        handle = self.store.begin(runtime, raw, expectation, now=now)
        self.controller.session().handle = handle
        return handle

    def complete(self, handle, response, current_pin, reference, *, attempts, now):
        session = self.controller.session()
        if session.stage != "admitted" or session.handle != handle:
            volume.reject()
        self.controller.point("before_complete")
        self.controller.current_identity()
        self.controller.check(nonce_state="consumed")
        self.store.complete(handle, response, current_pin, reference, attempts=attempts, now=now)
        self.controller.check(nonce_state="consumed")
        session.stage = "completed"

    def consume(self, handle, *, now):
        session = self.controller.session()
        if session.stage != "completed" or session.handle != handle:
            volume.reject()
        self.controller.point("before_consume")
        self.controller.current_identity()
        self.controller.check(nonce_state="consumed")
        result = self.store.consume(handle, now=now)
        self.controller.check(nonce_state="consumed")
        session.stage = "receipt_consumed"
        return result


class GuardedApplication:
    def __init__(self, route, controller):
        self.route, self.controller = route, controller

    async def __call__(self, scope, receive, send):
        token = self.controller.context.set(Session())
        captured = []
        status, body = 400, encode({"error": "staged_request_rejected"})

        async def buffer(message):
            if len(captured) >= 2:
                volume.reject()
            captured.append(message)

        try:
            self.controller.check()
            await self.route(scope, receive, buffer)
            if (len(captured) != 2 or captured[0].get("type") != "http.response.start"
                    or captured[1].get("type") != "http.response.body" or captured[1].get("more_body", False)
                    or not isinstance(captured[1].get("body"), bytes) or len(captured[1]["body"]) > 24576):
                volume.reject()
            if captured[0]["status"] == 200:
                self.controller.release(completion=scope.get("path") == COMPLETION_PATH)
                if scope.get("path") not in {IDENTITY_PATH, COMPLETION_PATH}:
                    volume.reject()
                status, body = 200, captured[1]["body"]
            elif captured[0]["status"] == 503:
                status, body = 503, encode({"error": "staged_capacity_unavailable"})
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # Never emit credentials, case text, native errors or buffered signed responses.
        finally:
            self.controller.context.reset(token)
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": body})


def build(root, journal, binding, *, key, issuer_key_id, receipts, resolve_identity, clock, transport, checkpoint=None):
    # An explicit mock transport is mandatory in this staged qualification factory.
    # There is no default, real socket backend, environment proxy or cloud fallback.
    if not isinstance(transport, httpx.MockTransport):
        volume.reject()
    controller = Controller(journal, binding, resolve_identity=resolve_identity, clock=clock, checkpoint=checkpoint)
    snapshot = Snapshot(root, controller)
    guarded = GuardedReceipts(controller, receipts)
    hook = ImmutableExecutionHook(snapshot, clock=clock, transport=GuardedTransport(controller, transport))
    route = StagedSignedRoute(key, issuer_key_id, resolve_identity=controller.identity, hook=hook, receipts=guarded, clock=clock)
    return GuardedApplication(route, controller)
