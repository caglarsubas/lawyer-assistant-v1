"""Unregistered authenticated review handoff; metadata decisions grant no trust."""

import asyncio
import re
import threading
from dataclasses import dataclass
from pathlib import Path

import operator_enrollment_evidence as evidence
from fastapi import HTTPException
from operator_review_auth import SessionAuthority

PREFIX = "/api/v1/firm-admin/operator-review/"
HANDOFF = "authenticated-operator-handoff-v1"
DECISION = "authenticated-operator-decision-v1"
DECISIONS = {"accept": "exact_versions_checked", "changes_required": "new_evidence_required", "reject": "evidence_declined"}
MAX_FILES, MAX_BODY, MAX_AGE = 128, 8192, 300


def conflict():
    raise HTTPException(409, "Operator review is stale or already recorded")


@dataclass(frozen=True)
class Target:
    packet_path: Path
    packet_sha256: str
    observation_path: Path
    observation_sha256: str
    stage: Path
    model_root: Path
    journal: object
    binding: object
    trust_root: Path
    api: object

    def source(self, now, *, historical=False):
        raw = evidence.read(self.packet_path)
        if evidence.sha(raw) != self.packet_sha256:
            raise ValueError("Exact packet bytes required")
        created = evidence.stamp(evidence.decode(raw)["created_at"])
        p = evidence.validate_packet(raw, self.packet_sha256, created if historical else now)
        o = evidence.validate_observation(evidence.read(self.observation_path), self.observation_sha256, self.packet_sha256)
        if (o["status"] != "reconciled_for_disposable_mock_validation" or created > now or o["observed_at"] > now
                or (not historical and now >= o["valid_until"])):
            conflict()
        return p, o

    def full(self, now):
        p, o = self.source(now)
        fresh = evidence.reconcile(self.packet_path, self.packet_sha256, self.stage, self.model_root, self.journal,
                                   self.binding, self.trust_root, api=self.api, clock=lambda: now)
        if fresh["status"] != "reconciled_for_disposable_mock_validation" or fresh["evidence"] != o["evidence"]:
            conflict()
        return self.fast(now)

    def fast(self, now):
        p, o = self.source(now)
        evidence.inspect_stage(self.stage, p["package_manifest_sha256"])
        self.api.sealed_volume.owner_dir(self.model_root, readonly=True)
        try:
            _, fence = self.api.readiness.binding_snapshot(self.journal, self.binding)
        except Exception:
            conflict()
        actual_binding = {"journal_id": self.binding.journal_id, "operation_id": self.binding.operation_id,
                          "record_sha256": self.binding.record_sha256, "volume_binding_sha256": self.binding.volume_binding_sha256,
                          "pin_sha256": evidence.sha(self.binding.pin_bytes)}
        if p["binding"] != actual_binding or evidence.sha(evidence.encode({"fence": fence, "binding": actual_binding})) != o["evidence"]["binding_context_sha256"]:
            conflict()
        public = evidence.public_snapshot(self.trust_root)
        if any(public[k] != o["evidence"][k] for k in public):
            conflict()
        e = p["enrollment"]
        if self.api.readiness.enrollment(self.trust_root, fingerprint=e["fingerprint"], issuer=e["issuer_key_id"],
                                        reviewer=e["reviewer"], provisioner=e["provisioned_by"],
                                        confirmation_sha=e["confirmation_sha256"], now=now) != "verified":
            conflict()
        context = evidence.sha(evidence.encode({"packet": self.packet_sha256, "observation": self.observation_sha256, "evidence": o["evidence"]}))
        return p, o, context


