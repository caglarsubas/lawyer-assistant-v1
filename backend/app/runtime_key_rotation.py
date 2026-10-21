"""Offline, journaled Fernet migration for the qualified private-record profile.

The API and all writers must be stopped. A separately authenticated cold backup
and recovery-key bundle are prerequisites, not products of this module. Other
populated encrypted ledgers are refused: some snapshot bindings hash ciphertext.
No revisions, review decisions, original plaintext or semantic dates are changed.
"""

import hashlib
import json
import os
import re
import stat
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import inspect, text

STAGE = ".runtime-key-rotation"
MAX_BLOB = 32 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
RECORD_COLUMNS = {"id", "kind", "firm_id", "matter_id", "owner_id", "payload", "revision", "created_at"}


class RotationError(RuntimeError):
    """Fixed diagnostics; caller must suppress underlying exceptions/parameters."""


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()


def _sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())


def _read(path, maximum=MAX_BLOB):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise RotationError("Rotation storage profile is not admitted")
        raw = os.read(fd, maximum + 1)
        if len(raw) > maximum:
            raise RotationError("Rotation storage profile is not admitted")
        return raw
    finally:
        os.close(fd)


def _tables(conn):
    inspector = inspect(conn)
    names = inspector.get_table_names()
    if any(not re.fullmatch(r"[a-z_]+", t) for t in names) or "records" not in names:
        raise RotationError("Database profile is not admitted")
    if {c["name"] for c in inspector.get_columns("records")} != RECORD_COLUMNS:
        raise RotationError("Database profile is not admitted")
    for name in names:
        if name != "records" and "payload" in {c["name"] for c in inspector.get_columns(name)}:
            if conn.execute(text('SELECT count(*) FROM "' + name + '"')).scalar():
                raise RotationError("Populated dependent ciphertext ledgers require separate qualification")
    return names


def _lock(conn):
    if conn.dialect.name == "postgresql":
        conn.execute(text("LOCK TABLE records IN EXCLUSIVE MODE"))


def _rows(conn):
    rows = [dict(r) for r in conn.execute(text("SELECT * FROM records ORDER BY id")).mappings()]
    if not 1 <= len(rows) <= 10000:
        raise RotationError("Database profile is not admitted")
    return rows


def _semantic(conn, cipher):
    result = {}
    for name in _tables(conn):
        rows = [dict(r) for r in conn.execute(text('SELECT * FROM "' + name + '"')).mappings()]
        if len(rows) > 100000:
            raise RotationError("Database profile is not admitted")
        if name == "records":
            for row in rows:
                row["payload"] = _sha(cipher.decrypt(row["payload"].encode()))
        result[name] = _sha(_json(sorted(rows, key=lambda r: _json(r))))
    return result


def _replace(stage, path, raw):
    working = stage / "working"
    if working.exists():
        _read(working)  # Reject nonregular files/symlinks before removing a partial working copy.
        working.unlink()
    _write(working, raw)
    os.replace(working, path)
    _sync(path.parent)


def _file_paths(data):
    directory = data / "documents"
    if directory.is_symlink() or not directory.is_dir():
        raise RotationError("Document profile is not admitted")
    paths = sorted(directory.iterdir())
    if len(paths) > 10000 or any(not re.fullmatch(r"[a-f0-9]{32}\.enc", p.name) for p in paths):
        raise RotationError("Document profile is not admitted")
    return paths


def _finish(stage, plan):
    for side in ("old", "new"):
        for item in plan["files"]:
            path = stage / side / item["name"]
            if path.exists():
                path.unlink()
        if (stage / side).exists():
            (stage / side).rmdir()
    if (stage / "working").exists():
        _read(stage / "working")
        (stage / "working").unlink()
    (stage / "journal.fernet").unlink(missing_ok=True)
    stage.rmdir()
    _sync(stage.parent)


def _verify(conn, data, plan, cipher, old=None):
    if _semantic(conn, cipher) != plan["semantic"]:
        raise RotationError("Semantic preservation verification failed")
    if {p.name for p in _file_paths(data)} != {f["name"] for f in plan["files"]}:
        raise RotationError("Document preservation verification failed")
    for item in plan["files"]:
        raw = _read(data / "documents" / item["name"])
        if _sha(cipher.decrypt(raw)) != item["plain_sha256"] or cipher.extract_timestamp(raw) != item["timestamp"]:
            raise RotationError("Document preservation verification failed")
        if old is not None:
            _reject_old(old, raw)
    if old is not None:
        for row in _rows(conn):
            _reject_old(old, row["payload"].encode())
    return {"encrypted_records": len(plan["rows"]), "encrypted_originals": len(plan["files"]),
            "semantic_database_unchanged": True, "original_plaintext_unchanged": True,
            "fernet_timestamps_preserved": True, "old_key_rejected": old is not None}


def _reject_old(old, raw):
    try:
        old.decrypt(raw)
    except InvalidToken:
        return
    raise RotationError("Retired key still decrypts active ciphertext")


