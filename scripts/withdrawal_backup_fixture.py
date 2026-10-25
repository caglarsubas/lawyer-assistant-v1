"""Fresh frozen archive/reconciliation cases with invented local identities."""

import asyncio
import os

import enrollment_revocation_fixture as retained
import operator_enrollment_evidence as e
import operator_review_fixture as raw
from withdrawal_history_backup import WithdrawalVault
from withdrawal_history_service import WithdrawalHistory

CASES = [("W01_empty_roundtrip", 200), ("W02_withdrawn_roundtrip", 200), ("W03_descendant_roundtrip", 200),
         ("W04_denied_history", 200), ("W05_stale_backup_head", 409), ("W06_changed_lifecycle", 409),
         ("W07_tampered_ciphertext", 400), ("W08_wrong_manifest_pin", 400), ("W09_foreign_manifest", 400),
         ("W10_self_comparison", 400), ("W11_revoked_reviewer", 401), ("W12_changed_preparer", 403),
         ("W13_lost_restore_reply", 200), ("W14_interrupted_intent", 200), ("W15_interrupted_files", 200),
         ("W16_missing_admission_intent", 400), ("W17_restore_replay", 400), ("W18_restore_race", 400),
         ("W19_stale_comparison", 409), ("W20_unassigned_and_csrf", 400), ("W21_tampered_stage", 400),
         ("W22_interrupted_backup", 200), ("W23_wrong_snapshot_pin", 409), ("W24_source_rollback", 400),
         ("W25_withdrawal_clock_rollback", 400), ("W26_replaced_key_namespace", 400)]
POLICY = {"schema": "withdrawal-backup-qualification-v1", "cases": [dict(id=n, expected=s) for n, s in CASES],
          "native_attempts_per_case": 1, "min_distinct_worker_processes": 2, "max_events": 256,
          "max_plaintext_bytes": 4194304, "new_stages_only": True, "independent_controls_external": True,
          "disposable_accounts_only": True, "model_verification_seconds": 20, "live_provider_requests": 0,
          "native_inference_calls": 0, "real_trust_enrolled": False, "runtime_installation": False, "production_activation": False}


