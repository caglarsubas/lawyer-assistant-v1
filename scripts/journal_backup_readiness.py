"""Staged independently reviewed copy readiness; never backup/restore execution."""

import asyncio
from dataclasses import asdict, dataclass

import operator_enrollment_evidence as e
import operator_recovery_inventory as inventory
import private_inventory_receipts as receipts
import receipt_recovery_inventory as physical
from cryptography.exceptions import InvalidTag
from fastapi import HTTPException
from planning_journal_reconciliation import JournalReconciler
from receipt_provisioning_readiness import Pins, fingerprint

FLAGS = physical.FLAGS | {"backup_execution_authorized", "restore_execution_authorized", "trust_migrated",
                         "key_custody_approved", "target_enrolled", "acknowledgement_recovered"}
DECISIONS = {"accept": ("exact_copy_context_checked", "reviewed_for_disposable_copy_qualification"),
             "changes_required": ("fresh_copy_context_required", "changes_required"),
             "reject": ("copy_readiness_declined", "rejected")}
PLAN = {"schema", "plan_id", "binding_sha256", "observation", "snapshot_sha256", "prepared_by", "assigned_reviewer",
        "created_at", "expires_at", *FLAGS}
REVIEW = {"schema", "plan_id", "plan_ciphertext_sha256", "plan_sha256", "snapshot_sha256", "reviewed_by", "reviewed_at",
          "decision", "reason_code", *FLAGS}
REFS = {"plan_id", "plan_ciphertext_sha256", "plan_sha256"}


def result(state="unavailable", **values):
    return {"schema": "journal-backup-readiness-v1", "state": state, "metadata_only": True, "source_read_only": True,
            "candidate_read_only": True, "atomic_snapshot": False, "current_authority_assessed": False,
            "content_authenticity": "unassessed", "fresh_independent_review_required": True,
            "observation": None, "plan": None, "review": None, **dict.fromkeys(FLAGS, False), **values}


