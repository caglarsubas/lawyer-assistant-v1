"""Frozen synthetic destination updates with separate independent approvals."""

import asyncio

import operator_enrollment_evidence as e
import operator_review_fixture as raw
import reader_namespace_fixture as retained
from destination_change import DestinationChange
from destination_change_log import DestinationChangeLog, scope_for

CASES = [("D01_reviewed_renewal", 200), ("D02_expired_legacy_new_authority", 200), ("D03_reviewed_retirement", 200),
         ("D04_fresh_rollback", 200), ("D05_self_review", 409), ("D06_denied_window", 409),
         ("D07_unopened_step", 409), ("D08_old_decision_reuse", 409), ("D09_canonical_withdrawal", 409),
         ("D10_changed_stage", 400), ("D11_revoked_reviewer", 403), ("D12_expired_window", 409),
         ("D13_lost_open_reply", 200), ("D14_lost_selection_reply", 200), ("D15_lost_transition_reply", 200),
         ("D16_readonly_reconciliation", 200), ("D17_early_finish", 409), ("D18_missing_window_admission", 400),
         ("D19_competing_open", 409), ("D20_competing_selection", 409)]
POLICY = {"schema": "destination-change-qualification-v1", "cases": [dict(id=n, expected=s) for n, s in CASES],
          "native_attempts_per_case": 1, "min_distinct_worker_processes": 2, "max_events": 256, "max_proposal_seconds": 300,
          "max_page_rows": 8, "model_verification_seconds": 20, "legacy_history_immutable": True,
          "destination_history_append_only": True, "fresh_independent_window_reader_and_transition_review": True,
          "no_inventory_during_change": True, "no_legacy_authority_reactivated": True, "canonical_fence_on_every_read": True,
          "disposable_accounts_only": True, "live_provider_requests": 0, "native_inference_calls": 0,
          "real_trust_enrolled": False, "runtime_installation": False, "production_activation": False}


