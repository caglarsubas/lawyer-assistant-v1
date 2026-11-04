"""Unregistered, read-only inventory and separately pinned metadata handoff.

Only host-retained acknowledged references are read. No discovery, publication,
acknowledgement recovery, destination provisioning or recovery execution.
"""

import sqlite3
import time
from dataclasses import asdict, dataclass
from types import MappingProxyType

import operator_enrollment_evidence as e
from cryptography.exceptions import InvalidTag
from fastapi import HTTPException
from operator_recovery_inputs import REFS, RecoveryInputReview
from operator_recovery_inputs import result as base_result
from sqlalchemy.exc import SQLAlchemyError

SCHEMA = "recovery-review-inventory-v1"
MAX_ENTRIES = 4
BUDGET_SECONDS = 10


def result(state, **values):
    return base_result(state, **{"schema": SCHEMA, "inventory": None, "handoff": None,
        "ready_for_pinned_disposable_review_handoff": False,
        "destination_attestation_verified": False, **values})


@dataclass(frozen=True, kw_only=True)
class Reference:
    review_id: str
    review_ciphertext_sha256: str
    review_sha256: str
    selection_id: str
    decision_ciphertext_sha256: str | None

    def __post_init__(self):
        for name in ("review_id", "selection_id"):
            e.token(getattr(self, name), 32)
        for name in ("review_ciphertext_sha256", "review_sha256"):
            e.token(getattr(self, name))
        if self.decision_ciphertext_sha256 is not None:
            e.token(self.decision_ciphertext_sha256)

    @property
    def sha256(self):
        return e.sha(e.encode(asdict(self)))


@dataclass(frozen=True, kw_only=True)
class DestinationPin:
    destination_id: str
    entry_id: str
    destination_context_sha256: str
    reference_sha256: str
    review_context_sha256: str
    selection_sha256: str
    journal_pins_sha256: str
    expires_at: int

    def __post_init__(self):
        e.token(self.destination_id, 32)
        e.token(self.entry_id, 32)
        for name in ("destination_context_sha256", "reference_sha256", "review_context_sha256",
                     "selection_sha256", "journal_pins_sha256"):
            e.token(getattr(self, name))
        e.stamp(self.expires_at)
        if self.destination_context_sha256 in {self.review_context_sha256, self.journal_pins_sha256}:
            e.reject()

    @property
    def sha256(self):
        return e.sha(e.encode(asdict(self)))


