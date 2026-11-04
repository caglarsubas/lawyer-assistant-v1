"""Explicit fixture-input selection and independent encrypted metadata review.

Unregistered trusted wiring only. No listener, recovery executor, appointment,
key generation, pin adoption or authority renewal is provided.
"""

import fcntl
import os
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import MappingProxyType

import operator_enrollment_evidence as e
import private_inventory_receipts as receipts
from cryptography.exceptions import InvalidTag
from fastapi import HTTPException
from operator_cold_recovery import ColdPins, inventory, recover
from operator_preview_manifest import inspect_host, inspect_package
from receipt_provisioning_readiness import Pins, fingerprint
from receipt_recovery_planning import RecoveryPlanner

FLAGS = {"automatic_recovery", "authority_renewed", "trust_enrolled", "production_activation",
         "legal_qualification", "key_custody_approved", "external_checksum_channel_verified"}
DECISIONS = {"accept": "exact_recovery_inputs_checked", "changes_required": "fresh_input_review_required",
             "reject": "recovery_inputs_declined"}
SCHEMA = "operator-recovery-input-review-v1"
REFS = {"review_id", "review_ciphertext_sha256", "review_sha256", "selection_id"}
REVIEW = {"schema", "review_id", "selection_id", "selection_sha256", "input_sha256", "inputs",
          "review_context_sha256", "prepared_by", "assigned_reviewer", "created_at", "expires_at", *FLAGS}
DECISION = {"schema", "review_id", "review_ciphertext_sha256", "review_sha256", "selection_id",
            "input_sha256", "review_context_sha256", "reviewed_by", "reviewed_at", "decision", "reason_code", *FLAGS}


def result(state, **values):
    return {"schema": "operator-recovery-input-readiness-v1", "state": state, "metadata_only": True,
            "source_read_only": True, "atomic_snapshot": False, "joint_rollback_qualified": False,
            "ready_for_disposable_input_handoff": False,
            "review": None, "decision": None, **dict.fromkeys(FLAGS, False), **values}


@dataclass(frozen=True, kw_only=True)
class Selection:
    case_root: Path = field(repr=False)
    anchors_root: Path = field(repr=False)
    stage_root: Path = field(repr=False)
    host_root: Path = field(repr=False)
    pins: ColdPins = field(repr=False)
    require_readonly: bool = True

    def __post_init__(self):
        if type(self.pins) is not ColdPins or type(self.require_readonly) is not bool:
            e.reject()
        for name in ("case_root", "anchors_root", "stage_root", "host_root"):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute() or value != value.resolve():
                e.reject()

    @property
    def sha256(self):
        return e.sha(e.encode({"pins": asdict(self.pins), "paths": [str(getattr(self, name)) for name in
            ("case_root", "anchors_root", "stage_root", "host_root")], "require_readonly": self.require_readonly}))


