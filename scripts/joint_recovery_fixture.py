"""Frozen mixed-anchor fixtures; invented evidence and disposable people only."""

import asyncio
import shutil

import journal_recovery_fixture as retained
import operator_enrollment_evidence as e
import operator_review_fixture as raw
from joint_recovery import JointRecovery

CASES = [("J01_ordered_progress", 200), ("J02_lost_destination_reply_restart", 200),
         ("J03_lost_window_reply_restart", 200), ("J04_stale_progress", 409),
         ("J05_finish_first_refused", 409), ("J06_missing_window_admission", 400),
         ("J07_missing_destination_admission", 400), ("J08_borrowed_actor", 409),
         ("J09_withdrawal_between_repairs", 200), ("J10_expiry_between_repairs", 200),
         ("J11_revoked_review_between_repairs", 200), ("J12_competing_first_repair", 409),
         ("J13_copied_namespace", 400), ("J14_wrong_plan_and_finish", 409),
         ("J15_clock_rollback", 409), ("J16_unfinished_window", 409)]
POLICY = {"schema": "joint-recovery-qualification-v1", "cases": [dict(id=n, expected=s) for n, s in CASES],
          "native_attempts_per_case": 1, "min_distinct_worker_processes": 2, "max_events": 256,
          "max_proposal_seconds": 300, "max_page_rows": 8, "model_verification_seconds": 20,
          "independent_admissions_required": True, "destination_before_finish_anchor": True,
          "fresh_view_each_step": True, "actor_bound_plan": True, "single_anchor_per_step": True,
          "no_atomic_joint_transaction": True, "histories_immutable": True, "no_authority_renewal": True,
          "invented_mixed_anchor_restore": True, "disposable_accounts_only": True,
          "live_provider_requests": 0, "native_inference_calls": 0, "real_trust_enrolled": False,
          "runtime_installation": False, "production_activation": False}


