"""Unregistered model-control journal with an independently retained anchor.

No model, application data, trust provisioning or inference is installed here.
The anchor must live outside journal backups under the trusted controller. A
privileged rollback of both files is outside this boundary.
"""

import fcntl
import os
import secrets
import sqlite3
import stat
import time
from contextlib import contextmanager
from pathlib import Path

import artifact_store as a
import sealed_volume as v

SCHEMA = "sealed-control-journal-v2"
MAX_OPERATIONS, MAX_EVENTS, MAX_COMMITS, MAX_NONCES, MAX_DEPTH = 512, 8192, 8192, 8192, 32
ZERO = "0" * 64


def head(journal_id, seq, previous, state):
    return a.digest(a.canonical({"schema": SCHEMA, "journal_id": journal_id, "seq": seq,
                                 "previous": previous, "state": state}))


def anchor_frame(journal_id, entry):
    return {"journal_id": journal_id, "seq": entry[0], "previous": entry[1], "head": entry[3]}


class Anchor:
    def __init__(self, path):
        self.path = Path(path)
        v.owner_dir(self.path.parent)

    @contextmanager
    def locked(self, *, write=False):
        fd = os.open(self.path, (os.O_RDWR if write else os.O_RDONLY) | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        try:
            start = os.fstat(fd)
            if (not stat.S_ISREG(start.st_mode) or start.st_uid != os.getuid() or start.st_nlink != 1
                    or stat.S_IMODE(start.st_mode) != 0o600 or not 0 < start.st_size <= 8 * 1024**2):
                v.reject()
            until = time.monotonic() + 2
            while True:
                try:
                    fcntl.flock(fd, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= until:
                        v.reject()
                    time.sleep(0.01)
            if (self.path.lstat().st_dev, self.path.lstat().st_ino) != (start.st_dev, start.st_ino):
                v.reject()
            os.lseek(fd, 0, os.SEEK_SET)
            raw = b""
            while True:
                block = os.read(fd, 65536)
                if not block:
                    break
                raw += block
                if len(raw) > 8 * 1024**2:
                    v.reject()
            if not raw.endswith(b"\n"):
                v.reject()
            lines = raw.splitlines()
            if not 1 <= len(lines) <= MAX_COMMITS:
                v.reject()
            last, identity = None, None
            for seq, line in enumerate(lines):
                item = a.strict_json(line)
                if (not isinstance(item, dict) or set(item) != {"journal_id", "seq", "previous", "head"}
                        or type(item["seq"]) is not int or item["seq"] != seq or a.canonical(item) != line):
                    v.reject()
                v.token(item["journal_id"])
                v.digest(item["head"])
                if item["previous"] != (last["head"] if last else ZERO) or (identity is not None and item["journal_id"] != identity):
                    v.reject()
                identity, last = item["journal_id"], item
            yield fd, last
        finally:
            os.close(fd)

    def append(self, fd, previous, frame):
        if frame["seq"] != previous["seq"] + 1 or frame["previous"] != previous["head"] or frame["journal_id"] != previous["journal_id"]:
            v.reject()
        raw = a.canonical(frame) + b"\n"
        if frame["seq"] >= MAX_COMMITS or os.fstat(fd).st_size + len(raw) > 8 * 1024**2:
            v.reject()
        os.lseek(fd, 0, os.SEEK_END)
        while raw:
            size = os.write(fd, raw)
            if not size:
                v.reject()
            raw = raw[size:]
        os.fsync(fd)


def limited(db, query, maximum):
    rows = db.execute(query + " LIMIT " + str(maximum + 1)).fetchall()
    if len(rows) > maximum:
        v.reject()
    return rows


def state(db):
    """Validate bounded graph/history, then commit their exact logical content."""
    operations = limited(db, "SELECT id,generation,record,state,proof FROM operations ORDER BY id", MAX_OPERATIONS)
    events = limited(db, "SELECT seq,operation,event FROM events ORDER BY seq", MAX_EVENTS)
    nonces = limited(db, "SELECT nonce,generation,state,wire_sha FROM nonces ORDER BY nonce", MAX_NONCES)
    records, generations, histories = {}, set(), {}
    for operation, generation, raw, status, proof in operations:
        if not isinstance(raw, str) or (proof is not None and not isinstance(proof, str)):
            v.reject()
        record = v.validate_record(a.strict_json(raw.encode()))
        if (a.canonical(record).decode() != raw or operation != record["operation_id"] or generation != record["generation_id"]
                or generation in generations or status not in {"copying", "prepared", "sealed", "revoked"}):
            v.reject()
        records[operation] = record
        generations.add(generation)
        histories[operation] = []
        if proof is not None:
            parsed = a.strict_json(proof.encode())
            a.validate_proof(parsed, record["manifest_digest"], a.Budget(), strategy="windowed-pinned")
            if a.canonical(parsed).decode() != proof or parsed["content_identity_sha256"] != record["content_sha256"]:
                v.reject()
    for expected, (seq, operation, event) in enumerate(events, 1):
        if seq != expected or operation not in histories:
            v.reject()
        history = histories[operation]
        prior = history[-1] if history else None
        if event not in {None: {"copying"}, "copying": {"prepared", "revoked"}, "prepared": {"sealed", "revoked"}, "sealed": {"revoked"}}.get(prior, set()):
            v.reject()
        history.append(event)
    for operation, _, _, status, proof in operations:
        history = histories[operation]
        if not history or history[-1] != status or ((proof is not None) != ("sealed" in history)):
            v.reject()
        seen, current = set(), operation
        while current is not None:
            if current in seen or current not in records or len(seen) >= MAX_DEPTH:
                v.reject()
            seen.add(current)
            record = records[current]
            parent = record["parent_operation"]
            if parent is not None:
                if parent not in records or any(record[key] != records[parent][key] for key in ("bundle_index_sha256", "content_sha256", "manifest_digest")):
                    v.reject()
            current = parent
    ever_sealed = {records[n]["generation_id"] for n, h in histories.items() if "sealed" in h}
    for challenge, generation, status, wire_sha in nonces:
        v.token(challenge)
        v.digest(wire_sha)
        if generation not in ever_sealed or status not in {"reserved", "consumed"}:
            v.reject()
    return a.digest(a.canonical({"operations": operations, "events": events, "nonces": nonces}))


def inspect(db, journal_id):
    if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
        v.reject()
    if db.execute("SELECT schema,id FROM metadata").fetchall() != [(SCHEMA, journal_id)]:
        v.reject()
    if {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")} != {"metadata", "operations", "events", "nonces", "audit"}:
        v.reject()
    if db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('view','trigger')").fetchone():
        v.reject()
    entries = limited(db, "SELECT seq,previous,state,head FROM audit ORDER BY seq", MAX_COMMITS)
    if not entries:
        v.reject()
    previous = ZERO
    for seq, entry in enumerate(entries):
        if entry[0] != seq or entry[1] != previous or entry[3] != head(journal_id, seq, previous, entry[2]):
            v.reject()
        v.digest(entry[2])
        previous = entry[3]
    if state(db) != entries[-1][2]:
        v.reject()
    return entries


def eligible(db, operation, statuses):
    seen, current = set(), v.token(operation)
    while current is not None:
        if current in seen or len(seen) >= MAX_DEPTH:
            v.reject()
        seen.add(current)
        row = db.execute("SELECT record,state FROM operations WHERE id=?", (current,)).fetchone()
        if row is None or row[1] not in (statuses if current == operation else {"sealed"}):
            v.reject()
        current = v.validate_record(a.strict_json(row[0].encode()))["parent_operation"]
    return len(seen)


class Journal(v.Journal):
    @classmethod
    def create(cls, path, anchor_path):
        path, anchor_path = Path(path), Path(anchor_path)
        v.owner_dir(path.parent)
        v.owner_dir(anchor_path.parent)
        if path.parent.resolve() == anchor_path.parent.resolve() or path.exists() or anchor_path.exists():
            v.reject()
        journal_id = secrets.token_hex(16)
        v.write_new(path, b"")
        db = sqlite3.connect(path)
        try:
            db.executescript("PRAGMA synchronous=FULL; CREATE TABLE metadata(schema TEXT,id TEXT);"
                             "CREATE TABLE operations(id TEXT PRIMARY KEY,generation TEXT UNIQUE,record TEXT,state TEXT,proof TEXT);"
                             "CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT,operation TEXT,event TEXT);"
                             "CREATE TABLE nonces(nonce TEXT PRIMARY KEY,generation TEXT,state TEXT,wire_sha TEXT);"
                             "CREATE TABLE audit(seq INTEGER PRIMARY KEY,previous TEXT,state TEXT,head TEXT);")
            db.execute("INSERT INTO metadata VALUES(?,?)", (SCHEMA, journal_id))
            initial = (0, ZERO, state(db), "")
            initial = (*initial[:3], head(journal_id, *initial[:3]))
            db.execute("INSERT INTO audit VALUES(?,?,?,?)", initial)
            db.commit()
        finally:
            db.close()
        v.sync_dir(path.parent)
        v.write_new(anchor_path, a.canonical(anchor_frame(journal_id, initial)) + b"\n")
        v.sync_dir(anchor_path.parent)
        return cls(path, anchor_path, journal_id)

    def __init__(self, path, anchor_path, journal_id, *, checkpoint=None):
        self.path, self.anchor, self.journal_id = Path(path), Anchor(anchor_path), v.token(journal_id)
        self.checkpoint = checkpoint
        with self.connect(readonly=True):
            pass

    @contextmanager
    def connect(self, *, readonly=False):
        v.control_file(self.path)
        with self.anchor.locked(write=not readonly) as (fd, fence):
            if fence["journal_id"] != self.journal_id:
                v.reject()
            db = sqlite3.connect(self.path.resolve().as_uri() + ("?mode=ro" if readonly else "?mode=rw"), uri=True, timeout=2, isolation_level=None)
            try:
                db.execute("PRAGMA query_only=" + ("ON" if readonly else "OFF"))
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN" if readonly else "BEGIN IMMEDIATE")
                entries = inspect(db, self.journal_id)
                if anchor_frame(self.journal_id, entries[-1]) != fence:
                    v.reject()
                yield db
                if readonly:
                    db.rollback()
                    return
                after = state(db)
                if after == entries[-1][2]:
                    db.rollback()
                    return
                seq = len(entries)
                if seq >= MAX_COMMITS:
                    v.reject()
                entry = (seq, entries[-1][3], after, head(self.journal_id, seq, entries[-1][3], after))
                db.execute("INSERT INTO audit VALUES(?,?,?,?)", entry)
                if self.checkpoint:
                    self.checkpoint("before_commit")
                db.commit()
                if self.checkpoint:
                    self.checkpoint("committed_unanchored")
                self.anchor.append(fd, fence, anchor_frame(self.journal_id, entry))
                if self.checkpoint:
                    self.checkpoint("anchored")
            except sqlite3.Error:
                db.rollback()
                raise ValueError("Control journal rejected") from None
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    def begin(self, operation, index, index_sha, binding_sha, *, purpose, parent=None):
        v.token(operation)
        v.digest(binding_sha)
        v.parse_index(a.canonical(index), index_sha)
        record = v.validate_record({"operation_id": operation, "generation_id": secrets.token_hex(16),
                                    "bundle_index_sha256": index_sha, "content_sha256": index["content_sha256"],
                                    "manifest_digest": index["manifest"], "volume_binding_sha256": binding_sha,
                                    "purpose": purpose, "parent_operation": parent, "production_activation": False})
        with self.connect() as db:
            if db.execute("SELECT count(*) FROM operations").fetchone()[0] >= MAX_OPERATIONS:
                v.reject()
            if purpose == "restore":
                if eligible(db, parent, {"sealed"}) >= MAX_DEPTH:
                    v.reject()
                previous = a.strict_json(db.execute("SELECT record FROM operations WHERE id=?", (parent,)).fetchone()[0].encode())
                if any(previous[k] != record[k] for k in ("bundle_index_sha256", "content_sha256", "manifest_digest")):
                    v.reject()
            db.execute("INSERT INTO operations VALUES(?,?,?,'copying',NULL)", (operation, record["generation_id"], a.canonical(record).decode()))
            db.execute("INSERT INTO events(operation,event) VALUES(?,'copying')", (operation,))
        return record

    def _transition(self, operation, previous, status, proof=None):
        if status not in {"copying": {"prepared"}, "prepared": {"sealed"}}.get(previous, set()):
            v.reject()
        with self.connect() as db:
            eligible(db, operation, {previous})
            record = a.strict_json(db.execute("SELECT record FROM operations WHERE id=?", (operation,)).fetchone()[0].encode())
            if status == "sealed":
                a.validate_proof(proof, record["manifest_digest"], a.Budget(), strategy="windowed-pinned")
                if proof["content_identity_sha256"] != record["content_sha256"]:
                    v.reject()
            db.execute("UPDATE operations SET state=?,proof=? WHERE id=?", (status, a.canonical(proof).decode() if proof else None, operation))
            db.execute("INSERT INTO events(operation,event) VALUES(?,?)", (operation, status))

    def revoke(self, operation):
        with self.connect() as db:
            v.token(operation)
            rows = db.execute("SELECT id,record,state FROM operations ORDER BY id").fetchall()
            if operation not in {r[0] for r in rows}:
                v.reject()
            affected = {operation}
            for _ in range(MAX_DEPTH):
                larger = affected | {n for n, raw, _ in rows if a.strict_json(raw.encode())["parent_operation"] in affected}
                if larger == affected:
                    break
                affected = larger
            else:
                v.reject()
            changed = []
            for name, _, status in rows:
                if name in affected and status != "revoked":
                    db.execute("UPDATE operations SET state='revoked' WHERE id=?", (name,))
                    db.execute("INSERT INTO events(operation,event) VALUES(?,'revoked')", (name,))
                    changed.append(name)
        return {"root": operation, "affected": sorted(affected), "newly_revoked": sorted(changed), "production_activation": False}

    def reserve_nonce(self, operation, challenge, wire_sha):
        v.token(challenge)
        v.digest(wire_sha)
        with self.connect() as db:
            eligible(db, operation, {"sealed"})
            generation = db.execute("SELECT generation FROM operations WHERE id=?", (operation,)).fetchone()[0]
            db.execute("INSERT INTO nonces VALUES(?,?,'reserved',?)", (challenge, generation, wire_sha))

    def consume_nonce(self, operation, challenge):
        with self.connect() as db:
            eligible(db, operation, {"sealed"})
            generation = db.execute("SELECT generation FROM operations WHERE id=?", (operation,)).fetchone()[0]
            cursor = db.execute("UPDATE nonces SET state='consumed' WHERE nonce=? AND generation=? AND state='reserved'", (v.token(challenge), generation))
            if cursor.rowcount != 1:
                v.reject()

    def recover(self, operation):
        with self.connect(readonly=True) as db:
            row = db.execute("SELECT generation,state FROM operations WHERE id=?", (v.token(operation),)).fetchone()
            if row is None:
                v.reject()
            events = [r[0] for r in db.execute("SELECT event FROM events WHERE operation=? ORDER BY seq", (operation,))]
            nonces = dict(db.execute("SELECT state,count(*) FROM nonces WHERE generation=? GROUP BY state", (row[0],)))
        return {"operation_id": operation, "generation_id": row[0], "state": row[1], "events": events,
                "nonce_counts": nonces, "automatic_repair_or_replay": False}

    @classmethod
    def reconcile(cls, path, anchor_path, journal_id):
        """Explicit crash recovery, never called by ordinary reads or admission."""
        path, anchor = Path(path), Anchor(anchor_path)
        v.control_file(path)
        v.token(journal_id)
        with anchor.locked(write=True) as (fd, fence):
            if fence["journal_id"] != journal_id:
                v.reject()
            db = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=2, isolation_level=None)
            try:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")  # SQLite may roll back an interrupted uncommitted transaction.
                entries = inspect(db, journal_id)
                latest = anchor_frame(journal_id, entries[-1])
                if latest == fence:
                    action = "already_aligned"
                elif len(entries) >= 2 and anchor_frame(journal_id, entries[-2]) == fence:
                    action = "retained_committed_transaction"
                else:
                    v.reject()
                db.rollback()
                if action == "retained_committed_transaction":
                    anchor.append(fd, fence, latest)
            except sqlite3.Error:
                raise ValueError("Control recovery rejected") from None
            finally:
                db.close()
        return {"action": action, "fence": latest, "semantic_mutations_replayed": 0,
                "automatic_activation": False, "production_activation": False}

    def backup(self, destination):
        destination = Path(destination)
        v.owner_dir(destination.parent)
        v.write_new(destination, b"")
        with self.connect(readonly=True) as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
            latest = inspect(source, self.journal_id)[-1]
        v.sync_dir(destination.parent)
        return {"backup_sha256": a.digest(v.small(destination, maximum=16 * 1024**2)),
                "fence": anchor_frame(self.journal_id, latest), "anchor_in_backup": False, "production_activation": False}


def restore_backup(source, destination, anchor_path, approved_sha, journal_id):
    """Exact latest backup into a fresh location; never rewind the separate anchor."""
    source, destination = Path(source), v.owner_dir(destination)
    if list(destination.iterdir()):
        v.reject()
    raw = v.small(source, readonly=True, maximum=16 * 1024**2)
    if a.digest(raw) != v.digest(approved_sha):
        v.reject()
    anchor = Anchor(anchor_path)
    with anchor.locked(write=True) as (_, fence):
        if fence["journal_id"] != v.token(journal_id):
            v.reject()
        stage = destination / "quarantined.sqlite"
        v.write_new(stage, raw)
        db = sqlite3.connect(stage.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            latest = inspect(db, journal_id)[-1]
            if anchor_frame(journal_id, latest) != fence:
                v.reject()
        except sqlite3.Error:
            raise ValueError("Backup restore rejected") from None
        finally:
            db.close()
        stage.rename(destination / "control.sqlite")
        v.sync_dir(destination)
    return {"journal_id": journal_id, "fence": fence, "backup_sha256": approved_sha,
            "new_location": True, "nonce_or_revocation_reset": False, "production_activation": False}
