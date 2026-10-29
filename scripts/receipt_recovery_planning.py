"""Unregistered, disposable-session review of metadata plans; no recovery executor."""

import asyncio
import os

import operator_enrollment_evidence as e
import operator_recovery_inventory as inventory
import private_inventory_receipts as receipts
import receipt_recovery_inventory as physical
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException
from operator_review_auth import SessionAuthority
from receipt_provisioning_readiness import Pins

ACTIONS = {"single_link_record": "fresh_authorized_reobservation", "unpublished_staging": "preserve_staging_for_review",
           "linked_publication": "preserve_links_and_investigate", "incomplete_staging": "preserve_partial_staging",
           "unverifiable_record": "quarantine_without_mutation", "unaccounted_links": "preserve_and_escalate",
           "unexpected_link_topology": "preserve_and_escalate", "unverifiable_links": "preserve_and_escalate"}
DECISIONS = {"accept": ("exact_inventory_and_actions_checked", "reviewed_for_metadata_planning"),
             "changes_required": ("fresh_inventory_required", "changes_required"),
             "reject": ("recovery_plan_declined", "rejected")}
PLAN_FIELDS = {"schema", "plan_id", "binding_sha256", "inventory", "snapshot_sha256", "actions", "prepared_by",
               "assigned_reviewer", "created_at", "expires_at", *physical.FLAGS}
DECISION_FIELDS = {"schema", "plan_id", "plan_ciphertext_sha256", "plan_sha256", "snapshot_sha256",
                   "reviewed_by", "decision", "reason_code", "reviewed_at", *physical.FLAGS}


def result(state="unavailable", **values):
    return {"schema": "receipt-recovery-plan-access-v1", "state": state, "metadata_only": True,
            "source_read_only": True, "atomic_snapshot": False, "current_authority_assessed": False,
            "content_authenticity": "unassessed", **dict.fromkeys(physical.FLAGS, False), **values}


def actions(observation, selected):
    if (not isinstance(selected, list) or not 1 <= len(selected) <= inventory.MAX_ITEMS
            or any(not isinstance(v, str) for v in selected) or len(set(selected)) != len(selected)):
        e.reject()
    rows = observation["entries"]
    chosen = [r for r in rows if r["entry_id"] in selected]
    if len(chosen) != len(selected):
        e.reject()
    # A plan cannot omit another observed name sharing an inode with its selection.
    inodes = {r["inode_sha256"] for r in chosen}
    if any(r["entry_id"] not in selected for r in rows if r["inode_sha256"] in inodes):
        e.reject()
    return [{"entry_id": r["entry_id"], "action": ACTIONS[r["state"]]} for r in chosen]


