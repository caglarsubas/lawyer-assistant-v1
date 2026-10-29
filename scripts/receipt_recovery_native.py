"""Frozen authorization-loss and process-kill protocols; disposable metadata only."""

import asyncio
import importlib
import json
import multiprocessing
import os
import shutil
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

sys.path[:0] = [str(Path(__file__).resolve().parent), "/backend"]
import controller_stage_manifest as controller_inspector  # noqa: E402
import receipt_stage_manifest as receipt_inspector  # noqa: E402
from receipt_fault_report import CASES, FALSE, TRUE, validate  # noqa: E402


def packages(packet, preparing=False):
    controller = Path("/stage" if preparing else "/models/stage")
    receipt = Path("/receipt-export" if preparing else "/models/receipt-stage")
    controller_inspector.inspect_stage(controller, packet["approved_manifest_sha256"], expected_owner=0 if preparing else 10002)
    receipt_inspector.inspect_stage(receipt, packet["receipt_manifest_sha256"])
    sys.path[:0] = [str(controller), str(receipt)]
    import portable_controller_fixture as portable
    api = portable.modules()
    m = SimpleNamespace(**{n: importlib.import_module("lawyer_receipt_stage." + n) for n in ("adapter", "receipts", "readiness", "inventory")})
    if any(n == "app" or n.startswith(("app.", "inference_engine")) for n in sys.modules):
        raise ValueError("Native package imports must precede host authentication")
    return api, m


def prepare(packet):
    api, _ = packages(packet, preparing=True)
    import portable_controller_native as retained
    proof = retained.prepare(10002, 10002, Path("/stage"), api)
    backups = Path("/backups")
    if list(backups.iterdir()):
        raise ValueError("Fresh backup volume required")
    backups.chmod(0o700)
    os.chown(backups, 10002, 10002)
    receipt = Path("/models/receipt-stage")
    shutil.copytree("/receipt-export", receipt)
    for parent, _, files in os.walk(receipt):
        for name in files:
            p = Path(parent) / name
            p.chmod(0o644)
            os.chown(p, 10002, 10002)
        Path(parent).chmod(0o755)
        os.chown(parent, 10002, 10002)
    if proof["private_inputs"] is not False:
        raise ValueError("Only invented fixture bytes allowed")
    return {"prepared": True, "private_case_inputs": False}


