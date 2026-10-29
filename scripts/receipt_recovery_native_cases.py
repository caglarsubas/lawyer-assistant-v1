"""Fresh frozen planning cases over actual SIGKILL leftovers; disposable accounts only."""

import os

import operator_enrollment_evidence as e
import private_inventory_receipts as receipts
from receipt_provisioning_readiness import Pins, fingerprint
from receipt_recovery_inventory import FLAGS
from receipt_recovery_planning import DECISIONS, RecoveryPlanner

CASES = [("I01_inventory", "observed_metadata", 0), ("I02_prepare", "pending_independent_review", 1),
         ("I03_self_review", "denied", 1), ("I04_wrong_snapshot", "conflict", 1),
         ("I05_independent_accept", "reviewed_for_metadata_planning", 2),
         ("I06_inspect", "reviewed_for_metadata_planning", 2), ("I07_duplicate_decision", "conflict", 2),
         ("I08_added_entry_stales", "stale_review_retained", 2), ("I09_fresh_plan", "pending_independent_review", 3),
         ("I10_changes_required", "changes_required", 4), ("I11_expiry", "stale_review_retained", 4),
         ("I12_revoked_reader", "denied", 4), ("I13_history", "stale_review_retained", 4)]


async def qualify(f, root, key, context_id, scope_sha256):
    source = receipts.ReceiptStore(root=root, context_id=context_id, scope_sha256=scope_sha256, key=key)
    journal_root = f.work / "recovery-plans"
    journal_root.mkdir(mode=0o700)
    journal = receipts.ReceiptStore(root=journal_root, context_id=context_id, scope_sha256=scope_sha256, key=os.urandom(32))
    pins = Pins(context_id=context_id, scope_sha256=scope_sha256, key_fingerprint=fingerprint(key), store_identity=source.identity,
                profile_id=f.authority.profile_id, profile_sha256=f.authority.marker_sha)
    planner = RecoveryPlanner(source, journal, pins, f.authority, preparer_id=f.ids["preparer"], reviewer_id=f.ids["reviewer"], clock=lambda: f.now)
    def files(path):
        return {p.name: (p.read_bytes(), p.stat().st_nlink, p.stat().st_mode, p.stat().st_uid) for p in path.iterdir()}
    original, histories, rows = files(root), f.four_histories(), []
    async def call(ident, operation, role="preparer", **body):
        before, old_journal = files(root), files(journal_root)
        scope = {"type": "http", "method": "POST", "path": "/api/v1/firm-admin/receipt-recovery/" + operation,
                 "headers": [(k.encode(), v.encode()) for k, v in f.headers(role).items()]}
        value = await planner.dispatch(scope, operation, **body)
        _, state, count = next(r for r in CASES if r[0] == ident)
        after = files(journal_root)
        if (value["state"] != state or any(value[k] is not False for k in FLAGS)
                or before != files(root) or any(files(root).get(k) != v for k, v in original.items())
                or f.four_histories() != histories or len(after) != count or any(after.get(k) != v for k, v in old_journal.items())
                or (state in {"denied", "conflict"} and any(k in value for k in ("plan", "review", "plan_ciphertext_sha256")))):
            raise ValueError("Frozen recovery planning outcome differs: " + ident)
        if any(b"prepared_by" in row[0] or b"reviewed_by" in row[0] for row in after.values()):
            raise ValueError("Planning metadata must remain encrypted")
        rows.append({"id": ident, "state": state, "journal_records": len(after)})
        return value
    observation = await call("I01_inventory", "inventory")
    if len(original) != 8 or observation["inventory"]["counts"] != {"single_link_record": 5, "unpublished_staging": 1, "linked_publication": 2}:
        raise ValueError("Actual forced-exit inventory differs")
    selected = [r["entry_id"] for r in observation["inventory"]["entries"]]
    prepare = {"plan_id": "a" * 32, "expected_snapshot_sha256": observation["snapshot_sha256"], "selected_entry_ids": selected}
    plan = await call("I02_prepare", "prepare", **prepare)
    refs = {k: plan[k] for k in ("plan_id", "plan_ciphertext_sha256", "plan_sha256")}
    review = {**refs, "decision": "accept", "reason_code": DECISIONS["accept"][0]}
    await call("I03_self_review", "decide", **review)
    await call("I04_wrong_snapshot", "prepare", **{**prepare, "plan_id": "b" * 32, "expected_snapshot_sha256": "0" * 64})
    decision = await call("I05_independent_accept", "decide", "reviewer", **review)
    inspect = {**refs, "decision_ciphertext_sha256": decision["decision_ciphertext_sha256"]}
    await call("I06_inspect", "inspect", **inspect)
    await call("I07_duplicate_decision", "decide", "reviewer", **review)
    # An explicit synthetic addition, separate from every read and plan operation.
    e.retain(root / (".pending-" + "8" * 32), receipts.MAGIC + os.urandom(48))
    await call("I08_added_entry_stales", "inspect", **inspect)
    fresh = await planner.dispatch({"type": "http", "method": "POST", "path": "/api/v1/firm-admin/receipt-recovery/inventory",
        "headers": [(k.encode(), v.encode()) for k, v in f.headers("preparer").items()]}, "inventory")
    if fresh["state"] != "observed_metadata" or len(fresh["inventory"]["entries"]) != 9:
        raise ValueError("Fresh bounded re-observation required")
    original_ids = set(selected)
    chosen = [r["entry_id"] for r in fresh["inventory"]["entries"] if r["entry_id"] not in original_ids]
    plan2 = await call("I09_fresh_plan", "prepare", plan_id="b" * 32, expected_snapshot_sha256=fresh["snapshot_sha256"], selected_entry_ids=chosen)
    refs2 = {k: plan2[k] for k in refs}
    decision2 = await call("I10_changes_required", "decide", "reviewer", **refs2, decision="changes_required", reason_code=DECISIONS["changes_required"][0])
    inspect2 = {**refs2, "decision_ciphertext_sha256": decision2["decision_ciphertext_sha256"]}
    f.now += 301
    await call("I11_expiry", "inspect", **inspect2)
    f.revoke("reviewer")
    await call("I12_revoked_reader", "inspect", "reviewer", **inspect2)
    await call("I13_history", "inspect", **inspect)
    return {"cases": rows, "original_entries_preserved": 8, "final_entries": 9, "journal_records": 4,
            "actual_app_auth_used": True, "independent_principals_used": True, "source_never_decrypted": True,
            "original_ciphertext_and_four_histories_exact": True, "prior_journal_ciphertext_exact": True,
            "controller_reads": 0, "fresh_inventory_reads": 1, "planning_API_attempts": 14,
            "automatic_repair": False, "execution_authorized": False}


