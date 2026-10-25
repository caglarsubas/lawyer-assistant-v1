"""Independent, bounded enrollment-withdrawal proposals and decisions."""

import operator_enrollment_evidence as e
from operator_review_journal import actor, reject
from restore_control_log import RestoreControlLog, ref


def fold(events, scope):
    requests, withdrawn = {}, {}
    last = scope["created_at"]
    for event in events:
        p, kind = event["payload"], event["kind"]
        common = {"proposal_id", "created_at", *e.FLAGS}
        fields = {"proposed": {"subject", "subject_sha256", "prepared_by", "reviewer", "expires_at"},
                  "decided": {"proposal_sha256", "decision", "reason_code", "reviewed_by"}}
        if kind not in fields or not isinstance(p, dict) or set(p) != common | fields[kind] or any(p[k] is not False for k in e.FLAGS):
            reject()
        ident, now = e.token(p["proposal_id"], 32), e.stamp(p["created_at"])
        if now < last:
            reject()
        last = now
        if kind == "proposed":
            s = p["subject"]
            if (ident in requests or not 0 < e.stamp(p["expires_at"]) - now <= 300 or not isinstance(s, dict)
                    or set(s) != {"target_enrollment_sha256", "basis_sha256", "lifecycle_head_sha256", "affected_enrollments"}
                    or s["target_enrollment_sha256"] not in scope["enrollments"]
                    or not isinstance(s["affected_enrollments"], list) or not s["affected_enrollments"]
                    or s["affected_enrollments"] != sorted(set(s["affected_enrollments"]))
                    or not set(s["affected_enrollments"]) <= set(scope["enrollments"]) or s["target_enrollment_sha256"] not in s["affected_enrollments"]
                    or p["subject_sha256"] != e.sha(e.encode(s))):
                reject()
            for k in ("target_enrollment_sha256", "basis_sha256", "lifecycle_head_sha256"):
                e.token(s[k])
            if any(s["target_enrollment_sha256"] in old["affected_enrollments"] for old in withdrawn.values()):
                reject()
            actor(p["prepared_by"], session=True)
            actor(p["reviewer"], session=False)
            if p["prepared_by"]["kind"] != "preparer" or p["reviewer"]["kind"] != "reviewer" or p["prepared_by"]["user_id"] == p["reviewer"]["user_id"]:
                reject()
            if any(who[k] != scope[k] for who in (p["prepared_by"], p["reviewer"]) for k in ("firm_id", "profile_id")):
                reject()
            requests[ident] = {"proposal": event}
            continue
        if ident not in requests or "decision" in requests[ident]:
            reject()
        state = requests[ident]
        proposal = state["proposal"]["payload"]
        actor(p["reviewed_by"], session=True)
        if (p["proposal_sha256"] != ref(state["proposal"]) or not proposal["created_at"] <= now < proposal["expires_at"]
                or {k: p["reviewed_by"][k] for k in proposal["reviewer"]} != proposal["reviewer"]
                or {"approve": "withdraw_exact_enrollment_lineage", "deny": "withdrawal_declined"}.get(p["decision"]) != p["reason_code"]):
            reject()
        if p["decision"] == "approve":
            s = proposal["subject"]
            if any(s["target_enrollment_sha256"] in old["affected_enrollments"] for old in withdrawn.values()):
                reject()
            withdrawn[s["target_enrollment_sha256"]] = {**s, "decision_sha256": ref(event)}
        state["decision"] = event
    return requests, withdrawn


class RevocationLog(RestoreControlLog):
    schema = "disposable-enrollment-withdrawal-v1"

    def validate(self, events):
        return fold(events, self.scope)
