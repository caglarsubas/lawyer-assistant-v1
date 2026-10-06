"""Matter-scoped, reversible lifecycle controls and dependency invalidation.

No operation in this module deletes bytes or certifies a retention rule as lawful.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from .auth import authenticate
from .db import Audit, Membership, Record, User, digest, now


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Reason(Input):
    reason: str = Field(min_length=3, max_length=2000)


class HoldInput(Reason):
    authority_reference: str = Field(min_length=1, max_length=1000)


class RetentionInput(Reason):
    policy_reference: str = Field(min_length=1, max_length=1000)
    retention_days: int | None = Field(default=None, ge=1, le=36500)
    trigger: Literal["manual_review", "matter_closed", "last_activity"] = "manual_review"
    review_due_at: str | None = Field(default=None, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$")
    qualification_reference: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def valid_date(self):
        if self.review_due_at:
            from datetime import date

            date.fromisoformat(self.review_due_at)
        return self


class ArchiveInput(Reason):
    expected_revision: int = Field(ge=1)


class Change(Input):
    kind: Literal["source", "assertion", "release"]
    old_id: str = Field(min_length=1, max_length=512)
    new_id: str | None = Field(default=None, min_length=1, max_length=512)

    @model_validator(mode="after")
    def distinct_versions(self):
        if self.new_id == self.old_id:
            raise ValueError("Old and new identifiers must differ")
        return self


class DependencyInput(Reason):
    changes: list[Change] = Field(min_length=1, max_length=100)


class ReleaseInput(Reason):
    old_release_id: str = Field(min_length=1, max_length=512)
    new_release_id: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def distinct_releases(self):
        if self.old_release_id == self.new_release_id:
            raise ValueError("Old and new release identifiers must differ")
        return self


SOURCE_KEYS = {
    "document_id",
    "document_sha256",
    "source_id",
    "source_sha256",
    "source_document_id",
    "artifact_id",
    "artifact_sha256",
    "passage_id",
    "evidence_id",
    "text_representation_id",
}
RELEASE_KEYS = {
    "release_id",
    "corpus_release_id",
    "graph_release_id",
    "bundle_sha256",
    "release_sha256",
}
EXTERNAL_GATES = [
    "Retention rules and authority references require qualified legal review.",
    "Physical erasure is not implemented; original files and derived records remain recoverable.",
    "Backup copies, exported documents, replicas and third-party copies require separate operator evidence.",
    "Database audit events are not an externally anchored, tamper-proof audit archive.",
]


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _audit(session, user, action, object_id, matter_id):
    session.add(Audit(actor_id=user.id, action=action, object_id=object_id, matter_id=matter_id))


def _current_user(session, user, admin=False):
    current = session.get(User, user.id, populate_existing=True)
    if not current or not current.active or current.firm_id != user.firm_id:
        raise HTTPException(401, "Oturum geçersiz")
    if admin and current.role != "admin":
        raise HTTPException(403, "Bu işlem yönetici yetkisi gerektirir")
    return current


def _matter(session, matter_id, user, *, admin=False, lock=False):
    current = _current_user(session, user)
    query = select(Record).where(Record.id == matter_id).execution_options(populate_existing=True)
    matter = session.scalar(query.with_for_update() if lock else query)
    membership = session.get(Membership, (matter_id, current.id), populate_existing=True)
    if (
        not matter
        or matter.kind not in {"matter", "archived_matter"}
        or matter.firm_id != current.firm_id
        or not membership
    ):
        raise HTTPException(404, "Dosya bulunamadı")
    if (admin or matter.kind == "archived_matter") and current.role != "admin":
        raise HTTPException(403, "Bu işlem yönetici yetkisi gerektirir")
    return matter


def _children(session, matter, kind=None, *, lock=False):
    query = select(Record).where(Record.matter_id == matter.id, Record.firm_id == matter.firm_id)
    if kind:
        query = query.where(Record.kind == kind)
    query = query.order_by(Record.created_at, Record.id)
    return list(session.scalars(query.with_for_update() if lock else query))


def _touch(store, matter):
    # A shared revision also invalidates research that started before a lifecycle change.
    store.update(matter, store.decode(matter))


def _commit(session):
    try:
        session.commit()
    except StaleDataError as exc:
        session.rollback()
        raise HTTPException(409, "Dosya değişti; güncel durumu kontrol ederek yeniden deneyin") from exc


def _event(store, session, matter, user, action, details):
    previous = session.scalar(
        select(Record)
        .where(
            Record.kind == "governance_event",
            Record.matter_id == matter.id,
            Record.firm_id == matter.firm_id,
        )
        .order_by(Record.created_at.desc(), Record.id.desc())
        .limit(1)
    )
    prior = store.decode(previous) if previous else {}
    payload = {
        "action": action,
        "actor_id": user.id,
        "matter_id": matter.id,
        "at": now(),
        "details": details,
        "previous_event_id": previous.id if previous else None,
        "previous_event_digest": prior.get("event_digest"),
        "sequence": prior.get("sequence", 0) + 1,
    }
    payload["event_digest"] = digest(_canonical(payload))
    event = store.add(session, "governance_event", user, payload, matter.id)
    _audit(session, user, action, event.id, matter.id)
    return event


def _holds(store, session, matter):
    released = {store.decode(record)["hold_id"] for record in _children(session, matter, "hold_release")}
    return [
        {**store.view(record), "status": "released" if record.id in released else "active"}
        for record in _children(session, matter, "legal_hold")
    ]


def _policy(store, session, matter):
    policies = _children(session, matter, "retention_policy")
    if policies:
        return store.view(policies[-1])
    return {
        "id": None,
        "retention_days": None,
        "trigger": "manual_review",
        "review_due_at": None,
        "automatic_expiry": False,
        "automatic_erasure": False,
        "qualification_status": "not_configured",
        "policy_reference": None,
    }


def dependency_ids(product):
    """Extract exact identifiers from declared provenance, never arbitrary prose."""
    found = {"source": set(), "assertion": set(), "release": set()}

    def add(kind, value):
        if isinstance(value, str) and value:
            found[kind].add(value)
        elif isinstance(value, list):
            for item in value:
                add(kind, item)

    def walk(value, context=""):
        if isinstance(value, list):
            for item in value:
                walk(item, context)
        elif isinstance(value, dict):
            for key, child in value.items():
                if key in SOURCE_KEYS:
                    add("source", child)
                elif key in RELEASE_KEYS:
                    add("release", child)
                elif key in {"assertion_id", "assertion_ids"}:
                    add("assertion", child)
                elif key == "id" and context in {"edges", "assertions"}:
                    add("assertion", child)
                elif key == "sources" and isinstance(child, dict):
                    found["source"].update(child)
                elif key == "practice_versions" and isinstance(child, dict):
                    found["source"].update(child)
                    for version in child.values():
                        if isinstance(version, dict):
                            add("source", version.get("version_id"))
                elif key == "assertions" and isinstance(child, dict):
                    found["assertion"].update(child)
                elif key in {"ontology", "model", "policy"} and context == "snapshots":
                    add("release", child)
                elif key == "ontology_sha256" and context in {"snapshots", "snapshot", "graphs"}:
                    add("release", child)
                walk(child, key)

    for field in ("snapshots", "evidence", "graph_paths", "authority_candidates", "dependencies"):
        walk(product.get(field), field)
    return found


def _impact(store, session, matter, changes, *, lock=False):
    impacts = []
    for record in _children(session, matter, "product", lock=lock):
        body = store.decode(record)
        ids = dependency_ids(body)
        matches = [change.model_dump() for change in changes if change.old_id in ids[change.kind]]
        if matches:
            impacts.append(
                {
                    "product_id": record.id,
                    "revision": record.revision,
                    "title": body.get("title", ""),
                    "status": body.get("status"),
                    "matches": matches,
                }
            )
    return impacts


def _invalidate(store, session, matter, user, changes, reason):
    impacts = _impact(store, session, matter, changes, lock=True)
    if not impacts:
        return {"matter_id": matter.id, "products": [], "event_id": None}
    _touch(store, matter)
    event = _event(
        store,
        session,
        matter,
        user,
        "dependencies_invalidated",
        {
            "reason": reason,
            "changes": [change.model_dump() for change in changes],
            "products": impacts,
            "reviewed_content_preserved": True,
        },
    )
    for impact in impacts:
        record = session.get(Record, impact["product_id"])
        body = store.decode(record)
        # Summary, claims, citations, original snapshots and review decisions are unchanged.
        body.update(status="stale", stale_reason=reason, stale_event_id=event.id)
        store.update(record, body)
    return {"matter_id": matter.id, "products": impacts, "event_id": event.id}


def _inventory(store, session, matter, data_dir):
    children = _children(session, matter)
    originals = []
    products = []
    vault = Path(data_dir) / "documents"
    for record in children:
        body = store.decode(record)
        if record.kind == "document":
            name = body.get("original_path")
            state = "not_recorded"
            if name:
                if not isinstance(name, str) or Path(name).name != name or name in {".", ".."}:
                    state = "unsafe_reference"
                else:
                    target = vault / name
                    state = "present" if target.is_file() and not target.is_symlink() else "unavailable"
            originals.append({"document_id": record.id, "sha256": body.get("sha256"), "state": state})
        elif record.kind == "product":
            products.append(
                {
                    "product_id": record.id,
                    "status": body.get("status"),
                    "dependencies": {key: sorted(ids) for key, ids in dependency_ids(body).items()},
                }
            )
    holds = [hold for hold in _holds(store, session, matter) if hold["status"] == "active"]
    inventory = {
        "matter_id": matter.id,
        "matter_revision": matter.revision,
        "matter_kind": matter.kind,
        "dry_run": True,
        "records": [{"id": matter.id, "kind": matter.kind}]
        + [{"id": record.id, "kind": record.kind} for record in children],
        "record_counts": dict(Counter([matter.kind] + [record.kind for record in children])),
        "originals": originals,
        "products": products,
        "active_hold_ids": [hold["id"] for hold in holds],
        "retention_policy": _policy(store, session, matter),
        "archive_allowed": not holds,
        "purge_allowed": False,
        "physical_erasure_available": False,
        "external_gates": EXTERNAL_GATES,
        "external_stores": {
            "backups": "not_inventoried",
            "exports": "not_recallable",
            "search_replicas": "not_verified",
        },
    }
    inventory["inventory_sha256"] = digest(_canonical(inventory))
    return inventory


def governance_router():
    router = APIRouter(prefix="/api/v1", tags=["governance"])

    @router.get("/matters/{matter_id}/governance")
    def governance(matter_id: str, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            matter = _matter(session, matter_id, user)
            return {
                "matter_id": matter.id,
                "matter_revision": matter.revision,
                "matter_kind": matter.kind,
                "holds": _holds(store, session, matter),
                "hold_releases": [store.view(row) for row in _children(session, matter, "hold_release")],
                "retention_policy": _policy(store, session, matter),
                "retention_policy_history": [
                    store.view(row) for row in _children(session, matter, "retention_policy")
                ],
                "archive_history": [
                    store.view(row) for row in _children(session, matter, "matter_tombstone")
                ],
                "restore_history": [store.view(row) for row in _children(session, matter, "matter_restore")],
                "ledger": [store.view(event) for event in _children(session, matter, "governance_event")],
                "external_gates": EXTERNAL_GATES,
            }

    @router.post("/matters/{matter_id}/legal-holds", status_code=201)
    def hold(matter_id: str, body: HoldInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            matter = _matter(session, matter_id, user, admin=True, lock=True)
            record = store.add(
                session,
                "legal_hold",
                user,
                {
                    **body.model_dump(),
                    "imposed_at": now(),
                    "imposed_by": user.id,
                },
                matter.id,
            )
            _touch(store, matter)
            _event(store, session, matter, user, "legal_hold_created", {"hold_id": record.id})
            _commit(session)
            return {**store.view(record), "status": "active"}

    @router.post("/matters/{matter_id}/legal-holds/{hold_id}/release")
    def release_hold(
        matter_id: str,
        hold_id: str,
        body: HoldInput,
        request: Request,
        user=Depends(authenticate),
    ):
        store = request.app.state.store
        with store.session() as session:
            matter = _matter(session, matter_id, user, admin=True, lock=True)
            holds = {item["id"]: item for item in _holds(store, session, matter)}
            if hold_id not in holds:
                raise HTTPException(404, "Koruma kaydı bulunamadı")
            if holds[hold_id]["status"] != "active":
                raise HTTPException(409, "Koruma kaydı zaten kaldırıldı")
            record = store.add(
                session,
                "hold_release",
                user,
                {
                    **body.model_dump(),
                    "hold_id": hold_id,
                    "released_at": now(),
                    "released_by": user.id,
                },
                matter.id,
            )
            _touch(store, matter)
            _event(
                store,
                session,
                matter,
                user,
                "legal_hold_released",
                {
                    "hold_id": hold_id,
                    "release_record_id": record.id,
                },
            )
            _commit(session)
            return {**store.view(record), "status": "released"}

    @router.put("/matters/{matter_id}/retention-policy", status_code=201)
    def retention(matter_id: str, body: RetentionInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            matter = _matter(session, matter_id, user, admin=True, lock=True)
            previous = _policy(store, session, matter)
            record = store.add(
                session,
                "retention_policy",
                user,
                {
                    **body.model_dump(),
                    "supersedes_policy_id": previous["id"],
                    "recorded_by": user.id,
                    "automatic_expiry": False,
                    "automatic_erasure": False,
                    "qualification_status": "operator_recorded_unqualified",
                },
                matter.id,
            )
            _touch(store, matter)
            _event(store, session, matter, user, "retention_policy_recorded", {"policy_id": record.id})
            _commit(session)
            return store.view(record)

    @router.post("/matters/{matter_id}/erasure-plan")
    def erasure_plan(matter_id: str, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            matter = _matter(session, matter_id, user, admin=True, lock=True)
            plan = _inventory(store, session, matter, request.app.state.settings.data_dir)
            _audit(session, user, "erasure_planned", plan["inventory_sha256"], matter.id)
            _commit(session)
            return plan

    @router.post("/matters/{matter_id}/archive")
    def archive(matter_id: str, body: ArchiveInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            matter = _matter(session, matter_id, user, admin=True, lock=True)
            if matter.kind != "matter" or matter.revision != body.expected_revision:
                raise HTTPException(409, "Dosya durumu veya sürümü değişti")
            if any(item["status"] == "active" for item in _holds(store, session, matter)):
                raise HTTPException(409, "Etkin hukuki koruma nedeniyle dosya arşivlenemez")
            inventory = _inventory(store, session, matter, request.app.state.settings.data_dir)
            tombstone = store.add(
                session,
                "matter_tombstone",
                user,
                {
                    "reason": body.reason,
                    "archived_by": user.id,
                    "archived_at": now(),
                    "previous_revision": matter.revision,
                    "inventory_sha256": inventory["inventory_sha256"],
                    "original_kind": "matter",
                    "physical_erasure": False,
                },
                matter.id,
            )
            cancelled = []
            for record in _children(session, matter, "research", lock=True):
                run = store.decode(record)
                if run.get("status") in {"queued", "running", "cancelling"}:
                    store.update(record, {**run, "status": "cancelling", "stop_reason": "matter_archived",
                                          "cancel_requested_at": run.get("cancel_requested_at") or now()})
                    cancelled.append(record.id)
            matter.kind = "archived_matter"
            _touch(store, matter)
            _event(
                store,
                session,
                matter,
                user,
                "matter_archived",
                {
                    "tombstone_id": tombstone.id,
                    "stop_requested_research_ids": cancelled,
                    "reason": body.reason,
                    "physical_erasure": False,
                },
            )
            _commit(session)
            for ident in cancelled:
                request.app.state.research_jobs.cancel(ident)
            return {
                "matter_id": matter.id,
                "revision": matter.revision,
                "status": "archived",
                "tombstone_id": tombstone.id,
                "physical_erasure": False,
                "restorable": True,
            }

    @router.get("/governance/archived-matters")
    def archived_matters(request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            current = _current_user(session, user)
            records = session.scalars(
                select(Record)
                .join(
                    Membership,
                    Membership.matter_id == Record.id,
                )
                .where(
                    Record.kind == "archived_matter",
                    Record.firm_id == current.firm_id,
                    Membership.user_id == current.id,
                )
                .order_by(Record.created_at, Record.id)
            )
            return [
                {
                    "id": record.id,
                    "title": store.decode(record).get("title", ""),
                    "revision": record.revision,
                    "status": "archived",
                    "can_restore": current.role == "admin",
                }
                for record in records
            ]

    @router.post("/governance/archived-matters/{matter_id}/restore")
    def restore(matter_id: str, body: ArchiveInput, request: Request, user=Depends(authenticate)):
        store = request.app.state.store
        with store.session() as session:
            matter = _matter(session, matter_id, user, admin=True, lock=True)
            if matter.kind != "archived_matter" or matter.revision != body.expected_revision:
                raise HTTPException(409, "Dosya durumu veya sürümü değişti")
            tombstones = _children(session, matter, "matter_tombstone")
            if not tombstones:
                raise HTTPException(409, "Doğrulanabilir arşiv kaydı bulunamadı")
            restored = store.add(
                session,
                "matter_restore",
                user,
                {
                    "reason": body.reason,
                    "restored_by": user.id,
                    "restored_at": now(),
                    "tombstone_id": tombstones[-1].id,
                    "previous_revision": matter.revision,
                    "research_restarted": False,
                },
                matter.id,
            )
            matter.kind = "matter"
            _touch(store, matter)
            _event(
                store,
                session,
                matter,
                user,
                "matter_restored",
                {
                    "restore_record_id": restored.id,
                    "tombstone_id": tombstones[-1].id,
                    "reason": body.reason,
                },
            )
            _commit(session)
            return {"matter_id": matter.id, "revision": matter.revision, "status": "active"}

    @router.post("/matters/{matter_id}/dependencies/impact")
    def dependency_impact(
        matter_id: str,
        body: DependencyInput,
        request: Request,
        user=Depends(authenticate),
    ):
        store = request.app.state.store
        with store.session() as session:
            matter = _matter(session, matter_id, user)
            products = _impact(store, session, matter, body.changes)
            _audit(session, user, "dependency_impact_planned", matter.id, matter.id)
            _commit(session)
            return {"matter_id": matter.id, "products": products, "dry_run": True}

    @router.post("/matters/{matter_id}/dependencies/invalidate")
    def dependency_invalidate(
        matter_id: str,
        body: DependencyInput,
        request: Request,
        user=Depends(authenticate),
    ):
        store = request.app.state.store
        with store.session() as session:
            matter = _matter(session, matter_id, user, admin=True, lock=True)
            result = _invalidate(store, session, matter, user, body.changes, body.reason)
            if not result["products"]:
                _audit(session, user, "dependency_invalidation_no_match", matter.id, matter.id)
            _commit(session)
            return {**result, "status": "completed", "reviewed_content_preserved": True}

    def release_operation(body, request, user, apply):
        store = request.app.state.store
        change = Change(kind="release", old_id=body.old_release_id, new_id=body.new_release_id)
        with store.session() as session:
            current = _current_user(session, user, admin=True)
            ids = list(
                session.scalars(
                    select(Record.id)
                    .join(
                        Membership,
                        Membership.matter_id == Record.id,
                    )
                    .where(
                        Record.kind.in_(["matter", "archived_matter"]),
                        Record.firm_id == current.firm_id,
                        Membership.user_id == current.id,
                    )
                    .order_by(Record.id)
                )
            )
            results = []
            for matter_id in ids:
                matter = _matter(session, matter_id, current, admin=True, lock=apply)
                if apply:
                    result = _invalidate(store, session, matter, current, [change], body.reason)
                else:
                    result = {"matter_id": matter.id, "products": _impact(store, session, matter, [change])}
                if result["products"]:
                    results.append(result)
                _audit(
                    session,
                    current,
                    "release_invalidation_checked" if apply else "release_impact_planned",
                    digest(_canonical(body.model_dump())),
                    matter.id,
                )
            _commit(session)
            return {
                "old_release_id": body.old_release_id,
                "new_release_id": body.new_release_id,
                "dry_run": not apply,
                "matters": results,
                "scope": "caller_memberships_only",
                "release_installed": False,
                "reviewed_content_preserved": True,
            }

    @router.post("/governance/releases/impact")
    def release_impact(body: ReleaseInput, request: Request, user=Depends(authenticate)):
        return release_operation(body, request, user, False)

    @router.post("/governance/releases/invalidate")
    def release_invalidate(body: ReleaseInput, request: Request, user=Depends(authenticate)):
        return release_operation(body, request, user, True)

    return router
