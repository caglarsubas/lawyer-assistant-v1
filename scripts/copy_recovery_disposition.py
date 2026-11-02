"""Encrypted, independently reviewed disposition plans. Never execute recovery."""

import asyncio
from dataclasses import asdict, dataclass

import operator_enrollment_evidence as e
import operator_recovery_inventory as inventory
import private_inventory_receipts as receipts
from cryptography.exceptions import InvalidTag
from fastapi import HTTPException
from journal_copy_reconciliation import REFS as COPY_REFS
from journal_copy_reconciliation import CopyReconciler
from journal_copy_reconciliation import result as reconciliation_result
from journal_materialization import FLAGS
from planning_journal_reconciliation import JournalReconciler

REFS = {"plan_id", "plan_ciphertext_sha256", "plan_sha256"}
PLAN = {"schema", "plan_id", "binding_sha256", "copy_refs", "reconciliation", "reconciliation_sha256",
        "disposition", "prepared_by", "assigned_reviewer", "created_at", "expires_at", *FLAGS}
REVIEW = {"schema", *REFS, "decision", "reason_code", "reviewed_by", "reviewed_at", *FLAGS}
STATES = {"review_reference_not_supplied", "intent_not_observed", "intent_reference_not_supplied",
          "consumed_intent_without_completion", "completion_reference_not_supplied",
          "retained_completion_reconciled", "retained_completion_reconciled_review_stale"}
DECISIONS = {"accept": "exact_observation_and_disposition_checked", "changes_required": "fresh_disposition_plan_required",
             "reject": "disposition_plan_declined"}


def result(state="unavailable", **values):
    return {"schema": "copy-recovery-disposition-v1", "state": state, "metadata_only": True, "planning_only": True,
            "source_read_only": True, "atomic_snapshot": False, "current_authority_assessed": False,
            "production_execution_authorized": False, "automatic_resume": False,
            "fresh_independent_review_required": True, "plan": None, "review": None,
            **dict.fromkeys(FLAGS, False), **values}


def dispositions(reconciliation):
    state = reconciliation["state"]
    if state not in STATES or not isinstance(reconciliation["history"], dict):
        e.reject()
    values = {"retain_for_independent_assessment"}
    if state in {"consumed_intent_without_completion", "retained_completion_reconciled_review_stale"}:
        values.add("seek_fresh_independent_context")
    if reconciliation["history"].get("completion_authenticated") is True:
        values.add("retain_verified_history")
    return values


