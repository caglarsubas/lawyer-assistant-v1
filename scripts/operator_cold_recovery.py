"""Read-only fixture reconstruction from independently retained host pins.

No descriptor discovery, provisioning, login, expiry extension or listener.
The caller supplies the original pins; a retained descriptor cannot approve itself.
"""

import os
import sqlite3
import stat
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import operator_checksum_handoff as h
import operator_enrollment_evidence as e
from operator_preview_binding import HostBinding
from operator_review_auth import SessionAuthority
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Store

SCHEMA = "disposable-cold-preview-controller-v1"
ROLES = ("source", "journal", "candidate", "readiness", "controls", "disposition")
KEYS = {name: ("journal" if name == "candidate" else name) + ".key" for name in ROLES}
FIELDS = {"schema", "fixture_scope", "stores", "source_pins", "source_binding", "candidate_pins",
          "readiness_binding", "controls_binding", "disposition_binding", "manifest_sha256",
          "profile_id", "profile_sha256", "database_identity", "firm_id", "actors", "bindings",
          "origin", "handoff_sha256", "binding_sha256", "receipt_sha256", "provenance_sha256"}


def identity(path):
    info = path.lstat()
    return info.st_dev, info.st_ino


def inventory(root):
    """Bounded exact ciphertext inventory; no decrypt, copy, repair or adoption."""
    root = e.directory(root)
    entries = sorted(root.iterdir())
    if len(entries) > 64:
        e.reject()
    rows, total = [], 0
    for path in entries:
        raw = e.read(path)
        info = path.lstat()
        total += len(raw)
        if total > 1024 * 1024:
            e.reject()
        rows.append([path.name, e.sha(raw), info.st_dev, info.st_ino, info.st_uid,
                     stat.S_IMODE(info.st_mode), info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns])
    return rows


@dataclass(frozen=True, kw_only=True)
class ColdPins:
    descriptor_sha256: str = field(repr=False)
    package_manifest_sha256: str = field(repr=False)
    handoff_sha256: str = field(repr=False)
    binding_sha256: str = field(repr=False)
    profile_sha256: str = field(repr=False)
    profile_id: str = field(repr=False)
    preparer_id: str = field(repr=False)
    reviewer_id: str = field(repr=False)
    source_id: str = field(repr=False)
    database_identity: tuple = field(repr=False)
    case_identity: tuple = field(repr=False)
    anchors_identity: tuple = field(repr=False)
    origin: str = field(repr=False)

    def __post_init__(self):
        for name in ("descriptor_sha256", "package_manifest_sha256", "handoff_sha256", "binding_sha256", "profile_sha256"):
            e.token(getattr(self, name))
        for name in ("profile_id", "preparer_id", "reviewer_id", "source_id"):
            e.token(getattr(self, name), 32)
        for name in ("database_identity", "case_identity", "anchors_identity"):
            value = getattr(self, name)
            if not isinstance(value, tuple) or len(value) != 2 or any(type(n) is not int or n < 0 for n in value):
                e.reject()
        if self.preparer_id == self.reviewer_id or self.origin != "http://operator.invalid":
            e.reject()


@dataclass(frozen=True, kw_only=True)
class RecoveredController:
    binding: HostBinding = field(repr=False)
    store: Store = field(repr=False)
    original_handoff: object = field(repr=False)

    def close(self):
        self.store.engine.dispose()


