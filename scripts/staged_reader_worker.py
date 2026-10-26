"""Disposable process worker. Configuration is protected fixture input, never HTTP."""

import asyncio
import os
import socket
import sqlite3
import sys
from pathlib import Path


def worker(descriptor_path, pipe, stop):
    try:
        asyncio.run(serve(descriptor_path, pipe, stop))
    except BaseException:
        try:
            pipe.send({"error": "disposable_worker_rejected"})
        except Exception:
            pass
        raise SystemExit(1) from None


async def serve(descriptor_path, pipe, stop):
    from types import SimpleNamespace

    import operator_enrollment_evidence as e
    import operator_review_fixture as retained
    import portable_controller_fixture as portable
    import uvicorn
    from authenticated_operator_review import Target
    from enrollment_revocation import EnrollmentRevocation
    from enrollment_revocation_log import RevocationLog
    from operator_review_auth import SessionAuthority
    from operator_review_journal import ReviewJournal
    from restore_authorization import RestoreAuthorization
    from restore_control_log import RestoreControlLog
    from restore_key_custody import KeyCustody
    from restore_lifecycle import RestoreLifecycle
    from restore_lifecycle_log import LifecycleLog
    from review_history_backup import HistoryVault
    from sqlalchemy import delete
    from staged_reader import StagedReader
    from staged_reader_log import ReaderLog
    from withdrawal_history_backup import WithdrawalVault
    from withdrawal_history_service import WithdrawalHistory

    from app.db import LoginSession, Store

    path = Path(descriptor_path)
    if not path.resolve().is_relative_to("/work"):
        raise ValueError("Disposable worker input required")
    config = e.decode(e.read(path))
    if config["production_activation"] is not False:
        raise ValueError("Disposable worker scope required")
    work_keys = ("profile", "packet", "observation", "trust", "v2_path", "journal_path", "ledger", "restores", "control_root", "clock_path", "lifecycle_root", "revocation_root", "archive_restores", "reader_root")
    if (any(not Path(config[k]).resolve().is_relative_to(path.parent.resolve()) for k in work_keys)
            or any(not Path(config[k]).resolve().is_relative_to("/anchors") for k in ("v2_anchor", "journal_anchor", "key", "auth_key", "manifests", "custody", "control_anchor", "lifecycle_anchor", "revocation_anchor", "archive_manifests", "reader_anchor"))
            or any(not Path(config[k]).resolve().is_relative_to("/backups") for k in ("bundles", "archive_bundles"))
            or config["stage"] != "/models/stage" or not Path(config["model"]).resolve().is_relative_to("/models")):
        raise ValueError("Disposable worker paths required")
    stage = Path(config["stage"])
    e.inspect_stage(stage, e.decode(e.read(Path(config["packet"])))["package_manifest_sha256"])
    sys.path.insert(0, str(stage))
    api = portable.modules()
    store = Store(SimpleNamespace(data_dir=Path(config["profile"]), encryption_key=e.read(Path(config["auth_key"])).decode(),
                                  demo_mode=True, database_url="sqlite:///" + str(Path(config["profile"]) / "disposable-identities.sqlite")))
    authority = SessionAuthority(store, config["profile"], firm_id=config["firm_id"], bindings=config["bindings"], origins=(retained.ORIGIN,))
    v2 = api.control.Journal(config["v2_path"], config["v2_anchor"], config["v2_id"])
    b = config["binding"]
    binding = api.controller.Binding(b["journal_id"], b["operation_id"], b["record_sha256"], b["volume_binding_sha256"], b["pin"].encode())
    target = Target(Path(config["packet"]), config["packet_sha256"], Path(config["observation"]), config["observation_sha256"],
                    stage, Path(config["model"]), v2, binding, Path(config["trust"]), api)
    journal = ReviewJournal(config["journal_path"], config["journal_anchor"], config["ledger"], config["journal_scope"], config["journal_id"], api)
    fault = config["fault"]
    control_fault = config["control_fault"]
    journal_fault = config["journal_fault"]
    def checkpoint(name):
        nonlocal fault, journal_fault, control_fault
        if name == control_fault:
            control_fault = None
            raise ValueError("Invented interrupted restore control")
        if name == "committed_unanchored" and journal_fault:
            with sqlite3.connect(journal.path) as db:
                count = db.execute("SELECT count(*) FROM records").fetchone()[0]
            if count >= 2:
                journal_fault = False
                raise ValueError("Invented interrupted commit")
        if name == fault:
            fault = None
            if name == "before_backup_commit":
                with store.session() as session:
                    session.execute(delete(LoginSession).where(LoginSession.user_id == config["revoke_user"]))
                    session.commit()
            else:
                raise ValueError("Invented interrupted backup or restore")
    journal.checkpoint = checkpoint
    vault = HistoryVault(journal, config["bundles"], config["manifests"], config["restores"], config["key"], checkpoint=checkpoint)
    def clock():
        value = e.decode(e.read(Path(config["clock_path"])))
        if set(value) != {"now"}:
            raise ValueError("Disposable clock required")
        return e.stamp(value["now"])
    if not 2 <= len(config["generations"]) <= 8:
        raise ValueError("Bounded disposable enrollment catalog required")
    children = {}
    for item in config["generations"]:
        if (any(not Path(item[k]).resolve().is_relative_to("/anchors") for k in ("custody", "control_anchor"))
                or not Path(item["control_root"]).resolve().is_relative_to(path.parent.resolve())):
            raise ValueError("Guarded disposable generation paths required")
        custody = KeyCustody(config["key"], item["custody"], item["custody_sha256"], journal.scope)
        controls = RestoreControlLog(item["control_root"], item["control_anchor"], item["control_scope"], item["control_id"], api)
        if item["custody_sha256"] in children:
            raise ValueError("Duplicate enrollment refused")
        children[item["custody_sha256"]] = RestoreAuthorization(authority, target, journal.ledger, journal, vault, custody, controls, clock=clock)
    lifecycle = LifecycleLog(config["lifecycle_root"], config["lifecycle_anchor"], config["lifecycle_scope"], config["lifecycle_id"], api, checkpoint=checkpoint)
    app = RestoreLifecycle(children, config["initial_generation"], lifecycle, clock=clock, checkpoint=checkpoint)
    revocations = RevocationLog(config["revocation_root"], config["revocation_anchor"], config["revocation_scope"], config["revocation_id"], api, checkpoint=checkpoint)
    app = EnrollmentRevocation(app, revocations, clock=clock, checkpoint=checkpoint)
    archive = WithdrawalVault(app, config["archive_bundles"], config["archive_manifests"], config["archive_restores"], config["key"], checkpoint=checkpoint)
    app = WithdrawalHistory(app, archive, clock=clock)
    reader_fault = config["reader_fault"]
    def reader_checkpoint(name):
        nonlocal reader_fault
        if name == reader_fault:
            reader_fault = None
            raise ValueError("Invented interrupted reader control")
    reader = ReaderLog(config["reader_root"], config["reader_anchor"], config["reader_scope"], config["reader_id"], api, checkpoint=reader_checkpoint)
    app = StagedReader(app, reader, clock=clock, checkpoint=checkpoint)
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, log_level="critical", access_log=False, lifespan="off",
                                           server_header=False, date_header=False, timeout_graceful_shutdown=2))
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    listener.setblocking(False)
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(3):
            while not server.started:
                if task.done():
                    raise ValueError("Disposable worker startup failed")
                await asyncio.sleep(0.01)
        if any(n == "app.main" or n.startswith(("app.provider", "inference_engine")) for n in sys.modules):
            raise ValueError("Forbidden worker startup")
        with retained.forbid_provider_helpers(api):
            pipe.send({"pid": os.getpid(), "port": listener.getsockname()[1], "actual_auth": True})
            while not stop.is_set():
                await asyncio.sleep(0.01)
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 3)
        listener.close()
        store.engine.dispose()
