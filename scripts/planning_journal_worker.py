"""Opt-in disposable process worker; private pipes only, no product fault route."""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

FIELDS = {"production_activation", "profile", "firm_id", "bindings", "auth_key", "clock_path", "source_root",
          "journal_root", "source_key", "journal_key", "source_pins", "journal_binding", "headers"}


def worker(descriptor, pipe, point):
    try:
        asyncio.run(serve(descriptor, pipe, point))
    except BaseException:
        try:
            pipe.send({"error": "disposable_journal_worker_rejected"})
        except (OSError, EOFError):
            pass
        raise SystemExit(1) from None


async def serve(descriptor, pipe, point):
    import operator_enrollment_evidence as e
    import receipt_fault_native as retained
    path = Path(descriptor)
    if path != path.resolve() or not path.is_relative_to("/work"):
        e.reject()
    config = e.decode(e.read(path))
    if not isinstance(config, dict) or set(config) != FIELDS or config["production_activation"] is not False:
        e.reject()
    for key in ("profile", "clock_path", "source_root", "journal_root"):
        candidate = Path(config[key])
        if candidate != candidate.resolve() or not candidate.is_relative_to(path.parent):
            e.reject()
    for key in ("auth_key", "source_key", "journal_key"):
        candidate = Path(config[key])
        if candidate != candidate.resolve() or not candidate.is_relative_to("/anchors"):
            e.reject()
    packet = e.decode(Path("/controller/operator-packet.json").read_bytes())
    retained.packages(packet)  # Verify both read-only exports before host auth loads.
    import private_inventory_receipts as receipts
    from operator_review_auth import SessionAuthority
    from operator_review_fixture import ORIGIN
    from planning_journal_reconciliation import JournalBinding, JournalReconciler
    from receipt_fault_probe import Probe
    from receipt_provisioning_readiness import Pins
    from receipt_recovery_planning import RecoveryPlanner

    from app.db import Store

    def pins(value):
        return Pins(**{**value, "store_identity": tuple(value["store_identity"])})
    profile = Path(config["profile"])
    store = Store(SimpleNamespace(data_dir=profile, encryption_key=e.read(Path(config["auth_key"])).decode(),
        demo_mode=True, database_url="sqlite:///" + str(profile / "disposable-identities.sqlite")))
    authority = SessionAuthority(store, profile, firm_id=config["firm_id"], bindings=config["bindings"], origins=(ORIGIN,))
    source_pins = pins(config["source_pins"])
    bound = JournalBinding(**{**config["journal_binding"], "pins": pins(config["journal_binding"]["pins"])})
    source = receipts.ReceiptStore(root=Path(config["source_root"]), context_id=source_pins.context_id,
        scope_sha256=source_pins.scope_sha256, key=e.read(Path(config["source_key"])))
    journal = receipts.ReceiptStore(root=Path(config["journal_root"]), context_id=source.context_id,
        scope_sha256=source.scope_sha256, key=e.read(Path(config["journal_key"])))
    def clock():
        value = e.decode(e.read(Path(config["clock_path"])))
        if set(value) != {"now"}:
            e.reject()
        return e.stamp(value["now"])
    planner = RecoveryPlanner(source, journal, source_pins, authority, preparer_id=bound.preparer_id,
        reviewer_id=bound.reviewer_id, clock=clock)
    reconciler = JournalReconciler(planner=planner, binding=bound)
    class JournalProbe(Probe):
        def pause(self, point, reads=0):
            super().pause(point, 0)  # These operations perform no controller reads.
    probe = JournalProbe(point, pipe)
    probe.install(receipts, journal)
    pipe.send({"pid": os.getpid(), "package_verified_before_auth": True, "actual_app_auth": True})
    completed = 0
    try:
        while True:
            if not await asyncio.to_thread(pipe.poll, 25):
                e.reject()
            request = pipe.recv()
            if request == {"stop": True}:
                break
            if (not isinstance(request, dict) or set(request) != {"operation", "body"}
                    or request["operation"] not in {"source_inventory", "prepare", "decide", "inventory", "reconcile"}
                    or not isinstance(request["body"], dict) or completed >= 3):
                e.reject()
            operation = request["operation"]
            scope = {"type": "http", "method": "POST", "path": "/api/v1/firm-admin/planning-journal/" + operation,
                     "headers": [(k.encode(), v.encode()) for k, v in config["headers"].items()]}
            if operation in {"source_inventory", "prepare", "decide"}:
                response = await planner.dispatch(scope, "inventory" if operation == "source_inventory" else operation, **request["body"])
            else:
                response = await reconciler.dispatch(scope, operation, **request["body"])
            completed += 1
            pipe.send({"pid": os.getpid(), "operation": operation, "response": response})
    finally:
        store.engine.dispose()
    pipe.send({"pid": os.getpid(), "completed": completed, "clean_exit": True, "controller_reads": 0, "probe_fired": probe.fired})
