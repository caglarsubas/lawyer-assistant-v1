"""Opt-in non-root native preview probe; only fresh public-code and fixture volumes."""

import asyncio
import errno
import http.client
import json
import multiprocessing
import os
import shutil
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

sys.path[:0] = ["/host/backend", "/host/scripts", "/host/backend/tests", "/host", str(Path(__file__).resolve().parent)]
from controller_stage_manifest import digest, strict  # noqa: E402
from native_operator_preview_report import CASES, FALSE, plan_sha256, validate  # noqa: E402

HOST, STAGE, WORK = Path("/host"), Path("/stage"), Path("/work")
PHASE = "initialization"
FAILURE_FRAMES = []
FAILURE_TYPE = None


def inventory(root):
    return {p.relative_to(root).as_posix(): digest(p.read_bytes()) for p in sorted(root.rglob("*"))
            if p.is_file() and not p.is_symlink()}


def filesystem(root):
    names = [r.split(" - ")[1].split()[0] for r in Path("/proc/self/mountinfo").read_text().splitlines()
             if r.split()[4] == str(root)]
    if names != ["ext4"]:
        raise ValueError("Exact ext4 volume mount required")
    return names[0]


def own(root, mode):
    for parent, _, files in os.walk(root, topdown=False):
        for name in files:
            path = Path(parent) / name
            if path.is_symlink():
                os.lchown(path, 10002, 10002)
            else:
                path.chmod(0o644)
                os.chown(path, 10002, 10002)
        Path(parent).chmod(mode)
        os.chown(parent, 10002, 10002)


def prepare():
    if os.getuid() != 0 or any(list(p.iterdir()) for p in (HOST, STAGE, WORK)):
        raise ValueError("Fresh qualification volumes required")
    shutil.copytree("/public-host", HOST, dirs_exist_ok=True)
    for name in ("valid", "M03_bytes", "M04_extra", "M05_symlink", "M06_hardlink", "M07_owner"):
        shutil.copytree("/public-preview", STAGE / name)
    asset = "operator_inspection_preview.html"
    (STAGE / "M03_bytes" / asset).write_text("invented changed page")
    (STAGE / "M04_extra" / "unapproved.txt").write_text("invented extra file")
    (STAGE / "M05_symlink" / asset).unlink()
    (STAGE / "M05_symlink" / asset).symlink_to(STAGE / "valid" / asset)
    os.link(STAGE / "M06_hardlink" / asset, STAGE / "external-link")
    # Keep the prepared volume nonempty: Docker's workdir copy-up can otherwise
    # replace an empty volume's root ownership on the second container creation.
    (WORK / ".qualification-volume").write_bytes(b"disposable-operator-preview-v1\n")
    own(HOST, 0o755)
    own(STAGE, 0o755)
    own(WORK, 0o700)
    os.chown(STAGE / "M07_owner" / asset, 10003, 10003)
    return {"prepared": True, "filesystem": filesystem(HOST), "private_case_inputs": False}


def readonly(root):
    if not os.statvfs(root).f_flag & os.ST_RDONLY:
        raise ValueError("Kernel read-only mount required")
    try:
        (root / ".native-write-probe").write_bytes(b"probe")
    except OSError as exc:
        if exc.errno != errno.EROFS:
            raise ValueError("EROFS required, not a permission denial") from None
    else:
        raise ValueError("Kernel write unexpectedly succeeded")


