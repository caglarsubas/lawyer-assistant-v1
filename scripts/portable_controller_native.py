"""Isolated-package acceptance driver; fake weights and loopback HTTP only."""

import asyncio
import json
import os
import shutil
import socket
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import controller_stage_manifest as external
import httpx
import portable_controller_fixture as q
import uvicorn


class Switch:
    def __init__(self, fixture):
        self.fixture, self.requests = fixture, 0

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            self.requests += 1
        await self.fixture.application(scope, receive, send)


async def protocol(f, *, native):
    f.application = f.app()
    switch = Switch(f)
    if not native:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=switch), base_url="http://fixture.invalid") as client:
            async def post(path, value):
                return await client.post(path, content=q.encode(value), headers={"authorization": "Bearer " + q.CREDENTIAL, "content-type": "application/json"})
            def rebuild():
                f.application = f.app()
            status, frame = await f.protocol(post, rebuild)
        return status, frame, switch.requests
    server = uvicorn.Server(uvicorn.Config(switch, log_config=None, log_level="critical", access_log=False,
                                           lifespan="off", server_header=False, date_header=False, timeout_graceful_shutdown=2))
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    listener.setblocking(False)
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(3):
            while not server.started:
                if task.done():
                    raise ValueError("Disposable HTTP startup failed")
                await asyncio.sleep(0.01)
        async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=0), trust_env=False, follow_redirects=False,
                                     base_url="http://127.0.0.1:" + str(listener.getsockname()[1]), timeout=5) as client:
            async def post(path, value):
                return await client.post(path, content=q.encode(value), headers={"authorization": "Bearer " + q.CREDENTIAL, "content-type": "application/json"})
            def rebuild():
                f.application = f.app()
            status, frame = await f.protocol(post, rebuild)
        return status, frame, switch.requests
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, 3)
        finally:
            listener.close()


async def run_case(name, stage, approved, models, work, anchors, m, *, native):
    result = {"id": name, "status": "invalid", "HTTP_requests": 0, "simulated_backend_sends": 0}
    if name.startswith(tuple("A%02d_" % n for n in range(1, 11))):
        target, expected = stage, approved
        if name in {n for n, _ in q.CASES[1:8]}:
            target = models / name
        if name == "A08_app_import":
            expected = q.sha((target / "guarded-stage-manifest.json").read_bytes())
        if name == "A09_wrong_approval":
            expected = "0" * 64
        if name == "A10_writable":
            target = work / "writable-stage"
            shutil.copytree(stage, target)
        try:
            external.inspect_stage(target, expected)
            result["status"] = "verified"
        except (ValueError, OSError, SyntaxError):
            result["status"] = "rejected"
        return result
    f = q.Fixture(name, models, work, anchors, m)
    f.change()
    if name in {"A27_HTTP", "A28_receipt_rollback"}:
        status, frame, requests = await protocol(f, native=native)
        result.update(status=status, frame=frame, HTTP_requests=requests, simulated_backend_sends=len(f.sent),
                      nonce_counts=f.journal.recover(f.operation)["nonce_counts"])
        return result
    if name == "A29_real_transport":
        real = httpx.AsyncHTTPTransport(retries=0)
        try:
            f.app(transport=real)
        except ValueError:
            result["status"] = "rejected"
        finally:
            await real.aclose()
        return result
    before = f.inventory()
    with ExitStack() as stack:
        if name == "A25_revoked_during_check":
            original = m.artifact_store.supervised_verify
            def revoke(*args, **kwargs):
                proof = original(*args, **kwargs)
                f.journal.revoke(f.operation)
                return proof
            stack.enter_context(patch.object(m.artifact_store, "supervised_verify", side_effect=revoke))
        if name == "A26_no_privileged_helpers":
            for helper in ("create_issuer", "load_signer", "confirm_key", "revoke_key"):
                stack.enter_context(patch.object(m.trust, helper, side_effect=AssertionError("Forbidden privileged helper")))
        assessed = m.readiness.assess(stage, approved, f.model, f.journal, f.binding, f.trust, **f.kw)
    exact = before == f.inventory()
    if name != "A25_revoked_during_check" and not exact:
        raise ValueError("Read-only readiness changed retained state")
    if any(assessed[n] for n in ("actual_provider_identity_verified", "executed_weights_qualified", "runtime_installation_authorized",
                                 "native_execution_authorized", "production_activation", "legal_qualification")):
        raise ValueError("Readiness granted authority")
    result.update(status=assessed["status"], gates=assessed["gates"], read_only_state_exact=exact,
                  external_revocation_injected=name == "A25_revoked_during_check")
    return result


