"""Encrypted immutable selected metadata; access always needs fresh authorization.

Store paths, keys and readers are trusted wiring, never request parameters.
This adds no route, key provisioning, history repair or execution authority.
"""

import asyncio
import os
import secrets
import stat
from dataclasses import dataclass, field
from pathlib import Path

import operator_enrollment_evidence as e
import operator_inventory_handoff as h
import operator_recovery_inventory as inventory
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SCHEMA, MAGIC, MAX_PLAIN = "private-inventory-receipt-v1", b"LARCP1\0", 65536
MAX_FILE = MAX_PLAIN + len(MAGIC) + 12 + 16
HANDOFF_FIELDS = {"schema", "receipt_sha256", "selection", "state", "metadata_only", "atomic_snapshot",
                  "current_authority_assessed", "review_validity", "source", "destination", "comparison"}


@dataclass(frozen=True, kw_only=True)
class ReceiptStore:
    root: Path
    context_id: str
    scope_sha256: str
    key: bytes = field(repr=False)
    identity: tuple = field(init=False)

    def __post_init__(self):
        root = e.directory(self.root)
        e.token(self.context_id, 32)
        e.token(self.scope_sha256)
        if not isinstance(self.key, bytes) or len(self.key) != 32:
            e.reject()
        info = root.stat()
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "identity", (info.st_dev, info.st_ino))


def _root(store):
    root = e.directory(store.root)
    info = root.stat()
    if (info.st_dev, info.st_ino) != store.identity:
        e.reject()
    return root


def _directory(store):
    fd = os.open(_root(store), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    info = os.fstat(fd)
    if ((info.st_dev, info.st_ino) != store.identity or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_uid != os.getuid()):
        os.close(fd)
        e.reject()
    return fd


def _aad(store, record_id):
    return e.encode({"schema": SCHEMA, "record_id": record_id, "context_id": store.context_id,
                     "scope_sha256": store.scope_sha256})


def _bind(store, reader, actor, record_id):
    e.token(actor)
    e.token(record_id, 32)
    if (not isinstance(store, ReceiptStore) or not isinstance(reader, inventory.BoundReader)
            or reader.scope_sha256 != store.scope_sha256 or not callable(reader.read) or not callable(reader.authorize)):
        e.reject()


async def _authorize(reader, actor):
    async with asyncio.timeout(inventory.READ_SECONDS):
        if await reader.authorize() != actor:
            raise PermissionError


def _comparison(before, after):
    fields = sorted({key for a, b in zip(before["observations"], after["observations"], strict=True)
                     for key in inventory.FIELDS if a[key] != b[key]})
    return {"outcome": "changed_metadata" if fields else "unchanged_metadata", "changed_fields": fields}


def _row(row, actor, reader, selection):
    if (not isinstance(row, dict) or set(row) != h.ROW_FIELDS or row["review_validity"] != "unassessed"
            or row["first_read_completed"] is not True or not isinstance(row["observations"], list)
            or len(row["observations"]) != 2 or {k: row[k] for k in selection} != selection):
        e.reject()
    for index, view in enumerate(row["observations"]):
        if not isinstance(view, dict) or set(view) != inventory.FIELDS:
            e.reject()
        status = "joint_context_observed" if index == 0 else "joint_finish_reconciled_readonly"
        inventory.observation(e.encode({**view, "status": status, **dict.fromkeys(inventory.FLAGS, False)}),
                              status, reader, actor, selection["change_id"])
    if row["state"] != h._state(row["observations"], selection):
        e.reject()


def _record(raw, store, reader, record_id):
    value = h._decode(raw)
    if (len(raw) > MAX_PLAIN or not isinstance(value, dict)
            or set(value) != {"schema", "record_id", "context_id", "scope_sha256", "handoff", "handoff_sha256"}
            or value["schema"] != SCHEMA or value["record_id"] != record_id
            or value["context_id"] != store.context_id or value["scope_sha256"] != store.scope_sha256):
        e.reject()
    old = value["handoff"]
    if (not isinstance(old, dict) or set(old) != HANDOFF_FIELDS | inventory.FLAGS
            or old["schema"] != "operator-inventory-handoff-v1" or old["metadata_only"] is not True
            or old["atomic_snapshot"] is not False or old["current_authority_assessed"] is not False
            or old["review_validity"] != "unassessed" or any(old[k] is not False for k in inventory.FLAGS)
            or value["handoff_sha256"] != e.sha(e.encode(old))):
        e.reject()
    h._selection(old["selection"])
    if old["selection"]["context_id"] != store.context_id:
        e.reject()
    source, destination = old["source"], old["destination"]
    if (not isinstance(source, dict) or set(source) != {"receipt_sha256", "inventory_sha256", "actor_sha256", "row"}
            or not isinstance(destination, dict) or set(destination) != {"inventory_sha256", "actor_sha256", "scope_sha256", "row"}
            or source["receipt_sha256"] != old["receipt_sha256"] or destination["scope_sha256"] != store.scope_sha256):
        e.reject()
    e.token(old["receipt_sha256"])
    for part in (source, destination):
        e.token(part["inventory_sha256"])
        e.token(part["actor_sha256"])
        _row(part["row"], part["actor_sha256"], reader, old["selection"])
    if (old["state"] != destination["row"]["state"]
            or old["comparison"] != _comparison(source["row"], destination["row"])):
        e.reject()
    return value


def _read(store, record_id, expected):
    directory = _directory(store)
    name = record_id + ".receipt"
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_nlink != 1
                    or stat.S_IMODE(before.st_mode) != 0o600 or not len(MAGIC) + 28 < before.st_size <= MAX_FILE):
                e.reject()
            raw = stream.read(MAX_FILE + 1)
            def identity(s):
                return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if (len(raw) != before.st_size or identity(before) != identity(os.fstat(stream.fileno()))
                    or identity(before) != identity(os.stat(name, dir_fd=directory, follow_symlinks=False))
                    or e.sha(raw) != expected or not raw.startswith(MAGIC)):
                e.reject()
        _root(store)
        return raw
    finally:
        os.close(directory)


