"""Unregistered, metadata-only packaging and read-only recipient observation."""

import fcntl
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from itertools import islice
from types import MappingProxyType

import operator_enrollment_evidence as e
from destination_snapshot_verification import destination_context
from fastapi import HTTPException
from operator_cold_recovery import inventory
from operator_recovery_inputs import FLAGS, RecoveryInputReview
from retention_authorization_readiness import RetentionAuthorization
from retention_authorization_readiness import result as retention_result
from sqlalchemy.exc import SQLAlchemyError

SCHEMA = "reviewed-metadata-handoff-v1"
PURPOSE = "disposable_metadata_observation_only"
MAX_FILES, MAX_BYTES, BUDGET_SECONDS = 4, 4096, 10
HASHES = {"proof_set_sha256", "proposal_sha256", "decision_sha256", "provenance_sha256",
          "reference_sha256", "plan_sha256"}
EVIDENCE = HASHES | {"original_handoff_expires_at", "expires_at"}
FIELDS = {"schema", "purpose", "specification", "specification_sha256", "evidence", "expires_at", *FLAGS}


def result(state, **values):
    return retention_result(state, **{"schema": SCHEMA, "handoff": None, "acceptance": None,
        "metadata_package_ready": False, "read_only_destination_acceptance": False, **values})


@dataclass(frozen=True, kw_only=True)
class Specification:
    handoff_id: str
    proof_entry_id: str
    proof_set_sha256: str
    source_context_sha256: str
    destination_id: str
    destination_context_sha256: str
    created_at: int
    expires_at: int

    def __post_init__(self):
        for name in ("handoff_id", "proof_entry_id", "destination_id"):
            e.token(getattr(self, name), 32)
        for name in ("proof_set_sha256", "source_context_sha256", "destination_context_sha256"):
            e.token(getattr(self, name))
        if e.stamp(self.created_at) >= e.stamp(self.expires_at):
            e.reject()

    @property
    def sha256(self):
        return e.sha(e.encode(asdict(self)))


@dataclass(frozen=True, kw_only=True)
class TransportPins:
    root_identity: tuple
    destination_context_sha256: str

    def __post_init__(self):
        if type(self.root_identity) is not tuple or len(self.root_identity) != 4 or any(type(x) is not int for x in self.root_identity):
            e.reject()
        e.token(self.destination_context_sha256)


def recipient_context(target, destination_id, selection_id):
    if type(target) is not RecoveryInputReview:
        e.reject()
    p = target.planner
    return e.sha(e.encode({"schema": SCHEMA, "target": destination_context(target, destination_id, selection_id),
        "preparer": p.authority.eligible(p.preparer, "preparer"),
        "reviewer": p.authority.eligible(p.reviewer, "reviewer")}))


