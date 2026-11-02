"""Disposable disposition-journal worker; fault points exist only on private pipes."""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

FIELDS = {"production_activation", "profile", "firm_id", "bindings", "auth_key", "clock_path", "service", "headers", "disposition"}
OPERATIONS = {"disposition_prepare", "disposition_decide", "journal_inventory", "journal_reconcile"}


def worker(descriptor, pipe, fault="none"):
    try:
        asyncio.run(serve(descriptor, pipe, fault))
    except BaseException:
        try:
            pipe.send({"error": "disposable_disposition_journal_worker_rejected"})
        except (OSError, EOFError):
            pass
        raise SystemExit(1) from None


async def serve(descriptor, pipe, fault):
    import operator_enrollment_evidence as e
    import receipt_fault_native as retained

    path = Path(descriptor)
    if path != path.resolve() or not path.is_relative_to("/work") or fault not in {"none", "before_link", "after_publish"}:
        e.reject()
    config = e.decode(e.read(path))
    if not isinstance(config, dict) or set(config) != FIELDS or config["production_activation"] is not False:
        e.reject()
    for key in ("profile", "clock_path"):
        p = Path(config[key])
        if p != p.resolve() or not p.is_relative_to(path.parent):
            e.reject()
    key_path = Path(config["auth_key"])
    if key_path != key_path.resolve() or not key_path.is_relative_to("/anchors"):
        e.reject()
    packet = e.decode(Path("/controller/operator-packet.json").read_bytes())
    retained.packages(packet)
    import private_inventory_receipts as receipts
    from copy_disposition_fixture import load as load_disposition
    from disposition_journal_reconciliation import DispositionReconciler
    from journal_materialization_fixture import load
    from operator_review_auth import SessionAuthority
    from operator_review_fixture import ORIGIN

    from app.db import Store

    profile = Path(config["profile"])
    store = Store(SimpleNamespace(data_dir=profile, encryption_key=e.read(key_path).decode(), demo_mode=True,
        database_url="sqlite:///" + str(profile / "disposable-identities.sqlite")))
    authority = SessionAuthority(store, profile, firm_id=config["firm_id"], bindings=config["bindings"], origins=(ORIGIN,))
    def clock():
        v = e.decode(e.read(Path(config["clock_path"])))
        if set(v) != {"now"}:
            e.reject()
        return e.stamp(v["now"])
    service = load(config["service"], authority, clock)
    disposition = load_disposition(service, config["disposition"], path.parent)
    def checkpoint():
        pipe.send({"pid": os.getpid(), "checkpoint": fault})
        if not pipe.poll(5) or pipe.recv() != {"resume": True}:
            e.reject()
    if fault != "none":
        original = receipts._publish
        def publish(target, ident, raw):
            if target is not disposition.planner.journal:
                e.reject()
            if fault == "before_link":
                link = receipts.os.link
                def before_link(*args, **kwargs):
                    checkpoint()
                    return link(*args, **kwargs)
                receipts.os.link = before_link
                try:
                    return original(target, ident, raw)
                finally:
                    receipts.os.link = link
            value = original(target, ident, raw)
            checkpoint()
            return value
        receipts._publish = publish
    pipe.send({"pid": os.getpid(), "package_verified_before_auth": True, "actual_app_auth": True, "fault_point": fault})
    try:
        if not await asyncio.to_thread(pipe.poll, 25):
            e.reject()
        request = pipe.recv()
        if (not isinstance(request, dict) or set(request) != {"operation", "body"}
                or request["operation"] not in OPERATIONS or not isinstance(request["body"], dict)):
            e.reject()
        op = request["operation"]
        scope = {"type": "http", "method": "POST", "path": "/api/v1/firm-admin/journal-copy/" + op,
                 "headers": [(k.encode(), v.encode()) for k, v in config["headers"].items()]}
        if op.startswith("disposition_"):
            response = await disposition.dispatch(scope, op.removeprefix("disposition_"), **request["body"])
        else:
            response = await DispositionReconciler(disposition=disposition).dispatch(scope, op.removeprefix("journal_"), **request["body"])
        if any(n == "app.main" or n.startswith(("app.provider", "inference_engine")) for n in __import__("sys").modules):
            e.reject()
        pipe.send({"pid": os.getpid(), "operation": op, "response": response})
    finally:
        store.engine.dispose()
    pipe.send({"pid": os.getpid(), "completed": 1, "clean_exit": True, "controller_reads": 0})