class Fixture(retained.Fixture):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.services = [JointRecovery(v.legacy, v.destination, v.controls, v.changes, clock=lambda: self.now, checkpoint=self.newpoint) for v in self.services]

    def descriptor(self, node, *, restored=None):
        value = super().descriptor(node, restored=restored)
        n = int(self.name[1:3])
        value.update(fault={2: "joint_destination_anchor_complete", 3: "joint_window_anchor_complete"}.get(n) if node == 0 else None,
                     reader_fault=None, namespace_fault=None, window_fault="finished_retained" if node == 0 else None)
        return value

    async def request_joint(self, client, action, role="preparer", **pins):
        return await raw.Fixture.request(self, client, action, role, {"change_id": self.change_id, **pins})

    async def observe_joint(self, client):
        before = self.four_histories()
        result = await self.request_joint(client, "joint_observe")
        if before != self.four_histories():
            raise ValueError("Observation changed retained evidence")
        self.readonly_checks += 1
        return result

    async def apply_joint(self, client, view, *, target=None, role="preparer", wrong_plan=False):
        target = target or view["next_target"] or "window"
        before = self.four_histories()
        anchor = self.reader_controls.anchor.path if target == "destination" else self.change_controls.anchor.path
        result = await self.request_joint(client, "joint_apply", role, target=target,
            expected_plan_sha256="0" * 64 if wrong_plan else view["plan_sha256"], expected_view_sha256=view["view_sha256"])
        after = self.four_histories()
        if before.keys() != after.keys() or any(v != after[k] for k, v in before.items() if k != str(anchor)):
            raise ValueError("Joint repair rewrote history or manufactured admission")
        if before[str(anchor)] != after[str(anchor)]:
            if not after[str(anchor)].startswith(before[str(anchor)]) or len(after[str(anchor)].splitlines()) != len(before[str(anchor)].splitlines()) + 1:
                raise ValueError("Joint repair changed more than one exact anchor frame")
            self.repaired_heads.add((target, view[target + "_tip_sha256"]))
            self.repair_count = len(self.repaired_heads)
        if result.status_code == 200 and (result.json()["authority_renewed"] or result.json()["atomic_joint_write"]):
            raise ValueError("Joint repair renewed authority or claimed atomicity")
        return result

    async def setup_joint(self, a, b, *, unfinished=False):
        await self.setup_window(a, b)
        if (await self.change(a, "change_open", decision_sha256=self.change_decision["decision_sha256"])).status_code != 200:
            raise ValueError("Reviewed joint window rejected")
        if (await self.select_child(a, b)).status_code != 200:
            raise ValueError("Reviewed joint child rejected")
        await self.new_transition(a, b)
        if unfinished:
            return
        self.window_fault = "finished_retained"
        if (await self.finish(a)).status_code != 400:
            raise ValueError("Invented pending finish was not retained")
        # Model a mixed restoration of independent external anchors, not an
        # ordinary atomic failure or a production rollback-resistance claim.
        p = self.reader_controls.anchor.path
        p.write_bytes(b"\n".join(p.read_bytes().splitlines()[:-1]) + b"\n")

    async def run(self, clients):
        a, b = clients
        n = int(self.name[1:3])
        if n == 15:
            self.advance(1)
        await self.setup_joint(a, b, unfinished=n == 16)
        if n == 15:
            self.advance(-1)
        if n in {6, 7}:
            controls = self.change_controls if n == 6 else self.reader_controls
            record = e.decode(e.read(sorted(controls.root.glob("[0-9][0-9][0-9][0-9].json"))[-1]))
            (controls.anchor.path.parent / (record["head"] + ".intent.json")).unlink()
        if n == 13:
            root = self.legacy_controls.root
            held = root.with_name(root.name + "-original")
            root.rename(held)
            shutil.copytree(held, root)
        observed = await self.observe_joint(a)
        if n in {6, 7, 13, 15, 16}:
            return observed.status_code
        if observed.status_code != 200:
            raise ValueError("Joint observation rejected")
        view = observed.json()
        if set(view["pending"]) != {"window", "destination"} or view["next_target"] != "destination":
            raise ValueError("Exact joint pending state missing")
        if (await self.inventory(a)).status_code != 400:
            raise ValueError("Pending joint evidence allowed an ordinary read")
        if n == 5:
            return (await self.apply_joint(a, view, target="window")).status_code
        if n == 8:
            return (await self.apply_joint(b, view, role="reviewer")).status_code
        if n == 14:
            if (await self.apply_joint(a, view, wrong_plan=True)).status_code != 409:
                raise ValueError("Unpinned joint plan accepted")
            return (await self.request_joint(a, "joint_finish_observe", expected_plan_sha256=view["plan_sha256"],
                expected_view_sha256=view["view_sha256"], expected_finish_sha256="0" * 64)).status_code
        if n == 2:
            self.backup_fault = "joint_destination_anchor_complete"
        if n == 12:
            replies = await asyncio.gather(*(self.apply_joint(c, view) for c in (a, b)))
            if sorted(v.status_code for v in replies) != [200, 409] or self.repair_count != 1:
                raise ValueError("Competing joint repair appended more than once")
            return 409
        result = await self.apply_joint(a, view)
        if result.status_code != (400 if n == 2 else 200):
            raise ValueError("Exact first anchor repair rejected")
        if n == 2 and hasattr(self, "restart_primary"):
            a = await self.restart_primary()
        if n == 4:
            return (await self.apply_joint(a, view, target="window")).status_code
        fresh = (await self.observe_joint(a)).json()
        if fresh["progress"] != "window_pending" or fresh["next_target"] != "window" or fresh["plan_sha256"] != view["plan_sha256"]:
            raise ValueError("Fresh progress did not retain the exact plan")
        if (await self.inventory(a)).status_code != 400:
            raise ValueError("Partial joint repair bypassed the read fence")
        if n == 9:
            await self.withdrawal(a, b)
        if n == 10:
            self.advance(301)
        if n == 11:
            self.revoke("reviewer")
        if n in {9, 10, 11}:
            fresh = (await self.observe_joint(a)).json()
            if n == 9 and fresh["current_source_matches"]:
                raise ValueError("Withdrawal was silently refreshed")
        if n == 3:
            self.backup_fault = "joint_window_anchor_complete"
        result = await self.apply_joint(a, fresh)
        if result.status_code != (400 if n == 3 else 200):
            raise ValueError("Exact second anchor repair rejected")
        if n == 3 and hasattr(self, "restart_primary"):
            a = await self.restart_primary()
        final = (await self.observe_joint(a)).json()
        if final["progress"] != "reconciled" or final["next_target"] is not None or final["pending"]:
            raise ValueError("Joint completion retained pending anchors")
        if (await self.apply_joint(a, final)).status_code != 200 or self.repair_count != 2:
            raise ValueError("Reconciled no-op replayed a retained frame")
        before = self.four_histories()
        result = await self.request_joint(a, "joint_finish_observe", expected_plan_sha256=final["plan_sha256"],
            expected_view_sha256=final["view_sha256"], expected_finish_sha256=final["finish_sha256"])
        if result.status_code != 200 or result.json()["finish_state"] != "anchored" or self.four_histories() != before:
            raise ValueError("Finish reconciliation changed retained evidence")
        self.readonly_checks += 1
        expected = 403 if n == 11 else 409 if n in {9, 10} else 200
        if (await self.inventory(a)).status_code != expected:
            raise ValueError("Joint metadata repair renewed legal authority")
        if n == 1 and (await self.inventory(a, previous=self.old_page)).status_code != 409:
            raise ValueError("Joint repair reactivated an old cursor")
        return result.status_code

    def result(self, status):
        return {**super().result(status), "explicit_per_anchor_progress": True, "joint_plan_and_view_required": True,
                "destination_before_finish_anchor": True, "no_atomic_joint_transaction": True,
                "invented_mixed_anchor_restore": True}
