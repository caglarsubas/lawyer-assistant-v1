"""Opt-in disposable fault worker. No fault controls are reachable over HTTP."""

import asyncio
import importlib
import os
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

FIELDS = {"production_activation", "stage", "approved", "profile", "firm_id", "bindings", "auth_key", "clock_path",
          "controller_port", "root", "receipt_key", "source_path", "source_sha256", "source_id", "selection", "pins"}


def configuration(path, e):
    path = Path(path)
    if path != path.resolve() or not path.is_relative_to("/work"):
        raise ValueError("Disposable descriptor required")
    value = e.decode(e.read(path))
    if (not isinstance(value, dict) or set(value) != FIELDS or value["production_activation"] is not False
            or value["stage"] != "/models/receipt-stage" or type(value["controller_port"]) is not int
            or not 1024 <= value["controller_port"] <= 65535):
        raise ValueError("Closed disposable worker wiring required")
    for name in ("profile", "root", "source_path", "clock_path"):
        target = Path(value[name])
        if target != target.resolve() or not target.is_relative_to(path.parent):
            raise ValueError("Exact disposable workspace required")
    for name in ("auth_key", "receipt_key"):
        target = Path(value[name])
        if target != target.resolve() or not target.is_relative_to("/anchors"):
            raise ValueError("Exact disposable key mount required")
    return value


def forbidden():
    return any(n == "app.main" or n.startswith(("app.provider", "inference_engine")) for n in sys.modules)


def worker(descriptor_path, pipe, stop, point):
    try:
        asyncio.run(serve(descriptor_path, pipe, stop, point))
    except BaseException:
        try:
            pipe.send({"error": "receipt_worker_rejected"})
        except (OSError, EOFError):
            pass
        raise SystemExit(1) from None


async def serve(descriptor_path, pipe, stop, point):
    from receipt_fault_probe import Probe
    probe = Probe(point, pipe)
    import operator_enrollment_evidence as e
    import receipt_stage_manifest as inspector

    config = configuration(descriptor_path, e)
    packet = e.decode(Path("/controller/operator-packet.json").read_bytes())
    if config["approved"] != packet["receipt_manifest_sha256"]:
        raise ValueError("Independent public package pin differs")
    inspector.inspect_stage(config["stage"], config["approved"])  # Never relax kernel read-only policy.
    sys.path.insert(0, config["stage"])
    m = SimpleNamespace(**{n: importlib.import_module("lawyer_receipt_stage." + n)
                          for n in ("adapter", "readiness", "receipts", "inventory")})
    if any(n == "app" or n.startswith(("app.", "inference_engine")) for n in sys.modules):
        raise ValueError("Package import loaded application or engine")
    # Trusted host authentication loads only after the isolated package is verified.
    import httpx
    import uvicorn
    from authenticated_operator_review import PREFIX
    from fastapi import HTTPException
    from operator_review_auth import SessionAuthority
    from operator_review_fixture import ORIGIN

    from app.db import Store

    profile = Path(config["profile"])
    store = Store(SimpleNamespace(data_dir=profile, encryption_key=e.read(Path(config["auth_key"])).decode(),
                                demo_mode=True, database_url="sqlite:///" + str(profile / "disposable-identities.sqlite")))
    authority = SessionAuthority(store, profile, firm_id=config["firm_id"], bindings=config["bindings"], origins=(ORIGIN,))
    receipts = m.receipts.ReceiptStore(root=Path(config["root"]), context_id=config["selection"]["context_id"],
                scope_sha256=config["pins"]["scope_sha256"], key=e.read(Path(config["receipt_key"])))
    probe.install(m.receipts, receipts)
    pins = m.readiness.Pins(**{**config["pins"], "store_identity": tuple(config["pins"]["store_identity"])})
    raw = e.read(Path(config["source_path"]))
    source = m.adapter.PreparedSource(raw=raw, expected_sha256=config["source_sha256"], selection=config["selection"])
    client = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=0), trust_env=False, follow_redirects=False,
                              base_url="http://127.0.0.1:" + str(config["controller_port"]), timeout=10)
    counts = {"HTTP_requests": 0, "controller_reads": 0}
    trace = []
    def clock():
        value = e.decode(e.read(Path(config["clock_path"])))
        if set(value) != {"now"}:
            raise ValueError("Closed disposable clock required")
        return e.stamp(value["now"])
    async def resolve(scope):
        try:
            current = authority.resolve(scope, "preparer", now=clock())
        except (HTTPException, ValueError):
            raise PermissionError from None
        actor = e.sha(e.encode(current))
        async def authorize():
            try:
                authority.recheck(current, now=clock())
            except (HTTPException, ValueError):
                raise PermissionError from None
            return actor
        async def read(action, body):
            if action not in {"joint_observe", "joint_finish_observe"}:
                raise ValueError("Read-only controller action required")
            await authorize()
            headers = {k.decode("ascii"): v.decode("ascii") for k, v in scope["headers"]
                       if k in {b"cookie", b"origin", b"x-csrf-token", b"content-type"}}
            # Fixed endpoint, loopback port and actions; never a user-provided URL.
            response = await client.post(PREFIX + action, content=e.encode(body), headers=headers)
            counts["controller_reads"] += 1
            await probe.after_read(counts["controller_reads"])
            if len(response.content) > 65536:
                raise ValueError("Controller response budget exceeded")
            return response.status_code, response.content
        return m.adapter.Session(actor_sha256=actor, profile_id=current["profile_id"],
                                 reader=m.inventory.BoundReader(scope_sha256=pins.scope_sha256, authorize=authorize, read=read))
    adapter = m.adapter.ReceiptAdapter(config["stage"], config["approved"], receipts, profile / "disposable-profile.json",
                                       pins, resolve, {config["source_id"]: source})
    if adapter.readiness()["state"] != "ready_for_disposable_validation":
        raise ValueError("Independent disposable bindings rejected")
    async def app(scope, receive, send):
        if scope["type"] != "http" or len(trace) >= 64:
            raise ValueError("Bounded HTTP campaign required")
        counts["HTTP_requests"] += 1
        before, status = counts["controller_reads"], None
        async def observed(frame):
            nonlocal status
            if frame["type"] == "http.response.start":
                status = frame["status"]
            await send(frame)
        await adapter(scope, receive, observed)
        trace.append({"status": status, "controller_reads": counts["controller_reads"] - before})
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
                    raise ValueError("Disposable receipt server startup failed")
                await asyncio.sleep(.01)
        if forbidden():
            raise ValueError("Forbidden provider startup")
        pipe.send({"pid": os.getpid(), "port": listener.getsockname()[1], "actual_auth": True, "package_verified_before_auth": True, "fault_point": point})
        while not stop.is_set():
            await asyncio.sleep(.01)
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 3)
        listener.close()
        await client.aclose()
        store.engine.dispose()
    pipe.send({"pid": os.getpid(), **counts, "trace": trace, "clean_exit": True, "probe_fired": probe.fired})
