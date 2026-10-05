import hashlib
import sqlite3
from contextlib import contextmanager

import pytest
from sqlalchemy import event, func, select, text, update
from test_provision_mappings import (
    mapping as mapping_fixture,
)
from test_provision_mappings import (
    propose,
    ready,
    review,
)
from test_provision_mappings import (
    source as source_fixture,
)
from test_provision_mappings import (
    workspace as workspace_fixture,
)
from test_source_reviews import another_client, assess, assign, revoke

from app.config import Settings
from app.db import Audit, Base, User
from app.provision_mapping_models import ProvisionMappingEvent, ProvisionMappingHead
from app.public_sources import PublicSourceStore
from app.release_snapshot import REQUIRED_USES, SnapshotError, locked_snapshot, readonly_store
from app.source_review_models import SourceReviewEvent, SourceReviewHead

mapping = mapping_fixture
source = source_fixture
workspace = workspace_fixture


@pytest.fixture
def accepted(mapping):
    ready(mapping, uses=sorted(REQUIRED_USES))
    identifier = propose(mapping, source_revision=5).json()["items"][0]["id"]
    result = review(mapping, identifier)
    assert result.status_code == 200
    return mapping


def operator_id(app):
    with app.state.store.session() as session:
        return session.scalar(select(User.id).where(User.username == "demo"))


@contextmanager
def snapshot(mapping, *, reader=None, **changes):
    app, _, sources, source_id, _ = mapping
    with locked_snapshot(reader or app.state.store, sources, **{
        "operator_id": operator_id(app), "source_id": source_id,
        "expected_source_review_revision": 5, "expected_mapping_revision": 2, **changes}) as value:
        yield value


def counts(app):
    with app.state.store.session() as session:
        return tuple(session.scalar(select(func.count()).select_from(model)) for model in (
            SourceReviewHead, SourceReviewEvent, ProvisionMappingHead, ProvisionMappingEvent, User, Audit))


def test_snapshot_is_exact_deterministic_and_has_no_writes(accepted):
    app, client, store, source_id, base = accepted
    before = counts(app)
    packages = {path.name: path.read_bytes() for path in (store.root / source_id).iterdir()}
    statements = []
    event.listen(app.state.store.engine, "before_cursor_execute", lambda *args: statements.append(args[2]))
    with snapshot(accepted) as first:
        assert first["state"] == client.get(base + "/provision-mappings").json()
        assert first["source_review"]["assessments"]["rights"]["permitted_uses"] == sorted(REQUIRED_USES)
        assert first["package"].text == store.verified_package(source_id).text
        assert first["binding"]["source_id"] == source_id
        assert first["binding"]["firm_id"] == "demo-firm"
        assert first["binding"]["operator_id"] == operator_id(app)
        assert first["binding"]["source_review_revision"] == 5
        assert first["binding"]["mapping_revision"] == 2
        assert len(first["binding"]["projections_sha256"]) == 64
        assert first["state"]["publication_eligible"] is False
        assert not any(hasattr(value, "_sa_instance_state") for value in first.values())
    with snapshot(accepted) as second:
        assert second["binding"] == first["binding"]
        assert second["source_review"] == first["source_review"]
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    assert counts(app) == before
    assert packages == {path.name: path.read_bytes() for path in (store.root / source_id).iterdir()}


def test_readonly_store_opens_existing_encryption_without_schema_bootstrap_or_key_changes(accepted, monkeypatch):
    app = accepted[0]
    settings = app.state.settings
    before_key = (settings.data_dir / "demo-encryption.key").read_bytes()
    before = counts(app)
    monkeypatch.setattr(Base.metadata, "create_all", lambda *_: pytest.fail("Schema initialization forbidden"))
    disposed = []
    with readonly_store(settings) as reader:
        event.listen(reader.engine, "engine_disposed", lambda engine: disposed.append(True))
        with snapshot(accepted, reader=reader) as value:
            assert value["state"]["handoff_ready"]
        assert reader.preparation_mac(b"exact manifest") == reader.preparation_mac(b"exact manifest")
        assert reader.preparation_mac(b"exact manifest") != reader.preparation_mac(b"changed manifest")
        assert reader.preparation_mac(b"exact manifest") != hashlib.sha256(b"exact manifest").hexdigest()
        mac = reader.preparation_mac(b"exact manifest")
        with pytest.raises(SnapshotError):
            reader.preparation_mac("not bytes")
    assert disposed == [True]
    with readonly_store(settings) as reader:
        assert reader.preparation_mac(b"exact manifest") == mac
    assert (settings.data_dir / "demo-encryption.key").read_bytes() == before_key
    assert counts(app) == before


