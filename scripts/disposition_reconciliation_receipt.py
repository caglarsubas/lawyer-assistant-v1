"""Bounded private receipts of exact read-only disposition reconciliation.

No persistence, imported receipts, acknowledgement recovery or execution route.
A checksum identifies these bytes; it is neither a signature nor authority.
"""

import asyncio
from dataclasses import dataclass

import operator_enrollment_evidence as e
import operator_recovery_inventory as inventory
from copy_recovery_disposition import FLAGS, REFS
from disposition_journal_reconciliation import DispositionReconciler
from fastapi import HTTPException

MAX_BYTES = 8192
FIELDS = REFS | {"decision_ciphertext_sha256", "expected_snapshot_sha256"}
OBSERVED = {"plan_not_observed", "plan_references_unavailable", "decision_not_observed",
            "decision_reference_not_supplied", "retained_disposition_reconciled",
            "retained_disposition_reconciled_stale"}
ERRORS = {"denied", "unverifiable", "snapshot_or_publication_conflict", "budget_exhausted", "unavailable"}
LIMITS = {"read_only": True, "source_read_only": True, "metadata_only": True, "planning_only": True,
          "atomic_snapshot": False, "current_authority_assessed": False,
          "production_execution_authorized": False, "automatic_resume": False,
          "fresh_independent_review_required": True, "receipt_persisted": False,
          "receipt_signed": False, **dict.fromkeys(FLAGS, False)}


def result(state="unavailable", **values):
    return {"schema": "disposition-reconciliation-receipt-access-v1", "state": state,
            **LIMITS, "receipt": None, "receipt_sha256": None, **values}


def project(observed, request, actor, issued_at):
    """Project only an authenticated service result, never a caller-supplied receipt."""
    observation = observed["observation"]
    snapshot = e.sha(e.encode(observation))
    if (observed["state"] not in OBSERVED or snapshot != request["expected_snapshot_sha256"]
            or snapshot != observed["snapshot_sha256"]):
        e.reject()
    review = observed["review"]
    value = {"schema": "disposition-reconciliation-receipt-v1", **LIMITS,
             "integrity_basis": "sha256_transport_checksum_only", "issued_at": e.stamp(issued_at),
             "actor_sha256": e.sha(e.encode(actor)), "binding_sha256": observation["binding_sha256"],
             "snapshot_sha256": snapshot, "copy_snapshot_sha256": e.sha(e.encode(observation["copy"])),
             "source_snapshot_sha256": observation["source_snapshot_sha256"],
             "journal_snapshot_sha256": observation["journal_snapshot_sha256"],
             "references": dict(request), "outcome": observed["state"],
             "plan_authenticated": observed["plan"] is not None, "decision_authenticated": review is not None,
             "decision": review["decision"] if review is not None else None,
             "planning_review_current": review is not None and observed["planning_review_current"],
             "plan_publication_observed": observed.get("plan_publication_observed", False),
             "decision_publication_observed": observed.get("decision_publication_observed", False),
             "reference_basis": "exact_supplied_references_with_explicit_nulls"}
    raw = e.encode(value)
    if len(raw) > MAX_BYTES:
        raise TimeoutError
    return value, e.sha(raw)


@dataclass(frozen=True, kw_only=True)
class DispositionReceiptService:
    reconciler: DispositionReconciler

    async def dispatch(self, scope, operation, **request):
        try:
            async with asyncio.timeout(inventory.TOTAL_SECONDS):
                if (not isinstance(self.reconciler, DispositionReconciler)
                        or operation != "receipt" or set(request) != FIELDS):
                    e.reject()
                request = dict(request)
                self.reconciler.validate()
                p = self.reconciler.disposition.planner
                actor = p.actor(scope)
                first = await self.reconciler.dispatch(scope, "reconcile", **request)
                if first["state"] not in OBSERVED:
                    return result(first["state"] if first["state"] in ERRORS else "unverifiable")
                # No cached result: repeat exact reads, observation and authorization.
                last = await self.reconciler.dispatch(scope, "reconcile", **request)
                if last["state"] not in OBSERVED:
                    return result(last["state"] if last["state"] in ERRORS else "unverifiable")
                if first != last:
                    raise FileExistsError
                receipt, digest = project(last, request, actor, p.clock())
                self.reconciler.validate()
                p.authority.recheck(actor, now=p.clock())
                return result("receipt_ready", receipt=receipt, receipt_sha256=digest)
        except (PermissionError, HTTPException):
            return result("denied")
        except TimeoutError:
            return result("budget_exhausted")
        except FileExistsError:
            return result("snapshot_or_publication_conflict")
        except (ValueError, TypeError, KeyError, RecursionError):
            return result("unverifiable")
        except Exception:
            return result()  # No raw errors or partial confidential observations.
