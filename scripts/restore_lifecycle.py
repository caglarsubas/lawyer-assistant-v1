"""Disposable metadata retirement and enrollment renewal; no key rotation or activation."""

import threading
from types import MappingProxyType

import operator_enrollment_evidence as e
from authenticated_operator_review import PREFIX, ReviewHandoff, conflict
from operator_review_journal import reject
from restore_authorization import RestoreAuthorization
from restore_control_log import fold as restore_fold
from restore_control_log import ref
from restore_key_custody import file_id
from restore_lifecycle_log import LifecycleLog, fold


def catalog_scope(children, initial, created_at):
    if not isinstance(children, dict) or not 2 <= len(children) <= 8 or initial not in children:
        reject()
    first = children[initial]
    entries = {}
    for digest, child in children.items():
        e.token(digest)
        if (not isinstance(child, RestoreAuthorization) or child.custody.approved != digest
                or child.journal.scope != first.journal.scope or child.journal.identity != first.journal.identity
                or child.journal.path != first.journal.path or child.authority.root != first.authority.root
                or dict(child.authority.bindings) != dict(first.authority.bindings) or child.target != first.target
                or child.vault.restores != first.vault.restores or child.vault.key_path != first.vault.key_path):
            reject()
        child.custody.check(0)
        entries[digest] = {"control_id": child.controls.identity, "control_scope": child.controls.scope}
    return {**first.journal.scope, "review_journal_id": first.journal.identity, "initial_enrollment_sha256": initial,
            "catalog_sha256": e.sha(e.encode(entries)), "packet_sha256": first.target.packet_sha256,
            "observation_sha256": first.target.observation_sha256, "created_at": e.stamp(created_at)}


