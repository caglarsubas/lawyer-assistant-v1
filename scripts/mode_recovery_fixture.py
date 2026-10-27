"""Fresh frozen controller retirement/rollback evidence, not legal acceptance."""

import asyncio
import shutil

import joint_recovery_fixture as retained
import operator_enrollment_evidence as e
from restore_control_log import ref

raw = retained.raw

DEFINITIONS = [('C01_retirement_ordered', 'retirement', 1, 200), ('C02_retirement_destination_restart', 'retirement', 2, 200), ('C03_retirement_finish_restart', 'retirement', 3, 200), ('C04_retirement_wrong_order', 'retirement', 5, 409), ('C05_retirement_missing_admission', 'retirement', 6, 400), ('C06_retirement_withdrawal', 'retirement', 9, 200), ('C07_retirement_expiry', 'retirement', 10, 200), ('C08_retirement_wrong_plan', 'retirement', 14, 409), ('C09_rollback_ordered', 'rollback', 1, 200), ('C10_rollback_destination_restart', 'rollback', 2, 200), ('C11_rollback_finish_restart', 'rollback', 3, 200), ('C12_rollback_stale_progress', 'rollback', 4, 409), ('C13_rollback_missing_admission', 'rollback', 7, 400), ('C14_rollback_revoked_review', 'rollback', 11, 200), ('C15_rollback_competing_repair', 'rollback', 12, 409), ('C16_rollback_borrowed_actor', 'rollback', 8, 409), ('C17_retirement_borrowed_actor', 'retirement', 8, 409), ('C18_rollback_wrong_plan', 'rollback', 14, 409)]
SCENARIOS = {name: scenario for name, mode, scenario, status in DEFINITIONS}
MODES = {name: mode for name, mode, scenario, status in DEFINITIONS}
CASES = [(name, status) for name, mode, scenario, status in DEFINITIONS]
POLICY = {**retained.POLICY, "schema": "mode-recovery-qualification-v1",
          "cases": [dict(id=name, expected=status, mode=mode, scenario=scenario) for name, mode, scenario, status in DEFINITIONS],
          "qualified_modes": ["retirement", "rollback"], "retirement_preserves_namespace": True,
          "rollback_requires_new_selection_and_reviews": True, "prior_approval_reuse_rejected": True}


class Fixture(retained.Fixture):
    def __init__(self, name, *args, **kwargs):
        super().__init__(name, *args, **kwargs)
        self.scenario = SCENARIOS.get(name, 1)
        self.change_mode = MODES.get(name, "retirement")

    def descriptor(self, node, *, restored=None):
        value = super().descriptor(node, restored=restored)
        value.update(fault={2: "joint_destination_anchor_complete", 3: "joint_window_anchor_complete"}.get(self.scenario) if node == 0 else None,
                     reader_fault=None, namespace_fault=None, window_fault="finished_retained" if node == 0 else None)
        return value

    async def initialize(self, a, b):
        await self.seed(a, b)
        await self.stage(a)
        await self.bind(a, b)
        self.namespace, self.mode = "destination", "initial"
        await self.next_stage(a, "-destination")
        await self.bind(a, b)
        self.rollback_target = self.reader_selection["selection_sha256"]
        if self.change_mode == "rollback":
            self.mode = "renewal"
            await self.next_stage(a, "-second-destination")
            await self.bind(a, b)
        for operation, client in ((self.prepare_transition, a), (self.decide_transition, b), (self.commit_transition, a)):
            if (await operation(client)).status_code != 200:
                raise ValueError("Initial mode transition rejected")
        self.old_commit, self.old_decision = dict(self.transition_commit), dict(self.transition_decision)
        self.legacy_before, self.destination_before, self.namespace_before = [self.retained_files(c) for c in (self.legacy_controls, self.reader_controls, self.transition_controls)]

    async def setup_window(self, a, b):
        await self.initialize(a, b)
        self.old_page = (await self.inventory(a)).json()
        if self.change_mode == "retirement":
            self.change_terms = dict.fromkeys(("proposal_id", "transition_id", "stage_id", "intent_sha256", "receipt_sha256", "target_selection_sha256"))
            self.change_terms["mode"] = "retirement"
        else:
            await self.next_stage(a, "-fresh-rollback")
            self.change_terms = {"mode": "rollback", "proposal_id": self.reader_id,
                "transition_id": e.sha((self.name + "-rollback-transition").encode())[:32], "stage_id": self.archive_restore_id,
                "intent_sha256": self.stage_pins["intent_sha256"], "receipt_sha256": self.stage_pins["receipt_sha256"],
                "target_selection_sha256": self.rollback_target}
        result = await self.change(a, "change_prepare", terms=self.change_terms)
        if result.status_code != 200:
            raise ValueError("Mode window preparation rejected")
        result = await self.change(b, "change_decide", role="reviewer", proposal_sha256=result.json()["proposal_sha256"], decision="approve", reason_code="exact_destination_change_checked")
        if result.status_code != 200 or result.json()["decision_sha256"] == self.old_decision["decision_sha256"]:
            raise ValueError("Fresh mode decision missing")
        self.change_decision = result.json()
        before = self.four_histories()
        old = await self.change(a, "change_open", decision_sha256=self.old_decision["decision_sha256"])
        if old.status_code != 409 or before != self.four_histories():
            raise ValueError("A prior namespace decision renewed mode authority")

    async def setup_joint(self, a, b, *, unfinished=False):
        await self.setup_window(a, b)
        if (await self.change(a, "change_open", decision_sha256=self.change_decision["decision_sha256"])).status_code != 200:
            raise ValueError("Reviewed mode window rejected")
        if self.change_mode == "retirement":
            if (await self.change(a, "change_step", step="retire", decision=None)).status_code != 200:
                raise ValueError("Reviewed destination retirement rejected")
            if self.retained_files(self.transition_controls) != self.namespace_before:
                raise ValueError("Retirement created another namespace transition")
        else:
            if (await self.select_child(a, b)).status_code != 200:
                raise ValueError("Fresh rollback child review rejected")
            row = e.decode(e.read(sorted(self.reader_controls.root.glob("[0-9][0-9][0-9][0-9].json"))[-1]))
            if row["kind"] != "selected" or ref(row) == self.rollback_target or row["payload"]["proposal_id"] != self.change_terms["proposal_id"]:
                raise ValueError("Rollback reused a historical selection")
            await self.new_transition(a, b)
        if unfinished:
            return
        self.window_fault = "finished_retained"
        if (await self.finish(a)).status_code != 400:
            raise ValueError("Mode finish interruption missing")
        p = self.reader_controls.anchor.path
        p.write_bytes(b"\n".join(p.read_bytes().splitlines()[:-1]) + b"\n")

    async def run(self, clients):
        a, b = clients
        n = self.scenario
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
        expected = 403 if n == 11 else 409 if self.change_mode == "retirement" or n in {9, 10} else 200
        if (await self.inventory(a)).status_code != expected:
            raise ValueError("Joint metadata repair renewed legal authority")
        if n == 1 and (await self.inventory(a, previous=self.old_page)).status_code != 409:
            raise ValueError("Joint repair reactivated an old cursor")
        return result.status_code

    def result(self, status):
        if self.change_mode == "retirement" and self.retained_files(self.transition_controls) != self.namespace_before:
            raise ValueError("Retirement changed the namespace history")
        return {**super().result(status), "qualified_change_mode": self.change_mode,
                "retirement_preserves_namespace": True, "rollback_requires_fresh_selection": True,
                "prior_namespace_approval_reuse_rejected": True}
