"""Fresh-process disposition journal interruptions on owned ext4 volumes only."""

import asyncio
import json
import multiprocessing
import os
import signal
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent), "/backend"]
import receipt_fault_native as retained  # noqa: E402
from disposition_journal_report import CASES, FALSE, TRUE, validate  # noqa: E402


async def protocol(name):
    import operator_enrollment_evidence as e
    import receipt_recovery_inventory as physical
    from copy_disposition_fixture import describe as describe_disposition
    from copy_disposition_fixture import make as make_disposition
    from copy_recovery_disposition import DECISIONS, REFS
    from disposition_journal_worker import worker
    from journal_backup_fixture import Fixture
    from journal_copy_reconciliation import CopyReconciler
    from journal_materialization import DECISIONS as COPY_DECISIONS
    from journal_materialization import OP_REFS
    from journal_materialization_fixture import describe, make

    root = Path("/work") / name
    root.mkdir(mode=0o700)
    f = Fixture(root)
    original = await f.planner.dispatch(f.scope(), "inventory")
    p = await f.planner.dispatch(f.scope(), "prepare", plan_id="2" * 32,
        expected_snapshot_sha256=original["snapshot_sha256"], selected_entry_ids=[r["entry_id"] for r in original["inventory"]["entries"]])
    accepted = await f.planner.dispatch(f.scope("reviewer"), "decide", **f.refs(p),
        decision="accept", reason_code="exact_inventory_and_actions_checked")
    if accepted["state"] != "reviewed_for_metadata_planning":
        e.reject()
    service = make(f, candidate_root=Path("/backups") / name)
    observed = await service.readiness.dispatch(f.scope(), "observe")
    rp = await service.readiness.dispatch(f.scope(), "prepare", plan_id="7" * 32, expected_snapshot_sha256=observed["snapshot_sha256"])
    rd = await service.readiness.dispatch(f.scope("reviewer"), "decide", **f.refs(rp),
        decision="accept", reason_code="exact_copy_context_checked")
    cp = await service.dispatch(f.scope(), "prepare", operation_id="8" * 32,
        expected_snapshot_sha256=observed["snapshot_sha256"], readiness_refs={**f.refs(rp), "decision_ciphertext_sha256": rd["decision_ciphertext_sha256"]})
    cd = await service.dispatch(f.scope("reviewer"), "decide", **{k: cp[k] for k in OP_REFS},
        decision="authorize", reason_code=COPY_DECISIONS["authorize"])
    if cd["state"] != "disposable_copy_authorized":
        e.reject()
    observation = await CopyReconciler(service=service).dispatch(f.scope(), "inventory")
    copy_refs = {**{k: cp[k] for k in OP_REFS}, "decision_ciphertext_sha256": cd["decision_ciphertext_sha256"],
        "intent_ciphertext_sha256": None, "completion_ciphertext_sha256": None, "expected_snapshot_sha256": observation["snapshot_sha256"]}
    disposition = make_disposition(service, root / "dispositions")
    anchor = Path("/anchors") / name
    anchor.mkdir(mode=0o700)
    keys = {}
    def key_path(key):
        if key not in keys:
            path = anchor / ("key-" + str(len(keys)))
            e.retain(path, key)
            keys[key] = path
        return keys[key]
    auth_key = key_path(f.auth_key)
    clock = root / "clock.json"
    e.retain(clock, e.encode({"now": f.now}))
    context = multiprocessing.get_context("spawn")
    processes, pids, rows = [], set(), []
    def files(path):
        return {p.name: (p.read_bytes(), physical.identity(p.stat())) for p in path.iterdir()}
    protected_roots = (f.planner.source.root, f.planner.journal.root, service.readiness.candidate.root,
                       service.readiness.reviews.planner.journal.root, service.controls.planner.journal.root)
    source_before = [files(r) for r in protected_roots]
    async def request(op, body=None, role="preparer", fault="none"):
        payload = {"production_activation": False, "profile": str(f.profile), "firm_id": "invented-firm",
            "bindings": dict(f.authority.bindings), "auth_key": str(auth_key), "clock_path": str(clock),
            "service": describe(service, key_path), "disposition": describe_disposition(disposition, key_path),
            "headers": {k.decode(): v.decode() for k, v in f.scope(role)["headers"]}}
        path = root / ("worker-" + str(len(processes)) + ".json")
        e.retain(path, e.encode(payload))
        parent, child = context.Pipe()
        process = context.Process(target=worker, args=(str(path), child, fault))
        before = files(disposition.planner.journal.root)
        processes.append((process, parent))
        process.start()
        child.close()
        if not await asyncio.to_thread(parent.poll, 5):
            e.reject()
        expected = {"pid": process.pid, "package_verified_before_auth": True, "actual_app_auth": True, "fault_point": fault}
        if parent.recv() != expected or process.pid in pids:
            e.reject()
        pids.add(process.pid)
        parent.send({"operation": op, "body": body or {}})
        if not await asyncio.to_thread(parent.poll, 25):
            e.reject()
        reply = parent.recv()
        if fault != "none":
            if reply != {"pid": process.pid, "checkpoint": fault}:
                e.reject()
            os.kill(process.pid, signal.SIGKILL)
            await asyncio.to_thread(process.join, 5)
            if process.is_alive() or process.exitcode != -signal.SIGKILL or not await asyncio.to_thread(parent.poll, 3):
                e.reject()
            try:
                parent.recv()
            except EOFError:
                pass
            else:
                e.reject()
            value = {"state": "connection_closed"}
        else:
            if set(reply) != {"pid", "operation", "response"} or reply["pid"] != process.pid or reply["operation"] != op:
                e.reject()
            value = reply["response"]
            if (not await asyncio.to_thread(parent.poll, 5)
                    or parent.recv() != {"pid": process.pid, "completed": 1, "clean_exit": True, "controller_reads": 0}):
                e.reject()
            await asyncio.to_thread(process.join, 4)
            if process.is_alive() or process.exitcode != 0:
                e.reject()
            if any(value[k] is not False for k in value if k in {"automatic_resume", "production_execution_authorized", "acknowledgement_recovered"}):
                e.reject()
        parent.close()
        after = files(disposition.planner.journal.root)
        if (source_before != [files(r) for r in protected_roots] or any(after.get(k) != v for k, v in before.items())
                or op.startswith("journal_") and after != before):
            e.reject()
        rows.append({"id": f"D{len(rows) + 1:02}", "state": value["state"]})
        return value
    async def inventory():
        return await request("journal_inventory")
    def selected(observed, plan=None, decision=None):
        return {"plan_id": "a" * 32, "plan_ciphertext_sha256": None, "plan_sha256": None,
            **({k: plan[k] for k in REFS} if plan else {}),
            "decision_ciphertext_sha256": decision and decision["decision_ciphertext_sha256"],
            "expected_snapshot_sha256": observed["snapshot_sha256"]}
    async def prepare(fault="none"):
        return await request("disposition_prepare", {"plan_id": "a" * 32, "copy_refs": copy_refs,
            "disposition": "retain_for_independent_assessment"}, fault=fault)
    try:
        if name.startswith("plan_"):
            await inventory()
            await prepare("before_link" if name.endswith("before_link") else "after_publish")
            observed = await inventory()
            exact = selected(observed)
            v = await request("journal_reconcile", exact)
            if v["plan"] is not None or v["review"] is not None:
                e.reject()
            await request("journal_reconcile", {**exact, "expected_snapshot_sha256": "f" * 64})
            await request("journal_inventory", role="other")
            f.revoke("preparer")
            await request("journal_inventory")
        else:
            plan = await prepare()
            decision_body = {**{k: plan[k] for k in REFS}, "decision": "accept", "reason_code": DECISIONS["accept"]}
            if name != "acknowledged_review":
                await inventory()
            review = await request("disposition_decide", decision_body, "reviewer",
                "none" if name == "acknowledged_review" else "before_link" if name.endswith("before_link") else "after_publish")
            observed = await inventory()
            exact = selected(observed, plan, review if name == "acknowledged_review" else None)
            v = await request("journal_reconcile", exact)
            if name != "acknowledged_review" and v["review"] is not None:
                e.reject()
            if name == "acknowledged_review":
                if v["review"]["reviewed_by"]["user_id"] != f.ids["reviewer"] or v["plan"]["prepared_by"]["user_id"] != f.ids["preparer"]:
                    e.reject()
                await request("journal_reconcile", {**exact, "decision_ciphertext_sha256": None})
            await request("journal_reconcile", {**exact, "plan_sha256": "f" * 64})
            if name == "acknowledged_review":
                await request("journal_reconcile", {**exact, "decision_ciphertext_sha256": "f" * 64})
            await request("journal_reconcile", {**exact, "expected_snapshot_sha256": "f" * 64})
            await request("journal_inventory", role="other")
            f.now += 301
            clock.write_bytes(e.encode({"now": f.now}))
            observed = await inventory()
            exact["expected_snapshot_sha256"] = observed["snapshot_sha256"]
            await request("journal_reconcile", exact)
            if name == "acknowledged_review":
                f.revoke("reviewer")
                await request("journal_reconcile", exact)
            f.revoke("preparer")
            await request("journal_inventory")
            await request("journal_reconcile", exact)
        if rows != [{"id": f"D{i:02}", "state": state} for i, state in enumerate(CASES[name], 1)]:
            e.reject()
        retained_files = files(disposition.planner.journal.root)
        killed = int(name != "acknowledged_review")
        return {"name": name, "cases": rows, "processes": len(pids), "intentional_SIGKILL_exits": killed,
            "clean_exits": len(pids) - killed, "acknowledged_responses": len(pids) - killed, "source_preparation_operations": 9,
            "retained_records": sum(n.endswith(".receipt") for n in retained_files),
            "retained_staging": sum(n.startswith(".pending-") for n in retained_files),
            **dict.fromkeys(TRUE, True), **dict.fromkeys(FALSE, False), "controller_reads": 0}
    finally:
        for process, pipe in processes:
            if process.is_alive():
                process.terminate()
                await asyncio.to_thread(process.join, 3)
            pipe.close()
        f.store.engine.dispose()


async def campaign(packet):
    api, _ = retained.packages(packet)
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
        protocols = [await protocol(name) for name in CASES]
    if any(n == "app.main" or n.startswith(("app.provider", "inference_engine")) for n in sys.modules):
        raise ValueError("Forbidden startup")
    value = {"schema": "native-disposition-journal-v1", "receipt_manifest_sha256": packet["receipt_manifest_sha256"],
        "controller_manifest_sha256": packet["approved_manifest_sha256"], "protocols": protocols, "filesystem": "ext4",
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
