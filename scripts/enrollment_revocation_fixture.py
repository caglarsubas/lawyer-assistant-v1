"""Fresh frozen inventory/withdrawal cases with disposable authenticated identities."""

import asyncio

import operator_enrollment_evidence as e
import operator_review_fixture as raw
import restore_authorization_fixture as retained
import restore_lifecycle_fixture as old
from cryptography.fernet import Fernet
from enrollment_revocation import EnrollmentRevocation
from enrollment_revocation_log import RevocationLog
from restore_authorization import RestoreAuthorization
from restore_control_log import RestoreControlLog
from restore_inventory import revocation_scope
from restore_key_custody import KeyCustody
from restore_lifecycle import RestoreLifecycle, catalog_scope
from restore_lifecycle_log import LifecycleLog

CASES = [("I01_inventory_pagination_readonly", 200), ("I02_tampered_cursor", 409), ("I03_other_actor_cursor", 409),
         ("I04_changed_snapshot", 409), ("I05_current_and_future_blocked", 200), ("I06_ancestor_and_descendants", 200),
         ("I07_unused_candidate_only", 200), ("I08_self_approval", 409), ("I09_wrong_subject_and_decision_pin", 409),
         ("I10_declined_withdrawal", 200), ("I11_changed_preparer_role", 403), ("I12_competing_decisions", 409),
         ("I13_lost_acknowledgement", 200), ("I14_unanchored_withdrawal", 200), ("I15_expired_source_packet", 200),
         ("I16_unassigned_and_csrf", 400), ("I17_pending_renewal_blocked", 200), ("I18_compromised_key_withdrawal", 200),
         ("I19_changed_control_proposal", 409), ("I20_legacy_bypass_and_missing_intent", 400)]
POLICY = {"schema": "enrollment-withdrawal-qualification-v1", "cases": [dict(id=n, expected=s) for n, s in CASES],
          "native_attempts_per_case": 1, "min_distinct_worker_processes": 2, "max_control_events": 256,
          "max_proposal_seconds": 300, "max_page_rows": 8, "configured_enrollments": 3,
          "disposable_accounts_only": True, "model_verification_seconds": 20, "live_provider_requests": 0,
          "native_inference_calls": 0, "real_trust_enrolled": False, "runtime_installation": False, "production_activation": False}


