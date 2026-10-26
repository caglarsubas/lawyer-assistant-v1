"""Unregistered reader retirement and independently reviewed rollback/renewal."""

import operator_enrollment_evidence as e
from authenticated_operator_review import PREFIX, ReviewHandoff, conflict
from enrollment_revocation_log import fold as withdrawals
from operator_review_journal import actor as validate_actor
from operator_review_journal import reject
from reader_lifecycle_log import ReaderLifecycleLog, fold, lineage
from restore_control_log import ref
from restore_inventory import page
from restore_key_custody import file_id
from staged_reader_log import scope_for
from withdrawal_history_backup import SCHEMA as ARCHIVE_SCHEMA
from withdrawal_history_service import WithdrawalHistory


def stage_subject(vault, ident, intent_pin, receipt_pin, fence, events, context, now):
    root = e.directory(vault.restores / e.token(ident, 32))
    raw, receipt_raw = e.read(root / "intent.json"), e.read(root / "receipt.json")
    if e.sha(raw) != e.token(intent_pin) or e.sha(receipt_raw) != e.token(receipt_pin):
        reject()
    intent = e.decode(raw)
    validate_actor(intent["prepared_by"], session=True)
    expected = {"schema": ARCHIVE_SCHEMA, "restore_id": ident, "backup_id": intent["backup_id"],
                "manifest_sha256": intent["manifest_sha256"], "journal_id": vault.log.identity,
                "head_sha256": fence["head"], "context_sha256": context, "prepared_by": intent["prepared_by"],
                **dict.fromkeys(e.FLAGS, False)}
    if intent != expected or intent["prepared_by"]["kind"] != "preparer":
        reject()
    vault.service.authority.recheck(intent["prepared_by"], now=now)
    value = vault.load(intent["backup_id"], intent["manifest_sha256"], fence, events, context)
    restored, tip = vault.restored(ident).scan(fence)
    if (restored != events or tip != fence or e.decode(receipt_raw) != {**intent, "intent_sha256": intent_pin,
            "snapshot_sha256": e.sha(e.encode(value)), "events": len(events)}):
        reject()
    return {"stage_id": ident, "intent_sha256": intent_pin, "receipt_sha256": receipt_pin,
            "journal_id": vault.log.identity, "revocation_head_sha256": fence["head"], "context_sha256": context,
            "stage_root_sha256": e.sha(e.encode(file_id(root / "journal"))), "snapshot_sha256": e.sha(e.encode(value))}, intent["prepared_by"]