class RestoreLifecycle(ReviewHandoff):
    actions = (*RestoreAuthorization.actions, "lifecycle_status", "lifecycle_recover", "observe_retirement", "prepare_retirement",
               "observe_renewal", "prepare_renewal", "decide_lifecycle", "retirement_status")

    def __init__(self, children, initial, lifecycle, **kwargs):
        if not isinstance(lifecycle, LifecycleLog) or lifecycle.scope != catalog_scope(children, initial, lifecycle.scope["created_at"]):
            reject()
        self.children, self.initial, self.lifecycle = MappingProxyType(dict(children)), initial, lifecycle
        self.admission = threading.Lock()
        first = children[initial]
        super().__init__(first.authority, first.target, first.ledger, **kwargs)

    def child(self, digest):
        if e.token(digest) not in self.children:
            conflict()
        return self.children[digest]

    def retirement_snapshot(self, generation, operation):
        child = self.child(generation)
        child.custody.check(0)  # Historical integrity, never renewed validity.
        with child.controls.locked() as (_, fence, events, _):
            operations, _ = restore_fold(events, child.controls.scope)
            ident = e.token(operation, 32)
            if ident not in operations or "consumed" not in operations[ident]:
                conflict()
            prepared = operations[ident]["prepared"]["payload"]
            root = e.directory(child.vault.restores / ident)
            iraw, rraw = e.read(root / "intent.json"), e.read(root / "receipt.json")
            intent, receipt = e.decode(iraw), e.decode(rraw)
            expected = {"schema": "review-history-restore-v1", "request_id": ident, "backup_id": prepared["backup_id"],
                        "manifest_sha256": prepared["manifest_sha256"], "head_sha256": prepared["review_head_sha256"],
                        "scope_sha256": e.sha(e.encode(child.journal.scope)), **dict.fromkeys(e.FLAGS, False)}
            mraw = e.read(child.vault.manifests / (prepared["backup_id"] + ".json"))
            manifest = e.decode(mraw)
            if (intent != expected or set(receipt) != set(expected) | {"intent_sha256", "snapshot_sha256", "records"}
                    or any(receipt[k] != v for k, v in expected.items()) or receipt["intent_sha256"] != e.sha(iraw)
                    or type(receipt["records"]) is not int or not 0 <= receipt["records"] <= 128
                    or e.sha(mraw) != prepared["manifest_sha256"] or receipt["snapshot_sha256"] != manifest["plaintext_sha256"]
                    or child.target_ref(ident) != prepared["target_sha256"]):
                reject()
            return {"target_generation": generation, "operation_id": ident, "controls_head_sha256": fence["head"],
                    "target_identity": file_id(root), "target_sha256": prepared["target_sha256"],
                    "intent_sha256": e.sha(iraw), "receipt_sha256": e.sha(rraw)}

    def renewal_snapshot(self, current, candidate, now):
        old, new = self.child(current), self.child(candidate)
        previous, successor = old.custody.check(0), new.custody.check(now)
        same = ("key_id", "scope_sha256", "fingerprint_sha256", "key_file", "purpose")
        if (candidate == current or any(previous[k] != successor[k] for k in same)
                or successor["expires_at"] <= previous["expires_at"] or successor["created_at"] < previous["created_at"]
                or successor["expires_at"] - successor["created_at"] > 86400):
            conflict()
        old.target.full(now)
        with old.controls.locked() as (_, before, _, _):
            old_head = before["head"]
        with new.controls.locked() as (_, after, events, _):
            if events or after["seq"] != 0:
                conflict()
            new_head = after["head"]
        with old.journal.anchor.locked() as (_, review):
            head = review["head"]
        return {"previous_generation": current, "candidate_generation": candidate, "previous_controls_head_sha256": old_head,
                "candidate_controls_head_sha256": new_head, "candidate_control_id": new.controls.identity, "review_head_sha256": head,
                "candidate_expiry": successor["expires_at"], "key_id": successor["key_id"],
                "key_fingerprint_sha256": successor["fingerprint_sha256"], "key_file": successor["key_file"]}

    def proposal_current(self, proposal, current, actor, now):
        p = proposal["payload"]
        if p["current_generation"] != current or not p["created_at"] <= now < p["expires_at"]:
            conflict()
        self.authority.recheck(p["prepared_by"], now=now)
        if self.authority.eligible(p["reviewer"]["user_id"], "reviewer") != p["reviewer"]:
            conflict()
        s = p["subject"]
        fresh = self.retirement_snapshot(s["target_generation"], s["operation_id"]) if p["kind"] == "retirement" else self.renewal_snapshot(current, s["candidate_generation"], now)
        if fresh != s:
            conflict()
        self.authority.recheck(actor, now=now)

    def handle(self, scope, value):
        action = scope["path"][len(PREFIX):]
        with self.admission:
            actor = self.children[self.initial].assigned(scope)
            repair = action == "lifecycle_recover" and value.get("repair") is True
            with self.lifecycle.locked(write=action in {"prepare_retirement", "prepare_renewal", "decide_lifecycle"} or repair,
                                       recovery=action == "lifecycle_recover") as (fd, fence, events, tip):
                current, used, requests, retired = fold(events, self.lifecycle.scope)
                now = e.stamp(self.clock())
                if now < (events[-1]["payload"]["created_at"] if events else self.lifecycle.scope["created_at"]):
                    conflict()
                if action in {"lifecycle_status", "lifecycle_recover"}:
                    if action == "lifecycle_status" and value:
                        reject()
                    if action == "lifecycle_recover":
                        if set(value) != {"expected_head_sha256", "expected_tip_sha256", "repair"} or type(value["repair"]) is not bool:
                            reject()
                        if repair:
                            if value["expected_head_sha256"] != fence["head"] or value["expected_tip_sha256"] != tip["head"]:
                                conflict()
                            self.authority.recheck(actor, now=e.stamp(self.clock()))
                            if fence != tip:
                                self.lifecycle.anchor.append(fd, fence, tip)
                    self.authority.recheck(actor, now=e.stamp(self.clock()))
                    published, _, _, published_retired = fold(events if repair else events[:fence["seq"]], self.lifecycle.scope)
                    return {"status": "lifecycle_reconciled" if repair else "lifecycle_observed", "enrollment_sha256": published,
                            "lifecycle_head_sha256": tip["head"] if repair else fence["head"], "lifecycle_tip_sha256": tip["head"],
                            "retired_targets": len(published_retired), "events": len(events), **dict.fromkeys(e.FLAGS, False)}
                if set(value) != {"enrollment_sha256", "expected_lifecycle_head_sha256", "request"} or not isinstance(value["request"], dict):
                    reject()
                if value["enrollment_sha256"] != current or value["expected_lifecycle_head_sha256"] != fence["head"]:
                    conflict()
                body = value["request"]
                if action == "retirement_status":
                    if set(body) != {"target_generation", "operation_id", "decision_sha256"}:
                        reject()
                    key = (e.token(body["target_generation"]), e.token(body["operation_id"], 32))
                    if key not in retired or ref(retired[key]) != e.token(body["decision_sha256"]):
                        conflict()
                    self.authority.recheck(actor, now=e.stamp(self.clock()))
                    return {"status": "retired_target_history_retained", "decision_sha256": ref(retired[key]), **dict.fromkeys(e.FLAGS, False)}
                if action in {"observe_retirement", "prepare_retirement", "observe_renewal", "prepare_renewal"}:
                    kind = "retirement" if action.endswith("retirement") else "renewal"
                    preparing = action.startswith("prepare")
                    fields = {"target_generation", "operation_id"} if kind == "retirement" else {"candidate_generation"}
                    if set(body) != fields | ({"request_id", "subject_sha256"} if preparing else set()):
                        reject()
                    if preparing and actor["kind"] != "preparer":
                        conflict()
                    if kind == "retirement":
                        key = (e.token(body["target_generation"]), e.token(body["operation_id"], 32))
                        if key[0] not in used or any(k[1] == key[1] for k in retired):
                            conflict()
                        subject = self.retirement_snapshot(*key)
                    else:
                        if body["candidate_generation"] in used:
                            conflict()
                        subject = self.renewal_snapshot(current, body["candidate_generation"], now)
                    digest = e.sha(e.encode(subject))
                    if not preparing:
                        self.authority.recheck(actor, now=e.stamp(self.clock()))
                        return {"status": "observed_exact_scope_needs_pin", "subject_sha256": digest, **dict.fromkeys(e.FLAGS, False)}
                    if digest != e.token(body["subject_sha256"]) or e.token(body["request_id"], 32) in requests:
                        conflict()
                    packet, obs = self.target.source(now)
                    payload = {"request_id": body["request_id"], "kind": kind, "current_generation": current, "subject": subject,
                               "subject_sha256": digest, "prepared_by": actor,
                               "reviewer": self.authority.eligible(packet["enrollment"]["reviewer"], "reviewer"), "created_at": now,
                               "expires_at": min(now + 300, actor["expires_at"], packet["expires_at"], obs["valid_until"], subject.get("candidate_expiry", now + 300)),
                               "packet_sha256": self.target.packet_sha256, "observation_sha256": self.target.observation_sha256,
                               **dict.fromkeys(e.FLAGS, False)}
                    self.proposal_current({"payload": payload}, current, actor, e.stamp(self.clock()))
                    event = self.lifecycle.append(fd, fence, events, "proposed", payload)
                    self.proposal_current(event, current, actor, e.stamp(self.clock()))
                    return {"status": "lifecycle_needs_independent_decision", "proposal_sha256": ref(event),
                            "enrollment_sha256": current, "lifecycle_head_sha256": event["head"], **dict.fromkeys(e.FLAGS, False)}
                if action == "decide_lifecycle":
                    if set(body) != {"request_id", "proposal_sha256", "decision", "reason_code"}:
                        reject()
                    ident = e.token(body["request_id"], 32)
                    if actor["kind"] != "reviewer" or ident not in requests or "decision" in requests[ident] or ref(requests[ident]["proposal"]) != e.token(body["proposal_sha256"]):
                        conflict()
                    proposal = requests[ident]["proposal"]
                    self.proposal_current(proposal, current, actor, now)
                    payload = {"request_id": ident, "proposal_sha256": body["proposal_sha256"], "reviewed_by": actor,
                               "decision": body["decision"], "reason_code": body["reason_code"], "created_at": now, **dict.fromkeys(e.FLAGS, False)}
                    event = self.lifecycle.append(fd, fence, events, "decided", payload)
                    self.proposal_current(proposal, current, actor, e.stamp(self.clock()))
                    self.point("lifecycle_decision_complete")
                    after_current = fold([*events, event], self.lifecycle.scope)[0]
                    return {"status": "lifecycle_decision_retained", "decision_sha256": ref(event), "decision": body["decision"],
                            "enrollment_sha256": after_current, "lifecycle_head_sha256": event["head"], **dict.fromkeys(e.FLAGS, False)}
                child = self.child(current)
                if action in {"prepare_restore", "select_restored_target", "execute_restore", "reconcile_restore", "restore_status"}:
                    ident = body.get("operation_id", body.get("request_id"))
                    if any(key[1] == ident for key in retired):
                        conflict()
                if action == "selected_history":
                    with child.controls.locked() as (_, _, controls, _):
                        _, selections = restore_fold(controls, child.controls.scope)
                        selection = selections.get(body.get("selection_id"))
                        if selection and any(key[1] == selection["payload"]["operation_id"] for key in retired):
                            conflict()
                return child.handle(scope, body)