class Fixture(old.Fixture):
    def __init__(self, name, models, work, anchors, api, *, backups=None):
        super().__init__(name, models, work, anchors, api, backups=backups)
        existing = self.children[self.initial]
        value = e.decode(e.read(self.children[self.successor].custody.enrollment))
        path = self.custody_root / "future.json"
        self.future = e.retain(path, e.encode({**value, "expires_at": self.now + 2700}))["sha256"]
        custody = KeyCustody(self.key_path, path, self.future, self.journal.scope)
        root, anchor = self.work / "future-restore-controls", self.base.anchors / "future-restore-anchor"
        root.mkdir(mode=0o700)
        anchor.mkdir(mode=0o700)
        controls = RestoreControlLog.create(root, anchor / "control.anchor", {**self.controls.scope, "custody_sha256": self.future}, api)
        self.children[self.future] = RestoreAuthorization(existing.authority, self.target, self.ledger, self.journal, existing.vault,
                                                         custody, controls, clock=lambda: self.now)
        root, anchor = self.work / "catalog-lifecycle", self.base.anchors / "catalog-lifecycle-anchor"
        root.mkdir(mode=0o700)
        anchor.mkdir(mode=0o700)
        self.lifecycle = LifecycleLog.create(root, anchor / "lifecycle.anchor", catalog_scope(self.children, self.initial, self.now), api)
        with self.lifecycle.locked() as (_, head, _, _):
            self.context = {"enrollment_sha256": self.initial, "expected_lifecycle_head_sha256": head["head"]}
        inners = [RestoreLifecycle(self.children, self.initial, self.lifecycle, clock=lambda: self.now) for _ in range(2)]
        root, anchor = self.work / "withdrawal-controls", self.base.anchors / "withdrawal-anchor"
        root.mkdir(mode=0o700)
        anchor.mkdir(mode=0o700)
        self.revocations = RevocationLog.create(root, anchor / "withdrawal.anchor", revocation_scope(inners[0]), api)
        self.revocations.checkpoint = self.controlpoint
        self.services = [EnrollmentRevocation(inner, self.revocations, clock=lambda: self.now, checkpoint=self.newpoint) for inner in inners]
        with self.revocations.locked() as (_, head, _, _):
            self.revocation_head = head["head"]
        self.withdrawal_id = e.sha((name + "-withdrawal").encode())[:32]
        self.withdrawal_proposal, self.withdrawal_decision = None, None

    def descriptor(self, node, *, restored=None):
        value = super().descriptor(node, restored=restored)
        value.update(fault="revocation_decision_complete" if self.name.startswith("I13_") and node == 0 else None,
                     control_fault="decided_retained" if self.name.startswith("I14_") and node == 0 else None,
                     revocation_root=str(self.revocations.root), revocation_anchor=str(self.revocations.anchor.path),
                     revocation_id=self.revocations.identity, revocation_scope=self.revocations.scope)
        return value

    async def request(self, client, action, role, body, **kwargs):
        if action in EnrollmentRevocation.management:
            value = dict(body)
            if action not in {"lifecycle_inventory", "revocation_recover"}:
                value.update(expected_revocation_head_sha256=self.revocation_head,
                             expected_lifecycle_head_sha256=self.context["expected_lifecycle_head_sha256"])
        else:
            inner = body if action in {"lifecycle_status", "lifecycle_recover"} else {**self.context, "request": body}
            value = {"expected_revocation_head_sha256": self.revocation_head, "request": inner}
        response = await raw.Fixture.request(self, client, action, role, value, **kwargs)
        if response.status_code == 200:
            result = response.json()
            if "revocation_head_sha256" in result:
                self.revocation_head = result["revocation_head_sha256"]
            if "lifecycle_head_sha256" in result and "enrollment_sha256" in result:
                self.context = {"enrollment_sha256": result["enrollment_sha256"], "expected_lifecycle_head_sha256": result["lifecycle_head_sha256"]}
        return response

    async def inventory(self, client, *, role="preparer", previous=None, wrong=False, headers=None):
        body = {"snapshot_sha256": None, "offset": 0, "limit": 1 if previous else 8, "cursor": None}
        if previous:
            body.update(snapshot_sha256=previous["snapshot_sha256"], offset=previous["next_offset"], limit=1,
                        cursor="0" * 64 if wrong else previous["next_cursor"])
        return await self.request(client, "lifecycle_inventory", role, body, headers=headers)

    async def withdraw_prepare(self, client, target, *, wrong=False):
        observed = await self.request(client, "observe_revocation", "preparer", {"target_enrollment_sha256": target})
        if observed.status_code != 200:
            return observed
        response = await self.request(client, "prepare_revocation", "preparer", {"target_enrollment_sha256": target, "proposal_id": self.withdrawal_id,
                                      "subject_sha256": "0" * 64 if wrong else observed.json()["subject_sha256"]})
        if response.status_code == 200:
            self.withdrawal_proposal = response.json()
        return response

    async def withdraw_decide(self, client, *, role="reviewer", denied=False, wrong=False):
        response = await self.request(client, "decide_revocation", role, {"proposal_id": self.withdrawal_id,
                                      "proposal_sha256": "0" * 64 if wrong else self.withdrawal_proposal["proposal_sha256"],
                                      "decision": "deny" if denied else "approve", "reason_code": "withdrawal_declined" if denied else "withdraw_exact_enrollment_lineage"})
        if response.status_code == 200:
            self.withdrawal_decision = response.json()
        return response

    async def withdrawal_status(self, client):
        response = await self.request(client, "revocation_status", "reviewer", {"proposal_id": self.withdrawal_id, "decision_sha256": None})
        if response.status_code != 200:
            return response
        return await self.request(client, "revocation_status", "reviewer", {"proposal_id": self.withdrawal_id, "decision_sha256": response.json()["decision_sha256"]})

    async def selected(self, client):
        child = self.children[self.context["enrollment_sha256"]]
        with child.controls.locked() as (_, fence, _, _):
            head = fence["head"]
        return await self.request(client, "selected_history", "reviewer", {"selection_id": self.selection_id,
                                  "selection_sha256": self.selection["selection_sha256"], "handoff_id": self.request_id,
                                  "handoff_sha256": self.handoff["handoff_sha256"], "decision_sha256": self.decision["decision_sha256"],
                                  "expected_control_head_sha256": head})

    def preserved_files(self):
        roots = (self.work, self.base.anchors, self.bundles)
        return {str(path): e.sha(path.read_bytes()) for root in roots for path in root.rglob("*") if path.is_file()}

    async def renew(self, a, b, candidate):
        self.proposal_id = e.sha((self.name + candidate).encode())[:32]
        if (await self.propose(a, "renewal", candidate=candidate)).status_code != 200 or (await self.lifecycle_decide(b, "renewal")).status_code != 200:
            raise ValueError("Invented lineage renewal failed")

    async def run(self, clients):
        a, b = clients
        n = int(self.name[1:3])
        await self.prepare(a)
        if (await self.decide(b)).status_code != 200:
            raise ValueError("Initial review rejected")
        self.remember()
        head = await self.heads(a)
        if (await self.backup_request(a, head)).status_code != 200 or (await self.prepare_grant(a, head)).status_code != 200 or (await self.authorize(b)).status_code != 200:
            raise ValueError("Initial restore grant rejected")
        restored = await self.execute(a)
        if restored.status_code != 200 or (await self.select(b, restored.json())).status_code != 200:
            raise ValueError("Initial target rejected")
        self.source_before = self.journal.path.read_bytes()
        self.independent_before = {p.name: p.read_bytes() for p in self.journal.anchor.path.parent.iterdir()}
        self.original_targets = {str(p.relative_to(self.restores)): p.read_bytes() for p in self.restores.rglob("*") if p.is_file()}
        self.original_backups = {p.name: p.read_bytes() for p in self.bundles.iterdir()}
        self.original_key = e.read(self.key_path)
        if n in {1, 2, 3, 4}:
            before = self.preserved_files()
            first = await self.request(a, "lifecycle_inventory", "preparer", {"snapshot_sha256": None, "offset": 0, "limit": 1, "cursor": None})
            if first.status_code != 200:
                raise ValueError("Initial inventory rejected")
            if n == 4:
                await self.renew(a, b, self.successor)
            result = await self.inventory(b, role="reviewer" if n == 3 else "preparer", previous=first.json(), wrong=n == 2)
            if n in {2, 3, 4}:
                return result.status_code
            if result.status_code != 200:
                raise ValueError("Bound inventory cursor rejected")
            last = await self.inventory(b, previous=result.json())
            if last.status_code != 200 or last.json()["next_cursor"] is not None or self.preserved_files() != before:
                raise ValueError("Inventory changed files or lost bounded pages")
            return last.status_code
        if n == 6:
            await self.renew(a, b, self.successor)
            await self.renew(a, b, self.future)
        if n == 15:
            self.now += 901
            self.clock_path.write_bytes(e.encode({"now": self.now}))
        if n == 16:
            if (await self.inventory(a, role="other")).status_code != 403:
                raise ValueError("Unassigned actor saw catalog metadata")
            headers = self.headers("preparer")
            headers.pop("x-csrf-token")
            return (await self.inventory(b, headers=headers)).status_code
        if n == 17:
            self.proposal_id = e.sha((self.name + "-pending-renewal").encode())[:32]
            if (await self.propose(a, "renewal")).status_code != 200:
                raise ValueError("Pending renewal rejected")
        if n == 18:
            self.key_path.write_bytes(Fernet.generate_key())
        if n == 20:
            direct = await raw.Fixture.request(self, a, "selected_history", "reviewer", {})
            if direct.status_code != 400:
                raise ValueError("Legacy route bypassed the outer fence")
        target = self.future if n == 7 else self.successor if n == 17 else self.initial
        response = await self.withdraw_prepare(a, target, wrong=n == 9)
        if n == 9:
            if response.status_code != 409 or (await self.withdraw_prepare(a, target)).status_code != 200:
                raise ValueError("Wrong withdrawal scope was accepted")
            return (await self.withdraw_decide(b, wrong=True)).status_code
        if response.status_code != 200:
            raise ValueError("Withdrawal preparation rejected")
        if n == 11:
            self.revise_role("preparer")
        if n == 19:
            changed = await self.request(b, "revoke_restore", "reviewer", {"operation_id": self.restore_id, "expected_control_head_sha256": await self.control(b)})
            if changed.status_code != 200:
                raise ValueError("Authorized control change rejected")
        if n == 20:
            next(self.revocations.anchor.path.parent.glob("*.intent.json")).unlink()
            return (await self.inventory(b)).status_code
        if n == 13:
            self.backup_fault = "revocation_decision_complete"
        if n == 14:
            self.control_fault = "decided_retained"
        if n == 12:
            values = await asyncio.gather(self.withdraw_decide(a), self.withdraw_decide(b))
            if sorted(r.status_code for r in values) != [200, 409]:
                raise ValueError("Competing withdrawals both committed")
            return 409
        response = await self.withdraw_decide(a if n in {13, 14} else b, role="preparer" if n == 8 else "reviewer", denied=n == 10)
        if n in {8, 11, 19}:
            return response.status_code
        if n == 14:
            if response.status_code != 400 or (await self.selected(b)).status_code != 400:
                raise ValueError("Unanchored withdrawal did not block ordinary access")
            observed = await self.request(b, "revocation_recover", "reviewer", {"expected_head_sha256": None, "expected_tip_sha256": None, "repair": False})
            if observed.status_code != 200 or observed.json()["published_withdrawals"] != 0:
                raise ValueError("Unanchored withdrawal was silently published")
            value = observed.json()
            response = await self.request(b, "revocation_recover", "reviewer", {"expected_head_sha256": value["revocation_head_sha256"], "expected_tip_sha256": value["revocation_tip_sha256"], "repair": True})
        if n == 13:
            if response.status_code != 400:
                raise ValueError("Lost withdrawal acknowledgement was not injected")
            if (await self.inventory(b)).status_code != 200:
                raise ValueError("Lost reply could not be observed without replay")
            response = await self.withdrawal_status(b)
        if response.status_code != 200:
            raise ValueError("Withdrawal decision rejected")
        if n in {7, 10, 17}:
            if n == 17 and (await self.lifecycle_decide(b, "renewal")).status_code != 409:
                raise ValueError("Pending renewal bypassed candidate withdrawal")
            if (await self.selected(b)).status_code != 200:
                raise ValueError("Unrelated active enrollment was withdrawn")
            if n == 7:
                await self.renew(a, b, self.successor)
                if (await self.propose(a, "renewal", candidate=self.future)).status_code != 409:
                    raise ValueError("Withdrawn candidate was reintroduced")
        else:
            if (await self.selected(b)).status_code != 409 or (await self.request(b, "restore_control", "preparer", {})).status_code != 409:
                raise ValueError("Withdrawn active lineage still served")
        if n == 5 and (await self.propose(a, "renewal")).status_code != 409:
            raise ValueError("Future renewal bypassed current lineage withdrawal")
        inventory = await self.inventory(b)
        if inventory.status_code != 200:
            raise ValueError("Read-only inventory lost retained withdrawal history")
        if n == 18 and any(row["validity"] != "integrity_unavailable" for row in inventory.json()["rows"]):
            raise ValueError("Compromised key was reported as usable")
        return (await self.withdrawal_status(b)).status_code

    def result(self, status):
        result = retained.Fixture.result(self, status)
        n = int(self.name[1:3])
        if n != 18 and e.read(self.key_path) != self.original_key:
            raise ValueError("Withdrawal changed encryption keys")
        if self.original_backups != {p.name: p.read_bytes() for p in self.bundles.iterdir()}:
            raise ValueError("Withdrawal changed encrypted backups")
        if any((self.restores / name).read_bytes() != raw for name, raw in self.original_targets.items()):
            raise ValueError("Withdrawal changed restored evidence/history")
        payload = b"".join(p.read_bytes() for p in self.revocations.root.iterdir())
        if any(v.encode() in payload for v in [*self.passwords.values(), *self.cookies.values(), *self.csrf.values()]):
            raise ValueError("Credential appeared in withdrawal records")
        result.update(withdrawal_events=len(list(self.revocations.root.glob("[0-9a-f]*.json"))), catalog_rows_defined=3,
                      no_system_evidence_or_key_mutation=True, lineage_withdrawal_is_not_key_destruction=True,
                      no_replay_or_automatic_reactivation=True, bounded_metadata_only_inventory=True)
        return result