def recover(case_root, anchors_root, pins, *, clock=e.utc):
    """Trusted fixture wiring only. Original sessions and five-minute expiry survive."""
    if type(pins) is not ColdPins or not callable(clock):
        e.reject()
    case, anchors = e.directory(case_root), e.directory(anchors_root)
    if (case == anchors or case in anchors.parents or anchors in case.parents
            or identity(case) != pins.case_identity or identity(anchors) != pins.anchors_identity):
        e.reject()
    raw = e.read(anchors / "controller.json")
    if e.sha(raw) != pins.descriptor_sha256:
        e.reject()
    value = e.decode(raw)
    if (not isinstance(value, dict) or set(value) != FIELDS or e.encode(value) != raw
            or value["schema"] != SCHEMA or value["fixture_scope"] != "invented_accounts_and_encrypted_metadata_only"
            or value["profile_id"] != pins.profile_id or value["profile_sha256"] != pins.profile_sha256
            or value["handoff_sha256"] != pins.handoff_sha256 or value["binding_sha256"] != pins.binding_sha256
            or tuple(value["database_identity"]) != pins.database_identity
            or value["actors"] != {"preparer": pins.preparer_id, "reviewer": pins.reviewer_id}
            or value["origin"] != pins.origin or value["firm_id"] != "invented-firm"
            or not isinstance(value["stores"], dict) or set(value["stores"]) != set(ROLES)):
        e.reject()
    from copy_recovery_disposition import DispositionPlanner
    from disposition_journal_reconciliation import DispositionReconciler
    from disposition_reconciliation_receipt import DispositionReceiptService
    from journal_backup_readiness import JournalBackupReadiness
    from journal_copy_reconciliation import CopyReconciler
    from journal_materialization import JournalMaterializer
    from planning_journal_reconciliation import JournalBinding, JournalReconciler
    from private_inventory_receipts import ReceiptStore
    from receipt_provisioning_readiness import Pins, fingerprint
    from receipt_recovery_planning import RecoveryPlanner

    stores, retained_keys = {}, {}
    for name in ROLES:
        row = value["stores"][name]
        if not isinstance(row, dict) or set(row) != {"path", "identity", "context_id", "scope_sha256", "key_fingerprint", "inventory"}:
            e.reject()
        relative = Path(row["path"])
        if relative.is_absolute() or len(relative.parts) != 1 or relative.name in {".", "..", "accounts"}:
            e.reject()
        root = e.directory(case / relative)
        if root.parent != case or list(identity(root)) != row["identity"] or inventory(root) != row["inventory"]:
            e.reject()
        key = e.read(anchors / KEYS[name])
        if fingerprint(key) != row["key_fingerprint"]:
            e.reject()
        retained_keys[KEYS[name]] = key
        stores[name] = ReceiptStore(root=root, context_id=row["context_id"], scope_sha256=row["scope_sha256"], key=key)
    profile = e.directory(case / "accounts")
    database = profile / "disposable-identities.sqlite"
    info = database.lstat()
    if (database != database.resolve() or identity(database) != pins.database_identity
            or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid() or info.st_nlink != 1
            or e.sha(e.read(profile / "disposable-profile.json")) != pins.profile_sha256):
        e.reject()
    # Never call Store.__init__: create_all and key/bootstrap generation are forbidden.
    store = object.__new__(Store)
    uri = "file:" + quote(str(database), safe="/") + "?mode=ro"
    store.engine = create_engine("sqlite:///" + str(database),
        creator=lambda: sqlite3.connect(uri, uri=True, check_same_thread=False), pool_pre_ping=True)
    store.session = sessionmaker(store.engine, expire_on_commit=False)
    try:
        authority = SessionAuthority(store, profile, firm_id=value["firm_id"], bindings=value["bindings"], origins=(pins.origin,))
        if authority.file_identity != pins.database_identity or authority.profile_id != pins.profile_id:
            e.reject()
        def decode_pins(row):
            return Pins(**{**row, "store_identity": tuple(row["store_identity"])})
        def binding(row):
            return JournalBinding(**{**row, "pins": decode_pins(row["pins"])})
        def planner(source, journal, old_pins):
            return RecoveryPlanner(stores[source], stores[journal], old_pins, authority,
                preparer_id=pins.preparer_id, reviewer_id=pins.reviewer_id, clock=clock)
        source_binding = binding(value["source_binding"])
        source = JournalReconciler(planner=planner("source", "journal", decode_pins(value["source_pins"])), binding=source_binding)
        reviews = JournalReconciler(planner=planner("journal", "readiness", source_binding.pins), binding=binding(value["readiness_binding"]))
        controls = JournalReconciler(planner=planner("journal", "controls", source_binding.pins), binding=binding(value["controls_binding"]))
        readiness = JournalBackupReadiness(source=source, candidate=stores["candidate"], candidate_pins=decode_pins(value["candidate_pins"]), reviews=reviews)
        materializer = JournalMaterializer(readiness=readiness, controls=controls, mode="backup", manifest_sha256=value["manifest_sha256"])
        disposition = DispositionPlanner(source=CopyReconciler(service=materializer), reviews=JournalReconciler(
            planner=planner("controls", "disposition", controls.binding.pins), binding=binding(value["disposition_binding"])))
        service = DispositionReceiptService(reconciler=DispositionReconciler(disposition=disposition))
        record = e.decode(e.read(anchors / "handoff.json"))
        receipt, provenance = e.read(anchors / "receipt.json"), e.read(anchors / "provenance.json")
        if e.sha(receipt) != value["receipt_sha256"] or e.sha(provenance) != value["provenance_sha256"]:
            e.reject()
        # Reconstitute the original preparation, never call prepare_handoff again.
        target = h.PreparedHandoff(source_id=pins.source_id, receipt_bytes=receipt, receipt_sha256=value["receipt_sha256"],
            provenance_bytes=provenance, provenance_sha256=value["provenance_sha256"], prepared_by=record["prepared_by"],
            assigned_reviewer=record["assigned_reviewer"], created_at=e.stamp(record["created_at"]),
            binding_sha256=pins.binding_sha256, profile_id=pins.profile_id)
        if target.record() != record or target.sha256 != pins.handoff_sha256:
            e.reject()
        selected = HostBinding(adapter=h.OperatorChecksumAdapter(service=service, sources={pins.source_id: target}),
            source_id=pins.source_id, handoff_sha256=pins.handoff_sha256, binding_sha256=pins.binding_sha256,
            profile_id=pins.profile_id, preparer_id=pins.preparer_id, reviewer_id=pins.reviewer_id, origin=pins.origin)
        selected.validate()
        for name, original in stores.items():
            if inventory(original.root) != value["stores"][name]["inventory"] or identity(original.root) != tuple(value["stores"][name]["identity"]):
                e.reject()
        if (e.read(anchors / "controller.json") != raw or identity(database) != pins.database_identity
                or any(e.read(anchors / name) != key for name, key in retained_keys.items())):
            e.reject()
        return RecoveredController(binding=selected, store=store, original_handoff=target)
    except BaseException:
        store.engine.dispose()
        raise
