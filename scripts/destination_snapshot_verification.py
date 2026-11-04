"""Unregistered destination-side verification of an explicit metadata handoff.

Trusted local wiring only. Digests are comparison commitments, never credentials
or authority to restore, publish, adopt acknowledgements or renew trust.
"""

import sqlite3
import time
from copy import deepcopy
from dataclasses import asdict, dataclass, fields

import operator_enrollment_evidence as e
from cryptography.exceptions import InvalidTag
from fastapi import HTTPException
from operator_recovery_inputs import REFS, RecoveryInputReview
from recovery_review_inventory import DestinationPin, Reference, ReviewInventory
from recovery_review_inventory import result as inventory_result
from sqlalchemy.exc import SQLAlchemyError

SCHEMA = "destination-snapshot-verification-v1"
BUDGET_SECONDS = 10


def result(state, **values):
    return inventory_result(state, **{"schema": SCHEMA, "snapshot_verified": False,
                                     "verification": None, **values})


@dataclass(frozen=True, kw_only=True)
class Snapshot:
    entry_id: str
    reference_sha256: str
    inventory_sha256: str
    destination_id: str
    destination_context_sha256: str
    destination_pin_sha256: str
    expires_at: int

    def __post_init__(self):
        for name in ("entry_id", "destination_id"):
            e.token(getattr(self, name), 32)
        for name in ("reference_sha256", "inventory_sha256", "destination_context_sha256", "destination_pin_sha256"):
            e.token(getattr(self, name))
        e.stamp(self.expires_at)

    @classmethod
    def parse(cls, value):
        if type(value) is not dict or set(value) != {f.name for f in fields(cls)}:
            e.reject()
        return cls(**value)

    @property
    def sha256(self):
        return e.sha(e.encode(asdict(self)))


def destination_context(target, destination_id, selection_id):
    """Host-side context to pin independently, never derived from a request."""
    if type(target) is not RecoveryInputReview:
        e.reject()
    selected = target.selections.get(e.token(selection_id, 32))
    if selected is None:
        e.reject()
    return e.sha(e.encode({"schema": SCHEMA, "destination_id": e.token(destination_id, 32),
        "review_context_sha256": target.context(), "selection_id": selection_id,
        "selection_sha256": selected.sha256, "journal_pins": asdict(target.journal_pins),
        "account_database_identity": target.planner.authority.file_identity}))


