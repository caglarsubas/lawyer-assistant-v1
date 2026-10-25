"""Actual disposable loopback HTTP and retained app auth; no app/provider startup."""

import asyncio
import json
import socket
import sys
from pathlib import Path


async def case(name, models, work, anchors, api):
    import httpx
    import operator_review_fixture as q
    import uvicorn

    f = q.Fixture(name, models, work, anchors, api)
    server = uvicorn.Server(uvicorn.Config(f.service, log_config=None, log_level="critical", access_log=False,
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
        with q.forbid_provider_helpers(api):
            async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=0), trust_env=False, follow_redirects=False,
                                         base_url="http://127.0.0.1:" + str(listener.getsockname()[1]), timeout=10) as client:
                status = await f.run(client)
        return f.result(status)
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, 3)
        finally:
            listener.close()
            f.close()


async def campaign(api):
    import operator_enrollment_evidence as evidence
    import operator_review_fixture as q
    import portable_controller_native as retained

    models, work, anchors = [Path("/" + n) for n in ("models", "work", "anchors")]
    before = retained.inventory(models)
    rows = []
    for name, expected in q.CASES:
        row = await case(name, models, work, anchors, api)
        rows.append(row)
        if row["status"] != expected:
            evidence.retain(work / "failed-review-report.json", evidence.encode(rows))
            raise ValueError("Frozen authenticated review case failed")
    if retained.inventory(models) != before or any(n == "app.main" or n.startswith(("app.provider", "inference_engine")) for n in sys.modules):
        raise ValueError("Readonly model or no-provider-startup invariant failed")
    return {"schema": "authenticated-operator-review-native-v1", "cases": rows,
            "policy_sha256": evidence.sha(evidence.encode(q.POLICY)), "actual_loopback_servers": len(rows),
            "actual_HTTP_requests": sum(r["HTTP_requests"] for r in rows), "read_only_model_and_package_inventory_exact": True,
            "actual_app_auth_used": True, "app_main_or_provider_imported": False,
            "live_provider_requests": 0, "native_inference_calls": 0, "real_accounts_or_sessions_used": False,
            "real_trust_enrolled": False, "runtime_installation": False, "private_case_inputs": False, "production_activation": False}


if __name__ == "__main__":
    import controller_stage_manifest as inspector
    import portable_controller_fixture as portable
    import portable_controller_native as retained

    packet = json.loads(Path("/controller/operator-packet.json").read_text())
    preparing = sys.argv[1] == "prepare"
    stage = Path("/stage" if preparing else "/models/stage")
    inspector.inspect_stage(stage, packet["approved_manifest_sha256"], expected_owner=packet["source_owner" if preparing else "owner"])
    sys.path.insert(0, str(stage))
    api = portable.modules()
    result = retained.prepare(int(sys.argv[2]), int(sys.argv[3]), stage, api) if preparing else asyncio.run(campaign(api))
    print(json.dumps(result), flush=True)
