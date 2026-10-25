"""Encrypted disposable review-history snapshots; independent controls stay external."""

import json
import os
import sqlite3
import stat
from pathlib import Path

import operator_enrollment_evidence as e
from cryptography.fernet import Fernet
from operator_review_journal import ReviewJournal, reject

SCHEMA = "review-history-backup-v1"
MAX_PLAIN, MAX_CIPHER, MAX_BACKUPS = 4 * 1024**2, 8 * 1024**2, 64


def read_blob(path):
    path = Path(path)
    e.directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o600 or not 0 < before.st_size <= MAX_CIPHER):
            reject()
        raw = stream.read(MAX_CIPHER + 1)
        def identity(v):
            return (v.st_dev, v.st_ino, v.st_mode, v.st_uid, v.st_nlink, v.st_size, v.st_mtime_ns, v.st_ctime_ns)
        if len(raw) != before.st_size or identity(before) != identity(os.fstat(stream.fileno())) or identity(before) != identity(path.lstat()):
            reject()
        return raw


def write_blob(path, raw):
    if not 0 < len(raw) <= MAX_CIPHER:
        reject()
    e.directory(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def decode_snapshot(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                reject()
            result[key] = value
        return result
    if not 0 < len(raw) <= MAX_PLAIN:
        reject()
    value = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: reject())
    if not isinstance(value, dict) or e.encode(value) != raw or set(value) != {"schema", "journal_id", "scope", "head", "records", "audit"} or value["schema"] != SCHEMA:
        reject()
    return value


class HistoryVault:
    def __init__(self, journal, bundles, manifests, restores, key_path, *, checkpoint=None):
        if not isinstance(journal, ReviewJournal):
            reject()
        self.journal = journal
        self.bundles, self.manifests, self.restores = [e.directory(p) for p in (bundles, manifests, restores)]
        self.key_path = Path(key_path)
        self.key_digest = e.sha(e.read(self.key_path))
        Fernet(e.read(self.key_path))
        roots = {journal.path.parent.resolve(), journal.ledger.resolve(), journal.anchor.path.parent.resolve(),
                 self.bundles, self.manifests, self.restores, e.directory(self.key_path.parent)}
        if len(roots) != 7:
            reject()
        self.checkpoint = checkpoint

    def cipher(self):
        raw = e.read(self.key_path)
        if e.sha(raw) != self.key_digest:
            reject()
        return Fernet(raw)

    def point(self, name):
        if self.checkpoint:
            self.checkpoint(name)

    def backup(self, ident, expected_head, recheck):
        e.token(ident, 32)
        with self.journal.locked() as (db, _, _, rows, tip, _):
            if e.token(expected_head) != tip["head"] or len(list(self.bundles.iterdir())) >= MAX_BACKUPS or len(list(self.manifests.iterdir())) >= MAX_BACKUPS:
                reject()
            payload = e.encode({"schema": SCHEMA, "journal_id": self.journal.identity, "scope": self.journal.scope,
                                "head": tip, "records": rows, "audit": db.execute("SELECT seq,frame FROM audit ORDER BY seq").fetchall()})
            if len(payload) > MAX_PLAIN:
                reject()
            ciphertext = self.cipher().encrypt(payload)
            manifest = {"schema": SCHEMA, "backup_id": ident, "journal_id": self.journal.identity,
                        "scope_sha256": e.sha(e.encode(self.journal.scope)), "head_sha256": tip["head"],
                        "plaintext_sha256": e.sha(payload), "ciphertext_sha256": e.sha(ciphertext), **dict.fromkeys(e.FLAGS, False)}
            self.point("before_backup_commit")
            recheck()
            write_blob(self.bundles / (ident + ".bundle"), ciphertext)
            self.journal.api.sealed_volume.sync_dir(self.bundles)
            self.point("backup_blob_retained")
            recheck()
            receipt = e.retain(self.manifests / (ident + ".json"), e.encode(manifest))
            self.journal.api.sealed_volume.sync_dir(self.manifests)
            self.point("backup_retained")
            recheck()
            return {"status": "encrypted_history_backup_retained", "backup_id": ident,
                    "manifest_sha256": receipt["sha256"], **dict.fromkeys(e.FLAGS, False)}

    def load(self, ident, expected_manifest, fence):
        e.token(ident, 32)
        raw = e.read(self.manifests / (ident + ".json"))
        m = e.decode(raw)
        if (e.sha(raw) != e.token(expected_manifest) or set(m) != {"schema", "backup_id", "journal_id", "scope_sha256", "head_sha256", "plaintext_sha256", "ciphertext_sha256", *e.FLAGS}
                or m["schema"] != SCHEMA or m["backup_id"] != ident or m["journal_id"] != self.journal.identity
                or m["scope_sha256"] != e.sha(e.encode(self.journal.scope)) or m["head_sha256"] != fence["head"]
                or any(m[k] is not False for k in e.FLAGS)):
            reject()
        encrypted = read_blob(self.bundles / (ident + ".bundle"))
        if e.sha(encrypted) != m["ciphertext_sha256"]:
            reject()
        raw = self.cipher().decrypt(encrypted)
        if e.sha(raw) != m["plaintext_sha256"]:
            reject()
        value = decode_snapshot(raw)
        if value["journal_id"] != self.journal.identity or value["scope"] != self.journal.scope or value["head"] != fence:
            reject()
        if not isinstance(value["records"], list) or not isinstance(value["audit"], list) or len(value["records"]) > 128 or len(value["audit"]) > 129:
            reject()
        return m, value

    def restored(self, ident):
        root = e.directory(self.restores / e.token(ident, 32))
        return ReviewJournal(root / "control/history.sqlite", self.journal.anchor.path, root / "ledger",
                             self.journal.scope, self.journal.identity, self.journal.api)

    def restore(self, ident, backup_id, expected_manifest, expected_head, recheck):
        e.token(ident, 32)
        # Restores serialize with all writer instances through the same external
        # anchor. They never restore/copy/rewind the anchor or its commit intents.
        with self.journal.anchor.locked(write=True) as (_, fence):
            if e.token(expected_head) != fence["head"] or len(list(self.restores.iterdir())) >= MAX_BACKUPS:
                reject()
            manifest, value = self.load(backup_id, expected_manifest, fence)
            root = self.restores / ident
            recheck()
            root.mkdir(mode=0o700)  # Exclusive new attempt. Existing attempts stay.
            for name in ("control", "ledger"):
                (root / name).mkdir(mode=0o700)
            intent = {"schema": "review-history-restore-v1", "request_id": ident, "backup_id": backup_id,
                      "manifest_sha256": expected_manifest, "head_sha256": fence["head"],
                      "scope_sha256": manifest["scope_sha256"], **dict.fromkeys(e.FLAGS, False)}
            intent_sha = e.retain(root / "intent.json", e.encode(intent))["sha256"]
            self.journal.api.sealed_volume.sync_dir(root)
            self.point("restore_intent_retained")
            target = self.restored(ident)
            self.journal.api.sealed_volume.write_new(target.path, b"")
            db = sqlite3.connect(target.path)
            try:
                db.executescript("PRAGMA synchronous=FULL; BEGIN IMMEDIATE; CREATE TABLE metadata(schema TEXT,id TEXT,scope TEXT);"
                                 "CREATE TABLE records(seq INTEGER PRIMARY KEY,name TEXT UNIQUE,raw TEXT,parent TEXT);"
                                 "CREATE TABLE audit(seq INTEGER PRIMARY KEY,frame TEXT);")
                from operator_review_journal import SCHEMA as JOURNAL_SCHEMA
                db.execute("INSERT INTO metadata VALUES(?,?,?)", (JOURNAL_SCHEMA, self.journal.identity, e.encode(self.journal.scope).decode()))
                db.executemany("INSERT INTO records VALUES(?,?,?,?)", value["records"])
                db.executemany("INSERT INTO audit VALUES(?,?)", value["audit"])
                rows, tip, missing = target.inspect(db, fence)
                if tip != fence:
                    reject()
                self.point("before_restore_commit")
                recheck()
                db.commit()
            finally:
                db.close()
            self.journal.api.sealed_volume.sync_dir(target.path.parent)
            for _, name, raw, _ in rows:
                recheck()
                e.retain(target.ledger / name, raw.encode())
            self.journal.api.sealed_volume.sync_dir(target.ledger)
            with sqlite3.connect(target.path) as db:
                _, tip, missing = target.inspect(db, fence)
                if missing or tip != fence:
                    reject()
            self.point("before_restore_receipt")
            recheck()
            receipt = {**intent, "intent_sha256": intent_sha, "snapshot_sha256": manifest["plaintext_sha256"], "records": len(rows)}
            receipt_sha = e.retain(root / "receipt.json", e.encode(receipt))["sha256"]
            self.journal.api.sealed_volume.sync_dir(root)
            self.point("restore_receipt_retained")
            recheck()
            return {"status": "exact_history_restored_to_new_stage", "request_id": ident,
                    "intent_sha256": intent_sha, "receipt_sha256": receipt_sha, **dict.fromkeys(e.FLAGS, False)}

    def status(self, ident, intent_pin, receipt_pin, recheck):
        with self.journal.anchor.locked() as (_, fence):
            root = e.directory(self.restores / e.token(ident, 32))
            raw = e.read(root / "intent.json")
            intent = e.decode(raw)
            receipt_raw = e.read(root / "receipt.json") if (root / "receipt.json").exists() else None
            observed = {"intent_sha256": e.sha(raw), "receipt_sha256": e.sha(receipt_raw) if receipt_raw else None}
            recheck()
            if intent_pin is None and receipt_pin is None:
                return {"status": "restore_observed_needs_pin", **observed, **dict.fromkeys(e.FLAGS, False)}
            if intent_pin != observed["intent_sha256"] or receipt_pin != observed["receipt_sha256"]:
                reject()
            if (intent["request_id"] != ident or intent["scope_sha256"] != e.sha(e.encode(self.journal.scope))
                    or intent["head_sha256"] != fence["head"] or any(intent[k] is not False for k in e.FLAGS)):
                reject()
            status = "restore_attempt_incomplete"
            if receipt_raw:
                receipt = e.decode(receipt_raw)
                if any(receipt[k] != value for k, value in intent.items()) or receipt["intent_sha256"] != observed["intent_sha256"]:
                    reject()
                target = self.restored(ident)
                self.journal.api.sealed_volume.control_file(target.path)
                with sqlite3.connect(target.path.resolve().as_uri() + "?mode=ro", uri=True) as db:
                    rows, tip, missing = target.inspect(db, fence)
                if tip != fence or missing or len(rows) != receipt["records"]:
                    reject()
                status = "restored_exact_history_retained"
            recheck()
            return {"status": status, **observed, **dict.fromkeys(e.FLAGS, False)}