class DestinationVerifier:
    def __init__(self, source, target, *, source_scope, reference, pin, selection_id, checkpoint=None):
        if (type(source) is not ReviewInventory or type(target) is not RecoveryInputReview
                or type(reference) is not Reference or type(pin) is not DestinationPin
                or type(source_scope) is not dict):
            e.reject()
        a, b = source.reviews.planner, target.planner
        if (a.authority.file_identity == b.authority.file_identity
                or a.authority.store is b.authority.store
                or {a.source.key, a.journal.key} & {b.source.key, b.journal.key}):
            e.reject()
        # Separate private account/store namespaces; common public host code is allowed.
        for left in (a.authority.root, a.source.root, a.journal.root):
            for right in (b.authority.root, b.source.root, b.journal.root):
                if left == right or left in right.parents or right in left.parents:
                    e.reject()
        self.source, self.target = source, target
        self.reference, self.pin = reference, pin
        self.selection_id = e.token(selection_id, 32)
        self._source_scope = deepcopy(source_scope)  # Server-held credential, never a request field or output.
        self.checkpoint = checkpoint
        self.context()

    def context(self):
        if (self.source.references.get(self.pin.entry_id) != self.reference
                or self.source.destination_pins.get(self.pin.destination_id) != self.pin
                or self.pin.reference_sha256 != self.reference.sha256
                or destination_context(self.target, self.pin.destination_id, self.selection_id)
                    != self.pin.destination_context_sha256):
            e.reject()
        return self.pin.destination_context_sha256

    @staticmethod
    def budget(deadline):
        if time.monotonic() >= deadline:
            raise TimeoutError

    def observe_target(self, scope, actor, deadline):
        self.budget(deadline)
        context = self.context()
        before = self.target.journal_inventory()
        captured = self.target.capture(scope, self.selection_id, actor)
        if context != self.context() or before != self.target.journal_inventory():
            raise FileExistsError
        self.budget(deadline)
        return {"context_sha256": context, "inputs": captured,
                "journal_sha256": e.sha(e.encode(before))}

    def source_matches(self, snapshot, deadline):
        self.budget(deadline)
        value = self.source.dispatch(deepcopy(self._source_scope), "handoff",
            entry_id=self.pin.entry_id, reference=asdict(self.reference),
            destination_id=self.pin.destination_id, expected_inventory_sha256=snapshot.inventory_sha256)
        self.budget(deadline)
        if value["state"] == "budget_exhausted":
            raise TimeoutError
        return (value["state"] == "ready_for_pinned_disposable_review_handoff"
                and value["handoff"] == asdict(snapshot))

    def dispatch(self, scope, operation, **request):
        try:
            p = self.target.planner
            actor = p.actor(scope, "reviewer")  # Authenticate destination before source or packet inspection.
            if operation != "verify" or set(request) != {"snapshot", "reference"}:
                e.reject()
            snapshot = Snapshot.parse(request["snapshot"])
            ref = request["reference"]
            if (type(ref) is not dict or set(ref) != REFS | {"decision_ciphertext_sha256"}
                    or Reference(**ref) != self.reference):
                e.reject()
            if (snapshot.entry_id != self.pin.entry_id or snapshot.destination_id != self.pin.destination_id
                    or snapshot.reference_sha256 != self.reference.sha256
                    or snapshot.destination_pin_sha256 != self.pin.sha256
                    or snapshot.destination_context_sha256 != self.context()
                    or snapshot.expires_at > self.pin.expires_at):
                return result("snapshot_binding_mismatch")
            with self.target.admission():
                deadline = time.monotonic() + BUDGET_SECONDS
                first = self.observe_target(scope, actor, deadline)
                if not self.source_matches(snapshot, deadline):
                    return result("source_snapshot_unavailable")
                if self.checkpoint is not None:
                    self.checkpoint("before_reobservation")  # Trusted disposable fault injection only.
                p.authority.recheck(actor, now=p.clock())
                if p.actor(scope, "reviewer") != actor:
                    raise PermissionError
                current = self.observe_target(scope, actor, deadline)
                if current != first:
                    raise FileExistsError
                if not self.source_matches(snapshot, deadline):
                    return result("source_snapshot_unavailable")
                if self.observe_target(scope, actor, deadline) != first:
                    raise FileExistsError
                expires = min(snapshot.expires_at, actor["expires_at"], current["inputs"]["expires_at"])
                if (e.stamp(p.clock()) >= expires
                        or e.stamp(self.source.reviews.planner.clock()) >= snapshot.expires_at):
                    return result("snapshot_expired")
                p.authority.recheck(actor, now=p.clock())
                if (p.actor(scope, "reviewer") != actor or self.context() != first["context_sha256"]
                        or e.sha(e.encode(self.target.journal_inventory())) != first["journal_sha256"]):
                    raise FileExistsError
                self.budget(deadline)
                verified = {"schema": SCHEMA, "snapshot_sha256": snapshot.sha256,
                    "reference_sha256": self.reference.sha256, "destination_context_sha256": self.context(),
                    "destination_actor_sha256": e.sha(e.encode(actor)),
                    "destination_inputs_sha256": e.sha(e.encode(current)),
                    "original_handoff_expires_at": snapshot.expires_at, "expires_at": expires}
                return result("destination_snapshot_verified", snapshot_verified=True, verification={**verified, "verification_sha256": e.sha(e.encode(verified))})
        except (PermissionError, HTTPException):
            return result("denied")
        except TimeoutError:
            return result("budget_exhausted")
        except FileExistsError:
            return result("observation_conflict")
        except (ValueError, TypeError, KeyError, RecursionError, OSError, InvalidTag, SQLAlchemyError, sqlite3.Error):
            return result("unverifiable")
