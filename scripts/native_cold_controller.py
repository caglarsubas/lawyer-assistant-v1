"""Opt-in cold interpreters; only retained invented fixture files and original pins."""

import http.client
import json
import multiprocessing
import os
import signal
import socket
import sqlite3
import sys
import threading
import time
import traceback
from dataclasses import replace
from pathlib import Path

sys.path[:0] = ["/host/backend", "/host/scripts", "/host/backend/tests", "/host", str(Path(__file__).resolve().parent)]
import native_operator_preview as retained  # noqa: E402
from controller_stage_manifest import strict  # noqa: E402
from native_cold_controller_report import CASES, COUNTS, FALSE, TRUE, plan_sha256, validate  # noqa: E402

PHASE = "initialization"
CHILD_FRAMES = []
FAULTS = {"pins", "descriptor", "handoff", "profile", "database", "expired", "preparer"}


def seed_controller(channel, packet):
    """A separate seeding interpreter exits; its objects never reach the supervisor."""
    f = None
    try:
        import operator_enrollment_evidence as e
        from cold_controller_fixture import retain
        from native_preview_restart import fixture
        f, selected, target, roots = fixture()
        pins = retain(f, selected, target, roots, retained.WORK / "cold-anchors", packet["manifest_sha256"])
        e.retain(retained.WORK / "client.json", e.encode({"cookies": f.cookies, "csrf": f.csrf, "sessions": f.sessions,
            "source_id": target.source_id, "handoff_sha256": target.sha256, "receipt_sha256": target.receipt_sha256,
            "provenance_sha256": target.provenance_sha256, "created_at": target.created_at}))
        channel.send({"seeded": True, "pins": pins, "pid": os.getpid()})
    except Exception as exc:  # noqa: BLE001 - fixed structural diagnostics only.
        channel.send({"failed": True, "error_type": type(exc).__name__})
    finally:
        if f is not None:
            f.store.engine.dispose()
        channel.close()


def cold_controller(channel, pins, fault):
    loaded, sock = None, None
    try:
        import operator_enrollment_evidence as e
        import operator_preview_binding as b
        import uvicorn
        from fastapi import HTTPException
        from operator_cold_recovery import recover
        from sqlalchemy import text
        from sqlalchemy.exc import OperationalError
        changed = pins
        if fault in {"descriptor", "handoff", "profile"}:
            changed = replace(pins, **{fault + "_sha256": "0" * 64})
        elif fault == "database":
            changed = replace(pins, database_identity=(0, 0))
        def clock():
            return e.utc() + (301 if fault == "expired" else 0)
        try:
            loaded = recover(retained.WORK / "restart-case", retained.WORK / "cold-anchors",
                             None if fault == "pins" else changed, clock=clock)
            app = b.bind_preview(retained.STAGE / "valid", pins.package_manifest_sha256,
                                 host_root=retained.HOST, binding=loaded.binding)
        except (ValueError, FileExistsError, PermissionError, HTTPException):
            if fault not in FAULTS:
                raise
            channel.send({"rejected": fault, "pid": os.getpid()})
            return
        if fault:
            raise ValueError("Negative cold reconstruction unexpectedly admitted")
        with loaded.store.session() as session:
            try:
                session.execute(text("CREATE TABLE forbidden_cold_write (id integer)"))
            except OperationalError as exc:
                if getattr(exc.orig, "sqlite_errorcode", None) != sqlite3.SQLITE_READONLY:
                    raise ValueError("Read-only account connection required") from None
            else:
                raise ValueError("Cold recovery opened writable accounts")
        counts = {"requests": 0, "authorized": False}
        authority = loaded.binding.adapter.service.reconciler.disposition.planner.authority
        original = authority.resolve
        def resolve(*args, **kwargs):
            actor = original(*args, **kwargs)
            counts["authorized"] = actor["kind"] == "reviewer"
            return actor
        authority.resolve = resolve
        async def instrumented(scope, receive, send):
            counts["requests"] += 1
            counts["authorized"] = False
            async def observed_receive():
                frame = await receive()
                if frame.get("more_body") and frame.get("body") == b"{":
                    if not counts["authorized"]:
                        raise ValueError("Real current authorization must precede partial-body checkpoint")
                    channel.send({"checkpoint": "authorized_partial_body", "requests": counts["requests"]})
                return frame
            return await app(scope, observed_receive, send)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(instrumented, access_log=False, log_level="critical", lifespan="off",
            proxy_headers=False, server_header=False, timeout_keep_alive=1, timeout_graceful_shutdown=2,
            limit_concurrency=4, h11_max_incomplete_event_size=16384))
        def control():
            if channel.recv() == "stop":
                server.should_exit = True
        threading.Thread(target=control, daemon=True).start()
        channel.send({"ready": True, "pid": os.getpid(), "address": sock.getsockname(), "requests": 0,
                      "readonly_accounts_verified": True})
        server.run(sockets=[sock])
        channel.send({"stopped": True, "requests": counts["requests"]})
    except Exception as exc:  # noqa: BLE001 - no credentials, private descriptor or exception values.
        frames = [{"source": Path(t.filename).name, "line": t.lineno, "function": t.name}
                  for t in traceback.extract_tb(exc.__traceback__)][-6:]
        channel.send({"failed": True, "error_type": type(exc).__name__, "frames": frames})
    finally:
        if loaded is not None:
            loaded.close()
        if sock is not None:
            sock.close()
        channel.close()


