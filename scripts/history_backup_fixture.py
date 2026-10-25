"""Frozen invented review-history restore and multi-instance fault cases."""

import asyncio

import anchored_review_fixture as old
import operator_enrollment_evidence as e
from cryptography.fernet import Fernet
from operator_review_auth import SessionAuthority
from review_history_backup import HistoryVault
from review_history_service import HistoryService

CASES = [("H01_roundtrip", 200), ("H02_missing_source_db", 200), ("H03_corrupt_source_db", 200),
         ("H04_corrupt_ciphertext", 400), ("H05_changed_key", 400), ("H06_manifest_pin", 400),
         ("H07_old_backup_current_head", 400), ("H08_foreign_scope", 400), ("H09_missing_manifest", 400),
         ("H10_readonly_status", 200), ("H11_restore_replay", 409), ("H12_backup_replay", 409),
         ("H13_restore_lost_ack", 400), ("H14_interrupted_restore", 200), ("H15_actor_revoked", 403),
         ("H16_unassigned", 403), ("H17_no_csrf", 400), ("H18_backup_race", 409),
         ("H19_restore_race", 409), ("H20_cross_instance_recovery", 200), ("H21_prepare_race", 409),
         ("H22_changed_head_pin", 400), ("H23_stale_review_restored", 200),
         ("H24_changed_restored_projection", 400), ("H25_interrupted_backup", 200),
         ("H26_restore_status_pin", 400)]
POLICY = {"schema": "review-history-backup-qualification-v1", "cases": [dict(id=n, expected=s) for n, s in CASES],
          "native_attempts_per_case": 1, "min_distinct_worker_processes": 2, "max_backups": 64,
          "max_plaintext_bytes": 4194304, "max_ciphertext_bytes": 8388608,
          "disposable_accounts_only": True, "model_verification_seconds": 20,
          "live_provider_requests": 0, "native_inference_calls": 0, "real_trust_enrolled": False,
          "runtime_installation": False, "production_activation": False}