async def protocol(mode, api, m, packet):
    import httpx
    import mode_recovery_fixture as fixture
    import operator_enrollment_evidence as e
    from joint_recovery_worker import worker as controller_worker
    from receipt_fault_worker import worker as receipt_worker

    name = "C01_retirement_ordered" if mode == "retirement" else "C09_rollback_ordered"
    f = fixture.Fixture(name, Path("/models"), Path("/work"), Path("/anchors"), api, backups=Path("/backups"))
    context = multiprocessing.get_context("spawn")
    workers, clients, pids, traces, rows = [], [], set(), [], []
    async def start(target, descriptor, is_receipt=False, point="none"):
        parent, child = context.Pipe(duplex=True)
        stop = context.Event()
        process = context.Process(target=target, args=(str(descriptor), child, stop, point) if is_receipt else (str(descriptor), child, stop))
        process.start()
        child.close()
        item = {"process": process, "stop": stop, "pipe": parent, "receipt": is_receipt, "finished": False}
        workers.append(item)
        if not await asyncio.to_thread(parent.poll, 5):
            raise ValueError("Native worker startup budget exceeded")
        ready = parent.recv()
        required = {"pid", "port", "actual_auth"} | ({"package_verified_before_auth", "fault_point"} if is_receipt else set())
        if (set(ready) != required or ready["pid"] != process.pid or ready["pid"] in pids
                or ready["actual_auth"] is not True or (is_receipt and (ready["package_verified_before_auth"] is not True or ready["fault_point"] != point))):
            raise ValueError("Distinct verified authenticated workers required")
        pids.add(process.pid)
        client = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=0), trust_env=False, follow_redirects=False,
                                   base_url="http://127.0.0.1:" + str(ready["port"]), timeout=30)
        clients.append(client)
        item.update(port=ready["port"], client=client, point=point)
        return item
    async def controller(node, restored=None):
        path = f.work / ("native-controller-" + str(node) + ".json")
        e.retain(path, e.encode(f.descriptor(node, restored=restored)))
        return await start(controller_worker, path)
    async def stop_one(item):
        if item["finished"]:
            return
        item["stop"].set()
        await asyncio.to_thread(item["process"].join, 4)
        if item["process"].is_alive() or item["process"].exitcode != 0:
            raise ValueError("Native process failed clean exit")
        if item["receipt"]:
            if not item["pipe"].poll(1):
                raise ValueError("Native receipt request accounting missing")
            value = item["pipe"].recv()
            if (set(value) != {"pid", "HTTP_requests", "controller_reads", "trace", "clean_exit", "probe_fired"}
                    or value["pid"] != item["process"].pid or value["clean_exit"] is not True
                    or value["probe_fired"] is not (item["point"] != "none")
                    or value["HTTP_requests"] != len(value["trace"]) or value["controller_reads"] != sum(x["controller_reads"] for x in value["trace"])):
                raise ValueError("Closed process request accounting required")
            traces.extend(value["trace"])
        item["finished"] = True
        item["pipe"].close()
        await item["client"].aclose()
    try:
        left, right = await asyncio.gather(controller(0), controller(1))
        a, b = left["client"], right["client"]
        async def restored(ident):
            return (await controller(len(workers), restored=ident))["client"]
        f.open_restored = restored
        await f.setup_joint(a, b)
        first = (await f.observe_joint(a)).json()
        snapshot = f.authority.snapshot(f.session_ids["preparer"], f.ids["preparer"], "preparer", now=f.now)
        actor = e.sha(e.encode(snapshot))
        async def authorized():
            f.authority.recheck(snapshot, now=f.now)
            return actor
        async def read(action, body):
            response = await fixture.raw.Fixture.request(f, a, action, "preparer", body)
            return response.status_code, response.content
        selection = {"context_id": e.sha(mode.encode())[:32], "change_id": f.change_id, "expected_context_sha256": first["context_sha256"]}
        reader = m.inventory.BoundReader(scope_sha256=first["scope_sha256"], authorize=authorized, read=read)
        source = e.encode(await m.inventory.collect({selection["context_id"]: reader}, [selection], actor_sha256=actor))
        source_path = f.work / "receipt-source.json"
        e.retain(source_path, source)
        root = f.work / "private-receipts"
        root.mkdir(mode=0o700)
        key = os.urandom(32)
        key_path = f.base.anchors / "disposable-receipt.key"
        e.retain(key_path, key)
        store = m.receipts.ReceiptStore(root=root, context_id=selection["context_id"], scope_sha256=first["scope_sha256"], key=key)
        profile = f.profile / "disposable-profile.json"
        pins = m.readiness.Pins(context_id=selection["context_id"], scope_sha256=first["scope_sha256"],
                key_fingerprint=m.readiness.fingerprint(key), store_identity=store.identity, profile_id=f.authority.profile_id,
                profile_sha256=e.sha(e.read(profile)))
        old = f.descriptor(0)
        descriptor = {k: old[k] for k in ("profile", "firm_id", "bindings", "auth_key", "clock_path", "production_activation")}
        descriptor.update(stage="/models/receipt-stage", approved=packet["receipt_manifest_sha256"], controller_port=left["port"],
                          root=str(root), receipt_key=str(key_path), source_path=str(source_path), source_sha256=e.sha(source),
                          source_id="2" * 32, selection=selection, pins=asdict(pins))
        descriptor_path = f.work / "native-receipt.json"
        e.retain(descriptor_path, e.encode(descriptor))
        sessions = {f.session_ids["preparer"]}
        seed = "1" * 32
        def capture(record):
            return {"source_id": "2" * 32, "expected_source_sha256": e.sha(source), "record_id": record}
        def reobserve(record, pin):
            return {"record_id": record, "expected_record_sha256": pin}
        def files():
            return {p.name: (p.read_bytes(), p.stat().st_nlink, p.stat().st_mode, p.stat().st_uid)
                    for p in root.iterdir()}
        async def post(item, action, body):
            return await item["client"].post(m.adapter.PREFIX + action, content=e.encode(body), headers=f.headers("preparer"))
        def check(ident, response):
            _, status, state, reads = next(row for row in CASES if row[0] == ident)
            data = response.json()
            if (response.status_code != status or data["state"] != state
                    or response.headers.get("cache-control") != "no-store"
                    or any(data.get(k) is not False for k in m.inventory.FLAGS)):
                raise ValueError("Frozen fault response differed: " + ident)
            if status != 200 and any(data.get(k) is not None for k in ("retained", "current", "comparison")):
                raise ValueError("Failed authorization or recovery disclosed retained metadata")
            rows.append({"id": ident, "status": status, "state": state, "controller_reads": reads})
            return data
        async def request(item, ident, action, body):
            before, history = files(), f.four_histories()
            response = await post(item, action, body)
            data = check(ident, response)
            after = files()
            if (f.four_histories() != history or source_path.read_bytes() != source
                    or any(after.get(k) != v for k, v in before.items())):
                raise ValueError("Original ciphertext, source or histories changed")
            if action == "retain" and data["state"] == "retained":
                if set(after) - set(before) != {body["record_id"] + ".receipt"}:
                    raise ValueError("Create-only retention changed unrelated entries")
            elif before != after:
                raise ValueError("Read or rejected request changed private entries")
            return data
        async def checkpoint(item, point):
            if not await asyncio.to_thread(item["pipe"].poll, 4):
                raise ValueError("Fault boundary was not reached")
            value = item["pipe"].recv()
            reads = 1 if point == "after_read_1" else 2
            if value != {"pid": item["process"].pid, "checkpoint": point, "controller_reads": reads}:
                raise ValueError("Exact native fault boundary required")
            return reads
        plain = await start(receipt_worker, descriptor_path, True)
        data = await request(plain, "F01_seed", "retain", capture(seed))
        seed_pin = data["record_sha256"]
        seed_bytes = (root / (seed + ".receipt")).read_bytes()
        await stop_one(plain)
        for point, ident, record, action, resumed in (
                ("after_read_1", "F02_read_revoked", seed, "reobserve", "F03_read_reauthorized"),
                ("after_read_2", "F04_retain_revoked", "3" * 32, "retain", "F05_retain_reauthorized"),
                ("after_publish", "F06_ack_revoked", "4" * 32, "retain", "F07_ack_reauthorized")):
            item = await start(receipt_worker, descriptor_path, True, point)
            before, history = files(), f.four_histories()
            body = reobserve(seed, seed_pin) if action == "reobserve" else capture(record)
            task = asyncio.create_task(post(item, action, body))
            try:
                await checkpoint(item, point)
                f.revoke("preparer")
                item["pipe"].send({"resume": True})
                check(ident, await asyncio.wait_for(task, 5))
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
            after = files()
            if (f.four_histories() != history or source_path.read_bytes() != source
                    or any(after.get(k) != v for k, v in before.items())):
                raise ValueError("Revocation changed retained evidence")
            if point == "after_publish":
                if set(after) - set(before) != {record + ".receipt"}:
                    raise ValueError("Lost acknowledgement must preserve committed ciphertext")
            elif before != after:
                raise ValueError("Revocation before publication created a record")
            await stop_one(item)
            f.login("preparer")  # Actual password check; a new independently authenticated session.
            if f.session_ids["preparer"] in sessions:
                raise ValueError("Recovery replayed a revoked session")
            sessions.add(f.session_ids["preparer"])
            plain = await start(receipt_worker, descriptor_path, True)
            if point == "after_publish":
                pin = e.sha((root / (record + ".receipt")).read_bytes())
                await request(plain, resumed, "reobserve", reobserve(record, pin))
            elif action == "retain":
                await request(plain, resumed, "retain", capture(record))
            else:
                await request(plain, resumed, "reobserve", reobserve(seed, seed_pin))
            await stop_one(plain)
        for number, point in enumerate(("before_link", "after_link", "after_directory_sync")):
            record = str(5 + number) * 32
            offset = 8 + number * 3
            names = [CASES[i - 1][0] for i in range(offset, offset + 3)]
            item = await start(receipt_worker, descriptor_path, True, point)
            before, history = files(), f.four_histories()
            task = asyncio.create_task(post(item, "retain", capture(record)))
            try:
                reads = await checkpoint(item, point)
                at_point = files()
                new = set(at_point) - set(before)
                pending = {k for k in new if k.startswith(".pending-")}
                target = record + ".receipt"
                expected = pending | ({target} if point != "before_link" else set())
                if (new != expected or len(pending) != (0 if point == "after_directory_sync" else 1)
                        or any(at_point.get(k) != v for k, v in before.items())
                        or (point == "after_link" and (at_point[target][1] != 2
                            or at_point[next(iter(pending))][0] != at_point[target][0]))
                        or (point == "after_directory_sync" and at_point[target][1] != 1)):
                    raise ValueError("Actual publication syscall boundary differs")
                item["process"].kill()  # Actual SIGKILL, no graceful cleanup or fabricated exception.
                await asyncio.to_thread(item["process"].join, 3)
                if item["process"].is_alive() or item["process"].exitcode != -9:
                    raise ValueError("Exact forced process exit required")
                try:
                    await asyncio.wait_for(task, 3)
                except httpx.RemoteProtocolError:
                    pass
                else:
                    raise ValueError("Killed request must lose its HTTP acknowledgement")
                item["finished"] = True
                item["pipe"].close()
                await item["client"].aclose()
                if files() != at_point or f.four_histories() != history or source_path.read_bytes() != source:
                    raise ValueError("Killed worker altered retained history")
                rows.append({"id": names[0], "status": None, "state": "connection_closed", "controller_reads": reads})
                traces.append({"status": None, "controller_reads": reads})
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
            # Re-open exactly the same root, key, profile, source and package.
            # No unlink, retrying client, import repair or orphan cleanup occurs.
            plain = await start(receipt_worker, descriptor_path, True)
            pin = e.sha((root / target).read_bytes()) if (root / target).exists() else "0" * 64
            await request(plain, names[1], "reobserve", reobserve(record, pin))
            await request(plain, names[2], "retain", capture(record))
            if number == 2:
                await request(plain, "F17_original", "reobserve", reobserve(seed, seed_pin))
            await stop_one(plain)
        if len(traces) != len(rows):
            raise ValueError("Native request accounting incomplete")
        for row, trace in zip(rows, traces, strict=True):
            if row["status"] != trace["status"] or row["controller_reads"] != trace["controller_reads"]:
                raise ValueError("Actual request accounting differs")
        if (root / (seed + ".receipt")).read_bytes() != seed_bytes:
            raise ValueError("Original encrypted receipt changed")
        result = {"mode": mode, "cases": rows, "distinct_processes": len(pids), "loopback_servers": len(pids),
                  "intentional_SIGKILL_exits": sum(w["process"].exitcode == -9 for w in workers), "fresh_receipt_sessions": len(sessions) - 1,
                  "clean_receipt_worker_exits": sum(w["receipt"] and w["finished"] and w["process"].exitcode == 0 for w in workers),
                  "receipt_HTTP_attempts": len(rows), "controller_reads": sum(r["controller_reads"] for r in rows),
                  "campaign_controller_requests": len(f.responses), "orphan_entries_preserved": len(list(root.glob(".pending-*"))),
                  "source_ciphertext_and_four_histories_exact": True, "no_failed_response_metadata": True,
                  "same_binding_restarts": True, "create_only_recovery": True}
        from receipt_recovery_native_cases import qualify
        result["recovery_planning"] = await qualify(f, root, key, selection["context_id"], first["scope_sha256"])
    finally:
        clean = True
        for item in workers:
            try:
                await stop_one(item)
            except (ValueError, OSError, EOFError):
                clean = False
                if item["process"].is_alive():
                    item["process"].terminate()
                    await asyncio.to_thread(item["process"].join, 2)
        await asyncio.gather(*(client.aclose() for client in clients))
        f.close()
        if not clean:
            raise ValueError("Unexpected native process cleanup failure")
    return result


