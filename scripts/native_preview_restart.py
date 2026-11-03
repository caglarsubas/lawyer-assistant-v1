"""Native interruption probe. No production route, fault endpoint or retry executor."""

import asyncio
import http.client
import json
import multiprocessing
import os
import signal
import socket
import sys
import threading
import time
import traceback
from dataclasses import replace
from pathlib import Path

sys.path[:0] = ["/host/backend", "/host/scripts", "/host/backend/tests", "/host", str(Path(__file__).resolve().parent)]
import native_operator_preview as retained  # noqa: E402
from controller_stage_manifest import digest, strict  # noqa: E402
from native_preview_restart_report import CASES, FALSE, TRUE, plan_sha256, validate  # noqa: E402

PHASE = "initialization"


def fixture():
    import operator_checksum_handoff as h
    import operator_enrollment_evidence as e
    import operator_preview_binding as b
    from copy_disposition_fixture import make as disposition
    from disposition_journal_reconciliation import DispositionReconciler
    from disposition_reconciliation_receipt import DispositionReceiptService
    from journal_backup_fixture import Fixture
    from journal_materialization_fixture import make

    case = retained.WORK / "restart-case"
    case.mkdir(mode=0o700)
    f = Fixture(case)
    if f.decide(f.prepare())["state"] != "reviewed_for_metadata_planning":
        raise ValueError("Exact invented history required")
    copy = make(f)
    d = disposition(copy, case / "dispositions")
    reconciler = DispositionReconciler(disposition=d)
    observed = asyncio.run(reconciler.dispatch(f.scope(), "inventory"))
    service = DispositionReceiptService(reconciler=reconciler)
    receipt = asyncio.run(service.dispatch(f.scope(), "receipt", plan_id="a" * 32,
        plan_ciphertext_sha256=None, plan_sha256=None, decision_ciphertext_sha256=None,
        expected_snapshot_sha256=observed["snapshot_sha256"]))
    if receipt["state"] != "receipt_ready":
        raise ValueError("Exact invented receipt required")
    source_id = "9" * 32
    provenance = e.encode({"schema": "independent-receipt-checksum-provenance-v1", "source_id": source_id,
        "reference_id": "d" * 32, "receipt_sha256": receipt["receipt_sha256"], "binding_sha256": reconciler.validate(),
        "profile_id": f.authority.profile_id, "recorded_at": f.now, "basis": "separately_retained_operator_checksum_record",
        "sender_authenticated": False, "external_channel_verified": False})
    target = h.prepare_handoff(service, f.scope(), source_id=source_id, receipt_bytes=e.encode(receipt["receipt"]),
        expected_receipt_sha256=receipt["receipt_sha256"], provenance_bytes=provenance,
        expected_provenance_sha256=e.sha(provenance))
    adapter = h.OperatorChecksumAdapter(service=service, sources={source_id: target})
    selected = b.HostBinding(adapter=adapter, source_id=source_id, handoff_sha256=target.sha256,
        binding_sha256=target.binding_sha256, profile_id=target.profile_id, preparer_id=f.ids["preparer"],
        reviewer_id=f.ids["reviewer"], origin="http://operator.invalid")
    roots = (f.source, f.journal, copy.readiness.candidate.root, copy.readiness.reviews.planner.journal.root,
             copy.controls.planner.journal.root, d.planner.journal.root)
    return f, selected, target, roots


def histories(roots):
    return {str(root): [(p.name, digest(p.read_bytes()), p.stat().st_mode, p.stat().st_uid, p.stat().st_nlink)
                       for p in sorted(root.iterdir())] for root in roots}


