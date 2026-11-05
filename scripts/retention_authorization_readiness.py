"""Read-only, disposable retention review and signed host-pin provenance checks."""

import fcntl
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from itertools import islice
from types import MappingProxyType

import operator_enrollment_evidence as e
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import HTTPException
from operator_cold_recovery import inventory
from operator_recovery_inputs import FLAGS
from sqlalchemy.exc import SQLAlchemyError
from verification_reference_readiness import VerificationReferences
from verification_reference_readiness import result as reference_result

SCHEMA = "retention-authorization-readiness-v1"
PURPOSE = "disposable_metadata_retention_only"
SCHEMAS = {"preparer": "retention-proposal-v1", "reviewer": "retention-decision-v1",
           "acknowledger": "retention-acknowledgement-provenance-v1"}
SUFFIXES = ("proposal", "decision", "provenance")
DECISIONS = {"accept": "exact_retention_metadata_checked", "changes_required": "fresh_retention_review_required",
             "reject": "retention_metadata_declined"}
BUDGET_SECONDS, MAX_FILES = 10, 12
COMMON = {"schema", "purpose", "proof_id", "profile_id", "store_context_sha256", "proof_context_sha256", "reference_sha256", *FLAGS}
FIELDS = {
    "preparer": COMMON | {"plan_sha256", "acknowledgement_pin_sha256", "provenance_sha256", "prepared_by", "assigned_reviewer", "created_at", "expires_at"},
    "reviewer": COMMON | {"proposal_sha256", "reviewed_by", "decision", "reason_code", "reviewed_at", "expires_at"},
    "acknowledger": COMMON | {"plan_sha256", "acknowledgement_pin_sha256", "issuer_context_sha256", "record_id",
        "ciphertext_sha256", "plaintext_sha256", "issued_at", "expires_at", "custody_status", "durability_status"},
}


def result(state, **values):
    return reference_result(state, **{"schema": SCHEMA, "retention_authorized": False,
        "durability_qualified": False, "independent_disposable_review_checked": False,
        "signed_provenance_matches_host_pins": False, "ready_for_disposable_retention_planning": False,
        "evidence": None, **values})


@dataclass(frozen=True, kw_only=True)
class KeyPin:
    key_id: str
    kind: str
    principal_id: str
    profile_id: str
    store_context_sha256: str
    issuer_context_sha256: str
    public_key: bytes = field(repr=False)
    not_before: int
    expires_at: int
    revoked: bool = False

    def __post_init__(self):
        for name in ("key_id", "principal_id", "profile_id"):
            e.token(getattr(self, name), 32)
        for name in ("store_context_sha256", "issuer_context_sha256"):
            e.token(getattr(self, name))
        if (self.kind not in SCHEMAS or type(self.public_key) is not bytes or len(self.public_key) != 32
                or type(self.revoked) is not bool or e.stamp(self.not_before) >= e.stamp(self.expires_at)):
            e.reject()

    def metadata(self):
        return {**asdict(self), "public_key": self.public_key.hex()}


@dataclass(frozen=True, kw_only=True)
class ProofSet:
    proof_id: str
    reference_entry_id: str
    reference_sha256: str
    proposal_sha256: str
    decision_sha256: str
    provenance_sha256: str

    def __post_init__(self):
        e.token(self.proof_id, 32)
        e.token(self.reference_entry_id, 32)
        for name in ("reference_sha256", "proposal_sha256", "decision_sha256", "provenance_sha256"):
            e.token(getattr(self, name))

    @property
    def sha256(self):
        return e.sha(e.encode(asdict(self)))


@dataclass(frozen=True, kw_only=True)
class ProofPins:
    root_identity: tuple
    profile_id: str
    store_context_sha256: str

    def __post_init__(self):
        if type(self.root_identity) is not tuple or len(self.root_identity) != 4 or any(type(v) is not int for v in self.root_identity):
            e.reject()
        e.token(self.profile_id, 32)
        e.token(self.store_context_sha256)