async def campaign(packet):
    api, m = packages(packet)
    import portable_controller_native as retained
    from operator_review_fixture import forbid_provider_helpers
    mounts = {line.split()[4]: line for line in Path("/proc/self/mountinfo").read_text().splitlines()}
    roots = ("/models", "/work", "/anchors", "/backups")
    if (os.getuid() != 10002 or len({mounts[p].split()[0] for p in roots}) != 4
            or any(mounts[p].split(" - ")[1].split()[0] != "ext4" for p in roots)
            or not os.statvfs("/models").f_flag & os.ST_RDONLY):
        raise ValueError("Four distinct ext4 volumes and kernel read-only packages required")
    before = retained.inventory(Path("/models"))
    with forbid_provider_helpers(api):
        modes = [await protocol(mode, api, m, packet) for mode in ("retirement", "rollback")]
    if any(n == "app.main" or n.startswith(("app.provider", "inference_engine")) for n in sys.modules):
        raise ValueError("Forbidden application startup")
    planning = [{"mode": item["mode"], **item.pop("recovery_planning")} for item in modes]
    report = {"schema": "native-receipt-fault-v1", "receipt_manifest_sha256": packet["receipt_manifest_sha256"],
              "controller_manifest_sha256": packet["approved_manifest_sha256"], "modes": modes, "filesystem": "ext4",
              "key_custody": "unassessed", "operator_appointments": "unassessed", **dict.fromkeys(TRUE, True),
              **dict.fromkeys(FALSE, False), "live_provider_requests": 0, "native_inference_calls": 0}
    report["read_only_package_inventory_exact"] = before == retained.inventory(Path("/models"))
    validate(report, packet["receipt_manifest_sha256"], packet["approved_manifest_sha256"])
    from receipt_recovery_native_cases import validate as validate_planning
    complete = {"schema": "native-receipt-recovery-planning-v1", "faults": report, "planning": planning, "production_activation": False}
    validate_planning(complete, packet["receipt_manifest_sha256"], packet["approved_manifest_sha256"])
    return complete


if __name__ == "__main__":
    packet = controller_inspector.strict(Path("/controller/operator-packet.json").read_bytes())
    if set(packet) != {"approved_manifest_sha256", "receipt_manifest_sha256", "production_activation"} or packet["production_activation"] is not False:
        raise ValueError("Closed public campaign pins required")
    if sys.argv[1:] == ["prepare"]:
        result = prepare(packet)
    elif sys.argv[1:] == ["run"]:
        result = asyncio.run(campaign(packet))
    else:
        raise ValueError("Closed native action required")
    print(json.dumps(result), flush=True)
