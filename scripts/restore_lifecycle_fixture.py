"""Fresh invented identities; frozen lifecycle retirement and renewal cases."""

import asyncio

import operator_enrollment_evidence as e
import restore_authorization_fixture as old
from cryptography.fernet import Fernet
from restore_authorization import RestoreAuthorization
from restore_control_log import RestoreControlLog
from restore_key_custody import KeyCustody
from restore_lifecycle import RestoreLifecycle, catalog_scope
from restore_lifecycle_log import LifecycleLog

CASES = [("N01_retire_selected", 200), ("N02_self_retirement", 409), ("N03_wrong_target_pin", 409),
         ("N04_declined_retirement", 200), ("N05_expired_restore_retirement", 200), ("N06_retirement_race", 409),
         ("N07_retirement_lost_ack", 200), ("N08_changed_target_receipt", 409), ("N09_renew_and_fresh_restore", 200),
         ("N10_self_renewal", 409), ("N11_declined_renewal", 200), ("N12_expired_predecessor", 200),
         ("N13_unknown_candidate", 409), ("N14_changed_key", 400), ("N15_changed_enrollment", 400),
         ("N16_changed_preparer_role", 403), ("N17_renewal_replay", 409), ("N18_renewal_race", 409),
         ("N19_unanchored_renewal", 200), ("N20_retired_history_after_renewal", 200),
         ("N21_unassigned", 403), ("N22_missing_csrf", 400), ("N23_stale_lifecycle_head", 409), ("N24_missing_lifecycle_intent", 400)]
POLICY = {"schema": "restore-lifecycle-qualification-v1", "cases": [dict(id=n, expected=s) for n, s in CASES],
          "native_attempts_per_case": 1, "min_distinct_worker_processes": 2, "max_control_events": 256,
          "max_proposal_seconds": 300, "max_enrollment_seconds": 86400, "max_configured_enrollments": 8,
          "disposable_accounts_only": True, "model_verification_seconds": 20,
          "live_provider_requests": 0, "native_inference_calls": 0, "real_trust_enrolled": False,
          "runtime_installation": False, "production_activation": False}


