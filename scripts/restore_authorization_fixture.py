"""Frozen disposable restore authorization, custody and selection cases."""

import asyncio

import history_backup_fixture as old
import operator_enrollment_evidence as e
from cryptography.fernet import Fernet
from restore_authorization import RestoreAuthorization
from restore_control_log import RestoreControlLog
from restore_key_custody import SCHEMA, KeyCustody, file_id

CASES = [("A01_roundtrip", 200), ("A02_direct_restore", 409), ("A03_self_authorize", 409),
         ("A04_denied", 409), ("A05_wrong_preparation", 409), ("A06_wrong_authorization", 409),
         ("A07_execution_replay", 409), ("A08_revoked", 409), ("A09_changed_key", 400),
         ("A10_replaced_key_inode", 400), ("A11_custody_changed", 400), ("A12_target_replaced", 409),
         ("A13_wrong_receipt", 400), ("A14_role_changed", 409), ("A15_preparer_selection", 409),
         ("A16_superseded_selection", 409), ("A17_lost_acknowledgement", 200),
         ("A18_unanchored_consumption", 200), ("A19_execution_race", 409),
         ("A20_wrong_control_head", 409), ("A21_unassigned", 403), ("A22_missing_csrf", 400),
         ("A23_control_rollback", 400), ("A24_stale_original_review", 200),
         ("A25_expired_grant", 409), ("A26_missing_admission_intent", 400)]
POLICY = {"schema": "restore-authorization-qualification-v1", "cases": [dict(id=n, expected=s) for n, s in CASES],
          "native_attempts_per_case": 1, "min_distinct_worker_processes": 2, "max_control_events": 256,
          "max_grant_seconds": 300, "disposable_accounts_only": True, "model_verification_seconds": 20,
          "live_provider_requests": 0, "native_inference_calls": 0, "real_trust_enrolled": False,
          "runtime_installation": False, "production_activation": False}


