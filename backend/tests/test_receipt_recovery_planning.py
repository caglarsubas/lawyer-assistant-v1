"""Real disposable accounts and physical interruption metadata; no live case inputs."""

import asyncio
import copy
import hashlib
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, select

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import operator_enrollment_evidence as e  # noqa: E402
import operator_recovery_inventory as inventory  # noqa: E402
import private_inventory_receipts as receipts  # noqa: E402
import receipt_recovery_inventory as physical  # noqa: E402
import receipt_recovery_planning as planning  # noqa: E402
from operator_review_auth import PROFILE, SessionAuthority  # noqa: E402
from operator_review_fixture import credential_seed  # noqa: E402
from receipt_provisioning_readiness import Pins, fingerprint  # noqa: E402

from app.auth import check_password, create_session  # noqa: E402
from app.db import EmployeeRole, FirmRole, LoginSession, Store, User, digest  # noqa: E402
from app.firm_rbac import CATALOG, initialize_firm  # noqa: E402


class Fixture:
    def __init__(self, root):
        root.chmod(0o700)
        self.root, self.now = root, e.utc()
        self.source, self.journal, self.profile = (root / name for name in ("receipts", "plans", "accounts"))
        for path in (self.source, self.journal, self.profile):
            path.mkdir(mode=0o700)
        self.store = Store(SimpleNamespace(data_dir=self.profile, encryption_key=Fernet.generate_key().decode(), demo_mode=True,
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


@pytest.fixture
def f(tmp_path):
    value = Fixture(tmp_path)
    yield value
    value.store.engine.dispose()


def test_exact_inventory_and_independent_encrypted_review_preserve_source(f):
    before = f.files()
    plan = f.prepare()
    assert plan["state"] == "pending_independent_review"
    review = f.decide(plan)
    assert review["state"] == "reviewed_for_metadata_planning"
    view = f.inspect(plan, review)
    assert view["state"] == "reviewed_for_metadata_planning"
    assert all(view[k] is False for k in physical.FLAGS)
    assert view["content_authenticity"] == "unassessed" and view["atomic_snapshot"] is False
    assert f.files() == before and len(f.files(f.journal)) == 2
    for path in f.journal.iterdir():
        assert b"prepared_by" not in path.read_bytes() and b"receipt-recovery-plan-v1" not in path.read_bytes()
        assert path.stat().st_mode & 0o777 == 0o600
    assert f.decide(plan)["state"] == "conflict" and f.files() == before


@pytest.mark.parametrize("decision", ["accept", "changes_required", "reject"])
def test_closed_decisions_remain_metadata_only(f, decision):
    plan = f.prepare()
    review = f.decide(plan, decision=decision)
    assert review["state"] == planning.DECISIONS[decision][1]
    assert f.inspect(plan, review)["state"] == review["state"]


@pytest.mark.parametrize("kind", ["self", "unassigned", "csrf", "origin", "revoked", "get", "no_origin", "duplicate_cookie"])
def test_real_auth_rejects_invalid_or_nonindependent_review_without_metadata(f, kind):
    plan = f.prepare()
    scope = f.scope("preparer" if kind == "self" else "other" if kind == "unassigned" else "reviewer")
    if kind in {"csrf", "origin"}:
        scope["headers"] = [(k, b"invalid" if k == (b"x-csrf-token" if kind == "csrf" else b"origin") else v) for k, v in scope["headers"]]
    if kind == "get":
        scope["method"] = "GET"
    elif kind == "no_origin":
        scope["headers"] = [(k, v) for k, v in scope["headers"] if k != b"origin"]
    elif kind == "duplicate_cookie":
        scope["headers"].append((b"cookie", b"la_session=untrusted"))
    if kind == "revoked":
        f.revoke("reviewer")
    before = f.files(f.journal)
    response = asyncio.run(f.planner.dispatch(scope, "decide", **f.refs(plan), decision="accept", reason_code=planning.DECISIONS["accept"][0]))
    assert response["state"] == "denied" and "plan" not in response and "review" not in response
    assert f.files(f.journal) == before


@pytest.mark.parametrize("change", ["entry", "bytes", "mode", "link", "expired", "preparer_session", "reviewer_session", "role"])
def test_changes_stale_retained_history_without_repair_or_rewrite(f, change):
    plan, before = f.prepare(), f.files()
    review = f.decide(plan)
    history = f.files(f.journal)
    path = f.source / ("1" * 32 + ".receipt")
    if change == "entry":
        f.add(".pending-" + "3" * 32)
    elif change == "bytes":
        path.write_bytes(receipts.MAGIC + os.urandom(48))
    elif change == "mode":
        path.chmod(0o644)
    elif change == "link":
        os.link(path, f.root / "outside")
    elif change == "expired":
        f.now += 301
    elif change.endswith("session"):
        f.revoke(change.split("_")[0])
    else:
        with f.store.session() as session:
            rid = session.scalar(select(EmployeeRole.role_id).where(EmployeeRole.user_id == f.ids["reviewer"]))
            session.get(FirmRole, rid).revision += 1
            session.commit()
    current = f.files()
    role = "reviewer" if change == "preparer_session" else "preparer"
    response = f.inspect(plan, review, role)
    assert response["state"] == "stale_review_retained"
    assert f.files() == current and f.files(f.journal) == history
    if change in {"expired", "preparer_session", "reviewer_session", "role"}:
        assert current == before


@pytest.mark.parametrize("kind", ["single", "staging", "partial", "pair", "outside", "duplicate", "topology"])
def test_physical_link_identity_and_partial_classification_without_decryption(f, kind):
    path = f.source / ("1" * 32 + ".receipt")
    expected = {"single_link_record": 1}
    if kind == "staging":
        f.add(".pending-" + "3" * 32)
        expected["unpublished_staging"] = 1
    elif kind == "partial":
        f.add(".pending-" + "3" * 32, b"")
        expected["incomplete_staging"] = 1
    elif kind == "pair":
        os.link(path, f.source / (".pending-" + "3" * 32))
        expected = {"linked_publication": 2}
    elif kind == "outside":
        os.link(path, f.root / "outside")
        expected = {"unaccounted_links": 1}
    elif kind == "duplicate":
        f.add("3" * 32 + ".receipt", path.read_bytes())
        expected = {"single_link_record": 2}
    elif kind == "topology":
        os.link(path, f.source / ("3" * 32 + ".receipt"))
        expected = {"unexpected_link_topology": 2}
    before = f.files()
    with patch.object(planning.AESGCM, "decrypt", side_effect=AssertionError("must not decrypt source")):
        observation = f.call("inventory")
        assert observation["state"] == "observed_metadata" and observation["inventory"]["counts"] == expected
        plan = f.prepare()
        assert plan["state"] == "pending_independent_review"
    assert f.files() == before


def test_linked_names_cannot_be_omitted_and_stale_snapshot_cannot_create_plan(f):
    os.link(f.source / ("1" * 32 + ".receipt"), f.source / (".pending-" + "3" * 32))
    observation = f.call("inventory")
    args = {"plan_id": "2" * 32, "expected_snapshot_sha256": observation["snapshot_sha256"],
            "selected_entry_ids": [observation["inventory"]["entries"][0]["entry_id"]]}
    assert f.call("prepare", **args)["state"] == "unverifiable"
    args["expected_snapshot_sha256"] = "e" * 64
    assert f.call("prepare", **args)["state"] == "conflict" and not list(f.journal.iterdir())


@pytest.mark.parametrize("change", ["symlink", "fifo", "mode", "unknown", "entries", "bytes", "time", "root"])
def test_unsafe_or_overbudget_inventory_is_closed_and_read_only(f, change):
    if change in {"symlink", "fifo"}:
        path = f.source / (".pending-" + "3" * 32)
        if change == "symlink":
            path.symlink_to(f.source / ("1" * 32 + ".receipt"))
        else:
            os.mkfifo(path, 0o600)
    elif change == "mode":
        (f.source / ("1" * 32 + ".receipt")).chmod(0o644)
    elif change == "unknown":
        f.add("unexpected-name")
    elif change == "entries":
        for i in range(32):
            f.add(f"{i + 2:032x}.receipt")
    elif change == "root":
        f.source.chmod(0o755)
    with patch.object(physical, "MAX_TOTAL_BYTES", 1 if change == "bytes" else physical.MAX_TOTAL_BYTES), \
            patch.object(physical, "SCAN_SECONDS", 0 if change == "time" else physical.SCAN_SECONDS):
        response = f.call("inventory")
    assert response["state"] == ("budget_exhausted" if change in {"entries", "bytes", "time"} else "unverifiable")
    assert response["inventory"] is None and response["snapshot_sha256"] is None and not list(f.journal.iterdir())


def test_mutation_between_scans_and_final_revocation_release_no_inventory(f):
    original = physical.scan
    def changing(*args):
        value = original(*args)
        (f.source / ("1" * 32 + ".receipt")).write_bytes(receipts.MAGIC + os.urandom(48))
        return value
    with patch.object(physical, "scan", side_effect=changing):
        response = f.call("inventory")
    assert response["state"] == "conflict" and response["inventory"] is None
    async def denied():
        raise PermissionError("private-exception-marker")
    reader = inventory.BoundReader(scope_sha256=f.pins.scope_sha256, authorize=denied, read=denied)
    response = asyncio.run(physical.observe(f.source_store, reader, f.pins, actor_sha256="e" * 64))
    assert response["state"] == "denied" and response["inventory"] is None
    assert "private-exception-marker" not in e.encode(response).decode()


@pytest.mark.parametrize("change", ["hash", "ciphertext", "kind", "decision_hash", "request_extra"])
def test_exact_encrypted_versions_closed_requests_and_purpose_binding(f, change):
    plan = f.prepare()
    review = f.decide(plan)
    refs = f.refs(plan)
    decision = review["decision_ciphertext_sha256"]
    if change == "hash":
        refs["plan_sha256"] = "e" * 64
    elif change == "ciphertext":
        path = f.journal / (plan["plan_id"] + ".receipt")
        raw = path.read_bytes()
        path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
        refs["plan_ciphertext_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif change == "kind":
        refs["plan_id"] = planning.RecoveryPlanner.decision_id(plan["plan_id"], plan["plan_ciphertext_sha256"])
        refs["plan_ciphertext_sha256"] = decision
    elif change == "decision_hash":
        decision = "e" * 64
    else:
        refs["repair_authorized"] = True
    before = f.files(f.journal)
    response = f.call("inspect", **refs, decision_ciphertext_sha256=decision)
    assert response["state"] == "unverifiable" and "plan" not in response
    assert f.files(f.journal) == before


def test_authorization_loss_after_commit_withholds_body_but_preserves_history(f):
    publish = receipts._publish
    def revoked(*args):
        publish(*args)
        f.revoke("preparer")
    before = f.files()
    with patch.object(receipts, "_publish", side_effect=revoked):
        response = f.prepare()
    assert response["state"] in {"denied", "conflict"} and "plan_ciphertext_sha256" not in response
    assert len(f.files(f.journal)) == 1 and f.files() == before


def test_trusted_wiring_requires_distinct_journal_key_namespace_and_real_principals(f):
    for journal, reviewer in ((f.source_store, f.ids["reviewer"]), (f.journal_store, f.ids["preparer"])):
        with pytest.raises(ValueError):
            planning.RecoveryPlanner(f.source_store, journal, f.pins, f.authority, preparer_id=f.ids["preparer"], reviewer_id=reviewer)


@pytest.mark.parametrize("change", ["scope_sha256", "key_fingerprint", "store_identity", "context_id"])
def test_independent_source_pins_cannot_be_replaced_by_observation(f, change):
    value = (0, 0) if change == "store_identity" else "e" * (32 if change == "context_id" else 64)
    pins = replace(f.pins, **{change: value})
    actor = f.planner.actor(f.scope())
    reader, digest = f.planner.reader(actor)
    result = asyncio.run(physical.observe(f.source_store, reader, pins, actor_sha256=digest))
    assert result["state"] == "unverifiable" and result["inventory"] is None


def test_native_source_bound_report_preserves_packages_and_four_histories():
    from receipt_recovery_native_cases import validate
    value = json.loads((ROOT / "docs/evidence/native-receipt-recovery-2026-10-29.json").read_text())
    assert value["status"] == "qualified" and value["disposable_volumes_removed"] is True
    native = value["native"]
    pins = native["faults"]
    assert validate(native, pins["receipt_manifest_sha256"], pins["controller_manifest_sha256"])["frozen_planning_cases"] == 26
    for name, expected in value["source_sha256"].items():
        assert name.startswith(("scripts/", "backend/app/", "deploy/fixtures/"))
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    for field in ("execution_authorized", "automatic_repair", "controller_reads", "planning_API_attempts"):
        changed = copy.deepcopy(native)
        changed["planning"][0][field] = True
        with pytest.raises(ValueError):
            validate(changed, pins["receipt_manifest_sha256"], pins["controller_manifest_sha256"])
