"""Unregistered recipient receipts and independently reviewed, read-only planning."""

import fcntl
import os
import re
import sqlite3
import stat
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from itertools import islice
from types import MappingProxyType

import metadata_handoff_readiness as handoff
import operator_enrollment_evidence as e
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import HTTPException
from operator_recovery_inputs import FLAGS, RecoveryInputReview
from retention_authorization_readiness import KeyPin
from sqlalchemy.exc import SQLAlchemyError

SCHEMA = "recipient-observation-readiness-v1"
PURPOSE = "disposable_recipient_metadata_only"
RECEIPT_SCHEMA = "recipient-observation-receipt-v1"
SCHEMAS = {"preparer": "recipient-retention-proposal-v1", "reviewer": "recipient-retention-decision-v1"}
DECISIONS = {"accept": "exact_recipient_receipt_checked", "changes_required": "fresh_recipient_review_required",
             "reject": "recipient_retention_declined"}
ACCEPTANCE = {"package_sha256", "specification_sha256", "proof_set_sha256", "reference_sha256",
              "destination_context_sha256", "destination_observation_sha256", "expires_at"}
RECEIPT = {"schema", "purpose", "receipt_id", "receipt_specification_sha256", "context_sha256", "acceptance",
           "observed_at", "expires_at", *FLAGS}
COMMON = {"schema", "purpose", "receipt_id", "receipt_sha256", "context_sha256", *FLAGS}
FIELDS = {
    "preparer": COMMON | {"prepared_by", "assigned_reviewer", "created_at", "expires_at"},
    "reviewer": COMMON | {"proposal_sha256", "reviewed_by", "reviewed_at", "expires_at", "decision", "reason_code"},
}
MAX_FILES, MAX_BYTES, BUDGET_SECONDS = 12, 4096, 10


def result(state, **values):
    return handoff.result(state, **{"schema": SCHEMA, "recipient_observation_receipt_ready": False,
        "recipient_retention_plan_ready": False, "independent_recipient_review_checked": False,
        "recipient_receipt": None, "recipient_retention_plan": None, **values})


@dataclass(frozen=True, kw_only=True)
class ReceiptSpecification:
    receipt_id: str
    metadata_entry_id: str
    metadata_specification_sha256: str
    metadata_package_sha256: str
    created_at: int
    expires_at: int

    def __post_init__(self):
        for name in ("receipt_id", "metadata_entry_id"):
            e.token(getattr(self, name), 32)
        for name in ("metadata_specification_sha256", "metadata_package_sha256"):
            e.token(getattr(self, name))
        if e.stamp(self.created_at) >= e.stamp(self.expires_at):
            e.reject()

    @property
    def sha256(self):
        return e.sha(e.encode(asdict(self)))


@dataclass(frozen=True, kw_only=True)
class ReviewSet:
    receipt_id: str
    receipt_sha256: str
    proposal_sha256: str
    decision_sha256: str

    def __post_init__(self):
        e.token(self.receipt_id, 32)
        for name in ("receipt_sha256", "proposal_sha256", "decision_sha256"):
            e.token(getattr(self, name))

    @property
    def sha256(self):
        return e.sha(e.encode(asdict(self)))


@dataclass(frozen=True, kw_only=True)
class ReceiptPins:
    root_identity: tuple
    handoff_binding_sha256: str
    review_context_sha256: str

    def __post_init__(self):
        if type(self.root_identity) is not tuple or len(self.root_identity) != 4 or any(type(n) is not int for n in self.root_identity):
            e.reject()
        e.token(self.handoff_binding_sha256)
        e.token(self.review_context_sha256)


def context(source, review, pins):
    return e.sha(e.encode({"schema": SCHEMA, "pins": asdict(pins), "handoff": source.binding(),
        "review": review.context(), "preparer": review.planner.authority.eligible(review.planner.preparer, "preparer"),
        "reviewer": review.planner.authority.eligible(review.planner.reviewer, "reviewer")}))


