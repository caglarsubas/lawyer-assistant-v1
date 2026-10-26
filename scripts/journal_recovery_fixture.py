"""Frozen admitted-tail repair cases; no real accounts, cases or provider calls."""

import asyncio
import shutil

import destination_change_fixture as retained
import operator_enrollment_evidence as e
import operator_review_fixture as raw
from journal_recovery import JournalRecovery

CASES = [("G01_open_anchor_repair", 200), ("G02_selection_anchor_repair", 200), ("G03_finish_anchor_repair", 200),
         ("G04_lost_finish_reply", 200), ("G05_lost_repair_reply", 200), ("G06_missing_admission", 400),
         ("G07_stale_view", 409), ("G08_expired_metadata_only", 200), ("G09_withdrawn_metadata_only", 200),
         ("G10_revoked_review_metadata_only", 200), ("G11_copied_namespace", 400), ("G12_wrong_change", 409),
         ("G13_competing_repair", 409), ("G14_joint_pending_refused", 409), ("G15_clock_rollback", 409),
         ("G16_readonly_finish_and_cursor", 200)]
POLICY = {"schema": "journal-recovery-qualification-v1", "cases": [dict(id=n, expected=s) for n, s in CASES],
          "native_attempts_per_case": 1, "min_distinct_worker_processes": 2, "max_events": 256,
          "max_proposal_seconds": 300, "max_page_rows": 8, "model_verification_seconds": 20,
          "admission_required": True, "exact_view_and_actor_binding": True, "joint_recovery_refused": True,
          "no_authority_renewal": True, "no_mutation_replay": True, "histories_immutable": True,
          "disposable_accounts_only": True, "live_provider_requests": 0, "native_inference_calls": 0,
          "real_trust_enrolled": False, "runtime_installation": False, "production_activation": False}


