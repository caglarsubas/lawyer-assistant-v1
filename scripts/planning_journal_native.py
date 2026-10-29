"""Frozen Linux journal process interruption/restart drill, with disposable identities."""

import asyncio
import json
import multiprocessing
import os
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent), "/backend"]
import receipt_fault_native as retained  # noqa: E402
from planning_journal_report import FALSE, STATES, TRUE, validate  # noqa: E402


async def protocol(mode, api, m, packet):
    import httpx
    import mode_recovery_fixture as fixture
    import operator_enrollment_evidence as e
    import private_inventory_receipts as receipts
    from joint_recovery_worker import worker as controller_worker
    from planning_journal_reconciliation import JournalBinding
    from planning_journal_worker import worker as journal_worker
    from receipt_provisioning_readiness import Pins, fingerprint
    from receipt_recovery_planning import DECISIONS

    f = fixture.Fixture("C01_retirement_ordered" if mode == "retirement" else "C09_rollback_ordered",
        Path("/models"), Path("/work"), Path("/anchors"), api, backups=Path("/backups"))
    context = multiprocessing.get_context("spawn")
    controllers, journals, pids, rows, attempts = [], [], set(), [], Counter()
    source_reads, acknowledged = 0, 0
    async def controller(node, restored=None):
        path = f.work / ("controller-" + str(node) + ".json")
        e.retain(path, e.encode(f.descriptor(node, restored=restored)))
        parent, child = context.Pipe()
        stop = context.Event()
        process = context.Process(target=controller_worker, args=(str(path), child, stop))
        process.start()
        child.close()
        item = {"process": process, "pipe": parent, "stop": stop, "finished": False}
        controllers.append(item)
        if not await asyncio.to_thread(parent.poll, 5):
            e.reject()
        ready = parent.recv()
        if ready != {"pid": process.pid, "port": ready.get("port"), "actual_auth": True}:
            e.reject()
        client = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=0), trust_env=False,
            follow_redirects=False, base_url="http://127.0.0.1:" + str(ready["port"]), timeout=30)
        item["client"] = client
        return client
    def files(root):
        return {p.name: (p.read_bytes(), p.stat().st_nlink, p.stat().st_mode, p.stat().st_uid) for p in root.iterdir()}
    async def start(journal, binding, key_path, role="preparer", point="none"):
        original = f.descriptor(0)
        descriptor = {k: original[k] for k in ("profile", "firm_id", "bindings", "auth_key", "production_activation")}
        descriptor.update(clock_path=str(clock_path), source_root=str(source_root), journal_root=str(journal.root),
            source_key=str(source_key_path), journal_key=str(key_path), source_pins=asdict(source_pins),
            journal_binding=asdict(binding), headers=f.headers(role))
        path = f.work / ("journal-worker-" + str(len(journals)) + ".json")
        e.retain(path, e.encode(descriptor))
        parent, child = context.Pipe()
        process = context.Process(target=journal_worker, args=(str(path), child, point))
        process.start()
        child.close()
        item = {"process": process, "pipe": parent, "completed": 0, "finished": False}
        journals.append(item)
        if not await asyncio.to_thread(parent.poll, 5):
            raise ValueError("Journal startup budget exceeded")
        if parent.recv() != {"pid": process.pid, "package_verified_before_auth": True, "actual_app_auth": True} or process.pid in pids:
            raise ValueError("Fresh verified journal process required")
        pids.add(process.pid)
        return item
    async def send(item, operation, body):
        attempts[operation] += 1
        item["pipe"].send({"operation": operation, "body": body})
    async def receive(item, operation):
        nonlocal acknowledged
        if not await asyncio.to_thread(item["pipe"].poll, 25):
            raise ValueError("Journal operation budget exceeded")
        value = item["pipe"].recv()
        if set(value) != {"pid", "operation", "response"} or value["pid"] != item["process"].pid or value["operation"] != operation:
            raise ValueError("Exact journal response required")
        item["completed"] += 1
        acknowledged += 1
        return value["response"]
    async def request(item, operation, body):
        await send(item, operation, body)
        return await receive(item, operation)
    async def stop(item):
        if item["finished"]:
            return
        item["pipe"].send({"stop": True})
        if not await asyncio.to_thread(item["pipe"].poll, 5):
            raise ValueError("Clean journal accounting missing")
        value = item["pipe"].recv()
        await asyncio.to_thread(item["process"].join, 4)
        if (value != {"pid": item["process"].pid, "completed": item["completed"], "clean_exit": True,
                "controller_reads": 0, "probe_fired": False} or item["process"].is_alive() or item["process"].exitcode != 0):
            raise ValueError("Clean journal process exit required")
        item["finished"] = True
        item["pipe"].close()
    def check(ident, value):
        if value["state"] != STATES[ident - 1]:
            raise ValueError("Frozen journal state differs: J" + str(ident))
        for key in ("authority_renewed", "record_adopted", "automatic_recovery", "native_execution_authorized"):
            if value[key] is not False:
                e.reject()
        if value.get("read_only") is True and (value["acknowledgement_recovered"] is not False or value["fresh_independent_review_required"] is not True):
            e.reject()
        if value["state"] in {"denied", "snapshot_conflict"} and any(value.get(k) is not None for k in ("journal", "plan", "review")):
            e.reject()
        rows.append({"id": f"J{ident:02}", "state": value["state"]})
    def preservation(before, journal, *, readonly=True):
        after = files(journal.root)
        if (files(source_root) != before[0] or f.four_histories() != history
                or any(after.get(k) != v for k, v in before[1].items()) or (readonly and after != before[1])):
            raise ValueError("Read/restart rewrote encrypted evidence or history")
    async def prepare(journal, binding, key_path, ident):
        item = await start(journal, binding, key_path)
        before = files(source_root), files(journal.root)
        observed = await request(item, "source_inventory", {})
        if observed["state"] != "observed_metadata":
            e.reject()
        body = {"plan_id": ident, "expected_snapshot_sha256": observed["snapshot_sha256"],
                "selected_entry_ids": [r["entry_id"] for r in observed["inventory"]["entries"]]}
        value = await request(item, "prepare", body)
        await stop(item)
        preservation(before, journal, readonly=False)
        if value["state"] != "pending_independent_review":
            e.reject()
        return {k: value[k] for k in ("plan_id", "plan_ciphertext_sha256", "plan_sha256")}, value
    async def reconcile(journal, binding, key_path, refs, role="preparer", direct=None, override=None):
        item = await start(journal, binding, key_path, role)
        before = files(source_root), files(journal.root)
        body = direct
        if body is None:
            observed = await request(item, "inventory", {})
            if observed["state"] != "observed_journal_metadata":
                e.reject()
            body = {**refs, "expected_source_snapshot_sha256": observed["source_snapshot_sha256"],
                    "expected_journal_snapshot_sha256": observed["journal_snapshot_sha256"]}
        body = {**body, **(override or {})}
        value = await request(item, "reconcile", body)
        await stop(item)
        preservation(before, journal)
        return value, body
    try:
        a, b = await asyncio.gather(controller(0), controller(1))
        async def restored(ident):
            return await controller(len(controllers), restored=ident)
        f.open_restored = restored
        await f.setup_joint(a, b)
        first = (await f.observe_joint(a)).json()
        snapshot = f.authority.snapshot(f.session_ids["preparer"], f.ids["preparer"], "preparer", now=f.now)
        actor = e.sha(e.encode(snapshot))
        async def authorized():
            f.authority.recheck(snapshot, now=f.now)
            return actor
        async def read(action, body):
            nonlocal source_reads
            response = await fixture.raw.Fixture.request(f, a, action, "preparer", body)
            source_reads += 1
            return response.status_code, response.content
        selection = {"context_id": e.sha(mode.encode())[:32], "change_id": f.change_id, "expected_context_sha256": first["context_sha256"]}
        reader = m.inventory.BoundReader(scope_sha256=first["scope_sha256"], authorize=authorized, read=read)
        raw = e.encode(await m.inventory.collect({selection["context_id"]: reader}, [selection], actor_sha256=actor))
        source_root = f.work / "source-receipts"
        source_root.mkdir(mode=0o700)
        source_key = os.urandom(32)
        source_key_path = f.base.anchors / "journal-source.key"
        e.retain(source_key_path, source_key)
        source = m.receipts.ReceiptStore(root=source_root, context_id=selection["context_id"], scope_sha256=first["scope_sha256"], key=source_key)
        captured = await m.receipts.retain(raw, e.sha(raw), selection, source, reader, actor_sha256=actor, record_id="1" * 32)
        if captured["state"] != "retained":
            e.reject()
        source_pins = Pins(context_id=source.context_id, scope_sha256=source.scope_sha256, key_fingerprint=fingerprint(source_key),
            store_identity=source.identity, profile_id=f.authority.profile_id, profile_sha256=f.authority.marker_sha)
        clock_path = f.work / "journal-clock.json"
        e.retain(clock_path, e.encode({"now": f.now}))
        history, original_source = f.four_histories(), files(source_root)
        for control in controllers:
            control["stop"].set()
            await asyncio.to_thread(control["process"].join, 4)
            if control["process"].is_alive() or control["process"].exitcode != 0:
                e.reject()
            control["finished"] = True
            control["pipe"].close()
            await control["client"].aclose()
        for kind in ("plan", "decision"):
            for point in ("before_link", "after_link", "after_directory_sync"):
                root = f.work / (kind + "-" + point)
                root.mkdir(mode=0o700)
                key_path = f.base.anchors / (kind + "-" + point + ".key")
                key = os.urandom(32)
                e.retain(key_path, key)
                journal = receipts.ReceiptStore(root=root, context_id=source.context_id, scope_sha256=source.scope_sha256, key=key)
                pins = Pins(context_id=source.context_id, scope_sha256=source.scope_sha256, key_fingerprint=fingerprint(key),
                    store_identity=journal.identity, profile_id=f.authority.profile_id, profile_sha256=f.authority.marker_sha)
                binding = JournalBinding(pins=pins, source_pins_sha256=e.sha(e.encode(asdict(source_pins))),
                    preparer_id=f.ids["preparer"], reviewer_id=f.ids["reviewer"])
                ident = "2" * 32
                refs = {"plan_id": ident, "plan_ciphertext_sha256": None, "plan_sha256": None}
                if kind == "decision":
                    refs, _ = await prepare(journal, binding, key_path, ident)
                item = await start(journal, binding, key_path, "preparer" if kind == "plan" else "reviewer", point)
                if kind == "plan":
                    observed = await request(item, "source_inventory", {})
                    body = {"plan_id": ident, "expected_snapshot_sha256": observed["snapshot_sha256"],
                            "selected_entry_ids": [r["entry_id"] for r in observed["inventory"]["entries"]]}
                else:
                    body = {**refs, "decision": "accept", "reason_code": DECISIONS["accept"][0]}
                before = files(source_root), files(root)
                await send(item, "prepare" if kind == "plan" else "decide", body)
                if not await asyncio.to_thread(item["pipe"].poll, 5) or item["pipe"].recv() != {"pid": item["process"].pid, "checkpoint": point, "controller_reads": 0}:
                    raise ValueError("Actual publication boundary required")
                at_point = files(root)
                pending = [v for k, v in at_point.items() if k.startswith(".pending-")]
                new_records = [v for k, v in at_point.items() if k not in before[1] and k.endswith(".receipt")]
                if (len(pending) != (0 if point == "after_directory_sync" else 1)
                        or len(new_records) != (0 if point == "before_link" else 1)
                        or (point == "after_link" and (new_records[0][0] != pending[0][0] or new_records[0][1] != 2 or pending[0][1] != 2))
                        or any(at_point.get(k) != v for k, v in before[1].items())):
                    raise ValueError("Interrupted publication topology differs")
                item["process"].kill()
                await asyncio.to_thread(item["process"].join, 3)
                if item["process"].is_alive() or item["process"].exitcode != -9 or files(root) != at_point:
                    e.reject()
                if not await asyncio.to_thread(item["pipe"].poll, 2):
                    e.reject()
                try:
                    item["pipe"].recv()
                except EOFError:
                    pass
                else:
                    raise ValueError("Killed publication acknowledged a result")
                item["finished"] = True
                item["pipe"].close()
                rows.append({"id": f"J{len(rows) + 1:02}", "state": "connection_closed"})
                value, last_body = await reconcile(journal, binding, key_path, refs)
                check(len(rows) + 1, value)
        retained_journal = files(journal.root)
        value, old_body = await reconcile(journal, binding, key_path, refs)
        check(13, value)
        e.retain(journal.root / (".pending-" + "3" * 32), b"unfinished")
        value, _ = await reconcile(journal, binding, key_path, refs, override={"expected_journal_snapshot_sha256": old_body["expected_journal_snapshot_sha256"]})
        check(14, value)
        e.retain(source_root / (".pending-" + "4" * 32), receipts.MAGIC + os.urandom(48))
        value, last_body = await reconcile(journal, binding, key_path, refs)
        check(15, value)
        f.revoke("reviewer")
        value, _ = await reconcile(journal, binding, key_path, refs, "reviewer", direct=last_body)
        check(16, value)
        value, _ = await reconcile(journal, binding, key_path, refs)
        check(17, value)
        f.login("reviewer")
        clock_path.write_bytes(e.encode({"now": f.now + 301}))
        value, _ = await reconcile(journal, binding, key_path, refs)
        check(18, value)
        fresh, value = await prepare(journal, binding, key_path, "5" * 32)
        check(19, value)
        item = await start(journal, binding, key_path, "reviewer")
        before = files(source_root), files(journal.root)
        body = {**fresh, "decision": "accept", "reason_code": DECISIONS["accept"][0]}
        value = await request(item, "decide", body)
        check(20, value)
        await stop(item)
        preservation(before, journal, readonly=False)
        value, _ = await reconcile(journal, binding, key_path, fresh)
        check(21, value)
        item = await start(journal, binding, key_path, "reviewer")
        before = files(source_root), files(journal.root)
        value = await request(item, "decide", body)
        check(22, value)
        await stop(item)
        preservation(before, journal)
        if any(files(source_root).get(k) != v for k, v in original_source.items()) or any(files(journal.root).get(k) != v for k, v in retained_journal.items()):
            e.reject()
        report = {"mode": mode, "cases": rows, "operation_attempts": dict(attempts), "journal_processes": len(pids),
            "intentional_SIGKILL_exits": sum(w["process"].exitcode == -9 for w in journals),
            "clean_journal_exits": sum(w["process"].exitcode == 0 for w in journals), "fresh_readonly_processes": attempts["reconcile"],
            "journal_API_attempts": sum(attempts.values()), "acknowledged_responses": acknowledged, "journal_controller_reads": 0,
            "source_preparation_controller_reads": source_reads, "original_source_entries": len(original_source),
            "final_source_entries": len(files(source_root)), "final_journal_entries": len(files(journal.root)),
            **dict.fromkeys(TRUE, True), **dict.fromkeys(FALSE, False)}
    finally:
        for item in journals:
            if item["process"].is_alive():
                item["process"].terminate()
                await asyncio.to_thread(item["process"].join, 3)
        for item in controllers:
            if not item["finished"]:
                item["stop"].set()
                await asyncio.to_thread(item["process"].join, 4)
                if item["process"].is_alive():
                    item["process"].terminate()
                    await asyncio.to_thread(item["process"].join, 2)
                if "client" in item:
                    await item["client"].aclose()
        f.close()
    return report


