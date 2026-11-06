"""Exclusive disposable retention of an independently reviewed recipient receipt."""

import secrets
import sqlite3
import time
from dataclasses import asdict, dataclass, field

import operator_enrollment_evidence as e
import private_inventory_receipts as storage
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException
from recipient_observation_readiness import RecipientObservation, result
from retention_authorization_readiness import KeyPin
from sqlalchemy.exc import SQLAlchemyError

SCHEMA = "disposable-recipient-receipt-retention-v1"
PLAN_READY = "ready_for_disposable_recipient_retention_planning"
BUDGET_SECONDS = 16
FAILURES = (ValueError, TypeError, KeyError, InvalidSignature, InvalidTag, OSError,
            sqlite3.Error, SQLAlchemyError)


@dataclass(frozen=True, kw_only=True)
class Permission:
    record_id: str
    receipt_id: str
    plan_sha256: str
    store_sha256: str
    issued_at: int
    expires_at: int
    issuer_signature: str = field(repr=False)
    custodian_signature: str = field(repr=False)

    def message(self, role, key_id):
        claims = asdict(self)
        del claims["issuer_signature"], claims["custodian_signature"]
        return e.encode({"schema": SCHEMA, "action": "retain", "role": role, "key_id": key_id, "claims": claims})


@dataclass(frozen=True, kw_only=True)
class ReopenPin:
    ciphertext_sha256: str
    issued_at: int
    expires_at: int
    signature: str = field(repr=False)

    def message(self, permission, key_id):
        return e.encode({"schema": SCHEMA, "action": "reopen", "permission_sha256": e.sha(e.encode(asdict(permission))),
                         "key_id": key_id, "ciphertext_sha256": self.ciphertext_sha256,
                         "issued_at": self.issued_at, "expires_at": self.expires_at})


def store_binding(store):
    return e.sha(e.encode({"schema": SCHEMA, "context_id": store.context_id, "scope_sha256": store.scope_sha256,
                           "directory_identity": store.identity, "key_sha256": e.sha(store.key)}))


def verify(key, signature, message, issued_at, expires_at, now):
    if key.revoked or not key.not_before <= e.stamp(issued_at) <= now < e.stamp(expires_at) <= key.expires_at:
        e.reject()
    Ed25519PublicKey.from_public_bytes(key.public_key).verify(bytes.fromhex(e.token(signature, 128)), message)


