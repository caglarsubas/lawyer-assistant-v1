"""Unregistered disposable backup/restore routes; no install or trust authority."""

import operator_enrollment_evidence as e
from anchored_operator_review import AnchoredReviewHandoff
from authenticated_operator_review import PREFIX, conflict
from review_history_backup import HistoryVault


class HistoryService(AnchoredReviewHandoff):
    actions = (*AnchoredReviewHandoff.actions, "backup", "restore", "restore_status")

    def __init__(self, authority, target, ledger, journal, vault, **kwargs):
        if not isinstance(vault, HistoryVault) or vault.journal is not journal:
            raise ValueError("Exact disposable history vault required")
        self.vault = vault
        super().__init__(authority, target, ledger, journal, **kwargs)

    def handle(self, scope, value):
        action = scope["path"][len(PREFIX):]
        if action not in {"backup", "restore", "restore_status"}:
            return super().handle(scope, value)
        with self.admission:
            actor = self.assigned(scope)
            def recheck():
                self.authority.recheck(actor, now=e.stamp(self.clock()))
            fields = {"request_id", "expected_head_sha256"} if action == "backup" else {"request_id", "backup_id", "manifest_sha256", "expected_head_sha256"} if action == "restore" else {"request_id", "intent_sha256", "receipt_sha256"}
            if set(value) != fields:
                raise ValueError("Exact history request fields required")
            try:
                if action == "backup":
                    return self.vault.backup(value["request_id"], value["expected_head_sha256"], recheck)
                if action == "restore":
                    return self.vault.restore(value["request_id"], value["backup_id"], value["manifest_sha256"], value["expected_head_sha256"], recheck)
                return self.vault.status(value["request_id"], value["intent_sha256"], value["receipt_sha256"], recheck)
            except FileExistsError:
                conflict()