class Fixture(old.Fixture):
    def __init__(self, name, models, work, anchors, api, *, backups=None):
        super().__init__(name, models, work, anchors, api, backups=backups)
        self.clock_path = self.work / "disposable-clock.json"
        e.retain(self.clock_path, e.encode({"now": self.now}))
        self.custody_root = self.base.anchors / "restore-custody"
        self.custody_root.mkdir(mode=0o700)
        self.enrollment_path = self.custody_root / "enrollment.json"
        info = self.key_path.stat()
        enrollment = {"schema": SCHEMA, "key_id": e.sha((name + "-key").encode())[:32],
                      "scope_sha256": e.sha(e.encode(self.journal.scope)), "fingerprint_sha256": e.sha(e.read(self.key_path)),
                      "key_file": {"device": info.st_dev, "inode": info.st_ino, "owner": info.st_uid},
                      "purpose": "review_history_backup_restore", "created_at": self.now - 1, "expires_at": self.now + 900,
                      **dict.fromkeys(e.FLAGS, False)}
        self.custody_sha = e.retain(self.enrollment_path, e.encode(enrollment))["sha256"]
        self.custody = KeyCustody(self.key_path, self.enrollment_path, self.custody_sha, self.journal.scope)
        control_root, control_anchor = self.work / "restore-controls", self.base.anchors / "restore-control-anchor"
        control_root.mkdir(mode=0o700)
        control_anchor.mkdir(mode=0o700)
        scope = {**self.journal.scope, "review_journal_id": self.journal.identity, "custody_sha256": self.custody_sha,
                 "restore_root_sha256": e.sha(e.encode(file_id(self.restores)))}
        self.controls = RestoreControlLog.create(control_root, control_anchor / "control.anchor", scope, api)
        self.controls.checkpoint = self.controlpoint
        self.control_fault = None
        self.services = [self.authorized(s) for s in self.services]
        self.prepared, self.authorization, self.selection = None, None, None

    def controlpoint(self, name):
        if self.control_fault == name:
            self.control_fault = None
            raise ValueError("Invented interrupted restore authorization")

    def authorized(self, service):
        return RestoreAuthorization(service.authority, self.target, self.ledger, self.journal, service.vault,
                                    self.custody, self.controls, clock=lambda: self.now, checkpoint=self.newpoint)

    def descriptor(self, node, *, restored=None):
        value = super().descriptor(node, restored=restored)
        value.update(fault="authorized_restore_complete" if self.name.startswith("A17_") and node == 0 else None,
                     journal_fault=False, control_fault="consumed_retained" if self.name.startswith("A18_") and node == 0 else None,
                     custody=str(self.enrollment_path), custody_sha256=self.custody_sha,
                     control_root=str(self.controls.root), control_anchor=str(self.controls.anchor.path),
                     control_scope=self.controls.scope, control_id=self.controls.identity, clock_path=str(self.clock_path))
        return value

    async def control(self, client):
        response = await self.request(client, "restore_control", "preparer", {})
        if response.status_code != 200:
            raise ValueError("Frozen restore control observation rejected")
        return response.json()["control_head_sha256"]

    async def prepare_grant(self, client, review_head, *, head=None, role="preparer", headers=None):
        response = await self.request(client, "prepare_restore", role, {"operation_id": self.restore_id,
                                      "backup_id": self.backup_id, "manifest_sha256": self.backed["manifest_sha256"],
                                      "expected_review_head_sha256": review_head,
                                      "expected_control_head_sha256": head or await self.control(client)}, headers=headers)
        if response.status_code == 200:
            self.prepared = response.json()
        return response

    async def authorize(self, client, *, role="reviewer", denied=False, wrong=False):
        response = await self.request(client, "authorize_restore", role, {"operation_id": self.restore_id,
                                      "prepared_sha256": "0" * 64 if wrong else self.prepared["prepared_sha256"],
                                      "decision": "deny" if denied else "approve", "reason_code": "restore_declined" if denied else "exact_restore_scope_checked",
                                      "expected_control_head_sha256": await self.control(client)})
        if response.status_code == 200:
            self.authorization = response.json()
        return response

    async def execute(self, client, *, wrong=False, head=None):
        return await self.request(client, "execute_restore", "preparer", {"operation_id": self.restore_id,
                                  "authorization_sha256": "0" * 64 if wrong else self.authorization["authorization_sha256"],
                                  "expected_control_head_sha256": head or await self.control(client)})

    async def reconcile(self, client, *, pin=True):
        body = {"operation_id": self.restore_id, "intent_sha256": None, "receipt_sha256": None,
                "expected_control_head_sha256": await self.control(client)}
        response = await self.request(client, "reconcile_restore", "preparer", body)
        if response.status_code != 200 or not pin or "intent_sha256" not in response.json():
            return response
        body.update({k: response.json()[k] for k in ("intent_sha256", "receipt_sha256")})
        return await self.request(client, "reconcile_restore", "preparer", body)

    async def select(self, client, result, *, role="reviewer", wrong=False, suffix="selection"):
        self.selection_id = e.sha((self.name + suffix).encode())[:32]
        response = await self.request(client, "select_restored_target", role, {"operation_id": self.restore_id, "selection_id": self.selection_id,
                                      "authorization_sha256": self.authorization["authorization_sha256"],
                                      "intent_sha256": result["intent_sha256"], "receipt_sha256": "0" * 64 if wrong else result["receipt_sha256"],
                                      "expected_control_head_sha256": await self.control(client)})
        if response.status_code == 200:
            self.selection = response.json()
        return response

    async def selected(self, client, *, ident=None, selection=None):
        return await self.request(client, "selected_history", "reviewer", {"selection_id": ident or self.selection_id,
                                  "selection_sha256": selection or self.selection["selection_sha256"], "handoff_id": self.request_id,
                                  "handoff_sha256": self.handoff["handoff_sha256"], "decision_sha256": self.decision["decision_sha256"],
                                  "expected_control_head_sha256": await self.control(client)})

    async def run(self, clients):
        a, b = clients
        n = int(self.name[1:3])
        await self.prepare(a)
        if (await self.decide(b)).status_code != 200:
            raise ValueError("Initial review rejected")
        self.remember()
        review_head = await self.heads(a)
        if (await self.backup_request(a, review_head)).status_code != 200:
            raise ValueError("Initial encrypted backup rejected")
        self.source_before = self.journal.path.read_bytes()
        self.independent_before = {p.name: p.read_bytes() for p in self.journal.anchor.path.parent.iterdir()}
        if n == 2:
            return (await self.restore_request(b, review_head)).status_code
        if n == 24:
            self.revoke("reviewer")
            self.login("reviewer")
        initial_control = self.controls.anchor.path.read_bytes()
        headers = self.headers("preparer") if n == 22 else None
        if headers:
            headers.pop("x-csrf-token")
        response = await self.prepare_grant(a, review_head, head="0" * 64 if n == 20 else None, role="other" if n == 21 else "preparer", headers=headers)
        if n in {20, 21, 22}:
            return response.status_code
        if response.status_code != 200:
            raise ValueError("Restore grant preparation rejected")
        if n == 23:
            self.controls.anchor.path.write_bytes(initial_control)
            return (await self.request(b, "restore_control", "preparer", {})).status_code
        if n == 26:
            next(self.controls.anchor.path.parent.glob("*.intent.json")).unlink()
            return (await self.request(b, "restore_control", "preparer", {})).status_code
        response = await self.authorize(b, role="preparer" if n == 3 else "reviewer", denied=n == 4, wrong=n == 5)
        if n in {3, 5}:
            return response.status_code
        if response.status_code != 200:
            raise ValueError("Independent restore authorization rejected")
        if n == 8:
            revoked = await self.request(b, "revoke_restore", "reviewer", {"operation_id": self.restore_id, "expected_control_head_sha256": await self.control(b)})
            if revoked.status_code != 200:
                raise ValueError("Restore revocation rejected")
        if n == 9:
            self.key_path.write_bytes(Fernet.generate_key())
        if n == 10:
            replacement = self.key_path.parent / "replacement.key"
            e.retain(replacement, e.read(self.key_path))
            replacement.replace(self.key_path)
        if n == 11:
            self.enrollment_path.write_bytes(e.read(self.enrollment_path) + b" ")
        if n == 12:
            self.restores.rename(self.work / "retained-restore-namespace")
            self.restores.mkdir(mode=0o700)
        if n == 14:
            self.revise_role("reviewer")
        if n == 25:
            self.now += 301
            self.clock_path.write_bytes(e.encode({"now": self.now}))
        if n == 17:
            self.backup_fault = "authorized_restore_complete"
        if n == 18:
            self.control_fault = "consumed_retained"
        if n == 19:
            head = await self.control(b)
            results = await asyncio.gather(self.execute(a, head=head), self.execute(b, head=head))
            if sorted(r.status_code for r in results) != [200, 409]:
                raise ValueError("Duplicate authorized restore admitted")
            return 409
        response = await self.execute(a, wrong=n == 6)
        if n in {4, 6, 8, 9, 10, 11, 12, 14, 25}:
            return response.status_code
        if n == 18:
            if response.status_code != 400:
                raise ValueError("Interrupted consumption was acknowledged")
            observed = await self.request(b, "restore_control_recover", "reviewer", {"expected_head_sha256": None, "expected_tip_sha256": None, "repair": False})
            if observed.status_code != 200:
                raise ValueError("Control tail could not be observed")
            value = observed.json()
            repaired = await self.request(b, "restore_control_recover", "reviewer", {"expected_head_sha256": value["control_head_sha256"], "expected_tip_sha256": value["control_tip_sha256"], "repair": True})
            if repaired.status_code != 200 or (await self.execute(b)).status_code != 409:
                raise ValueError("Consumption recovery renewed execution authority")
            status = await self.reconcile(b, pin=False)
            if status.status_code != 200 or status.json()["status"] != "consumed_restore_not_materialized":
                raise ValueError("Uncertain restore was silently materialized")
            return status.status_code
        if n == 17:
            if response.status_code != 400 or (await self.execute(b)).status_code != 409:
                raise ValueError("Uncertain acknowledgement permitted replay")
            response = await self.reconcile(b)
        if response.status_code != 200:
            raise ValueError("Authorized restore rejected")
        if n == 7:
            return (await self.execute(b)).status_code
        selected = await self.select(b, response.json(), role="preparer" if n == 15 else "reviewer", wrong=n == 13)
        if n in {13, 15}:
            return selected.status_code
        if selected.status_code != 200:
            raise ValueError("Exact restored target selection rejected")
        if n == 16:
            previous, previous_sha = self.selection_id, self.selection["selection_sha256"]
            if (await self.select(a, response.json(), suffix="second-selection")).status_code != 200:
                raise ValueError("Fresh explicit selection rejected")
            return (await self.selected(b, ident=previous, selection=previous_sha)).status_code
        result = await self.selected(b)
        if result.status_code == 200 and result.json()["status"] != ("selected_stale_review_retained" if n == 24 else "selected_exact_history_readable"):
            raise ValueError("Selected exact history status lost")
        return result.status_code

    def result(self, status):
        result = super().result(status)
        if self.journal.path.read_bytes() != self.source_before:
            raise ValueError("Authorization rewrote source history")
        raw = b"".join(p.read_bytes() for p in self.controls.root.iterdir())
        if any(v.encode() in raw for v in [*self.passwords.values(), *self.cookies.values(), *self.csrf.values()]):
            raise ValueError("Restore control leaked a credential")
        result.update(original_history_preserved=True, restore_control_events=len(list(self.controls.root.glob("[0-9a-f]*.json"))),
                      independent_restore_authorization=True, key_custody_pinned=True, no_live_target_selected=True)
        return result