def validate(value, receipt_manifest, controller_manifest):
    from receipt_fault_report import validate as faults
    if (not isinstance(value, dict) or set(value) != {"schema", "faults", "planning", "production_activation"}
            or value["schema"] != "native-receipt-recovery-planning-v1" or value["production_activation"] is not False):
        raise ValueError("Closed recovery campaign required")
    faults(value["faults"], receipt_manifest, controller_manifest)
    if not isinstance(value["planning"], list) or len(value["planning"]) != 2:
        raise ValueError("Both modes required")
    expected = {"original_entries_preserved": 8, "final_entries": 9, "journal_records": 4,
            "actual_app_auth_used": True, "independent_principals_used": True, "source_never_decrypted": True,
            "original_ciphertext_and_four_histories_exact": True, "prior_journal_ciphertext_exact": True,
            "controller_reads": 0, "fresh_inventory_reads": 1, "planning_API_attempts": 14,
            "automatic_repair": False, "execution_authorized": False}
    for item, mode in zip(value["planning"], ("retirement", "rollback"), strict=True):
        if (set(item) != {"mode", "cases", *expected} or item["mode"] != mode
                or any(type(item[k]) is not type(v) or item[k] != v for k, v in expected.items())
                or item["cases"] != [{"id": n, "state": state, "journal_records": count} for n, state, count in CASES]
                or any(type(row["journal_records"]) is not int for row in item["cases"])):
            raise ValueError("Frozen planning outcomes differ")
    return {"qualified_modes": 2, "frozen_HTTP_cases": 34, "frozen_planning_cases": 26, "production_activation": False}
