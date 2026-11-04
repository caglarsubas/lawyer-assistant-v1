"""Fresh, rights-free identities and a separate encrypted review sidecar only."""

import os
from dataclasses import dataclass
from pathlib import Path

import build_operator_preview
import native_operator_preview as native
import native_preview_restart as previous
from cold_controller_fixture import retain
from journal_backup_fixture import pins as journal_pins
from operator_cold_recovery import inventory
from operator_recovery_inputs import RecoveryInputReview, Selection
from private_inventory_receipts import ReceiptStore
from receipt_recovery_planning import RecoveryPlanner

ROOT = Path(__file__).resolve().parents[1]
SELECTION, ALTERNATE = "a" * 32, "b" * 32


@dataclass
class Fixture:
    account: object
    selected: Selection
    stores: tuple
    sidecar: ReceiptStore
    journal_pins: object

    def service(self, checkpoint=None):
        p = self.account.planner
        planner = RecoveryPlanner(p.source, self.sidecar, p.pins, self.account.authority,
            preparer_id=p.preparer, reviewer_id=p.reviewer, clock=lambda: self.account.now)
        return RecoveryInputReview(planner, self.journal_pins,
            {SELECTION: self.selected, ALTERNATE: self.selected}, checkpoint=checkpoint)

    def protected(self):
        return [inventory(root) for root in self.stores], inventory(self.selected.anchors_root)


def make(root):
    root = Path(root)
    root.mkdir(mode=0o700)
    old = native.WORK
    try:
        native.WORK = root
        account, binding, target, stores = previous.fixture()
    finally:
        native.WORK = old
    exported = build_operator_preview.build(root / "public-preview")
    anchors = root / "anchors"
    original_pins = retain(account, binding, target, stores, anchors, exported["manifest_sha256"])
    selected = Selection(case_root=account.root, anchors_root=anchors, stage_root=root / "public-preview",
                         host_root=ROOT, pins=original_pins, require_readonly=False)
    sidecar_root = root / "input-reviews"
    sidecar_root.mkdir(mode=0o700)
    sidecar = ReceiptStore(root=sidecar_root, context_id=account.source_store.context_id,
                          scope_sha256=account.source_store.scope_sha256, key=os.urandom(32))
    return Fixture(account, selected, stores, sidecar, journal_pins(account, sidecar))
