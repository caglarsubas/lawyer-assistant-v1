"""Independent append-only retirement and enrollment supersession decisions."""

import operator_enrollment_evidence as e
from operator_review_journal import actor, reject
from restore_control_log import RestoreControlLog, ref


def identity(value):
    if not isinstance(value, dict) or set(value) != {"device", "inode", "owner"} or any(type(v) is not int or v < 0 for v in value.values()):
        reject()


def subject(value, kind):
    fields = {"target_generation", "operation_id", "controls_head_sha256", "target_identity", "target_sha256", "intent_sha256", "receipt_sha256"} if kind == "retirement" else {
        "previous_generation", "candidate_generation", "previous_controls_head_sha256", "candidate_controls_head_sha256", "candidate_control_id", "review_head_sha256", "candidate_expiry", "key_id", "key_fingerprint_sha256", "key_file"}
    if not isinstance(value, dict) or set(value) != fields:
        reject()
    for k, v in value.items():
        if k in {"target_identity", "key_file"}:
            identity(v)
        elif k == "candidate_expiry":
            e.stamp(v)
        else:
            e.token(v, 32 if k in {"operation_id", "candidate_control_id", "key_id"} else 64)


def fold(events, scope):
    current, used, requests, retired = scope["initial_enrollment_sha256"], {scope["initial_enrollment_sha256"]}, {}, {}
    last = scope["created_at"]
    for event in events:
        p, kind = event["payload"], event["kind"]
        common = {"request_id", "created_at", *e.FLAGS}
        fields = {"proposed": {"kind", "current_generation", "subject", "subject_sha256", "prepared_by", "reviewer", "expires_at", "packet_sha256", "observation_sha256"},
                  "decided": {"proposal_sha256", "reviewed_by", "decision", "reason_code"}}
        if kind not in fields or not isinstance(p, dict) or set(p) != common | fields[kind] or any(p[k] is not False for k in e.FLAGS):
            reject()
        ident, now = e.token(p["request_id"], 32), e.stamp(p["created_at"])
        if now < last:
            reject()
        last = now
        if kind == "proposed":
            if ident in requests or p["kind"] not in {"retirement", "renewal"} or p["current_generation"] != current or not 0 < e.stamp(p["expires_at"]) - now <= 300:
                reject()
            subject(p["subject"], p["kind"])
            if p["subject_sha256"] != e.sha(e.encode(p["subject"])) or any(p[k] != scope[k] for k in ("packet_sha256", "observation_sha256")):
                reject()
            actor(p["prepared_by"], session=True)
            actor(p["reviewer"], session=False)
            if p["prepared_by"]["kind"] != "preparer" or p["reviewer"]["kind"] != "reviewer" or p["prepared_by"]["user_id"] == p["reviewer"]["user_id"]:
                reject()
            for who in (p["prepared_by"], p["reviewer"]):
                if any(who[k] != scope[k] for k in ("firm_id", "profile_id")):
                    reject()
            s = p["subject"]
            if p["kind"] == "renewal":
                if s["previous_generation"] != current or s["candidate_generation"] in used:
                    reject()
            elif s["target_generation"] not in used or (s["target_generation"], s["operation_id"]) in retired:
                reject()
            requests[ident] = {"proposal": event}
            continue
        if ident not in requests or "decision" in requests[ident]:
            reject()
        state = requests[ident]
        proposal = state["proposal"]["payload"]
        actor(p["reviewed_by"], session=True)
        if (p["proposal_sha256"] != ref(state["proposal"]) or not proposal["created_at"] <= now < proposal["expires_at"]
                or proposal["current_generation"] != current or {k: p["reviewed_by"][k] for k in proposal["reviewer"]} != proposal["reviewer"]):
            reject()
        expected_reason = ("retire_exact_target" if proposal["kind"] == "retirement" else "renew_exact_enrollment") if p["decision"] == "approve" else "lifecycle_declined"
        if p["decision"] not in {"approve", "deny"} or p["reason_code"] != expected_reason:
            reject()
        if p["decision"] == "approve":
            s = proposal["subject"]
            if proposal["kind"] == "renewal":
                if s["candidate_generation"] in used or now >= s["candidate_expiry"]:
                    reject()
                current = s["candidate_generation"]
                used.add(current)
            else:
                key = (s["target_generation"], s["operation_id"])
                if key in retired:
                    reject()
                retired[key] = event
        state["decision"] = event
    return current, used, requests, retired


class LifecycleLog(RestoreControlLog):
    schema = "restore-lifecycle-control-v1"

    def validate(self, events):
        return fold(events, self.scope)
