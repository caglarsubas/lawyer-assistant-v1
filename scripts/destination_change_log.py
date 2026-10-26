"""Separate, append-only authorization for destination maintenance windows."""

import operator_enrollment_evidence as e
from operator_review_journal import actor, reject
from reader_namespace_log import scope_for as namespace_scope
from restore_control_log import RestoreControlLog, ref
from restore_key_custody import file_id

SUBJECT = {"transition_commit_sha256", "transition_head_sha256", "legacy_head_sha256", "legacy_history_sha256",
           "destination_head_sha256", "destination_history_sha256", "revocation_head_sha256", "context_sha256"}
TERMS = {"mode", "proposal_id", "transition_id", "stage_id", "intent_sha256", "receipt_sha256", "target_selection_sha256"}


def terms(value):
    if not isinstance(value, dict) or set(value) != TERMS or value["mode"] not in {"renewal", "rollback", "retirement"}:
        reject()
    if value["mode"] == "retirement":
        if any(value[k] is not None for k in TERMS - {"mode"}):
            reject()
        return
    for k in ("proposal_id", "transition_id", "stage_id"):
        e.token(value[k], 32)
    for k in ("intent_sha256", "receipt_sha256"):
        e.token(value[k])
    if value["mode"] == "rollback":
        e.token(value["target_selection_sha256"])
    elif value["target_selection_sha256"] is not None:
        reject()


def scope_for(service, root):
    if service.controls.scope != namespace_scope(service.legacy, service.destination, service.controls.root):
        reject()
    return {**service.controls.scope, "namespace_id": service.controls.identity,
            "namespace_root_sha256": e.sha(e.encode(file_id(service.controls.root))),
            "namespace_anchor_root_sha256": e.sha(e.encode(file_id(service.controls.anchor.path.parent))),
            "change_root_sha256": e.sha(e.encode(file_id(root)))}


def fold(events, scope):
    states, opened, previous_time = {}, None, scope["created_at"]
    fields = {"proposed": {"subject", "terms", "prepared_by", "reviewer", "expires_at", "predecessor_sha256"},
              "decided": {"proposal_sha256", "reviewed_by", "decision", "reason_code"},
              "opened": {"decision_sha256", "opened_by"},
              "finished": {"opened_sha256", "finished_by", "result", "transition_commit_sha256", "destination_head_sha256"}}
    for event in events:
        p, kind = event["payload"], event["kind"]
        if kind not in fields or not isinstance(p, dict) or set(p) != {"change_id", "created_at", *e.FLAGS} | fields[kind] or any(p[k] is not False for k in e.FLAGS):
            reject()
        ident, now = e.token(p["change_id"], 32), e.stamp(p["created_at"])
        if now < previous_time:
            reject()
        previous_time = now
        if kind == "proposed":
            if not isinstance(p["subject"], dict) or set(p["subject"]) != SUBJECT:
                reject()
            for item in p["subject"].values():
                e.token(item)
            terms(p["terms"])
            actor(p["prepared_by"], session=True)
            actor(p["reviewer"], session=False)
            if (ident in states or p["predecessor_sha256"] != (ref(opened) if opened else None)
                    or p["prepared_by"]["kind"] != "preparer" or p["reviewer"]["kind"] != "reviewer"
                    or p["prepared_by"]["user_id"] == p["reviewer"]["user_id"]
                    or not 0 < e.stamp(p["expires_at"]) - now <= 300 or p["expires_at"] > p["prepared_by"]["expires_at"]
                    or any(a[k] != scope[k] for a in (p["prepared_by"], p["reviewer"]) for k in ("firm_id", "profile_id"))):
                reject()
            if opened and "finished" not in states[opened["payload"]["change_id"]] and now < states[opened["payload"]["change_id"]]["proposed"]["payload"]["expires_at"]:
                reject()
            states[ident] = {"proposed": event}
            continue
        if ident not in states:
            reject()
        state = states[ident]
        original = state["proposed"]["payload"]
        if not original["created_at"] <= now < original["expires_at"]:
            reject()
        if kind == "decided":
            actor(p["reviewed_by"], session=True)
            if ("decided" in state or p["proposal_sha256"] != ref(state["proposed"])
                    or {k: p["reviewed_by"][k] for k in original["reviewer"]} != original["reviewer"]
                    or now >= p["reviewed_by"]["expires_at"]
                    or {"approve": "exact_destination_change_checked", "deny": "destination_change_declined"}.get(p["decision"]) != p["reason_code"]):
                reject()
        elif kind == "opened":
            actor(p["opened_by"], session=True)
            if ("opened" in state or "decided" not in state or state["decided"]["payload"]["decision"] != "approve"
                    or p["decision_sha256"] != ref(state["decided"]) or p["opened_by"] != original["prepared_by"]
                    or original["predecessor_sha256"] != (ref(opened) if opened else None)
                    or now >= state["decided"]["payload"]["reviewed_by"]["expires_at"]):
                reject()
            opened = event
        else:
            actor(p["finished_by"], session=True)
            if ("finished" in state or state.get("opened") != opened or p["opened_sha256"] != ref(opened)
                    or p["finished_by"] != original["prepared_by"]
                    or p["result"] != ("retired" if original["terms"]["mode"] == "retirement" else "renewed")):
                reject()
            e.token(p["transition_commit_sha256"])
            e.token(p["destination_head_sha256"])
        state[kind] = event
    return states, opened


class DestinationChangeLog(RestoreControlLog):
    schema = "disposable-destination-change-v1"

    def validate(self, events):
        return fold(events, self.scope)
