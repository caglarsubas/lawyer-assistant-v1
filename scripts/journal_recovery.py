"""Exact admitted-tail repair and metadata-only finish reconciliation."""

from contextlib import ExitStack

import operator_enrollment_evidence as e
from authenticated_operator_review import PREFIX, conflict
from destination_change import DestinationChange
from destination_change_log import fold, scope_for
from operator_review_journal import reject
from reader_namespace_log import fold as transitions
from restore_control_log import ref

RECOVERY = {"recovery_observe", "recovery_apply", "finish_observe"}


class JournalRecovery(DestinationChange):
    management = DestinationChange.management | RECOVERY

    def view(self, actor, ident, target, window, namespace, legacy, destination, canonical):
        _, wh, ws, wt = window
        _, nh, ns, _ = namespace
        _, lh, ls, _ = legacy
        _, dh, ds, dt = destination
        _, fence, events, _ = canonical
        states, opened = fold(ws, self.changes.scope)
        if ident not in states:
            conflict()
        state, now = states[ident], e.stamp(self.clock())
        p = state["proposed"]["payload"]
        times = [row["payload"].get("created_at", self.changes.scope["created_at"]) for rows in (ws, ns, ls, ds, events) for row in rows]
        if now < max([self.changes.scope["created_at"], *times]):
            conflict()
        if actor["user_id"] not in {p["prepared_by"]["user_id"], p["reviewer"]["user_id"]}:
            conflict()
        if lh["head"] != p["subject"]["legacy_head_sha256"] or e.sha(e.encode(ls)) != p["subject"]["legacy_history_sha256"]:
            conflict()
        # A changed canonical fence is observed explicitly. Repairing retained
        # evidence is not a grant to use that evidence against today's source.
        historical = {events[0]["previous"] if events else fence["head"]}
        historical.update(row["head"] for row in events)
        if p["subject"]["revocation_head_sha256"] not in historical:
            conflict()
        data = {"ns": ns, "ds": ds, "fence": fence, "events": events}
        if "opened" in state:
            if state["opened"] != opened:
                conflict()
            phase, _, _ = self.projection(state, data)
            if "finished" in state:
                final = state["finished"]["payload"]
                _, active = transitions(ns, self.controls.scope)
                if (phase != ("retired" if p["terms"]["mode"] == "retirement" else "transition_committed")
                        or active is None or final["transition_commit_sha256"] != ref(active)
                        or final["destination_head_sha256"] != dt["head"]):
                    conflict()
        else:
            phase = "decided" if "decided" in state else "proposed"
            if dh != dt or nh["head"] != p["subject"]["transition_head_sha256"] or dt["head"] != p["subject"]["destination_head_sha256"]:
                conflict()
        pending = {name: rows[-1] for name, head, tip, rows in (("window", wh, wt, ws), ("destination", dh, dt, ds)) if head != tip}
        for name, row in pending.items():
            if name == "window" and row["payload"]["change_id"] != ident:
                conflict()
            if name == "destination" and "opened" not in state:
                conflict()
        context = self.inner.vault.context(fence, events, now)
        result = {"target": target, "change_id": ident, "window_head_sha256": wh["head"], "window_tip_sha256": wt["head"],
                  "destination_head_sha256": dh["head"], "destination_tip_sha256": dt["head"],
                  "namespace_head_sha256": nh["head"], "legacy_head_sha256": lh["head"],
                  "revocation_head_sha256": fence["head"], "context_sha256": context,
                  "history_sha256": e.sha(e.encode({"window": ws, "namespace": ns, "legacy": ls, "destination": ds})),
                  "scope_sha256": e.sha(e.encode(self.changes.scope)), "actor_sha256": e.sha(e.encode(actor)),
                  "phase": "finished" if "finished" in state else phase,
                  "finish_sha256": ref(state["finished"]) if "finished" in state else None,
                  "finish_state": ("pending_anchor" if wh != wt else "anchored") if "finished" in state else "not_finished",
                  "pending": {k: {"kind": row["kind"], "event_sha256": ref(row)} for k, row in pending.items()},
                  "current_source_matches": p["subject"]["revocation_head_sha256"] == fence["head"] and p["subject"]["context_sha256"] == context}
        result["view_sha256"] = e.sha(e.encode(result))
        return result

    def handle(self, scope, value):
        action = scope["path"][len(PREFIX):]
        if action not in RECOVERY:
            result = super().handle(scope, value)
            if action == "change_finish":
                self.point("finish_reply_complete")
            return result
        actor = self.inner.inner.assigned(scope)  # Before inspection, including malformed/corrupt targets.
        fields = {"recovery_observe": {"change_id", "target"},
                  "recovery_apply": {"change_id", "target", "expected_view_sha256"},
                  "finish_observe": {"change_id", "expected_view_sha256", "expected_finish_sha256"}}
        if set(value) != fields[action]:
            reject()
        ident = e.token(value["change_id"], 32)
        target = "window" if action == "finish_observe" else value["target"]
        if target not in {"window", "destination"}:
            reject()
        with self.change_lock, ExitStack() as stack:
            window = stack.enter_context(self.changes.locked(write=action == "recovery_apply" and target == "window", recovery=True))
            if self.changes.scope != scope_for(self, self.changes.root):
                reject()
            namespace = stack.enter_context(self.controls.locked())
            legacy = stack.enter_context(self.legacy.controls.locked())
            destination = stack.enter_context(self.destination.controls.locked(write=action == "recovery_apply" and target == "destination", recovery=True))
            canonical = stack.enter_context(self.inner.inner.revocations.locked())
            view = self.view(actor, ident, target, window, namespace, legacy, destination, canonical)
            self.authority.recheck(actor, now=e.stamp(self.clock()))
            if action == "recovery_observe":
                return {"status": "recovery_context_observed", **view, "authority_renewed": False, **dict.fromkeys(e.FLAGS, False)}
            if value["expected_view_sha256"] != view["view_sha256"]:
                conflict()
            if action == "finish_observe":
                if value["expected_finish_sha256"] != view["finish_sha256"]:
                    conflict()
                return {"status": "finish_reconciled_readonly", **view, "authority_renewed": False, **dict.fromkeys(e.FLAGS, False)}
            if len(view["pending"]) > 1 or view["pending"] and target not in view["pending"]:
                conflict()  # No implicit joint recovery or repair of another journal.
            control, frame = (self.changes, window) if target == "window" else (self.destination.controls, destination)
            fd, head, _, tip = frame
            changed = head != tip
            if changed:
                control.anchor.append(fd, head, tip)
                self.point("recovery_anchor_complete")
            self.authority.recheck(actor, now=e.stamp(self.clock()))
            return {"status": "retained_anchor_reconciled" if changed else "anchor_already_reconciled",
                    "target": target, "head_sha256": tip["head"], "repaired": changed,
                    "authority_renewed": False, **dict.fromkeys(e.FLAGS, False)}