@dataclass(frozen=True, kw_only=True)
class JournalBackupReadiness:
    """All stores/pins/principals come from trusted wiring, never request payloads.

    A candidate uses the independently pinned source-journal key for byte-exact
    copies. That equality is checked, never provisioned. The review key is separate.
    No decryption of source or candidate records, copy helper or trust import exists.
    """
    source: JournalReconciler
    candidate: receipts.ReceiptStore
    candidate_pins: Pins
    reviews: JournalReconciler

    def __post_init__(self):
        self.validate()

    def validate(self):
        if (not isinstance(self.source, JournalReconciler) or not isinstance(self.reviews, JournalReconciler)
                or not isinstance(self.candidate, receipts.ReceiptStore) or not isinstance(self.candidate_pins, Pins)):
            e.reject()
        self.source.validate()
        self.reviews.validate()
        p, r, t = self.source.planner, self.reviews.planner, self.candidate_pins
        roots = [p.source.root, p.journal.root, self.candidate.root, r.journal.root]
        if (any(a == b or a in b.parents or b in a.parents for i, a in enumerate(roots) for b in roots[i + 1:])
                or r.source is not p.journal or r.pins != self.source.binding.pins or r.authority is not p.authority
                or (r.preparer, r.reviewer) != (p.preparer, p.reviewer)
                or self.candidate.key != p.journal.key or r.journal.key in {p.source.key, p.journal.key}
                or self.candidate.context_id != t.context_id or t.context_id != r.pins.context_id
                or self.candidate.scope_sha256 != t.scope_sha256 or t.scope_sha256 != r.pins.scope_sha256
                or self.candidate.identity != t.store_identity or fingerprint(self.candidate.key) != t.key_fingerprint
                or (t.profile_id, t.profile_sha256) != (r.authority.profile_id, r.authority.marker_sha)):
            e.reject()
        receipts._root(self.candidate)
        return e.sha(e.encode({"schema": "journal-copy-readiness-binding-v1", "source": asdict(self.source.binding),
                              "candidate": asdict(t), "reviews": asdict(self.reviews.binding)}))

    async def capture(self, actor):
        bound = self.validate()
        self.source.planner.authority.recheck(actor, now=self.source.planner.clock())
        source = await self.source.capture(actor)
        if source["state"] != "observed_journal_metadata":
            if source["state"] == "budget_exhausted":
                raise TimeoutError
            if source["state"] == "denied":
                raise PermissionError
            raise FileExistsError
        reader, digest = self.source.planner.reader(actor)
        target = await physical.observe(self.candidate, reader, self.candidate_pins, actor_sha256=digest)
        if target["state"] != "observed_metadata":
            if target["state"] == "budget_exhausted":
                raise TimeoutError
            if target["state"] == "denied":
                raise PermissionError
            raise FileExistsError
        original, candidate = source["journal"], target["inventory"]
        def manifest(view):
            return sorted(({k: row[k] for k in ("record_id", "ciphertext_sha256", "bytes")} for row in view["entries"]),
                          key=lambda row: row["record_id"] or "")
        clean = all(row["state"] == "single_link_record" for view in (original, candidate) for row in view["entries"])
        a, b = manifest(original), manifest(candidate)
        comparison = ("interrupted_or_unverifiable_entries" if not clean else "empty_source" if not a else
                      "empty_destination" if not b else "exact_ciphertext_copy" if a == b else "copy_mismatch")
        value = {"binding_sha256": bound, "source_snapshot_sha256": source["source_snapshot_sha256"],
                 "journal_snapshot_sha256": source["journal_snapshot_sha256"], "candidate_snapshot_sha256": target["snapshot_sha256"],
                 "source_inventory": original, "candidate_inventory": candidate, "comparison": comparison,
                 "manifest": a, "manifest_sha256": e.sha(e.encode(a))}
        if self.validate() != bound:
            raise FileExistsError
        self.source.planner.authority.recheck(actor, now=self.source.planner.clock())
        return value

    async def unchanged(self, actor, observation):
        if await self.capture(actor) != observation:
            raise FileExistsError

    @staticmethod
    def decision_id(ident, cipher):
        return e.sha(e.encode(["journal-copy-readiness-review-v1", ident, cipher]))[:32]

    def plan(self, ident, cipher, digest):
        value = self.reviews.planner.read("journal-copy-plan-v1", ident, cipher)
        if (not isinstance(value, dict) or set(value) != PLAN or value["schema"] != "journal-copy-readiness-plan-v1"
                or value["plan_id"] != ident or e.sha(e.encode(value)) != e.token(digest)
                or value["binding_sha256"] != self.validate() or value["binding_sha256"] != value["observation"]["binding_sha256"]
                or value["snapshot_sha256"] != e.sha(e.encode(value["observation"]))
                or value["observation"]["comparison"] not in {"empty_destination", "exact_ciphertext_copy"}
                or value["prepared_by"]["user_id"] != self.source.planner.preparer
                or value["assigned_reviewer"]["user_id"] != self.source.planner.reviewer
                or e.stamp(value["expires_at"]) - e.stamp(value["created_at"]) != 300
                or any(value[k] is not False for k in FLAGS)):
            e.reject()
        return value

    def review(self, value, cipher, digest, expected):
        review = self.reviews.planner.read("journal-copy-review-v1", self.decision_id(value["plan_id"], cipher), expected)
        if (not isinstance(review, dict) or set(review) != REVIEW or review["schema"] != "journal-copy-readiness-review-v1"
                or review["plan_id"] != value["plan_id"] or review["plan_ciphertext_sha256"] != cipher
                or review["plan_sha256"] != digest or review["snapshot_sha256"] != value["snapshot_sha256"]
                or review["reviewed_by"]["user_id"] != self.source.planner.reviewer or review["decision"] not in DECISIONS
                or review["reason_code"] != DECISIONS[review["decision"]][0]
                or not value["created_at"] <= e.stamp(review["reviewed_at"]) <= value["expires_at"]
                or any(review[k] is not False for k in FLAGS)):
            e.reject()
        return review

    async def current(self, actor, plan, review=None):
        await self.unchanged(actor, plan["observation"])
        p = self.source.planner
        p.current_actors(plan)
        p.current_window(plan)
        if review:
            p.authority.recheck(review["reviewed_by"], now=p.clock())
        p.authority.recheck(actor, now=p.clock())

    async def dispatch(self, scope, operation, **request):
        try:
            async with asyncio.timeout(inventory.TOTAL_SECONDS):
                self.validate()
                p, audit = self.source.planner, self.reviews.planner
                if operation not in {"observe", "prepare", "decide", "inspect"}:
                    e.reject()
                actor = p.actor(scope, {"prepare": "preparer", "decide": "reviewer"}.get(operation))
                if operation in {"observe", "prepare"}:
                    required = set() if operation == "observe" else {"plan_id", "expected_snapshot_sha256"}
                    if set(request) != required:
                        e.reject()
                    observation = await self.capture(actor)
                    digest = e.sha(e.encode(observation))
                    await self.unchanged(actor, observation)
                    if operation == "observe":
                        return result("observed_copy_metadata", observation=observation, snapshot_sha256=digest)
                    ident = e.token(request["plan_id"], 32)
                    if e.token(request["expected_snapshot_sha256"]) != digest:
                        raise FileExistsError
                    if observation["comparison"] not in {"empty_destination", "exact_ciphertext_copy"}:
                        return result("blocked_copy_context")
                    now = e.stamp(p.clock())
                    plan = {"schema": "journal-copy-readiness-plan-v1", "plan_id": ident,
                            "binding_sha256": self.validate(), "observation": observation, "snapshot_sha256": digest,
                            "prepared_by": actor, "assigned_reviewer": p.authority.eligible(p.reviewer, "reviewer"),
                            "created_at": now, "expires_at": now + 300, **dict.fromkeys(FLAGS, False)}
                    await self.current(actor, plan)
                    cipher = audit.write("journal-copy-plan-v1", ident, plan)
                    await self.current(actor, plan)
                    return result("pending_independent_review", plan_id=ident, plan_ciphertext_sha256=cipher, plan_sha256=e.sha(e.encode(plan)))
                if set(request) != REFS | ({"decision", "reason_code"} if operation == "decide" else {"decision_ciphertext_sha256"}):
                    e.reject()
                ident = e.token(request["plan_id"], 32)
                cipher, digest = e.token(request["plan_ciphertext_sha256"]), e.token(request["plan_sha256"])
                plan = self.plan(ident, cipher, digest)
                if operation == "decide":
                    decision = request["decision"]
                    if decision not in DECISIONS or request["reason_code"] != DECISIONS[decision][0]:
                        e.reject()
                    await self.current(actor, plan)
                    review = {"schema": "journal-copy-readiness-review-v1", "plan_id": ident,
                              "plan_ciphertext_sha256": cipher, "plan_sha256": digest, "snapshot_sha256": plan["snapshot_sha256"],
                              "reviewed_by": actor, "reviewed_at": e.stamp(p.clock()), "decision": decision,
                              "reason_code": request["reason_code"], **dict.fromkeys(FLAGS, False)}
                    retained = audit.write("journal-copy-review-v1", self.decision_id(ident, cipher), review)
                    await self.current(actor, plan, review)
                    return result(DECISIONS[decision][1], decision_ciphertext_sha256=retained)
                review = self.review(plan, cipher, digest, request["decision_ciphertext_sha256"]) if request["decision_ciphertext_sha256"] is not None else None
                state = DECISIONS[review["decision"]][1] if review else "review_reference_not_supplied"
                # Only current authorized callers may inspect retained historical metadata.
                # Stale review remains exact history and never carries execution authority.
                try:
                    await self.current(actor, plan, review)
                except (FileExistsError, PermissionError, HTTPException):
                    state = "stale_readiness_review_retained"
                self.validate()
                p.authority.recheck(actor, now=p.clock())
                return result(state, plan=plan, review=review, review_reference_basis="caller_retained_exact_digest")
        except (PermissionError, HTTPException):
            return result("denied")
        except TimeoutError:
            return result("budget_exhausted")
        except receipts.RetentionUncertain:
            return result("retention_uncertain")
        except FileExistsError:
            return result("snapshot_or_publication_conflict")
        except (InvalidTag, ValueError, TypeError, KeyError, RecursionError):
            return result("unverifiable")
        except Exception:
            return result()
