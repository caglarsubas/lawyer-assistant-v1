"""Invented disposition journal for isolated qualification, never provisioning."""

import os

import operator_enrollment_evidence as e
import private_inventory_receipts as receipts
from copy_recovery_disposition import DispositionPlanner
from journal_backup_fixture import reconciler
from journal_copy_reconciliation import CopyReconciler
from receipt_recovery_planning import RecoveryPlanner


def make(service, root):
    root.mkdir(mode=0o700)
    source = service.controls.planner.journal
    p = service.planner
    journal = receipts.ReceiptStore(root=root, context_id=source.context_id,
                                   scope_sha256=source.scope_sha256, key=os.urandom(32))
    planner = RecoveryPlanner(source, journal, service.controls.binding.pins, p.authority,
                             preparer_id=p.preparer, reviewer_id=p.reviewer, clock=p.clock)
    fixture = type("Bindings", (), {"ids": {"preparer": p.preparer, "reviewer": p.reviewer}, "authority": p.authority})()
    return DispositionPlanner(source=CopyReconciler(service=service), reviews=reconciler(fixture, planner))


def describe(disposition, key_path):
    from dataclasses import asdict

    return {"root": str(disposition.planner.journal.root), "key": str(key_path(disposition.planner.journal.key)),
            "binding": asdict(disposition.reviews.binding)}


def load(service, value, base):
    from pathlib import Path

    from planning_journal_reconciliation import JournalBinding, JournalReconciler
    from receipt_provisioning_readiness import Pins

    if not isinstance(value, dict) or set(value) != {"root", "key", "binding"}:
        e.reject()
    root, key = Path(value["root"]), Path(value["key"])
    if root != root.resolve() or not root.is_relative_to(base) or key != key.resolve() or not key.is_relative_to("/anchors"):
        e.reject()
    row = value["binding"]
    pins = Pins(**{**row["pins"], "store_identity": tuple(row["pins"]["store_identity"])})
    binding = JournalBinding(**{**row, "pins": pins})
    s, p = service.controls.planner.journal, service.planner
    journal = receipts.ReceiptStore(root=root, context_id=s.context_id, scope_sha256=s.scope_sha256, key=e.read(key))
    planner = RecoveryPlanner(s, journal, service.controls.binding.pins, p.authority,
                             preparer_id=p.preparer, reviewer_id=p.reviewer, clock=p.clock)
    return DispositionPlanner(source=CopyReconciler(service=service), reviews=JournalReconciler(planner=planner, binding=binding))