class Fixture(retained.Fixture):
    def __init__(self, name, models, work, anchors, api, *, backups=None):
        super().__init__(name, models, work, anchors, api, backups=backups)
        self.services = [JournalRecovery(v.legacy, v.destination, v.controls, v.changes, clock=lambda: self.now, checkpoint=self.newpoint) for v in self.services]
        self.window_fault = None
        self.change_controls.checkpoint = self.windowpoint
        self.repair_count = self.readonly_checks = 0
        self.repaired_heads = set()

    def windowpoint(self, name):
        if name == self.window_fault:
            self.window_fault = None
            raise ValueError("Invented interrupted maintenance anchor")

    def descriptor(self, node, *, restored=None):
        value = super().descriptor(node, restored=restored)
        n = int(self.name[1:3])
        window = "opened_retained" if n == 1 else "finished_retained" if n in {3, 5, 8, 9, 10, 11, 14} else None
        value.update(fault={4: "finish_reply_complete", 5: "recovery_anchor_complete"}.get(n) if node == 0 else None,
                     reader_fault="selected_retained" if n in {2, 6, 7, 12, 13, 15} and node == 0 else None,
                     namespace_fault=None, window_fault=window if node == 0 else None)
        return value

    def four_histories(self):
        return {str(p): v for controls in (self.legacy_controls, self.reader_controls, self.transition_controls, self.change_controls) for p, v in self.retained_files(controls).items()}

    async def observe_recovery(self, client, target="window", *, change_id=None):
        result = await raw.Fixture.request(self, client, "recovery_observe", "preparer", {"change_id": change_id or self.change_id, "target": target})
        if result.status_code == 200 and result.json()["authority_renewed"] is not False:
            raise ValueError("Recovery observation created authority")
        return result

    async def repair(self, client, view, *, wrong=False):
        before = self.four_histories()
        anchor = self.change_controls.anchor.path if view["target"] == "window" else self.reader_controls.anchor.path
        result = await raw.Fixture.request(self, client, "recovery_apply", "preparer", {"change_id": self.change_id, "target": view["target"], "expected_view_sha256": "0" * 64 if wrong else view["view_sha256"]})
        if result.status_code == 200 and result.json()["authority_renewed"] is not False:
            raise ValueError("Anchor repair renewed authority")
        after = self.four_histories()
        if before.keys() != after.keys() or any(v != after[k] for k, v in before.items() if k != str(anchor)):
            raise ValueError("Repair rewrote history or manufactured admission")
        if before[str(anchor)] != after[str(anchor)]:
            if not after[str(anchor)].startswith(before[str(anchor)]) or len(after[str(anchor)].splitlines()) != len(before[str(anchor)].splitlines()) + 1:
                raise ValueError("Repair changed more than one exact anchor frame")
            self.repaired_heads.add((view["target"], view[view["target"] + "_tip_sha256"]))
            self.repair_count = len(self.repaired_heads)
        return result

    async def reconcile_finish(self, client):
        result = await self.observe_recovery(client)
        if result.status_code != 200:
            return result
        value = result.json()
        before = self.four_histories()
        result = await raw.Fixture.request(self, client, "finish_observe", "preparer", {"change_id": self.change_id,
            "expected_view_sha256": value["view_sha256"], "expected_finish_sha256": value["finish_sha256"]})
        if before != self.four_histories() or result.status_code == 200 and result.json()["authority_renewed"] is not False:
            raise ValueError("Finish reconciliation changed a history or anchor")
        self.readonly_checks += 1
        return result

    async def setup_window(self, a, b):
        await self.initialize(a, b)
        self.old_page = (await self.inventory(a)).json()
        await self.next_stage(a, "-recoverable")
        self.change_terms = {"mode": "renewal", "proposal_id": self.reader_id, "transition_id": e.sha((self.name + "-new-transition").encode())[:32],
            "stage_id": self.archive_restore_id, "intent_sha256": self.stage_pins["intent_sha256"], "receipt_sha256": self.stage_pins["receipt_sha256"], "target_selection_sha256": None}
        result = await self.change(a, "change_prepare", terms=self.change_terms)
        if result.status_code != 200:
            raise ValueError("Recovery maintenance preparation rejected")
        result = await self.change(b, "change_decide", role="reviewer", proposal_sha256=result.json()["proposal_sha256"], decision="approve", reason_code="exact_destination_change_checked")
        if result.status_code != 200:
            raise ValueError("Recovery maintenance review rejected")
        self.change_decision = result.json()

    async def select_child(self, a, b):
        for client, step, role, decision in ((a, "prepare", "preparer", None), (b, "decide", "reviewer", "approve")):
            if (await self.change(client, "change_step", role=role, step=step, decision=decision)).status_code != 200:
                raise ValueError("Fresh child preparation/review rejected")
        return await self.change(a, "change_step", step="select", decision=None)

    async def new_transition(self, a, b):
        self.transition_id = self.change_terms["transition_id"]
        for operation, client in ((self.prepare_transition, a), (self.decide_transition, b), (self.commit_transition, a)):
            if (await operation(client)).status_code != 200:
                raise ValueError("Recovery successor transition rejected")

    async def finish(self, a):
        result = await self.change(a, "change_status")
        if result.status_code != 200:
            return result
        pins = result.json()
        return await self.change(a, "change_finish", transition_commit_sha256=pins["transition_commit_sha256"], destination_head_sha256=pins["destination_head_sha256"])

    async def run(self, clients):
        a, b = clients
        n = int(self.name[1:3])
        await self.setup_window(a, b)
        if n == 1:
            self.window_fault = "opened_retained"
        result = await self.change(a, "change_open", decision_sha256=self.change_decision["decision_sha256"])
        if n == 1:
            if result.status_code != 400 or (await self.inventory(a)).status_code != 400:
                raise ValueError("Unanchored opening did not fence reads")
            view = (await self.observe_recovery(a)).json()
            if (await self.repair(b, view)).status_code != 200 or (await self.inventory(a)).status_code != 409:
                raise ValueError("Exact opening recovery bypassed the read fence")
        elif result.status_code != 200:
            raise ValueError("Recovery window opening rejected")
        if n in {2, 6, 7, 12, 13, 15}:
            self.binding_fault = "selected_retained"
        if n == 15:
            # Child selection follows the maintenance event in time. Only the
            # child journal's timestamp is ahead after the deliberate rollback.
            for c, step, role, decision in ((a, "prepare", "preparer", None), (b, "decide", "reviewer", "approve")):
                if (await self.change(c, "change_step", role=role, step=step, decision=decision)).status_code != 200:
                    raise ValueError("Clock fixture setup rejected")
            self.advance(1)
            result = await self.change(a, "change_step", step="select", decision=None)
            self.advance(-1)
        else:
            result = await self.select_child(a, b)
        if n in {2, 6, 7, 12, 13, 15}:
            if result.status_code != 400:
                raise ValueError("Child pending-tail interruption missing")
            if n == 6:
                event = e.decode(e.read(self.reader_controls.root / "0006.json"))
                (self.reader_controls.anchor.path.parent / (event["head"] + ".intent.json")).unlink()
            response = await self.observe_recovery(a, "destination", change_id="0" * 32 if n == 12 else None)
            if n in {6, 12, 15}:
                return response.status_code
            if response.status_code != 200:
                raise ValueError("Destination recovery observation rejected")
            view = response.json()
            if n == 7:
                before = self.four_histories()
                result = await self.repair(a, view, wrong=True)
                if before != self.four_histories():
                    raise ValueError("Stale repair modified evidence")
                return result.status_code
            if n == 13:
                replies = await asyncio.gather(*(self.repair(c, view) for c in (a, b)))
                if sorted(v.status_code for v in replies) != [200, 409] or self.repair_count != 1:
                    raise ValueError("A retained anchor was repaired more than once")
                return 409
            if (await self.repair(a, view)).status_code != 200 or (await self.inventory(a)).status_code != 409:
                raise ValueError("Child repair activated an unfinished window")
        elif result.status_code != 200:
            raise ValueError("Recovery child selection rejected")
        await self.new_transition(a, b)
        if n in {3, 5, 8, 9, 10, 11, 14}:
            self.window_fault = "finished_retained"
        if n == 4:
            self.backup_fault = "finish_reply_complete"
        result = await self.finish(a)
        if n in {3, 4, 5, 8, 9, 10, 11, 14}:
            if result.status_code != 400:
                raise ValueError("Interrupted finish was not injected")
            if n == 8:
                self.advance(301)
            if n == 9:
                await self.withdrawal(a, b)
            if n == 10:
                self.revoke("reviewer")
            if n == 11:
                root = self.legacy_controls.root
                held = root.with_name(root.name + "-original")
                root.rename(held)
                shutil.copytree(held, root)
            if n == 14:
                anchor = self.reader_controls.anchor.path
                anchor.write_bytes(b"\n".join(anchor.read_bytes().splitlines()[:-1]) + b"\n")
            observed = await self.observe_recovery(a)
            if n == 11:
                return observed.status_code
            if observed.status_code != 200:
                raise ValueError("Finish recovery metadata rejected")
            view = observed.json()
            if view["finish_state"] != ("anchored" if n == 4 else "pending_anchor"):
                raise ValueError("Retained finish was confused with anchored completion")
            if n == 9 and view["current_source_matches"]:
                raise ValueError("Withdrawal context was silently refreshed")
            if n == 5:
                self.backup_fault = "recovery_anchor_complete"
            result = await self.repair(a, view)
            if n == 14:
                return result.status_code
            if n == 5:
                if result.status_code != 400:
                    raise ValueError("Lost repair reply was not injected")
                fresh = (await self.observe_recovery(a)).json()
                result = await self.repair(a, fresh)
                if result.status_code != 200 or result.json()["repaired"]:
                    raise ValueError("Lost repair replayed anchor mutation")
            elif result.status_code != 200:
                raise ValueError("Admitted finish repair rejected")
        elif result.status_code != 200:
            raise ValueError("Recovery finish rejected")
        before = self.four_histories()
        result = await self.reconcile_finish(b)
        if result.status_code != 200 or before != self.four_histories() or result.json()["phase"] != "finished" or result.json()["finish_state"] != "anchored":
            raise ValueError("Exact finish did not reconcile read-only")
        if n in {8, 9, 10}:
            status = (await self.inventory(a)).status_code
            if status != (403 if n == 10 else 409):
                raise ValueError("Metadata recovery reactivated expired or revoked authority")
            return result.status_code
        if n == 16:
            view = (await self.observe_recovery(a)).json()
            result = await self.repair(a, view)
            if result.status_code != 200 or result.json()["repaired"] or before != self.four_histories():
                raise ValueError("Anchored no-op changed a history")
            if (await self.inventory(a, previous=self.old_page)).status_code != 409:
                raise ValueError("Recovery revived an old cursor")
        return (await self.inventory(a)).status_code

    def result(self, status):
        value = super().result(status)
        value.update(anchor_repairs=self.repair_count, readonly_recovery_checks=self.readonly_checks,
                     admitted_tail_required=True, exact_recovery_view_required=True, metadata_repair_never_renews_authority=True,
                     recovery_preserves_all_four_histories=True, joint_repair_never_automatic=True)
        return value