def serve(sock, channel, packet):
    """Only this child owns invented credentials; IPC never reaches HTTP or logs."""
    value = None
    phase = "host_import"
    try:
        import operator_checksum_handoff as h
        import operator_enrollment_evidence as e
        import operator_preview_binding as b
        import uvicorn
        from copy_disposition_fixture import make as make_disposition
        from disposition_journal_reconciliation import DispositionReconciler
        from disposition_reconciliation_receipt import DispositionReceiptService
        from journal_backup_fixture import Fixture
        from journal_materialization_fixture import make

        case = WORK / "case"
        case.mkdir(mode=0o700)
        phase = "fixture_initialization"
        value = Fixture(case)
        if value.decide(value.prepare())["state"] != "reviewed_for_metadata_planning":
            raise ValueError("Invented initial review not retained")
        copy = make(value)
        disposition = make_disposition(copy, case / "dispositions")
        phase = "handoff_preparation"
        reconciler = DispositionReconciler(disposition=disposition)
        observed = asyncio.run(reconciler.dispatch(value.scope(), "inventory"))
        service = DispositionReceiptService(reconciler=reconciler)
        receipt = asyncio.run(service.dispatch(value.scope(), "receipt", plan_id="a" * 32,
            plan_ciphertext_sha256=None, plan_sha256=None, decision_ciphertext_sha256=None,
            expected_snapshot_sha256=observed["snapshot_sha256"]))
        if receipt["state"] != "receipt_ready":
            raise ValueError("Exact invented receipt required")
        SOURCE = "9" * 32
        provenance = e.encode({"schema": "independent-receipt-checksum-provenance-v1", "source_id": SOURCE,
            "reference_id": "d" * 32, "receipt_sha256": receipt["receipt_sha256"],
            "binding_sha256": reconciler.validate(), "profile_id": value.authority.profile_id,
            "recorded_at": value.now, "basis": "separately_retained_operator_checksum_record",
            "sender_authenticated": False, "external_channel_verified": False})
        target = h.prepare_handoff(service, value.scope(), source_id=SOURCE, receipt_bytes=e.encode(receipt["receipt"]),
            expected_receipt_sha256=receipt["receipt_sha256"], provenance_bytes=provenance,
            expected_provenance_sha256=e.sha(provenance))
        adapter = h.OperatorChecksumAdapter(service=service, sources={SOURCE: target})
        p = adapter.service.reconciler.disposition.planner
        selected = b.HostBinding(adapter=adapter, source_id=SOURCE, handoff_sha256=target.sha256,
            binding_sha256=target.binding_sha256, profile_id=target.profile_id, preparer_id=p.preparer,
            reviewer_id=p.reviewer, origin=p.authority.app.state.settings.origins[0])
        phase = "history_capture"
        def protected():
            roots = [value.source, value.journal, copy.readiness.candidate.root,
                     copy.readiness.reviews.planner.journal.root, copy.controls.planner.journal.root,
                     disposition.planner.journal.root]
            return {str(root): [(p.name, digest(p.read_bytes()), p.stat().st_mode, p.stat().st_uid, p.stat().st_nlink)
                               for p in sorted(root.iterdir())] for root in roots}
        before = protected()
        rows = [{"id": "M01_kernel_readonly", "state": "verified"}]
        phase = "writable_fixtures"
        shutil.copytree(STAGE / "valid", WORK / "writable-stage")
        (WORK / "writable-stage").chmod(0o755)
        shutil.copytree(HOST, WORK / "writable-host")
        (WORK / "writable-host").chmod(0o755)
        for name in list(CASES)[1:9]:
            phase = name
            root = WORK / "writable-stage" if name == "M08_writable_stage" else STAGE / (
                "valid" if name in {"M02_pin", "M09_writable_host"} else name)
            host = WORK / "writable-host" if name == "M09_writable_host" else HOST
            pin = "0" * 64 if name == "M02_pin" else packet["manifest_sha256"]
            try:
                b.bind_preview(root, pin, host_root=host, binding=selected)  # Default read-only policy.
            except ValueError:
                rows.append({"id": name, "state": "rejected"})
            else:
                raise ValueError("Negative native binding passed")
        phase = "valid_binding"
        app = b.bind_preview(STAGE / "valid", packet["manifest_sha256"], host_root=HOST, binding=selected)
        # The engine was created only inside this process; no inherited pool.
        server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level="critical", lifespan="off",
            proxy_headers=False, server_header=False, timeout_keep_alive=1, timeout_graceful_shutdown=2,
            limit_concurrency=4, h11_max_incomplete_event_size=16384))

        def control():
            while True:
                command = channel.recv()
                if command == "expire":
                    value.now = target.created_at + 301
                    channel.send({"advanced": True})
                elif command == "revoke":
                    value.revoke("reviewer")
                    channel.send({"revoked": True})
                elif command == "stop":
                    server.should_exit = True
                    return
                else:
                    server.should_exit = True
                    return

        threading.Thread(target=control, daemon=True).start()
        channel.send({"pid": os.getpid(), "rows": rows,
            "headers": [(k.decode(), v.decode()) for k, v in value.scope("reviewer")["headers"]],
            "source_id": SOURCE, "handoff_sha256": target.sha256, "provenance_sha256": target.provenance_sha256,
            "receipt_sha256": target.receipt_sha256, "prepared_at": target.created_at})
        server.run(sockets=[sock])
        channel.send({"stopped": True, "four_histories_exact": before == protected()})
    except Exception as exc:  # noqa: BLE001 - only fixed phase and exception class, never values.
        frames = [{"source": str(Path(t.filename).relative_to(HOST)) if Path(t.filename).is_relative_to(HOST)
                   else "dependency/" + Path(t.filename).name, "line": t.lineno, "function": t.name}
                  for t in traceback.extract_tb(exc.__traceback__)]
        channel.send({"failed": True, "phase": phase, "error_type": type(exc).__name__, "frames": frames[-8:]})
    finally:
        if value is not None:
            value.store.engine.dispose()
        channel.close()


