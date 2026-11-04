"""Unregistered read-only plans and exact acknowledged verification references."""

import fcntl
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from itertools import islice
from types import MappingProxyType

import operator_enrollment_evidence as e
import private_inventory_receipts as receipts
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from destination_snapshot_verification import DestinationVerifier, Snapshot
from destination_snapshot_verification import result as verification_result
from fastapi import HTTPException
from operator_cold_recovery import inventory
from operator_recovery_inputs import FLAGS
from receipt_provisioning_readiness import Pins, fingerprint
from sqlalchemy.exc import SQLAlchemyError

SCHEMA = "verification-reference-readiness-v1"
PLAN_SCHEMA = "verification-retention-plan-v1"
RECORD_SCHEMA = "retained-destination-verification-v1"
MAX_RECORDS, MAX_PLAIN, BUDGET_SECONDS = 8, 16384, 10
PLAN_FIELDS = {"schema", "store_context_sha256", "snapshot", "source_reference", "verification"}
RECORD_FIELDS = {"schema", "record_id", "store_context_sha256", "plan_sha256", "plan", *FLAGS}


def result(state, **values):
    return verification_result(state, **{"schema": SCHEMA, "read_only": True,
        "retention_plan_ready": False, "retention_plan": None, "reobservation": None,
        "host_acknowledgement_pin_matched": False, "genuine_acknowledgement_verified": False, **values})


@dataclass(frozen=True, kw_only=True)
class Reference:
    record_id: str
    ciphertext_sha256: str
    plaintext_sha256: str
    acknowledgement_sha256: str | None

    def __post_init__(self):
        e.token(self.record_id, 32)
        for name in ("ciphertext_sha256", "plaintext_sha256"):
            e.token(getattr(self, name))
        if self.acknowledgement_sha256 is not None:
            e.token(self.acknowledgement_sha256)

    @property
    def sha256(self):
        return e.sha(e.encode(asdict(self)))


@dataclass(frozen=True, kw_only=True)
class AcknowledgementPin:
    record_id: str
    ciphertext_sha256: str
    plaintext_sha256: str
    store_context_sha256: str
    plan_sha256: str
    issuer_context_sha256: str

    def __post_init__(self):
        e.token(self.record_id, 32)
        for name in ("ciphertext_sha256", "plaintext_sha256", "store_context_sha256", "plan_sha256", "issuer_context_sha256"):
            e.token(getattr(self, name))

    @property
    def sha256(self):
        return e.sha(e.encode(asdict(self)))