class RetentionAuthorization:
    def __init__(self, references, root, pins, keys, proof_sets, *, checkpoint=None):
        if (type(references) is not VerificationReferences or type(pins) is not ProofPins
                or type(keys) is not dict or set(keys) != set(SCHEMAS)
                or type(proof_sets) is not dict or len(proof_sets) > 4):
            e.reject()
        self.references, self.root, self.pins = references, e.directory(root), pins
        for kind, key in keys.items():
            if type(key) is not KeyPin or key.kind != kind:
                e.reject()
        if any(len({getattr(k, name) for k in keys.values()}) != 3 for name in ("key_id", "principal_id", "public_key")):
            e.reject()
        for ident, item in proof_sets.items():
            e.token(ident, 32)
            if type(item) is not ProofSet:
                e.reject()
        roots = [references.store.root]
        for service in (references.verifier.source.reviews, references.verifier.target):
            p = service.planner
            roots += [p.authority.root, p.source.root, p.journal.root]
            roots += [getattr(s, n) for s in service.selections.values() for n in ("case_root", "anchors_root", "stage_root")]
        if any(self.root == r or self.root in r.parents or r in self.root.parents for r in roots):
            e.reject()
        self.keys, self.proof_sets = MappingProxyType(dict(keys)), MappingProxyType(dict(proof_sets))
        self.lock, self.checkpoint = threading.RLock(), checkpoint
        self.binding()

    def binding(self):
        p = self.references.verifier.target.planner
        info = e.directory(self.root).lstat()
        if ((info.st_dev, info.st_ino, info.st_uid, info.st_mode) != self.pins.root_identity
                or self.pins.profile_id != p.authority.profile_id
                or self.pins.store_context_sha256 != self.references.binding()):
            e.reject()
        return e.sha(e.encode({"schema": SCHEMA, "pins": asdict(self.pins),
            "keys": {k: v.metadata() for k, v in self.keys.items()},
            "proof_sets": {k: asdict(v) for k, v in self.proof_sets.items()},
            "references": self.references.registry()}))

    def proof_context(self):
        return e.sha(e.encode({"schema": SCHEMA, "pins": asdict(self.pins)}))

    def observe(self):
        self.binding()
        if len(tuple(islice(self.root.iterdir(), MAX_FILES + 1))) > MAX_FILES:
            e.reject()
        rows = inventory(self.root)
        if len(rows) > MAX_FILES or any(not re.fullmatch(r"[0-9a-f]{32}\.(?:proposal|decision|provenance)\.json", r[0]) for r in rows):
            e.reject()
        return rows

    @contextmanager
    def admission(self):
        if not self.lock.acquire(timeout=2):
            raise TimeoutError
        fd = None
        deadline = time.monotonic() + 2
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

    def envelope(self, raw, kind, proof, now):
        value, key = e.decode(raw), self.keys[kind]
        if (type(value) is not dict or set(value) != {"schema", "key_id", "claims", "signature"}
                or value["schema"] != "retention-signed-envelope-v1" or value["key_id"] != key.key_id
                or key.revoked or not key.not_before <= now < key.expires_at
                or key.profile_id != self.pins.profile_id or key.store_context_sha256 != self.pins.store_context_sha256):
            e.reject()
        claims = value["claims"]
        if (type(claims) is not dict or set(claims) != FIELDS[kind] or claims["schema"] != SCHEMAS[kind]
                or claims["purpose"] != PURPOSE or claims["proof_id"] != proof.proof_id
                or claims["profile_id"] != self.pins.profile_id
                or claims["store_context_sha256"] != self.pins.store_context_sha256
                or claims["proof_context_sha256"] != self.proof_context()
                or claims["reference_sha256"] != proof.reference_sha256 or any(claims[k] is not False for k in FLAGS)):
            e.reject()
        signature = bytes.fromhex(e.token(value["signature"], 128))
        Ed25519PublicKey.from_public_bytes(key.public_key).verify(signature, SCHEMAS[kind].encode() + b"\0" + e.encode(claims))
        return claims

    def read(self, proof, now):
        raws = [e.read(self.root / (proof.proof_id + "." + suffix + ".json")) for suffix in SUFFIXES]
        if [e.sha(raw) for raw in raws] != [proof.proposal_sha256, proof.decision_sha256, proof.provenance_sha256]:
            e.reject()
        return [self.envelope(raw, kind, proof, now) for raw, kind in zip(raws, SCHEMAS, strict=True)], raws

    def validate(self, proof, values, actor, now):
        p = self.references.verifier.target.planner
        proposal, decision, provenance = values
        ref = self.references.references.get(proof.reference_entry_id)
        ack = self.references.acknowledgements.get(ref.acknowledgement_sha256) if ref else None
        if ref is None or ack is None or ref.sha256 != proof.reference_sha256:
            e.reject()
        if (proposal["prepared_by"]["user_id"] != p.preparer or self.keys["preparer"].principal_id != p.preparer
                or self.keys["reviewer"].principal_id != p.reviewer or decision["reviewed_by"] != actor
                or proposal["assigned_reviewer"] != p.authority.eligible(p.reviewer, "reviewer")
                or proposal["provenance_sha256"] != proof.provenance_sha256
                or decision["proposal_sha256"] != proof.proposal_sha256
                or DECISIONS.get(decision["decision"]) != decision["reason_code"]):
            e.reject()
        p.authority.recheck(proposal["prepared_by"], now=now)
        for kind, item, start in (("preparer", proposal, "created_at"), ("reviewer", decision, "reviewed_at"),
                                  ("acknowledger", provenance, "issued_at")):
            if (not self.keys[kind].not_before <= e.stamp(item[start]) <= now < e.stamp(item["expires_at"])
                    or item["expires_at"] > self.keys[kind].expires_at):
                e.reject()
        if (not provenance["issued_at"] <= proposal["created_at"] <= decision["reviewed_at"]
                or decision["expires_at"] > proposal["expires_at"]
                or provenance["custody_status"] != "unqualified" or provenance["durability_status"] != "unqualified"
                or any(k.issuer_context_sha256 != ack.issuer_context_sha256 for k in self.keys.values())
                or (provenance["record_id"], provenance["ciphertext_sha256"], provenance["plaintext_sha256"],
                    provenance["issuer_context_sha256"], provenance["plan_sha256"], provenance["acknowledgement_pin_sha256"]) !=
                   (ref.record_id, ref.ciphertext_sha256, ref.plaintext_sha256, ack.issuer_context_sha256,
                    proposal["plan_sha256"], ref.acknowledgement_sha256)
                or proposal["acknowledgement_pin_sha256"] != ref.acknowledgement_sha256
                or proposal["plan_sha256"] != ack.plan_sha256):
            e.reject()
        return ref

    def current(self, scope, proof, deadline):
        self.budget(deadline)
        value = self.references.dispatch(scope, "reobserve", entry_id=proof.reference_entry_id,
            reference=asdict(self.references.references[proof.reference_entry_id]))
        self.budget(deadline)
        if value["state"] == "budget_exhausted":
            raise TimeoutError
        if value["state"] != "retained_verification_reobserved":
            return None
        return value["reobservation"]

    def dispatch(self, scope, operation, **request):
        try:
            p = self.references.verifier.target.planner
            actor = p.actor(scope, "reviewer")  # Before registry lookup, file inspection or signature parsing.
            if operation != "inspect" or set(request) != {"entry_id", "proof_set_sha256"}:
                e.reject()
            proof = self.proof_sets.get(e.token(request["entry_id"], 32))
            if proof is None or proof.sha256 != e.token(request["proof_set_sha256"]):
                e.reject()
            with self.admission():
                deadline = time.monotonic() + BUDGET_SECONDS
                self.budget(deadline)
                binding, before, now = self.binding(), self.observe(), p.clock()
                values, raw = self.read(proof, now)
                self.validate(proof, values, actor, now)
                if values[1]["decision"] != "accept":
                    return result("independent_review_not_accepted")
                first = self.current(scope, proof, deadline)
                if first is None:
                    return result("verification_unavailable")
                if self.checkpoint is not None:
                    self.checkpoint("before_reobservation")  # Trusted qualification hook only.
                p.authority.recheck(actor, now=p.clock())
                if p.actor(scope, "reviewer") != actor:
                    raise PermissionError
                current = self.current(scope, proof, deadline)
                if current is None:
                    return result("verification_unavailable")
                final, final_raw = self.read(proof, p.clock())
                self.validate(proof, final, actor, p.clock())
                if binding != self.binding() or before != self.observe() or raw != final_raw or first != current:
                    raise FileExistsError
                if (current["reference_sha256"] != proof.reference_sha256 or current["plan_sha256"] != final[0]["plan_sha256"]
                        or any(v["expires_at"] > current["expires_at"] for v in final)):
                    e.reject()
                p.authority.recheck(actor, now=p.clock())
                self.budget(deadline)
                return result("ready_for_disposable_retention_planning", independent_disposable_review_checked=True,
                    signed_provenance_matches_host_pins=True, ready_for_disposable_retention_planning=True,
                    evidence={"proof_set_sha256": proof.sha256, "proposal_sha256": proof.proposal_sha256,
                        "decision_sha256": proof.decision_sha256, "provenance_sha256": proof.provenance_sha256,
                        "reference_sha256": proof.reference_sha256, "plan_sha256": current["plan_sha256"],
                        "original_handoff_expires_at": current["original_handoff_expires_at"],
                        "expires_at": min(current["expires_at"], *(v["expires_at"] for v in final))})
        except (PermissionError, HTTPException):
            return result("denied")
        except TimeoutError:
            return result("budget_exhausted")
        except FileExistsError:
            return result("observation_conflict")
        except (InvalidSignature, ValueError, TypeError, KeyError, RecursionError, OSError, sqlite3.Error, SQLAlchemyError):
            return result("unverifiable")
