"""External exclusive metadata publication with invented local identities only."""

import os
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import operator_enrollment_evidence as e
import private_inventory_receipts as receipts
from cryptography.fernet import Fernet
from journal_backup_fixture import Fixture as BaseAccount
from metadata_handoff_readiness import MetadataHandoff, Specification, TransportPins, recipient_context
from operator_review_auth import PROFILE, SessionAuthority
from operator_review_fixture import credential_seed
from receipt_provisioning_readiness import Pins, fingerprint
from receipt_recovery_planning import RecoveryPlanner
from recovery_input_fixture import SELECTION
from recovery_input_fixture import make as make_target
from retention_authorization_fixture import ENTRY as PROOF_ENTRY
from retention_authorization_fixture import make as make_source
from sqlalchemy import delete

from app.auth import check_password, create_session
from app.db import EmployeeRole, FirmRole, Store, User, digest
from app.firm_rbac import CATALOG, initialize_firm

DESTINATION = "d" * 32


class RecipientAccount(BaseAccount):
    """Fresh recipient namespace; no identity/profile aliases with the sender."""

    def __init__(self, root, *, age_seconds=0):
        if type(age_seconds) is not int or not 0 <= age_seconds <= 120:
            e.reject()
        root.chmod(0o700)
        self.root, self.now = root, e.utc() - age_seconds
        self.source, self.journal, self.profile = (root / n for n in ("receipts", "plans", "accounts"))
        for path in (self.source, self.journal, self.profile):
            path.mkdir(mode=0o700)
        namespace = os.urandom(16).hex()
        self.auth_key = Fernet.generate_key()
        self.store = Store(SimpleNamespace(data_dir=self.profile, encryption_key=self.auth_key.decode(), demo_mode=True,
            database_url="sqlite:///" + str(self.profile / "disposable-identities.sqlite")))
        (self.profile / "disposable-identities.sqlite").chmod(0o600)
        self.ids = {role: e.sha((namespace + role).encode())[:32] for role in ("preparer", "reviewer", "other")}
        self.cookies, self.csrf, self.sessions = {}, {}, {}
        passwords, hashes = credential_seed()
        with self.store.session() as session:
            for role, ident in self.ids.items():
                session.add(User(id=ident, username=role, name="Disposable recipient", firm_id="invented-firm",
                                 role="admin", active=True, password_hash=hashes[role]))
            session.flush()
            initialize_firm(session, "invented-firm")
            for role, ident in self.ids.items():
                session.execute(delete(EmployeeRole).where(EmployeeRole.user_id == ident))
                rid = e.sha((namespace + role + "-role").encode())[:32]
                session.add(FirmRole(id=rid, firm_id="invented-firm", name=role,
                    permissions=e.encode(sorted(CATALOG)).decode(), revision=1, starter=False))
                session.flush()
                session.add(EmployeeRole(user_id=ident, role_id=rid))
            session.commit()
        for role, ident in self.ids.items():
            with self.store.session() as session:
                user = session.get(User, ident)
                assert check_password(passwords[role], user.password_hash)
                self.cookies[role], self.csrf[role] = create_session(session, user, 1)
                self.sessions[role] = digest(self.cookies[role])
        e.retain(self.profile / "disposable-profile.json", e.encode({"schema": PROFILE,
            "profile_id": e.sha((namespace + "profile").encode())[:32], "production_activation": False}))
        self.authority = SessionAuthority(self.store, self.profile, firm_id="invented-firm",
            bindings={ident: "preparer" if role == "preparer" else "reviewer" for role, ident in self.ids.items()},
            origins=("http://operator.invalid",))
        context, scope = os.urandom(16).hex(), os.urandom(32).hex()
        self.source_store = receipts.ReceiptStore(root=self.source, context_id=context, scope_sha256=scope, key=os.urandom(32))
        self.journal_store = receipts.ReceiptStore(root=self.journal, context_id=context, scope_sha256=scope, key=os.urandom(32))
        self.pins = Pins(context_id=context, scope_sha256=scope, key_fingerprint=fingerprint(self.source_store.key),
            store_identity=self.source_store.identity, profile_id=self.authority.profile_id, profile_sha256=self.authority.marker_sha)
        self.planner = RecoveryPlanner(self.source_store, self.journal_store, self.pins, self.authority,
            preparer_id=self.ids["preparer"], reviewer_id=self.ids["reviewer"], clock=lambda: self.now)
        self.add("1" * 32 + ".receipt")