def worker(sock, channel, f, selected, packet, fault):
    phase = "binding"
    try:
        import operator_preview_binding as b
        import uvicorn
        from fastapi import HTTPException
        # Parent closes every connection before fork; child receives a fresh pool.
        f.store.engine.dispose(close=False)
        if fault == "expired":
            f.now += 301
        if fault == "pin":
            selected = replace(selected, handoff_sha256="0" * 64)
        try:
            app = b.bind_preview(retained.STAGE / "valid", packet["manifest_sha256"],
                                 host_root=retained.HOST, binding=selected)
        except (ValueError, FileExistsError, PermissionError, HTTPException) as exc:
            expected = {"expired": FileExistsError, "pin": ValueError, "preparer": HTTPException}.get(fault)
            if expected is None or not isinstance(exc, expected):
                raise ValueError("Unexpected binding rejection") from None
            channel.send({"rejected": fault, "pid": os.getpid()})
            return
        if fault is not None:
            raise ValueError("Negative binding unexpectedly admitted")
        counts = {"requests": 0, "authorized": False}
        original = f.authority.resolve
        def resolve(*args, **kwargs):
            actor = original(*args, **kwargs)
            counts["authorized"] = actor["kind"] == "reviewer"
            return actor
        f.authority.resolve = resolve

        async def instrumented(scope, receive, send):
            counts["requests"] += 1
            counts["authorized"] = False
            async def observed_receive():
                frame = await receive()
                if frame.get("more_body") and frame.get("body") == b"{":
                    if not counts["authorized"]:
                        raise ValueError("Partial checkpoint preceded real admission")
                    channel.send({"checkpoint": "authorized_partial_body", "requests": counts["requests"]})
                return frame
            return await app(scope, observed_receive, send)

        server = uvicorn.Server(uvicorn.Config(instrumented, access_log=False, log_level="critical", lifespan="off",
            proxy_headers=False, server_header=False, timeout_keep_alive=1, timeout_graceful_shutdown=2,
            limit_concurrency=4, h11_max_incomplete_event_size=16384))
        def control():
            if channel.recv() == "stop":
                server.should_exit = True
        threading.Thread(target=control, daemon=True).start()
        phase = "listener"
        channel.send({"ready": True, "pid": os.getpid(), "requests": 0, "fresh_pool": True})
        server.run(sockets=[sock])
        channel.send({"stopped": True, "requests": counts["requests"]})
    except Exception as exc:  # noqa: BLE001 - never disclose exception values or credentials.
        channel.send({"failed": True, "phase": phase, "error_type": type(exc).__name__})
    finally:
        f.store.engine.dispose()
        sock.close()
        channel.close()


