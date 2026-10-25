"""Encrypted withdrawal history staged against the current independent fence."""

from pathlib import Path

import operator_enrollment_evidence as e
from cryptography.fernet import Fernet
from enrollment_revocation_log import RevocationLog, fold
from operator_review_journal import reject
from review_history_backup import MAX_BACKUPS, MAX_PLAIN, read_blob, write_blob

SCHEMA = "disposable-withdrawal-history-v1"


class WithdrawalVault:
    def __init__(self, service, bundles, manifests, restores, key, *, checkpoint=None):
        from enrollment_revocation import EnrollmentRevocation

        if not isinstance(service, EnrollmentRevocation):
            reject()
        self.service, self.log = service, service.revocations
        self.bundles, self.manifests, self.restores = [e.directory(p) for p in (bundles, manifests, restores)]
        self.key = Path(key)
        self.custody = service.inner.children[service.inner.initial].custody
        if self.custody.key_path != self.key:
            reject()
        self.custody.check(0)
        self.key_sha = e.sha(e.read(self.key))
        Fernet(e.read(self.key))
        if len({self.log.root, self.log.anchor.path.parent.resolve(), self.bundles, self.manifests, self.restores, self.key.parent.resolve()}) != 6:
            reject()
        self.checkpoint = checkpoint

    def point(self, name):
        if self.checkpoint:
            self.checkpoint(name)

    def cipher(self):
        self.custody.check(0)
        raw = e.read(self.key)
        if e.sha(raw) != self.key_sha:
            reject()
        return Fernet(raw)

    def context(self, fence, events, now):
        if now < (events[-1]["payload"]["created_at"] if events else self.log.scope["created_at"]):
            reject()
        _, withdrawn = fold(events, self.log.scope)
        snapshot = self.service.fresh(withdrawn, now)
        return e.sha(e.encode({"basis_sha256": snapshot["basis_sha256"], "revocation_head_sha256": fence["head"]}))

    def snapshot(self, fence, events, context):
        names = ["metadata.json", *(f"{event['seq']:04x}.json" for event in events)]
        value = {"schema": SCHEMA, "journal_id": self.log.identity, "scope": self.log.scope, "head": fence,
                 "context_sha256": context, "files": [[name, e.read(self.log.root / name).decode()] for name in names]}
        if len(e.encode(value)) > MAX_PLAIN:
            reject()
        return value

    def backup(self, ident, fence, events, context, recheck):
        e.token(ident, 32)
        if len(list(self.bundles.iterdir())) >= MAX_BACKUPS or len(list(self.manifests.iterdir())) >= MAX_BACKUPS:
            reject()
        raw = e.encode(self.snapshot(fence, events, context))
        encrypted = self.cipher().encrypt(raw)
        manifest = {"schema": SCHEMA, "backup_id": ident, "journal_id": self.log.identity,
                    "scope_sha256": e.sha(e.encode(self.log.scope)), "head_sha256": fence["head"], "context_sha256": context,
                    "plaintext_sha256": e.sha(raw), "ciphertext_sha256": e.sha(encrypted), **dict.fromkeys(e.FLAGS, False)}
        recheck()
        write_blob(self.bundles / (ident + ".withdrawal"), encrypted)
        self.log.api.sealed_volume.sync_dir(self.bundles)
        self.point("withdrawal_blob_retained")
        recheck()
        pin = e.retain(self.manifests / (ident + ".json"), e.encode(manifest))["sha256"]
        self.log.api.sealed_volume.sync_dir(self.manifests)
        self.point("withdrawal_manifest_retained")
        recheck()
        return {"status": "withdrawal_backup_retained", "manifest_sha256": pin, **dict.fromkeys(e.FLAGS, False)}

    def load(self, ident, pin, fence, events, context):
        e.token(ident, 32)
        raw = e.read(self.manifests / (ident + ".json"))
        m = e.decode(raw)
        encrypted = read_blob(self.bundles / (ident + ".withdrawal"))
        plain = self.cipher().decrypt(encrypted)
        expected = {"schema": SCHEMA, "backup_id": ident, "journal_id": self.log.identity,
                    "scope_sha256": e.sha(e.encode(self.log.scope)), "head_sha256": fence["head"], "context_sha256": context,
                    "plaintext_sha256": e.sha(plain), "ciphertext_sha256": e.sha(encrypted), **dict.fromkeys(e.FLAGS, False)}
        if e.token(pin) != e.sha(raw) or m != expected or len(plain) > MAX_PLAIN or plain != e.encode(self.snapshot(fence, events, context)):
            reject()
        return e.decode(plain)

    def restored(self, ident):
        root = e.directory(self.restores / e.token(ident, 32))
        return RevocationLog(root / "journal", self.log.anchor.path, self.log.scope, self.log.identity, self.log.api)

    def restore(self, ident, backup, pin, fence, events, context, actor, recheck):
        e.token(ident, 32)
        if len(list(self.restores.iterdir())) >= MAX_BACKUPS:
            reject()
        value = self.load(backup, pin, fence, events, context)
        recheck()
        root = self.restores / ident
        root.mkdir(mode=0o700)
        (root / "journal").mkdir(mode=0o700)
        intent = {"schema": SCHEMA, "restore_id": ident, "backup_id": backup, "manifest_sha256": pin,
                  "journal_id": self.log.identity, "head_sha256": fence["head"], "context_sha256": context,
                  "prepared_by": actor, **dict.fromkeys(e.FLAGS, False)}
        intent_pin = e.retain(root / "intent.json", e.encode(intent))["sha256"]
        self.log.api.sealed_volume.sync_dir(root)
        self.log.api.sealed_volume.sync_dir(self.restores)
        self.point("withdrawal_restore_intent_retained")
        for name, raw in value["files"]:
            recheck()
            e.retain(root / "journal" / name, raw.encode())
        self.log.api.sealed_volume.sync_dir(root / "journal")
        self.point("withdrawal_restore_files_retained")
        self.restored(ident).scan(fence)  # Independent anchor and admission intents stay external.
        recheck()
        receipt = {**intent, "intent_sha256": intent_pin, "snapshot_sha256": e.sha(e.encode(value)), "events": len(events)}
        receipt_pin = e.retain(root / "receipt.json", e.encode(receipt))["sha256"]
        self.log.api.sealed_volume.sync_dir(root)
        self.point("withdrawal_restore_receipt_retained")
        recheck()
        return {"status": "withdrawal_history_staged_needs_independent_comparison", "intent_sha256": intent_pin,
                "receipt_sha256": receipt_pin, **dict.fromkeys(e.FLAGS, False)}

    def status(self, ident, intent_pin, receipt_pin, fence, events, context, actor, recheck):
        root = e.directory(self.restores / e.token(ident, 32))
        raw = e.read(root / "intent.json")
        receipt_raw = e.read(root / "receipt.json") if (root / "receipt.json").exists() else None
        pins = {"intent_sha256": e.sha(raw), "receipt_sha256": e.sha(receipt_raw) if receipt_raw else None}
        recheck()
        if intent_pin is None and receipt_pin is None:
            return {"status": "withdrawal_restore_observed_needs_pin", **pins, **dict.fromkeys(e.FLAGS, False)}
        intent = e.decode(raw)
        if (pins != {"intent_sha256": intent_pin, "receipt_sha256": receipt_pin} or actor["kind"] != "reviewer"
                or actor["user_id"] == intent["prepared_by"]["user_id"] or intent["restore_id"] != ident
                or intent["journal_id"] != self.log.identity or intent["head_sha256"] != fence["head"] or intent["context_sha256"] != context
                or any(intent[k] is not False for k in e.FLAGS)):
            reject()
        self.service.authority.recheck(intent["prepared_by"], now=e.stamp(self.service.clock()))
        status = "withdrawal_restore_incomplete"
        if receipt_raw:
            value = self.load(intent["backup_id"], intent["manifest_sha256"], fence, events, context)
            receipt = e.decode(receipt_raw)
            expected = {**intent, "intent_sha256": pins["intent_sha256"], "snapshot_sha256": e.sha(e.encode(value)), "events": len(events)}
            restored_events, tip = self.restored(ident).scan(fence)
            if receipt != expected or tip != fence or restored_events != events:
                reject()
            _, withdrawn = fold(restored_events, self.log.scope)
            status = "withdrawal_history_matches_current_fence"
        else:
            withdrawn = {}
        recheck()
        return {"status": status, **pins, "retained_withdrawals": len(withdrawn), **dict.fromkeys(e.FLAGS, False)}
