"""Staged, separately authorized ciphertext copies; no trust or live activation."""

import asyncio
from dataclasses import asdict, dataclass

import operator_enrollment_evidence as e
import operator_recovery_inventory as inventory
import private_inventory_receipts as receipts
import receipt_recovery_inventory as physical
from cryptography.exceptions import InvalidTag
from fastapi import HTTPException
from journal_backup_readiness import REFS, JournalBackupReadiness
from planning_journal_reconciliation import JournalReconciler

FLAGS = physical.FLAGS | {"trust_migrated", "key_custody_approved", "target_enrolled", "acknowledgement_recovered"}
PLAN_FIELDS = {"schema", "operation_id", "binding_sha256", "mode", "manifest_sha256", "observation", "readiness_refs",
               "prepared_by", "assigned_reviewer", "created_at", "expires_at", *FLAGS}
REVIEW_FIELDS = {"schema", "operation_id", "plan_ciphertext_sha256", "plan_sha256", "reviewed_by", "reviewed_at",
                 "decision", "reason_code", *FLAGS}
INTENT_FIELDS = {"schema", "operation_id", "plan_ciphertext_sha256", "plan_sha256", "decision_ciphertext_sha256",
                 "binding_sha256", "mode", "manifest_sha256", "created_at", *FLAGS}
COMPLETION_FIELDS = {"schema", "operation_id", "intent_ciphertext_sha256", "intent_sha256", "binding_sha256",
                     "manifest_sha256", "target_inventory", "target_snapshot_sha256", "completed_at", *FLAGS}
OP_REFS = {"operation_id", "plan_ciphertext_sha256", "plan_sha256"}
DECISIONS = {"authorize": "exact_disposable_copy_authorized", "changes_required": "fresh_copy_review_required",
             "reject": "copy_execution_declined"}


def result(state="unavailable", **values):
    return {"schema": "journal-materialization-v1", "state": state, "metadata_only": True, "source_read_only": True,
            "atomic_snapshot": False, "current_authority_assessed": False, "production_execution_authorized": False,
            "content_authenticity": "unassessed", "history": None, **dict.fromkeys(FLAGS, False), **values}


@dataclass(frozen=True, kw_only=True)
class CopyOrigin:
    service: object
    operation_id: str
    plan_ciphertext_sha256: str
    plan_sha256: str
    decision_ciphertext_sha256: str
    intent_ciphertext_sha256: str
    intent_sha256: str
    completion_ciphertext_sha256: str

    def refs(self):
        value = {k: getattr(self, k) for k in OP_REFS | {"decision_ciphertext_sha256", "intent_ciphertext_sha256",
                                                       "intent_sha256", "completion_ciphertext_sha256"}}
        for key, item in value.items():
            e.token(item, 32 if key == "operation_id" else 64)
        return value