def test_readonly_store_disposes_when_caller_fails(accepted):
    disposed = []
    with pytest.raises(RuntimeError, match="Caller output failed"):
        with readonly_store(accepted[0].state.settings) as reader:
            event.listen(reader.engine, "engine_disposed", lambda engine: disposed.append(True))
            raise RuntimeError("Caller output failed")
    assert disposed == [True]


@pytest.mark.parametrize("operation", ["orm", "direct_update", "ddl"])
def test_reader_rejects_database_mutation_and_ddl(accepted, operation):
    app = accepted[0]
    before = counts(app)
    with readonly_store(app.state.settings) as reader:
        with reader.session() as session, pytest.raises(SnapshotError):
            if operation == "orm":
                user = session.scalar(select(User))
                user.name = "Unauthorized change"
                session.commit()
            elif operation == "direct_update":
                session.execute(update(User).values(name="Unauthorized change"))
            else:
                session.execute(text("CREATE TABLE forbidden_table (id TEXT)"))
    assert counts(app) == before
    with app.state.store.session() as session:
        assert session.scalar(select(User.name).where(User.username == "demo")) == "Demo Avukat"


@pytest.mark.parametrize("demo,db_exists,key_exists", [
    (False, True, True), (True, False, True), (True, True, False), (True, False, False)])
def test_reader_never_creates_database_or_encryption_files(tmp_path, demo, db_exists, key_exists):
    from cryptography.fernet import Fernet

    path = tmp_path / "existing.db"
    if db_exists:
        sqlite3.connect(path).close()
    if key_exists:
        (tmp_path / "demo-encryption.key").write_bytes(Fernet.generate_key())
    before = {file.name: file.read_bytes() for file in tmp_path.iterdir()}
    settings = Settings(_env_file=None, demo_mode=demo, data_dir=tmp_path, database_url=f"sqlite:///{path}")
    with pytest.raises(SnapshotError), readonly_store(settings):
        pass
    assert before == {file.name: file.read_bytes() for file in tmp_path.iterdir()}


def test_reader_missing_schema_is_not_created(tmp_path):
    from cryptography.fernet import Fernet

    path = tmp_path / "existing.db"
    sqlite3.connect(path).close()
    settings = Settings(_env_file=None, demo_mode=True, data_dir=tmp_path, database_url=f"sqlite:///{path}",
                        encryption_key=Fernet.generate_key().decode())
    with pytest.raises(SnapshotError), readonly_store(settings) as reader:
        with reader.session() as session:
            session.scalar(select(User))
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
    assert not (tmp_path / "demo-encryption.key").exists()


@pytest.mark.parametrize("changes", [
    {"source_id": "bad"}, {"operator_id": ""}, {"expected_source_review_revision": True},
    {"expected_mapping_revision": True}, {"expected_source_review_revision": 0}, {"expected_mapping_revision": -1},
    {"expected_source_review_revision": 4}, {"expected_mapping_revision": 1},
    {"expected_source_review_revision": 1001}, {"operator_id": "f" * 32}, {"source_id": "f" * 64}])
def test_snapshot_requires_exact_ids_and_revisions(accepted, changes):
    with pytest.raises(SnapshotError), snapshot(accepted, **changes):
        pytest.fail("Invalid snapshot must not yield")


@pytest.mark.parametrize("kind", ["inactive", "role", "firm"])
def test_snapshot_denies_revoked_or_foreign_operator(accepted, kind):
    revoke(accepted[0], kind)
    with pytest.raises(SnapshotError), snapshot(accepted):
        pytest.fail("Revoked operator must not obtain a snapshot")


def test_other_admin_cannot_prepare_sources_owned_by_another_reviewer(accepted):
    app = accepted[0]
    another_client(app, username="another-admin", role="admin")
    with app.state.store.session() as session:
        other = session.scalar(select(User.id).where(User.username == "another-admin"))
    with pytest.raises(SnapshotError, match="own"), snapshot(accepted, operator_id=other):
        pytest.fail("Ownership cannot be overridden by an admin")


