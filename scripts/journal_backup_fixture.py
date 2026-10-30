"""Disposable identities and invented copy metadata, never a live account store."""

import asyncio
import os
from dataclasses import asdict
from types import SimpleNamespace

import operator_enrollment_evidence as e
import private_inventory_receipts as receipts
import receipt_recovery_inventory as physical
import receipt_recovery_planning as planning
from cryptography.fernet import Fernet
from journal_backup_readiness import JournalBackupReadiness
from operator_review_auth import PROFILE, SessionAuthority
from operator_review_fixture import credential_seed
from planning_journal_reconciliation import JournalBinding, JournalReconciler
from receipt_provisioning_readiness import Pins, fingerprint
from sqlalchemy import delete

from app.auth import check_password, create_session
from app.db import EmployeeRole, FirmRole, LoginSession, Store, User, digest
from app.firm_rbac import CATALOG, initialize_firm


class Fixture:
    def __init__(self, root):
        root.chmod(0o700)
        self.root, self.now = root, e.utc()
        self.source, self.journal, self.profile = (root / name for name in ("receipts", "plans", "accounts"))
        for path in (self.source, self.journal, self.profile):
            path.mkdir(mode=0o700)
        self.auth_key = Fernet.generate_key()
        self.store = Store(SimpleNamespace(data_dir=self.profile, encryption_key=self.auth_key.decode(), demo_mode=True,
            database_url="sqlite:///" + str(self.profile / "disposable-identities.sqlite")))
        (self.profile / "disposable-identities.sqlite").chmod(0o600)
        self.ids = {r: e.sha(r.encode())[:32] for r in ("preparer", "reviewer", "other")}
        self.cookies, self.csrf, self.sessions = {}, {}, {}
        passwords, hashes = credential_seed()
        with self.store.session() as session:
            for role, ident in self.ids.items():
                session.add(User(id=ident, username=role, name="Disposable", firm_id="invented-firm", role="admin", active=True, password_hash=hashes[role]))
            session.flush()
            initialize_firm(session, "invented-firm")
            for role, ident in self.ids.items():
                session.execute(delete(EmployeeRole).where(EmployeeRole.user_id == ident))
                rid = e.sha((role + "-role").encode())[:32]
                session.add(FirmRole(id=rid, firm_id="invented-firm", name=role, permissions=e.encode(sorted(CATALOG)).decode(), revision=1, starter=False))
                session.flush()
                session.add(EmployeeRole(user_id=ident, role_id=rid))
            session.commit()
        for role, ident in self.ids.items():
            with self.store.session() as session:
                user = session.get(User, ident)
                assert check_password(passwords[role], user.password_hash)
                self.cookies[role], self.csrf[role] = create_session(session, user, 1)
                self.sessions[role] = digest(self.cookies[role])
        e.retain(self.profile / "disposable-profile.json", e.encode({"schema": PROFILE, "profile_id": "b" * 32, "production_activation": False}))
        self.authority = SessionAuthority(self.store, self.profile, firm_id="invented-firm",
            bindings={v: "preparer" if k == "preparer" else "reviewer" for k, v in self.ids.items()}, origins=("http://operator.invalid",))
        self.source_store = receipts.ReceiptStore(root=self.source, context_id="c" * 32, scope_sha256="d" * 64, key=os.urandom(32))
        self.journal_store = receipts.ReceiptStore(root=self.journal, context_id="c" * 32, scope_sha256="d" * 64, key=os.urandom(32))
        self.pins = Pins(context_id="c" * 32, scope_sha256="d" * 64, key_fingerprint=fingerprint(self.source_store.key),
            store_identity=self.source_store.identity, profile_id=self.authority.profile_id, profile_sha256=self.authority.marker_sha)
        self.planner = planning.RecoveryPlanner(self.source_store, self.journal_store, self.pins, self.authority,
            preparer_id=self.ids["preparer"], reviewer_id=self.ids["reviewer"], clock=lambda: self.now)
        self.add("1" * 32 + ".receipt")

    def add(self, name, raw=None):
        path = self.source / name
        if raw == b"":
            path.touch(mode=0o600)
        else:
            e.retain(path, raw if raw is not None else receipts.MAGIC + os.urandom(48))

    def scope(self, role="preparer"):
        return {"type": "http", "method": "POST", "path": "/api/v1/firm-admin/operator-review/inspect", "headers": [(k.encode(), v.encode()) for k, v in
            {"cookie": "la_session=" + self.cookies[role], "x-csrf-token": self.csrf[role], "origin": "http://operator.invalid"}.items()]}

    def call(self, operation, role="preparer", **body):
        return asyncio.run(self.planner.dispatch(self.scope(role), operation, **body))

    def prepare(self, ident="2" * 32):
        observation = self.call("inventory")
        assert observation["state"] == "observed_metadata"
        return self.call("prepare", plan_id=ident, expected_snapshot_sha256=observation["snapshot_sha256"],
            selected_entry_ids=[r["entry_id"] for r in observation["inventory"]["entries"]])

    def refs(self, plan):
        return {k: plan[k] for k in ("plan_id", "plan_ciphertext_sha256", "plan_sha256")}

    def decide(self, plan, role="reviewer", decision="accept"):
        return self.call("decide", role, **self.refs(plan), decision=decision, reason_code=planning.DECISIONS[decision][0])

    def inspect(self, plan, review=None, role="preparer"):
        return self.call("inspect", role, **self.refs(plan), decision_ciphertext_sha256=review and review["decision_ciphertext_sha256"])

    def files(self, root=None):
        return {p.name: (p.read_bytes(), physical.identity(p.stat())) for p in (root or self.source).iterdir()}

    def revoke(self, role):
        with self.store.session() as session:
            session.execute(delete(LoginSession).where(LoginSession.token_hash == self.sessions[role]))
            session.commit()


def pins(f, store):
    return Pins(context_id=store.context_id, scope_sha256=store.scope_sha256, key_fingerprint=fingerprint(store.key),
        store_identity=store.identity, profile_id=f.authority.profile_id, profile_sha256=f.authority.marker_sha)


def reconciler(f, planner):
    return JournalReconciler(planner=planner, binding=JournalBinding(pins=pins(f, planner.journal),
        source_pins_sha256=e.sha(e.encode(asdict(planner.pins))), preparer_id=planner.preparer, reviewer_id=planner.reviewer))


def service(f):
    for name in ("candidate", "copy-reviews"):
        (f.root / name).mkdir(mode=0o700)
    candidate = receipts.ReceiptStore(root=f.root / "candidate", context_id=f.journal_store.context_id,
        scope_sha256=f.journal_store.scope_sha256, key=f.journal_store.key)
    reviews = receipts.ReceiptStore(root=f.root / "copy-reviews", context_id=candidate.context_id,
        scope_sha256=candidate.scope_sha256, key=os.urandom(32))
    planner = planning.RecoveryPlanner(f.journal_store, reviews, pins(f, f.journal_store), f.authority,
        preparer_id=f.ids["preparer"], reviewer_id=f.ids["reviewer"], clock=lambda: f.now)
    return JournalBackupReadiness(source=reconciler(f, f.planner), candidate=candidate,
        candidate_pins=pins(f, candidate), reviews=reconciler(f, planner))

