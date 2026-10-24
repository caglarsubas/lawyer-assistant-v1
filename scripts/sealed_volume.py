"""Staged model-only transfer into fresh volumes. No application/provider startup."""

import hashlib
import os
import re
import secrets
import sqlite3
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import artifact_store as a

FORMAT = "lawyer-sealed-model-bundle-v1"
SCHEMA = "sealed-volume-control-v1"
HEX = re.compile(r"[0-9a-f]{64}\Z")
TOKEN = re.compile(r"[0-9a-f]{32}\Z")


def reject():
    raise ValueError("Sealed model operation rejected")


def token(value):
    if not isinstance(value, str) or not TOKEN.fullmatch(value):
        reject()
    return value


def digest(value):
    if not isinstance(value, str) or not HEX.fullmatch(value):
        reject()
    return value


def owner_dir(path, *, readonly=False):
    path = Path(path).absolute()
    if path != path.resolve():
        reject()
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        reject()
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        if readonly and not a.readonly(fd):
            reject()
    finally:
        os.close(fd)
    return path


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def small(path, *, readonly=False, maximum=a.META):
    owner_dir(Path(path).parent, readonly=readonly)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= maximum
                or (readonly and not a.readonly(stream.fileno()))):
            reject()
        raw = stream.read(maximum + 1)
        if len(raw) != info.st_size or a.identity(info) != a.identity(os.fstat(stream.fileno())):
            reject()
        return raw


def write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def control_file(path):
    owner_dir(Path(path).parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= 16 * 1024**2):
            reject()
    finally:
        os.close(fd)


def validate_record(record):
    if (not isinstance(record, dict) or set(record) != {"operation_id", "generation_id", "bundle_index_sha256",
            "content_sha256", "manifest_digest", "volume_binding_sha256", "purpose", "parent_operation", "production_activation"}
            or record["production_activation"] is not False or record["purpose"] not in {"import", "restore"}
            or not isinstance(record["manifest_digest"], str) or not a.SHA.fullmatch(record["manifest_digest"])):
        reject()
    token(record["operation_id"])
    token(record["generation_id"])
    for key in ("bundle_index_sha256", "content_sha256", "volume_binding_sha256"):
        digest(record[key])
    if record["purpose"] == "restore":
        token(record["parent_operation"])
    elif record["parent_operation"] is not None:
        reject()
    return record


def projection(proof):
    return {"manifest": proof["manifest_digest"], "artifacts": proof["artifacts"]}


def index_for(proof):
    a.validate_proof(proof, proof["manifest_digest"], a.Budget(), strategy="windowed-pinned")
    return {"format": FORMAT, **projection(proof), "content_sha256": proof["content_identity_sha256"],
            "total_bytes": proof["bytes_hashed"]}


def parse_index(raw, expected_sha):
    if a.digest(raw) != digest(expected_sha):
        reject()
    value = a.strict_json(raw)
    if (not isinstance(value, dict) or set(value) != {"format", "manifest", "artifacts", "content_sha256", "total_bytes"}
            or value["format"] != FORMAT or not isinstance(value["manifest"], str)
            or not a.SHA.fullmatch(value["manifest"]) or not isinstance(value["artifacts"], list)
            or not 3 <= len(value["artifacts"]) <= 18):
        reject()
    refs, total = [], 0
    for item in value["artifacts"]:
        if (not isinstance(item, dict) or set(item) != {"digest", "bytes"}
                or not isinstance(item["digest"], str) or not a.SHA.fullmatch(item["digest"])
                or type(item["bytes"]) is not int or not 0 < item["bytes"] <= a.MAX_MODEL):
            reject()
        refs.append(item["digest"])
        total += item["bytes"]
    if (len(set(refs)) != len(refs) or refs[0] != value["manifest"] or type(value["total_bytes"]) is not int
            or value["total_bytes"] != total or total > a.MAX_TOTAL
            or value["content_sha256"] != a.digest(a.canonical({"manifest": value["manifest"], "artifacts": value["artifacts"]}))):
        reject()
    if raw != a.canonical(value):
        reject()
    return value


@dataclass(frozen=True)
class TransferBudget:
    seconds: float = 90
    max_bytes: int = a.MAX_TOTAL

    def validate(self):
        if (type(self.seconds) not in {float, int} or not 0 < self.seconds <= 180
                or type(self.max_bytes) is not int or not 0 < self.max_bytes <= a.MAX_TOTAL):
            reject()