def test_snapshot_requires_all_six_rights_scopes(mapping):
    ready(mapping)
    identifier = propose(mapping, source_revision=5).json()["items"][0]["id"]
    assert review(mapping, identifier).status_code == 200
    with pytest.raises(SnapshotError, match="rights"), snapshot(mapping):
        pytest.fail("Local review permission is not corpus preparation permission")


@pytest.mark.parametrize("change", ["source_rejected", "source_reaffirmed", "mapping_rejected", "unreviewed_mapping"])
def test_snapshot_rejects_not_ready_or_stale_current_states(accepted, change):
    _, client, _, _, base = accepted
    source_revision, mapping_revision = 5, 2
    identifier = client.get(base + "/provision-mappings").json()["items"][0]["id"]
    if change.startswith("source"):
        assert assess(client, base + "/review", 5, "legal",
                      "rejected" if change == "source_rejected" else "accepted").status_code == 200
        source_revision = 6
    elif change == "mapping_rejected":
        assert review(accepted, identifier, 2, 5, "rejected").status_code == 200
        mapping_revision = 3
    else:
        assert propose(accepted, 2, 5, candidate_id=None, start=0, end=18, label="Other manual").status_code == 200
        mapping_revision = 3
    with pytest.raises(SnapshotError), snapshot(accepted, expected_source_review_revision=source_revision,
                                              expected_mapping_revision=mapping_revision):
        pytest.fail("All included mappings and current source assessments must be ready")


@pytest.mark.parametrize("change", ["source", "mapping", "owner", "role", "inactive", "firm", "package"])
def test_snapshot_exit_revalidates_live_authorization_ledgers_and_bytes(accepted, change):
    app, client, sources, source_id, base = accepted
    with pytest.raises(SnapshotError), snapshot(accepted) as value:
        if change == "source":
            assert assess(client, base + "/review", 5, "legal").status_code == 200
        elif change == "mapping":
            identifier = value["state"]["items"][0]["id"]
            assert review(accepted, identifier, 2, 5, "rejected").status_code == 200
        elif change == "owner":
            assert assign(client, base + "/review", 5, "release").status_code == 200
        elif change == "package":
            path = sources.root / source_id / "text.txt"
            path.chmod(0o600)
            path.write_bytes(path.read_bytes() + b"tampered")
        else:
            revoke(app, change)


def test_caller_cannot_mutate_snapshot_into_bypassing_live_checks(accepted):
    app, client, _, _, base = accepted
    with pytest.raises(SnapshotError), snapshot(accepted) as value:
        assert assess(client, base + "/review", 5, "legal").status_code == 200
        value["binding"]["source_review_revision"] = 6
        value["state"]["source_review_revision"] = 6
        value["source_review"]["context"]["revision"] = 6
    assert counts(app)[1] == 6


@pytest.mark.parametrize("target", ["source", "mapping"])
def test_snapshot_rejects_corrupt_ledger_envelopes(accepted, target):
    app = accepted[0]
    model = SourceReviewHead if target == "source" else ProvisionMappingHead
    with app.state.store.session() as session:
        row = session.scalar(select(model))
        row.payload = "broken ciphertext"
        session.commit()
    with pytest.raises(SnapshotError, match="integrity"), snapshot(accepted):
        pytest.fail("Ledger corruption must fail closed")


def test_current_package_is_checked_before_yield_and_again_on_exit(accepted, monkeypatch):
    original = PublicSourceStore.verified_package
    calls = []

    def verify(store, identifier):
        calls.append(identifier)
        return original(store, identifier)

    monkeypatch.setattr(PublicSourceStore, "verified_package", verify)
    with snapshot(accepted):
        assert len(calls) == 1
    assert calls == [accepted[3], accepted[3]]


def test_postgres_reader_uses_bounded_connection_lock_and_statement_timeouts(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from sqlalchemy import create_engine

    from app import release_snapshot

    calls = []

    def capture(url, **kwargs):
        calls.append(kwargs)
        return create_engine("sqlite://")  # No network or PostgreSQL service needed for contract check.

    monkeypatch.setattr(release_snapshot, "create_engine", capture)
    settings = Settings(_env_file=None, demo_mode=False, data_dir=tmp_path,
                        database_url="postgresql+psycopg://fixture:fixture@127.0.0.1/fixture?connect_timeout=0",
                        encryption_key=Fernet.generate_key().decode())
    with readonly_store(settings):
        assert calls == [{"pool_pre_ping": True, "connect_args": {
            "connect_timeout": 5, "options": "-c lock_timeout=5000 -c statement_timeout=15000"}}]
