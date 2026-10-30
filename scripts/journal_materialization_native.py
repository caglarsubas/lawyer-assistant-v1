"""Opt-in ext4 materialization and read-only verification on disposable volumes."""

import asyncio
import json
import multiprocessing
import os
import signal
import sys
from collections import Counter
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent), "/backend"]
import receipt_fault_native as retained  # noqa: E402
from journal_materialization_report import FALSE, INTERRUPTED, ROUND_TRIP, TRUE, validate  # noqa: E402


async def protocol(name):
    import operator_enrollment_evidence as e
    import private_inventory_receipts as receipts
    import receipt_recovery_inventory as physical
    from journal_backup_fixture import Fixture
    from journal_materialization import DECISIONS, FLAGS, OP_REFS, CopyOrigin
    from journal_materialization_fixture import describe, make
    from journal_materialization_worker import worker

    root = Path("/work") / ("materialization-" + name)
    root.mkdir(mode=0o700)
    f = Fixture(root)
    source = await f.planner.dispatch(f.scope(), "inventory")
    original_plan = await f.planner.dispatch(f.scope(), "prepare", plan_id="2" * 32,
        expected_snapshot_sha256=source["snapshot_sha256"], selected_entry_ids=[r["entry_id"] for r in source["inventory"]["entries"]])
    original_review = await f.planner.dispatch(f.scope("reviewer"), "decide", **f.refs(original_plan),
        decision="accept", reason_code="exact_inventory_and_actions_checked")
    if original_review["state"] != "reviewed_for_metadata_planning":
        e.reject()
    service = make(f, candidate_root=Path("/backups") / name)
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
    processes, pids, rows, attempts = [], set(), [], Counter()
    acknowledged, killed = 0, 0
    def files(root):
        return {p.name: (p.read_bytes(), physical.identity(p.stat())) for p in root.iterdir()}
    originals = files(f.source), files(f.journal)
    async def request(op, body=None, role="preparer", *, selected=None, interrupt=False):
        nonlocal acknowledged, killed
        selected = selected or service
        payload = {"production_activation": False, "profile": str(f.profile), "firm_id": "invented-firm",
                   "bindings": dict(f.authority.bindings), "auth_key": str(auth_key), "clock_path": str(clock),
                   "service": describe(selected, key_path), "headers": {k.decode(): v.decode() for k, v in f.scope(role)["headers"]}}
        path = root / ("worker-" + str(len(processes)) + ".json")
        e.retain(path, e.encode(payload))
        parent, child = context.Pipe()
        process = context.Process(target=worker, args=(str(path), child, interrupt))
        before = files(selected.planner.source.root), files(selected.planner.journal.root), files(selected.readiness.candidate.root)
        histories = [(r, files(r)) for r in (selected.controls.planner.journal.root, selected.readiness.reviews.planner.journal.root)]
        if selected.origin:
            old = selected.origin.service
            histories += [(r, files(r)) for r in (old.controls.planner.journal.root, old.readiness.reviews.planner.journal.root)]
        processes.append((process, parent))
        process.start()
        child.close()
        if not await asyncio.to_thread(parent.poll, 5):
            e.reject()
        if parent.recv() != {"pid": process.pid, "package_verified_before_auth": True, "actual_app_auth": True} or process.pid in pids:
            e.reject()
        pids.add(process.pid)
        attempts[op] += 1
        parent.send({"operation": op, "body": body or {}})
        if not await asyncio.to_thread(parent.poll, 25):
            e.reject()
        reply = parent.recv()
        if interrupt:
            if reply != {"pid": process.pid, "checkpoint": "target_copy_1"}:
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
            killed += 1
            value = {"state": "connection_closed"}
        else:
            if set(reply) != {"pid", "operation", "response"} or reply["pid"] != process.pid or reply["operation"] != op:
                e.reject()
            value = reply["response"]
            if not await asyncio.to_thread(parent.poll, 5) or parent.recv() != {"pid": process.pid, "completed": 1, "clean_exit": True, "controller_reads": 0}:
                e.reject()
            await asyncio.to_thread(process.join, 4)
            if process.is_alive() or process.exitcode != 0 or any(value[k] is not False for k in FLAGS if k in value):
                e.reject()
            acknowledged += 1
        parent.close()
        if ((files(selected.planner.source.root), files(selected.planner.journal.root)) != before[:2]
                or op != "materialize" and files(selected.readiness.candidate.root) != before[2]
                or any(any(files(r).get(k) != v for k, v in history.items()) for r, history in histories)
                or op == "verify" and any(files(r) != history for r, history in histories)):
            e.reject()
        rows.append({"id": f"M{len(rows) + 1:02}", "state": value["state"]})
        return value
    def refs(value):
        return {k: value[k] for k in OP_REFS}
    def decide_body(plan):
        return {**refs(plan), "decision": "authorize", "reason_code": DECISIONS["authorize"]}
    def materialize_body(plan, decision):
        return {**refs(plan), "decision_ciphertext_sha256": decision["decision_ciphertext_sha256"]}
    def verify_body(plan, decision, completion):
        return {**materialize_body(plan, decision), **{k: completion[k] for k in
                ("intent_ciphertext_sha256", "intent_sha256", "completion_ciphertext_sha256")}}
    async def prepare(selected, ident):
        observed = await request("ready_observe", selected=selected)
        ready_plan = await request("ready_prepare", {"plan_id": "7" * 32, "expected_snapshot_sha256": observed["snapshot_sha256"]}, selected=selected)
        ready_refs = f.refs(ready_plan)
        review = await request("ready_decide", {**ready_refs, "decision": "accept", "reason_code": "exact_copy_context_checked"}, "reviewer", selected=selected)
        plan = await request("copy_prepare", {"operation_id": ident, "expected_snapshot_sha256": observed["snapshot_sha256"],
            "readiness_refs": {**ready_refs, "decision_ciphertext_sha256": review["decision_ciphertext_sha256"]}}, selected=selected)
        return plan, review
    try:
        plan, readiness = await prepare(service, "8" * 32)
        await request("materialize", materialize_body(plan, readiness))
        await request("copy_decide", decide_body(plan))
        decision = await request("copy_decide", decide_body(plan), "reviewer")
        if name == "interrupted_copy":
            await request("materialize", materialize_body(plan, decision), interrupt=True)
            missing = {**materialize_body(plan, decision), "intent_ciphertext_sha256": None, "intent_sha256": None,
                       "completion_ciphertext_sha256": None}
            before = files(service.controls.planner.journal.root), files(service.readiness.candidate.root)
            if len(before[0]) != 3 or len(before[1]) != 1:
                e.reject()
            await request("verify", missing)
            await request("materialize", materialize_body(plan, decision))
            await request("verify", missing, "other")
            f.revoke("reviewer")
            await request("verify", missing)
            if (files(service.controls.planner.journal.root), files(service.readiness.candidate.root)) != before:
                e.reject()
        else:
            completion = await request("materialize", materialize_body(plan, decision))
            exact = verify_body(plan, decision, completion)
            await request("verify", exact)
            await request("materialize", materialize_body(plan, decision))
            restored = make(f, "restore", source=service.readiness.candidate, origin=CopyOrigin(service=service, **exact))
            rp, rr = await prepare(restored, "9" * 32)
            await request("materialize", materialize_body(rp, decision), selected=restored)
            await request("copy_decide", decide_body(rp), selected=restored)
            rd = await request("copy_decide", decide_body(rp), "reviewer", selected=restored)
            rc = await request("materialize", materialize_body(rp, rd), selected=restored)
            rexact = verify_body(rp, rd, rc)
            await request("verify", rexact, selected=restored)
            await request("verify", exact)
            e.retain(restored.readiness.candidate.root / (".pending-" + "e" * 32), receipts.MAGIC + os.urandom(48))
            await request("verify", rexact, selected=restored)
            await request("verify", exact)
            f.now += 301
            clock.write_bytes(e.encode({"now": f.now}))
            await request("verify", exact)
            f.revoke("preparer")
            await request("verify", exact)
        states = ROUND_TRIP if name == "round_trip" else INTERRUPTED
        if rows != [{"id": f"M{i:02}", "state": s} for i, s in enumerate(states, 1)] or originals != (files(f.source), files(f.journal)):
            e.reject()
        target = restored.readiness.candidate if name == "round_trip" else service.readiness.candidate
        return {"name": name, "cases": rows, "processes": len(pids), "intentional_SIGKILL_exits": killed,
                "clean_exits": len(pids) - killed, "acknowledged_responses": acknowledged, "operation_attempts": dict(attempts),
                "source_preparation_operations": 3, "controller_reads": 0, "target_entries": len(files(target.root)),
                **dict.fromkeys(TRUE, True), **dict.fromkeys(FALSE, False)}
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
        protocols = [await protocol(name) for name in ("round_trip", "interrupted_copy")]
    if any(n == "app.main" or n.startswith(("app.provider", "inference_engine")) for n in sys.modules):
        raise ValueError("Forbidden startup")
    value = {"schema": "native-journal-materialization-v1", "receipt_manifest_sha256": packet["receipt_manifest_sha256"],
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
