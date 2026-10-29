"""Bounded physical metadata observations. Never decrypt, repair or adopt receipts."""

import asyncio
import os
import re
import stat
import time
from collections import Counter

import operator_enrollment_evidence as e
import operator_recovery_inventory as inventory
import private_inventory_receipts as receipts
from receipt_provisioning_readiness import Pins, fingerprint

MAX_ENTRIES, MAX_TOTAL_BYTES, SCAN_SECONDS = 32, 1024 * 1024, 2
FLAGS = inventory.FLAGS | {"receipt_repair_authorized", "automatic_recovery", "record_adopted", "content_verified"}


def binding(store, reader, pins, actor):
    e.token(actor)
    if (not isinstance(store, receipts.ReceiptStore) or not isinstance(pins, Pins)
            or not isinstance(reader, inventory.BoundReader) or not callable(reader.authorize)
            or store.context_id != pins.context_id or store.scope_sha256 != pins.scope_sha256
            or reader.scope_sha256 != pins.scope_sha256 or store.identity != pins.store_identity
            or fingerprint(store.key) != pins.key_fingerprint):
        e.reject()
    receipts._root(store)
    return e.sha(e.encode({"context_id": pins.context_id, "scope_sha256": pins.scope_sha256,
        "store_identity": pins.store_identity, "key_fingerprint": pins.key_fingerprint,
        "profile_id": pins.profile_id, "profile_sha256": pins.profile_sha256}))


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def scan(store, bound, deadline):
    def budget():
        if time.monotonic() >= deadline:
            raise TimeoutError
    budget()
    directory = receipts._directory(store)
    try:
        before = identity(os.fstat(directory))
        rows, total = [], 0
        with os.scandir(directory) as items:
            for item in items:
                budget()
                if len(rows) >= MAX_ENTRIES:
                    raise TimeoutError
                name = item.name
                if re.fullmatch(r"[0-9a-f]{32}\.receipt", name):
                    kind, record = "record", name[:32]
                elif re.fullmatch(r"\.pending-[0-9a-f]{32}", name):
                    kind, record = "staging", None
                else:
                    e.reject()
                info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink < 1
                        or not 0 <= info.st_size <= receipts.MAX_FILE):
                    e.reject()
                total += info.st_size
                if total > MAX_TOTAL_BYTES:
                    raise TimeoutError
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
                with os.fdopen(fd, "rb") as stream:
                    if identity(os.fstat(stream.fileno())) != identity(info):
                        raise FileExistsError
                    raw = stream.read(receipts.MAX_FILE + 1)
                    if (len(raw) != info.st_size or identity(os.fstat(stream.fileno())) != identity(info)
                            or identity(os.stat(name, dir_fd=directory, follow_symlinks=False)) != identity(info)):
                        raise FileExistsError
                budget()
                rows.append({"entry_id": e.sha(e.encode({"binding": bound, "name": name})), "kind": kind,
                    "record_id": record, "ciphertext_sha256": e.sha(raw), "bytes": len(raw), "links": info.st_nlink,
                    "inode_sha256": e.sha(e.encode({"binding": bound, "inode": [info.st_dev, info.st_ino]})),
                    "version_sha256": e.sha(e.encode(identity(info))),
                    "envelope_shape_matches": len(raw) > len(receipts.MAGIC) + 28 and raw.startswith(receipts.MAGIC)})
        if before != identity(os.fstat(directory)):
            raise FileExistsError
        receipts._root(store)
        # Link identity, not matching bytes, establishes which names share an inode.
        for row in rows:
            group = [r for r in rows if r["inode_sha256"] == row["inode_sha256"]]
            if row["links"] != len(group):
                state = "unaccounted_links"
            elif len(group) == 2 and {r["kind"] for r in group} == {"record", "staging"}:
                state = "linked_publication" if all(r["envelope_shape_matches"] for r in group) else "unverifiable_links"
            elif len(group) != 1:
                state = "unexpected_link_topology"
            elif row["kind"] == "record":
                state = "single_link_record" if row["envelope_shape_matches"] else "unverifiable_record"
            else:
                state = "unpublished_staging" if row["envelope_shape_matches"] else "incomplete_staging"
            row["state"] = state
        rows.sort(key=lambda row: row["entry_id"])
        budget()
        return {"schema": "receipt-physical-inventory-v1", "binding_sha256": bound,
                "root_version_sha256": e.sha(e.encode(before)), "entries": rows,
                "counts": dict(sorted(Counter(row["state"] for row in rows).items()))}
    finally:
        os.close(directory)


async def observe(store, reader, pins, *, actor_sha256):
    result = {"schema": "receipt-interruption-inventory-v1", "state": "unavailable", "read_only": True,
              "metadata_only": True, "atomic_snapshot": False, "current_authority_assessed": False,
              "content_authenticity": "unassessed", "inventory": None, "snapshot_sha256": None,
              **dict.fromkeys(FLAGS, False)}
    try:
        async with asyncio.timeout(inventory.TOTAL_SECONDS):
            await receipts._authorize(reader, actor_sha256)
            bound = binding(store, reader, pins, actor_sha256)
            deadline = time.monotonic() + SCAN_SECONDS
            first = scan(store, bound, deadline)
            await receipts._authorize(reader, actor_sha256)
            second = scan(store, bound, deadline)
            if first != second or binding(store, reader, pins, actor_sha256) != bound:
                raise FileExistsError
            await receipts._authorize(reader, actor_sha256)
            result.update(state="observed_metadata", inventory=second, snapshot_sha256=e.sha(e.encode(second)))
    except PermissionError:
        result["state"] = "denied"
    except TimeoutError:
        result["state"] = "budget_exhausted"
    except FileExistsError:
        result["state"] = "conflict"
    except (ValueError, TypeError, KeyError, RecursionError):
        result["state"] = "unverifiable"
    except Exception:
        pass  # No paths, names, metadata fragments or exception bodies survive failure.
    return result