def campaign(packet):
    global PHASE
    if (os.getuid() != 10002 or packet["case_plan_sha256"] != plan_sha256()
            or retained.WORK.stat().st_uid != os.getuid() or retained.WORK.stat().st_mode & 0o777 != 0o700
            or (retained.WORK / ".qualification-volume").read_bytes() != b"disposable-operator-preview-v1\n"):
        raise ValueError("Frozen private native context required")
    retained.readonly(retained.HOST)
    retained.readonly(retained.STAGE)
    if retained.filesystem(retained.HOST) != retained.filesystem(retained.STAGE):
        raise ValueError("Matching native filesystems required")
    host, stage = retained.inventory(retained.HOST), retained.inventory(retained.STAGE)
    PHASE = "fixture"
    f, selected, target, roots = fixture()
    before = histories(roots)
    context, processes, rows, kills = multiprocessing.get_context("fork"), [], [], []
    total_requests = 0
    PAGE = "/api/v1/firm-admin/disposition-receipt-stage/"
    preview, session, comparison = PAGE + "preview", PAGE + "preview-session", PAGE + "reobserve"
    def row(name):
        global PHASE
        PHASE = name
        if name not in CASES:
            raise ValueError("Closed native case required")
        rows.append({"id": name, "state": "verified"})
    def exact():
        if before != histories(roots):
            raise ValueError("Read-only restart changed encrypted stores")
    def closed(address):
        try:
            connection = socket.create_connection(address, timeout=.3)
        except ConnectionRefusedError:
            return
        else:
            connection.close()
            raise ValueError("Listener survived exit")
    def start(fault=None):
        global PHASE
        PHASE = "start_" + (fault or "listener")
        f.store.engine.dispose()
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        address = sock.getsockname()
        parent, child = context.Pipe()
        process = context.Process(target=worker, args=(sock, child, f, selected, packet, fault))
        process.start()
        sock.close()
        child.close()
        processes.append((process, parent, address))
        if not parent.poll(20):
            raise TimeoutError("Bounded restart required")
        initial = parent.recv()
        if initial.get("pid") != process.pid or process.pid == os.getpid():
            raise ValueError("Separate fresh initialized worker required")
        if fault:
            if initial != {"rejected": fault, "pid": process.pid}:
                raise ValueError("Binding fault was not rejected")
            process.join(4)
            if process.exitcode != 0:
                raise ValueError("Rejected worker did not exit cleanly")
            closed(address)
        else:
            if initial != {"ready": True, "pid": process.pid, "requests": 0, "fresh_pool": True}:
                raise ValueError("Worker reused a request or authority result")
            deadline = time.monotonic() + 5
            while True:
                try:
                    socket.create_connection(address, timeout=.2).close()
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Restart listener unavailable") from None
                    time.sleep(.02)
        return process, parent, address
    def stop(item, *, kill, requests):
        process, channel, address = item
        if kill:
            os.kill(process.pid, signal.SIGKILL)
        else:
            channel.send("stop")
        process.join(4)
        if process.exitcode != (-9 if kill else 0):
            raise ValueError("Actual expected worker exit required")
        if kill:
            kills.append(process.exitcode)
        elif not channel.poll(1) or channel.recv() != {"stopped": True, "requests": requests}:
            raise ValueError("Completed request count differs")
        closed(address)
        exact()
    def headers(role="reviewer"):
        return {**{k.decode(): v.decode() for k, v in f.scope(role)["headers"]},
                "host": "operator.invalid", "content-type": "application/json"}
    def request(item, name, path, expected=200, body=b"{}", selected_headers=None):
        nonlocal total_requests
        global PHASE
        PHASE = name
        connection = http.client.HTTPConnection(*item[2], timeout=4)
        h = selected_headers if selected_headers is not None else headers()
        method = "GET" if path == session else "POST"
        status, raw = retained.reply(connection, method, path, h, body if method == "POST" else None)
        total_requests += 1
        if status != expected or expected != 200 and any(v.encode() in raw for v in (target.sha256, target.receipt_sha256)):
            raise ValueError("Frozen restart status or non-disclosure differs")
        value = strict(raw)
        if expected == 200 and path == session and value["csrf_token"] != h["x-csrf-token"]:
            raise ValueError("Fresh current-session bootstrap differs")
        if expected == 200 and path == preview:
            content = value["preview"]
            if (content != {"source_id": target.source_id, "handoff_sha256": target.sha256,
                    "provenance_sha256": target.provenance_sha256, "prepared_at": target.created_at,
                    "expires_at": target.created_at + 300} or value["preview_sha256"] != digest(json.dumps(
                        content, sort_keys=True, separators=(",", ":")).encode())):
                raise ValueError("Original evidence and expiry were not retained")
        if expected == 200 and path == comparison and value["state"] != "staged_handoff_reobserved":
            raise ValueError("Explicit fresh comparison required")
        row(name)
        exact()
    try:
        first = start()
        stop(first, kill=True, requests=0)
        row("K01_idle_SIGKILL")
        row("K02_idle_socket_closed")
        second = start()
        request(second, "R01_missing_session", preview, 403, selected_headers={"host": "operator.invalid"})
        request(second, "R02_wrong_CSRF", preview, 403, selected_headers={**headers(), "x-csrf-token": "0" * 48})
        request(second, "R03_current_bootstrap", session, selected_headers={**headers(), "x-operator-preview": "1"})
        request(second, "R04_exact_preview", preview)
        PHASE = "partial_request"
        partial = socket.create_connection(second[2], timeout=2)
        h = {**headers(), "content-length": "2"}
        partial.sendall(("POST " + preview + " HTTP/1.1\r\n" + "\r\n".join(k + ": " + v for k, v in h.items()) + "\r\n\r\n{").encode())
        total_requests += 1
        if not second[1].poll(1) or second[1].recv() != {"checkpoint": "authorized_partial_body", "requests": 5}:
            raise ValueError("Actual admitted partial-body checkpoint required")
        stop(second, kill=True, requests=5)
        row("K03_partial_body_SIGKILL")
        try:
            response = partial.recv(8192)
        except ConnectionResetError:
            response = b""
        finally:
            partial.close()
        if response:
            raise ValueError("Interrupted partial request released a response")
        row("K04_partial_response_withheld")
        row("K05_partial_socket_closed")
        old = headers()
        f.revoke("reviewer")
        from app.auth import create_session
        from app.db import User
        from app.db import digest as token_digest
        with f.store.session() as db:
            f.cookies["reviewer"], f.csrf["reviewer"] = create_session(db, db.get(User, f.ids["reviewer"]), 1)
        f.sessions["reviewer"] = token_digest(f.cookies["reviewer"])
        third = start()
        request(third, "R05_revoked_cookie", preview, 403, selected_headers=old)
        request(third, "R06_old_CSRF_new_cookie", preview, 403, selected_headers={**headers(), "x-csrf-token": old["x-csrf-token"]})
        request(third, "R07_new_session_bootstrap", session, selected_headers={**headers(), "x-operator-preview": "1"})
        request(third, "R08_new_session_preview", preview)
        payload = {"source_id": target.source_id, "expected_handoff_sha256": target.sha256,
                   "independent_receipt_sha256": target.receipt_sha256}
        request(third, "R09_independent_comparison", comparison, body=json.dumps(payload).encode())
        stop(third, kill=True, requests=5)
        row("K06_after_observation_SIGKILL")
        row("K07_observation_socket_closed")
        fourth = start()
        request(fourth, "R10_restart_bootstrap", session, selected_headers={**headers(), "x-operator-preview": "1"})
        request(fourth, "R11_original_version_and_expiry", preview)
        request(fourth, "R12_missing_independent_entry", comparison, 400)
        request(fourth, "R13_wrong_independent_entry", comparison, 409,
                body=json.dumps({**payload, "independent_receipt_sha256": "0" * 64}).encode())
        request(fourth, "R14_explicit_comparison", comparison, body=json.dumps(payload).encode())
        stop(fourth, kill=False, requests=5)
        row("R15_clean_shutdown_closed")
        start("expired")
        row("B01_expired_handoff")
        start("pin")
        row("B02_changed_trusted_pin")
        f.revoke("preparer")
        start("preparer")
        row("B03_revoked_preparer")
        exact()
        if (len({p.pid for p, _, _ in processes}) != 7 or total_requests != 15
                or retained.inventory(retained.HOST) != host or retained.inventory(retained.STAGE) != stage):
            raise ValueError("Closed native process/request/source inventory differs")
        value = {"schema": "native-preview-restart-v1", "package_manifest_sha256": packet["manifest_sha256"],
            "case_plan_sha256": plan_sha256(), "cases": rows, "filesystem": "ext4", "processes": len(processes),
            "SIGKILL_exitcodes": kills, "HTTP_requests": total_requests, "session_replacements": 1,
            "native_inference_calls": 0, "provider_requests": 0,
            "fixture_scope": "invented_accounts_and_encrypted_metadata_only",
            "restart_scope": "forked_workers_controller_retains_fixture_in_memory",
            **dict.fromkeys(FALSE, False), **dict.fromkeys(TRUE, True)}
        validate(value, packet["manifest_sha256"])
        return value
    finally:
        for process, channel, _ in processes:
            if process.is_alive():
                process.kill()
                process.join(4)
            channel.close()
        f.store.engine.dispose()


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in {"prepare", "run"}:
            raise ValueError("Closed native entrypoint required")
        packet = strict(Path("/controller/packet.json").read_bytes())
        result = retained.prepare() if sys.argv[1] == "prepare" else campaign(packet)
        print(json.dumps(result))
    except Exception as exc:  # noqa: BLE001 - safe structural diagnostics only.
        frames = [{"source": Path(t.filename).name, "line": t.lineno, "function": t.name}
                  for t in traceback.extract_tb(exc.__traceback__)][-8:]
        print(json.dumps({"schema": "native-preview-failure-v1", "phase": PHASE,
                          "error_type": type(exc).__name__, "frames": frames}))
        raise SystemExit(1) from None
