"""A separate immutable transition lineage; neither reader history is imported."""

import operator_enrollment_evidence as e
from operator_review_journal import actor, reject
from restore_control_log import RestoreControlLog, ref
from restore_key_custody import file_id

SUBJECT = {"legacy_id", "legacy_head_sha256", "legacy_selection_sha256", "legacy_history_sha256",
           "destination_id", "destination_head_sha256", "destination_selection_sha256", "destination_history_sha256",
           "revocation_head_sha256", "context_sha256", "snapshot_sha256", "valid_until"}


def scope_for(legacy, destination, root):
    source = legacy.inner.inner.revocations
    result = dict(source.scope)
    for name, controls in (("legacy", legacy.controls), ("destination", destination.controls)):
        result.update({name + "_id": controls.identity, name + "_root_sha256": e.sha(e.encode(file_id(controls.root))),
                       name + "_anchor_root_sha256": e.sha(e.encode(file_id(controls.anchor.path.parent)))})
    result.update(revocation_id=source.identity, revocation_root_sha256=e.sha(e.encode(file_id(source.root))),
                  revocation_anchor_root_sha256=e.sha(e.encode(file_id(source.anchor.path.parent))),
                  stage_catalog_sha256=e.sha(e.encode(file_id(legacy.inner.vault.restores))),
                  transition_root_sha256=e.sha(e.encode(file_id(root))))
    return result


def fold(events, scope):
    proposals, active, previous_time = {}, None, scope["created_at"]
    fields = {"proposed": {"subject", "predecessor_sha256", "prepared_by", "reviewer", "expires_at"},
              "decided": {"proposal_sha256", "reviewed_by", "decision", "reason_code"},
              "committed": {"decision_sha256", "committed_by"}}
    for event in events:
        p, kind = event["payload"], event["kind"]
        if kind not in fields or not isinstance(p, dict) or set(p) != {"transition_id", "created_at", *e.FLAGS} | fields[kind] or any(p[k] is not False for k in e.FLAGS):
            reject()
        ident, now = e.token(p["transition_id"], 32), e.stamp(p["created_at"])
        if now < previous_time:
            reject()
        previous_time = now
        if kind == "proposed":
            if not isinstance(p["subject"], dict) or set(p["subject"]) != SUBJECT:
                reject()
            for key, value in p["subject"].items():
                if key == "valid_until":
                    e.stamp(value)
                else:
                    e.token(value, 32 if key in {"legacy_id", "destination_id"} else 64)
            if any(p["subject"][k] != scope[k] for k in ("legacy_id", "destination_id")):
                reject()
            actor(p["prepared_by"], session=True)
            actor(p["reviewer"], session=False)
            if (ident in proposals or p["predecessor_sha256"] != (ref(active) if active else None)
                    or not 0 < e.stamp(p["expires_at"]) - now <= 300 or p["expires_at"] > min(p["prepared_by"]["expires_at"], p["subject"]["valid_until"])
                    or p["prepared_by"]["kind"] != "preparer" or p["reviewer"]["kind"] != "reviewer"
                    or p["prepared_by"]["user_id"] == p["reviewer"]["user_id"]
                    or any(a[k] != scope[k] for a in (p["prepared_by"], p["reviewer"]) for k in ("firm_id", "profile_id"))):
                reject()
            proposals[ident] = {"proposed": event}
            continue
        if ident not in proposals:
            reject()
        state = proposals[ident]
        original = state["proposed"]["payload"]
        if not original["created_at"] <= now < original["expires_at"] or original["predecessor_sha256"] != (ref(active) if active else None):
            reject()
        if kind == "decided":
            actor(p["reviewed_by"], session=True)
            if ("decided" in state or p["proposal_sha256"] != ref(state["proposed"])
                    or {k: p["reviewed_by"][k] for k in original["reviewer"]} != original["reviewer"]
                    or now >= p["reviewed_by"]["expires_at"]
                    or {"approve": "exact_reader_transition_checked", "deny": "transition_declined"}.get(p["decision"]) != p["reason_code"]):
                reject()
        else:
            actor(p["committed_by"], session=True)
            if ("committed" in state or "decided" not in state or state["decided"]["payload"]["decision"] != "approve"
                    or p["decision_sha256"] != ref(state["decided"]) or p["committed_by"] != original["prepared_by"]
                    or now >= state["decided"]["payload"]["reviewed_by"]["expires_at"]):
                reject()
            active = event
        state[kind] = event
    return proposals, active


class NamespaceLog(RestoreControlLog):
    schema = "disposable-reader-namespace-transition-v1"

    def validate(self, events):
        return fold(events, self.scope)