@dataclass
class Fixture:
    pair: object
    source: object
    target: object
    proof: object
    root: Path
    pins: TransportPins
    specification: Specification
    recipient_input_expires_at: int

    def service(self, *, packages=None, specifications=None, source=None, target=None, pins=None,
                source_scope=None, checkpoint=None):
        return MetadataHandoff(source or self.source.service({PROOF_ENTRY: self.proof}), target or self.target.service(),
            self.root, pins or self.pins, specifications if specifications is not None else {self.specification.handoff_id: self.specification},
            packages if packages is not None else {}, source_scope=source_scope or self.pair.target.account.scope("reviewer"),
            destination_id=DESTINATION, selection_id=SELECTION, checkpoint=checkpoint)

    def call(self, operation, *, service=None, scope=None, package_sha256=None, specification=None):
        spec = specification or self.specification
        chosen = self.pair.target.account if operation == "package" else self.target.account
        request = {"entry_id": spec.handoff_id, "specification_sha256": spec.sha256}
        if operation == "accept":
            request["package_sha256"] = package_sha256
        return (service or self.service()).dispatch(scope or chosen.scope("reviewer"), operation, **request)

    def protected(self):
        import stat
        rows = []
        for p in sorted(self.root.iterdir()):
            info = p.lstat()
            rows.append((p.name, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
                         os.readlink(p) if stat.S_ISLNK(info.st_mode) else p.read_bytes()))
        return self.source.protected(), self.target.protected(), rows

    def publish(self, *, mutate=None, raw_transform=None):
        before = self.protected()
        value = self.call("package")
        assert self.protected() == before and value["state"] == "metadata_package_ready"
        manifest = value["handoff"]["manifest"]
        if mutate:
            mutate(manifest)
        raw = e.encode(manifest)
        if raw_transform:
            raw = raw_transform(raw)
        e.retain(self.root / (self.specification.handoff_id + ".metadata.json"), raw)
        return e.sha(raw), value

    def fork(self, root, *, source=None, proof=None, specification=None):
        root.mkdir(mode=0o700)
        return wrap(self.pair, source or self.source, self.target, proof or self.proof,
                    root, specification=specification)


def wrap(pair, source, target, proof, root, *, specification=None):
    info = root.lstat()
    context = recipient_context(target.service(), DESTINATION, SELECTION)
    pins = TransportPins(root_identity=(info.st_dev, info.st_ino, info.st_uid, info.st_mode),
                         destination_context_sha256=context)
    now = pair.target.account.now  # The specification is authored on the source clock.
    source_context = source.service({PROOF_ENTRY: proof}).binding()
    spec = specification or Specification(handoff_id=os.urandom(16).hex(), proof_entry_id=PROOF_ENTRY,
        proof_set_sha256=proof.sha256, source_context_sha256=source_context, destination_id=DESTINATION,
        destination_context_sha256=context, created_at=now, expires_at=pair.snapshot["expires_at"])
    return Fixture(pair, source, target, proof, root, pins, spec, target.metadata_input_expires_at)


def make_recipient(root, *, age_seconds=0):
    def account(path):
        return RecipientAccount(path, age_seconds=age_seconds)
    with patch("journal_backup_fixture.Fixture", account):
        target = make_target(root)
    target.metadata_input_expires_at = target.account.now + 300
    return target


def make(pair, root, *, recipient=None):
    root.mkdir(mode=0o700)
    source = make_source(pair, root / "retention")
    proof = source.publish()
    target = recipient or make_recipient(root / "recipient")
    now = max(pair.source.account.now, pair.target.account.now, target.account.now)
    pair.source.account.now = pair.target.account.now = target.account.now = now
    transport = root / "transport"
    transport.mkdir(mode=0o700)
    return wrap(pair, source, target, proof, transport)


def new_specification(f, **changes):
    return replace(f.specification, **changes)