class ReviewHandoff:
    actions = ("prepare", "decide", "inspect")

    def __init__(self, authority, target, ledger, *, clock=evidence.utc, checkpoint=None):
        if not isinstance(authority, SessionAuthority) or not isinstance(target, Target):
            raise ValueError("Trusted disposable authority and target required")
        self.authority, self.target = authority, target
        self.ledger = evidence.directory(ledger)
        self.clock, self.checkpoint, self.lock = clock, checkpoint, threading.Lock()
        self.inventory()

    def inventory(self):
        paths = list(self.ledger.iterdir())
        if len(paths) > MAX_FILES or any(not re.fullmatch(r"[0-9a-f]{32}\.(?:handoff|decision)\.json", p.name) for p in paths):
            raise ValueError("Bounded private review inventory required")
        for path in paths:
            evidence.read(path)
        return paths

    def point(self, name):
        if self.checkpoint is not None:
            self.checkpoint(name)  # Trusted qualification hook, never an HTTP field.

    def retain_record(self, path, raw):
        return evidence.retain(path, raw)

    def read_record(self, ident, kind, expected):
        raw = evidence.read(self.ledger / (evidence.token(ident, 32) + "." + kind + ".json"))
        if evidence.sha(raw) != evidence.token(expected):
            conflict()
        record = evidence.decode(raw)
        fields = {"schema", "handoff_id", "packet_sha256", "observation_sha256", "context_sha256", "prepared_by", "reviewer", "created_at", "expires_at", *evidence.FLAGS}
        if kind == "decision":
            fields |= {"handoff_sha256", "reviewed_by", "reviewed_at", "decision", "reason_code"}
        if (set(record) != fields or record["schema"] != (HANDOFF if kind == "handoff" else DECISION)
                or record["handoff_id"] != ident or any(record[k] is not False for k in evidence.FLAGS)
                or record["packet_sha256"] != self.target.packet_sha256 or record["observation_sha256"] != self.target.observation_sha256):
            conflict()
        if kind == "decision" and DECISIONS.get(record["decision"]) != record["reason_code"]:
            conflict()
        return record

    def current(self, record, actor, now):
        p, _, context = self.target.fast(now)
        if (not record["created_at"] <= now < record["expires_at"] or record["context_sha256"] != context
                or record["prepared_by"]["user_id"] != p["enrollment"]["provisioned_by"]
                or record["reviewer"]["user_id"] != p["enrollment"]["reviewer"]
                or record["reviewer"]["user_id"] == record["prepared_by"]["user_id"]
                or actor["user_id"] not in {record["prepared_by"]["user_id"], record["reviewer"]["user_id"]}):
            conflict()
        self.authority.recheck(record["prepared_by"], now=now)
        if self.authority.eligible(record["reviewer"]["user_id"], "reviewer") != record["reviewer"]:
            conflict()
        if "reviewed_by" in record:
            if not record["created_at"] <= record["reviewed_at"] <= now:
                conflict()
            self.authority.recheck(record["reviewed_by"], now=now)
            if {k: record["reviewed_by"][k] for k in record["reviewer"]} != record["reviewer"]:
                conflict()
        self.authority.recheck(actor, now=now)

    def handle(self, scope, value):
        action = scope["path"][len(PREFIX):]
        now = evidence.stamp(self.clock())
        actor = self.authority.resolve(scope, "preparer" if action == "prepare" else "reviewer" if action == "decide" else None, now=now)
        p, o = self.target.source(now, historical=action == "inspect")
        expected_user = p["enrollment"]["provisioned_by" if action == "prepare" else "reviewer"]
        parties = {p["enrollment"]["provisioned_by"], p["enrollment"]["reviewer"]}
        if (action != "inspect" and actor["user_id"] != expected_user) or actor["user_id"] not in parties:
            raise HTTPException(403, "Assigned operator required")
        with self.lock:
            self.inventory()
            if action == "prepare":
                if set(value) != {"request_id", "packet_sha256", "observation_sha256"} or value["packet_sha256"] != self.target.packet_sha256 or value["observation_sha256"] != self.target.observation_sha256:
                    raise ValueError("Exact target required")
                ident = evidence.token(value["request_id"], 32)
                if len(self.inventory()) >= MAX_FILES - 1:
                    conflict()
                reviewer = self.authority.eligible(p["enrollment"]["reviewer"], "reviewer")
                if reviewer["user_id"] == actor["user_id"]:
                    raise HTTPException(403, "Independent authenticated subject required")
                self.target.full(now)
                _, _, context = self.target.fast(evidence.stamp(self.clock()))
                record = {"schema": HANDOFF, "handoff_id": ident, "packet_sha256": self.target.packet_sha256,
                          "observation_sha256": self.target.observation_sha256, "context_sha256": context,
                          "prepared_by": actor, "reviewer": reviewer, "created_at": now,
                          "expires_at": min(now + MAX_AGE, p["expires_at"], o["valid_until"], actor["expires_at"]),
                          **dict.fromkeys(evidence.FLAGS, False)}
                self.point("before_commit")
                self.current(record, actor, evidence.stamp(self.clock()))
                path = self.ledger / (ident + ".handoff.json")
                try:
                    receipt = self.retain_record(path, evidence.encode(record))
                except FileExistsError:
                    conflict()
                self.point("after_commit")
                self.current(record, actor, evidence.stamp(self.clock()))
                return {"status": "pending_independent_review", "handoff_id": ident, "handoff_sha256": receipt["sha256"], **dict.fromkeys(evidence.FLAGS, False)}
            required = {"handoff_id", "handoff_sha256", "decision", "reason_code"} if action == "decide" else {"handoff_id", "handoff_sha256", "decision_sha256"}
            if set(value) != required:
                raise ValueError("Exact review fields required")
            ident = evidence.token(value["handoff_id"], 32)
            handoff = self.read_record(ident, "handoff", value["handoff_sha256"])
            if action == "inspect":
                path = self.ledger / (ident + ".decision.json")
                if not path.exists():
                    self.current(handoff, actor, evidence.stamp(self.clock()))
                    return {"status": "pending_independent_review", "handoff_id": ident, **dict.fromkeys(evidence.FLAGS, False)}
                observed = evidence.sha(evidence.read(path))
                if value["decision_sha256"] is None:
                    self.authority.recheck(actor, now=evidence.stamp(self.clock()))
                    return {"status": "observed_decision_needs_pin", "handoff_id": ident, "decision_sha256": observed, **dict.fromkeys(evidence.FLAGS, False)}
                decision = self.read_record(ident, "decision", value["decision_sha256"])
                if decision["handoff_sha256"] != value["handoff_sha256"]:
                    conflict()
                try:
                    self.current(decision, actor, evidence.stamp(self.clock()))
                    status = "reviewed_for_disposable_handoff"
                except Exception:
                    status = "stale_review_retained"
                self.authority.recheck(actor, now=evidence.stamp(self.clock()))
                return {"status": status, "handoff_id": ident, "decision_sha256": observed, "decision": decision["decision"], **dict.fromkeys(evidence.FLAGS, False)}
            if DECISIONS.get(value["decision"]) != value["reason_code"] or actor["user_id"] != handoff["reviewer"]["user_id"]:
                raise ValueError("Bounded independent decision required")
            if (self.ledger / (ident + ".decision.json")).exists():
                conflict()
            self.current(handoff, actor, evidence.stamp(self.clock()))
            self.target.full(now)
            self.current(handoff, actor, evidence.stamp(self.clock()))
            decision = {**handoff, "schema": DECISION, "handoff_sha256": value["handoff_sha256"], "reviewed_by": actor,
                        "reviewed_at": evidence.stamp(self.clock()), "decision": value["decision"], "reason_code": value["reason_code"]}
            self.point("before_commit")
            self.current(decision, actor, evidence.stamp(self.clock()))
            try:
                receipt = self.retain_record(self.ledger / (ident + ".decision.json"), evidence.encode(decision))
            except FileExistsError:
                conflict()
            self.point("after_commit")
            self.current(decision, actor, evidence.stamp(self.clock()))
            return {"status": "review_recorded_for_disposable_handoff", "handoff_id": ident,
                    "decision_sha256": receipt["sha256"], "decision": value["decision"], **dict.fromkeys(evidence.FLAGS, False)}

    async def __call__(self, scope, receive, send):
        # Keep the existing firm guard through release, including rejected bodies.
        scope = {**scope, "state": {}}
        try:
            await self.respond(scope, receive, send)
        finally:
            guard = scope["state"].get("firm_guard")
            if guard:
                guard.__exit__(None, None, None)

    async def respond(self, scope, receive, send):
        status, result, worker = 200, None, None
        try:
            if scope["type"] != "http" or scope.get("method") != "POST" or scope.get("path") not in {PREFIX + x for x in self.actions} or scope.get("query_string"):
                raise ValueError("Unsupported staged request")
            headers = scope.get("headers", [])
            if len(headers) > 64 or sum(len(k) + len(v) for k, v in headers) > 16384:
                raise ValueError("Header budget exceeded")
            for name in (b"cookie", b"origin", b"x-csrf-token", b"content-type"):
                if sum(key.lower() == name for key, _ in headers) != 1:
                    raise ValueError("Unambiguous session headers required")
            if next(v for k, v in headers if k.lower() == b"content-type") != b"application/json":
                raise ValueError("JSON required")
            cookie = next(v for k, v in headers if k.lower() == b"cookie").decode("ascii")
            if (sum(part.partition("=")[0].strip() == "la_session" for part in cookie.split(";")) != 1
                    or any(k.lower() == b"authorization" for k, _ in headers)):
                raise ValueError("Unambiguous cookie-only authentication required")
            raw = b""
            async with asyncio.timeout(3):
                while True:
                    message = await receive()
                    if message["type"] != "http.request":
                        raise ValueError("Disconnected request")
                    raw += message.get("body", b"")
                    if len(raw) > MAX_BODY:
                        raise HTTPException(413, "Body budget exceeded")
                    if not message.get("more_body"):
                        break
            value = evidence.decode(raw)
            if not isinstance(value, dict):
                raise ValueError("Object required")
            worker = asyncio.create_task(asyncio.to_thread(self.handle, scope, value))
            result = await asyncio.shield(worker)
        except asyncio.CancelledError:
            # An admitted metadata write can finish after a lost acknowledgement.
            # Wait for it before releasing the real firm guard; never replay it.
            if worker is not None:
                try:
                    await worker
                except Exception:
                    pass
            raise
        except Exception as error:
            status = getattr(error, "status_code", 400)
            if status not in {401, 403, 409, 413}:
                status = 400
            result = {"error": "operator_review_rejected", **dict.fromkeys(evidence.FLAGS, False)}
        body = evidence.encode(result)
        await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": body})