class Fixture(retained.Fixture):
    def __init__(self, name, models, work, anchors, api, *, backups=None):
        super().__init__(name, models, work, anchors, api, backups=backups)
        root, anchor = self.work / "destination-changes", self.base.anchors / "destination-change-anchor"
        root.mkdir(mode=0o700)
        anchor.mkdir(mode=0o700)
        self.change_controls = DestinationChangeLog.create(root, anchor / "change.anchor", scope_for(self.services[0], root), api)
        self.services = [DestinationChange(v.legacy, v.destination, v.controls, self.change_controls, clock=lambda: self.now, checkpoint=self.newpoint) for v in self.services]
        self.change_id = e.sha((name + "-change").encode())[:32]
        self.change_terms = self.change_proposal = self.change_decision = self.change_opened = None
        self.legacy_before = self.destination_before = self.namespace_before = None

    def descriptor(self, node, *, restored=None):
        value = super().descriptor(node, restored=restored)
        n = int(self.name[1:3])
        value.update(fault={13: "destination_change_opened_complete", 14: "reader_selected_complete", 15: "namespace_committed_complete"}.get(n) if node == 0 else None,
                     reader_fault=None, namespace_fault=None,
                     change_root=str(self.change_controls.root), change_anchor=str(self.change_controls.anchor.path),
                     change_id=self.change_controls.identity, change_scope=self.change_controls.scope)
        return value

    @staticmethod
    def retained_files(controls):
        return {p: p.read_bytes() for p in [*controls.root.iterdir(), *controls.anchor.path.parent.iterdir()] if p.is_file()}

    def histories_preserved(self):
        if self.legacy_before is None:
            raise ValueError("Initial reviewed histories must exist")
        if self.retained_files(self.legacy_controls) != self.legacy_before:
            raise ValueError("Legacy history changed")
        for controls, before in ((self.reader_controls, self.destination_before), (self.transition_controls, self.namespace_before)):
            for path, value in before.items():
                if not path.exists() or (not path.read_bytes().startswith(value) if path == controls.anchor.path else path.read_bytes() != value):
                    raise ValueError("An earlier destination or transition event was rewritten")

    async def change(self, client, action, role="preparer", **body):
        result = await raw.Fixture.request(self, client, "change_observe", role, {})
        if result.status_code != 200:
            return result
        pins = result.json()
        body.update(change_id=self.change_id, expected_change_head_sha256=pins["change_head_sha256"], expected_subject_sha256=pins["subject_sha256"])
        result = await raw.Fixture.request(self, client, action, role, body)
        self.histories_preserved()
        return result

    async def initialize(self, a, b):
        await self.seed(a, b)
        await self.stage(a)
        await self.bind(a, b)
        self.namespace, self.mode = "destination", "initial"
        await self.next_stage(a, "-destination")
        await self.bind(a, b)
        self.rollback_target = self.reader_selection["selection_sha256"]
        if self.name.startswith("D04_"):
            self.mode = "renewal"
            await self.next_stage(a, "-second-destination")
            await self.bind(a, b)
        for operation, client in ((self.prepare_transition, a), (self.decide_transition, b), (self.commit_transition, a)):
            if (await operation(client)).status_code != 200:
                raise ValueError("Invented initial transition rejected")
        self.old_commit = dict(self.transition_commit)
        self.old_decision = dict(self.transition_decision)
        self.legacy_before, self.destination_before, self.namespace_before = [self.retained_files(c) for c in (self.legacy_controls, self.reader_controls, self.transition_controls)]

    async def run(self, clients):
        a, b = clients
        n = int(self.name[1:3])
        await self.initialize(a, b)
        if n == 2:
            self.advance(301)
            if (await self.inventory(a)).status_code != 409:
                raise ValueError("Expired legacy authority remained usable")
        if n == 3:
            self.change_terms = dict.fromkeys(("proposal_id", "transition_id", "stage_id", "intent_sha256", "receipt_sha256", "target_selection_sha256"))
            self.change_terms["mode"] = "retirement"
        else:
            await self.next_stage(a, "-maintenance")
            self.change_terms = {"mode": "rollback" if n == 4 else "renewal", "proposal_id": self.reader_id,
                                 "transition_id": e.sha((self.name + "-fresh-transition").encode())[:32], "stage_id": self.archive_restore_id,
                                 "intent_sha256": self.stage_pins["intent_sha256"], "receipt_sha256": self.stage_pins["receipt_sha256"],
                                 "target_selection_sha256": self.rollback_target if n == 4 else None}
        result = await self.change(a, "change_prepare", terms=self.change_terms)
        if result.status_code != 200:
            raise ValueError("Destination maintenance preparation rejected")
        self.change_proposal = result.json()
        if n == 7:
            return (await self.change(a, "change_step", step="prepare", decision=None)).status_code
        result = await self.change(a if n == 5 else b, "change_decide", role="preparer" if n == 5 else "reviewer",
                                   proposal_sha256=self.change_proposal["proposal_sha256"], decision="deny" if n == 6 else "approve",
                                   reason_code="destination_change_declined" if n == 6 else "exact_destination_change_checked")
        if n == 5:
            return result.status_code
        if result.status_code != 200:
            raise ValueError("Maintenance independent decision rejected")
        self.change_decision = result.json()
        if n == 6:
            if (await self.change(a, "change_status")).json()["grant_current"]:
                raise ValueError("Denied review appeared to grant maintenance authority")
        if n == 13:
            self.backup_fault = "destination_change_opened_complete"
        if n == 19:
            results = await asyncio.gather(*(self.change(c, "change_open", decision_sha256=self.change_decision["decision_sha256"]) for c in (a, b)))
            if sorted(v.status_code for v in results) != [200, 409]:
                raise ValueError("A destination window opened more than once")
            return 409
        result = await self.change(a, "change_open", decision_sha256=self.old_decision["decision_sha256"] if n == 8 else self.change_decision["decision_sha256"])
        if n in {6, 8}:
            return result.status_code
        if n == 13:
            if result.status_code != 400 or (await self.change(a, "change_status")).json()["phase"] != "opened":
                raise ValueError("Lost window reply did not reconcile")
            if (await self.change(a, "change_open", decision_sha256=self.change_decision["decision_sha256"])).status_code != 409:
                raise ValueError("Window opening replayed")
        elif result.status_code != 200:
            raise ValueError("Maintenance opening rejected")
        if n == 18:
            event = e.decode(e.read(self.change_controls.root / "0003.json"))
            (self.change_controls.anchor.path.parent / (event["head"] + ".intent.json")).unlink()
            return (await self.change(a, "change_status")).status_code
        if (await self.inventory(a)).status_code != 409:
            raise ValueError("Open maintenance admitted old or new inventory")
        if n == 9:
            await self.withdrawal(a, b)
        if n == 10:
            path = self.archive_restores / self.archive_restore_id / "receipt.json"
            path.write_bytes(path.read_bytes() + b"changed")
        if n == 11:
            self.revoke("reviewer")
        if n == 12:
            self.advance(301)
        if n == 16:
            before = self.retained_files(self.change_controls)
            result = await self.change(a, "change_status")
            if result.status_code != 200 or result.json()["phase"] != "opened" or not result.json()["grant_current"] or self.retained_files(self.change_controls) != before:
                raise ValueError("Readonly maintenance status changed authority")
            return result.status_code
        if n == 3:
            result = await self.change(a, "change_step", step="retire", decision=None)
            if result.status_code != 200:
                raise ValueError("Reviewed retirement rejected")
            status = (await self.change(a, "change_status")).json()
            result = await self.change(a, "change_finish", transition_commit_sha256=status["transition_commit_sha256"], destination_head_sha256=status["destination_head_sha256"])
            if (await self.inventory(a)).status_code != 409:
                raise ValueError("Retirement fell back to legacy namespace")
            return result.status_code
        result = await self.change(a, "change_step", step="prepare", decision=None)
        if n in {9, 10, 11, 12}:
            return result.status_code
        if result.status_code != 200:
            raise ValueError("Reviewed child preparation rejected")
        if (await self.change(b, "change_step", role="reviewer", step="decide", decision="approve")).status_code != 200:
            raise ValueError("Fresh child review rejected")
        if n == 14:
            self.backup_fault = "reader_selected_complete"
        if n == 20:
            results = await asyncio.gather(*(self.change(c, "change_step", step="select", decision=None) for c in (a, b)))
            if sorted(v.status_code for v in results) != [200, 409]:
                raise ValueError("Destination selection committed more than once")
            return 409
        result = await self.change(a, "change_step", step="select", decision=None)
        if n == 14:
            if result.status_code != 400 or (await self.change(a, "change_status")).json()["phase"] != "reader_selected":
                raise ValueError("Lost selection reply did not reconcile")
            if (await self.change(a, "change_step", step="select", decision=None)).status_code != 409:
                raise ValueError("Child selection replayed")
        elif result.status_code != 200:
            raise ValueError("Fresh child selection rejected")
        if n == 17:
            pins = (await self.change(a, "change_status")).json()
            return (await self.change(a, "change_finish", transition_commit_sha256=pins["transition_commit_sha256"], destination_head_sha256=pins["destination_head_sha256"])).status_code
        self.transition_id = self.change_terms["transition_id"]
        for operation, client in ((self.prepare_transition, a), (self.decide_transition, b)):
            if (await operation(client)).status_code != 200:
                raise ValueError("Fresh transition review rejected")
        if n == 15:
            self.backup_fault = "namespace_committed_complete"
        result = await self.commit_transition(a)
        if n == 15:
            status = await self.transition_status(a)
            if result.status_code != 400 or status.status_code != 200 or not status.json()["usable"]:
                raise ValueError("Lost new transition reply did not reconcile")
            self.transition_commit = status.json()
            if (await self.commit_transition(a)).status_code != 409:
                raise ValueError("Transition commit replayed")
        elif result.status_code != 200:
            raise ValueError("New transition commit rejected")
        if (await self.inventory(a)).status_code != 409:
            raise ValueError("Unfinished change admitted inventory")
        status = (await self.change(a, "change_status")).json()
        if (await self.change(a, "change_finish", transition_commit_sha256=status["transition_commit_sha256"], destination_head_sha256=status["destination_head_sha256"])).status_code != 200:
            raise ValueError("Verified maintenance completion rejected")
        if (await self.change(a, "change_status")).json()["grant_current"]:
            raise ValueError("Finished window appeared to remain an authority grant")
        result = await self.inventory(a)
        if result.status_code != 200:
            raise ValueError("Fresh reviewed destination did not become readable")
        for namespace in ("legacy", "destination"):
            self.namespace = namespace
            if (await self.view(a)).status_code != 409:
                raise ValueError("A direct reader route bypassed the transition")
        saved, self.transition_commit = self.transition_commit, self.old_commit
        if (await self.inventory(a)).status_code != 409:
            raise ValueError("Old transition became new authority")
        self.transition_commit = saved
        return result.status_code

    def result(self, status):
        self.histories_preserved()
        value = super().result(status)
        payload = b"".join(p.read_bytes() for p in self.change_controls.root.iterdir() if p.is_file())
        if any(v.encode() in payload for v in [*self.passwords.values(), *self.cookies.values(), *self.csrf.values()]):
            raise ValueError("Credentials entered destination-change history")
        value.update(change_events=len(list(self.change_controls.root.glob("[0-9a-f]*.json"))), legacy_history_immutable=True,
                     destination_and_transition_prefixes_preserved=True, fresh_window_child_and_transition_review_required=True,
                     no_inventory_during_change=True, legacy_reference_is_not_authority=True, no_unreviewed_destination_delegation=True)
        return value