class VerificationReferences:
    def __init__(self, verifier, store, pins, references, acknowledgements, *, checkpoint=None):
        if (type(verifier) is not DestinationVerifier or type(store) is not receipts.ReceiptStore
                or type(pins) is not Pins or type(references) is not dict or type(acknowledgements) is not dict
                or len(references) > 4 or len(acknowledgements) > 4):
            e.reject()
        for ident, ref in references.items():
            e.token(ident, 32)
            if type(ref) is not Reference:
                e.reject()
        for ident, pin in acknowledgements.items():
            if type(pin) is not AcknowledgementPin or ident != pin.sha256:
                e.reject()
        for service in (verifier.source.reviews, verifier.target):
            p = service.planner
            if store.key in {p.source.key, p.journal.key}:
                e.reject()
            roots = [p.authority.root, p.source.root, p.journal.root]
            roots += [getattr(s, name) for s in service.selections.values()
                      for name in ("case_root", "anchors_root", "stage_root")]
            if any(store.root == root or store.root in root.parents or root in store.root.parents for root in roots):
                e.reject()
        self.verifier, self.store, self.pins = verifier, store, pins
        self.references, self.acknowledgements = MappingProxyType(dict(references)), MappingProxyType(dict(acknowledgements))
        self.lock, self.checkpoint = threading.RLock(), checkpoint
        self.binding()

    def binding(self):
        p, store, pin = self.verifier.target.planner, self.store, self.pins
        receipts._root(store)
        if ((store.context_id, store.scope_sha256, store.identity, fingerprint(store.key)) !=
                (pin.context_id, pin.scope_sha256, pin.store_identity, pin.key_fingerprint)
                or (pin.profile_id, pin.profile_sha256) != (p.authority.profile_id, p.authority.marker_sha)
                or (store.context_id, store.scope_sha256) != (p.journal.context_id, p.journal.scope_sha256)):
            e.reject()
        return e.sha(e.encode({"schema": SCHEMA, "pins": asdict(pin),
                              "destination_context_sha256": self.verifier.context()}))

    def registry(self):
        return e.sha(e.encode({"references": {k: asdict(v) for k, v in self.references.items()},
            "acknowledgements": {k: asdict(v) for k, v in self.acknowledgements.items()}}))

    def aad(self, record_id):
        return e.encode({"schema": RECORD_SCHEMA, "record_id": e.token(record_id, 32),
                         "store_context_sha256": self.binding()})

    def inventory(self):
        self.binding()
        if len(tuple(islice(self.store.root.iterdir(), MAX_RECORDS + 1))) > MAX_RECORDS:
            e.reject()
        rows = inventory(self.store.root)
        if (len(rows) > MAX_RECORDS or any(not re.fullmatch(r"[0-9a-f]{32}\.receipt", r[0])
                or r[4] != os.getuid() or r[5] != 0o600 or r[6] != 1
                or r[7] > MAX_PLAIN + len(receipts.MAGIC) + 28 for r in rows)):
            e.reject()
        return rows

    @contextmanager
    def admission(self):
        deadline = time.monotonic() + 2
        if not self.lock.acquire(timeout=2):
            raise TimeoutError
        fd = None
        try:
            fd = receipts._directory(self.store)
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError from None
                    time.sleep(.01)
            self.binding()
            yield
        finally:
            try:
                if fd is not None:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    finally:
                        os.close(fd)
            finally:
                self.lock.release()

    @staticmethod
    def budget(deadline):
        if time.monotonic() >= deadline:
            raise TimeoutError

    def plan(self, scope, snapshot, source_reference, deadline):
        self.budget(deadline)
        checked = self.verifier.dispatch(scope, "verify", snapshot=snapshot, reference=source_reference)
        self.budget(deadline)
        if checked["state"] == "budget_exhausted":
            raise TimeoutError
        if checked["state"] != "destination_snapshot_verified":
            return None
        return {"schema": PLAN_SCHEMA, "store_context_sha256": self.binding(),
            "snapshot": asdict(Snapshot.parse(snapshot)), "source_reference": asdict(self.verifier.reference),
            "verification": checked["verification"]}

    def record(self, ref):
        raw = receipts._read(self.store, ref.record_id, ref.ciphertext_sha256)
        offset = len(receipts.MAGIC)
        plain = AESGCM(self.store.key).decrypt(raw[offset:offset + 12], raw[offset + 12:], self.aad(ref.record_id))
        if len(plain) > MAX_PLAIN or e.sha(plain) != ref.plaintext_sha256:
            e.reject()
        value = e.decode(plain)
        if (type(value) is not dict or set(value) != RECORD_FIELDS or value["schema"] != RECORD_SCHEMA
                or value["record_id"] != ref.record_id or value["store_context_sha256"] != self.binding()
                or any(value[k] is not False for k in FLAGS) or type(value["plan"]) is not dict
                or set(value["plan"]) != PLAN_FIELDS or value["plan"]["schema"] != PLAN_SCHEMA
                or value["plan"]["store_context_sha256"] != self.binding()
                or value["plan_sha256"] != e.sha(e.encode(value["plan"]))):
            e.reject()
        return value, raw

    def dispatch(self, scope, operation, **request):
        try:
            p = self.verifier.target.planner
            actor = p.actor(scope, "reviewer")  # Before registry, namespace or retained-body inspection.
            if operation not in {"retention_preview", "reobserve"}:
                e.reject()
            expected = {"snapshot", "source_reference"} if operation == "retention_preview" else {"entry_id", "reference"}
            if set(request) != expected:
                e.reject()
            ref, ack = None, None
            if operation == "reobserve":
                ref = self.references.get(e.token(request["entry_id"], 32))
                supplied = request["reference"]
                if ref is None or type(supplied) is not dict or set(supplied) != set(asdict(ref)) or Reference(**supplied) != ref:
                    e.reject()
                if ref.acknowledgement_sha256 is None:
                    return result("acknowledgement_required")
                ack = self.acknowledgements.get(ref.acknowledgement_sha256)
                if (ack is None or (ack.record_id, ack.ciphertext_sha256, ack.plaintext_sha256, ack.store_context_sha256) !=
                        (ref.record_id, ref.ciphertext_sha256, ref.plaintext_sha256, self.binding())):
                    return result("acknowledgement_pin_required")
            with self.admission():
                deadline = time.monotonic() + BUDGET_SECONDS
                self.budget(deadline)
                binding, registry, before = self.binding(), self.registry(), self.inventory()
                if ref is None:
                    snapshot, source_reference = request["snapshot"], request["source_reference"]
                    retained, raw = None, None
                else:
                    retained, raw = self.record(ref)
                    if ack.plan_sha256 != retained["plan_sha256"]:
                        e.reject()
                    snapshot, source_reference = retained["plan"]["snapshot"], retained["plan"]["source_reference"]
                first = self.plan(scope, snapshot, source_reference, deadline)
                if first is None:
                    return result("verification_unavailable")
                if self.checkpoint is not None:
                    self.checkpoint("before_reobservation")  # Trusted disposable qualification hook only.
                p.authority.recheck(actor, now=p.clock())
                if p.actor(scope, "reviewer") != actor:
                    raise PermissionError
                current = self.plan(scope, snapshot, source_reference, deadline)
                if current is None:
                    return result("verification_unavailable")
                if (first != current or binding != self.binding() or registry != self.registry()
                        or before != self.inventory() or ref is not None and self.record(ref)[1] != raw):
                    raise FileExistsError
                p.authority.recheck(actor, now=p.clock())
                if p.actor(scope, "reviewer") != actor:
                    raise PermissionError
                self.budget(deadline)
                if ref is None:
                    return result("private_retention_plan_ready", retention_plan_ready=True,
                        retention_plan={"plan": current, "plan_sha256": e.sha(e.encode(current))})
                if retained["plan"] != current:
                    return result("retained_verification_needs_revalidation")
                return result("retained_verification_reobserved", host_acknowledgement_pin_matched=True,
                    reobservation={"reference_sha256": ref.sha256, "plan_sha256": retained["plan_sha256"],
                        "verification_sha256": current["verification"]["verification_sha256"],
                        "original_handoff_expires_at": current["verification"]["original_handoff_expires_at"],
                        "expires_at": current["verification"]["expires_at"]})
        except (PermissionError, HTTPException):
            return result("denied")
        except TimeoutError:
            return result("budget_exhausted")
        except FileExistsError:
            return result("observation_conflict")
        except (InvalidTag, ValueError, TypeError, KeyError, RecursionError, OSError, SQLAlchemyError, sqlite3.Error):
            return result("unverifiable")
