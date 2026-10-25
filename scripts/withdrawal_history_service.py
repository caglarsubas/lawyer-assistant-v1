"""Authenticated disposable archive actions; comparison grants no activation."""

import operator_enrollment_evidence as e
from authenticated_operator_review import PREFIX, ReviewHandoff, conflict
from operator_review_journal import reject


class WithdrawalHistory(ReviewHandoff):
    management = {"withdrawal_snapshot", "backup_withdrawal_history", "restore_withdrawal_history", "withdrawal_restore_status"}

    def __init__(self, inner, vault, **kwargs):
        from enrollment_revocation import EnrollmentRevocation
        from withdrawal_history_backup import WithdrawalVault

        if not isinstance(inner, EnrollmentRevocation) or not isinstance(vault, WithdrawalVault) or vault.service is not inner:
            reject()
        self.inner, self.vault = inner, vault
        self.actions = (*inner.actions, *sorted(self.management))
        super().__init__(inner.authority, inner.target, inner.ledger, **kwargs)

    def handle(self, scope, value):
        action = scope["path"][len(PREFIX):]
        if action not in self.management:
            return self.inner.handle(scope, value)
        with self.lock, self.inner.revocations.locked() as (_, fence, events, _):
            actor = self.inner.assigned(scope)
            context = self.vault.context(fence, events, e.stamp(self.clock()))
            def recheck():
                self.authority.recheck(actor, now=e.stamp(self.clock()))
                self.target.source(e.stamp(self.clock()), historical=True)
                if self.vault.context(fence, events, e.stamp(self.clock())) != context:
                    conflict()
            recheck()
            if action == "withdrawal_snapshot":
                if value:
                    reject()
                return {"status": "withdrawal_snapshot_observed", "context_sha256": context,
                        "revocation_head_sha256": fence["head"], **dict.fromkeys(e.FLAGS, False)}
            fields = {"backup_withdrawal_history": {"backup_id"},
                      "restore_withdrawal_history": {"restore_id", "backup_id", "manifest_sha256"},
                      "withdrawal_restore_status": {"restore_id", "intent_sha256", "receipt_sha256"}}
            common = {"expected_context_sha256", "expected_revocation_head_sha256"}
            if set(value) != fields[action] | common or value["expected_context_sha256"] != context or value["expected_revocation_head_sha256"] != fence["head"]:
                conflict()
            if action == "withdrawal_restore_status":
                return self.vault.status(value["restore_id"], value["intent_sha256"], value["receipt_sha256"], fence, events, context, actor, recheck)
            if actor["kind"] != "preparer":
                conflict()
            if action == "backup_withdrawal_history":
                return self.vault.backup(value["backup_id"], fence, events, context, recheck)
            return self.vault.restore(value["restore_id"], value["backup_id"], value["manifest_sha256"], fence, events, context, actor, recheck)