def copy_store(source, target, index, *, deadline, max_bytes, cancelled=None, checkpoint=None):
    """Copy only approved content-addressed names, retaining all source descriptors."""
    owner_dir(source, readonly=True)
    owner_dir(source / "blobs", readonly=True)
    if index["total_bytes"] > max_bytes:
        reject()
    target.mkdir(mode=0o700)
    for name in ("blobs", "manifests", "manifests-v2"):
        (target / name).mkdir(mode=0o700)
    handles, copied = [], 0
    directories = []

    def check():
        if time.monotonic() >= deadline or (cancelled is not None and cancelled()):
            reject()

    try:
        root_fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        directories.append((root_fd, Path(source), a.identity(os.fstat(root_fd))))
        blobs_fd = os.open("blobs", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root_fd)
        directories.append((blobs_fd, Path(source) / "blobs", a.identity(os.fstat(blobs_fd))))
        for item in index["artifacts"]:
            check()
            name = item["digest"].replace(":", "-")
            path = source / "blobs" / name
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=blobs_fd)
            before = os.fstat(fd)
            handles.append((fd, path, a.identity(before)))
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_nlink != 1
                    or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size != item["bytes"] or not a.readonly(fd)):
                reject()
            out = os.open(target / "blobs" / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            count, h = 0, hashlib.sha256()
            with os.fdopen(os.dup(fd), "rb", buffering=0) as src, os.fdopen(out, "wb", buffering=0) as dst:
                while True:
                    check()
                    block = src.read(a.CHUNK)
                    if not block:
                        break
                    count += len(block)
                    copied += len(block)
                    if count > item["bytes"] or copied > max_bytes:
                        reject()
                    h.update(block)
                    pending = memoryview(block)
                    while pending:
                        n = dst.write(pending)
                        if not n:
                            reject()
                        pending = pending[n:]
                    if count % (64 * a.CHUNK) == 0:
                        os.fsync(dst.fileno())
                        if hasattr(os, "posix_fadvise"):
                            os.posix_fadvise(dst.fileno(), count - 64 * a.CHUNK, 64 * a.CHUNK, os.POSIX_FADV_DONTNEED)
                os.fsync(dst.fileno())
            if count != item["bytes"] or h.hexdigest() != item["digest"][7:]:
                reject()
            if checkpoint is not None:
                checkpoint("copied_blob")
        for fd, path, saved in handles:
            if a.identity(os.fstat(fd)) != saved or a.identity(path.lstat()) != saved or not a.readonly(fd):
                reject()
        for fd, path, saved in directories:
            if a.identity(os.fstat(fd)) != saved or a.identity(path.lstat()) != saved or not a.readonly(fd):
                reject()
        check()
        if copied != index["total_bytes"] or {p.name for p in (source / "blobs").iterdir()} != {v["digest"].replace(":", "-") for v in index["artifacts"]}:
            reject()
        for name in ("blobs", "manifests", "manifests-v2"):
            sync_dir(target / name)
        sync_dir(target)
        return copied
    finally:
        for fd, _, _ in reversed(handles):
            os.close(fd)
        for fd, _, _ in reversed(directories):
            os.close(fd)


def export_bundle(source, destination, manifest_digest, *, budget=TransferBudget(), cancelled=None):
    budget.validate()
    deadline = time.monotonic() + budget.seconds
    destination = owner_dir(destination)
    if list(destination.iterdir()):
        reject()
    proof = a.supervised_verify(source, manifest_digest, a.Budget(seconds=min(20, budget.seconds)), strategy="windowed-pinned", cancelled=cancelled)
    index = index_for(proof)
    stage = destination / ("staging-" + secrets.token_hex(16))
    stage.mkdir(mode=0o700)
    copied = copy_store(Path(source), stage / "store", index, deadline=deadline, max_bytes=budget.max_bytes, cancelled=cancelled)
    raw = a.canonical(index)
    write_new(stage / "index.json", raw)
    sync_dir(stage)
    if time.monotonic() >= deadline or (cancelled is not None and cancelled()):
        reject()
    stage.rename(destination / "bundle")
    sync_dir(destination)
    return {"bundle_index_sha256": a.digest(raw), "copied_bytes": copied, "content_sha256": index["content_sha256"], "production_activation": False}


class Journal:
    @classmethod
    def create(cls, path):
        path = Path(path)
        owner_dir(path.parent)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        db = sqlite3.connect(path)
        try:
            db.executescript("PRAGMA synchronous=FULL; CREATE TABLE metadata(schema TEXT);"
                             "CREATE TABLE operations(id TEXT PRIMARY KEY,generation TEXT UNIQUE,record TEXT,state TEXT,proof TEXT);"
                             "CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT,operation TEXT,event TEXT);"
                             "CREATE TABLE nonces(nonce TEXT PRIMARY KEY,generation TEXT,state TEXT,wire_sha TEXT);")
            db.execute("INSERT INTO metadata VALUES(?)", (SCHEMA,))
            db.commit()
        finally:
            db.close()
        sync_dir(path.parent)
        return cls(path)

    def __init__(self, path):
        self.path = Path(path)
        with self.connect(readonly=True) as db:
            if db.execute("PRAGMA integrity_check").fetchone() != ("ok",) or db.execute("SELECT schema FROM metadata").fetchall() != [(SCHEMA,)]:
                reject()

    @contextmanager
    def connect(self, *, readonly=False):
        # SQLite owns mutable-page consistency and locking; model-file time
        # invariants must not be applied to a live control journal.
        control_file(self.path)
        db = sqlite3.connect(self.path.resolve().as_uri() + ("?mode=ro" if readonly else "?mode=rw"), uri=True, timeout=2, isolation_level=None)
        try:
            if readonly:
                db.execute("PRAGMA query_only=ON")
            else:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
            yield db
            if not readonly:
                db.commit()
        except sqlite3.Error:
            db.rollback()
            raise ValueError("Sealed control journal rejected") from None
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, operation):
        token(operation)
        with self.connect(readonly=True) as db:
            row = db.execute("SELECT generation,record,state,proof FROM operations WHERE id=?", (operation,)).fetchone()
        if row is None:
            reject()
        record = validate_record(a.strict_json(row[1].encode()))
        if row[0] != record["generation_id"] or record["operation_id"] != operation or row[2] not in {"copying", "prepared", "sealed", "revoked"}:
            reject()
        return {"generation_id": row[0], "record": record, "state": row[2],
                "proof": a.strict_json(row[3].encode()) if row[3] else None}

    def begin(self, operation, index, index_sha, binding_sha, *, purpose, parent=None):
        token(operation)
        digest(index_sha)
        digest(binding_sha)
        parse_index(a.canonical(index), index_sha)
        if purpose not in {"import", "restore"} or (purpose == "import" and parent is not None):
            reject()
        generation = secrets.token_hex(16)
        record = {"operation_id": operation, "generation_id": generation, "bundle_index_sha256": index_sha,
                  "content_sha256": index["content_sha256"], "manifest_digest": index["manifest"],
                  "volume_binding_sha256": binding_sha, "purpose": purpose, "parent_operation": parent,
                  "production_activation": False}
        validate_record(record)
        with self.connect() as db:
            if purpose == "restore":
                token(parent)
                prior = db.execute("SELECT record,state FROM operations WHERE id=?", (parent,)).fetchone()
                if prior is None or prior[1] != "sealed" or a.strict_json(prior[0].encode())["bundle_index_sha256"] != index_sha:
                    reject()
            db.execute("INSERT INTO operations VALUES(?,?,?,'copying',NULL)", (operation, generation, a.canonical(record).decode()))
            db.execute("INSERT INTO events(operation,event) VALUES(?,'copying')", (operation,))
        return record

    def _transition(self, operation, previous, state, proof=None):
        allowed = {"copying": {"prepared", "revoked"}, "prepared": {"sealed", "revoked"}, "sealed": {"revoked"}}
        if state not in allowed.get(previous, set()):
            reject()
        with self.connect() as db:
            if state == "sealed":
                row = db.execute("SELECT record FROM operations WHERE id=?", (token(operation),)).fetchone()
                if row is None:
                    reject()
                record = a.strict_json(row[0].encode())
                a.validate_proof(proof, record["manifest_digest"], a.Budget(), strategy="windowed-pinned")
                if proof["content_identity_sha256"] != record["content_sha256"]:
                    reject()
            cursor = db.execute("UPDATE operations SET state=?,proof=COALESCE(?,proof) WHERE id=? AND state=?", (state, a.canonical(proof).decode() if proof else None, token(operation), previous))
            if cursor.rowcount != 1:
                reject()
            db.execute("INSERT INTO events(operation,event) VALUES(?,?)", (operation, state))

    def revoke(self, operation):
        row = self.get(operation)
        self._transition(operation, row["state"], "revoked")

    def recover(self, operation):
        row = self.get(operation)
        with self.connect(readonly=True) as db:
            events = [v[0] for v in db.execute("SELECT event FROM events WHERE operation=? ORDER BY seq", (operation,))]
            nonces = db.execute("SELECT state,count(*) FROM nonces WHERE generation=? GROUP BY state", (row["generation_id"],)).fetchall()
        return {"operation_id": operation, "generation_id": row["generation_id"], "state": row["state"],
                "events": events, "nonce_counts": dict(nonces), "automatic_repair_or_replay": False}

    def reserve_nonce(self, operation, challenge, wire_sha):
        token(challenge)
        digest(wire_sha)
        with self.connect() as db:
            row = db.execute("SELECT generation,state FROM operations WHERE id=?", (token(operation),)).fetchone()
            if row is None or row[1] != "sealed":
                reject()
            db.execute("INSERT INTO nonces VALUES(?,?,'reserved',?)", (challenge, row[0], wire_sha))

    def consume_nonce(self, operation, challenge):
        with self.connect() as db:
            row = db.execute("SELECT generation,state FROM operations WHERE id=?", (token(operation),)).fetchone()
            if row is None or row[1] != "sealed":
                reject()
            cursor = db.execute("UPDATE nonces SET state='consumed' WHERE nonce=? AND generation=? AND state='reserved'", (token(challenge), row[0]))
            if cursor.rowcount != 1:
                reject()


