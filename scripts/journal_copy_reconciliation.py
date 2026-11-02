"""Bounded, read-only copy reconciliation. No recovery, execution or adoption."""

import asyncio
from dataclasses import dataclass

import operator_enrollment_evidence as e
import operator_recovery_inventory as inventory
from cryptography.exceptions import InvalidTag
from fastapi import HTTPException
from journal_materialization import FLAGS, INTENT_FIELDS, OP_REFS, JournalMaterializer

REFS = OP_REFS | {"decision_ciphertext_sha256", "intent_ciphertext_sha256", "completion_ciphertext_sha256"}


def result(state="unavailable", **values):
    return {"schema": "journal-copy-reconciliation-v1", "state": state,
            "metadata_only": True, "read_only": True, "atomic_snapshot": False,
            "current_authority_assessed": False, "production_execution_authorized": False,
            "automatic_resume": False, "fresh_independent_review_required": True,
            "observation": None, "snapshot_sha256": None, "history": None,
            **dict.fromkeys(FLAGS, False), **values}


@dataclass(frozen=True, kw_only=True)
class CopyReconciler:
    """Service bindings are trusted local wiring, never caller-selected paths/keys.

    Physical observations may supply an exact ciphertext reference for a later
    authenticated read. They cannot supply a lost acknowledgement or new authority.
    """

    service: JournalMaterializer

    def validate(self):
        if not isinstance(self.service, JournalMaterializer):
            e.reject()
        return self.service.validate()

    async def capture(self, actor):
        s = self.service
        binding = self.validate()
        copy = await s.readiness.capture(actor)
        controls = await s.controls.capture(actor)
        if controls["state"] != "observed_journal_metadata":
            if controls["state"] == "budget_exhausted":
                raise TimeoutError
            raise FileExistsError
        s.planner.authority.recheck(actor, now=s.planner.clock())
        if controls["source_snapshot_sha256"] != copy["journal_snapshot_sha256"]:
            raise FileExistsError
        if self.validate() != binding:
            raise FileExistsError
        return {"binding_sha256": binding, "copy": copy, "controls": controls["journal"],
                "controls_source_snapshot_sha256": controls["source_snapshot_sha256"],
                "controls_snapshot_sha256": controls["journal_snapshot_sha256"],
                "origin": await CopyReconciler(service=s.origin.service).capture(actor) if s.origin else None}

    @staticmethod
    def publication(observation, ident, cipher=None):
        rows = [r for r in observation["controls"]["entries"] if r["record_id"] == ident]
        if not rows:
            if cipher is not None:
                raise FileExistsError
            return False
        if len(rows) != 1 or rows[0]["state"] != "single_link_record":
            raise FileExistsError
        if cipher is not None and rows[0]["ciphertext_sha256"] != e.token(cipher):
            raise FileExistsError
        return True

    async def reconcile(self, actor, observation, request):
        s = self.service
        plan = s.plan(request)
        self.publication(observation, plan["operation_id"], request["plan_ciphertext_sha256"])
        review_id = s.ident("review", plan["operation_id"], request["plan_ciphertext_sha256"])
        ic, rc = request["intent_ciphertext_sha256"], request["completion_ciphertext_sha256"]
        dc = request["decision_ciphertext_sha256"]
        history = {**{k: request[k] for k in OP_REFS}, "decision_ciphertext_sha256": dc,
                   "intent_ciphertext_sha256": ic, "completion_ciphertext_sha256": rc,
                   "mode": s.mode, "manifest_sha256": s.manifest_sha256,
                   "target_comparison": observation["copy"]["comparison"],
                   "execution_review_current": False, "intent_authenticated": False,
                   "completion_authenticated": False}
        if dc is None:
            if ic is not None or rc is not None:
                e.reject()
            history["review_publication_observed"] = self.publication(observation, review_id)
            return result("review_reference_not_supplied", history=history)
        self.publication(observation, review_id, dc)
        review = s.review(plan, request)
        current = True
        try:
            await s.source_current(actor, plan, review)
        except (FileExistsError, PermissionError, HTTPException):
            current = False
        history.update(decision=review["decision"], reviewed_at=review["reviewed_at"], execution_review_current=current)
        intent_id = s.ident("intent", plan["operation_id"], request["plan_ciphertext_sha256"])
        observed = self.publication(observation, intent_id, ic)
        history["intent_publication_observed"] = observed
        if ic is None:
            if rc is not None:
                e.reject()
            return result("intent_reference_not_supplied" if observed else "intent_not_observed", history=history)
        intent = s.read("intent", intent_id, ic, INTENT_FIELDS, "journal-materialization-intent-v1")
        if (any(intent[k] != request[k] for k in OP_REFS | {"decision_ciphertext_sha256"})
                or intent["binding_sha256"] != self.validate() or intent["mode"] != s.mode
                or intent["manifest_sha256"] != s.manifest_sha256 or review["decision"] != "authorize"
                or not plan["created_at"] <= e.stamp(intent["created_at"]) <= plan["expires_at"]):
            e.reject()
        history.update(intent_authenticated=True, intent_sha256=e.sha(e.encode(intent)))
        completion_id = s.ident("completion", plan["operation_id"], ic)
        observed = self.publication(observation, completion_id, rc)
        history["completion_publication_observed"] = observed
        if rc is None:
            return result("completion_reference_not_supplied" if observed else "consumed_intent_without_completion", history=history)
        verified = await s.verify(actor, plan, review, {**request, "intent_sha256": history["intent_sha256"]})
        if verified["state"] not in {"retained_copy_verified", "retained_copy_verified_review_stale"}:
            raise FileExistsError
        history.update(completion_authenticated=True, execution_review_current=verified["execution_review_current"])
        return result("retained_completion_reconciled" if history["execution_review_current"] else
                      "retained_completion_reconciled_review_stale", history=history)

    async def dispatch(self, scope, operation, **request):
        try:
            async with asyncio.timeout(inventory.TOTAL_SECONDS):
                self.validate()
                actor = self.service.planner.actor(scope)
                if operation not in {"inventory", "reconcile"} or (operation == "inventory" and request):
                    e.reject()
                if operation == "reconcile" and set(request) != REFS | {"expected_snapshot_sha256"}:
                    e.reject()
                first = await self.capture(actor)
                snapshot = e.sha(e.encode(first))
                if operation == "reconcile":
                    if e.token(request["expected_snapshot_sha256"]) != snapshot:
                        raise FileExistsError
                    response = await self.reconcile(actor, first, request)
                else:
                    response = result("observed_copy_restart_metadata")
                if await self.capture(actor) != first:
                    raise FileExistsError
                history = response["history"]
                if history and "decision" in history:
                    plan = self.service.plan(request)
                    review = self.service.review(plan, request)
                    try:
                        await self.service.source_current(actor, plan, review)
                    except (FileExistsError, PermissionError, HTTPException):
                        history["execution_review_current"] = False
                        if response["state"] == "retained_completion_reconciled":
                            response["state"] = "retained_completion_reconciled_review_stale"
                self.service.planner.authority.recheck(actor, now=self.service.planner.clock())
                return {**response, "observation": first, "snapshot_sha256": snapshot}
        except (PermissionError, HTTPException):
            return result("denied")
        except TimeoutError:
            return result("budget_exhausted")
        except FileExistsError:
            return result("snapshot_or_publication_conflict")
        except (InvalidTag, ValueError, TypeError, KeyError, RecursionError, FileNotFoundError):
            return result("unverifiable")
        except Exception:
            return result()  # No paths, credentials, exception text or partial history.