class ReviewInventory:
    def __init__(self, reviews, references, destination_pins, *, checkpoint=None):
        if (type(reviews) is not RecoveryInputReview or not isinstance(references, dict)
                or not 1 <= len(references) <= MAX_ENTRIES or not isinstance(destination_pins, dict)
                or len(destination_pins) > MAX_ENTRIES):
            e.reject()
        for ident, ref in references.items():
            e.token(ident, 32)
            if type(ref) is not Reference:
                e.reject()
        for ident, pin in destination_pins.items():
            e.token(ident, 32)
            if type(pin) is not DestinationPin or pin.destination_id != ident:
                e.reject()
        self.reviews = reviews
        self.references = MappingProxyType(dict(references))
        self.destination_pins = MappingProxyType(dict(destination_pins))
        self.checkpoint = checkpoint

    def context(self):
        return e.sha(e.encode({"schema": SCHEMA, "review_context_sha256": self.reviews.context(),
            "references": {k: asdict(v) for k, v in self.references.items()},
            "destination_pins": {k: asdict(v) for k, v in self.destination_pins.items()}}))

    @staticmethod
    def budget(deadline):
        if time.monotonic() >= deadline:
            raise TimeoutError

    def collect(self, scope, actor, deadline):
        r, entries = self.reviews, []
        context = self.context()
        before = r.journal_inventory()
        for ident, ref in sorted(self.references.items()):
            self.budget(deadline)
            request = asdict(ref)
            review = r.read_review(request)
            decision = r.read_decision(request, review) if ref.decision_ciphertext_sha256 is not None else None
            try:
                r.current(scope, review, actor, decision)
                state = decision["decision"] if decision else "decision_reference_required"
            except (PermissionError, FileExistsError, ValueError, OSError, HTTPException):
                state = "review_retained_needs_revalidation"
            entries.append({"entry_id": ident, "reference": request, "reference_sha256": ref.sha256,
                "state": state, "decision_reference_present": decision is not None,
                "selection_sha256": review["selection_sha256"],
                "review": {k: review[k] for k in ("review_id", "selection_id", "input_sha256", "expires_at")},
                "decision": {k: decision[k] for k in ("decision", "reason_code", "reviewed_at")} if decision else None})
        self.budget(deadline)
        if before != r.journal_inventory() or context != self.context():
            raise FileExistsError
        return {"context_sha256": context, "actor": actor,
                "journal_sha256": e.sha(e.encode(before)), "entries": entries}

    def dispatch(self, scope, operation, **request):
        try:
            r, p = self.reviews, self.reviews.planner
            actor = p.actor(scope)  # Before registry, ciphertext or source inspection.
            if operation not in {"inventory", "handoff"}:
                e.reject()
            fields = {"entry_id", "reference", "destination_id", "expected_inventory_sha256"} if operation == "handoff" else set()
            if set(request) != fields:
                e.reject()
            with r.admission():
                deadline = time.monotonic() + BUDGET_SECONDS
                first = self.collect(scope, actor, deadline)
                if self.checkpoint is not None:
                    self.checkpoint("before_reobservation")  # Trusted fixture wiring only.
                p.authority.recheck(actor, now=p.clock())
                if p.actor(scope) != actor:
                    raise PermissionError
                current = self.collect(scope, actor, deadline)
                if first != current:
                    raise FileExistsError
                digest = e.sha(e.encode(current))
                p.authority.recheck(actor, now=p.clock())
                if p.actor(scope) != actor:
                    raise PermissionError
                self.budget(deadline)
                if operation == "inventory":
                    return result("acknowledged_review_inventory", inventory={"inventory_sha256": digest,
                        "entries": current["entries"], "acknowledged_references_only": True})
                if e.token(request["expected_inventory_sha256"]) != digest:
                    raise FileExistsError
                ident = e.token(request["entry_id"], 32)
                ref = self.references.get(ident)
                if (ref is None or not isinstance(request["reference"], dict)
                        or set(request["reference"]) != REFS | {"decision_ciphertext_sha256"}
                        or Reference(**request["reference"]) != ref):
                    e.reject()
                entry = next(row for row in current["entries"] if row["entry_id"] == ident)
                if entry["state"] != "accept" or not entry["decision_reference_present"]:
                    return result("independent_acceptance_required")
                dest_id = e.token(request["destination_id"], 32)
                pin = self.destination_pins.get(dest_id)
                if pin is None:
                    return result("destination_pin_required")
                if (pin.entry_id != ident or pin.reference_sha256 != ref.sha256
                        or pin.selection_sha256 != entry["selection_sha256"]
                        or pin.review_context_sha256 != r.context()
                        or pin.journal_pins_sha256 != e.sha(e.encode(asdict(r.journal_pins)))):
                    return result("destination_pin_mismatch")
                expires = min(pin.expires_at, entry["review"]["expires_at"], actor["expires_at"])
                if e.stamp(p.clock()) >= expires:
                    return result("handoff_expired")
                return result("ready_for_pinned_disposable_review_handoff",
                    ready_for_pinned_disposable_review_handoff=True,
                    handoff={"entry_id": ident, "reference_sha256": ref.sha256,
                        "inventory_sha256": digest, "destination_id": dest_id,
                        "destination_context_sha256": pin.destination_context_sha256,
                        "destination_pin_sha256": pin.sha256, "expires_at": expires})
        except (PermissionError, HTTPException):
            return result("denied")
        except TimeoutError:
            return result("budget_exhausted")
        except FileExistsError:
            return result("observation_conflict")
        except (ValueError, TypeError, KeyError, RecursionError, OSError, InvalidTag, SQLAlchemyError, sqlite3.Error):
            return result("unverifiable")