class RecipientObservation:
    def __init__(self, source, review, root, pins, keys, specifications, reviews, *, recipient_scope, checkpoint=None):
        if (type(source) is not handoff.MetadataHandoff or type(review) is not RecoveryInputReview
                or type(pins) is not ReceiptPins or type(keys) is not dict or set(keys) != set(SCHEMAS)
                or type(specifications) is not dict or len(specifications) > 4
                or type(reviews) is not dict or not set(reviews) <= set(specifications)
                or type(recipient_scope) is not dict):
            e.reject()
        for kind, key in keys.items():
            if type(key) is not KeyPin or key.kind != kind:
                e.reject()
        if any(len({getattr(k, n) for k in keys.values()}) != 2 for n in ("key_id", "principal_id", "public_key")):
            e.reject()
        for ident, spec in specifications.items():
            if type(spec) is not ReceiptSpecification or ident != spec.receipt_id:
                e.reject()
            original = source.specifications.get(spec.metadata_entry_id)
            if (original is None or original.sha256 != spec.metadata_specification_sha256
                    or source.packages.get(original.handoff_id) != spec.metadata_package_sha256
                    or not original.created_at <= spec.created_at < spec.expires_at <= original.expires_at):
                e.reject()
        for ident, value in reviews.items():
            if type(value) is not ReviewSet or value.receipt_id != ident:
                e.reject()
        self.source, self.review, self.root, self.pins = source, review, e.directory(root), pins
        self.keys, self.specifications, self.reviews = (MappingProxyType(dict(x)) for x in (keys, specifications, reviews))
        self._recipient_scope = deepcopy(recipient_scope)
        self.lock, self.checkpoint = threading.RLock(), checkpoint
        ancestors = (source.source.references.verifier.source.reviews, source.source.references.verifier.target, source.target)
        p = review.planner
        for service in ancestors:
            a = service.planner
            if (a.authority.profile_id == p.authority.profile_id or a.authority.file_identity == p.authority.file_identity
                    or {a.preparer, a.reviewer} & {p.preparer, p.reviewer}):
                e.reject()
        roots = [source.root, source.source.root, source.source.references.store.root]
        for service in (*ancestors, review):
            a = service.planner
            roots += [a.authority.root, a.source.root, a.journal.root]
            roots += [getattr(s, n) for s in service.selections.values()
                      for n in ("case_root", "anchors_root", "stage_root", "host_root")]
        if any(self.root == r or self.root in r.parents or r in self.root.parents for r in roots):
            e.reject()
        self.binding()

    def context(self):
        return context(self.source, self.review, self.pins)

    def binding(self):
        info, p = e.directory(self.root).lstat(), self.review.planner
        ctx = self.context()
        if ((info.st_dev, info.st_ino, info.st_uid, info.st_mode) != self.pins.root_identity
                or self.source.binding() != self.pins.handoff_binding_sha256
                or self.review.context() != self.pins.review_context_sha256):
            e.reject()
        for kind, key in self.keys.items():
            if (key.profile_id != p.authority.profile_id or key.store_context_sha256 != ctx
                    or key.issuer_context_sha256 != self.pins.handoff_binding_sha256
                    or key.principal_id != (p.preparer if kind == "preparer" else p.reviewer)):
                e.reject()
        return e.sha(e.encode({"context": ctx, "keys": {k: v.metadata() for k, v in self.keys.items()},
            "specifications": {k: asdict(v) for k, v in self.specifications.items()},
            "reviews": {k: asdict(v) for k, v in self.reviews.items()}}))

    def observe(self):
        self.binding()
        paths = tuple(islice(self.root.iterdir(), MAX_FILES + 1))
        if len(paths) > MAX_FILES or any(not re.fullmatch(r"[0-9a-f]{32}\.(?:receipt|proposal|decision)\.json", p.name)
                or p.name[:32] not in self.specifications or p.lstat().st_size > MAX_BYTES for p in paths):
            e.reject()
        rows = []
        for path in sorted(paths):
            raw, info = e.read(path), path.lstat()
            if len(raw) > MAX_BYTES:
                e.reject()
            rows.append([path.name, e.sha(raw), info.st_dev, info.st_ino, info.st_uid,
                         stat.S_IMODE(info.st_mode), info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns])
        return rows

    @contextmanager
    def admission(self):
        deadline = time.monotonic() + 2
        if not self.lock.acquire(timeout=2):
            raise TimeoutError
        fd = None
        try:
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError from None
                    time.sleep(.01)
            self.binding()
            self.budget(deadline)
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

    def current(self, spec, deadline):
        self.budget(deadline)
        value = self.source.dispatch(deepcopy(self._recipient_scope), "accept", entry_id=spec.metadata_entry_id,
            specification_sha256=spec.metadata_specification_sha256, package_sha256=spec.metadata_package_sha256)
        self.budget(deadline)
        if value["state"] == "budget_exhausted":
            raise TimeoutError
        if value["state"] != "read_only_destination_acceptance":
            return None
        accepted = value["acceptance"]
        if (type(accepted) is not dict or set(accepted) != ACCEPTANCE
                or accepted["package_sha256"] != spec.metadata_package_sha256
                or accepted["specification_sha256"] != spec.metadata_specification_sha256):
            e.reject()
        for name in ACCEPTANCE - {"expires_at"}:
            e.token(accepted[name])
        e.stamp(accepted["expires_at"])
        return accepted

    def receipt(self, spec, acceptance, now):
        return {"schema": RECEIPT_SCHEMA, "purpose": PURPOSE, "receipt_id": spec.receipt_id,
            "receipt_specification_sha256": spec.sha256, "context_sha256": self.context(), "acceptance": acceptance,
            "observed_at": now, "expires_at": min(spec.expires_at, acceptance["expires_at"]), **dict.fromkeys(FLAGS, False)}

    def envelope(self, raw, kind, spec, proof, now):
        value, key = e.decode(raw), self.keys[kind]
        if (type(value) is not dict or set(value) != {"schema", "key_id", "claims", "signature"}
                or value["schema"] != "recipient-retention-signed-envelope-v1" or value["key_id"] != key.key_id
                or e.encode(value) != raw or key.revoked or not key.not_before <= now < key.expires_at):
            e.reject()
        claims = value["claims"]
        if (type(claims) is not dict or set(claims) != FIELDS[kind] or claims["schema"] != SCHEMAS[kind]
                or claims["purpose"] != PURPOSE or claims["receipt_id"] != spec.receipt_id
                or claims["receipt_sha256"] != proof.receipt_sha256 or claims["context_sha256"] != self.context()
                or any(claims[k] is not False for k in FLAGS)):
            e.reject()
        Ed25519PublicKey.from_public_bytes(key.public_key).verify(bytes.fromhex(e.token(value["signature"], 128)),
                                                               SCHEMAS[kind].encode() + b"\0" + e.encode(claims))
        return claims

    def read(self, spec, proof, actor, now):
        raws = [e.read(self.root / (spec.receipt_id + "." + suffix + ".json"))
                for suffix in ("receipt", "proposal", "decision")]
        if (any(len(raw) > MAX_BYTES for raw in raws)
                or [e.sha(raw) for raw in raws] != [proof.receipt_sha256, proof.proposal_sha256, proof.decision_sha256]):
            e.reject()
        value = e.decode(raws[0])
        if (type(value) is not dict or set(value) != RECEIPT or value["schema"] != RECEIPT_SCHEMA
                or value["purpose"] != PURPOSE or value["receipt_id"] != spec.receipt_id
                or value["receipt_specification_sha256"] != spec.sha256 or value["context_sha256"] != self.context()
                or e.encode(value) != raws[0] or any(value[k] is not False for k in FLAGS)
                or type(value["acceptance"]) is not dict or set(value["acceptance"]) != ACCEPTANCE):
            e.reject()
        for name in ACCEPTANCE - {"expires_at"}:
            e.token(value["acceptance"][name])
        if (not spec.created_at <= e.stamp(value["observed_at"]) <= now < e.stamp(value["expires_at"])
                or value["expires_at"] != min(spec.expires_at, e.stamp(value["acceptance"]["expires_at"]))):
            e.reject()
        proposal, decision = [self.envelope(raw, kind, spec, proof, now)
                              for raw, kind in zip(raws[1:], SCHEMAS, strict=True)]
        p = self.review.planner
        if (proposal["prepared_by"]["user_id"] != p.preparer
                or proposal["assigned_reviewer"] != p.authority.eligible(p.reviewer, "reviewer")
                or decision["reviewed_by"] != actor or decision["proposal_sha256"] != proof.proposal_sha256
                or DECISIONS.get(decision["decision"]) != decision["reason_code"]):
            e.reject()
        p.authority.recheck(proposal["prepared_by"], now=now)
        for kind, claims, start in (("preparer", proposal, "created_at"), ("reviewer", decision, "reviewed_at")):
            if (not self.keys[kind].not_before <= e.stamp(claims[start]) <= now < e.stamp(claims["expires_at"])
                    or claims["expires_at"] > min(self.keys[kind].expires_at, value["expires_at"])):
                e.reject()
        if (not value["observed_at"] <= proposal["created_at"] <= decision["reviewed_at"]
                or decision["expires_at"] > proposal["expires_at"]):
            e.reject()
        return value, proposal, decision, raws

    def dispatch(self, scope, operation, **request):
        try:
            planner = self.source.target.planner if operation == "observe" else self.review.planner
            actor = planner.actor(scope, "reviewer")  # Before registry lookup, file reads or parsing.
            expected = {"entry_id", "specification_sha256"} | ({"review_set_sha256"} if operation == "plan" else set())
            if operation not in {"observe", "plan"} or set(request) != expected:
                e.reject()
            spec = self.specifications.get(e.token(request["entry_id"], 32))
            if spec is None or spec.sha256 != e.token(request["specification_sha256"]):
                e.reject()
            proof = self.reviews.get(spec.receipt_id) if operation == "plan" else None
            if operation == "plan" and (proof is None or proof.sha256 != e.token(request["review_set_sha256"])):
                e.reject()
            with self.admission():
                deadline, now = time.monotonic() + BUDGET_SECONDS, planner.clock()
                self.budget(deadline)
                binding, before, transport = self.binding(), self.observe(), self.source.observe()
                if not spec.created_at <= now < spec.expires_at:
                    e.reject()
                retained = self.read(spec, proof, actor, now) if proof else None
                if retained and retained[2]["decision"] != "accept":
                    return result("review_" + retained[2]["decision"])
                if self.checkpoint:
                    self.checkpoint("before_reobservation")
                if binding != self.binding() or before != self.observe() or transport != self.source.observe():
                    raise FileExistsError
                if retained and retained != self.read(spec, proof, actor, planner.clock()):
                    raise FileExistsError
                current = self.current(spec, deadline)
                if current is None:
                    return result("source_unavailable")
                # One complete parent acceptance already re-observes the signed
                # source and recipient twice. Do not multiply that nested work.
                if retained and retained[0]["acceptance"] != current:
                    return result("observation_conflict")
                value = retained[0] if retained else self.receipt(spec, current, now)
                raw = e.encode(value)
                if len(raw) > MAX_BYTES or now >= value["expires_at"]:
                    e.reject()
                if binding != self.binding() or before != self.observe() or transport != self.source.observe():
                    raise FileExistsError
                if retained and retained != self.read(spec, proof, actor, planner.clock()):
                    raise FileExistsError
                planner.authority.recheck(actor, now=planner.clock())
                if planner.actor(scope, "reviewer") != actor:
                    raise PermissionError
                expires = min(value["expires_at"], current["expires_at"], actor["expires_at"],
                              retained[1]["expires_at"] if retained else value["expires_at"],
                              retained[2]["expires_at"] if retained else value["expires_at"])
                if planner.clock() >= expires:
                    e.reject()
                self.budget(deadline)
                if operation == "observe":
                    return result("recipient_observation_receipt_ready", recipient_observation_receipt_ready=True,
                                  recipient_receipt={"sha256": e.sha(raw), "manifest": value})
                return result("ready_for_disposable_recipient_retention_planning", recipient_retention_plan_ready=True,
                    independent_recipient_review_checked=True,
                    recipient_retention_plan={"receipt_sha256": proof.receipt_sha256, "review_set_sha256": proof.sha256,
                        "proposal_sha256": proof.proposal_sha256, "decision_sha256": proof.decision_sha256,
                        "context_sha256": self.context(), "acceptance_sha256": e.sha(e.encode(current)),
                        "action": "disposable_metadata_retention_planning_only", "expires_at": expires})
        except (PermissionError, HTTPException):
            return result("denied")
        except TimeoutError:
            return result("budget_exhausted")
        except FileExistsError:
            return result("observation_conflict")
        except (ValueError, TypeError, KeyError, AttributeError, InvalidSignature, RecursionError, OSError, sqlite3.Error, SQLAlchemyError):
            return result("unverifiable")