class Fixture(old.Fixture):
    def __init__(self, name, models, work, anchors, api, *, backups=None):
        super().__init__(name, models, work, anchors, api, backups=backups)
        base = self.services[0]
        original = e.decode(e.read(self.enrollment_path))
        children = {}
        for label, expiry in (("initial", 120), ("successor", 1800)):
            path = self.custody_root / (label + ".json")
            digest = e.retain(path, e.encode({**original, "expires_at": self.now + expiry}))["sha256"]
            custody = KeyCustody(self.key_path, path, digest, self.journal.scope)
            root, independent = self.work / (label + "-restore-controls"), self.base.anchors / (label + "-restore-anchor")
            root.mkdir(mode=0o700)
            independent.mkdir(mode=0o700)
            scope = {**base.controls.scope, "custody_sha256": digest}
            controls = RestoreControlLog.create(root, independent / "control.anchor", scope, api)
            children[digest] = RestoreAuthorization(base.authority, self.target, self.ledger, self.journal, base.vault,
                                                    custody, controls, clock=lambda: self.now)
        self.initial, self.successor = children
        self.children = children
        current = children[self.initial]
        self.custody, self.controls = current.custody, current.controls
        self.enrollment_path, self.custody_sha = self.custody.enrollment, self.custody.approved
        life_root, life_anchor = self.work / "lifecycle-controls", self.base.anchors / "lifecycle-anchor"
        life_root.mkdir(mode=0o700)
        life_anchor.mkdir(mode=0o700)
        self.lifecycle = LifecycleLog.create(life_root, life_anchor / "lifecycle.anchor", catalog_scope(children, self.initial, self.now), api)
        self.lifecycle.checkpoint = self.controlpoint
        self.services = [RestoreLifecycle(children, self.initial, self.lifecycle, clock=lambda: self.now, checkpoint=self.newpoint) for _ in range(2)]
        with self.lifecycle.locked() as (_, head, _, _):
            self.context = {"enrollment_sha256": self.initial, "expected_lifecycle_head_sha256": head["head"]}
        self.proposal_id, self.proposal, self.life_decision = e.sha((name + "-life").encode())[:32], None, None

    def descriptor(self, node, *, restored=None):
        value = super().descriptor(node, restored=restored)
        value.update(fault="lifecycle_decision_complete" if self.name.startswith("N07_") and node == 0 else None,
                     control_fault="decided_retained" if self.name.startswith("N19_") and node == 0 else None,
                     initial_generation=self.initial, generations=[{"custody": str(s.custody.enrollment), "custody_sha256": digest,
                     "control_root": str(s.controls.root), "control_anchor": str(s.controls.anchor.path), "control_id": s.controls.identity,
                     "control_scope": s.controls.scope} for digest, s in self.children.items()],
                     lifecycle_root=str(self.lifecycle.root), lifecycle_anchor=str(self.lifecycle.anchor.path),
                     lifecycle_id=self.lifecycle.identity, lifecycle_scope=self.lifecycle.scope)
        return value

    async def request(self, client, action, role, body, **kwargs):
        value = body if action in {"lifecycle_status", "lifecycle_recover"} else {**self.context, "request": body}
        response = await super().request(client, action, role, value, **kwargs)
        if response.status_code == 200 and "lifecycle_head_sha256" in response.json():
            result = response.json()
            self.context = {"enrollment_sha256": result["enrollment_sha256"], "expected_lifecycle_head_sha256": result["lifecycle_head_sha256"]}
        return response

    async def propose(self, client, kind, *, role="preparer", wrong=False, candidate=None, headers=None):
        body = {"target_generation": self.initial, "operation_id": self.restore_id} if kind == "retirement" else {"candidate_generation": candidate or self.successor}
        observed = await self.request(client, "observe_" + kind, "preparer", body)
        if observed.status_code != 200:
            return observed
        body.update(request_id=self.proposal_id, subject_sha256="0" * 64 if wrong else observed.json()["subject_sha256"])
        response = await self.request(client, "prepare_" + kind, role, body, headers=headers)
        if response.status_code == 200:
            self.proposal = response.json()
        return response

    async def lifecycle_decide(self, client, kind, *, role="reviewer", denied=False, wrong=False):
        response = await self.request(client, "decide_lifecycle", role, {"request_id": self.proposal_id,
                                      "proposal_sha256": "0" * 64 if wrong else self.proposal["proposal_sha256"], "decision": "deny" if denied else "approve",
                                      "reason_code": "lifecycle_declined" if denied else "retire_exact_target" if kind == "retirement" else "renew_exact_enrollment"})
        if response.status_code == 200:
            self.life_decision = response.json()
        return response

    async def retired_status(self, client, decision):
        return await self.request(client, "retirement_status", "reviewer", {"target_generation": self.initial,
                                  "operation_id": self.restore_id, "decision_sha256": decision["decision_sha256"]})

    async def run(self, clients):
        a, b = clients
        n = int(self.name[1:3])
        await self.prepare(a)
        if (await self.decide(b)).status_code != 200:
            raise ValueError("Initial exact review rejected")
        self.remember()
        head = await self.heads(a)
        if (await self.backup_request(a, head)).status_code != 200 or (await self.prepare_grant(a, head)).status_code != 200 or (await self.authorize(b)).status_code != 200:
            raise ValueError("Initial authorized restore rejected")
        restored = await self.execute(a)
        if restored.status_code != 200 or (await self.select(b, restored.json())).status_code != 200:
            raise ValueError("Initial exact selection rejected")
        self.source_before = self.journal.path.read_bytes()
        self.independent_before = {p.name: p.read_bytes() for p in self.journal.anchor.path.parent.iterdir()}
        self.restore_before = {str(p.relative_to(self.restores)): p.read_bytes() for p in self.restores.rglob("*") if p.is_file()}
        self.backups_before = {p.name: p.read_bytes() for p in self.bundles.iterdir()}
        self.initial_controls_before = {p.name: p.read_bytes() for p in self.controls.root.iterdir()}
        self.key_before = e.read(self.key_path)
        old_context = dict(self.context)
        if n in {5, 12}:
            self.now += 121
            self.clock_path.write_bytes(e.encode({"now": self.now}))
        kind = "retirement" if n <= 8 or n in {20, 21, 22, 23, 24} else "renewal"
        headers = self.headers("preparer") if n == 22 else None
        if headers:
            headers.pop("x-csrf-token")
        response = await self.propose(a, kind, role="other" if n == 21 else "preparer", wrong=n == 3,
                                      candidate="0" * 64 if n == 13 else None, headers=headers)
        if n == 3:
            if response.status_code != 409 or (await self.propose(a, kind)).status_code != 200:
                raise ValueError("Wrong target pin was admitted")
            return (await self.lifecycle_decide(b, kind, wrong=True)).status_code
        if n in {13, 21, 22}:
            return response.status_code
        if response.status_code != 200:
            raise ValueError("Lifecycle proposal rejected")
        if n == 5:
            self.now += 301
            self.clock_path.write_bytes(e.encode({"now": self.now}))
            if (await self.lifecycle_decide(b, kind)).status_code != 409:
                raise ValueError("Expired lifecycle proposal was accepted")
            self.proposal_id = e.sha((self.name + "-fresh-retirement").encode())[:32]
            if (await self.propose(a, kind)).status_code != 200:
                raise ValueError("Fresh independent retirement was refused")
        if n == 8:
            path = self.restores / self.restore_id / "receipt.json"
            path.write_bytes(e.read(path) + b" ")
        if n == 14:
            self.key_path.write_bytes(Fernet.generate_key())
        if n == 15:
            path = self.children[self.successor].custody.enrollment
            path.write_bytes(e.read(path) + b" ")
        if n == 16:
            self.revise_role("preparer")
        if n == 23:
            self.context["expected_lifecycle_head_sha256"] = old_context["expected_lifecycle_head_sha256"]
        if n == 24:
            next(self.lifecycle.anchor.path.parent.glob("*.intent.json")).unlink()
        if n == 7:
            self.backup_fault = "lifecycle_decision_complete"
        if n == 19:
            self.control_fault = "decided_retained"
        if n in {6, 18}:
            results = await asyncio.gather(self.lifecycle_decide(a, kind), self.lifecycle_decide(b, kind))
            if sorted(r.status_code for r in results) != [200, 409]:
                raise ValueError("Competing lifecycle decisions both admitted")
            return 409
        response = await self.lifecycle_decide(a if n in {7, 19} else b, kind, role="preparer" if n in {2, 10} else "reviewer", denied=n in {4, 11})
        if n in {2, 8, 10, 14, 15, 16, 23, 24}:
            return response.status_code
        if n == 19:
            if response.status_code != 400:
                raise ValueError("Unanchored renewal was acknowledged")
            observed = await self.request(b, "lifecycle_recover", "reviewer", {"expected_head_sha256": None, "expected_tip_sha256": None, "repair": False})
            if observed.status_code != 200 or observed.json()["enrollment_sha256"] != self.initial:
                raise ValueError("Unanchored enrollment silently became current")
            pins = observed.json()
            response = await self.request(b, "lifecycle_recover", "reviewer", {"expected_head_sha256": pins["lifecycle_head_sha256"], "expected_tip_sha256": pins["lifecycle_tip_sha256"], "repair": True})
        if n == 7:
            if response.status_code != 400:
                raise ValueError("Lost retirement reply was acknowledged")
            response = await self.request(b, "lifecycle_status", "reviewer", {})
            if response.status_code != 200 or response.json()["retired_targets"] != 1:
                raise ValueError("Another instance lost the retained retirement")
        if response.status_code != 200:
            raise ValueError("Exact lifecycle decision rejected")
        if n == 17:
            return (await self.lifecycle_decide(b, kind)).status_code
        if n in {4, 11}:
            selected = await self.selected(b)
            if selected.status_code != 200:
                raise ValueError("Declined lifecycle request withdrew valid history")
            return selected.status_code
        if kind == "retirement":
            if (await self.selected(b)).status_code != 409:
                raise ValueError("Retired target still served")
            if n == 7:
                raw = e.decode(e.read(sorted(self.lifecycle.root.glob("[0-9a-f]*.json"))[-1]))
                from restore_control_log import ref
                decision = {"decision_sha256": ref(raw)}
            else:
                decision = self.life_decision
            if n == 20:
                self.proposal_id = e.sha((self.name + "-renewal").encode())[:32]
                if (await self.propose(a, "renewal")).status_code != 200 or (await self.lifecycle_decide(b, "renewal")).status_code != 200:
                    raise ValueError("Renewal after retirement rejected")
            return (await self.retired_status(b, decision)).status_code
        if self.context["enrollment_sha256"] != self.successor:
            raise ValueError("Approved enrollment was not superseded")
        previous = {**old_context, "request": {}}
        stale = await super().request(b, "restore_control", "preparer", previous)
        if stale.status_code != 409:
            raise ValueError("Superseded enrollment still accepted requests")
        controls = await self.request(b, "restore_control", "preparer", {})
        if controls.status_code != 200 or controls.json()["events"] != 0:
            raise ValueError("Renewal copied old restore approvals")
        if n == 9:
            self.restore_id = e.sha((self.name + "-fresh-restore").encode())[:32]
            if (await self.prepare_grant(a, head)).status_code != 200 or (await self.authorize(b)).status_code != 200:
                raise ValueError("Fresh restore authorization missing")
            fresh = await self.execute(a)
            if fresh.status_code != 200 or (await self.select(b, fresh.json())).status_code != 200:
                raise ValueError("Fresh exact restore/selection rejected")
            return (await self.selected(b)).status_code
        return response.status_code

    def result(self, status):
        result = super().result(status)
        n = int(self.name[1:3])
        if n != 14 and e.read(self.key_path) != self.key_before:
            raise ValueError("Enrollment renewal changed encryption keys")
        if self.backups_before != {p.name: p.read_bytes() for p in self.bundles.iterdir()}:
            raise ValueError("Lifecycle operation rewrote encrypted backups")
        for name, raw in self.restore_before.items():
            if n != 8 and (self.restores / name).read_bytes() != raw:
                raise ValueError("Lifecycle operation rewrote a restored target")
        if self.initial_controls_before != {p.name: p.read_bytes() for p in self.controls.root.iterdir()}:
            raise ValueError("Lifecycle operation rewrote initial restore approvals")
        result.update(lifecycle_events=len(list(self.lifecycle.root.glob("[0-9a-f]*.json"))),
                      original_targets_and_backups_retained=True, enrollment_renewal_is_not_key_rotation=True,
                      fresh_restore_authorization_required=True, retired_targets_not_served=True)
        return result