@dataclass(frozen=True, kw_only=True)
class DispositionPlanner:
    source: CopyReconciler
    reviews: JournalReconciler

    def __post_init__(self):
        self.validate()

    @property
    def planner(self):
        return self.reviews.planner

    def validate(self):
        if not isinstance(self.source, CopyReconciler) or not isinstance(self.reviews, JournalReconciler):
            e.reject()
        binding = self.source.validate()
        self.reviews.validate()
        s, p = self.source.service, self.planner
        original = s.planner
        if (p.source is not s.controls.planner.journal or p.pins != s.controls.binding.pins
                or p.authority is not original.authority or p.clock is not original.clock
                or (p.preparer, p.reviewer) != (original.preparer, original.reviewer)):
            e.reject()
        protected = [original.source, original.journal, s.readiness.candidate,
                     s.readiness.reviews.planner.journal, s.controls.planner.journal]
        if s.origin:
            old = s.origin.service
            protected += [old.planner.source, old.planner.journal, old.readiness.candidate,
                          old.readiness.reviews.planner.journal, old.controls.planner.journal]
        if any(p.journal.root == x.root or p.journal.root in x.root.parents or x.root in p.journal.root.parents
               or p.journal.key == x.key for x in protected):
            e.reject()
        return e.sha(e.encode({"schema": "copy-disposition-binding-v1", "source": binding,
                              "reviews": asdict(self.reviews.binding)}))

    async def observe(self, scope, refs):
        if not isinstance(refs, dict) or set(refs) != COPY_REFS | {"expected_snapshot_sha256"}:
            e.reject()
        value = await self.source.dispatch(scope, "reconcile", **refs)
        if value["state"] == "denied":
            raise PermissionError
        if value["state"] == "budget_exhausted":
            raise TimeoutError
        if value["state"] == "snapshot_or_publication_conflict":
            raise FileExistsError
        if value["state"] == "unavailable":
            raise RuntimeError
        if value["state"] not in STATES:
            e.reject()
        return value

    def plan(self, request):
        ident, cipher, digest = (request[k] for k in ("plan_id", "plan_ciphertext_sha256", "plan_sha256"))
        value = self.planner.read("copy-disposition-plan-v1", ident, cipher)
        if (not isinstance(value, dict) or set(value) != PLAN or value["schema"] != "copy-disposition-plan-v1"
                or value["plan_id"] != e.token(ident, 32) or e.sha(e.encode(value)) != e.token(digest)
                or value["binding_sha256"] != self.validate() or any(value[k] is not False for k in FLAGS)
                or value["prepared_by"]["user_id"] != self.planner.preparer
                or value["assigned_reviewer"]["user_id"] != self.planner.reviewer
                or e.stamp(value["expires_at"]) - e.stamp(value["created_at"]) != 300):
            e.reject()
        refs, observed = value["copy_refs"], value["reconciliation"]
        fixed = reconciliation_result()
        if (not isinstance(refs, dict) or set(refs) != COPY_REFS | {"expected_snapshot_sha256"}
                or set(observed) != set(fixed)
                or any(observed[k] != v for k, v in fixed.items() if k not in {"state", "observation", "snapshot_sha256", "history"})
                or observed["schema"] != "journal-copy-reconciliation-v1" or observed["read_only"] is not True
                or observed["metadata_only"] is not True or any(observed[k] is not False for k in FLAGS)
                or observed["observation"]["binding_sha256"] != self.source.validate()
                or e.sha(e.encode(observed["observation"])) != e.token(refs["expected_snapshot_sha256"])
                or observed["snapshot_sha256"] != refs["expected_snapshot_sha256"]
                or any(observed["history"][k] != refs[k] for k in COPY_REFS)
                or value["reconciliation_sha256"] != e.sha(e.encode(observed))
                or value["disposition"] not in dispositions(observed)):
            e.reject()
        return value

    @staticmethod
    def decision_id(plan, cipher):
        return e.sha(e.encode(["copy-disposition-review-v1", plan["plan_id"], cipher]))[:32]

    def review(self, plan, request):
        cipher = e.token(request["decision_ciphertext_sha256"])
        value = self.planner.read("copy-disposition-review-v1", self.decision_id(plan, request["plan_ciphertext_sha256"]), cipher)
        if (not isinstance(value, dict) or set(value) != REVIEW or value["schema"] != "copy-disposition-review-v1"
                or any(value[k] != request[k] for k in REFS) or any(value[k] is not False for k in FLAGS)
                or value["reviewed_by"]["user_id"] != self.planner.reviewer or value["decision"] not in DECISIONS
                or value["reason_code"] != DECISIONS[value["decision"]]
                or not plan["created_at"] <= e.stamp(value["reviewed_at"]) <= plan["expires_at"]):
            e.reject()
        return value

    async def current(self, scope, actor, plan, review=None):
        self.validate()
        p = self.planner
        p.current_actors(plan)
        p.current_window(plan)
        if review is not None:
            p.authority.recheck(review["reviewed_by"], now=p.clock())
        if await self.observe(scope, plan["copy_refs"]) != plan["reconciliation"]:
            raise FileExistsError
        p.current_actors(plan)
        p.current_window(plan)
        p.authority.recheck(actor, now=p.clock())

    async def dispatch(self, scope, operation, **request):
        try:
            async with asyncio.timeout(inventory.TOTAL_SECONDS):
                self.validate()
                if operation not in {"prepare", "decide", "inspect"}:
                    e.reject()
                p = self.planner
                actor = p.actor(scope, "preparer" if operation == "prepare" else "reviewer" if operation == "decide" else None)
                if operation == "prepare":
                    if set(request) != {"plan_id", "copy_refs", "disposition"}:
                        e.reject()
                    observed = await self.observe(scope, request["copy_refs"])
                    if request["disposition"] not in dispositions(observed):
                        e.reject()
                    now = e.stamp(p.clock())
                    plan = {"schema": "copy-disposition-plan-v1", "plan_id": e.token(request["plan_id"], 32),
                        "binding_sha256": self.validate(), "copy_refs": request["copy_refs"], "reconciliation": observed,
                        "reconciliation_sha256": e.sha(e.encode(observed)), "disposition": request["disposition"],
                        "prepared_by": actor, "assigned_reviewer": p.authority.eligible(p.reviewer, "reviewer"),
                        "created_at": now, "expires_at": now + 300, **dict.fromkeys(FLAGS, False)}
                    await self.current(scope, actor, plan)
                    cipher = p.write("copy-disposition-plan-v1", plan["plan_id"], plan)
                    refs = {"plan_id": plan["plan_id"], "plan_ciphertext_sha256": cipher, "plan_sha256": e.sha(e.encode(plan))}
                    await self.current(scope, actor, plan)
                    if self.plan(refs) != plan:
                        raise FileExistsError
                    p.authority.recheck(actor, now=p.clock())
                    return result("disposition_needs_independent_review", **refs)
                fields = REFS | ({"decision", "reason_code"} if operation == "decide" else {"decision_ciphertext_sha256"})
                if set(request) != fields:
                    e.reject()
                first = await self.source.capture(actor)
                plan = self.plan(request)
                if operation == "decide":
                    decision = request["decision"]
                    if decision not in DECISIONS or request["reason_code"] != DECISIONS[decision]:
                        e.reject()
                    await self.current(scope, actor, plan)
                    review = {"schema": "copy-disposition-review-v1", **{k: request[k] for k in REFS | {"decision", "reason_code"}},
                        "reviewed_by": actor, "reviewed_at": e.stamp(p.clock()), **dict.fromkeys(FLAGS, False)}
                    cipher = p.write("copy-disposition-review-v1", self.decision_id(plan, request["plan_ciphertext_sha256"]), review)
                    await self.current(scope, actor, plan, review)
                    if self.plan(request) != plan or self.review(plan, {**request, "decision_ciphertext_sha256": cipher}) != review:
                        raise FileExistsError
                    p.authority.recheck(actor, now=p.clock())
                    return result("reviewed_disposition_plan" if decision == "accept" else decision, decision_ciphertext_sha256=cipher)
                review = None if request["decision_ciphertext_sha256"] is None else self.review(plan, request)
                current = True
                try:
                    await self.current(scope, actor, plan, review)
                except (FileExistsError, PermissionError, HTTPException):
                    current = False
                if (await self.source.capture(actor) != first or self.plan(request) != plan
                        or review is not None and self.review(plan, request) != review):
                    raise FileExistsError
                try:
                    p.current_actors(plan)
                    p.current_window(plan)
                    if review is not None:
                        p.authority.recheck(review["reviewed_by"], now=p.clock())
                except (FileExistsError, PermissionError, HTTPException):
                    current = False
                p.authority.recheck(actor, now=p.clock())
                return result("retained_disposition_review" if current else "retained_disposition_review_stale",
                              plan=plan, review=review, planning_review_current=current, operation_read_only=True)
        except (PermissionError, HTTPException):
            return result("denied")
        except TimeoutError:
            return result("budget_exhausted")
        except receipts.RetentionUncertain:
            return result("retention_uncertain")
        except FileExistsError:
            return result("snapshot_or_publication_conflict")
        except (InvalidTag, ValueError, TypeError, KeyError, RecursionError, FileNotFoundError):
            return result("unverifiable")
        except Exception:
            return result()  # No credentials, source paths, exception text or partial history.
