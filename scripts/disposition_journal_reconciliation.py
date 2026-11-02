"""Read-only restart observations of independently reviewed disposition journals."""

import asyncio
from dataclasses import dataclass

import operator_enrollment_evidence as e
import operator_recovery_inventory as inventory
from copy_recovery_disposition import FLAGS, REFS, DispositionPlanner
from cryptography.exceptions import InvalidTag
from fastapi import HTTPException


def result(state="unavailable", **values):
    return {"schema": "disposition-journal-reconciliation-v1", "state": state,
            "read_only": True, "source_read_only": True, "metadata_only": True, "planning_only": True,
            "atomic_snapshot": False, "current_authority_assessed": False,
            "production_execution_authorized": False, "automatic_resume": False,
            "fresh_independent_review_required": True, "observation": None, "snapshot_sha256": None,
            "plan": None, "review": None, "planning_review_current": False,
            **dict.fromkeys(FLAGS, False), **values}


@dataclass(frozen=True, kw_only=True)
class DispositionReconciler:
    """Trusted, independently pinned local wiring; callers supply no stores or keys."""

    disposition: DispositionPlanner

    def validate(self):
        if not isinstance(self.disposition, DispositionPlanner):
            e.reject()
        return self.disposition.validate()

    async def capture(self, actor):
        bound = self.validate()
        d = self.disposition
        source = await d.source.capture(actor)
        journal = await d.reviews.capture(actor)
        if journal["state"] != "observed_journal_metadata":
            if journal["state"] == "budget_exhausted":
                raise TimeoutError
            if journal["state"] == "denied":
                raise PermissionError
            if journal["state"] == "unverifiable":
                e.reject()
            if journal["state"] == "snapshot_conflict":
                raise FileExistsError
            raise RuntimeError
        if (source["controls_snapshot_sha256"] != journal["source_snapshot_sha256"]
                or self.validate() != bound):
            raise FileExistsError
        d.planner.authority.recheck(actor, now=d.planner.clock())
        return {"binding_sha256": bound, "copy": source, "journal": journal["journal"],
                "source_snapshot_sha256": journal["source_snapshot_sha256"],
                "journal_snapshot_sha256": journal["journal_snapshot_sha256"]}

    @staticmethod
    def publication(observed, ident, cipher):
        rows = [r for r in observed["journal"]["entries"] if r["kind"] == "record" and r["record_id"] == ident]
        if not rows:
            if cipher is not None:
                raise FileExistsError
            return None
        if len(rows) != 1 or rows[0]["state"] != "single_link_record":
            e.reject()
        if cipher is not None and rows[0]["ciphertext_sha256"] != e.token(cipher):
            raise FileExistsError
        return rows[0]

    async def reconcile(self, scope, request, observed):
        ident = e.token(request["plan_id"], 32)
        cipher, digest, decision = (request[k] for k in
                                   ("plan_ciphertext_sha256", "plan_sha256", "decision_ciphertext_sha256"))
        if (cipher is None) != (digest is None) or cipher is None and decision is not None:
            e.reject()
        if cipher is not None:
            e.token(cipher)
            e.token(digest)
        if decision is not None:
            e.token(decision)
        row = self.publication(observed, ident, cipher)
        if row is None:
            return result("plan_not_observed")
        if cipher is None:
            return result("plan_references_unavailable", plan_publication_observed=True)
        d = self.disposition
        plan = d.plan(request)
        decision_row = self.publication(observed, d.decision_id(plan, cipher), decision)
        checked = await d.dispatch(scope, "inspect", **{k: request[k] for k in REFS},
                                   decision_ciphertext_sha256=decision)
        if checked["state"] not in {"retained_disposition_review", "retained_disposition_review_stale"}:
            return result(checked["state"])
        if checked["plan"] != plan or decision is not None and checked["review"] is None:
            e.reject()
        state = ("decision_reference_not_supplied" if decision_row else "decision_not_observed") if decision is None else (
            "retained_disposition_reconciled" if checked["planning_review_current"] else "retained_disposition_reconciled_stale")
        return result(state, plan=plan, review=checked["review"],
                      planning_review_current=checked["planning_review_current"],
                      plan_publication_observed=True, decision_publication_observed=decision_row is not None,
                      decision_reference_basis="caller_supplied" if decision is not None else "not_supplied")

    async def dispatch(self, scope, operation, **request):
        try:
            async with asyncio.timeout(inventory.TOTAL_SECONDS):
                self.validate()
                if operation not in {"inventory", "reconcile"}:
                    e.reject()
                if operation == "inventory" and request or operation == "reconcile" and set(request) != (
                        REFS | {"decision_ciphertext_sha256", "expected_snapshot_sha256"}):
                    e.reject()
                d = self.disposition
                p = d.planner
                actor = p.actor(scope)
                first = await self.capture(actor)
                snapshot = e.sha(e.encode(first))
                if operation == "inventory":
                    response = result("observed_disposition_journal_metadata")
                else:
                    if e.token(request["expected_snapshot_sha256"]) != snapshot:
                        raise FileExistsError
                    response = await self.reconcile(scope, request, first)
                if await self.capture(actor) != first:
                    raise FileExistsError
                if response["plan"] is not None:
                    plan, review = response["plan"], response["review"]
                    if d.plan(request) != plan or review is not None and d.review(plan, request) != review:
                        raise FileExistsError
                    try:
                        p.current_actors(plan)
                        p.current_window(plan)
                        if review is not None:
                            p.authority.recheck(review["reviewed_by"], now=p.clock())
                    except (PermissionError, HTTPException, FileExistsError):
                        response["planning_review_current"] = False
                        if review is not None:
                            response["state"] = "retained_disposition_reconciled_stale"
                p.authority.recheck(actor, now=p.clock())
                self.validate()
                if response["state"] in {"observed_disposition_journal_metadata", "plan_not_observed",
                        "plan_references_unavailable", "decision_reference_not_supplied", "decision_not_observed",
                        "retained_disposition_reconciled", "retained_disposition_reconciled_stale"}:
                    return {**response, "observation": first, "snapshot_sha256": snapshot}
                return response
        except (PermissionError, HTTPException):
            return result("denied")
        except TimeoutError:
            return result("budget_exhausted")
        except FileExistsError:
            return result("snapshot_or_publication_conflict")
        except (InvalidTag, ValueError, TypeError, KeyError, RecursionError, FileNotFoundError):
            return result("unverifiable")
        except Exception:
            return result()  # No paths, credentials, exception text or partial plaintext.
