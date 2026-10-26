"""Separate disposable worker processes and actual loopback HTTP on real ext4."""

import asyncio
import json
import multiprocessing
import os
import sys
from pathlib import Path


async def case(name, models, work, anchors, api):
    import httpx
    import operator_enrollment_evidence as e
    import reader_lifecycle_fixture as q
    from operator_review_fixture import forbid_provider_helpers
    from reader_lifecycle_worker import worker

    f = q.Fixture(name, models, work, anchors, api, backups=Path("/backups"))
    processes, clients, pids = [], [], []
    context = multiprocessing.get_context("spawn")
    async def start(node, restored=None):
        path = f.work / ("worker-" + str(node) + ".json")
        e.retain(path, e.encode(f.descriptor(node, restored=restored)))
        parent, child = context.Pipe(duplex=False)
        stop = context.Event()
        process = context.Process(target=worker, args=(str(path), child, stop))
        process.start()
        child.close()
        processes.append((process, stop, parent))
        if not await asyncio.to_thread(parent.poll, 5):
            raise ValueError("Disposable worker startup budget exceeded")
        ready = parent.recv()
        if set(ready) != {"pid", "port", "actual_auth"} or ready["pid"] != process.pid or ready["pid"] in pids or ready["actual_auth"] is not True:
            raise ValueError("Distinct actual authenticated process required")
        pids.append(process.pid)
        client = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=0), trust_env=False, follow_redirects=False,
                                   base_url="http://127.0.0.1:" + str(ready["port"]), timeout=10)
        clients.append(client)
        return client
    try:
        # Both workers already coexist during the case. Start them together
        # within that same two-process/two-CPU budget instead of serializing
        # their independent interpreter and authentication initialization.
        a, b = await asyncio.gather(start(0), start(1))
        async def restored(ident):
            return await start(len(processes), restored=ident)
        f.open_restored = restored
        with forbid_provider_helpers(api):
            status = await f.run((a, b))
        row = f.result(status)
        row.update(distinct_worker_processes=len(set(pids)), actual_loopback_servers=len(pids), shared_disposable_identity_store=True)
    finally:
        await asyncio.gather(*(c.aclose() for c in clients))
        for process, stop, _ in processes:
            stop.set()
        clean = True
        for process, _, pipe in processes:
            await asyncio.to_thread(process.join, 4)
            if process.is_alive():
                process.terminate()
                await asyncio.to_thread(process.join, 2)
                clean = False
            clean = clean and process.exitcode == 0
            pipe.close()
        f.close()
        if not clean:
            raise ValueError("Disposable process exit failed")
    row["all_worker_processes_exited_cleanly"] = True
    return row


async def campaign(api):
    import operator_enrollment_evidence as e
    import portable_controller_native as retained
    import reader_lifecycle_fixture as q

    models, work, anchors = [Path("/" + n) for n in ("models", "work", "anchors")]
    mounts = {line.split()[4]: line.split()[0] for line in Path("/proc/self/mountinfo").read_text().splitlines()}
    if len({mounts[str(p)] for p in (models, work, anchors, Path("/backups"))}) != 4:
        raise ValueError("Separate disposable retention mounts required")
    before, rows = retained.inventory(models), []
    for name, expected in q.CASES:
        print(json.dumps({"case_started": name}), file=sys.stderr, flush=True)
        row = await case(name, models, work, anchors, api)
        rows.append(row)
        print(json.dumps({"case_completed": name, "status": row["status"], "HTTP_requests": row["HTTP_requests"]}), file=sys.stderr, flush=True)
        if row["status"] != expected:
            print(json.dumps({"failed_case": name, "retained_rows": rows}), flush=True)
            raise ValueError("Frozen multi-process history case failed")
    if retained.inventory(models) != before or any(n == "app.main" or n.startswith(("app.provider", "inference_engine")) for n in sys.modules):
        raise ValueError("Readonly model or startup invariant failed")
    return {"schema": "reader-lifecycle-native-v1", "cases": rows, "policy_sha256": e.sha(e.encode(q.POLICY)),
            "actual_loopback_servers": sum(r["actual_loopback_servers"] for r in rows),
            "actual_HTTP_requests": sum(r["HTTP_requests"] for r in rows),
            "min_distinct_worker_processes": min(r["distinct_worker_processes"] for r in rows),
            "read_only_model_and_package_inventory_exact": True, "actual_app_auth_used": True,
            "separate_backup_and_control_mounts": True,
            "app_main_or_provider_imported": False, "live_provider_requests": 0, "native_inference_calls": 0,
            "real_accounts_or_sessions_used": False, "real_trust_enrolled": False, "runtime_installation": False,
            "private_case_inputs": False, "production_activation": False}


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
    if preparing:
        result = retained.prepare(int(sys.argv[2]), int(sys.argv[3]), stage, api)
        backups = Path("/backups")
        backups.chmod(0o700)
        os.chown(backups, int(sys.argv[2]), int(sys.argv[3]))
        line = next(x for x in Path("/proc/self/mountinfo").read_text().splitlines() if x.split()[4] == "/backups")
        result["filesystems"]["backups"] = line.split(" - ", 1)[1].split()[0]
    else:
        result = asyncio.run(campaign(api))
    print(json.dumps(result), flush=True)
