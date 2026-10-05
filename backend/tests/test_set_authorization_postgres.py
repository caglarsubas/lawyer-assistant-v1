"""Opt-in real PostgreSQL runtime-authorization race on disposable fixture storage.

The shared fixture admits only the dedicated local test database, creates a fresh
random child database, and drops only that child. No dotenv or provider is used.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from test_public_sources import source as source_fixture
from test_release_set_authorization import ONTOLOGY
from test_release_set_authorization import authorized_set as authorized_set_fixture
from test_snapshot_set_postgres import observe_identity_lock, wait_until_blocked
from test_snapshot_set_postgres import postgres_database as postgres_database_fixture
from test_source_reviews import assess

from app.config import Settings
from app.main import create_app
from app.release_authorization import AuthorizationError, ReleaseAuthorization
from app.release_snapshot import readonly_store

postgres_database = postgres_database_fixture


@pytest.fixture
def postgres_authorized_set(postgres_database, tmp_path):
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
