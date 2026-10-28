"""Frozen real HTTP receipt protocols on fresh local Docker volumes only."""

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
from receipt_http_report import CASES, FALSE, TRUE, validate  # noqa: E402


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
    from receipt_http_worker import worker as receipt_worker

    name = "C01_retirement_ordered" if mode == "retirement" else "C09_rollback_ordered"
    f = fixture.Fixture(name, Path("/models"), Path("/work"), Path("/anchors"), api, backups=Path("/backups"))
    context = multiprocessing.get_context("spawn")
    workers, clients, pids, traces, rows = [], [], set(), [], []
    async def start(target, descriptor, is_receipt=False):
        parent, child = context.Pipe(duplex=False)
        stop = context.Event()
        process = context.Process(target=target, args=(str(descriptor), child, stop))
        process.start()
        child.close()
        item = {"process": process, "stop": stop, "pipe": parent, "receipt": is_receipt, "finished": False}
        workers.append(item)
        if not await asyncio.to_thread(parent.poll, 5):
            raise ValueError("Native worker startup budget exceeded")
        ready = parent.recv()
        required = {"pid", "port", "actual_auth"} | ({"package_verified_before_auth"} if is_receipt else set())
        if (set(ready) != required or ready["pid"] != process.pid or ready["pid"] in pids
                or ready["actual_auth"] is not True or (is_receipt and ready["package_verified_before_auth"] is not True)):
            raise ValueError("Distinct verified authenticated workers required")
        pids.add(process.pid)
        client = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=0), trust_env=False, follow_redirects=False,
                                   base_url="http://127.0.0.1:" + str(ready["port"]), timeout=30)
        clients.append(client)
        item.update(port=ready["port"], client=client)
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
            if (set(value) != {"pid", "HTTP_requests", "controller_reads", "trace", "clean_exit"}
                    or value["pid"] != item["process"].pid or value["clean_exit"] is not True
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
        receipt = await start(receipt_worker, descriptor_path, True)
        record, body, ciphertext = "1" * 32, None, None
        async def request(ident, action="reobserve", value=None, headers=None, suffix=""):
            nonlocal body, ciphertext
            before = f.four_histories()
            response = await receipt["client"].post(m.adapter.PREFIX + action + suffix,
                content=e.encode(body if value is None else value), headers=f.headers("preparer") if headers is None else headers)
            data = response.json()
            expected = next(x for x in CASES if x[0] == ident)
            outcome = data["comparison"]["outcome"] if data.get("comparison") else None
            if (response.status_code != expected[1] or data["state"] != expected[2] or outcome != expected[3]
                    or response.headers.get("cache-control") != "no-store" or f.four_histories() != before
                    or source_path.read_bytes() != source):
                raise ValueError("Frozen HTTP response or evidence differed: " + ident)
            if response.status_code != 200 and data.get("retained") is not None:
                raise ValueError("Rejected request returned retained metadata")
            path = root / (record + ".receipt")
            if ident == "H02_retain":
                ciphertext = path.read_bytes()
                body = {"record_id": record, "expected_record_sha256": data["record_sha256"]}
            if ciphertext is not None and (path.read_bytes() != ciphertext or list(root.iterdir()) != [path]):
                raise ValueError("Read or rejected request changed encrypted history")
            rows.append({"id": ident, "status": response.status_code, "state": data["state"], "outcome": outcome})
            return data
        ready = await request("H01_readiness", "readiness", {})
        if ready["operator_appointments"] != "unassessed" or ready["key_custody"] != "unassessed":
            raise ValueError("Fixture readiness granted real authority")
        capture = {"source_id": "2" * 32, "expected_source_sha256": e.sha(source), "record_id": record}
        await request("H02_retain", "retain", capture)
        await request("H03_reobserve")
        await request("H04_cookie", headers={**f.headers("preparer"), "cookie": "la_session=invalid-disposable"})
        await request("H05_origin", headers={**f.headers("preparer"), "origin": "https://unapproved.invalid"})
        await request("H06_csrf", headers={k: v for k, v in f.headers("preparer").items() if k != "x-csrf-token"})
        await request("H07_role", headers=f.headers("other"))
        await request("H08_query", suffix="?unapproved=1")
        await request("H09_source_pin", "retain", {**capture, "expected_source_sha256": "0" * 64, "record_id": "3" * 32})
        await request("H10_record_pin", value={**body, "expected_record_sha256": "0" * 64})
        await stop_one(receipt)
        receipt = await start(receipt_worker, descriptor_path, True)
        await request("H11_restart")
        for ident in ("H12_destination", "H13_window"):
            view = (await f.observe_joint(a)).json()
            if (await f.apply_joint(a, view)).status_code != 200:
                raise ValueError("Explicit fixture repair rejected")
            await request(ident)
        if mode == "retirement":
            f.advance(301)
        else:
            await f.withdrawal(a, b)
        await request("H14_source_changed")
        f.revoke("preparer")
        await request("H15_revocation")
        await stop_one(receipt)
        if len(traces) != len(rows):
            raise ValueError("Actual HTTP accounting differs")
        for row, trace in zip(rows, traces, strict=True):
            if row["status"] != trace["status"]:
                raise ValueError("Actual status accounting differs")
            row["controller_reads"] = trace["controller_reads"]
        result = {"mode": mode, "cases": rows, "distinct_processes": len(pids), "loopback_servers": len(pids),
                  "receipt_worker_restarts": 1, "receipt_HTTP_requests": len(traces),
                  "controller_reads": sum(x["controller_reads"] for x in traces), "campaign_controller_requests": len(f.responses),
                  "source_and_ciphertext_exact": True, "four_histories_exact_across_reads": True,
                  "negative_requests_no_controller_io": all(r["controller_reads"] == 0 for r in rows if r["status"] != 200)}
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
            raise ValueError("Native campaign process cleanup failed")
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
        raise ValueError("Four distinct disposable ext4 volumes and read-only packages required")
    before = retained.inventory(Path("/models"))
    with forbid_provider_helpers(api):
        modes = [await protocol(mode, api, m, packet) for mode in ("retirement", "rollback")]
    if any(n == "app.main" or n.startswith(("app.provider", "inference_engine")) for n in sys.modules):
        raise ValueError("Forbidden application startup")
    report = {"schema": "native-receipt-http-v1", "receipt_manifest_sha256": packet["receipt_manifest_sha256"],
              "controller_manifest_sha256": packet["approved_manifest_sha256"], "modes": modes, "filesystem": "ext4",
              "key_custody": "unassessed", "operator_appointments": "unassessed", **dict.fromkeys(TRUE, True),
              **dict.fromkeys(FALSE, False), "live_provider_requests": 0, "native_inference_calls": 0}
    report["read_only_package_inventory_exact"] = before == retained.inventory(Path("/models"))
    validate(report, packet["receipt_manifest_sha256"], packet["approved_manifest_sha256"])
    return report


if __name__ == "__main__":
    packet = controller_inspector.strict(Path("/controller/operator-packet.json").read_bytes())
    if set(packet) != {"approved_manifest_sha256", "receipt_manifest_sha256", "production_activation"} or packet["production_activation"] is not False:
        raise ValueError("Closed public campaign pins required")
    action = sys.argv[1:]
    if action == ["prepare"]:
        result = prepare(packet)
    elif action == ["run"]:
        result = asyncio.run(campaign(packet))
    else:
        raise ValueError("Closed native campaign action required")
    print(json.dumps(result), flush=True)
