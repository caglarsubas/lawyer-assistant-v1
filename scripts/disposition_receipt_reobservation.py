"""Fresh authorized observation of exact retained, unsigned receipt metadata.

The retained checksum is independent trusted wiring, never a request field.
No receipt supplies authorization, an acknowledgement, or execution approval.
"""

import asyncio
from dataclasses import dataclass, field

import disposition_reconciliation_receipt as receipts
import operator_enrollment_evidence as e
import operator_recovery_inventory as inventory
from fastapi import HTTPException

HASHES = {"actor_sha256", "binding_sha256", "snapshot_sha256", "copy_snapshot_sha256",
          "source_snapshot_sha256", "journal_snapshot_sha256"}
BOOLEANS = {"plan_authenticated", "decision_authenticated", "planning_review_current",
            "plan_publication_observed", "decision_publication_observed"}
FIELDS = {"schema", "integrity_basis", "issued_at", *HASHES, "references", "outcome", "decision",
          "reference_basis", *BOOLEANS, *receipts.LIMITS}
COMPARABLE = (HASHES - {"actor_sha256", "binding_sha256"}) | BOOLEANS | {"outcome", "decision"}
LIMITS = {**receipts.LIMITS, "retained_receipt_authenticated": False,
          "checksum_authenticates_sender": False, "authority_renewed": False}


def result(state="unavailable", **values):
    return {"schema": "disposition-receipt-reobservation-access-v1", "state": state, **LIMITS,
            "reobservation": None, "reobservation_sha256": None, **values}