def rotate(engine, data_dir, old_key, new_key, *, checkpoint=lambda phase: None):
    """On ambiguous commit/crash, retain the journal and call recover before startup."""
    data = Path(data_dir)
    stage = data / STAGE
    if data.is_symlink() or stage.exists() or stage.is_symlink() or old_key == new_key:
        raise RotationError("Rotation requires a new key and an unstaged existing vault")
    old, new = Fernet(old_key), Fernet(new_key)
    multi = MultiFernet([new, old])
    committing = False
    plan = None
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            _lock(conn)
            semantic = _semantic(conn, old)
            rows = _rows(conn)
            plan = {"schema": "private-fernet-rotation-v1", "old_key_sha256": _sha(old_key),
                    "new_key_sha256": _sha(new_key), "semantic": semantic, "rows": [], "files": []}
            for row in rows:
                token = multi.rotate(row["payload"].encode())
                if old.extract_timestamp(row["payload"].encode()) != new.extract_timestamp(token):
                    raise RotationError("Ciphertext timestamp verification failed")
                plan["rows"].append({"id": row["id"], "revision": row["revision"],
                                     "old": row["payload"], "new": token.decode()})
            stage.mkdir(mode=0o700)
            (stage / "old").mkdir(mode=0o700)
            (stage / "new").mkdir(mode=0o700)
            total = 0
            for path in _file_paths(data):
                raw = _read(path)
                total += len(raw)
                if total > MAX_TOTAL:
                    raise RotationError("Document profile is not admitted")
                plain = old.decrypt(raw)
                token = multi.rotate(raw)
                item = {"name": path.name, "old_sha256": _sha(raw), "new_sha256": _sha(token),
                        "plain_sha256": _sha(plain), "timestamp": old.extract_timestamp(raw)}
                plan["files"].append(item)
                _write(stage / "old" / path.name, raw)
                _write(stage / "new" / path.name, token)
            journal = new.encrypt(_json(plan))
            if len(journal) > 96 * 1024 * 1024:
                raise RotationError("Rotation journal budget exceeded")
            _write(stage / "journal.fernet", journal)
            _sync(stage / "old")
            _sync(stage / "new")
            _sync(stage)
            _sync(data)
            checkpoint("staged")
            for item in plan["rows"]:
                changed = conn.execute(text("UPDATE records SET payload=:new WHERE id=:id AND revision=:revision AND payload=:old"), item)
                if changed.rowcount != 1:
                    raise RotationError("Database changed during rotation")
            for item in plan["files"]:
                _replace(stage, data / "documents" / item["name"], _read(stage / "new" / item["name"]))
                checkpoint("file_swapped")
            checkpoint("before_commit")
            committing = True
            tx.commit()
            checkpoint("after_commit")
            report = _verify(conn, data, plan, new, old)
            _finish(stage, plan)
            return {**report, "state": "rotated"}
        except BaseException:
            if not committing:
                tx.rollback()
                if plan and (stage / "journal.fernet").is_file():
                    for item in plan["files"]:
                        _replace(stage, data / "documents" / item["name"], _read(stage / "old" / item["name"]))
                    _verify(conn, data, plan, old)
                    _finish(stage, plan)
                elif plan and stage.is_dir():
                    # No journal means no active file/row swaps were started.
                    _finish(stage, plan)
                raise RotationError("Rotation stopped before commit; active data remain on the old key") from None
            raise RotationError("Rotation commit requires journal recovery before application startup") from None


def recover(engine, data_dir, old_key, new_key):
    """Choose rollback/roll-forward from exact committed row state, never a guess."""
    data = Path(data_dir)
    stage = data / STAGE
    if data.is_symlink() or stage.is_symlink():
        raise RotationError("Rotation journal is not admitted")
    old, new = Fernet(old_key), Fernet(new_key)
    try:
        plan = json.loads(new.decrypt(_read(stage / "journal.fernet", 96 * 1024 * 1024)))
        if any((stage / side).is_symlink() for side in ("old", "new")):
            raise RotationError("Rotation journal is not admitted")
        if (plan["schema"] != "private-fernet-rotation-v1" or plan["old_key_sha256"] != _sha(old_key)
                or plan["new_key_sha256"] != _sha(new_key)):
            raise RotationError("Rotation journal does not match supplied keys")
        with engine.begin() as conn:
            _lock(conn)
            current = {r["id"]: [r["revision"], r["payload"]] for r in _rows(conn)}
            states = [side for side in ("old", "new") if current == {
                row["id"]: [row["revision"], row[side]] for row in plan["rows"]}]
            if len(states) != 1:
                raise RotationError("Committed row state does not match the rotation journal")
            side = states[0]
            cipher = new if side == "new" else old
            if _semantic(conn, cipher) != plan["semantic"]:
                raise RotationError("Semantic preservation verification failed")
            if {p.name for p in _file_paths(data)} != {f["name"] for f in plan["files"]}:
                raise RotationError("Document set changed during rotation")
            replacements = []
            for item in plan["files"]:
                if not re.fullmatch(r"[a-f0-9]{32}\.enc", item["name"]):
                    raise RotationError("Rotation journal is not admitted")
                path = data / "documents" / item["name"]
                current_hash = _sha(_read(path))
                if current_hash not in {item["old_sha256"], item["new_sha256"]}:
                    raise RotationError("Document state does not match the rotation journal")
                if current_hash == item[side + "_sha256"]:
                    continue
                raw = _read(stage / side / item["name"])
                if _sha(raw) != item[side + "_sha256"]:
                    raise RotationError("Staged document integrity verification failed")
                replacements.append((path, raw))
            # Validate every input before overwriting even the first original.
            for path, raw in replacements:
                _replace(stage, path, raw)
            report = _verify(conn, data, plan, cipher, old if side == "new" else None)
            _finish(stage, plan)
            return {**report, "state": "rotated" if side == "new" else "rolled_back"}
    except Exception:
        raise RotationError("Rotation recovery stopped; retain journal and authenticated backup") from None
