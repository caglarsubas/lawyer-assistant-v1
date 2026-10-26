"""Explicit, independently reviewed namespace routing; no production registration."""

from contextlib import ExitStack

import operator_enrollment_evidence as e
from authenticated_operator_review import PREFIX, ReviewHandoff, conflict
from enrollment_revocation_log import fold as withdrawals
from operator_review_journal import reject
from reader_lifecycle import ReaderLifecycle
from reader_lifecycle_log import fold as destination_fold
from reader_namespace_log import NamespaceLog, fold, scope_for
from restore_control_log import ref
from restore_inventory import page
from staged_reader import StagedReader
from staged_reader_log import fold as legacy_fold


class ReaderNamespace(ReviewHandoff):
    management = {"transition_observe", "transition_prepare", "transition_decide", "transition_commit", "transition_status", "transition_recover", "transition_inventory"}

    def __init__(self, legacy, destination, controls, **kwargs):
        if (not isinstance(legacy, StagedReader) or not isinstance(destination, ReaderLifecycle)
                or legacy.inner is not destination.inner or not isinstance(controls, NamespaceLog)
                or controls.scope != scope_for(legacy, destination, controls.root)):
            reject()
        roots = [controls.root, controls.anchor.path.parent.resolve(), legacy.controls.root,
                 legacy.controls.anchor.path.parent.resolve(), destination.controls.root,
                 destination.controls.anchor.path.parent.resolve(), legacy.inner.inner.revocations.root,
                 legacy.inner.inner.revocations.anchor.path.parent.resolve(), legacy.inner.vault.restores]
        if len(set(roots)) != len(roots) or any(a in b.parents for a in roots for b in roots if a != b):
            reject()
        self.legacy, self.destination, self.controls, self.inner = legacy, destination, controls, legacy.inner
        self.delegates = {prefix + action: (child, action) for prefix, child in (("legacy_", legacy), ("destination_", destination)) for action in child.management}
        self.actions = (*self.inner.actions, *sorted(self.management), *sorted(self.delegates))
        super().__init__(legacy.authority, legacy.target, legacy.ledger, **kwargs)

    def subject(self, actor):
        with ExitStack() as stack:
            _, left, le, _ = stack.enter_context(self.legacy.controls.locked())
            _, right, de, _ = stack.enter_context(self.destination.controls.locked())
            _, fence, events, _ = stack.enter_context(self.inner.inner.revocations.locked())
            lp, last = legacy_fold(le, self.legacy.controls.scope)
            dp, selected, retired = destination_fold(de, self.destination.controls.scope)
            if last is None or selected is None or ref(selected) in retired:
                conflict()
            ls, ds = lp[last["payload"]["proposal_id"]], dp[selected["payload"]["proposal_id"]]
            now = e.stamp(self.clock())
            context = self.inner.vault.context(fence, events, now)
            self.legacy.current(ls, actor, fence, events, context)
            self.destination.current(ds, actor, fence, events, context)
            a, b = ls["proposed"]["payload"]["subject"], ds["proposed"]["payload"]["subject"]
            if a["snapshot_sha256"] != b["snapshot_sha256"] or a["stage_id"] == b["stage_id"]:
                conflict()
            value = {"legacy_id": self.legacy.controls.identity, "legacy_head_sha256": left["head"],
                     "legacy_selection_sha256": ref(last), "legacy_history_sha256": e.sha(e.encode(le)),
                     "destination_id": self.destination.controls.identity, "destination_head_sha256": right["head"],
                     "destination_selection_sha256": ref(selected), "destination_history_sha256": e.sha(e.encode(de)),
                     "revocation_head_sha256": fence["head"], "context_sha256": context, "snapshot_sha256": a["snapshot_sha256"],
                     "valid_until": min(ls["proposed"]["payload"]["expires_at"], ds["proposed"]["payload"]["expires_at"],
                                        ls["decided"]["payload"]["reviewed_by"]["expires_at"], ds["decided"]["payload"]["reviewed_by"]["expires_at"])}
            yield value, fence, events
            # Retain source locks across page assembly and both final checks.
            self.legacy.current(ls, actor, fence, events, context)
            self.destination.current(ds, actor, fence, events, context)

    def current(self, state, actor, subject):
        p, now = state["proposed"]["payload"], e.stamp(self.clock())
        if not p["created_at"] <= now < p["expires_at"] or p["subject"] != subject:
            conflict()
        self.authority.recheck(p["prepared_by"], now=now)
        if self.authority.eligible(p["reviewer"]["user_id"], "reviewer") != p["reviewer"]:
            conflict()
        if "decided" in state:
            self.authority.recheck(state["decided"]["payload"]["reviewed_by"], now=now)
        self.authority.recheck(actor, now=e.stamp(self.clock()))

    def handle(self, scope, value):
        from contextlib import contextmanager

        action = scope["path"][len(PREFIX):]
        if action not in self.management and action not in self.delegates:
            return self.inner.handle(scope, value)
        actor = self.inner.inner.assigned(scope)  # Before any transition or reader storage inspection.
        repair = action == "transition_recover" and value.get("repair") is True
        writes = action in {"transition_prepare", "transition_decide", "transition_commit"} or repair
        with self.lock, self.controls.locked(write=writes, recovery=action == "transition_recover") as (fd, head, history, tip):
            if self.controls.scope != scope_for(self.legacy, self.destination, self.controls.root):
                reject()
            now = e.stamp(self.clock())
            if now < (history[-1]["payload"]["created_at"] if history else self.controls.scope["created_at"]):
                reject()
            proposals, active = fold(history, self.controls.scope)
            if action in self.delegates:
                child, operation = self.delegates[action]
                if active is not None or child is self.destination and operation == "reader_inventory":
                    conflict()  # No pre-approval destination use or post-commit namespace bypass.
                forwarded = {**scope, "path": PREFIX + operation, "raw_path": (PREFIX + operation).encode()}
                result = child.handle(forwarded, value)
                self.authority.recheck(actor, now=e.stamp(self.clock()))
                return result
            if action == "transition_recover":
                if set(value) != {"expected_head_sha256", "expected_tip_sha256", "repair"} or type(value["repair"]) is not bool:
                    reject()
                if repair:
                    if value["expected_head_sha256"] != head["head"] or value["expected_tip_sha256"] != tip["head"]:
                        conflict()
                    self.authority.recheck(actor, now=e.stamp(self.clock()))
                    if head != tip:
                        self.controls.anchor.append(fd, head, tip)
                self.authority.recheck(actor, now=e.stamp(self.clock()))
                return {"status": "transition_log_reconciled" if repair else "transition_log_observed", "transition_head_sha256": tip["head"] if repair else head["head"], "transition_tip_sha256": tip["head"], **dict.fromkeys(e.FLAGS, False)}
            if action == "transition_status":
                if set(value) != {"transition_id", "decision_sha256", "commit_sha256"}:
                    reject()
                ident = e.token(value["transition_id"], 32)
                if ident not in proposals:
                    conflict()
                state = proposals[ident]
                pins = {"decision_sha256": ref(state["decided"]) if "decided" in state else None,
                        "commit_sha256": ref(state["committed"]) if "committed" in state else None}
                if value["decision_sha256"] is None and value["commit_sha256"] is None:
                    self.authority.recheck(actor, now=e.stamp(self.clock()))
                    return {"status": "transition_observed_needs_pin", **pins, **dict.fromkeys(e.FLAGS, False)}
                if any(value[k] != v for k, v in pins.items()):
                    conflict()
                usable = False
                if "committed" in state and state["committed"] == active:
                    try:
                        with contextmanager(self.subject)(actor) as (subject, _, _):
                            self.current(state, actor, subject)
                            usable = True
                    except Exception:
                        pass  # Historical observation never refreshes a grant.
                self.authority.recheck(actor, now=e.stamp(self.clock()))
                return {"status": "transition_retained", **pins, "subject": state["proposed"]["payload"]["subject"],
                        "usable": usable, "active": "committed" in state and state["committed"] == active,
                        "transition_head_sha256": head["head"], **dict.fromkeys(e.FLAGS, False)}
            with contextmanager(self.subject)(actor) as (subject, fence, events):
                digest = e.sha(e.encode(subject))
                observed = {"transition_head_sha256": head["head"], "subject_sha256": digest}
                if action == "transition_observe":
                    if value:
                        reject()
                    return {"status": "transition_context_observed", **observed, "subject": subject, **dict.fromkeys(e.FLAGS, False)}
                fields = {"transition_prepare": {"transition_id"}, "transition_decide": {"transition_id", "proposal_sha256", "decision", "reason_code"},
                          "transition_commit": {"transition_id", "decision_sha256"}, "transition_inventory": {"commit_sha256", "snapshot_sha256", "offset", "limit", "cursor"}}
                if set(value) != fields[action] | {"expected_transition_head_sha256", "expected_subject_sha256"}:
                    reject()
                if any(value["expected_" + k] != v for k, v in observed.items()):
                    conflict()
                if action == "transition_inventory":
                    if active is None or value["commit_sha256"] != ref(active):
                        conflict()
                    state = proposals[active["payload"]["transition_id"]]
                    self.current(state, actor, subject)
                    _, withdrawn = withdrawals(events, self.inner.inner.revocations.scope)
                    snapshot = self.inner.inner.fresh(withdrawn, e.stamp(self.clock()))
                    snapshot["basis_sha256"] = e.sha(e.encode({"source": snapshot["basis_sha256"], "transition": ref(active), "head": head["head"], "subject": digest}))
                    result = page(snapshot, fence["head"], actor, {k: value[k] for k in ("snapshot_sha256", "offset", "limit", "cursor")})
                    self.current(state, actor, subject)
                    return {**result, "status": "transition_inventory_observed", "commit_sha256": ref(active), **observed}
                ident = e.token(value["transition_id"], 32)
                if action == "transition_prepare":
                    if actor["kind"] != "preparer" or ident in proposals:
                        conflict()
                    packet, _ = self.target.source(now, historical=True)
                    payload = {"transition_id": ident, "subject": subject, "predecessor_sha256": ref(active) if active else None,
                               "prepared_by": actor, "reviewer": self.authority.eligible(packet["enrollment"]["reviewer"], "reviewer"),
                               "created_at": now, "expires_at": min(now + 300, actor["expires_at"], subject["valid_until"]), **dict.fromkeys(e.FLAGS, False)}
                    self.current({"proposed": {"payload": payload}}, actor, subject)
                    event = self.controls.append(fd, head, history, "proposed", payload)
                    self.current({"proposed": event}, actor, subject)
                    return {"status": "transition_needs_independent_review", "proposal_sha256": ref(event), "transition_head_sha256": event["head"], **dict.fromkeys(e.FLAGS, False)}
                if ident not in proposals:
                    conflict()
                state = proposals[ident]
                p = state["proposed"]["payload"]
                if p["predecessor_sha256"] != (ref(active) if active else None):
                    conflict()
                self.current(state, actor, subject)
                if action == "transition_decide":
                    if actor["kind"] != "reviewer" or "decided" in state or value["proposal_sha256"] != ref(state["proposed"]):
                        conflict()
                    payload = {"transition_id": ident, "proposal_sha256": value["proposal_sha256"], "reviewed_by": actor,
                               "decision": value["decision"], "reason_code": value["reason_code"], "created_at": now, **dict.fromkeys(e.FLAGS, False)}
                    event = self.controls.append(fd, head, history, "decided", payload)
                    self.current({**state, "decided": event}, actor, subject)
                    return {"status": "transition_decision_retained", "decision_sha256": ref(event), "transition_head_sha256": event["head"], **dict.fromkeys(e.FLAGS, False)}
                if (actor != p["prepared_by"] or "committed" in state or "decided" not in state
                        or state["decided"]["payload"]["decision"] != "approve" or value["decision_sha256"] != ref(state["decided"])):
                    conflict()
                event = self.controls.append(fd, head, history, "committed", {"transition_id": ident, "decision_sha256": value["decision_sha256"], "committed_by": actor, "created_at": now, **dict.fromkeys(e.FLAGS, False)})
                self.current(state, actor, subject)
                self.point("namespace_committed_complete")
                return {"status": "reader_namespace_transition_committed", "commit_sha256": ref(event), "transition_head_sha256": event["head"], **dict.fromkeys(e.FLAGS, False)}