class Fixture(old.Fixture):
    def __init__(self, name, models, work, anchors, api, *, backups=None):
        super().__init__(name, models, work, anchors, api)
        self.bundles = backups / name if backups else self.work / "encrypted-history"
        self.catalog = self.base.anchors / "independent-backup-manifests"
        self.restores = self.work / "restored-history"
        self.keys = self.base.anchors / "history-keys"
        for path in (self.bundles, self.catalog, self.restores, self.keys):
            path.mkdir(mode=0o700)
        self.key_path = self.keys / "backup.key"
        e.retain(self.key_path, Fernet.generate_key())
        e.retain(self.keys / "disposable-auth.key", Fernet.generate_key())
        self.backup_id, self.restore_id = [e.sha((name + x).encode())[:32] for x in ("-backup", "-restore")]
        self.backup_fault, self.backed, self.restored_result = None, None, None
        self.independent_before = None
        self.services = [self.service_for(self.journal), self.service_for(self.journal)]
        self.open_restored = None

    def newpoint(self, name):
        if self.backup_fault == name:
            self.backup_fault = None
            if name == "before_backup_commit":
                self.revoke("preparer")
            else:
                raise ValueError("Invented interrupted history operation")

    def service_for(self, journal):
        authority = SessionAuthority(self.store, self.profile, firm_id=self.authority.firm_id,
                                     bindings=dict(self.authority.bindings), origins=self.authority.app.state.settings.origins)
        vault = HistoryVault(journal, self.bundles, self.catalog, self.restores, self.key_path, checkpoint=self.newpoint)
        return HistoryService(authority, self.target, journal.ledger, journal, vault, clock=lambda: self.now)

    def descriptor(self, node, *, restored=None):
        journal = self.services[0].vault.restored(restored) if restored else self.journal
        fault = {13: "restore_receipt_retained", 14: "restore_intent_retained", 15: "before_backup_commit", 25: "backup_blob_retained"}.get(int(self.name[1:3])) if node == 0 else None
        return {"profile": str(self.profile), "auth_key": str(self.keys / "disposable-auth.key"),
                "firm_id": self.authority.firm_id, "bindings": dict(self.authority.bindings),
                "packet": str(self.packet_path), "packet_sha256": self.packet_sha,
                "observation": str(self.observation_path), "observation_sha256": self.observation_sha,
                "stage": str(self.target.stage), "model": str(self.base.model), "trust": str(self.base.trust),
                "v2_path": str(self.base.journal.path), "v2_anchor": str(self.base.journal.anchor.path),
                "v2_id": self.base.journal.journal_id, "binding": {"journal_id": self.base.binding.journal_id,
                "operation_id": self.base.binding.operation_id, "record_sha256": self.base.binding.record_sha256,
                "volume_binding_sha256": self.base.binding.volume_binding_sha256, "pin": self.base.binding.pin_bytes.decode()},
                "journal_path": str(journal.path), "journal_anchor": str(journal.anchor.path),
                "journal_id": journal.identity, "journal_scope": journal.scope, "ledger": str(journal.ledger),
                "bundles": str(self.bundles), "manifests": str(self.catalog), "restores": str(self.restores),
                "key": str(self.key_path), "now": self.now, "fault": fault,
                "journal_fault": int(self.name[1:3]) == 20 and node == 1,
                "revoke_user": self.ids["preparer"], "production_activation": False}

    async def heads(self, client):
        response = await self.recover(client, repair=False)
        if response.status_code != 200:
            raise ValueError("Frozen head observation failed")
        return response.json()["anchor_head_sha256"]

    async def backup_request(self, client, head, *, ident=None, role="preparer", headers=None):
        response = await self.request(client, "backup", role, {"request_id": ident or self.backup_id, "expected_head_sha256": head}, headers=headers)
        if response.status_code == 200:
            self.backed = response.json()
        return response

    async def restore_request(self, client, head, *, ident=None, manifest=None):
        return await self.request(client, "restore", "preparer", {"request_id": ident or self.restore_id, "backup_id": self.backup_id,
                                  "manifest_sha256": manifest or self.backed["manifest_sha256"], "expected_head_sha256": head})

    async def status(self, client, ident, *, pin=True, wrong=False):
        body = {"request_id": ident, "intent_sha256": None, "receipt_sha256": None}
        response = await self.request(client, "restore_status", "preparer", body)
        if response.status_code != 200 or not pin:
            return response
        body.update({k: response.json()[k] for k in ("intent_sha256", "receipt_sha256")})
        if wrong:
            body["intent_sha256"] = "0" * 64
        return await self.request(client, "restore_status", "preparer", body)

    async def run(self, clients):
        a, b = clients
        n = int(self.name[1:3])
        if n == 21:
            body = {"request_id": self.request_id, "packet_sha256": self.packet_sha, "observation_sha256": self.observation_sha}
            results = await asyncio.gather(self.request(a, "prepare", "preparer", body), self.request(b, "prepare", "preparer", body))
            if sorted(r.status_code for r in results) != [200, 409]:
                raise ValueError("Cross-instance duplicate prepare admitted")
            return 409
        await self.prepare(a)
        if n == 20:
            self.fault = "committed_unanchored"
        decision = await self.decide(b)
        if n == 20:
            self.fault = None  # Native workers own their matching trusted hook.
            if decision.status_code != 400:
                raise ValueError("Cross-instance interruption was acknowledged")
            recovered = await self.recover(a)
            if recovered.status_code != 200:
                raise ValueError("Another instance did not recover exact history")
            raw = e.read(self.ledger / (self.request_id + ".decision.json"))
            return (await self.inspect(b, self.request_id, self.handoff["handoff_sha256"], e.sha(raw), "reviewed_for_disposable_handoff")).status_code
        if decision.status_code != 200:
            raise ValueError("Frozen initial decision failed")
        self.remember()
        head = await self.heads(a)
        if n == 15:
            self.backup_fault = "before_backup_commit"
        if n == 16:
            return (await self.backup_request(b, head, role="other")).status_code
        if n == 17:
            headers = self.headers("preparer")
            headers.pop("x-csrf-token")
            return (await self.backup_request(b, head, headers=headers)).status_code
        if n == 18:
            results = await asyncio.gather(self.backup_request(a, head), self.backup_request(b, head))
            if sorted(r.status_code for r in results) != [200, 409]:
                raise ValueError("Cross-instance duplicate backup admitted")
            return 409
        if n == 25:
            self.backup_fault = "backup_blob_retained"
        backed = await self.backup_request(a, head)
        if n in {15, 25}:
            if n == 15:
                return backed.status_code
            if backed.status_code != 400 or list(self.catalog.iterdir()):
                raise ValueError("Interrupted backup gained a manifest")
            duplicate = await self.backup_request(b, head)
            if duplicate.status_code != 409:
                raise ValueError("Partial backup was overwritten")
            return (await self.backup_request(b, head, ident=e.sha((self.name + "-fresh-backup").encode())[:32])).status_code
        if backed.status_code != 200:
            raise ValueError("Frozen encrypted backup rejected")
        if n == 12:
            return (await self.backup_request(b, head)).status_code
        if n == 2:
            self.journal.path.unlink()
        if n == 3:
            self.journal.path.write_bytes(b"invented damaged source database")
        if n == 4:
            path = self.bundles / (self.backup_id + ".bundle")
            path.write_bytes(path.read_bytes() + b"tampered")
        if n == 5:
            self.key_path.write_bytes(Fernet.generate_key())
        if n == 8:
            path = self.catalog / (self.backup_id + ".json")
            value = e.decode(e.read(path))
            value["scope_sha256"] = "0" * 64
            path.write_bytes(e.encode(value))
            self.backed["manifest_sha256"] = e.sha(e.encode(value))
        if n == 9:
            (self.catalog / (self.backup_id + ".json")).unlink()
        if n in {7, 22}:
            body = {"request_id": e.sha((self.name + "-later").encode())[:32], "packet_sha256": self.packet_sha, "observation_sha256": self.observation_sha}
            if (await self.request(a, "prepare", "preparer", body)).status_code != 200:
                raise ValueError("Frozen later review was not retained")
            if n == 7:
                head = await self.heads(b)
        if n == 23:
            self.revoke("reviewer")
            self.login("reviewer")
        source_before = self.journal.path.read_bytes() if self.journal.path.exists() else None
        self.independent_before = {p.name: p.read_bytes() for p in self.journal.anchor.path.parent.iterdir()}
        if n in {13, 14}:
            self.backup_fault = "restore_receipt_retained" if n == 13 else "restore_intent_retained"
        if n == 19:
            results = await asyncio.gather(self.restore_request(a, head), self.restore_request(b, head))
            if sorted(r.status_code for r in results) != [200, 409]:
                raise ValueError("Cross-instance duplicate restore admitted")
            return 409
        response = await self.restore_request(a if n in {13, 14} else b, head, manifest="0" * 64 if n == 6 else None)
        if (self.journal.path.read_bytes() if self.journal.path.exists() else None) != source_before:
            raise ValueError("Restore overwrote the original journal")
        self.preserved()
        if response.status_code != 200 and n not in {13, 14}:
            return response.status_code
        if n == 14:
            if response.status_code != 400:
                raise ValueError("Interrupted restore was acknowledged")
            status = await self.status(b, self.restore_id)
            if status.status_code != 200 or status.json()["status"] != "restore_attempt_incomplete":
                raise ValueError("Incomplete restore could not be inspected")
            original = e.read(self.restores / self.restore_id / "intent.json")
            fresh = e.sha((self.name + "-fresh-restore").encode())[:32]
            result = await self.restore_request(b, head, ident=fresh)
            if e.read(self.restores / self.restore_id / "intent.json") != original:
                raise ValueError("Fresh attempt rewrote failed history")
            return result.status_code
        if n == 11:
            return (await self.restore_request(b, head)).status_code
        status = await self.status(b, self.restore_id, pin=n != 10, wrong=n == 26)
        if status.status_code != 200 or n in {10, 26}:
            return status.status_code
        if status.json()["status"] != "restored_exact_history_retained":
            raise ValueError("Restored snapshot was not verified")
        if n == 13 and response.status_code != 400:
            raise ValueError("Lost restore acknowledgement was not injected")
        if n == 24:
            path = self.restores / self.restore_id / "ledger" / (self.request_id + ".decision.json")
            path.write_bytes(path.read_bytes() + b"changed")
            return (await self.status(a, self.restore_id)).status_code
        restored = await self.open_restored(self.restore_id)
        await self.inspect(restored, self.request_id, self.handoff["handoff_sha256"], self.decision["decision_sha256"],
                           "stale_review_retained" if n == 23 else "reviewed_for_disposable_handoff")
        return response.status_code

    def result(self, status):
        self.preserved()
        result = old.old.Fixture.result(self, status)
        if self.independent_before is not None and self.independent_before != {p.name: p.read_bytes() for p in self.journal.anchor.path.parent.iterdir()}:
            raise ValueError("Restore rewrote independently retained controls")
        encrypted = b"".join(p.read_bytes() for p in self.bundles.iterdir())
        if any(raw in encrypted for raw in self.saved.values()):
            raise ValueError("Original review bytes appeared in an encrypted bundle")
        result.update(encrypted_bundles=len(list(self.bundles.iterdir())), independent_manifests=len(list(self.catalog.iterdir())),
                      restore_attempts=len(list(self.restores.iterdir())), original_history_preserved=True,
                      anchor_and_intents_not_restored=True, no_automatic_activation=True)
        return result
