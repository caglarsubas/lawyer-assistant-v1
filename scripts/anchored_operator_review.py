"""Unregistered authenticated recovery and explicit, parent-linked fresh review."""

import threading

import operator_enrollment_evidence as e
from authenticated_operator_review import PREFIX, ReviewHandoff, conflict
from fastapi import HTTPException
from operator_review_journal import ReviewJournal


class AnchoredReviewHandoff(ReviewHandoff):
    actions = (*ReviewHandoff.actions, "recover", "rereview")

    def __init__(self, authority, target, ledger, journal, **kwargs):
        if not isinstance(journal, ReviewJournal) or journal.ledger != e.directory(ledger):
            raise ValueError("Bound anchored review journal required")
        expected = {"firm_id": authority.firm_id, "profile_id": authority.profile_id,
                    "marker_sha256": authority.marker_sha, "bindings_sha256": e.sha(e.encode(dict(authority.bindings)))}
        if journal.scope != expected:
            raise ValueError("Exact disposable identity scope required")
        self.journal, self.parent_link, self.admission = journal, None, threading.Lock()
        super().__init__(authority, target, ledger, **kwargs)

    def retain_record(self, path, raw):
        return self.journal.append(path, raw, self.parent_link if path.name.endswith(".handoff.json") else None)

    def assigned(self, scope):
        now = e.stamp(self.clock())
        actor = self.authority.resolve(scope, None, now=now)
        packet, _ = self.target.source(now, historical=True)
        if actor["user_id"] not in {packet["enrollment"]["provisioned_by"], packet["enrollment"]["reviewer"]}:
            raise HTTPException(403, "Assigned operator required")
        return actor

    def handle(self, scope, value):
        action = scope["path"][len(PREFIX):]
        with self.admission:
            if action == "recover":
                actor = self.assigned(scope)
                if set(value) != {"expected", "repair"} or type(value["repair"]) is not bool:
                    raise ValueError("Explicit recovery pin required")
                if value["expected"] is not None and (not isinstance(value["expected"], dict) or set(value["expected"]) != {"anchor_head_sha256", "journal_tip_sha256"}):
                    raise ValueError("Exact recovery heads required")
                def recheck():
                    self.authority.recheck(actor, now=e.stamp(self.clock()))
                result = self.journal.recover(value["expected"], repair=value["repair"], recheck=recheck)
                if value["repair"]:
                    self.point("recovered")
                recheck()
                return result
            # No ordinary read or write can silently advance an anchor or project.
            with self.journal.locked():
                pass
            self.parent_link = None
            if action == "rereview":
                self.assigned(scope)
                required = {"parent", "request_id", "packet_sha256", "observation_sha256"}
                if set(value) != required or not isinstance(value["parent"], dict) or set(value["parent"]) != {"handoff_id", "handoff_sha256", "decision_sha256"}:
                    raise ValueError("Exact retained parent required")
                self.parent_link = self.journal.parent(value["parent"])
                if value["request_id"] == self.parent_link["handoff_id"]:
                    conflict()
                scope = {**scope, "path": PREFIX + "prepare"}
                value = {k: v for k, v in value.items() if k != "parent"}
            try:
                result = super().handle(scope, value)
                if action == "rereview":
                    result["status"] = "fresh_independent_review_required"
                if action == "inspect" and result["status"] != "observed_decision_needs_pin":
                    result["parent"] = self.journal.lineage(value["handoff_id"])
                return result
            finally:
                self.parent_link = None