class RecoveryPlanner:
    """Trusted wiring only. Source and encrypted journal must be disjoint and independently keyed.

    Accepting a plan records independent metadata review, never permission to unlink,
    repair, adopt an orphan, decrypt source receipts or execute a controller action.
    """

    def __init__(self, source, journal, pins, authority, *, preparer_id, reviewer_id, clock=e.utc):
        if (not isinstance(source, receipts.ReceiptStore) or not isinstance(journal, receipts.ReceiptStore)
                or not isinstance(pins, Pins) or not isinstance(authority, SessionAuthority) or not callable(clock)
                or source.root == journal.root or source.root in journal.root.parents or journal.root in source.root.parents
                or source.key == journal.key or source.context_id != journal.context_id
                or source.scope_sha256 != journal.scope_sha256 or preparer_id == reviewer_id):
            e.reject()
        self.source, self.journal, self.pins, self.authority = source, journal, pins, authority
        self.preparer, self.reviewer, self.clock = e.token(preparer_id, 32), e.token(reviewer_id, 32), clock
        self.validate()
        authority.eligible(self.preparer, "preparer")
        authority.eligible(self.reviewer, "reviewer")

    def validate(self):
        self.authority.validate_profile()
        receipts._root(self.journal)
        if self.authority.profile_id != self.pins.profile_id or self.authority.marker_sha != self.pins.profile_sha256:
            raise PermissionError

    def actor(self, scope, kind=None):
        self.validate()
        headers = scope.get("headers", [])
        if (scope.get("type") != "http" or scope.get("method") != "POST" or scope.get("query_string")
                or not scope.get("path", "").startswith("/api/v1/firm-admin/")
                or len(headers) > 64 or sum(len(k) + len(v) for k, v in headers) > 16384):
            raise PermissionError
        for name in (b"cookie", b"origin", b"x-csrf-token"):
            if sum(k.lower() == name for k, _ in headers) != 1:
                raise PermissionError
        cookie = next(v for k, v in headers if k.lower() == b"cookie").decode("ascii")
        if sum(p.partition("=")[0].strip() == "la_session" for p in cookie.split(";")) != 1:
            raise PermissionError
        admission = {**scope, "state": {}}
        try:
            actor = self.authority.resolve(admission, kind, now=self.clock())
        finally:
            guard = admission["state"].get("firm_guard")
            if guard:
                guard.__exit__(None, None, None)
        if actor["user_id"] not in {self.preparer, self.reviewer}:
            raise PermissionError
        if kind and actor["user_id"] != (self.preparer if kind == "preparer" else self.reviewer):
            raise PermissionError
        return actor

    def reader(self, actor):
        digest = e.sha(e.encode(actor))
        async def authorize():
            self.validate()
            self.authority.recheck(actor, now=self.clock())
            return digest
        async def no_controller_reads(*args):
            raise PermissionError
        return inventory.BoundReader(scope_sha256=self.pins.scope_sha256, authorize=authorize, read=no_controller_reads), digest

    async def observe(self, actor):
        reader, digest = self.reader(actor)
        value = await physical.observe(self.source, reader, self.pins, actor_sha256=digest)
        if value["state"] != "observed_metadata":
            return value
        self.authority.recheck(actor, now=self.clock())
        return value

    def aad(self, kind, ident):
        return e.encode({"schema": "receipt-recovery-encrypted-v1", "kind": kind, "id": ident,
                         "context_id": self.journal.context_id, "scope_sha256": self.journal.scope_sha256,
                         "profile_id": self.pins.profile_id, "profile_sha256": self.pins.profile_sha256})

    def write(self, kind, ident, value):
        plain = e.encode(value)
        if len(plain) > e.MAX_BYTES:
            e.reject()
        nonce = os.urandom(12)
        raw = receipts.MAGIC + nonce + AESGCM(self.journal.key).encrypt(nonce, plain, self.aad(kind, ident))
        receipts._publish(self.journal, ident, raw)
        return e.sha(raw)

    def read(self, kind, ident, expected):
        e.token(ident, 32)
        e.token(expected)
        raw = receipts._read(self.journal, ident, expected)
        offset = len(receipts.MAGIC)
        return e.decode(AESGCM(self.journal.key).decrypt(raw[offset:offset + 12], raw[offset + 12:], self.aad(kind, ident)))

    def plan(self, ident, cipher, digest):
        value = self.read("plan", ident, cipher)
        e.token(digest)
        if (not isinstance(value, dict) or set(value) != PLAN_FIELDS or value["schema"] != "receipt-recovery-plan-v1"
                or value["plan_id"] != ident or e.sha(e.encode(value)) != digest
                or any(value[k] is not False for k in physical.FLAGS)
                or value["snapshot_sha256"] != e.sha(e.encode(value["inventory"]))
                or value["binding_sha256"] != value["inventory"]["binding_sha256"]
                or value["prepared_by"]["user_id"] != self.preparer or value["assigned_reviewer"]["user_id"] != self.reviewer
                or value["prepared_by"]["user_id"] == value["assigned_reviewer"]["user_id"]
                or value["expires_at"] - value["created_at"] != 300
                or value["actions"] != actions(value["inventory"], [r["entry_id"] for r in value["actions"]])):
            e.reject()
        e.stamp(value["created_at"])
        e.stamp(value["expires_at"])
        # Match the independently pinned source even for historical reads.
        reader, actor_hash = self.reader(value["prepared_by"])
        if physical.binding(self.source, reader, self.pins, actor_hash) != value["binding_sha256"]:
            e.reject()
        return value

    def current_actors(self, plan):
        self.authority.recheck(plan["prepared_by"], now=self.clock())
        if self.authority.eligible(self.reviewer, "reviewer") != plan["assigned_reviewer"]:
            raise PermissionError

    async def unchanged(self, actor, snapshot):
        observed = await self.observe(actor)
        if observed["state"] != "observed_metadata" or observed["snapshot_sha256"] != snapshot:
            raise FileExistsError
        return observed

    @staticmethod
    def decision_id(ident, cipher):
        return e.sha(e.encode(["receipt-recovery-decision-v1", ident, cipher]))[:32]

    async def dispatch(self, scope, operation, **request):
        try:
            async with asyncio.timeout(inventory.TOTAL_SECONDS):
                if operation == "inventory":
                    if request:
                        e.reject()
                    return await self.observe(self.actor(scope))
                actor = self.actor(scope, {"prepare": "preparer", "decide": "reviewer", "inspect": None}[operation])
                ident = e.token(request["plan_id"], 32)
                if operation == "prepare":
                    if set(request) != {"plan_id", "expected_snapshot_sha256", "selected_entry_ids"}:
                        e.reject()
                    snap = e.token(request["expected_snapshot_sha256"])
                    observed = await self.unchanged(actor, snap)
                    now = e.stamp(self.clock())
                    value = {"schema": "receipt-recovery-plan-v1", "plan_id": ident, "binding_sha256": observed["inventory"]["binding_sha256"],
                             "inventory": observed["inventory"], "snapshot_sha256": snap,
                             "actions": actions(observed["inventory"], request["selected_entry_ids"]), "prepared_by": actor,
                             "assigned_reviewer": self.authority.eligible(self.reviewer, "reviewer"),
                             "created_at": now, "expires_at": now + 300, **dict.fromkeys(physical.FLAGS, False)}
                    await self.unchanged(actor, snap)
                    self.current_actors(value)
                    cipher = self.write("plan", ident, value)
                    await self.unchanged(actor, snap)
                    self.current_actors(value)
                    return result("pending_independent_review", plan_id=ident, plan_ciphertext_sha256=cipher, plan_sha256=e.sha(e.encode(value)))
                required = {"plan_id", "plan_ciphertext_sha256", "plan_sha256"}
                if set(request) != required | ({"decision", "reason_code"} if operation == "decide" else {"decision_ciphertext_sha256"}):
                    e.reject()
                cipher, digest = request["plan_ciphertext_sha256"], request["plan_sha256"]
                value = self.plan(ident, cipher, digest)
                snap = value["snapshot_sha256"]
                decision_id = self.decision_id(ident, cipher)
                if operation == "decide":
                    decision, reason = request["decision"], request["reason_code"]
                    if decision not in DECISIONS or reason != DECISIONS[decision][0]:
                        e.reject()
                    self.current_actors(value)
                    if not value["created_at"] <= self.clock() <= value["expires_at"]:
                        raise FileExistsError
                    await self.unchanged(actor, snap)
                    record = {"schema": "receipt-recovery-review-v1", "plan_id": ident, "plan_ciphertext_sha256": cipher,
                              "plan_sha256": digest, "snapshot_sha256": snap, "reviewed_by": actor,
                              "decision": decision, "reason_code": reason, "reviewed_at": e.stamp(self.clock()),
                              **dict.fromkeys(physical.FLAGS, False)}
                    self.current_actors(value)
                    self.authority.recheck(actor, now=self.clock())
                    committed = self.write("decision", decision_id, record)
                    await self.unchanged(actor, snap)
                    self.current_actors(value)
                    return result(DECISIONS[decision][1], decision_ciphertext_sha256=committed)
                committed = request["decision_ciphertext_sha256"]
                review = None
                if committed is not None:
                    review = self.read("decision", decision_id, committed)
                    if (not isinstance(review, dict) or set(review) != DECISION_FIELDS or review["schema"] != "receipt-recovery-review-v1"
                            or review["plan_id"] != ident or review["plan_ciphertext_sha256"] != cipher or review["plan_sha256"] != digest
                            or review["snapshot_sha256"] != snap or review["reviewed_by"]["user_id"] != self.reviewer
                            or review["decision"] not in DECISIONS or review["reason_code"] != DECISIONS[review["decision"]][0]
                            or not value["created_at"] <= e.stamp(review["reviewed_at"]) <= value["expires_at"]
                            or any(review[k] is not False for k in physical.FLAGS)):
                        e.reject()
                fresh = await self.observe(actor)
                current = fresh["state"] == "observed_metadata" and fresh["snapshot_sha256"] == snap
                try:
                    self.current_actors(value)
                    if review:
                        self.authority.recheck(review["reviewed_by"], now=self.clock())
                except (PermissionError, HTTPException):
                    current = False
                current = current and value["created_at"] <= self.clock() <= value["expires_at"]
                self.authority.recheck(actor, now=self.clock())
                state = (DECISIONS[review["decision"]][1] if review else "pending_independent_review") if current else "stale_review_retained"
                return result(state, plan=value, review=review, fresh_inventory_state=fresh["state"])
        except (PermissionError, HTTPException):
            return result("denied")
        except TimeoutError:
            return result("budget_exhausted")
        except receipts.RetentionUncertain:
            return result("retention_uncertain")
        except FileExistsError:
            return result("conflict")
        except (InvalidTag, ValueError, TypeError, KeyError, RecursionError):
            return result("unverifiable")
        except Exception:
            return result()  # Never disclose exception text, paths or partial decrypted metadata.