class RetentionUncertain(Exception):
    """Publication occurred but durability/acknowledgement could not be verified."""


def _publish(store, record_id, raw):
    directory = _directory(store)
    temporary = ".pending-" + secrets.token_hex(16)
    published, created = False, False
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
        created = True
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        _root(store)
        os.link(temporary, record_id + ".receipt", src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        published = True
        os.unlink(temporary, dir_fd=directory)
        created = False
        os.fsync(directory)
        _root(store)
        _read(store, record_id, e.sha(raw))
    except Exception:
        if published:
            raise RetentionUncertain from None
        raise
    finally:
        cleanup_error = False
        try:
            if created:
                os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        except OSError:
            cleanup_error = True
        os.close(directory)
        if cleanup_error:
            if published:
                raise RetentionUncertain from None
            raise OSError("Private staging cleanup incomplete") from None


def _result(operation, record_id, expected=None):
    return {"schema": "private-inventory-receipt-access-v1", "operation": operation, "record_id": record_id,
            "record_sha256": expected, "state": "unavailable", "metadata_only": True, "read_only": operation == "reobserve",
            "atomic_snapshot": False, "current_authority_assessed": False, "review_validity": "unassessed",
            "retained": None, "current": None, "comparison": None, **dict.fromkeys(inventory.FLAGS, False)}


async def retain(raw, expected_receipt_sha256, request, store, reader, *, actor_sha256, record_id):
    """Fresh handoff then create-only encrypted publication; return no cached body."""
    _bind(store, reader, actor_sha256, record_id)
    h._selection(request)
    request = dict(request)
    if request["context_id"] != store.context_id:
        e.reject()
    result = _result("retain", record_id)
    try:
        async with asyncio.timeout(inventory.TOTAL_SECONDS):
            await _authorize(reader, actor_sha256)
            value = await h.handoff(raw, expected_receipt_sha256, request, {store.context_id: reader}, actor_sha256=actor_sha256)
            result["state"] = value["state"]
            if value["source"] is None:
                return result
            plain = e.encode({"schema": SCHEMA, "record_id": record_id, "context_id": store.context_id,
                              "scope_sha256": store.scope_sha256, "handoff": value, "handoff_sha256": e.sha(e.encode(value))})
            _record(plain, store, reader, record_id)
            nonce = secrets.token_bytes(12)
            ciphertext = MAGIC + nonce + AESGCM(store.key).encrypt(nonce, plain, _aad(store, record_id))
            await _authorize(reader, actor_sha256)
            _publish(store, record_id, ciphertext)  # No yield between final authorization and publication.
            result.update(state="retained", record_sha256=e.sha(ciphertext))
    except PermissionError:
        result["state"] = "denied"
    except TimeoutError:
        result["state"] = "budget_exhausted"
    except RetentionUncertain:
        result["state"] = "retention_uncertain"  # Preserve a possibly published record; no retry or cleanup of history.
    except FileExistsError:
        result["state"] = "conflict"
    except (ValueError, TypeError, KeyError, RecursionError):
        result["state"] = "unverifiable"
    except Exception:
        result["state"] = "unavailable"
    return result


async def reobserve(store, reader, record_id, expected_record_sha256, *, actor_sha256):
    """Read exactly one pinned record and reauthorize fresh controller reads; no writes."""
    _bind(store, reader, actor_sha256, record_id)
    e.token(expected_record_sha256)
    result = _result("reobserve", record_id, expected_record_sha256)
    try:
        async with asyncio.timeout(inventory.TOTAL_SECONDS):
            await _authorize(reader, actor_sha256)
            raw = _read(store, record_id, expected_record_sha256)
            offset = len(MAGIC)
            plain = AESGCM(store.key).decrypt(raw[offset:offset + 12], raw[offset + 12:], _aad(store, record_id))
            record = _record(plain, store, reader, record_id)
            await _authorize(reader, actor_sha256)
            old = record["handoff"]
            current = await inventory.collect({store.context_id: reader}, [old["selection"]], actor_sha256=actor_sha256)
            row = current["rows"][0]
            result["state"] = row["state"]
            if row["state"] not in h.OBSERVED:
                return result
            comparison = _comparison(old["destination"]["row"], row)
            await _authorize(reader, actor_sha256)
            if _read(store, record_id, expected_record_sha256) != raw:
                e.reject()
            result.update(retained=old, current=row, comparison=comparison)
    except PermissionError:
        result["state"] = "denied"
    except TimeoutError:
        result["state"] = "budget_exhausted"
    except (InvalidTag, ValueError, TypeError, KeyError, RecursionError):
        result["state"] = "unverifiable"
    except Exception:
        result["state"] = "unavailable"  # Adapter errors stay private; cancellation propagates.
    return result