class MetadataHandoff:
    def __init__(self, source, target, root, pins, specifications, packages, *, source_scope,
                 destination_id, selection_id, checkpoint=None):
        if (type(source) is not RetentionAuthorization or type(target) is not RecoveryInputReview
                or type(pins) is not TransportPins or type(specifications) is not dict
                or type(packages) is not dict or len(specifications) > 4 or not set(packages) <= set(specifications)):
            e.reject()
        for ident, spec in specifications.items():
            e.token(ident, 32)
            if type(spec) is not Specification or spec.handoff_id != ident:
                e.reject()
        for digest in packages.values():
            e.token(digest)
        self.source, self.target, self.root, self.pins = source, target, e.directory(root), pins
        self.specifications, self.packages = MappingProxyType(dict(specifications)), MappingProxyType(dict(packages))
        self.destination_id, self.selection_id = e.token(destination_id, 32), e.token(selection_id, 32)
        self._source_scope = deepcopy(source_scope)  # Host-held; never a request field, package or result.
        self.lock, self.checkpoint = threading.RLock(), checkpoint
        a, b = source.references.verifier.target.planner, target.planner
        if (a.authority.profile_id == b.authority.profile_id or a.authority.file_identity == b.authority.file_identity
                or {a.preparer, a.reviewer} & {b.preparer, b.reviewer}):
            e.reject()
        roots = [source.root, source.references.store.root]
        for service in (source.references.verifier.source.reviews, source.references.verifier.target, target):
            p = service.planner
            roots += [p.authority.root, p.source.root, p.journal.root]
            roots += [getattr(s, n) for s in service.selections.values()
                      for n in ("case_root", "anchors_root", "stage_root", "host_root")]
        if any(self.root == r or self.root in r.parents or r in self.root.parents for r in roots):
            e.reject()
        self.binding()

    def binding(self):
        info = e.directory(self.root).lstat()
        context = recipient_context(self.target, self.destination_id, self.selection_id)
        if ((info.st_dev, info.st_ino, info.st_uid, info.st_mode) != self.pins.root_identity
                or context != self.pins.destination_context_sha256):
            e.reject()
        return e.sha(e.encode({"schema": SCHEMA, "pins": asdict(self.pins), "source": self.source.binding(),
            "specifications": {k: asdict(v) for k, v in self.specifications.items()}, "packages": dict(self.packages)}))

    def observe(self):
        self.binding()
        entries = tuple(islice(self.root.iterdir(), MAX_FILES + 1))
        if len(entries) > MAX_FILES or any(not re.fullmatch(r"[0-9a-f]{32}\.metadata\.json", p.name)
                or p.name[:32] not in self.specifications for p in entries):
            e.reject()
        for p in entries:
            if p.lstat().st_size > MAX_BYTES:
                e.reject()
        return inventory(self.root)

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
            if time.monotonic() >= deadline:
                raise TimeoutError
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

    def current(self, scope, spec, deadline):
        self.budget(deadline)
        value = self.source.dispatch(deepcopy(scope), "inspect", entry_id=spec.proof_entry_id,
                                     proof_set_sha256=spec.proof_set_sha256)
        self.budget(deadline)
        if value["state"] == "budget_exhausted":
            raise TimeoutError
        if value["state"] != "ready_for_disposable_retention_planning":
            return None
        evidence = value["evidence"]
        if type(evidence) is not dict or set(evidence) != EVIDENCE or evidence["proof_set_sha256"] != spec.proof_set_sha256:
            e.reject()
        for name in HASHES:
            e.token(evidence[name])
        for name in EVIDENCE - HASHES:
            e.stamp(evidence[name])
        return evidence

    def manifest(self, spec, evidence):
        return {"schema": SCHEMA, "purpose": PURPOSE, "specification": asdict(spec),
            "specification_sha256": spec.sha256, "evidence": evidence,
            "expires_at": min(spec.expires_at, evidence["expires_at"], evidence["original_handoff_expires_at"]),
            **dict.fromkeys(FLAGS, False)}

    def destination_observation(self, scope, actor, deadline):
        self.budget(deadline)
        before = self.target.journal_inventory()
        inputs = self.target.capture(scope, self.selection_id, actor)
        if before != self.target.journal_inventory():
            raise FileExistsError
        self.budget(deadline)
        return {"sha256": e.sha(e.encode({"context": recipient_context(self.target, self.destination_id, self.selection_id),
                                         "inputs": inputs, "journal": before})), "expires_at": e.stamp(inputs["expires_at"])}

    def dispatch(self, scope, operation, **request):
        try:
            planner = self.source.references.verifier.target.planner if operation == "package" else self.target.planner
            actor = planner.actor(scope, "reviewer")  # Before lookup, file reads or manifest parsing.
            fields = {"entry_id", "specification_sha256"} | ({"package_sha256"} if operation == "accept" else set())
            if operation not in {"package", "accept"} or set(request) != fields:
                e.reject()
            spec = self.specifications.get(e.token(request["entry_id"], 32))
            if spec is None or spec.sha256 != e.token(request["specification_sha256"]):
                e.reject()
            if operation == "accept" and self.packages.get(spec.handoff_id) != e.token(request["package_sha256"]):
                e.reject()
            with self.admission():
                deadline = time.monotonic() + BUDGET_SECONDS
                self.budget(deadline)
                binding, before = self.binding(), self.observe()
                now = planner.clock()
                if (not spec.created_at <= now < spec.expires_at or spec.source_context_sha256 != self.source.binding()
                        or spec.destination_id != self.destination_id
                        or spec.destination_context_sha256 != self.pins.destination_context_sha256):
                    e.reject()
                raw, value = None, None
                if operation == "accept":
                    raw = e.read(self.root / (spec.handoff_id + ".metadata.json"))
                    value = e.decode(raw)
                    if (len(raw) > MAX_BYTES or e.sha(raw) != self.packages[spec.handoff_id] or type(value) is not dict
                            or set(value) != FIELDS or e.encode(value) != raw):
                        e.reject()
                    if (value["schema"] != SCHEMA or value["purpose"] != PURPOSE
                            or value["specification"] != asdict(spec) or value["specification_sha256"] != spec.sha256
                            or any(value[k] is not False for k in FLAGS)
                            or type(value["evidence"]) is not dict or set(value["evidence"]) != EVIDENCE):
                        e.reject()
                    for name in HASHES:
                        e.token(value["evidence"][name])
                    for name in EVIDENCE - HASHES:
                        e.stamp(value["evidence"][name])
                    if (value["evidence"]["proof_set_sha256"] != spec.proof_set_sha256
                            or e.stamp(value["expires_at"]) != min(spec.expires_at, value["evidence"]["expires_at"],
                                value["evidence"]["original_handoff_expires_at"])):
                        e.reject()
                source_scope = scope if operation == "package" else self._source_scope
                first = self.current(source_scope, spec, deadline)
                if first is None:
                    return result("source_unavailable")
                expected = self.manifest(spec, first)
                if len(e.encode(expected)) > MAX_BYTES or now >= expected["expires_at"]:
                    e.reject()
                if operation == "accept" and value != expected:
                    e.reject()
                observed = self.destination_observation(scope, actor, deadline) if operation == "accept" else None
                if self.checkpoint:
                    self.checkpoint("before_reobservation")  # Trusted test hook only.
                planner.authority.recheck(actor, now=planner.clock())
                if planner.actor(scope, "reviewer") != actor:
                    raise PermissionError
                if binding != self.binding() or before != self.observe():
                    raise FileExistsError
                if operation == "accept" and raw != e.read(self.root / (spec.handoff_id + ".metadata.json")):
                    raise FileExistsError
                current = self.current(source_scope, spec, deadline)
                if current is None:
                    return result("source_unavailable")
                if current != first or binding != self.binding() or before != self.observe():
                    raise FileExistsError
                if operation == "accept":
                    if raw != e.read(self.root / (spec.handoff_id + ".metadata.json")):
                        raise FileExistsError
                    if observed != self.destination_observation(scope, actor, deadline):
                        raise FileExistsError
                planner.authority.recheck(actor, now=planner.clock())
                expires = min(expected["expires_at"], actor["expires_at"],
                              observed["expires_at"] if observed is not None else expected["expires_at"])
                if planner.clock() >= expires:
                    e.reject()
                self.budget(deadline)
                digest = e.sha(e.encode(expected))
                if operation == "package":
                    return result("metadata_package_ready", metadata_package_ready=True,
                                  handoff={"package_sha256": digest, "manifest": expected})
                return result("read_only_destination_acceptance", read_only_destination_acceptance=True,
                    acceptance={"package_sha256": digest, "specification_sha256": spec.sha256,
                        "proof_set_sha256": spec.proof_set_sha256, "reference_sha256": first["reference_sha256"],
                        "destination_context_sha256": spec.destination_context_sha256,
                        "destination_observation_sha256": observed["sha256"], "expires_at": expires})
        except (PermissionError, HTTPException):
            return result("denied")
        except TimeoutError:
            return result("budget_exhausted")
        except FileExistsError:
            return result("observation_conflict")
        except (ValueError, TypeError, KeyError, RecursionError, OSError, sqlite3.Error, SQLAlchemyError):
            return result("unverifiable")