class RecoveryInputReview:
    def __init__(self, planner, journal_pins, selections, *, checkpoint=None):
        if (type(planner) is not RecoveryPlanner or type(journal_pins) is not Pins
                or not isinstance(selections, dict) or not 1 <= len(selections) <= 16):
            e.reject()
        for ident, selected in selections.items():
            e.token(ident, 32)
            if type(selected) is not Selection:
                e.reject()
            pins = selected.pins
            if ((pins.preparer_id, pins.reviewer_id) != (planner.preparer, planner.reviewer)
                    or (pins.profile_id, pins.profile_sha256, pins.database_identity) !=
                    (planner.authority.profile_id, planner.authority.marker_sha, planner.authority.file_identity)
                    or any(planner.journal.root == root or planner.journal.root in root.parents or root in planner.journal.root.parents
                           for root in (selected.case_root, selected.anchors_root, selected.stage_root, selected.host_root))):
                e.reject()
        self.planner, self.journal_pins = planner, journal_pins
        self.selections = MappingProxyType(dict(selections))
        self.lock, self.checkpoint = threading.RLock(), checkpoint
        self.context()

    def context(self):
        p, pin = self.planner, self.journal_pins
        p.validate()
        receipts._root(p.journal)
        if (p.journal.identity != pin.store_identity or fingerprint(p.journal.key) != pin.key_fingerprint
                or (p.journal.context_id, p.journal.scope_sha256) != (pin.context_id, pin.scope_sha256)
                or (pin.profile_id, pin.profile_sha256) != (p.authority.profile_id, p.authority.marker_sha)):
            e.reject()
        return e.sha(e.encode({"schema": SCHEMA, "journal": asdict(pin),
            "preparer_id": p.preparer, "reviewer_id": p.reviewer}))

    def journal_inventory(self):
        self.context()
        rows = inventory(self.planner.journal.root)
        if any(not re.fullmatch(r"[0-9a-f]{32}\.receipt", row[0]) for row in rows):
            e.reject()
        return rows

    def point(self, name):
        if self.checkpoint is not None:
            self.checkpoint(name)  # Trusted qualification hook, never a request option.

    @contextmanager
    def admission(self):
        deadline = time.monotonic() + 2
        if not self.lock.acquire(timeout=2):
            raise TimeoutError
        fd = None
        try:
            fd = receipts._directory(self.planner.journal)
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError from None
                    time.sleep(.01)
            self.context()
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

    def capture(self, scope, selection_id, actor):
        self.context()
        selected = self.selections.get(e.token(selection_id, 32))
        if selected is None:
            e.reject()
        loaded = recover(selected.case_root, selected.anchors_root, selected.pins, clock=self.planner.clock)
        try:
            current = loaded.binding.adapter.service.reconciler.disposition.planner.actor(scope)
            if current != actor:
                raise PermissionError
            manifest, assets = inspect_package(selected.stage_root, selected.pins.package_manifest_sha256,
                                               require_readonly=selected.require_readonly)
            inspect_host(selected.host_root, manifest, require_readonly=selected.require_readonly)
            target = loaded.original_handoff
            protected = loaded.binding.adapter.service.reconciler.disposition.source.service
            keys = [protected.planner.source.key, protected.planner.journal.key,
                    protected.readiness.reviews.planner.journal.key, protected.controls.planner.journal.key,
                    loaded.binding.adapter.service.reconciler.disposition.planner.journal.key]
            if self.planner.journal.key in keys:
                e.reject()
            snapshot = {"schema": "operator-recovery-input-snapshot-v1", "selection_id": selection_id,
                "selection_sha256": selected.sha256, "descriptor_sha256": selected.pins.descriptor_sha256,
                "package_manifest_sha256": selected.pins.package_manifest_sha256, "source_id": target.source_id,
                "handoff_sha256": target.sha256, "binding_sha256": target.binding_sha256,
                "receipt_sha256": target.receipt_sha256, "provenance_sha256": target.provenance_sha256,
                "profile_id": target.profile_id, "prepared_at": target.created_at,
                "expires_at": target.created_at + 300, "kernel_readonly_public_inputs": selected.require_readonly}
            last, last_assets = inspect_package(selected.stage_root, selected.pins.package_manifest_sha256,
                                                require_readonly=selected.require_readonly)
            inspect_host(selected.host_root, last, require_readonly=selected.require_readonly)
            loaded.binding.validate()
            if last != manifest or last_assets != assets or loaded.binding.adapter.service.reconciler.disposition.planner.actor(scope) != actor:
                raise FileExistsError
            self.planner.authority.recheck(actor, now=self.planner.clock())
            return snapshot
        finally:
            loaded.close()

    @staticmethod
    def decision_id(ident, cipher):
        return e.sha(e.encode([SCHEMA, "decision", ident, cipher]))[:32]

    def read_review(self, request):
        p = self.planner
        value = p.read(SCHEMA, e.token(request["review_id"], 32), e.token(request["review_ciphertext_sha256"]))
        if (not isinstance(value, dict) or set(value) != REVIEW or value["schema"] != SCHEMA
                or value["review_id"] != request["review_id"] or value["selection_id"] != request["selection_id"]
                or any(value[k] is not False for k in FLAGS) or e.sha(e.encode(value)) != e.token(request["review_sha256"])
                or value["input_sha256"] != e.sha(e.encode(value["inputs"]))
                or value["selection_sha256"] != value["inputs"]["selection_sha256"]
                or value["review_context_sha256"] != self.context()
                or value["prepared_by"]["user_id"] != p.preparer or value["assigned_reviewer"]["user_id"] != p.reviewer
                or value["inputs"]["selection_id"] != value["selection_id"]
                or not value["inputs"]["prepared_at"] <= e.stamp(value["created_at"]) < e.stamp(value["expires_at"])
                    <= min(value["inputs"]["expires_at"], value["prepared_by"]["expires_at"], value["created_at"] + 300)):
            e.reject()
        return value

    def read_decision(self, request, review):
        value = self.planner.read(SCHEMA + "-decision", self.decision_id(request["review_id"], request["review_ciphertext_sha256"]),
                                  e.token(request["decision_ciphertext_sha256"]))
        if (not isinstance(value, dict) or set(value) != DECISION or value["schema"] != SCHEMA + "-decision"
                or any(value[k] is not False for k in FLAGS) or any(value[k] != request[k] for k in REFS)
                or value["input_sha256"] != review["input_sha256"] or value["review_context_sha256"] != self.context()
                or value["reviewed_by"]["user_id"] != self.planner.reviewer
                or {k: value["reviewed_by"][k] for k in review["assigned_reviewer"]} != review["assigned_reviewer"]
                or not review["created_at"] <= e.stamp(value["reviewed_at"]) < review["expires_at"]
                or DECISIONS.get(value["decision"]) != value["reason_code"]):
            e.reject()
        return value

    def current(self, scope, review, actor, decision=None):
        p, now = self.planner, e.stamp(self.planner.clock())
        if not review["created_at"] <= now < review["expires_at"]:
            raise FileExistsError
        p.authority.recheck(review["prepared_by"], now=now)
        if p.authority.eligible(p.reviewer, "reviewer") != review["assigned_reviewer"]:
            raise PermissionError
        if decision is not None:
            p.authority.recheck(decision["reviewed_by"], now=now)
        observed = self.capture(scope, review["selection_id"], actor)
        if observed != review["inputs"] or e.sha(e.encode(observed)) != review["input_sha256"]:
            raise FileExistsError
        p.authority.recheck(actor, now=p.clock())

    def dispatch(self, scope, operation, **request):
        try:
            if operation not in {"observe", "prepare", "decide", "inspect", "readiness"}:
                e.reject()
            p = self.planner
            actor = p.actor(scope, {"prepare": "preparer", "decide": "reviewer"}.get(operation))
            # Admission precedes input selection, key reads and journal inspection.
            with self.admission():
                rows = self.journal_inventory()
                if operation in {"prepare", "decide"} and len(rows) >= (63 if operation == "prepare" else 64):
                    raise FileExistsError
                if operation in {"observe", "prepare"}:
                    fields = {"selection_id"} | ({"review_id", "expected_input_sha256"} if operation == "prepare" else set())
                    if set(request) != fields:
                        e.reject()
                    snapshot = self.capture(scope, request["selection_id"], actor)
                    digest = e.sha(e.encode(snapshot))
                    if operation == "observe":
                        return result("inputs_observed", inputs=snapshot, input_sha256=digest)
                    if e.token(request["expected_input_sha256"]) != digest:
                        raise FileExistsError
                    now = e.stamp(p.clock())
                    record = {"schema": SCHEMA, "review_id": e.token(request["review_id"], 32),
                        "selection_id": request["selection_id"], "selection_sha256": snapshot["selection_sha256"],
                        "input_sha256": digest, "inputs": snapshot, "review_context_sha256": self.context(),
                        "prepared_by": actor, "assigned_reviewer": p.authority.eligible(p.reviewer, "reviewer"),
                        "created_at": now, "expires_at": min(snapshot["expires_at"], actor["expires_at"], now + 300),
                        **dict.fromkeys(FLAGS, False)}
                    self.current(scope, record, actor)
                    self.point("before_prepare_publish")
                    self.current(scope, record, actor)
                    cipher = p.write(SCHEMA, record["review_id"], record)
                    self.point("after_prepare_publish")
                    self.current(scope, record, actor)
                    return result("pending_independent_review", review_id=record["review_id"],
                        review_ciphertext_sha256=cipher, review_sha256=e.sha(e.encode(record)),
                        selection_id=record["selection_id"], input_sha256=digest, expires_at=record["expires_at"])
                fields = REFS | ({"decision", "reason_code", "expected_input_sha256"} if operation == "decide" else {"decision_ciphertext_sha256"})
                if set(request) != fields:
                    e.reject()
                review = self.read_review(request)
                if operation == "decide":
                    if DECISIONS.get(request["decision"]) != request["reason_code"] or e.token(request["expected_input_sha256"]) != review["input_sha256"]:
                        e.reject()
                    self.current(scope, review, actor)
                    record = {"schema": SCHEMA + "-decision", **{k: request[k] for k in REFS},
                        "input_sha256": review["input_sha256"], "review_context_sha256": self.context(),
                        "reviewed_by": actor, "reviewed_at": e.stamp(p.clock()), "decision": request["decision"],
                        "reason_code": request["reason_code"], **dict.fromkeys(FLAGS, False)}
                    self.point("before_decision_publish")
                    self.current(scope, review, actor)
                    cipher = p.write(SCHEMA + "-decision", self.decision_id(request["review_id"], request["review_ciphertext_sha256"]), record)
                    self.point("after_decision_publish")
                    self.current(scope, review, actor, record)
                    return result("independent_review_recorded", decision=request["decision"], decision_ciphertext_sha256=cipher)
                if request["decision_ciphertext_sha256"] is None:
                    p.authority.recheck(actor, now=p.clock())
                    if p.actor(scope) != actor:
                        raise PermissionError
                    return result("decision_reference_required")
                decision = self.read_decision(request, review)
                try:
                    self.current(scope, review, actor, decision)
                    state = "reviewed_for_disposable_inputs" if decision["decision"] == "accept" else decision["decision"]
                except (PermissionError, FileExistsError, ValueError, OSError, HTTPException):
                    state = "review_retained_needs_revalidation"
                p.authority.recheck(actor, now=p.clock())
                if p.actor(scope) != actor:
                    raise PermissionError
                self.journal_inventory()
                self.point("before_read_release")
                if self.read_review(request) != review or self.read_decision(request, review) != decision:
                    raise FileExistsError
                if p.actor(scope) != actor:
                    raise PermissionError
                return result(state, ready_for_disposable_input_handoff=operation == "readiness" and state == "reviewed_for_disposable_inputs",
                    review={"review_id": review["review_id"], "selection_id": review["selection_id"],
                            "input_sha256": review["input_sha256"], "expires_at": review["expires_at"]},
                    decision={"decision": decision["decision"], "reason_code": decision["reason_code"], "reviewed_at": decision["reviewed_at"]})
        except (PermissionError, HTTPException):
            return result("denied")
        except receipts.RetentionUncertain:
            return result("retention_uncertain")
        except TimeoutError:
            return result("budget_exhausted")
        except FileExistsError:
            return result("input_or_review_conflict")
        except (ValueError, TypeError, KeyError, RecursionError, OSError, InvalidTag):
            return result("unverifiable")
