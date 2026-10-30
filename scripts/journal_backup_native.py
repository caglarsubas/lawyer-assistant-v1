"""Opt-in Linux copy-readiness qualification over invented encrypted histories."""

import asyncio
import json
import multiprocessing
import os
import sys
from dataclasses import asdict, replace
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent), "/backend"]
import receipt_fault_native as retained  # noqa: E402
from journal_backup_report import FALSE, STATES, TRUE, validate  # noqa: E402


async def protocol(mode):
    import operator_enrollment_evidence as e
    import private_inventory_receipts as receipts
    from journal_backup_fixture import Fixture, pins, service
    from journal_backup_readiness import DECISIONS, FLAGS
    from journal_backup_worker import worker

    root = Path("/work") / ("copy-readiness-" + mode)
    root.mkdir(mode=0o700)
    f = Fixture(root)
    source_view = await f.planner.dispatch(f.scope(), "inventory")
    original_plan = await f.planner.dispatch(f.scope(), "prepare", plan_id="2" * 32,
        expected_snapshot_sha256=source_view["snapshot_sha256"], selected_entry_ids=[r["entry_id"] for r in source_view["inventory"]["entries"]])
    source_review = await f.planner.dispatch(f.scope("reviewer"), "decide", **f.refs(original_plan), decision="accept",
        reason_code="exact_inventory_and_actions_checked")
    if source_review["state"] != "reviewed_for_metadata_planning":
        e.reject()
    readiness = service(f)
    def files(root):
        return {p.name: (p.read_bytes(), p.stat().st_nlink, p.stat().st_mode, p.stat().st_uid) for p in root.iterdir()}
    original = files(f.source), files(f.journal)
    if mode == "existing_copy":
        for path in f.journal.iterdir():
            e.retain(readiness.candidate.root / path.name, path.read_bytes())
    anchor = Path("/anchors") / mode
    anchor.mkdir(mode=0o700)
    for name, key in (("source", f.source_store.key), ("journal", f.journal_store.key),
                      ("reviews", readiness.reviews.planner.journal.key), ("auth", f.auth_key)):
        e.retain(anchor / (name + ".key"), key)
    clock_path = root / "clock.json"
    e.retain(clock_path, e.encode({"now": f.now}))
    context, processes, rows, pids = multiprocessing.get_context("spawn"), [], [], set()
    async def request(operation, body=None, role="preparer", *, selected=None):
        selected = selected or readiness
        descriptor = {"production_activation": False, "profile": str(f.profile), "firm_id": "invented-firm",
            "bindings": dict(f.authority.bindings), "auth_key": str(anchor / "auth.key"), "clock_path": str(clock_path),
            "source_root": str(f.source), "journal_root": str(f.journal), "source_key": str(anchor / "source.key"),
            "journal_key": str(anchor / "journal.key"), "source_pins": asdict(f.pins), "journal_binding": asdict(readiness.source.binding),
            "headers": {k.decode(): v.decode() for k, v in f.scope(role)["headers"]},
            "candidate_root": str(selected.candidate.root), "candidate_pins": asdict(selected.candidate_pins),
            "reviews_root": str(selected.reviews.planner.journal.root), "reviews_key": str(anchor / "reviews.key"),
            "reviews_binding": asdict(selected.reviews.binding)}
        path = root / ("worker-" + str(len(processes)) + ".json")
        e.retain(path, e.encode(descriptor))
        parent, child = context.Pipe()
        process = context.Process(target=worker, args=(str(path), child))
        before = files(f.source), files(f.journal), files(selected.candidate.root)
        audit_before = files(selected.reviews.planner.journal.root)
        processes.append((process, parent))
        process.start()
        child.close()
        if not await asyncio.to_thread(parent.poll, 5):
            e.reject()
        if parent.recv() != {"pid": process.pid, "package_verified_before_auth": True, "actual_app_auth": True} or process.pid in pids:
            e.reject()
        pids.add(process.pid)
        parent.send({"operation": operation, "body": body or {}})
        if not await asyncio.to_thread(parent.poll, 25):
            e.reject()
        reply = parent.recv()
        if set(reply) != {"pid", "operation", "response"} or reply["pid"] != process.pid or reply["operation"] != operation:
            e.reject()
        value = reply["response"]
        parent.send({"stop": True})
        if not await asyncio.to_thread(parent.poll, 5) or parent.recv() != {"pid": process.pid, "completed": 1, "clean_exit": True, "controller_reads": 0}:
            e.reject()
        await asyncio.to_thread(process.join, 4)
        if process.is_alive() or process.exitcode != 0:
            e.reject()
        parent.close()
        if (before != (files(f.source), files(f.journal), files(selected.candidate.root))
                or any(files(selected.reviews.planner.journal.root).get(k) != v for k, v in audit_before.items())
                or operation in {"observe", "inspect"} and audit_before != files(selected.reviews.planner.journal.root)
                or any(value[k] is not False for k in FLAGS)):
            e.reject()
        rows.append({"id": f"B{len(rows) + 1:02}", "state": value["state"]})
        return value
    def prepare_body(ident, observed):
        return {"plan_id": ident, "expected_snapshot_sha256": observed["snapshot_sha256"]}
    def decision_body(plan):
        return {**f.refs(plan), "decision": "accept", "reason_code": DECISIONS["accept"][0]}
    def inspect_body(plan, review):
        return {**f.refs(plan), "decision_ciphertext_sha256": review["decision_ciphertext_sha256"]}
    try:
        observed = await request("observe")
        expected = "empty_destination" if mode == "empty_target" else "exact_ciphertext_copy"
        if observed["observation"]["comparison"] != expected:
            e.reject()
        a = await request("prepare", prepare_body("8" * 32, observed))
        await request("decide", decision_body(a), "preparer")
        ar = await request("decide", decision_body(a), "reviewer")
        await request("inspect", inspect_body(a, ar))
        e.retain(readiness.candidate.root / (".pending-" + "e" * 32), receipts.MAGIC + os.urandom(48))
        await request("inspect", inspect_body(a, ar))
        await request("prepare", prepare_body("9" * 32, observed))
        renewed_root = root / "independently-pinned-candidate"
        renewed_root.mkdir(mode=0o700)
        for path in f.journal.iterdir():
            e.retain(renewed_root / path.name, path.read_bytes())
        candidate = receipts.ReceiptStore(root=renewed_root, context_id=readiness.candidate.context_id,
            scope_sha256=readiness.candidate.scope_sha256, key=readiness.candidate.key)
        renewed = replace(readiness, candidate=candidate, candidate_pins=pins(f, candidate))
        await request("inspect", inspect_body(a, ar), selected=renewed)
        observed_b = await request("observe", selected=renewed)
        if observed_b["observation"]["comparison"] != "exact_ciphertext_copy":
            e.reject()
        b = await request("prepare", prepare_body("a" * 32, observed_b), selected=renewed)
        br = await request("decide", decision_body(b), "reviewer", selected=renewed)
        await request("inspect", inspect_body(b, br), selected=renewed)
        await request("decide", decision_body(b), "reviewer", selected=renewed)
        f.now += 301
        clock_path.write_bytes(e.encode({"now": f.now}))
        await request("inspect", inspect_body(b, br), selected=renewed)
        c = await request("prepare", prepare_body("b" * 32, observed_b), selected=renewed)
        cr = await request("decide", decision_body(c), "reviewer", selected=renewed)
        await request("inspect", inspect_body(c, br), selected=renewed)
        f.revoke("reviewer")
        await request("inspect", inspect_body(c, cr), "reviewer", selected=renewed)
        await request("inspect", inspect_body(c, cr), selected=renewed)
        if rows != [{"id": f"B{i:02}", "state": s} for i, s in enumerate(STATES, 1)] or original != (files(f.source), files(f.journal)):
            e.reject()
        return {"mode": mode, "cases": rows, "fresh_worker_processes": len(pids), "source_preparation_operations": 3,
                "readiness_API_attempts": len(rows), "controller_reads": 0, **dict.fromkeys(TRUE, True), **dict.fromkeys(FALSE, False)}
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
        modes = [await protocol(mode) for mode in ("empty_target", "existing_copy")]
    if any(n == "app.main" or n.startswith(("app.provider", "inference_engine")) for n in sys.modules):
        raise ValueError("Forbidden startup")
    value = {"schema": "native-journal-backup-readiness-v1", "receipt_manifest_sha256": packet["receipt_manifest_sha256"],
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
