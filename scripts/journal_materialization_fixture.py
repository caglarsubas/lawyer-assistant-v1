"""Invented copy contexts for qualification; no provisioning or production wiring."""

import os
from dataclasses import replace

import operator_enrollment_evidence as e
import private_inventory_receipts as receipts
from journal_backup_fixture import pins, reconciler
from journal_backup_readiness import JournalBackupReadiness
from journal_materialization import JournalMaterializer
from receipt_recovery_planning import RecoveryPlanner


def make(f, prefix="backup", *, source=None, candidate_root=None, origin=None, manifest_sha256=None):
    source = source or f.journal_store
    candidate_root = candidate_root or f.root / (prefix + "-target")
    candidate_root.mkdir(mode=0o700)
    ready_root, controls_root = (f.root / (prefix + suffix) for suffix in ("-readiness", "-controls"))
    ready_root.mkdir(mode=0o700)
    controls_root.mkdir(mode=0o700)
    def planner(journal, previous, previous_pins):
        return RecoveryPlanner(previous, journal, previous_pins, f.authority,
            preparer_id=f.ids["preparer"], reviewer_id=f.ids["reviewer"], clock=lambda: f.now)
    def store(root, key):
        return receipts.ReceiptStore(root=root, context_id=source.context_id, scope_sha256=source.scope_sha256, key=key)
    p = planner(source, f.source_store, f.pins)
    ready = JournalBackupReadiness(source=reconciler(f, p), candidate=store(candidate_root, source.key),
        candidate_pins=pins(f, store(candidate_root, source.key)), reviews=reconciler(f,
            planner(store(ready_root, os.urandom(32)), source, pins(f, source))))
    rows = sorted(({"record_id": path.stem, "ciphertext_sha256": e.sha(path.read_bytes()), "bytes": path.stat().st_size}
                   for path in source.root.iterdir()), key=lambda r: r["record_id"])
    return JournalMaterializer(readiness=ready, controls=reconciler(f,
        planner(store(controls_root, os.urandom(32)), source, pins(f, source))), mode="restore" if origin else "backup",
        manifest_sha256=manifest_sha256 or e.sha(e.encode(rows)), origin=origin)


def reopen(service):
    """Fresh objects with the same independently retained fixture bindings."""
    return replace(service)


def describe(service, key_path):
    from dataclasses import asdict

    p, r, c = service.planner, service.readiness.reviews.planner, service.controls.planner
    value = {"source_root": str(p.source.root), "journal_root": str(p.journal.root),
             "candidate_root": str(service.readiness.candidate.root), "readiness_root": str(r.journal.root),
             "controls_root": str(c.journal.root), "source_key": str(key_path(p.source.key)),
             "journal_key": str(key_path(p.journal.key)), "readiness_key": str(key_path(r.journal.key)),
             "controls_key": str(key_path(c.journal.key)), "source_pins": asdict(p.pins),
             "source_binding": asdict(service.readiness.source.binding), "candidate_pins": asdict(service.readiness.candidate_pins),
             "readiness_binding": asdict(service.readiness.reviews.binding), "controls_binding": asdict(service.controls.binding),
             "mode": service.mode, "manifest_sha256": service.manifest_sha256, "origin": None}
    if service.origin:
        value["origin"] = {"service": describe(service.origin.service, key_path), "refs": service.origin.refs()}
    return value


def load(value, authority, clock, depth=0):
    """Only closed protected qualification descriptors, never request payloads."""
    from pathlib import Path

    from journal_materialization import CopyOrigin
    from planning_journal_reconciliation import JournalBinding, JournalReconciler
    from receipt_provisioning_readiness import Pins

    fields = {"source_root", "journal_root", "candidate_root", "readiness_root", "controls_root", "source_key", "journal_key",
              "readiness_key", "controls_key", "source_pins", "source_binding", "candidate_pins", "readiness_binding",
              "controls_binding", "mode", "manifest_sha256", "origin"}
    if not isinstance(value, dict) or set(value) != fields or depth > 1:
        e.reject()
    for key in ("source_root", "journal_root", "candidate_root", "readiness_root", "controls_root"):
        path = Path(value[key])
        if path != path.resolve() or not (path.is_relative_to("/work") or path.is_relative_to("/backups")):
            e.reject()
    for key in ("source_key", "journal_key", "readiness_key", "controls_key"):
        path = Path(value[key])
        if path != path.resolve() or not path.is_relative_to("/anchors"):
            e.reject()
    def decode_pins(row):
        return Pins(**{**row, "store_identity": tuple(row["store_identity"])})
    def binding(row):
        return JournalBinding(**{**row, "pins": decode_pins(row["pins"])})
    sp, sb = decode_pins(value["source_pins"]), binding(value["source_binding"])
    def store(name, key):
        return receipts.ReceiptStore(root=Path(value[name]), context_id=sp.context_id, scope_sha256=sp.scope_sha256,
            key=e.read(Path(value[key])))
    def planner(source, journal, pins):
        return RecoveryPlanner(source, journal, pins, authority, preparer_id=sb.preparer_id, reviewer_id=sb.reviewer_id, clock=clock)
    original, journal = store("source_root", "source_key"), store("journal_root", "journal_key")
    candidate = store("candidate_root", "journal_key")
    readiness = JournalBackupReadiness(source=JournalReconciler(planner=planner(original, journal, sp), binding=sb),
        candidate=candidate, candidate_pins=decode_pins(value["candidate_pins"]), reviews=JournalReconciler(
            planner=planner(journal, store("readiness_root", "readiness_key"), sb.pins), binding=binding(value["readiness_binding"])))
    origin = None
    if value["origin"] is not None:
        if not isinstance(value["origin"], dict) or set(value["origin"]) != {"service", "refs"}:
            e.reject()
        origin = CopyOrigin(service=load(value["origin"]["service"], authority, clock, depth + 1), **value["origin"]["refs"])
    return JournalMaterializer(readiness=readiness, controls=JournalReconciler(
        planner=planner(journal, store("controls_root", "controls_key"), sb.pins), binding=binding(value["controls_binding"])),
        mode=value["mode"], manifest_sha256=value["manifest_sha256"], origin=origin)
