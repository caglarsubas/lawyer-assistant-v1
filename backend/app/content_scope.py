"""Explicit scope origins; no hierarchy, ownership, role or tag-only case grants."""
from fastapi import HTTPException
from sqlalchemy import delete, exists, or_, select
from sqlalchemy.orm import aliased

from .db import (
    AccessConfiguration,
    Audit,
    CaseResponsibility,
    CustomerAssignment,
    LoginSession,
    Membership,
    Record,
    ScopeMigration,
    User,
    WorkspaceCustomerLink,
    now,
)


def case_scope(matter_id, user_id, firm_id):
    """Correlated predicate for both record lists and case-authorized user lists."""
    customer = aliased(Record)
    direct = exists(select(1).select_from(Membership).where(
        Membership.matter_id == matter_id, Membership.user_id == user_id))
    client = exists(select(1).select_from(WorkspaceCustomerLink)
                    .join(CustomerAssignment, CustomerAssignment.customer_id == WorkspaceCustomerLink.customer_id)
                    .join(customer, customer.id == WorkspaceCustomerLink.customer_id).where(
                        WorkspaceCustomerLink.matter_id == matter_id, WorkspaceCustomerLink.firm_id == firm_id,
                        CustomerAssignment.user_id == user_id, CustomerAssignment.firm_id == firm_id,
                        CustomerAssignment.scope == "all_cases", customer.kind == "customer", customer.firm_id == firm_id))
    return or_(direct, client)


def has_case_scope(session, matter_id, user):
    # Existing direct grants remain independently revocable and cheap to verify.
    if session.get(Membership, (matter_id, user.id), populate_existing=True):
        return True
    return bool(session.scalar(select(case_scope(matter_id, user.id, user.firm_id))))


def scoped_records(user, kinds=("matter",)):
    return select(Record).where(Record.kind.in_(kinds), Record.firm_id == user.firm_id,
                                case_scope(Record.id, user.id, user.firm_id))


def scoped_users(session, matter_id, firm_id):
    return session.scalars(select(User).where(User.firm_id == firm_id, User.active.is_(True),
                                             case_scope(matter_id, User.id, firm_id)).order_by(User.name, User.id)).all()


def initialize_scope(store, session, firm_id):
    """One-time additive conversion of existing detail visibility; never infer case grants."""
    marker = session.get(ScopeMigration, firm_id)
    if marker:
        if marker.version != 1:
            raise RuntimeError("Unsupported content scope migration version")
        return
    customers = {row.id: row for row in session.scalars(select(Record).where(
        Record.kind == "customer", Record.firm_id == firm_id))}
    for row in customers.values():
        owner = session.get(User, row.owner_id)
        if owner and owner.firm_id == firm_id and not session.get(CustomerAssignment, (row.id, owner.id)):
            session.add(CustomerAssignment(customer_id=row.id, user_id=owner.id, firm_id=firm_id,
                                           scope="details", assigned_by=owner.id))
    for row in session.scalars(select(Record).where(Record.kind.in_(["matter", "archived_matter"]),
                                                   Record.firm_id == firm_id)):
        for ident in set(store.decode(row).get("customer_ids", [])) & customers.keys():
            if not session.get(WorkspaceCustomerLink, (row.id, ident)):
                session.add(WorkspaceCustomerLink(matter_id=row.id, customer_id=ident, firm_id=firm_id))
    session.add(ScopeMigration(firm_id=firm_id))


def configuration(session, record):
    row = session.get(AccessConfiguration, record.id)
    if not row:
        row = AccessConfiguration(target_id=record.id, firm_id=record.firm_id, kind=record.kind, revision=1)
        session.add(row)
        session.flush()
    if row.firm_id != record.firm_id:
        raise HTTPException(409, "Atama yapılandırması doğrulanamadı")
    return row


def record_change(store, session, actor, target_id, action, before, after):
    row = store.add(session, "access_change", actor, {
        "target_id": target_id, "action": action, "before": before, "after": after, "recorded_at": now(),
    })
    session.add(Audit(actor_id=actor.id, action=action, object_id=row.id))


def invalidate_scope(store, session, firm_id, user_ids):
    """Within the exclusive firm guard: invalidate sessions and persist stop intent atomically."""
    from .firm_rbac import permissions_for

    ids = set(user_ids)
    session.execute(delete(LoginSession).where(LoginSession.user_id.in_(ids)))
    stopped = []
    for row in session.scalars(select(Record).where(Record.kind == "research", Record.firm_id == firm_id,
                                                   Record.owner_id.in_(ids)).with_for_update()):
        state = store.decode(row)
        if state.get("status") not in {"queued", "running"}:
            continue
        owner = session.get(User, row.owner_id, populate_existing=True)
        if owner and owner.active and "matter.write" in permissions_for(session, owner) and has_case_scope(session, row.matter_id, owner):
            continue
        state.update(status="cancelling", stop_reason="access_revoked", cancel_requested_at=now())
        store.update(row, state)
        stopped.append(row.id)
    return stopped


def remove_queued(app, ids):
    for ident in ids:
        app.state.research_jobs.cancel(ident)


def sync_links(store, session, actor, matter, customer_ids):
    old = set(session.scalars(select(WorkspaceCustomerLink.customer_id).where(
        WorkspaceCustomerLink.matter_id == matter.id, WorkspaceCustomerLink.firm_id == actor.firm_id)))
    new = set(customer_ids)
    if old == new:
        return []
    affected = list(session.scalars(select(CustomerAssignment.user_id).where(
        CustomerAssignment.customer_id.in_(old ^ new), CustomerAssignment.firm_id == actor.firm_id,
        CustomerAssignment.scope == "all_cases")))
    session.execute(delete(WorkspaceCustomerLink).where(WorkspaceCustomerLink.matter_id == matter.id))
    session.add_all([WorkspaceCustomerLink(matter_id=matter.id, customer_id=ident, firm_id=actor.firm_id) for ident in customer_ids])
    session.flush()
    if not scoped_users(session, matter.id, actor.firm_id):
        raise HTTPException(409, "En az bir aktif dosya erişimi korunmalı")
    record_change(store, session, actor, matter.id, "case_client_links_changed", sorted(old), sorted(new))
    return invalidate_scope(store, session, actor.firm_id, affected)


def access_explanation(session, matter, user):
    from .firm_rbac import permissions_for

    clients = list(session.scalars(select(CustomerAssignment.customer_id).join(
        WorkspaceCustomerLink, WorkspaceCustomerLink.customer_id == CustomerAssignment.customer_id).where(
            WorkspaceCustomerLink.matter_id == matter.id, WorkspaceCustomerLink.firm_id == user.firm_id,
            CustomerAssignment.user_id == user.id, CustomerAssignment.firm_id == user.firm_id,
            CustomerAssignment.scope == "all_cases")))
    role = session.get(CaseResponsibility, (matter.id, user.id))
    direct = bool(session.get(Membership, (matter.id, user.id)))
    return {"matter_id": matter.id, "permissions": sorted(permissions_for(session, user)),
            "direct_case_grant": direct, "client_all_cases_origins": clients,
            "supervisor": bool(direct and role and role.firm_id == user.firm_id and role.supervisor),
            "responsible": bool(direct and role and role.firm_id == user.firm_id and role.responsible),
            "hierarchy_grants_access": False}
