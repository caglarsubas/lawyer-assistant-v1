"""Read-only reconciliation of exact planning-journal observations after restart."""

import asyncio
from dataclasses import asdict, dataclass

import operator_enrollment_evidence as e
import operator_recovery_inventory as inventory
import receipt_recovery_inventory as physical
from cryptography.exceptions import InvalidTag
from fastapi import HTTPException
from receipt_provisioning_readiness import Pins, fingerprint
from receipt_recovery_planning import DECISIONS, RecoveryPlanner


def result(state="unavailable", **values):
    return {"schema": "planning-journal-reconciliation-v1", "state": state, "read_only": True,
            "metadata_only": True, "atomic_snapshot": False, "current_authority_assessed": False,
            "acknowledgement_recovered": False, "fresh_independent_review_required": True,
            "journal_record_authenticated": False, "journal": None, "plan": None, "review": None,
            **dict.fromkeys(physical.FLAGS, False), **values}


@dataclass(frozen=True, kw_only=True)
class JournalBinding:
    pins: Pins
    source_pins_sha256: str
    preparer_id: str
    reviewer_id: str

    def __post_init__(self):
        if not isinstance(self.pins, Pins) or self.preparer_id == self.reviewer_id:
            e.reject()
        e.token(self.source_pins_sha256)
        e.token(self.preparer_id, 32)
        e.token(self.reviewer_id, 32)


@dataclass(frozen=True, kw_only=True)
class JournalReconciler:
    """Bindings are independently supplied trusted wiring, never request fields.

    Observed hashes identify retained bytes, not a recovered acknowledgement or
    permission to adopt, repair, delete, renew authority or execute a plan.
    """
    planner: RecoveryPlanner
    binding: JournalBinding

    def __post_init__(self):
        self.validate()

    def validate(self):
        planner, binding = self.planner, self.binding
        if not isinstance(planner, RecoveryPlanner) or not isinstance(binding, JournalBinding):
            e.reject()
        planner.validate()
        pins = binding.pins
        if (e.sha(e.encode(asdict(planner.pins))) != binding.source_pins_sha256
                or planner.preparer != binding.preparer_id or planner.reviewer != binding.reviewer_id
                or planner.journal.context_id != pins.context_id or planner.journal.scope_sha256 != pins.scope_sha256
                or planner.journal.identity != pins.store_identity or fingerprint(planner.journal.key) != pins.key_fingerprint
                or planner.authority.profile_id != pins.profile_id or planner.authority.marker_sha != pins.profile_sha256
                or planner.source.root == planner.journal.root or planner.source.root in planner.journal.root.parents
                or planner.journal.root in planner.source.root.parents or planner.source.key == planner.journal.key):
            e.reject()

    async def capture(self, actor):
        self.validate()
        source = await self.planner.observe(actor)
        if source["state"] != "observed_metadata":
            return result(source["state"])
        reader, digest = self.planner.reader(actor)
        journal = await physical.observe(self.planner.journal, reader, self.binding.pins, actor_sha256=digest)
        if journal["state"] != "observed_metadata":
            return result(journal["state"])
        self.validate()
        self.planner.authority.recheck(actor, now=self.planner.clock())
        return result("observed_journal_metadata", journal=journal["inventory"],
                      source_snapshot_sha256=source["snapshot_sha256"], journal_snapshot_sha256=journal["snapshot_sha256"])

    async def dispatch(self, scope, operation, **request):
        try:
            async with asyncio.timeout(inventory.TOTAL_SECONDS):
                self.validate()
                actor = self.planner.actor(scope)
                first = await self.capture(actor)
                if first["state"] != "observed_journal_metadata":
                    return first
                if operation == "inventory":
                    if request:
                        e.reject()
                    response = first
                else:
                    if operation != "reconcile" or set(request) != {"plan_id", "plan_ciphertext_sha256", "plan_sha256",
                            "expected_journal_snapshot_sha256", "expected_source_snapshot_sha256"}:
                        e.reject()
                    for field in ("expected_journal_snapshot_sha256", "expected_source_snapshot_sha256"):
                        e.token(request[field])
                    if (request["expected_journal_snapshot_sha256"] != first["journal_snapshot_sha256"]
                            or request["expected_source_snapshot_sha256"] != first["source_snapshot_sha256"]):
                        return result("snapshot_conflict")
                    response = await self.reconcile(scope, request, first)
                # Never return cached inventory or decrypted history after a change.
                last = await self.capture(actor)
                if (last["state"] != "observed_journal_metadata" or last != first):
                    return result(last["state"] if last["state"] != "observed_journal_metadata" else "snapshot_conflict")
                self.validate()
                if response.get("plan") is not None:
                    try:
                        self.planner.current_actors(response["plan"])
                        self.planner.current_window(response["plan"])
                        if response.get("review") is not None:
                            self.planner.authority.recheck(response["review"]["reviewed_by"], now=self.planner.clock())
                    except (PermissionError, HTTPException, FileExistsError):
                        response["historical_review_state"] = "stale_review_retained"
                        if response.get("review") is not None:
                            response["state"] = "stale_decision_preserved"
                self.planner.authority.recheck(actor, now=self.planner.clock())
                return response
        except (PermissionError, HTTPException):
            return result("denied")
        except TimeoutError:
            return result("budget_exhausted")
        except (InvalidTag, ValueError, TypeError, KeyError, RecursionError):
            return result("unverifiable")
        except Exception:
            return result()  # No paths, credentials, exception text or partial plaintext.

    async def reconcile(self, scope, request, observed):
        ident = e.token(request["plan_id"], 32)
        cipher, digest = request["plan_ciphertext_sha256"], request["plan_sha256"]
        if (cipher is None) != (digest is None):
            e.reject()
        if cipher is not None:
            e.token(cipher)
            e.token(digest)
        entries = {row["record_id"]: row for row in observed["journal"]["entries"] if row["kind"] == "record"}
        def outcome(state, **values):
            return {**observed, "state": state, **values}
        row = entries.get(ident)
        if row is None:
            return outcome("plan_not_observed")
        if row["state"] != "single_link_record":
            return outcome("plan_publication_unverifiable")
        if cipher is None:
            return outcome("plan_references_unavailable")
        if row["ciphertext_sha256"] != cipher:
            return result("version_conflict")
        # The plan must already have exact independently retained references.
        plan = self.planner.plan(ident, cipher, digest)
        decision_id = self.planner.decision_id(ident, cipher)
        decision = entries.get(decision_id)
        if decision is not None and decision["state"] != "single_link_record":
            return outcome("decision_publication_unverifiable")
        expected_decision = decision["ciphertext_sha256"] if decision else None
        checked = await self.planner.dispatch(scope, "inspect", plan_id=ident, plan_ciphertext_sha256=cipher,
            plan_sha256=digest, decision_ciphertext_sha256=expected_decision)
        if checked["state"] not in {"pending_independent_review", "stale_review_retained", *(v[1] for v in DECISIONS.values())}:
            return result(checked["state"])
        if checked.get("plan") != plan or (decision is not None and checked.get("review") is None):
            e.reject()
        state = "decision_not_observed" if decision is None else (
            "stale_decision_preserved" if checked["state"] == "stale_review_retained" else "retained_decision_observed")
        return outcome(state, plan=plan, review=checked["review"], journal_record_authenticated=True,
                       historical_review_state=checked["state"], decision_ciphertext_sha256=expected_decision,
                       decision_digest_basis="observed_in_exact_journal_snapshot" if decision else "not_observed")
