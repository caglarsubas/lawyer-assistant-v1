"""Append-only disposable reader choices; no trust or writer authority."""

import operator_enrollment_evidence as e
from operator_review_journal import actor, reject
from restore_control_log import RestoreControlLog, ref
from restore_key_custody import file_id

SCHEMA = "disposable-staged-reader-v1"
SUBJECT_FIELDS = {"stage_id", "intent_sha256", "receipt_sha256", "journal_id", "revocation_head_sha256",
                  "context_sha256", "stage_root_sha256", "snapshot_sha256"}


def scope_for(history, root):
    log = history.inner.revocations
    return {**log.scope, "revocation_id": log.identity, "revocation_root_sha256": e.sha(e.encode(file_id(log.root))),
            "stage_catalog_sha256": e.sha(e.encode(file_id(history.vault.restores))),
            "reader_root_sha256": e.sha(e.encode(file_id(root)))}


def validate_subject(value):
    if not isinstance(value, dict) or set(value) != SUBJECT_FIELDS:
        reject()
    for key, item in value.items():
        e.token(item, 32 if key in {"stage_id", "journal_id"} else 64)


def fold(events, scope):
    proposals, active, previous_time = {}, None, scope["created_at"]
    fields = {"proposed": {"subject", "prepared_by", "reviewer", "expires_at"},
              "decided": {"proposal_sha256", "reviewed_by", "decision", "reason_code"},
              "selected": {"decision_sha256", "selected_by"}}
    for event in events:
        p, kind = event["payload"], event["kind"]
        if kind not in fields or not isinstance(p, dict) or set(p) != {"proposal_id", "created_at", *e.FLAGS} | fields[kind] or any(p[k] is not False for k in e.FLAGS):
            reject()
        ident, now = e.token(p["proposal_id"], 32), e.stamp(p["created_at"])
        if now < previous_time:
            reject()
        previous_time = now
        if kind == "proposed":
            validate_subject(p["subject"])
            actor(p["prepared_by"], session=True)
            actor(p["reviewer"], session=False)
            if (ident in proposals or not 0 < e.stamp(p["expires_at"]) - now <= 300
                    or p["expires_at"] > p["prepared_by"]["expires_at"] or p["prepared_by"]["kind"] != "preparer"
                    or p["reviewer"]["kind"] != "reviewer" or p["prepared_by"]["user_id"] == p["reviewer"]["user_id"]
                    or any(a[k] != scope[k] for a in (p["prepared_by"], p["reviewer"]) for k in ("firm_id", "profile_id"))):
                reject()
            proposals[ident] = {"proposed": event}
            continue
        if ident not in proposals:
            reject()
        state = proposals[ident]
        original = state["proposed"]["payload"]
        if not original["created_at"] <= now < original["expires_at"]:
            reject()
        if kind == "decided":
            actor(p["reviewed_by"], session=True)
            if ("decided" in state or p["proposal_sha256"] != ref(state["proposed"])
                    or {k: p["reviewed_by"][k] for k in original["reviewer"]} != original["reviewer"]
                    or now >= p["reviewed_by"]["expires_at"]
                    or {"approve": "exact_reader_scope_checked", "deny": "reader_declined"}.get(p["decision"]) != p["reason_code"]):
                reject()
        else:
            actor(p["selected_by"], session=True)
            if ("selected" in state or "decided" not in state or state["decided"]["payload"]["decision"] != "approve"
                    or p["decision_sha256"] != ref(state["decided"]) or p["selected_by"] != original["prepared_by"]
                    or now >= state["decided"]["payload"]["reviewed_by"]["expires_at"]):
                reject()
            active = event
        state[kind] = event
    return proposals, active


class ReaderLog(RestoreControlLog):
    schema = SCHEMA

    def validate(self, events):
        return fold(events, self.scope)