def retained(raw, expected, binding, now):
    """Check exact canonical bytes; even a valid checksum is not historical proof."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= receipts.MAX_BYTES or e.sha(raw) != e.token(expected):
        e.reject()
    value = e.decode(raw)
    if (not isinstance(value, dict) or set(value) != FIELDS or e.encode(value) != raw
            or value["schema"] != "disposition-reconciliation-receipt-v1"
            or value["integrity_basis"] != "sha256_transport_checksum_only"
            or value["reference_basis"] != "exact_supplied_references_with_explicit_nulls"
            or any(value[k] is not v for k, v in receipts.LIMITS.items())
            or value["binding_sha256"] != binding or e.stamp(value["issued_at"]) > e.stamp(now)
            or value["outcome"] not in receipts.OBSERVED or any(type(value[k]) is not bool for k in BOOLEANS)):
        e.reject()
    for key in HASHES:
        e.token(value[key])
    refs = value["references"]
    if not isinstance(refs, dict) or set(refs) != receipts.FIELDS:
        e.reject()
    e.token(refs["plan_id"], 32)
    for key in receipts.FIELDS - {"plan_id"}:
        if refs[key] is not None:
            e.token(refs[key])
    if ((refs["plan_ciphertext_sha256"] is None) != (refs["plan_sha256"] is None)
            or refs["expected_snapshot_sha256"] != value["snapshot_sha256"]
            or refs["plan_sha256"] is None and refs["decision_ciphertext_sha256"] is not None
            or value["plan_authenticated"] != (refs["plan_sha256"] is not None)
            or value["decision_authenticated"] != (refs["decision_ciphertext_sha256"] is not None)
            or value["decision_authenticated"] != (value["decision"] in {"accept", "changes_required", "reject"})
            or value["decision"] is not None and not value["decision_authenticated"]
            or value["planning_review_current"] and not value["decision_authenticated"]):
        e.reject()
    expected_outcome = ("plan_not_observed" if not value["plan_publication_observed"] else
                        "plan_references_unavailable" if not value["plan_authenticated"] else
                        ("decision_reference_not_supplied" if value["decision_publication_observed"] else
                         "decision_not_observed") if not value["decision_authenticated"] else
                        "retained_disposition_reconciled" if value["planning_review_current"] else
                        "retained_disposition_reconciled_stale")
    if (value["outcome"] != expected_outcome
            or value["plan_authenticated"] and not value["plan_publication_observed"]
            or value["decision_authenticated"] and not value["decision_publication_observed"]):
        e.reject()
    return value


def project(previous, current, expected):
    changed = sorted(k for k in COMPARABLE if previous[k] != current[k])
    value = {"schema": "disposition-receipt-reobservation-v1", **LIMITS,
             "retained_receipt_sha256": expected,
             "reference_basis": "exact_retained_selection_with_explicit_nulls",
             "comparison_basis": "retained_unsigned_metadata_vs_fresh_authorized_reads",
             "comparison": {"outcome": "changed_metadata" if changed else "unchanged_metadata",
                            "changed_fields": changed},
             "current_receipt": current, "current_receipt_sha256": e.sha(e.encode(current))}
    raw = e.encode(value)
    if len(raw) > receipts.MAX_BYTES:
        raise TimeoutError
    return value, e.sha(raw)


@dataclass(frozen=True, kw_only=True)
class DispositionReceiptReobserver:
    service: receipts.DispositionReceiptService
    expected_receipt_sha256: str = field(repr=False)

    async def dispatch(self, scope, operation, **request):
        try:
            async with asyncio.timeout(inventory.TOTAL_SECONDS):
                if (not isinstance(self.service, receipts.DispositionReceiptService)
                        or operation != "reobserve" or set(request) != {"receipt_bytes"}):
                    e.reject()
                reconciler = self.service.reconciler
                binding = reconciler.validate()
                p = reconciler.disposition.planner
                actor = p.actor(scope)  # Current session/firm/origin/CSRF before inspecting retained bytes.
                previous = retained(request["receipt_bytes"], self.expected_receipt_sha256, binding, p.clock())
                first = await reconciler.dispatch(scope, "inventory")
                if first["state"] != "observed_disposition_journal_metadata":
                    return result(first["state"] if first["state"] in receipts.ERRORS else "unverifiable")
                # Never fill absent plan/review references from the newly observed journal.
                selection = {**previous["references"], "expected_snapshot_sha256": first["snapshot_sha256"]}
                fresh = await self.service.dispatch(scope, "receipt", **selection)
                if fresh["state"] != "receipt_ready":
                    return result(fresh["state"] if fresh["state"] in receipts.ERRORS else "unverifiable")
                current = retained(e.encode(fresh["receipt"]), fresh["receipt_sha256"], binding, p.clock())
                if (current["references"] != selection or current["snapshot_sha256"] != first["snapshot_sha256"]
                        or current["actor_sha256"] != e.sha(e.encode(actor))):
                    raise FileExistsError
                last = await self.service.dispatch(scope, "receipt", **selection)
                if last["state"] != "receipt_ready":
                    return result(last["state"] if last["state"] in receipts.ERRORS else "unverifiable")
                confirmed = retained(e.encode(last["receipt"]), last["receipt_sha256"], binding, p.clock())
                if (confirmed["issued_at"] < current["issued_at"]
                        or current["issued_at"] < previous["issued_at"]
                        or {k: v for k, v in confirmed.items() if k != "issued_at"} != {
                            k: v for k, v in current.items() if k != "issued_at"}):
                    raise FileExistsError
                value, digest = project(previous, confirmed, self.expected_receipt_sha256)
                if reconciler.validate() != binding:
                    raise FileExistsError
                if confirmed["planning_review_current"]:
                    # A review that expires or loses its actors during projection is withheld,
                    # rather than silently renewing the earlier current-review observation.
                    plan = reconciler.disposition.plan(selection)
                    p.current_actors(plan)
                    p.current_window(plan)
                    p.authority.recheck(reconciler.disposition.review(plan, selection)["reviewed_by"], now=p.clock())
                p.authority.recheck(actor, now=p.clock())
                if e.stamp(p.clock()) < confirmed["issued_at"]:
                    raise FileExistsError
                if p.actor(scope) != actor:
                    raise PermissionError
                return result("receipt_reobserved", reobservation=value, reobservation_sha256=digest)
        except (PermissionError, HTTPException):
            return result("denied")
        except TimeoutError:
            return result("budget_exhausted")
        except FileExistsError:
            return result("snapshot_or_publication_conflict")
        except (ValueError, TypeError, KeyError, RecursionError):
            return result("unverifiable")
        except Exception:  # noqa: BLE001 - confidentiality boundary withholds raw diagnostics.
            return result()  # No partial receipts, paths, identities, credentials or raw errors.