def campaign(packet):
    global PHASE
    import operator_enrollment_evidence as e
    from operator_cold_recovery import inventory
    if (os.getuid() != 10002 or packet["case_plan_sha256"] != plan_sha256()
            or retained.WORK.stat().st_uid != os.getuid() or retained.WORK.stat().st_mode & 0o777 != 0o700
            or (retained.WORK / ".qualification-volume").read_bytes() != b"disposable-operator-preview-v1\n"):
        raise ValueError("Closed private native context required")
    retained.readonly(retained.HOST)
    retained.readonly(retained.STAGE)
    retained.filesystem(retained.HOST)
    retained.filesystem(retained.STAGE)
    host, stage = retained.inventory(retained.HOST), retained.inventory(retained.STAGE)
    context, processes, rows, kills = multiprocessing.get_context("spawn"), [], [], []
    requests = 0
    def row(name):
        global PHASE
        PHASE = name
        if name not in CASES:
            raise ValueError("Closed cold-recovery case required")
        rows.append({"id": name, "state": "verified"})
    def process(target, *args):
        global CHILD_FRAMES
        parent, child = context.Pipe()
        worker = context.Process(target=target, args=(child, *args))
        worker.start()
        child.close()
        processes.append((worker, parent))
        if not parent.poll(30):
            raise TimeoutError("Cold interpreter startup exceeded budget")
        initial = parent.recv()
        if initial.get("failed"):
            CHILD_FRAMES = initial.get("frames", [])
            raise ValueError("Cold child initialization failed")
        if initial.get("pid") != worker.pid or worker.pid == os.getpid():
            raise ValueError("Fresh isolated interpreter failed")
        return worker, parent, initial
    def closed(address):
        try:
            connection = socket.create_connection(address, timeout=.3)
        except ConnectionRefusedError:
            return
        connection.close()
        raise ValueError("Cold controller left an open listener")
    try:
        PHASE = "seed"
        seeder, channel, initial = process(seed_controller, packet)
        pins = initial.get("pins")
        if initial.get("seeded") is not True:
            raise ValueError("Retained independent seed pins required")
        seeder.join(4)
        if seeder.exitcode != 0:
            raise ValueError("Seeder retained live controller state")
        row("C01_seed_process_exited")
        case, anchors = retained.WORK / "restart-case", retained.WORK / "cold-anchors"
        desc = e.decode(e.read(anchors / "controller.json"))
        roots = [case / desc["stores"][n]["path"] for n in ("source", "journal", "candidate", "readiness", "controls", "disposition")]
        before, keys = [inventory(root) for root in roots], inventory(anchors)
        client = e.decode(e.read(retained.WORK / "client.json"))
        database = case / "accounts/disposable-identities.sqlite"
        database_hash = e.sha(database.read_bytes())
        def exact(*, accounts=True):
            if before != [inventory(root) for root in roots] or keys != inventory(anchors):
                raise ValueError("Cold recovery changed exact stores or retained keys")
            if accounts and e.sha(database.read_bytes()) != database_hash:
                raise ValueError("Cold reconstruction wrote the account store")
        def start(fault=None):
            global PHASE
            PHASE = "cold_" + (fault or "listener")
            worker, pipe, first = process(cold_controller, pins, fault)
            if fault:
                if first != {"rejected": fault, "pid": worker.pid}:
                    raise ValueError("Changed or missing retained trust was not rejected")
                worker.join(4)
                if worker.exitcode != 0:
                    raise ValueError("Rejected controller failed to exit")
                return None
            if (first.get("ready") is not True or first.get("requests") != 0
                    or first.get("readonly_accounts_verified") is not True or first["address"][0] != "127.0.0.1"):
                raise ValueError("Cold load reused results or failed read-only binding")
            address = first["address"]
            deadline = time.monotonic() + 5
            while True:
                try:
                    socket.create_connection(address, timeout=.2).close()
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Cold listener unavailable") from None
                    time.sleep(.02)
            return worker, pipe, address
        def stop(item, *, kill, count):
            worker, pipe, address = item
            if kill:
                os.kill(worker.pid, signal.SIGKILL)
            else:
                pipe.send("stop")
            worker.join(4)
            if worker.exitcode != (-9 if kill else 0):
                raise ValueError("Actual controller exit differs")
            if kill:
                kills.append(worker.exitcode)
            elif not pipe.poll(1) or pipe.recv() != {"stopped": True, "requests": count}:
                raise ValueError("Fresh cold controller request count differs")
            closed(address)
        page = "/api/v1/firm-admin/disposition-receipt-stage/"
        preview, session, compare = page + "preview", page + "preview-session", page + "reobserve"
        headers = {"cookie": "la_session=" + client["cookies"]["reviewer"], "x-csrf-token": client["csrf"]["reviewer"],
                   "origin": pins.origin, "host": "operator.invalid", "content-type": "application/json"}
        def request(item, name, path, status=200, body=b"{}", extra=None, *, accounts=True):
            nonlocal requests
            connection = http.client.HTTPConnection(*item[2], timeout=4)
            selected = headers if extra is None else extra
            result, raw = retained.reply(connection, "GET" if path == session else "POST", path, selected, body if path != session else None)
            requests += 1
            if result != status or status != 200 and any(client[k].encode() in raw for k in ("handoff_sha256", "receipt_sha256")):
                raise ValueError("Cold authorization status or non-disclosure differs")
            value = e.decode(raw)
            if status == 200 and path == session and value["csrf_token"] != headers["x-csrf-token"]:
                raise ValueError("Original current session must authorize again")
            if status == 200 and path == preview and value["preview"] != {
                "source_id": client["source_id"], "handoff_sha256": client["handoff_sha256"],
                "provenance_sha256": client["provenance_sha256"], "prepared_at": client["created_at"],
                "expires_at": client["created_at"] + 300}:
                raise ValueError("Cold recovery renewed or changed the original handoff")
            if status == 200 and path == compare and value["state"] != "staged_handoff_reobserved":
                raise ValueError("Independent explicit comparison required")
            row(name)
            exact(accounts=accounts)
        idle = start()
        stop(idle, kill=True, count=0)
        row("K01_idle_controller_SIGKILL")
        row("K02_idle_listener_closed")
        for fault, name in zip(("pins", "descriptor", "handoff", "profile", "database", "expired"),
            ("B01_missing_independent_pins", "B02_wrong_descriptor_pin", "B03_wrong_handoff_pin",
             "B04_wrong_profile_pin", "B05_wrong_database_inode", "B06_expired_original_handoff"), strict=True):
            start(fault)
            row(name)
            exact()
        partial_worker = start()
        request(partial_worker, "R01_missing_cookie", preview, 403, extra={"host": "operator.invalid"})
        request(partial_worker, "R02_wrong_CSRF", preview, 403, extra={**headers, "x-csrf-token": "0" * 48})
        bootstrap = {**headers, "x-operator-preview": "1"}
        request(partial_worker, "R03_fresh_bootstrap", session, extra=bootstrap)
        request(partial_worker, "R04_exact_original_preview", preview)
        PHASE = "partial_body"
        partial = socket.create_connection(partial_worker[2], timeout=2)
        partial.sendall(("POST " + preview + " HTTP/1.1\r\n" + "\r\n".join(k + ": " + v for k, v in
            {**headers, "content-length": "2"}.items()) + "\r\n\r\n{").encode())
        requests += 1
        if not partial_worker[1].poll(1) or partial_worker[1].recv() != {"checkpoint": "authorized_partial_body", "requests": 5}:
            raise ValueError("Actual current-session partial-body admission required")
        stop(partial_worker, kill=True, count=5)
        row("K03_partial_controller_SIGKILL")
        try:
            raw = partial.recv(8192)
        except ConnectionResetError:
            raw = b""
        finally:
            partial.close()
        if raw:
            raise ValueError("Killed controller released a partial response")
        row("K04_partial_response_withheld")
        row("K05_partial_listener_closed")
        exact()
        observed = start()
        request(observed, "R05_cold_bootstrap", session, extra=bootstrap)
        request(observed, "R06_original_version_and_expiry", preview)
        payload = {"source_id": client["source_id"], "expected_handoff_sha256": client["handoff_sha256"],
                   "independent_receipt_sha256": client["receipt_sha256"]}
        request(observed, "R07_missing_independent_entry", compare, 400)
        request(observed, "R08_wrong_independent_entry", compare, 409, e.encode({**payload, "independent_receipt_sha256": "0" * 64}))
        request(observed, "R09_explicit_independent_comparison", compare, body=e.encode(payload))
        stop(observed, kill=True, count=5)
        row("K06_completed_observation_SIGKILL")
        row("K07_completed_listener_closed")
        exact()
        def revoke(role):
            from operator_cold_recovery import identity
            if identity(database) != pins.database_identity:
                raise ValueError("Original invented account store required")
            with sqlite3.connect(database) as db:
                count = db.execute("DELETE FROM sessions WHERE token_hash = ?", (client["sessions"][role],)).rowcount
                if count != 1:
                    raise ValueError("Explicit invented session revocation required")
        revoke("reviewer")
        revoked = start()
        request(revoked, "R10_revoked_cookie_bootstrap", session, 403, extra=bootstrap, accounts=False)
        request(revoked, "R11_revoked_cookie_preview", preview, 403, accounts=False)
        stop(revoked, kill=False, count=2)
        row("R12_clean_shutdown_closed")
        revoke("preparer")
        start("preparer")
        row("B07_revoked_preparer")
        exact(accounts=False)
        row("S01_original_six_stores_and_retained_keys")
        with sqlite3.connect(database) as db:
            if db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] != 1:
                raise ValueError("Recovery created or renewed an account session")
        row("S02_no_recovery_account_writes")
        if len({p.pid for p, _ in processes}) != 12 or requests != 12 or len(processes) != 12:
            raise ValueError("Actual cold interpreter or HTTP inventory differs")
        row("C02_distinct_cold_interpreters")
        if retained.inventory(retained.HOST) != host or retained.inventory(retained.STAGE) != stage:
            raise ValueError("Cold qualification changed public source or staged version")
        value = {"schema": "native-cold-controller-v1", "package_manifest_sha256": packet["manifest_sha256"],
            "case_plan_sha256": plan_sha256(), "cases": rows, "filesystem": "ext4", "SIGKILL_exitcodes": kills,
            "fixture_scope": "invented_accounts_and_encrypted_metadata_only",
            "restart_scope": "spawned_cold_interpreters_original_pins_and_retained_files_only",
            **COUNTS, **dict.fromkeys(TRUE, True), **dict.fromkeys(FALSE, False)}
        validate(value, packet["manifest_sha256"])
        return value
    finally:
        for worker, pipe in processes:
            if worker.is_alive():
                worker.kill()
                worker.join(4)
            pipe.close()


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in {"prepare", "run"}:
            raise ValueError("Closed cold-controller entrypoint required")
        packet = strict(Path("/controller/packet.json").read_bytes())
        result = retained.prepare() if sys.argv[1] == "prepare" else campaign(packet)
        print(json.dumps(result))
    except Exception as exc:  # noqa: BLE001 - no private state or exception values.
        frames = [{"source": Path(t.filename).name, "line": t.lineno, "function": t.name}
                  for t in traceback.extract_tb(exc.__traceback__)][-8:]
        print(json.dumps({"schema": "native-preview-failure-v1", "phase": PHASE, "error_type": type(exc).__name__, "frames": (CHILD_FRAMES + frames)[-8:]}))
        raise SystemExit(1) from None
