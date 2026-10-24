"""Actual disposable loopback ASGI HTTP with a mock model backend only."""

import asyncio
import json
import os
import socket
import sys
from pathlib import Path

import artifact_store as a
import guarded_route_fixture as q
import httpx
import uvicorn


class Switch:
    def __init__(self, fixture):
        self.fixture, self.requests = fixture, 0

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            self.requests += 1
        await self.fixture.application(scope, receive, send)


async def case(name, binding_prefix):
    models, work, anchors = Path("/models"), Path("/work"), Path("/anchors")
    index = q.decode(q.volume.small(models / name / "index.json", readonly=True))
    proof = a.supervised_verify(models / name / ("snapshot-" + q.operation(name + "-child")) / "store",
                                index["manifest"], strategy="windowed-pinned")
    f = q.Fixture(name, models, work, anchors, binding_prefix=binding_prefix, proof=proof)
    try:
        f.application = f.app()
    except (ValueError, OSError):
        result = f.result("setup_rejected", "factory")
        return {**result, "loopback_server": False, "HTTP_requests": 0, "fixture_proof": proof}
    switch = Switch(f)
    server = uvicorn.Server(uvicorn.Config(switch, log_config=None, log_level="critical", access_log=False,
                                           lifespan="off", server_header=False, date_header=False,
                                           timeout_graceful_shutdown=2))
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    listener.setblocking(False)
    port = listener.getsockname()[1]
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(3):
            while not server.started:
                if task.done():
                    raise ValueError("Disposable server did not start")
                await asyncio.sleep(0.01)
        async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=0), trust_env=False,
                                     follow_redirects=False, base_url="http://127.0.0.1:" + str(port), timeout=5) as client:
            async def post(path, value):
                return await client.post(path, content=q.encode(value), headers={"authorization": "Bearer " + q.CREDENTIAL,
                                          "content-type": "application/json"})
            status = await f.run(post, f.app)
        if f.application.controller.context.get() is not None:
            raise ValueError("Request context leaked")
        return {**f.result(status, "direct" if name == "G23_direct_hook" else "HTTP"),
                "loopback_server": True, "HTTP_requests": switch.requests, "fixture_proof": proof}
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, 3)
        finally:
            listener.close()


def prepare(uid, gid):
    roots = [Path("/" + n) for n in ("models", "work", "anchors")]
    if any(list(p.iterdir()) for p in roots):
        raise ValueError("Fresh disposable volumes required")
    q.layout(Path("/models"))
    for root in roots:
        for parent, _, files in os.walk(root, topdown=False):
            for name in files:
                path = Path(parent) / name
                path.chmod(0o600)
                os.chown(path, uid, gid)
            os.chmod(parent, 0o700)
            os.chown(parent, uid, gid)
    mounts = Path("/proc/self/mountinfo").read_text().splitlines()
    return {"filesystems": {p.name: next(line.split(" - ", 1)[1].split()[0] for line in mounts if line.split()[4] == str(p)) for p in roots},
            "fixture_cases": len(q.CASES), "tensor_count": 0, "private_inputs": False}


def inventory():
    root = Path("/models")
    return {str(p.relative_to(root)): q.sha(p.read_bytes()) for p in sorted(root.rglob("*")) if p.is_file()}


async def campaign():
    packet = json.loads(Path("/controller/operator-packet.json").read_text())
    before = inventory()
    rows = []
    for name, status, sends in q.CASES:
        result = await case(name, packet["binding_prefix"])
        rows.append(result)
        if result["status"] != status or result["simulated_backend_sends"] != sends:
            q.volume.write_new(Path("/work/failed-report.json"), q.encode(rows))
            raise ValueError("Frozen controller HTTP case failed")
    after = inventory()
    if before != after:
        raise ValueError("Read-only model fixture changed")
    return {"schema": "guarded-controller-native-report-v1", "policy_sha256": packet["policy_sha256"],
            "cases": rows, "read_only_model_inventory_exact": True, "model_inventory_sha256": q.sha(q.encode(before)),
            "actual_loopback_servers": sum(r["loopback_server"] for r in rows),
            "actual_HTTP_requests": sum(r["HTTP_requests"] for r in rows), "backend_transport": "explicit_httpx_mock_only",
            "live_provider_requests": 0, "native_inference_calls": 0, "runtime_keys_used": False,
            "independent_real_trust_confirmed": False, "private_case_inputs": False,
            "production_activation": False, "model_performance_retested": False}


if __name__ == "__main__":
    result = prepare(int(sys.argv[2]), int(sys.argv[3])) if sys.argv[1] == "prepare" else asyncio.run(campaign())
    print(json.dumps(result), flush=True)
