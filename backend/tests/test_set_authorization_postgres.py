"""Opt-in real PostgreSQL runtime-authorization race on disposable fixture storage.

The shared fixture admits only the dedicated local test database, creates a fresh
random child database, and drops only that child. No dotenv or provider is used.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from test_provision_mappings import mapping as mapping_fixture
from test_public_sources import source as source_fixture
from test_release_authorization import authorized as authorized_fixture
from test_release_set_authorization import ONTOLOGY
from test_release_set_authorization import authorized_set as authorized_set_fixture
from test_snapshot_set_postgres import observe_identity_lock, wait_until_blocked
from test_snapshot_set_postgres import postgres_database as postgres_database_fixture
from test_source_reviews import assess

from app.config import Settings
from app.db import User
from app.main import create_app
from app.provision_mapping_models import ProvisionMappingHead
from app.release_authorization import AuthorizationError, ReleaseAuthorization
from app.release_snapshot import readonly_store
from app.source_review_models import SourceReviewHead

postgres_database = postgres_database_fixture


@pytest.fixture
def postgres_authorized_set(postgres_database, tmp_path, request):
    # Bypass environment and dotenv entirely; use only the disposable child URL.
    settings = Settings.model_construct(
        demo_mode=True, cookie_secure=False, data_dir=tmp_path / "workspace",
        database_url=postgres_database.render_as_string(hide_password=False),
        public_source_dir=tmp_path / "public-only",
    )
    app = create_app(settings)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/auth/login", json={"username": "demo", "password": "demo-local-only"})
            assert response.status_code == 200
            client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
            workspace = (app, client, client.get("/api/v1/matters").json()[0]["id"])
            source = source_fixture.__wrapped__(tmp_path)
            if getattr(request, "param", "set") == "single":
                fixture = authorized_fixture.__wrapped__(mapping_fixture.__wrapped__(workspace, source), tmp_path)
                fixture.update(app=app, sources=fixture["mapping"][2], mappings=[fixture["mapping"]])
                yield fixture
            else:
                yield authorized_set_fixture.__wrapped__(workspace, source, tmp_path)
    finally:
        app.state.store.engine.dispose()


def test_runtime_v2_guard_holds_second_source_rights_write_and_rejects_next_use(postgres_authorized_set):
    fixture = postgres_authorized_set
    app = fixture["app"]
    second = sorted(fixture["mappings"], key=lambda value: value[3])[1]
    assert second[3] != sorted(fixture["mappings"], key=lambda value: value[3])[0][3]

    def revoke_second_rights():
        return assess(second[1], second[4] + "/review", 6, "rights", decision="needs_changes")

    with readonly_store(app.state.settings) as reader, ThreadPoolExecutor(max_workers=1) as pool:
        # Use the application's public dispatcher, not the source-set gate directly.
        authorization = ReleaseAuthorization(reader, fixture["sources"], fixture["root"],
                                               fixture["public_key"], ONTOLOGY, fixture["epoch_path"])
        with authorization(fixture["info"], "read") as receipt:
            assert receipt == {"release_id": fixture["info"]["release_id"], "current": True}
            with observe_identity_lock(app.state.store.engine) as observed:
                writer = pool.submit(revoke_second_rights)
                attempted, pids = observed
                assert attempted.wait(5)
                # Database-observed blocking proves locking through the yield;
                # elapsed time or an unfinished future alone would not prove it.
                assert wait_until_blocked(app.state.store.engine, pids[0])
                assert not writer.done()
        response = writer.result(timeout=10)
        assert response.status_code == 200, response.text
        rights = next(item for item in response.json()["assessments"] if item["category"] == "rights")
        assert rights["decision"] == "needs_changes"
        with pytest.raises(AuthorizationError), authorization(fixture["info"], "read"):
            pytest.fail("Committed revocation of the second source must invalidate the whole release")


@pytest.mark.parametrize("postgres_authorized_set", ["single", "set"], indirect=True)
def test_five_runtime_readers_share_authorization_and_block_each_protected_row(postgres_authorized_set):
    fixture = postgres_authorized_set
    app = fixture["app"]
    # Every reader must enter before any can exit. Serial readers cannot pass this
    # barrier, even on a machine fast enough to hide timing-only regressions.
    entered = Barrier(5)
    with readonly_store(app.state.settings) as reader:
        authorization = ReleaseAuthorization(reader, fixture["sources"], fixture["root"],
                                             fixture["public_key"], ONTOLOGY, fixture["epoch_path"])

        def read():
            with authorization(fixture["info"], "read") as receipt:
                entered.wait(timeout=10)
                assert receipt["current"]

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(read) for _ in range(5)]
            for future in futures:
                future.result(timeout=20)

        binding = fixture["body"]["source_binding"]
        sources = binding.get("sources", [binding])
        targets = [(User, binding["operator_id"], "active")]
        targets += [(model, source[field], "revision") for source in sources
                    for model, field in ((SourceReviewHead, "source_review_head_id"),
                                         (ProvisionMappingHead, "mapping_head_id"))]
        # Bypass the common operator lock so missing protection of a later source
        # or mapping row cannot be masked. These are committed no-op fixture writes.
        def write(model, identifier, field):
            with app.state.store.session() as session:
                session.execute(update(model).where(model.id == identifier).values({field: getattr(model, field)}))
                session.commit()

        with ThreadPoolExecutor(max_workers=len(targets)) as pool:
            with authorization(fixture["info"], "read"), observe_identity_lock(
                    app.state.store.engine, statement_fragment="UPDATE ") as observed:
                futures = [pool.submit(write, *target) for target in targets]
                # A separate Event per target would require SQL parameters in the
                # observation hook. Instead, await each scheduled PID with a bound.
                deadline = time.monotonic() + 4
                while len(observed[1]) < len(targets) and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert len(observed[1]) == len(targets)
                for pid in observed[1]:
                    assert wait_until_blocked(app.state.store.engine, pid)
                assert not any(future.done() for future in futures)
            for future in futures:
                future.result(timeout=10)
        # Preparation/publication must keep their original exclusive semantics.
        for action in ("install", "activate", "rollback"):
            with ThreadPoolExecutor(max_workers=1) as pool:
                with authorization(fixture["info"], "read"), observe_identity_lock(reader.engine) as observed:
                    def transition():
                        with authorization(fixture["info"], action):
                            return True
                    future = pool.submit(transition)
                    assert observed[0].wait(5)
                    assert wait_until_blocked(app.state.store.engine, observed[1][0])
                    assert not future.done()
                assert future.result(timeout=10)
        # A real committed account revocation wins over a reader that was waiting
        # on its lock; the public signature alone must not admit that reader.
        with app.state.store.session() as writer, ThreadPoolExecutor(max_workers=1) as pool:
            writer.scalar(select(User).where(User.id == binding["operator_id"]).with_for_update())
            writer.execute(update(User).where(User.id == binding["operator_id"]).values(active=False))

            def denied():
                with pytest.raises(AuthorizationError), authorization(fixture["info"], "read"):
                    pytest.fail("Committed revocation admitted a waiting reader")

            with observe_identity_lock(reader.engine, statement_fragment="FOR SHARE") as observed:
                future = pool.submit(denied)
                assert observed[0].wait(5)
                assert wait_until_blocked(app.state.store.engine, observed[1][0])
                writer.commit()
                future.result(timeout=10)
        # Failed validation must release every acquired row lock.
        with app.state.store.session() as session:
            for model, identifier, _ in targets:
                assert session.scalar(select(model).where(model.id == identifier).with_for_update(nowait=True))