def import_bundle(bundle, destination, journal, operation, expected_index_sha, binding_sha, *,
                  purpose="import", parent=None, budget=TransferBudget(), cancelled=None, checkpoint=None):
    budget.validate()
    deadline = time.monotonic() + budget.seconds
    bundle, destination = owner_dir(bundle, readonly=True), owner_dir(destination)
    if {p.name for p in bundle.iterdir()} != {"index.json", "store"} or list(destination.iterdir()):
        reject()
    raw = small(bundle / "index.json", readonly=True)
    index = parse_index(raw, expected_index_sha)
    record = journal.begin(operation, index, expected_index_sha, binding_sha, purpose=purpose, parent=parent)
    write_new(destination / ".target-reserved", a.canonical({"operation_id": operation, "generation_id": record["generation_id"]}))
    sync_dir(destination)
    proof = a.supervised_verify(bundle / "store", index["manifest"], a.Budget(seconds=min(20, budget.seconds)), strategy="windowed-pinned", cancelled=cancelled)
    if index_for(proof) != index:
        reject()
    stage = destination / ("staging-" + record["generation_id"])
    stage.mkdir(mode=0o700)
    copied = copy_store(bundle / "store", stage / "store", index, deadline=deadline, max_bytes=budget.max_bytes,
                        cancelled=cancelled, checkpoint=checkpoint)
    if time.monotonic() >= deadline or (cancelled is not None and cancelled()):
        reject()
    stage.rename(destination / ("snapshot-" + record["generation_id"]))
    sync_dir(destination)
    if checkpoint is not None:
        checkpoint("renamed")
    if time.monotonic() >= deadline or (cancelled is not None and cancelled()):
        reject()
    journal._transition(operation, "copying", "prepared")
    if time.monotonic() >= deadline or (cancelled is not None and cancelled()):
        journal.revoke(operation)
        reject()
    return {"record": record, "copied_bytes": copied, "requires_readonly_reverification": True, "production_activation": False}


def seal(destination, journal, operation, binding_sha):
    destination = owner_dir(destination, readonly=True)
    row = journal.get(operation)
    if row["state"] not in {"prepared", "sealed"} or row["record"]["volume_binding_sha256"] != digest(binding_sha):
        reject()
    proof = a.supervised_verify(destination / ("snapshot-" + row["generation_id"]) / "store",
                                row["record"]["manifest_digest"], strategy="windowed-pinned")
    if proof["content_identity_sha256"] != row["record"]["content_sha256"]:
        reject()
    if row["state"] == "prepared":
        journal._transition(operation, "prepared", "sealed", proof)
    elif journal.get(operation)["state"] != "sealed":
        reject()
    return {"record": row["record"], "proof": proof, "native_execution_authorized": False, "production_activation": False}
