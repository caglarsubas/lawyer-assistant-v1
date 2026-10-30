"""Disposable copy worker on private pipes; no product route or fault endpoint."""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

FIELDS = {"production_activation", "profile", "firm_id", "bindings", "auth_key", "clock_path", "service", "headers"}
OPERATIONS = {"ready_observe", "ready_prepare", "ready_decide", "copy_prepare", "copy_decide", "materialize", "verify"}


def worker(descriptor, pipe, interrupt=False):
    try:
        asyncio.run(serve(descriptor, pipe, interrupt))
    except BaseException:
        try:
            pipe.send({"error": "disposable_materialization_worker_rejected"})
        except (OSError, EOFError):
            pass
        raise SystemExit(1) from None


async def serve(descriptor, pipe, interrupt):
    import operator_enrollment_evidence as e
    import receipt_fault_native as retained

    path = Path(descriptor)
    if path != path.resolve() or not path.is_relative_to("/work") or type(interrupt) is not bool:
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
    fired = False
    if interrupt:
        original = receipts._publish
        def publish(target, ident, raw):
            nonlocal fired
            value = original(target, ident, raw)
            if target is service.readiness.candidate and not fired:
                fired = True
                pipe.send({"pid": os.getpid(), "checkpoint": "target_copy_1"})
                if not pipe.poll(5) or pipe.recv() != {"resume": True}:
                    e.reject()
            return value
        receipts._publish = publish
    pipe.send({"pid": os.getpid(), "package_verified_before_auth": True, "actual_app_auth": True})
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
        if op.startswith("ready_"):
            response = await service.readiness.dispatch(scope, op.removeprefix("ready_"), **request["body"])
        else:
            response = await service.dispatch(scope, op.removeprefix("copy_"), **request["body"])
        pipe.send({"pid": os.getpid(), "operation": op, "response": response})
    finally:
        store.engine.dispose()
    pipe.send({"pid": os.getpid(), "completed": 1, "clean_exit": True, "controller_reads": 0})
