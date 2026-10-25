"""Disposable restore grants and guarded read-only selection; never live activation."""

import operator_enrollment_evidence as e
from authenticated_operator_review import PREFIX, ReviewHandoff, conflict
from operator_review_journal import reject
from restore_control_log import RestoreControlLog, fold, ref
from restore_key_custody import KeyCustody, file_id
from review_history_service import HistoryService


class RestoreAuthorization(HistoryService):
    actions = (*HistoryService.actions, "restore_control", "restore_control_recover", "key_custody_status",
               "prepare_restore", "authorize_restore", "execute_restore", "revoke_restore", "reconcile_restore",
               "select_restored_target", "selected_history")

    def __init__(self, authority, target, ledger, journal, vault, custody, controls, **kwargs):
        if not isinstance(custody, KeyCustody) or not isinstance(controls, RestoreControlLog) or custody.key_path != vault.key_path:
            reject()
        expected = {**journal.scope, "review_journal_id": journal.identity, "custody_sha256": custody.approved,
                    "restore_root_sha256": e.sha(e.encode(file_id(vault.restores)))}
        if controls.scope != expected:
            reject()
        self.custody, self.controls = custody, controls
        super().__init__(authority, target, ledger, journal, vault, **kwargs)

    def target_ref(self, ident):
        root = e.sha(e.encode(file_id(self.vault.restores)))
        if root != self.controls.scope["restore_root_sha256"]:
            conflict()
        return e.sha(e.encode({"root": root, "target": e.token(ident, 32), "journal": self.journal.identity, "scope": self.journal.scope}))

    def grant_current(self, state, actor, now, *, approved=False):
        p = state["prepared"]["payload"]
        if "revoked" in state or not p["created_at"] <= now < p["expires_at"] or p["target_sha256"] != self.target_ref(p["operation_id"]):
            conflict()
        self.custody.check(now)
        self.target.fast(now)
        if p["packet_sha256"] != self.target.packet_sha256 or p["observation_sha256"] != self.target.observation_sha256:
            conflict()
        self.authority.recheck(p["prepared_by"], now=now)
        if self.authority.eligible(p["reviewer"]["user_id"], "reviewer") != p["reviewer"]:
            conflict()
        if "decision" in state:
            self.authority.recheck(state["decision"]["payload"]["reviewed_by"], now=now)
        if approved and ("decision" not in state or state["decision"]["payload"]["decision"] != "approve"):
            conflict()
        with self.journal.anchor.locked() as (_, fence):
            if fence["head"] != p["review_head_sha256"]:
                conflict()
            self.vault.load(p["backup_id"], p["manifest_sha256"], fence)
        self.authority.recheck(actor, now=now)

    def handle(self, scope, value):
        action = scope["path"][len(PREFIX):]
        if action == "restore":
            self.assigned(scope)
            conflict()  # The inherited direct restore route cannot bypass grants.
        new = set(self.actions) - set(HistoryService.actions)
        if action not in new:
            if action == "backup":
                self.assigned(scope)
                self.custody.check(e.stamp(self.clock()))
            result = super().handle(scope, value)
            if action == "backup":
                self.custody.check(e.stamp(self.clock()))
            return result
        with self.admission:
            actor = self.assigned(scope)
            now = e.stamp(self.clock())
            if action == "key_custody_status":
                if value:
                    reject()
                try:
                    self.custody.check(now)
                    status = "key_custody_bound_for_disposable_restore"
                except Exception:
                    status = "key_custody_stale_retained"
                self.authority.recheck(actor, now=e.stamp(self.clock()))
                return {"status": status, "custody_sha256": self.custody.approved, **dict.fromkeys(e.FLAGS, False)}
            if action in {"restore_control", "restore_control_recover"}:
                if action == "restore_control" and value:
                    reject()
                if action == "restore_control_recover" and set(value) != {"expected_head_sha256", "expected_tip_sha256", "repair"}:
                    reject()
                repair = value.get("repair", False)
                if type(repair) is not bool:
                    reject()
                with self.controls.locked(write=repair, recovery=action == "restore_control_recover") as (fd, fence, events, tip):
                    if repair:
                        if value["expected_head_sha256"] != fence["head"] or value["expected_tip_sha256"] != tip["head"]:
                            conflict()
                        self.authority.recheck(actor, now=e.stamp(self.clock()))
                        if tip != fence:
                            self.controls.anchor.append(fd, fence, tip)
                    self.authority.recheck(actor, now=e.stamp(self.clock()))
                    return {"status": "restore_control_reconciled" if repair else "restore_control_observed",
                            "control_head_sha256": tip["head"] if repair else fence["head"], "control_tip_sha256": tip["head"],
                            "events": len(events), **dict.fromkeys(e.FLAGS, False)}
            fields = {
                "prepare_restore": {"operation_id", "backup_id", "manifest_sha256", "expected_review_head_sha256", "expected_control_head_sha256"},
                "authorize_restore": {"operation_id", "prepared_sha256", "decision", "reason_code", "expected_control_head_sha256"},
                "execute_restore": {"operation_id", "authorization_sha256", "expected_control_head_sha256"},
                "revoke_restore": {"operation_id", "expected_control_head_sha256"},
                "reconcile_restore": {"operation_id", "intent_sha256", "receipt_sha256", "expected_control_head_sha256"},
                "select_restored_target": {"operation_id", "selection_id", "authorization_sha256", "intent_sha256", "receipt_sha256", "expected_control_head_sha256"},
                "selected_history": {"selection_id", "selection_sha256", "handoff_id", "handoff_sha256", "decision_sha256", "expected_control_head_sha256"},
            }
            if action not in fields or set(value) != fields[action]:
                reject()
            with self.controls.locked(write=action not in {"selected_history", "reconcile_restore"}) as (fd, fence, events, _):
                if e.token(value["expected_control_head_sha256"]) != fence["head"]:
                    conflict()
                operations, selections = fold(events, self.controls.scope)
                if action == "prepare_restore":
                    if actor["kind"] != "preparer":
                        conflict()
                    ident = e.token(value["operation_id"], 32)
                    if ident in operations:
                        conflict()
                    self.target.full(now)
                    p, o = self.target.source(now)
                    key = self.custody.check(now)
                    with self.journal.anchor.locked() as (_, review):
                        if review["head"] != e.token(value["expected_review_head_sha256"]):
                            conflict()
                        self.vault.load(value["backup_id"], value["manifest_sha256"], review)
                    payload = {"operation_id": ident, "backup_id": value["backup_id"], "manifest_sha256": value["manifest_sha256"],
                               "review_head_sha256": review["head"], "target_sha256": self.target_ref(ident), "custody_sha256": self.custody.approved,
                               "packet_sha256": self.target.packet_sha256, "observation_sha256": self.target.observation_sha256,
                               "prepared_by": actor, "reviewer": self.authority.eligible(p["enrollment"]["reviewer"], "reviewer"),
                               "created_at": now, "expires_at": min(now + 300, p["expires_at"], o["valid_until"], actor["expires_at"], key["expires_at"]), **dict.fromkeys(e.FLAGS, False)}
                    self.grant_current({"prepared": {"payload": payload}}, actor, e.stamp(self.clock()))
                    event = self.controls.append(fd, fence, events, "prepared", payload)
                    self.grant_current({"prepared": event}, actor, e.stamp(self.clock()))
                    return {"status": "restore_prepared_needs_independent_authorization", "operation_id": ident, "prepared_sha256": ref(event), **dict.fromkeys(e.FLAGS, False)}
                if action == "selected_history":
                    sid = e.token(value["selection_id"], 32)
                    if sid not in selections or list(selections)[-1] != sid or ref(selections[sid]) != e.token(value["selection_sha256"]):
                        conflict()
                    selected = selections[sid]["payload"]
                    state = operations[selected["operation_id"]]
                    self.grant_current(state, actor, now, approved=True)
                    self.vault.status(selected["operation_id"], selected["restore_intent_sha256"], selected["restore_receipt_sha256"], lambda: self.authority.recheck(actor, now=e.stamp(self.clock())))
                    journal = self.vault.restored(selected["operation_id"])
                    with journal.locked():
                        reader = ReviewHandoff(self.authority, self.target, journal.ledger, clock=self.clock)
                        handoff = reader.read_record(value["handoff_id"], "handoff", value["handoff_sha256"])
                        decision = reader.read_record(value["handoff_id"], "decision", value["decision_sha256"])
                        if decision["handoff_sha256"] != value["handoff_sha256"] or any(decision[k] != v for k, v in handoff.items() if k != "schema"):
                            conflict()
                        try:
                            reader.current(decision, actor, now)
                            status = "selected_exact_history_readable"
                        except Exception:
                            status = "selected_stale_review_retained"
                    self.grant_current(state, actor, e.stamp(self.clock()), approved=True)
                    return {"status": status, "selection_id": sid, "decision_sha256": value["decision_sha256"], "decision": decision["decision"], **dict.fromkeys(e.FLAGS, False)}
                ident = e.token(value["operation_id"], 32)
                if ident not in operations:
                    conflict()
                state, payload = operations[ident], {"operation_id": ident, "created_at": now, **dict.fromkeys(e.FLAGS, False)}
                if action == "reconcile_restore":
                    if "consumed" not in state:
                        conflict()
                    if not (self.vault.restores / ident).exists():
                        return {"status": "consumed_restore_not_materialized", **dict.fromkeys(e.FLAGS, False)}
                    result = self.vault.status(ident, value["intent_sha256"], value["receipt_sha256"], lambda: self.authority.recheck(actor, now=e.stamp(self.clock())))
                    return {**result, "operation_id": ident}
                if action == "revoke_restore":
                    if "revoked" in state:
                        conflict()
                    payload["revoked_by"] = actor
                    event = self.controls.append(fd, fence, events, "revoked", payload)
                    self.authority.recheck(actor, now=e.stamp(self.clock()))
                    return {"status": "restore_grant_revoked", "revocation_sha256": ref(event), **dict.fromkeys(e.FLAGS, False)}
                self.grant_current(state, actor, now, approved=action != "authorize_restore")
                if action == "authorize_restore":
                    if actor["kind"] != "reviewer" or "decision" in state or value["prepared_sha256"] != ref(state["prepared"]):
                        conflict()
                    payload.update(prepared_sha256=value["prepared_sha256"], reviewed_by=actor, decision=value["decision"], reason_code=value["reason_code"])
                    event = self.controls.append(fd, fence, events, "decision", payload)
                    self.grant_current({**state, "decision": event}, actor, e.stamp(self.clock()))
                    return {"status": "restore_authorization_recorded", "authorization_sha256": ref(event), "decision": value["decision"], **dict.fromkeys(e.FLAGS, False)}
                if value["authorization_sha256"] != ref(state["decision"]):
                    conflict()
                if action == "select_restored_target":
                    if actor["kind"] != "reviewer" or "consumed" not in state:
                        conflict()
                    e.token(value["intent_sha256"])
                    e.token(value["receipt_sha256"])
                    status = self.vault.status(ident, value["intent_sha256"], value["receipt_sha256"], lambda: self.authority.recheck(actor, now=e.stamp(self.clock())))
                    if status["status"] != "restored_exact_history_retained":
                        conflict()
                    payload.update(selection_id=e.token(value["selection_id"], 32), authorization_sha256=value["authorization_sha256"],
                                   restore_intent_sha256=value["intent_sha256"], restore_receipt_sha256=value["receipt_sha256"], selected_by=actor)
                    event = self.controls.append(fd, fence, events, "selected", payload)
                    self.grant_current(state, actor, e.stamp(self.clock()), approved=True)
                    return {"status": "restored_target_selected_for_disposable_reads", "selection_sha256": ref(event), **dict.fromkeys(e.FLAGS, False)}
                if actor != state["prepared"]["payload"]["prepared_by"] or "consumed" in state:
                    conflict()
                payload.update(authorization_sha256=value["authorization_sha256"], executed_by=actor)
                consumed = self.controls.append(fd, fence, events, "consumed", payload)
                # Retain consumption before materialization while holding the
                # cross-process control lock. Every path locks controls before
                # the review anchor, so revocation cannot race this operation.
                # An uncertain result is reconciled; it is never executed again.
                def recheck():
                    stamp = e.stamp(self.clock())
                    self.authority.recheck(actor, now=stamp)
                    self.authority.recheck(state["decision"]["payload"]["reviewed_by"], now=stamp)
                    if not state["prepared"]["payload"]["created_at"] <= stamp < state["prepared"]["payload"]["expires_at"]:
                        conflict()
                    self.custody.check(stamp)
                    self.target.fast(stamp)
                    if self.target_ref(ident) != state["prepared"]["payload"]["target_sha256"]:
                        conflict()
                prepared = state["prepared"]["payload"]
                result = self.vault.restore(ident, prepared["backup_id"], prepared["manifest_sha256"], prepared["review_head_sha256"], recheck)
                self.grant_current({**state, "consumed": consumed}, actor, e.stamp(self.clock()), approved=True)
                self.point("authorized_restore_complete")
                return {**result, "authorization_sha256": value["authorization_sha256"]}