@dataclass(frozen=True, kw_only=True)
class RecipientReceiptRetention:
    observation: RecipientObservation
    store: storage.ReceiptStore
    permission: Permission
    issuer: KeyPin
    custodian: KeyPin
    reopen_pin: ReopenPin | None = None

    def __post_init__(self):
        if (type(self.observation) is not RecipientObservation or type(self.store) is not storage.ReceiptStore
                or type(self.permission) is not Permission
                or (self.reopen_pin is not None and type(self.reopen_pin) is not ReopenPin)):
            e.reject()
        o, parent = self.observation, self.observation.source
        references = parent.source.references
        roots = [o.root, parent.root, parent.source.root, references.store.root]
        profiles, principals = set(), set()
        for review in (o.review, parent.target, references.verifier.target, references.verifier.source.reviews):
            planner = review.planner
            profiles.add(planner.authority.profile_id)
            principals.update((planner.preparer, planner.reviewer))
            roots.extend((planner.authority.root, planner.source.root, planner.journal.root))
            roots.extend(getattr(s, name) for s in review.selections.values()
                         for name in ("case_root", "anchors_root", "stage_root", "host_root"))
        if self.store.key == references.store.key or any(
                self.store.root == root or self.store.root in root.parents or root in self.store.root.parents
                for root in roots):
            e.reject()
        for key, kind in ((self.issuer, "reviewer"), (self.custodian, "acknowledger")):
            if (type(key) is not KeyPin or key.kind != kind or key.profile_id in profiles
                    or key.principal_id in principals or key.issuer_context_sha256 != self.store.scope_sha256
                    or key.store_context_sha256 != self.permission.store_sha256):
                e.reject()
        for name in ("key_id", "principal_id", "profile_id", "public_key"):
            values = (self.issuer, self.custodian, *o.keys.values())
            if len({getattr(key, name) for key in values[:2]}) != 2 or any(
                    getattr(key, name) == getattr(previous, name) for key in values[:2] for previous in values[2:]):
                e.reject()
        e.token(self.permission.record_id, 32)
        e.token(self.permission.receipt_id, 32)
        e.token(self.permission.plan_sha256)
        if self.permission.store_sha256 != store_binding(self.store):
            e.reject()

    def _authorize(self, planner, scope, actor, *, reopen):
        now, permit = planner.clock(), self.permission
        planner.authority.recheck(actor, now=now)
        if planner.actor(scope, "reviewer") != actor:
            raise PermissionError
        if self.observation.binding() != self.store.scope_sha256:
            e.reject()
        verify(self.issuer, permit.issuer_signature, permit.message("issuer", self.issuer.key_id),
               permit.issued_at, permit.expires_at, now)
        verify(self.custodian, permit.custodian_signature, permit.message("custodian", self.custodian.key_id),
               permit.issued_at, permit.expires_at, now)
        if reopen:
            pin = self.reopen_pin
            if pin is None or not permit.issued_at <= e.stamp(pin.issued_at) < e.stamp(pin.expires_at) <= permit.expires_at:
                e.reject()
            verify(self.custodian, pin.signature, pin.message(permit, self.custodian.key_id),
                   pin.issued_at, pin.expires_at, now)
        return now

    def dispatch(self, scope, operation, **request):
        o, permit = self.observation, self.permission
        planner = o.review.planner
        deadline = time.monotonic() + BUDGET_SECONDS
        published = False
        try:
            actor = planner.actor(scope, "reviewer")
            reopen = operation == "reopen"
            fields = {"record_id", "ciphertext_sha256"} if reopen else {"record_id"}
            if (operation not in {"retain", "reopen"} or set(request) != fields
                    or e.token(request["record_id"], 32) != permit.record_id):
                e.reject()
            record_id = permit.record_id
            now = self._authorize(planner, scope, actor, reopen=reopen)
            spec, proof = o.specifications[permit.receipt_id], o.reviews[permit.receipt_id]
            aad = e.encode({"schema": SCHEMA, "record_id": record_id, "store_sha256": permit.store_sha256})
            with o.admission():
                before = o.observe(), o.source.observe()
                receipt, _, decision, raws = o.read(spec, proof, actor, now)
            if decision["decision"] != "accept" or permit.issued_at < decision["reviewed_at"]:
                e.reject()
            plain = e.encode({"schema": SCHEMA, "receipt": receipt, "permission": asdict(permit)})
            if reopen:
                digest = e.token(request["ciphertext_sha256"])
                if digest != self.reopen_pin.ciphertext_sha256:
                    e.reject()
                raw = storage._read(self.store, record_id, digest)
                offset = len(storage.MAGIC)
                if AESGCM(self.store.key).decrypt(raw[offset:offset + 12], raw[offset + 12:], aad) != plain:
                    e.reject()
            o.budget(deadline)
            checked = o.dispatch(scope, "plan", entry_id=spec.receipt_id, specification_sha256=spec.sha256,
                                 review_set_sha256=proof.sha256)
            if checked["state"] == "budget_exhausted":
                raise TimeoutError
            if checked["state"] == "denied":
                raise PermissionError
            plan = checked["recipient_retention_plan"]
            if (checked["state"] != PLAN_READY or e.sha(e.encode(plan)) != permit.plan_sha256
                    or permit.expires_at > plan["expires_at"]):
                e.reject()
            with o.admission():
                if not reopen:
                    nonce = secrets.token_bytes(12)
                    raw = storage.MAGIC + nonce + AESGCM(self.store.key).encrypt(nonce, plain, aad)
                    digest = e.sha(raw)
                if before != (o.observe(), o.source.observe()):
                    e.reject()
                if reopen and storage._read(self.store, record_id, digest) != raw:
                    e.reject()
                now = self._authorize(planner, scope, actor, reopen=reopen)
                if o.read(spec, proof, actor, now)[3] != raws:
                    e.reject()
                o.budget(deadline)
                if not reopen:
                    storage._publish(self.store, record_id, raw)
                    published = True
                    if before != (o.observe(), o.source.observe()):
                        e.reject()
                    now = self._authorize(planner, scope, actor, reopen=False)
                    if o.read(spec, proof, actor, now)[3] != raws:
                        e.reject()
                    o.budget(deadline)
            return result("recipient_receipt_reopened" if reopen else "recipient_receipt_retained", schema=SCHEMA,
                          read_only=reopen, record_id=record_id, ciphertext_sha256=digest, receipt_sha256=proof.receipt_sha256,
                          expires_at=self.reopen_pin.expires_at if reopen else permit.expires_at)
        except storage.RetentionUncertain:
            return result("retention_uncertain", schema=SCHEMA)
        except TimeoutError:
            state = "budget_exhausted"
        except (PermissionError, HTTPException):
            state = "denied"
        except FileExistsError:
            state = "retention_conflict"
        except FAILURES:
            state = "unverifiable"
        return result("retention_uncertain" if published else state, schema=SCHEMA)