async def campaign(packet):
    api, m = retained.packages(packet)
    import portable_controller_native as portable
    from operator_review_fixture import forbid_provider_helpers
    mounts = {line.split()[4]: line for line in Path("/proc/self/mountinfo").read_text().splitlines()}
    roots = ("/models", "/work", "/anchors", "/backups")
    if (os.getuid() != 10002 or len({mounts[p].split()[0] for p in roots}) != 4
            or any(mounts[p].split(" - ")[1].split()[0] != "ext4" for p in roots)
            or not os.statvfs("/models").f_flag & os.ST_RDONLY):
        raise ValueError("Four distinct ext4 volumes and read-only packages required")
    before = portable.inventory(Path("/models"))
    with forbid_provider_helpers(api):
        modes = [await protocol(mode, api, m, packet) for mode in ("retirement", "rollback")]
    if any(n == "app.main" or n.startswith(("app.provider", "inference_engine")) for n in sys.modules):
        raise ValueError("Forbidden startup")
    value = {"schema": "native-planning-journal-restart-v1", "receipt_manifest_sha256": packet["receipt_manifest_sha256"],
        "controller_manifest_sha256": packet["approved_manifest_sha256"], "modes": modes, "filesystem": "ext4",
        "read_only_packages_exact": before == portable.inventory(Path("/models")), "private_case_inputs": False,
        "live_provider_requests": 0, "native_inference_calls": 0, "key_custody": "unassessed", "operator_appointments": "unassessed",
        "power_loss_qualified": False, "production_activation": False}
    validate(value, packet["receipt_manifest_sha256"], packet["approved_manifest_sha256"])
    return value


if __name__ == "__main__":
    packet = retained.controller_inspector.strict(Path("/controller/operator-packet.json").read_bytes())
    if set(packet) != {"approved_manifest_sha256", "receipt_manifest_sha256", "production_activation"} or packet["production_activation"] is not False:
        raise ValueError("Closed public pins required")
    if sys.argv[1:] == ["prepare"]:
        output = retained.prepare(packet)
    elif sys.argv[1:] == ["run"]:
        output = asyncio.run(campaign(packet))
    else:
        raise ValueError("Closed native action required")
    print(json.dumps(output), flush=True)