class ReaderLifecycle(ReviewHandoff):
    management = {"reader_observe", "reader_prepare", "reader_decide", "reader_select", "reader_status", "reader_recover", "reader_inventory", "reader_retire"}

    def __init__(self, inner, controls, **kwargs):
        if not isinstance(inner, WithdrawalHistory) or not isinstance(controls, ReaderLifecycleLog) or controls.scope != scope_for(inner, controls.root):
            reject()
        if len({controls.root, controls.anchor.path.parent.resolve(), inner.inner.revocations.root,
                inner.inner.revocations.anchor.path.parent.resolve(), inner.vault.restores}) != 5:
            reject()
        self.inner, self.controls = inner, controls
        self.actions = (*inner.actions, *sorted(self.management))
        super().__init__(inner.authority, inner.target, inner.ledger, **kwargs)

    def current(self, state, actor, fence, events, context):
        p, now = state["proposed"]["payload"], e.stamp(self.clock())
        if (not p["created_at"] <= now < p["expires_at"] or p["subject"]["revocation_head_sha256"] != fence["head"]
                or p["subject"]["context_sha256"] != context):
            conflict()
        self.authority.recheck(p["prepared_by"], now=now)
        if self.authority.eligible(p["reviewer"]["user_id"], "reviewer") != p["reviewer"]:
            conflict()
        if "decided" in state:
            self.authority.recheck(state["decided"]["payload"]["reviewed_by"], now=now)
        subject, prepared = stage_subject(self.inner.vault, p["subject"]["stage_id"], p["subject"]["intent_sha256"],
                                           p["subject"]["receipt_sha256"], fence, events, context, now)
        if subject != p["subject"] or prepared != p["prepared_by"]:
            reject()
        if self.inner.vault.context(fence, events, e.stamp(self.clock())) != context:
            conflict()
        self.authority.recheck(actor, now=e.stamp(self.clock()))

    def handle(self, scope, value):
        action = scope["path"][len(PREFIX):]
        if action not in self.management:
            return self.inner.handle(scope, value)  # Ordinary writes never use the staged journal.
        actor = self.inner.inner.assigned(scope)  # Authenticate before reading any reader-control metadata.
        repair = action == "reader_recover" and value.get("repair") is True
        with self.lock, self.controls.locked(write=action in {"reader_prepare", "reader_decide", "reader_select", "reader_retire"} or repair,
                                           recovery=action == "reader_recover") as (fd, head, history, tip), self.inner.inner.revocations.locked() as (_, fence, events, _):
            now = e.stamp(self.clock())
            if self.controls.scope != scope_for(self.inner, self.controls.root) or now < (history[-1]["payload"]["created_at"] if history else self.controls.scope["created_at"]):
                reject()
            proposals, last, retired = fold(history, self.controls.scope)
            active = last if last and ref(last) not in retired else None
            context = self.inner.vault.context(fence, events, now)
            observed = {"binding_head_sha256": head["head"], "revocation_head_sha256": fence["head"], "context_sha256": context,
                        "active_selection_sha256": ref(active) if active else None,
                        "last_selection_sha256": ref(last) if last else None,
                        "retirement_sha256": ref(retired[ref(last)]) if last and ref(last) in retired else None, **dict.fromkeys(e.FLAGS, False)}
            if action == "reader_recover":
                if set(value) != {"expected_head_sha256", "expected_tip_sha256", "repair"} or type(value["repair"]) is not bool:
                    reject()
                if repair:
                    if value["expected_head_sha256"] != head["head"] or value["expected_tip_sha256"] != tip["head"]:
                        conflict()
                    self.authority.recheck(actor, now=e.stamp(self.clock()))
                    if head != tip:
                        self.controls.anchor.append(fd, head, tip)
                self.authority.recheck(actor, now=e.stamp(self.clock()))
                return {"status": "reader_log_reconciled" if repair else "reader_log_observed", "binding_head_sha256": tip["head"] if repair else head["head"],
                        "binding_tip_sha256": tip["head"], **dict.fromkeys(e.FLAGS, False)}
            if action == "reader_observe":
                if value:
                    reject()
                self.authority.recheck(actor, now=e.stamp(self.clock()))
                return {"status": "reader_context_observed", **observed}
            fields = {"reader_prepare": {"proposal_id", "stage_id", "intent_sha256", "receipt_sha256", "mode", "predecessor_sha256", "retirement_sha256", "target_selection_sha256"},
                      "reader_decide": {"proposal_id", "proposal_sha256", "decision", "reason_code"},
                      "reader_select": {"proposal_id", "decision_sha256"},
                      "reader_retire": {"proposal_id", "selection_sha256", "reason_code"},
                      "reader_status": {"proposal_id", "decision_sha256", "selection_sha256"},
                      "reader_inventory": {"selection_sha256", "snapshot_sha256", "offset", "limit", "cursor"}}
            common = {"expected_binding_head_sha256", "expected_revocation_head_sha256", "expected_context_sha256"}
            if set(value) != fields[action] | common:
                reject()
            if any(value["expected_" + k] != observed[k] for k in ("binding_head_sha256", "revocation_head_sha256", "context_sha256")):
                conflict()
            if action == "reader_inventory":
                if active is None or value["selection_sha256"] != ref(active):
                    conflict()
                state = proposals[active["payload"]["proposal_id"]]
                self.current(state, actor, fence, events, context)
                _, withdrawn = withdrawals(events, self.inner.inner.revocations.scope)
                snapshot = self.inner.inner.fresh(withdrawn, now)
                snapshot["basis_sha256"] = e.sha(e.encode({"source": snapshot["basis_sha256"], "selection": ref(active), "binding_head": head["head"]}))
                result = page(snapshot, fence["head"], actor, {k: value[k] for k in ("snapshot_sha256", "offset", "limit", "cursor")})
                self.current(state, actor, fence, events, context)
                return {**result, "status": "staged_reader_inventory_observed", "binding_head_sha256": head["head"], "selection_sha256": ref(active)}
            ident = e.token(value["proposal_id"], 32)
            if action == "reader_prepare":
                if actor["kind"] != "preparer" or ident in proposals:
                    conflict()
                subject, prepared = stage_subject(self.inner.vault, value["stage_id"], value["intent_sha256"], value["receipt_sha256"], fence, events, context, now)
                if prepared != actor:
                    conflict()
                packet, _ = self.target.source(now, historical=True)
                payload = {"proposal_id": ident, "subject": subject, "prepared_by": actor,
                           "reviewer": self.authority.eligible(packet["enrollment"]["reviewer"], "reviewer"), "created_at": now,
                           **{k: value[k] for k in ("mode", "predecessor_sha256", "retirement_sha256", "target_selection_sha256")},
                           "expires_at": min(now + 300, actor["expires_at"]), **dict.fromkeys(e.FLAGS, False)}
                lineage(payload, last, retired, proposals)
                self.current({"proposed": {"payload": payload}}, actor, fence, events, context)
                event = self.controls.append(fd, head, history, "proposed", payload)
                self.current({"proposed": event}, actor, fence, events, context)
                return {"status": "reader_needs_independent_decision", "proposal_sha256": ref(event), "binding_head_sha256": event["head"], **dict.fromkeys(e.FLAGS, False)}
            if ident not in proposals:
                conflict()
            state = proposals[ident]
            if action == "reader_retire":
                if (active is None or active["payload"]["proposal_id"] != ident
                        or value["selection_sha256"] != ref(active) or value["reason_code"] != "reader_retired"):
                    conflict()
                original = state["proposed"]["payload"]
                if actor["user_id"] not in {original["prepared_by"]["user_id"], original["reviewer"]["user_id"]}:
                    conflict()
                self.authority.recheck(actor, now=e.stamp(self.clock()))
                event = self.controls.append(fd, head, history, "retired", {"proposal_id": ident,
                    "selection_sha256": ref(active), "retired_by": actor, "reason_code": value["reason_code"],
                    "created_at": now, **dict.fromkeys(e.FLAGS, False)})
                self.authority.recheck(actor, now=e.stamp(self.clock()))
                self.point("reader_retired_complete")
                return {"status": "exact_reader_retired", "retirement_sha256": ref(event),
                        "binding_head_sha256": event["head"], **dict.fromkeys(e.FLAGS, False)}
            if action == "reader_status":
                pins = {"decision_sha256": ref(state["decided"]) if "decided" in state else None,
                        "selection_sha256": ref(state["selected"]) if "selected" in state else None}
                self.authority.recheck(actor, now=e.stamp(self.clock()))
                if value["decision_sha256"] is None and value["selection_sha256"] is None:
                    return {"status": "reader_binding_observed_needs_pin", **pins, **dict.fromkeys(e.FLAGS, False)}
                if any(value[k] != pin for k, pin in pins.items()):
                    conflict()
                current = False
                if "selected" in state and state["selected"] == active:
                    try:
                        self.current(state, actor, fence, events, context)
                        current = True
                    except Exception:
                        pass  # Retained metadata is not renewed authority.
                self.authority.recheck(actor, now=e.stamp(self.clock()))
                return {"status": "reader_binding_retained", **pins, "usable": current,
                        "active": "selected" in state and state["selected"] == active,
                        "decision": state["decided"]["payload"]["decision"] if "decided" in state else None,
                        "mode": state["proposed"]["payload"]["mode"],
                        "predecessor_sha256": state["proposed"]["payload"]["predecessor_sha256"],
                        "retirement_sha256": ref(state["retired"]) if "retired" in state else None, **dict.fromkeys(e.FLAGS, False)}
            if (action == "reader_select" and "selected" in state) or (action == "reader_decide" and "decided" in state):
                conflict()
            lineage(state["proposed"]["payload"], last, retired, proposals)
            self.current(state, actor, fence, events, context)
            if action == "reader_decide":
                if actor["kind"] != "reviewer" or "decided" in state or value["proposal_sha256"] != ref(state["proposed"]):
                    conflict()
                payload = {"proposal_id": ident, "proposal_sha256": value["proposal_sha256"], "reviewed_by": actor,
                           "decision": value["decision"], "reason_code": value["reason_code"], "created_at": now, **dict.fromkeys(e.FLAGS, False)}
                event = self.controls.append(fd, head, history, "decided", payload)
                self.current({**state, "decided": event}, actor, fence, events, context)
                return {"status": "reader_decision_retained", "decision_sha256": ref(event), "binding_head_sha256": event["head"], **dict.fromkeys(e.FLAGS, False)}
            if (actor != state["proposed"]["payload"]["prepared_by"] or "selected" in state or "decided" not in state
                    or state["decided"]["payload"]["decision"] != "approve" or value["decision_sha256"] != ref(state["decided"])):
                conflict()
            event = self.controls.append(fd, head, history, "selected", {"proposal_id": ident, "decision_sha256": value["decision_sha256"],
                                         "selected_by": actor, "created_at": now, **dict.fromkeys(e.FLAGS, False)})
            self.current(state, actor, fence, events, context)
            self.point("reader_selected_complete")
            return {"status": "disposable_reader_selected", "selection_sha256": ref(event), "binding_head_sha256": event["head"], **dict.fromkeys(e.FLAGS, False)}
