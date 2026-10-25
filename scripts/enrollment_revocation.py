"""Disposable inventory and lineage withdrawal; never key destruction or activation."""

import threading

import operator_enrollment_evidence as e
from authenticated_operator_review import PREFIX, ReviewHandoff, conflict
from enrollment_revocation_log import RevocationLog, fold
from operator_review_journal import reject
from restore_control_log import ref
from restore_inventory import capture, page, revocation_scope, subject
from restore_lifecycle import RestoreLifecycle


class EnrollmentRevocation(ReviewHandoff):
    management = {"lifecycle_inventory", "observe_revocation", "prepare_revocation", "decide_revocation", "revocation_status", "revocation_recover"}
    actions = (*RestoreLifecycle.actions, *sorted(management))

    def __init__(self, inner, revocations, **kwargs):
        if not isinstance(inner, RestoreLifecycle) or not isinstance(revocations, RevocationLog) or revocations.scope != revocation_scope(inner):
            reject()
        self.inner, self.revocations, self.admission = inner, revocations, threading.Lock()
        super().__init__(inner.authority, inner.target, inner.ledger, **kwargs)

    def assigned(self, scope):
        return self.inner.children[self.inner.initial].assigned(scope)

    def fresh(self, withdrawn, now):
        if self.revocations.scope != revocation_scope(self.inner):
            conflict()
        return capture(self.inner, withdrawn, now)

    def proposal_current(self, proposal, actor, withdrawn, now):
        p = proposal["payload"]
        if not p["created_at"] <= now < p["expires_at"]:
            conflict()
        self.authority.recheck(p["prepared_by"], now=now)
        if self.authority.eligible(p["reviewer"]["user_id"], "reviewer") != p["reviewer"]:
            conflict()
        if subject(self.fresh(withdrawn, now), p["subject"]["target_enrollment_sha256"]) != p["subject"]:
            conflict()
        self.authority.recheck(actor, now=now)

    def handle(self, scope, value):
        action = scope["path"][len(PREFIX):]
        with self.admission:
            actor = self.assigned(scope)
            repair = action == "revocation_recover" and value.get("repair") is True
            with self.revocations.locked(write=action in {"prepare_revocation", "decide_revocation"} or repair,
                                         recovery=action == "revocation_recover") as (fd, fence, events, tip):
                requests, withdrawn = fold(events, self.revocations.scope)
                now = e.stamp(self.clock())
                if now < (events[-1]["payload"]["created_at"] if events else self.revocations.scope["created_at"]):
                    conflict()
                if action == "revocation_recover":
                    if set(value) != {"expected_head_sha256", "expected_tip_sha256", "repair"} or type(value["repair"]) is not bool:
                        reject()
                    if repair:
                        if value["expected_head_sha256"] != fence["head"] or value["expected_tip_sha256"] != tip["head"]:
                            conflict()
                        self.authority.recheck(actor, now=e.stamp(self.clock()))
                        if fence != tip:
                            self.revocations.anchor.append(fd, fence, tip)
                    _, published = fold(events if repair else events[:fence["seq"]], self.revocations.scope)
                    self.authority.recheck(actor, now=e.stamp(self.clock()))
                    return {"status": "revocation_reconciled" if repair else "revocation_observed",
                            "revocation_head_sha256": tip["head"] if repair else fence["head"], "revocation_tip_sha256": tip["head"],
                            "published_withdrawals": len(published), **dict.fromkeys(e.FLAGS, False)}
                snapshot = self.fresh(withdrawn, now)
                if action == "lifecycle_inventory":
                    result = page(snapshot, fence["head"], actor, value)
                    if self.fresh(withdrawn, e.stamp(self.clock()))["basis_sha256"] != snapshot["basis_sha256"]:
                        conflict()
                    self.authority.recheck(actor, now=e.stamp(self.clock()))
                    return result
                if action not in self.management:
                    if set(value) != {"expected_revocation_head_sha256", "request"} or not isinstance(value["request"], dict):
                        reject()
                    if value["expected_revocation_head_sha256"] != fence["head"]:
                        conflict()
                    current = snapshot["basis"]["active_enrollment_sha256"]
                    if current in snapshot["effective"]:
                        conflict()
                    original = value["request"]
                    body = original.get("request", {})
                    if not isinstance(body, dict):
                        reject()
                    if action in {"observe_renewal", "prepare_renewal"} and body.get("candidate_generation") in snapshot["effective"]:
                        conflict()
                    if action == "decide_lifecycle":
                        request = snapshot["requests"].get(body.get("request_id"))
                        if request:
                            p = request["proposal"]["payload"]
                            if p["kind"] == "renewal" and p["subject"]["candidate_generation"] in snapshot["effective"]:
                                conflict()
                    # Do not hold the inner lifecycle lock while calling its
                    # handler. The outer fence serializes all wrapped instances;
                    # the inner handler independently checks its exact head.
                    return self.inner.handle(scope, original)
                fields = {
                    "observe_revocation": {"target_enrollment_sha256"},
                    "prepare_revocation": {"target_enrollment_sha256", "proposal_id", "subject_sha256"},
                    "decide_revocation": {"proposal_id", "proposal_sha256", "decision", "reason_code"},
                    "revocation_status": {"proposal_id", "decision_sha256"},
                }
                common = {"expected_revocation_head_sha256", "expected_lifecycle_head_sha256"}
                if action not in fields or set(value) != fields[action] | common:
                    reject()
                if value["expected_revocation_head_sha256"] != fence["head"] or value["expected_lifecycle_head_sha256"] != snapshot["basis"]["lifecycle_head_sha256"]:
                    conflict()
                if action in {"observe_revocation", "prepare_revocation"}:
                    s = subject(snapshot, value["target_enrollment_sha256"])
                    digest = e.sha(e.encode(s))
                    if action == "observe_revocation":
                        self.authority.recheck(actor, now=e.stamp(self.clock()))
                        return {"status": "withdrawal_scope_observed_needs_pin", "subject_sha256": digest, **dict.fromkeys(e.FLAGS, False)}
                    ident = e.token(value["proposal_id"], 32)
                    if actor["kind"] != "preparer" or ident in requests or digest != e.token(value["subject_sha256"]):
                        conflict()
                    packet, _ = self.target.source(now, historical=True)
                    payload = {"proposal_id": ident, "subject": s, "subject_sha256": digest, "prepared_by": actor,
                               "reviewer": self.authority.eligible(packet["enrollment"]["reviewer"], "reviewer"), "created_at": now,
                               "expires_at": min(now + 300, actor["expires_at"]), **dict.fromkeys(e.FLAGS, False)}
                    self.proposal_current({"payload": payload}, actor, withdrawn, e.stamp(self.clock()))
                    event = self.revocations.append(fd, fence, events, "proposed", payload)
                    self.proposal_current(event, actor, withdrawn, e.stamp(self.clock()))
                    return {"status": "withdrawal_needs_independent_decision", "proposal_sha256": ref(event),
                            "revocation_head_sha256": event["head"], **dict.fromkeys(e.FLAGS, False)}
                ident = e.token(value["proposal_id"], 32)
                if ident not in requests:
                    conflict()
                state = requests[ident]
                if action == "revocation_status":
                    if "decision" not in state:
                        conflict()
                    digest = ref(state["decision"])
                    if value["decision_sha256"] is not None and value["decision_sha256"] != e.token(digest):
                        conflict()
                    self.authority.recheck(actor, now=e.stamp(self.clock()))
                    return {"status": "withdrawal_decision_observed_needs_pin" if value["decision_sha256"] is None else "withdrawal_decision_retained",
                            "decision_sha256": digest, "decision": state["decision"]["payload"]["decision"], **dict.fromkeys(e.FLAGS, False)}
                if actor["kind"] != "reviewer" or "decision" in state or value["proposal_sha256"] != ref(state["proposal"]):
                    conflict()
                self.proposal_current(state["proposal"], actor, withdrawn, now)
                payload = {"proposal_id": ident, "proposal_sha256": value["proposal_sha256"], "decision": value["decision"],
                           "reason_code": value["reason_code"], "reviewed_by": actor, "created_at": now, **dict.fromkeys(e.FLAGS, False)}
                event = self.revocations.append(fd, fence, events, "decided", payload)
                self.proposal_current(state["proposal"], actor, withdrawn, e.stamp(self.clock()))
                self.point("revocation_decision_complete")
                return {"status": "withdrawal_decision_retained", "decision_sha256": ref(event), "decision": value["decision"],
                        "revocation_head_sha256": event["head"], **dict.fromkeys(e.FLAGS, False)}