def inventory(root):
    return {str(p.relative_to(root)): q.sha(p.read_bytes()) for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()}


def prepare(uid, gid, stage, m):
    roots = [Path("/" + n) for n in ("models", "work", "anchors")]
    if any(list(p.iterdir()) for p in roots):
        raise ValueError("Fresh disposable volumes required")
    q.prepare(roots[0], stage, m)
    shutil.copytree(stage, roots[0] / "stage")
    for root in roots:
        for parent, _, files in os.walk(root, topdown=False):
            p = Path(parent)
            public = root.name == "models" and p.relative_to(root).parts[:1] in [("stage",), *[(n,) for n, _ in q.CASES[1:8]]]
            for name in files:
                file = p / name
                if file.is_symlink():
                    os.lchown(file, uid, gid)
                else:
                    # Hardlink fixture has two names; chmod before either chown.
                    if file.stat().st_uid == os.getuid():
                        file.chmod(0o644 if public else 0o600)
                        os.chown(file, uid, gid)
            p.chmod(0o755 if public else 0o700)
            os.chown(p, uid, gid)
    mounts = Path("/proc/self/mountinfo").read_text().splitlines()
    return {"filesystems": {p.name: next(line.split(" - ", 1)[1].split()[0] for line in mounts if line.split()[4] == str(p)) for p in roots},
            "tensor_count": 0, "private_inputs": False}


async def campaign(stage, approved, m):
    models, work, anchors = [Path("/" + n) for n in ("models", "work", "anchors")]
    before = inventory(models)
    rows = []
    for name, expected in q.CASES:
        row = await run_case(name, stage, approved, models, work, anchors, m, native=True)
        rows.append(row)
        if row["status"] != expected:
            q.write(work / "failed-report.json", q.encode(rows))
            raise ValueError("Frozen portable qualification failed")
    if before != inventory(models):
        raise ValueError("Read-only fixtures changed")
    forbidden = any(n == "app" or n.startswith(("app.", "inference_engine")) for n in sys.modules)
    if forbidden:
        raise ValueError("Application or engine dependency loaded")
    return {"schema": "portable-controller-native-v1", "cases": rows, "package_manifest_sha256": approved,
            "actual_loopback_servers": 2, "actual_HTTP_requests": sum(r["HTTP_requests"] for r in rows),
            "read_only_model_inventory_exact": True, "application_or_engine_imports": False,
            "native_inference_calls": 0, "live_provider_requests": 0, "real_trust_confirmed": False,
            "private_case_inputs": False, "production_activation": False}


if __name__ == "__main__":
    packet = json.loads(Path("/controller/operator-packet.json").read_text())
    preparing = sys.argv[1] == "prepare"
    stage, approved = Path("/stage" if preparing else "/models/stage"), packet["approved_manifest_sha256"]
    # Trusted inspector runs before adding the package parent or importing it.
    external.inspect_stage(stage, approved, expected_owner=packet["source_owner" if preparing else "owner"])
    sys.path.insert(0, str(stage))
    m = q.modules()
    value = prepare(int(sys.argv[2]), int(sys.argv[3]), stage, m) if sys.argv[1] == "prepare" else asyncio.run(campaign(stage, approved, m))
    print(json.dumps(value), flush=True)