def reply(connection, method, path, headers, body=None):
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    raw = response.read(24577)
    connection.close()  # One deliberate request per connection; never retry a POST after idle expiry.
    if len(raw) > 24576 or response.getheader("cache-control") != "no-store":
        raise ValueError("Bounded no-store response required")
    return response.status, raw


def campaign(packet):
    global PHASE, FAILURE_FRAMES, FAILURE_TYPE
    PHASE = "mount_checks"
    if (os.getuid() != 10002 or packet["case_plan_sha256"] != plan_sha256()
            or os.statvfs(WORK).f_flag & os.ST_RDONLY):
        raise ValueError("Non-root frozen native context required")
    os.chdir(WORK)
    if ((WORK / ".qualification-volume").read_bytes() != b"disposable-operator-preview-v1\n"
            or WORK.stat().st_uid != os.getuid() or WORK.stat().st_mode & 0o777 != 0o700):
        raise ValueError("Prepared disposable work namespace differs")
    readonly(HOST)
    readonly(STAGE)
    if filesystem(HOST) != filesystem(STAGE):
        raise ValueError("Matching volume filesystem required")
    host_before, stage_before = inventory(HOST), inventory(STAGE)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    address = sock.getsockname()
    context = multiprocessing.get_context("fork")
    parent, child = context.Pipe()
    process = context.Process(target=serve, args=(sock, child, packet))
    process.start()
    child.close()
    sock.close()
    stopped = None
    try:
        if not parent.poll(20):
            raise TimeoutError("Bounded host initialization required")
        setup = parent.recv()
        if "failed" in setup:
            FAILURE_FRAMES = setup.get("frames", [])
            FAILURE_TYPE = setup.get("error_type")
            PHASE = setup["phase"] if setup.get("phase") in {*CASES, "host_import", "fixture_initialization",
                "handoff_preparation", "history_capture", "writable_fixtures", "valid_binding"} else "host_initialization"
            raise ValueError("Host initialization failed")
        if type(setup.get("pid")) is not int or setup["pid"] <= 0 or setup["pid"] == os.getpid():
            raise ValueError("Separate initialized host required")
        deadline = time.monotonic() + 10
        while True:
            try:
                socket.create_connection(address, timeout=.2).close()
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Listener did not start") from None
                time.sleep(.02)
        rows = setup["rows"]
        headers = {**dict(setup["headers"]), "host": "operator.invalid", "content-type": "application/json"}
        client = http.client.HTTPConnection(*address, timeout=4)
        page = "/firm-admin/operator-preview"
        session = "/api/v1/firm-admin/disposition-receipt-stage/preview-session"
        preview = "/api/v1/firm-admin/disposition-receipt-stage/preview"
        comparison = "/api/v1/firm-admin/disposition-receipt-stage/reobserve"

        def checked(name, method, path, request_headers, body=None, status=200):
            global PHASE
            PHASE = name
            actual, raw = reply(client, method, path, request_headers, body)
            if actual != status:
                raise ValueError("Frozen native HTTP status differs")
            if status != 200 and (setup["receipt_sha256"].encode() in raw or setup["handoff_sha256"].encode() in raw):
                raise ValueError("Denied response disclosed evidence")
            rows.append({"id": name, "state": "verified"})
            return raw

        raw = checked("H01_shell", "GET", page, {"host": "operator.invalid"})
        if any(secret.encode() in raw for secret in (setup["receipt_sha256"], setup["handoff_sha256"],
                headers["cookie"], headers["x-csrf-token"])):
            raise ValueError("Generic shell disclosed private values")
        boot = strict(checked("H02_session", "GET", session, {**headers, "x-operator-preview": "1"}))
        if boot["csrf_token"] != headers["x-csrf-token"]:
            raise ValueError("Current session bootstrap differs")
        raw = checked("H03_preview", "POST", preview, headers, b"{}")
        value = strict(raw)
        from operator_enrollment_evidence import encode
        if (setup["receipt_sha256"].encode() in raw or value["preview_sha256"] != digest(encode(value["preview"]))
                or value["preview"] != {"source_id": setup["source_id"], "handoff_sha256": setup["handoff_sha256"],
                    "provenance_sha256": setup["provenance_sha256"], "prepared_at": setup["prepared_at"],
                    "expires_at": setup["prepared_at"] + 300}):
            raise ValueError("Exact preview binding differs")
        query = {"source_id": setup["source_id"], "expected_handoff_sha256": setup["handoff_sha256"],
                 "independent_receipt_sha256": "0" * 64}
        checked("H04_mismatch", "POST", comparison, headers, json.dumps(query), status=409)
        query["independent_receipt_sha256"] = setup["receipt_sha256"]
        observation = strict(checked("H05_comparison", "POST", comparison, headers, json.dumps(query)))
        if (observation["state"] != "staged_handoff_reobserved" or observation["observation_sha256"] != digest(
                encode(observation["observation"])) or observation["observation"]["provenance_sender_authenticated"] is not False):
            raise ValueError("Exact source response or authority boundary differs")
        checked("H06_csrf", "POST", preview, {k: v for k, v in headers.items() if k != "x-csrf-token"}, b"{}", 403)
        checked("H07_origin", "POST", preview, {**headers, "origin": "http://foreign.invalid"}, b"{}", 403)
        checked("H08_host", "POST", preview, {**headers, "host": "foreign.invalid"}, b"{}", 403)
        checked("H09_forwarded", "POST", preview, {**headers, "x-forwarded-host": "operator.invalid"}, b"{}", 403)
        PHASE = "H10_body_timeout"
        with socket.create_connection(address, timeout=4) as slow:
            slow.settimeout(4)
            request = "POST " + preview + " HTTP/1.1\r\n" + "".join(k + ": " + v + "\r\n" for k, v in headers.items())
            slow.sendall((request + "content-length: 64\r\n\r\n{").encode())
            response = http.client.HTTPResponse(slow)
            response.begin()
            raw = response.read(8193)
            if response.status != 504 or len(raw) > 4096 or b"budget_exhausted" not in raw or setup["handoff_sha256"].encode() in raw:
                raise ValueError("Native partial-body timeout failed")
        rows.append({"id": "H10_body_timeout", "state": "verified"})
        PHASE = "H11_expiry"
        parent.send("expire")
        if not parent.poll(3) or parent.recv() != {"advanced": True}:
            raise TimeoutError("Clock control acknowledgement missing")
        checked("H11_expiry", "POST", preview, headers, b"{}", 409)
        PHASE = "H12_revocation"
        parent.send("revoke")
        if not parent.poll(3) or parent.recv() != {"revoked": True}:
            raise TimeoutError("Revocation acknowledgement missing")
        checked("H12_revocation", "POST", preview, headers, b"{}", 403)
        client.close()
        PHASE = "H13_shutdown"
        parent.send("stop")
        if not parent.poll(5):
            raise TimeoutError("Listener shutdown acknowledgement missing")
        stopped = parent.recv()
        process.join(5)
        if process.exitcode != 0 or stopped != {"stopped": True, "four_histories_exact": True}:
            raise ValueError("Host did not stop with retained histories")
        try:
            socket.create_connection(address, timeout=.2).close()
        except ConnectionRefusedError:
            pass
        else:
            raise ValueError("Listener remained open")
        rows.append({"id": "H13_shutdown", "state": "verified"})
        report = {"schema": "native-operator-preview-v1", "package_manifest_sha256": packet["manifest_sha256"],
            "case_plan_sha256": plan_sha256(), "cases": rows, "filesystem": "ext4", "kernel_readonly": True,
            "source_inventory_exact": host_before == inventory(HOST), "stage_inventory_exact": stage_before == inventory(STAGE),
            "four_histories_exact": stopped["four_histories_exact"], "separate_server_and_client": True,
            "listener_loopback_only": address[0] == "127.0.0.1", "listener_closed": True, "native_inference_calls": 0,
            "provider_requests": 0, "HTTP_requests": 12, "clock_scope": "controlled_disposable_clock", **dict.fromkeys(FALSE, False)}
        validate(report, packet["manifest_sha256"])
        return report
    finally:
        if process.is_alive():
            process.terminate()
            process.join(3)
        if process.is_alive():
            process.kill()
            process.join(3)
        parent.close()


if __name__ == "__main__":
    try:
        packet = strict(Path("/controller/packet.json").read_bytes())
        value = prepare() if sys.argv[1:] == ["prepare"] else campaign(packet) if sys.argv[1:] == ["run"] else None
        if value is None:
            raise ValueError("Explicit native mode required")
        print(json.dumps(value, separators=(",", ":")))
    except Exception as exc:  # noqa: BLE001 - no raw fixture or configuration diagnostics.
        print(json.dumps({"schema": "native-preview-failure-v1", "phase": PHASE, "error_type": FAILURE_TYPE or type(exc).__name__,
                          "frames": FAILURE_FRAMES}))
        raise SystemExit("Native preview probe failed; activation remains disabled") from None
