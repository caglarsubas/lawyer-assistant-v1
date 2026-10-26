"""Permanent exact-selection retirement and fresh, independently reviewed succession."""

import operator_enrollment_evidence as e
from operator_review_journal import actor, reject
from restore_control_log import ref
from restore_key_custody import file_id
from staged_reader_log import ReaderLog

SCHEMA = "disposable-reader-lifecycle-v1"
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


def lineage(payload, last, retired, proposals):
    previous = ref(last) if last else None
    retirement = ref(retired[previous]) if previous in retired else None
    if payload["predecessor_sha256"] != previous or payload["retirement_sha256"] != retirement:
        reject()
    mode, target = payload["mode"], payload["target_selection_sha256"]
    if mode == "initial":
        if last is not None or target is not None:
            reject()
    elif mode == "renewal":
        if last is None or target is not None:
            reject()
    elif mode == "rollback":
        targets = [state for state in proposals.values() if "selected" in state and ref(state["selected"]) == target]
        if last is None or target == previous or len(targets) != 1:
            reject()
        before = targets[0]["proposed"]["payload"]["subject"]
        if any(before[k] != payload["subject"][k] for k in ("journal_id", "snapshot_sha256")):
            reject()
    else:
        reject()


def fold(events, scope):
    proposals, last, retired, previous_time = {}, None, {}, scope["created_at"]
    fields = {"proposed": {"subject", "prepared_by", "reviewer", "expires_at", "mode", "predecessor_sha256", "retirement_sha256", "target_selection_sha256"},
              "decided": {"proposal_sha256", "reviewed_by", "decision", "reason_code"},
              "selected": {"decision_sha256", "selected_by"},
              "retired": {"selection_sha256", "retired_by", "reason_code"}}
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
            lineage(p, last, retired, proposals)
            proposals[ident] = {"proposed": event}
            continue
        if ident not in proposals:
            reject()
        state = proposals[ident]
        original = state["proposed"]["payload"]
        if kind == "retired":
            actor(p["retired_by"], session=True)
            if (last is None or last["payload"]["proposal_id"] != ident or p["selection_sha256"] != ref(last)
                    or p["selection_sha256"] in retired or p["reason_code"] != "reader_retired"
                    or p["retired_by"]["user_id"] not in {original["prepared_by"]["user_id"], original["reviewer"]["user_id"]}
                    or now >= p["retired_by"]["expires_at"]
                    or any(p["retired_by"][k] != scope[k] for k in ("firm_id", "profile_id"))):
                reject()
            retired[p["selection_sha256"]] = event
            state[kind] = event
            continue
        if not original["created_at"] <= now < original["expires_at"]:
            reject()
        lineage(original, last, retired, proposals)
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
            last = event
        state[kind] = event
    return proposals, last, retired


class ReaderLifecycleLog(ReaderLog):
    schema = SCHEMA

    def validate(self, events):
        return fold(events, self.scope)
