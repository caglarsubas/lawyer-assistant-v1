"""Guarded destination maintenance; historical legacy references never grant access."""

import threading
from contextlib import ExitStack

import operator_enrollment_evidence as e
from authenticated_operator_review import PREFIX, conflict
from destination_change_log import DestinationChangeLog, fold, scope_for, terms
from operator_review_journal import reject
from reader_lifecycle import stage_subject
from reader_lifecycle_log import fold as destination_fold
from reader_namespace import ReaderNamespace
from reader_namespace_log import fold as transition_fold
from restore_control_log import ref
from staged_reader_log import fold as legacy_fold

CHANGE_ACTIONS = {"change_observe", "change_prepare", "change_decide", "change_open", "change_step", "change_status", "change_finish"}


def tail(events, head, digest):
    matches = [n + 1 for n, row in enumerate(events) if row["head"] == head and e.sha(e.encode(events[:n + 1])) == digest]
    if len(matches) != 1:
        conflict()
    return events[matches[0]:]


class DestinationChange(ReaderNamespace):
    management = ReaderNamespace.management | CHANGE_ACTIONS

    def __init__(self, legacy, destination, controls, changes, **kwargs):
        super().__init__(legacy, destination, controls, **kwargs)
        if not isinstance(changes, DestinationChangeLog) or changes.scope != scope_for(self, changes.root):
            reject()
        roots = [changes.root, changes.anchor.path.parent.resolve(), controls.root, controls.anchor.path.parent.resolve(),
                 legacy.controls.root, legacy.controls.anchor.path.parent.resolve(), destination.controls.root,
                 destination.controls.anchor.path.parent.resolve(), self.inner.inner.revocations.root,
                 self.inner.inner.revocations.anchor.path.parent.resolve(), self.inner.vault.restores]
        if len(set(roots)) != len(roots) or any(a in b.parents for a in roots for b in roots if a != b):
            reject()
        self.changes = changes
        self.change_lock = threading.Lock()
        self._change = None

    def snapshot(self):
        with ExitStack() as stack:
            _, nh, ns, _ = stack.enter_context(self.controls.locked())
            _, lh, ls, _ = stack.enter_context(self.legacy.controls.locked())
            _, dh, ds, _ = stack.enter_context(self.destination.controls.locked())
            _, fence, events, _ = stack.enter_context(self.inner.inner.revocations.locked())
            states, active = transition_fold(ns, self.controls.scope)
            _, selected = legacy_fold(ls, self.legacy.controls.scope)
            if active is None or selected is None:
                conflict()
            original = states[active["payload"]["transition_id"]]["proposed"]["payload"]["subject"]
            if lh["head"] != original["legacy_head_sha256"] or e.sha(e.encode(ls)) != original["legacy_history_sha256"]:
                conflict()
            context = self.inner.vault.context(fence, events, e.stamp(self.clock()))
            subject = {"transition_commit_sha256": ref(active), "transition_head_sha256": nh["head"],
                       "legacy_head_sha256": lh["head"], "legacy_history_sha256": e.sha(e.encode(ls)),
                       "destination_head_sha256": dh["head"], "destination_history_sha256": e.sha(e.encode(ds)),
                       "revocation_head_sha256": fence["head"], "context_sha256": context}
            return subject, {"ns": ns, "ds": ds, "fence": fence, "events": events}

    def current_window(self, state, actor, subject):
        p, now = state["proposed"]["payload"], e.stamp(self.clock())
        stable = ("legacy_head_sha256", "legacy_history_sha256", "revocation_head_sha256", "context_sha256")
        if not p["created_at"] <= now < p["expires_at"] or any(p["subject"][k] != subject[k] for k in stable):
            conflict()
        self.authority.recheck(p["prepared_by"], now=now)
        if self.authority.eligible(p["reviewer"]["user_id"], "reviewer") != p["reviewer"]:
            conflict()
        if "decided" in state:
            self.authority.recheck(state["decided"]["payload"]["reviewed_by"], now=now)
        self.authority.recheck(actor, now=e.stamp(self.clock()))

    def projection(self, state, data):
        p = state["proposed"]["payload"]
        rows = tail(data["ds"], p["subject"]["destination_head_sha256"], p["subject"]["destination_history_sha256"])
        if p["terms"]["mode"] == "retirement":
            if len(rows) > 1 or rows and rows[0]["kind"] != "retired" or data["ns"][-1]["head"] != p["subject"]["transition_head_sha256"]:
                conflict()
            if rows:
                original = data["ds"][:-1]
                _, last, _ = destination_fold(original, self.destination.controls.scope)
                if (last is None or rows[0]["payload"]["selection_sha256"] != ref(last)
                        or rows[0]["payload"]["retired_by"] != p["prepared_by"]
                        or not state["opened"]["payload"]["created_at"] <= rows[0]["payload"]["created_at"] < p["expires_at"]):
                    conflict()
            return "retired" if rows else "opened", rows, []
        kinds = [row["kind"] for row in rows]
        if kinds != ["proposed", "decided", "selected"][:len(rows)] or len(rows) > 3:
            conflict()
        for row in rows:
            if row["payload"]["proposal_id"] != p["terms"]["proposal_id"] or not state["opened"]["payload"]["created_at"] <= row["payload"]["created_at"] < p["expires_at"]:
                conflict()
        if rows:
            child = rows[0]["payload"]
            if (child["prepared_by"] != p["prepared_by"] or child["reviewer"] != p["reviewer"]
                    or child["mode"] != p["terms"]["mode"] or child["target_selection_sha256"] != p["terms"]["target_selection_sha256"]
                    or any(child["subject"][k] != p["terms"][k] for k in ("stage_id", "intent_sha256", "receipt_sha256"))):
                conflict()
        base = next(n + 1 for n, row in enumerate(data["ns"]) if row["head"] == p["subject"]["transition_head_sha256"])
        nrows = data["ns"][base:]
        if [row["kind"] for row in nrows] != ["proposed", "decided", "committed"][:len(nrows)] or len(nrows) > 3:
            conflict()
        for row in nrows:
            if row["payload"]["transition_id"] != p["terms"]["transition_id"] or not p["created_at"] <= row["payload"]["created_at"] < p["expires_at"]:
                conflict()
        if nrows:
            if len(rows) != 3 or nrows[0]["payload"]["predecessor_sha256"] != p["subject"]["transition_commit_sha256"]:
                conflict()
            source = nrows[0]["payload"]["subject"]
            if (source["destination_head_sha256"] != rows[-1]["head"] or source["destination_history_sha256"] != e.sha(e.encode(data["ds"]))
                    or any(source[k] != p["subject"][k] for k in ("legacy_head_sha256", "legacy_history_sha256", "revocation_head_sha256", "context_sha256"))):
                conflict()
        if nrows:
            phase = ("transition_proposed", "transition_decided", "transition_committed")[len(nrows) - 1]
        else:
            phase = ("opened", "reader_proposed", "reader_decided", "reader_selected")[len(rows)]
        if len(rows) >= 2 and rows[1]["payload"]["decision"] != "approve":
            phase = "reader_denied"
        return phase, rows, nrows

    def subject(self, actor):
        if self._change is None:
            yield from super().subject(actor)
            return
        p = self._change["proposed"]["payload"]
        with ExitStack() as stack:
            _, lh, ls, _ = stack.enter_context(self.legacy.controls.locked())
            _, dh, ds, _ = stack.enter_context(self.destination.controls.locked())
            _, fence, events, _ = stack.enter_context(self.inner.inner.revocations.locked())
            _, last = legacy_fold(ls, self.legacy.controls.scope)
            proposals, selected, retired = destination_fold(ds, self.destination.controls.scope)
            if (last is None or selected is None or ref(selected) in retired
                    or lh["head"] != p["subject"]["legacy_head_sha256"] or e.sha(e.encode(ls)) != p["subject"]["legacy_history_sha256"]):
                conflict()
            state = proposals[selected["payload"]["proposal_id"]]
            context = self.inner.vault.context(fence, events, e.stamp(self.clock()))
            self.destination.current(state, actor, fence, events, context)
            value = {"legacy_id": self.legacy.controls.identity, "legacy_head_sha256": lh["head"], "legacy_selection_sha256": ref(last),
                     "legacy_history_sha256": e.sha(e.encode(ls)), "destination_id": self.destination.controls.identity,
                     "destination_head_sha256": dh["head"], "destination_selection_sha256": ref(selected), "destination_history_sha256": e.sha(e.encode(ds)),
                     "revocation_head_sha256": fence["head"], "context_sha256": context, "snapshot_sha256": state["proposed"]["payload"]["subject"]["snapshot_sha256"],
                     "valid_until": min(state["proposed"]["payload"]["expires_at"], state["decided"]["payload"]["reviewed_by"]["expires_at"])}
            yield value, fence, events
            self.destination.current(state, actor, fence, events, context)

    def handle(self, scope, value):
        action = scope["path"][len(PREFIX):]
        if action not in self.management and action not in self.delegates:
            return self.inner.handle(scope, value)
        actor = self.inner.inner.assigned(scope)
        writes = action in {"change_prepare", "change_decide", "change_open", "change_finish"}
        with self.change_lock, self.changes.locked(write=writes) as (fd, head, history, _):
            if self.changes.scope != scope_for(self, self.changes.root):
                reject()
            states, opened = fold(history, self.changes.scope)
            active = states[opened["payload"]["change_id"]] if opened else None
            self._change = active
            try:
                if action not in CHANGE_ACTIONS:
                    if active and "finished" not in active:
                        if action == "transition_inventory":
                            conflict()
                        if action in {"transition_prepare", "transition_decide", "transition_commit"}:
                            subject, data = self.snapshot()
                            self.current_window(active, actor, subject)
                            phase, _, _ = self.projection(active, data)
                            if phase not in {"reader_selected", "transition_proposed", "transition_decided"} or value.get("transition_id") != active["proposed"]["payload"]["terms"]["transition_id"]:
                                conflict()
                    return super().handle(scope, value)
                subject, data = self.snapshot()
                observed = {"change_head_sha256": head["head"], "subject_sha256": e.sha(e.encode(subject))}
                if action == "change_observe":
                    if value:
                        reject()
                    return {"status": "destination_change_context", **observed, "subject": subject, **dict.fromkeys(e.FLAGS, False)}
                fields = {"change_prepare": {"change_id", "terms"}, "change_decide": {"change_id", "proposal_sha256", "decision", "reason_code"},
                          "change_open": {"change_id", "decision_sha256"}, "change_step": {"change_id", "step", "decision"},
                          "change_status": {"change_id"}, "change_finish": {"change_id", "transition_commit_sha256", "destination_head_sha256"}}
                if set(value) != fields[action] | {"expected_change_head_sha256", "expected_subject_sha256"}:
                    reject()
                if any(value["expected_" + k] != v for k, v in observed.items()):
                    conflict()
                ident, now = e.token(value["change_id"], 32), e.stamp(self.clock())
                if action == "change_prepare":
                    if actor["kind"] != "preparer" or ident in states or active and "finished" not in active and now < active["proposed"]["payload"]["expires_at"]:
                        conflict()
                    terms(value["terms"])
                    if value["terms"]["mode"] != "retirement":
                        _, prepared = stage_subject(self.inner.vault, value["terms"]["stage_id"], value["terms"]["intent_sha256"], value["terms"]["receipt_sha256"], data["fence"], data["events"], subject["context_sha256"], now)
                        if prepared != actor:
                            conflict()
                    packet, _ = self.target.source(now, historical=True)
                    payload = {"change_id": ident, "subject": subject, "terms": value["terms"], "prepared_by": actor,
                               "reviewer": self.authority.eligible(packet["enrollment"]["reviewer"], "reviewer"), "created_at": now,
                               "expires_at": min(now + 300, actor["expires_at"]), "predecessor_sha256": ref(opened) if opened else None, **dict.fromkeys(e.FLAGS, False)}
                    self.current_window({"proposed": {"payload": payload}}, actor, subject)
                    event = self.changes.append(fd, head, history, "proposed", payload)
                    return {"status": "destination_change_needs_review", "proposal_sha256": ref(event), "change_head_sha256": event["head"], **dict.fromkeys(e.FLAGS, False)}
                if ident not in states:
                    conflict()
                state, p = states[ident], states[ident]["proposed"]["payload"]
                if action == "change_status":
                    usable = False
                    try:
                        self.current_window(state, actor, subject)
                        usable = opened is not None and state.get("opened") == opened and "finished" not in state
                    except Exception:
                        pass
                    phase = "finished" if "finished" in state else self.projection(state, data)[0] if "opened" in state else "decided" if "decided" in state else "proposed"
                    self.authority.recheck(actor, now=e.stamp(self.clock()))
                    return {"status": "destination_change_retained", "phase": phase, "grant_current": usable,
                            "opened_sha256": ref(state["opened"]) if "opened" in state else None,
                            "transition_commit_sha256": subject["transition_commit_sha256"], "destination_head_sha256": subject["destination_head_sha256"], **dict.fromkeys(e.FLAGS, False)}
                self.current_window(state, actor, subject)
                if action in {"change_decide", "change_open"} and subject != p["subject"]:
                    conflict()
                if action == "change_decide":
                    if actor["kind"] != "reviewer" or "decided" in state or value["proposal_sha256"] != ref(state["proposed"]):
                        conflict()
                    payload = {"change_id": ident, "proposal_sha256": value["proposal_sha256"], "reviewed_by": actor, "created_at": now,
                               "decision": value["decision"], "reason_code": value["reason_code"], **dict.fromkeys(e.FLAGS, False)}
                    event = self.changes.append(fd, head, history, "decided", payload)
                    return {"status": "destination_change_decision_retained", "decision_sha256": ref(event), "change_head_sha256": event["head"], **dict.fromkeys(e.FLAGS, False)}
                if action == "change_open":
                    if actor != p["prepared_by"] or "opened" in state or "decided" not in state or state["decided"]["payload"]["decision"] != "approve" or value["decision_sha256"] != ref(state["decided"]):
                        conflict()
                    event = self.changes.append(fd, head, history, "opened", {"change_id": ident, "decision_sha256": value["decision_sha256"], "opened_by": actor, "created_at": now, **dict.fromkeys(e.FLAGS, False)})
                    self.point("destination_change_opened_complete")
                    return {"status": "destination_change_opened", "opened_sha256": ref(event), "change_head_sha256": event["head"], **dict.fromkeys(e.FLAGS, False)}
                if opened is None or state.get("opened") != opened or "finished" in state:
                    conflict()
                phase, rows, nrows = self.projection(state, data)
                if action == "change_step":
                    step = value["step"]
                    expected = {"opened": "retire" if p["terms"]["mode"] == "retirement" else "prepare", "reader_proposed": "decide", "reader_decided": "select"}
                    if expected.get(phase) != step or step != "decide" and (value["decision"] is not None or actor != p["prepared_by"]):
                        conflict()
                    proposals, last, retired = destination_fold(data["ds"], self.destination.controls.scope)
                    body = {"expected_binding_head_sha256": subject["destination_head_sha256"], "expected_revocation_head_sha256": subject["revocation_head_sha256"], "expected_context_sha256": subject["context_sha256"]}
                    if step == "prepare":
                        body.update({k: p["terms"][k] for k in ("proposal_id", "stage_id", "intent_sha256", "receipt_sha256", "mode", "target_selection_sha256")}, predecessor_sha256=ref(last) if last else None, retirement_sha256=ref(retired[ref(last)]) if last and ref(last) in retired else None)
                    elif step == "decide":
                        body.update(proposal_id=p["terms"]["proposal_id"], proposal_sha256=ref(rows[0]), decision=value["decision"], reason_code={"approve": "exact_reader_scope_checked", "deny": "reader_declined"}.get(value["decision"]))
                    elif step == "select":
                        body.update(proposal_id=p["terms"]["proposal_id"], decision_sha256=ref(rows[1]))
                    else:
                        if last is None or ref(last) in retired:
                            conflict()
                        body.update(proposal_id=last["payload"]["proposal_id"], selection_sha256=ref(last), reason_code="reader_retired")
                    forwarded = {**scope, "path": PREFIX + "reader_" + step, "raw_path": (PREFIX + "reader_" + step).encode()}
                    result = self.destination.handle(forwarded, body)
                    after, changed = self.snapshot()
                    self.current_window(state, actor, after)
                    self.projection(state, changed)
                    return result
                if (value["destination_head_sha256"] != subject["destination_head_sha256"] or value["transition_commit_sha256"] != subject["transition_commit_sha256"]
                        or actor != p["prepared_by"] or phase != ("retired" if p["terms"]["mode"] == "retirement" else "transition_committed")):
                    conflict()
                if p["terms"]["mode"] == "retirement" and (nrows or subject["transition_commit_sha256"] != p["subject"]["transition_commit_sha256"]):
                    conflict()
                event = self.changes.append(fd, head, history, "finished", {"change_id": ident, "opened_sha256": ref(opened), "finished_by": actor, "created_at": now,
                    "result": "retired" if p["terms"]["mode"] == "retirement" else "renewed", "transition_commit_sha256": subject["transition_commit_sha256"],
                    "destination_head_sha256": subject["destination_head_sha256"], **dict.fromkeys(e.FLAGS, False)})
                return {"status": "destination_change_finished", "change_head_sha256": event["head"], **dict.fromkeys(e.FLAGS, False)}
            finally:
                self._change = None
