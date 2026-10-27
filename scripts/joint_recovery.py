"""Explicit per-anchor reconciliation of causally related admitted tails."""

from contextlib import ExitStack

import operator_enrollment_evidence as e
from authenticated_operator_review import PREFIX, conflict
from destination_change_log import scope_for
from journal_recovery import JournalRecovery
from operator_review_journal import reject

JOINT = {"joint_observe", "joint_apply", "joint_finish_observe"}


class JointRecovery(JournalRecovery):
    management = JournalRecovery.management | JOINT

    def joint_view(self, actor, ident, window, namespace, legacy, destination, canonical):
        view = self.view(actor, ident, "window", window, namespace, legacy, destination, canonical)
        if (view["phase"] != "finished" or window[2][-1]["kind"] != "finished"
                or destination[2][-1]["kind"] not in {"selected", "retired"}):
            conflict()
        # Existing projection checks bind the exact child, independent review,
        # transition and retained finish. Only anchor positions may progress.
        names = {"change_id", "window_tip_sha256", "destination_tip_sha256", "namespace_head_sha256",
                 "legacy_head_sha256", "revocation_head_sha256", "context_sha256", "history_sha256",
                 "scope_sha256", "actor_sha256", "finish_sha256"}
        plan = {k: view[k] for k in names}
        view["plan_sha256"] = e.sha(e.encode({"schema": "joint-recovery-plan-v1", **plan}))
        view["next_target"] = "destination" if "destination" in view["pending"] else "window" if "window" in view["pending"] else None
        view["progress"] = "reconciled" if not view["pending"] else "destination_pending" if "destination" in view["pending"] else "window_pending"
        view["view_sha256"] = e.sha(e.encode({k: v for k, v in view.items() if k != "view_sha256"}))
        return view

    def handle(self, scope, value):
        action = scope["path"][len(PREFIX):]
        if action not in JOINT:
            return super().handle(scope, value)
        actor = self.inner.inner.assigned(scope)
        fields = {"joint_observe": {"change_id"},
                  "joint_apply": {"change_id", "target", "expected_plan_sha256", "expected_view_sha256"},
                  "joint_finish_observe": {"change_id", "expected_plan_sha256", "expected_view_sha256", "expected_finish_sha256"}}
        if set(value) != fields[action]:
            reject()
        ident = e.token(value["change_id"], 32)
        target = value.get("target", "window")
        if not isinstance(target, str) or target not in {"window", "destination"}:
            reject()
        with self.change_lock, ExitStack() as stack:
            window = stack.enter_context(self.changes.locked(write=action == "joint_apply" and target == "window", recovery=True))
            if self.changes.scope != scope_for(self, self.changes.root):
                reject()
            namespace = stack.enter_context(self.controls.locked())
            legacy = stack.enter_context(self.legacy.controls.locked())
            destination = stack.enter_context(self.destination.controls.locked(write=action == "joint_apply" and target == "destination", recovery=True))
            canonical = stack.enter_context(self.inner.inner.revocations.locked())
            view = self.joint_view(actor, ident, window, namespace, legacy, destination, canonical)
            self.authority.recheck(actor, now=e.stamp(self.clock()))
            flags = {"authority_renewed": False, "atomic_joint_write": False, **dict.fromkeys(e.FLAGS, False)}
            if action == "joint_observe":
                return {"status": "joint_context_observed", **view, **flags}
            if value["expected_plan_sha256"] != view["plan_sha256"] or value["expected_view_sha256"] != view["view_sha256"]:
                conflict()
            if action == "joint_finish_observe":
                if value["expected_finish_sha256"] != view["finish_sha256"]:
                    conflict()
                return {"status": "joint_finish_reconciled_readonly", **view, **flags}
            if view["next_target"] is not None and target != view["next_target"]:
                conflict()
            control, frame = (self.changes, window) if target == "window" else (self.destination.controls, destination)
            fd, head, _, tip = frame
            changed = head != tip
            if changed:
                control.anchor.append(fd, head, tip)
                self.point("joint_" + target + "_anchor_complete")
            self.authority.recheck(actor, now=e.stamp(self.clock()))
            return {"status": "joint_anchor_reconciled" if changed else "joint_already_reconciled",
                    "target": target, "head_sha256": tip["head"], "plan_sha256": view["plan_sha256"], "repaired": changed, **flags}