@dataclass(frozen=True, kw_only=True)
class JournalMaterializer:
    readiness: JournalBackupReadiness
    controls: JournalReconciler
    mode: str
    manifest_sha256: str
    origin: CopyOrigin | None = None

    def __post_init__(self):
        self.validate()

    def validate(self):
        if not isinstance(self.readiness, JournalBackupReadiness) or not isinstance(self.controls, JournalReconciler):
            e.reject()
        if self.mode not in {"backup", "restore"}:
            e.reject()
        e.token(self.manifest_sha256)
        bound = self.readiness.validate()
        self.controls.validate()
        p, c, ready = self.readiness.source.planner, self.controls.planner, self.readiness.reviews.planner
        roots = [p.source.root, p.journal.root, self.readiness.candidate.root, ready.journal.root, c.journal.root]
        if (any(a == b or a in b.parents or b in a.parents for i, a in enumerate(roots) for b in roots[i + 1:])
                or c.source is not p.journal or c.pins != self.readiness.source.binding.pins or c.authority is not p.authority
                or (c.preparer, c.reviewer) != (p.preparer, p.reviewer)
                or c.journal.key in {p.source.key, p.journal.key, ready.journal.key}):
            e.reject()
        origin = None
        if self.mode == "backup":
            if self.origin is not None:
                e.reject()
        else:
            if (not isinstance(self.origin, CopyOrigin) or not isinstance(self.origin.service, JournalMaterializer)
                    or self.origin.service.mode != "backup" or self.origin.service.origin is not None):
                e.reject()
            old = self.origin.service
            if (old.readiness.candidate != p.journal or old.manifest_sha256 != self.manifest_sha256
                    or old.planner.authority is not p.authority or old.planner.source != p.source):
                e.reject()
            protected = [old.planner.source.root, old.planner.journal.root, old.readiness.candidate.root,
                         old.readiness.reviews.planner.journal.root, old.controls.planner.journal.root]
            if any(a == b or a in b.parents or b in a.parents for a in roots[2:] for b in protected):
                e.reject()
            origin = {"binding_sha256": old.validate(), "refs": self.origin.refs()}
        return e.sha(e.encode({"schema": "journal-materialization-binding-v1", "readiness": bound,
                              "controls": asdict(self.controls.binding), "mode": self.mode,
                              "manifest_sha256": self.manifest_sha256, "origin": origin}))

    @property
    def planner(self):
        return self.readiness.source.planner

    @staticmethod
    def ident(kind, operation, cipher):
        return e.sha(e.encode(["journal-materialization-v1", kind, operation, cipher]))[:32]

    def read(self, kind, ident, cipher, fields, schema):
        value = self.controls.planner.read("materialization-" + kind + "-v1", ident, cipher)
        if (not isinstance(value, dict) or set(value) != fields or value["schema"] != schema
                or any(value[k] is not False for k in FLAGS)):
            e.reject()
        return value

    def plan(self, request):
        ident = e.token(request["operation_id"], 32)
        cipher, digest = e.token(request["plan_ciphertext_sha256"]), e.token(request["plan_sha256"])
        plan = self.read("plan", ident, cipher, PLAN_FIELDS, "journal-materialization-plan-v1")
        if (plan["operation_id"] != ident or e.sha(e.encode(plan)) != digest or plan["binding_sha256"] != self.validate()
                or plan["mode"] != self.mode or plan["manifest_sha256"] != self.manifest_sha256
                or plan["observation"]["manifest_sha256"] != self.manifest_sha256
                or plan["observation"]["comparison"] != "empty_destination"
                or plan["prepared_by"]["user_id"] != self.planner.preparer
                or plan["assigned_reviewer"]["user_id"] != self.planner.reviewer
                or not 1 <= e.stamp(plan["expires_at"]) - e.stamp(plan["created_at"]) <= 300
                or e.sha(e.encode(plan["observation"]["manifest"])) != self.manifest_sha256
                or plan["observation"]["binding_sha256"] != self.readiness.validate()):
            e.reject()
        self.prerequisite(plan)
        return plan

    def prerequisite(self, plan):
        refs = plan["readiness_refs"]
        if not isinstance(refs, dict) or set(refs) != REFS | {"decision_ciphertext_sha256"}:
            e.reject()
        rp = self.readiness.plan(refs["plan_id"], refs["plan_ciphertext_sha256"], refs["plan_sha256"])
        rr = self.readiness.review(rp, refs["plan_ciphertext_sha256"], refs["plan_sha256"], refs["decision_ciphertext_sha256"])
        if rr["decision"] != "accept" or rp["observation"] != plan["observation"] or plan["expires_at"] > rp["expires_at"]:
            e.reject()
        return rp, rr

    def review(self, plan, request):
        cipher = e.token(request["decision_ciphertext_sha256"])
        try:
            review = self.read("review", self.ident("review", plan["operation_id"], request["plan_ciphertext_sha256"]),
                               cipher, REVIEW_FIELDS, "journal-materialization-review-v1")
        except FileNotFoundError:
            raise PermissionError from None
        if (review["operation_id"] != plan["operation_id"] or review["plan_ciphertext_sha256"] != request["plan_ciphertext_sha256"]
                or review["plan_sha256"] != request["plan_sha256"] or review["reviewed_by"]["user_id"] != self.planner.reviewer
                or review["decision"] not in DECISIONS or review["reason_code"] != DECISIONS[review["decision"]]
                or not plan["created_at"] <= e.stamp(review["reviewed_at"]) <= plan["expires_at"]):
            e.reject()
        return review

    def actors_current(self, actor, plan, review=None):
        self.validate()
        p = self.planner
        rp, rr = self.prerequisite(plan)
        for record in (rp, plan):
            p.current_actors(record)
            p.current_window(record)
        p.authority.recheck(rr["reviewed_by"], now=p.clock())
        if review is not None:
            p.authority.recheck(review["reviewed_by"], now=p.clock())
        p.authority.recheck(actor, now=p.clock())

    async def source_current(self, actor, plan, review=None):
        self.actors_current(actor, plan, review)
        if self.origin is not None:
            old, refs = self.origin.service, self.origin.refs()
            op = old.plan(refs)
            verified = await old.verify(actor, op, old.review(op, refs), refs)
            if verified["state"] not in {"retained_copy_verified", "retained_copy_verified_review_stale"}:
                raise FileExistsError
        source = await self.readiness.source.capture(actor)
        expected = plan["observation"]
        if (source["state"] != "observed_journal_metadata" or source["source_snapshot_sha256"] != expected["source_snapshot_sha256"]
                or source["journal_snapshot_sha256"] != expected["journal_snapshot_sha256"]):
            raise FileExistsError
        self.actors_current(actor, plan, review)

    async def target(self, actor):
        self.validate()
        self.planner.authority.recheck(actor, now=self.planner.clock())
        reader, digest = self.planner.reader(actor)
        value = await physical.observe(self.readiness.candidate, reader, self.readiness.candidate_pins, actor_sha256=digest)
        if value["state"] == "budget_exhausted":
            raise TimeoutError
        if value["state"] != "observed_metadata":
            raise FileExistsError
        self.validate()
        self.planner.authority.recheck(actor, now=self.planner.clock())
        return value

    @staticmethod
    def matches(observed, manifest):
        rows = observed["inventory"]["entries"]
        return (all(r["state"] == "single_link_record" for r in rows)
                and sorted(({k: r[k] for k in ("record_id", "ciphertext_sha256", "bytes")} for r in rows), key=lambda r: r["record_id"]) == manifest)

    async def prepare(self, scope, actor, request):
        if set(request) != {"operation_id", "expected_snapshot_sha256", "readiness_refs"}:
            e.reject()
        refs = request["readiness_refs"]
        if not isinstance(refs, dict) or set(refs) != REFS | {"decision_ciphertext_sha256"}:
            e.reject()
        rp = self.readiness.plan(refs["plan_id"], refs["plan_ciphertext_sha256"], refs["plan_sha256"])
        rr = self.readiness.review(rp, refs["plan_ciphertext_sha256"], refs["plan_sha256"], refs["decision_ciphertext_sha256"])
        if rr["decision"] != "accept":
            raise PermissionError
        await self.readiness.current(actor, rp, rr)
        observation = rp["observation"]
        if (e.sha(e.encode(observation)) != e.token(request["expected_snapshot_sha256"])
                or observation["manifest_sha256"] != self.manifest_sha256 or observation["comparison"] != "empty_destination"):
            raise FileExistsError
        now = e.stamp(self.planner.clock())
        plan = {"schema": "journal-materialization-plan-v1", "operation_id": e.token(request["operation_id"], 32),
                "binding_sha256": self.validate(), "mode": self.mode, "manifest_sha256": self.manifest_sha256,
                "observation": observation, "readiness_refs": refs, "prepared_by": actor,
                "assigned_reviewer": self.planner.authority.eligible(self.planner.reviewer, "reviewer"),
                "created_at": now, "expires_at": min(now + 300, rp["expires_at"]), **dict.fromkeys(FLAGS, False)}
        if plan["expires_at"] <= now:
            raise FileExistsError
        await self.source_current(actor, plan)
        cipher = self.controls.planner.write("materialization-plan-v1", plan["operation_id"], plan)
        await self.source_current(actor, plan)
        await self.readiness.unchanged(actor, observation)
        self.actors_current(actor, plan)
        return result("copy_needs_independent_authorization", operation_id=plan["operation_id"],
                      plan_ciphertext_sha256=cipher, plan_sha256=e.sha(e.encode(plan)))

    async def materialize(self, actor, plan, review, request):
        if review["decision"] != "authorize":
            raise PermissionError
        await self.source_current(actor, plan, review)
        await self.readiness.unchanged(actor, plan["observation"])
        audit = self.controls.planner
        intent = {"schema": "journal-materialization-intent-v1", **{k: request[k] for k in OP_REFS | {"decision_ciphertext_sha256"}},
                  "binding_sha256": self.validate(), "mode": self.mode, "manifest_sha256": self.manifest_sha256,
                  "created_at": e.stamp(self.planner.clock()), **dict.fromkeys(FLAGS, False)}
        iid = self.ident("intent", plan["operation_id"], request["plan_ciphertext_sha256"])
        ic = audit.write("materialization-intent-v1", iid, intent)  # Consume once before touching the destination.
        await self.source_current(actor, plan, review)
        await self.readiness.unchanged(actor, plan["observation"])
        manifest, completed = plan["observation"]["manifest"], []
        for row in manifest:
            await self.source_current(actor, plan, review)
            if not self.matches(await self.target(actor), completed):
                raise FileExistsError
            raw = receipts._read(self.planner.journal, row["record_id"], row["ciphertext_sha256"])
            if len(raw) != row["bytes"]:
                e.reject()
            await self.source_current(actor, plan, review)
            receipts._publish(self.readiness.candidate, row["record_id"], raw)
            completed.append(row)
            await self.source_current(actor, plan, review)
            if not self.matches(await self.target(actor), completed):
                raise FileExistsError
        target = await self.target(actor)
        if not self.matches(target, manifest):
            raise FileExistsError
        receipt = {"schema": "journal-materialization-completion-v1", "operation_id": plan["operation_id"],
                   "intent_ciphertext_sha256": ic, "intent_sha256": e.sha(e.encode(intent)), "binding_sha256": self.validate(),
                   "manifest_sha256": self.manifest_sha256, "target_inventory": target["inventory"],
                   "target_snapshot_sha256": target["snapshot_sha256"], "completed_at": e.stamp(self.planner.clock()),
                   **dict.fromkeys(FLAGS, False)}
        await self.source_current(actor, plan, review)
        rc = audit.write("materialization-completion-v1", self.ident("completion", plan["operation_id"], ic), receipt)
        await self.source_current(actor, plan, review)
        if await self.target(actor) != target:
            raise FileExistsError
        self.actors_current(actor, plan, review)
        return result("ciphertext_" + self.mode + "_materialized", mode=self.mode, manifest_sha256=self.manifest_sha256,
                      intent_ciphertext_sha256=ic, intent_sha256=receipt["intent_sha256"], completion_ciphertext_sha256=rc)

    async def verify(self, actor, plan, review, request):
        ic, digest, rc = (request[k] for k in ("intent_ciphertext_sha256", "intent_sha256", "completion_ciphertext_sha256"))
        if ic is None or digest is None or rc is None:
            return result("completion_reference_not_supplied")
        intent = self.read("intent", self.ident("intent", plan["operation_id"], request["plan_ciphertext_sha256"]),
                           e.token(ic), INTENT_FIELDS, "journal-materialization-intent-v1")
        if (e.sha(e.encode(intent)) != e.token(digest) or any(intent[k] != request[k] for k in OP_REFS | {"decision_ciphertext_sha256"})
                or intent["binding_sha256"] != self.validate() or intent["mode"] != self.mode
                or intent["manifest_sha256"] != self.manifest_sha256 or review["decision"] != "authorize"
                or not plan["created_at"] <= e.stamp(intent["created_at"]) <= plan["expires_at"]):
            e.reject()
        receipt = self.read("completion", self.ident("completion", plan["operation_id"], ic), e.token(rc),
                            COMPLETION_FIELDS, "journal-materialization-completion-v1")
        if (receipt["operation_id"] != plan["operation_id"] or receipt["intent_ciphertext_sha256"] != ic
                or receipt["intent_sha256"] != digest or receipt["manifest_sha256"] != self.manifest_sha256
                or receipt["binding_sha256"] != self.validate()
                or receipt["target_snapshot_sha256"] != e.sha(e.encode(receipt["target_inventory"]))
                or not intent["created_at"] <= e.stamp(receipt["completed_at"]) <= plan["expires_at"]):
            e.reject()
        target = await self.target(actor)
        if target["snapshot_sha256"] != receipt["target_snapshot_sha256"] or not self.matches(target, plan["observation"]["manifest"]):
            raise FileExistsError
        current = True
        try:
            await self.source_current(actor, plan, review)
        except (FileExistsError, PermissionError, HTTPException):
            current = False
        if await self.target(actor) != target:
            raise FileExistsError
        try:
            self.actors_current(actor, plan, review)
        except (FileExistsError, PermissionError, HTTPException):
            current = False
        self.planner.authority.recheck(actor, now=self.planner.clock())
        return result("retained_copy_verified" if current else "retained_copy_verified_review_stale", mode=self.mode,
                      manifest_sha256=self.manifest_sha256, target_snapshot_sha256=target["snapshot_sha256"],
                      execution_review_current=current, history={"plan": plan, "review": review, "intent": intent, "completion": receipt})

    async def dispatch(self, scope, operation, **request):
        try:
            async with asyncio.timeout(inventory.TOTAL_SECONDS):
                self.validate()
                if operation not in {"prepare", "decide", "materialize", "verify"}:
                    e.reject()
                actor = self.planner.actor(scope, "preparer" if operation in {"prepare", "materialize"} else "reviewer" if operation == "decide" else None)
                if operation == "prepare":
                    return await self.prepare(scope, actor, request)
                fields = OP_REFS | ({"decision", "reason_code"} if operation == "decide" else {"decision_ciphertext_sha256"})
                if operation == "verify":
                    fields |= {"intent_ciphertext_sha256", "intent_sha256", "completion_ciphertext_sha256"}
                if set(request) != fields:
                    e.reject()
                plan = self.plan(request)
                if operation == "decide":
                    decision = request["decision"]
                    if decision not in DECISIONS or request["reason_code"] != DECISIONS[decision]:
                        e.reject()
                    await self.source_current(actor, plan)
                    await self.readiness.unchanged(actor, plan["observation"])
                    review = {"schema": "journal-materialization-review-v1", **{k: request[k] for k in OP_REFS | {"decision", "reason_code"}},
                              "reviewed_by": actor, "reviewed_at": e.stamp(self.planner.clock()), **dict.fromkeys(FLAGS, False)}
                    cipher = self.controls.planner.write("materialization-review-v1",
                        self.ident("review", plan["operation_id"], request["plan_ciphertext_sha256"]), review)
                    await self.source_current(actor, plan, review)
                    await self.readiness.unchanged(actor, plan["observation"])
                    self.actors_current(actor, plan, review)
                    return result("disposable_copy_authorized" if decision == "authorize" else decision, decision_ciphertext_sha256=cipher)
                review = self.review(plan, request)
                if operation == "materialize":
                    return await self.materialize(actor, plan, review, request)
                return await self.verify(actor, plan, review, request)
        except (PermissionError, HTTPException):
            return result("denied")
        except TimeoutError:
            return result("budget_exhausted")
        except receipts.RetentionUncertain:
            return result("retention_uncertain")
        except FileExistsError:
            return result("copy_context_or_publication_conflict")
        except (InvalidTag, ValueError, TypeError, KeyError, RecursionError):
            return result("unverifiable")
        except Exception:
            return result()  # Never emit paths, credentials, exception text or partial decrypted history.