class Fixture(retained.Fixture):
    def __init__(self, name, models, work, anchors, api, *, backups=None):
        super().__init__(name, models, work, anchors, api, backups=backups)
        self.archive_bundles = self.bundles.parent / (name + "-withdrawal-bundles")
        self.archive_manifests = self.base.anchors / "withdrawal-manifests"
        self.archive_restores = self.work / "withdrawal-restores"
        for root in (self.archive_bundles, self.archive_manifests, self.archive_restores):
            root.mkdir(mode=0o700)
        self.archive_id, self.archive_restore_id = [e.sha((name + suffix).encode())[:32] for suffix in ("-archive", "-archive-restore")]
        self.history_pin, self.history_backed = None, None
        self.services = [WithdrawalHistory(service, WithdrawalVault(service, self.archive_bundles, self.archive_manifests,
                                                                   self.archive_restores, self.key_path, checkpoint=self.newpoint),
                                           clock=lambda: self.now) for service in self.services]

    def descriptor(self, node, *, restored=None):
        value = super().descriptor(node)
        faults = {13: "withdrawal_restore_receipt_retained", 14: "withdrawal_restore_intent_retained",
                  15: "withdrawal_restore_files_retained", 22: "withdrawal_blob_retained"}
        value.update(fault=faults.get(int(self.name[1:3])) if node == 0 else None, journal_fault=False, control_fault=None,
                     archive_bundles=str(self.archive_bundles), archive_manifests=str(self.archive_manifests),
                     archive_restores=str(self.archive_restores))
        return value

    async def request(self, client, action, role, body, **kwargs):
        if action not in WithdrawalHistory.management:
            return await super().request(client, action, role, body, **kwargs)
        value = dict(body)
        if action != "withdrawal_snapshot":
            value.update(expected_context_sha256=self.history_pin["context_sha256"],
                         expected_revocation_head_sha256=self.history_pin["revocation_head_sha256"])
        return await raw.Fixture.request(self, client, action, role, value, **kwargs)

    async def snapshot(self, client):
        response = await self.request(client, "withdrawal_snapshot", "preparer", {})
        if response.status_code == 200:
            self.history_pin = response.json()
        return response

    async def archive(self, client):
        response = await self.request(client, "backup_withdrawal_history", "preparer", {"backup_id": self.archive_id})
        if response.status_code == 200:
            self.history_backed = response.json()
        return response

    async def restore_archive(self, client, *, wrong=False):
        return await self.request(client, "restore_withdrawal_history", "preparer", {"restore_id": self.archive_restore_id,
                                  "backup_id": self.archive_id, "manifest_sha256": "0" * 64 if wrong else self.history_backed["manifest_sha256"]})

    async def compare(self, client, *, role="reviewer", wrong=False):
        observed = await self.request(client, "withdrawal_restore_status", role, {"restore_id": self.archive_restore_id,
                                      "intent_sha256": None, "receipt_sha256": None})
        if observed.status_code != 200:
            return observed
        value = observed.json()
        return await self.request(client, "withdrawal_restore_status", role, {"restore_id": self.archive_restore_id,
                                  "intent_sha256": "0" * 64 if wrong else value["intent_sha256"], "receipt_sha256": value["receipt_sha256"]})

    async def withdrawal(self, a, b, *, denied=False):
        if (await self.withdraw_prepare(a, self.initial)).status_code != 200 or (await self.withdraw_decide(b, denied=denied)).status_code != 200:
            raise ValueError("Invented archive withdrawal setup rejected")

    async def seed(self, a, b):
        await self.prepare(a)
        if (await self.decide(b)).status_code != 200:
            raise ValueError("Invented review seed rejected")
        self.remember()
        head = await self.heads(a)
        if (await self.backup_request(a, head)).status_code != 200 or (await self.prepare_grant(a, head)).status_code != 200 or (await self.authorize(b)).status_code != 200:
            raise ValueError("Invented original restore seed rejected")
        result = await self.execute(a)
        if result.status_code != 200 or (await self.select(b, result.json())).status_code != 200:
            raise ValueError("Invented original selection rejected")
        self.source_before = self.journal.path.read_bytes()
        self.independent_before = {p.name: p.read_bytes() for p in self.journal.anchor.path.parent.iterdir()}
        self.original_targets = {str(p.relative_to(self.restores)): p.read_bytes() for p in self.restores.rglob("*") if p.is_file()}
        self.original_backups = {p.name: p.read_bytes() for p in self.bundles.iterdir()}
        self.original_key = e.read(self.key_path)

    async def run(self, clients):
        a, b = clients
        n = int(self.name[1:3])
        await self.seed(a, b)
        if n == 25:
            self.now += 10
            self.clock_path.write_bytes(e.encode({"now": self.now}))
            await self.withdrawal(a, b)
            self.now -= 5
            self.clock_path.write_bytes(e.encode({"now": self.now}))
            return (await self.snapshot(a)).status_code
        if n == 3:
            await self.renew(a, b, self.successor)
        if n in {2, 3, 4, 16, 24}:
            await self.withdrawal(a, b, denied=n == 4)
        if (await self.snapshot(a)).status_code != 200:
            raise ValueError("Initial archive snapshot rejected")
        if n == 20:
            self.login("other")
            if (await self.request(b, "withdrawal_snapshot", "other", {})).status_code != 403:
                raise ValueError("Unassigned archive access accepted")
            headers = self.headers("preparer")
            headers.pop("x-csrf-token")
            return (await self.request(a, "withdrawal_snapshot", "preparer", {}, headers=headers)).status_code
        if n == 23:
            self.history_pin["context_sha256"] = "0" * 64
            return (await self.archive(a)).status_code
        if n == 22:
            self.backup_fault = "withdrawal_blob_retained"
            if (await self.archive(a)).status_code != 400 or (await self.archive(a)).status_code != 400:
                raise ValueError("Interrupted backup was silently overwritten")
            self.archive_id = e.sha((self.name + "-fresh-archive").encode())[:32]
        if (await self.archive(a)).status_code != 200:
            raise ValueError("Invented archive rejected")
        if n == 5:
            await self.withdrawal(a, b)
        if n == 6:
            await self.renew(a, b, self.successor)
        if n in {5, 6}:
            return (await self.restore_archive(a)).status_code
        if n == 7:
            path = self.archive_bundles / (self.archive_id + ".withdrawal")
            path.write_bytes(path.read_bytes() + b"changed")
        if n == 9:
            path = self.archive_manifests / (self.archive_id + ".json")
            value = e.decode(e.read(path))
            value["scope_sha256"] = "0" * 64
            path.write_bytes(e.encode(value))
            self.history_backed["manifest_sha256"] = e.sha(e.read(path))
        if n == 16:
            event = e.decode(e.read(self.revocations.root / "0002.json"))
            (self.revocations.anchor.path.parent / (event["head"] + ".intent.json")).unlink()
        if n == 24:
            (self.revocations.root / "0002.json").unlink()
        if n == 26:
            original = e.read(self.key_path)
            # Keep the old inode alive so ext4 cannot recycle it immediately.
            # This fault must replace the pinned namespace, not merely recreate
            # identical bytes under a recycled inode number.
            fd = os.open(self.key_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                old = os.fstat(fd)
                self.key_path.unlink()
                e.retain(self.key_path, original)
                if (self.key_path.stat().st_dev, self.key_path.stat().st_ino) == (old.st_dev, old.st_ino):
                    raise ValueError("Replacement fault did not change the pinned namespace")
            finally:
                os.close(fd)
            if (await self.snapshot(a)).status_code != 200:
                raise ValueError("Unknown integrity metadata observation rejected")
        if n in {13, 14, 15}:
            self.backup_fault = {13: "withdrawal_restore_receipt_retained", 14: "withdrawal_restore_intent_retained", 15: "withdrawal_restore_files_retained"}[n]
        if n == 18:
            replies = await asyncio.gather(self.restore_archive(a), self.restore_archive(b))
            if sorted(r.status_code for r in replies) != [200, 400]:
                raise ValueError("Competing exclusive stages both committed")
            return 400
        result = await self.restore_archive(a, wrong=n == 8)
        if n in {7, 8, 9, 16, 24, 26}:
            return result.status_code
        if n in {13, 14, 15}:
            if result.status_code != 400:
                raise ValueError("Archive interruption was not injected")
        elif result.status_code != 200:
            raise ValueError("Invented stage rejected")
        if n == 17:
            return (await self.restore_archive(b)).status_code
        if n == 11:
            self.revoke("reviewer")
        if n == 12:
            self.revise_role("preparer")
        if n == 19:
            await self.withdrawal(a, b)
        if n == 21:
            path = self.archive_restores / self.archive_restore_id / "journal/metadata.json"
            path.write_bytes(path.read_bytes() + b"changed")
        before = self.preserved_files()
        response = await self.compare(b, role="preparer" if n == 10 else "reviewer")
        if before != self.preserved_files():
            raise ValueError("Read-only reconciliation wrote retained files")
        if n in {10, 11, 12, 19, 21}:
            return response.status_code
        expected = "withdrawal_restore_incomplete" if n in {14, 15} else "withdrawal_history_matches_current_fence"
        if response.status_code != 200 or response.json()["status"] != expected:
            raise ValueError("Exact archive reconciliation status lost")
        if n in {2, 3} and (await self.selected(b)).status_code != 409:
            raise ValueError("Restored withdrawal history reactivated authority")
        return response.status_code

    def result(self, status):
        result = super().result(status)
        if e.read(self.key_path) != self.original_key:
            raise ValueError("Archive replaced the encryption key")
        plaintext = [e.read(p) for p in self.revocations.root.iterdir() if p.is_file()]
        encrypted = b"".join(p.read_bytes() for p in self.archive_bundles.iterdir())
        if any(raw in encrypted for raw in plaintext):
            raise ValueError("Withdrawal history appeared unencrypted in a backup")
        result.update(withdrawal_archives=len(list(self.archive_bundles.iterdir())), withdrawal_manifests=len(list(self.archive_manifests.iterdir())),
                      withdrawal_restore_attempts=len(list(self.archive_restores.iterdir())), independent_withdrawal_controls_external=True,
                      comparison_read_only=True, restore_grants_or_activation_created=False)
        return result
