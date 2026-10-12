"""Isolated TEST-ONLY bytes, never cached authorization or legal-review verdicts."""
import copy
import shutil
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.public_sources import PublicSourceStore


def login(app, username, password):
    client = TestClient(app)
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


@contextmanager
def cloned_empty_workspace(root, destination):
    """No source review records or decisions; every subject still starts empty."""
    shutil.copytree(root, destination, dirs_exist_ok=True)
    settings = Settings.model_construct(demo_mode=True, cookie_secure=False, data_dir=destination,
        database_url=f"sqlite:///{destination / 'workspace.db'}", provider_base_url="", provider_api_key="", provider_model="")
    app = create_app(settings)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/auth/login", json={"username": "demo", "password": "demo-local-only"})
            assert response.status_code == 200, response.text
            client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
            yield app, client, client.get("/api/v1/matters").json()[0]["id"]
    finally:
        app.state.store.engine.dispose()


@contextmanager
def cloned_equivalence(seed, destination):
    root, evidence = seed
    shutil.copytree(root, destination, dirs_exist_ok=True)
    original_app = evidence[0][0][0]
    data_dir = destination / original_app.state.settings.data_dir.relative_to(root)
    source_dir = destination / evidence[0][0][2].root.relative_to(root)
    settings = Settings.model_construct(demo_mode=True, cookie_secure=False, data_dir=data_dir,
        database_url=f"sqlite:///{data_dir / 'workspace.db'}", public_source_dir=source_dir,
        provider_base_url="", provider_api_key="", provider_model="")
    app = create_app(settings)
    lifetime = TestClient(app)
    lifetime.__enter__()
    clients = []
    try:
        owner = login(app, "demo", "demo-local-only")
        clients.append(owner)
        identity = login(app, "identity-peer", "local-review-password")
        clients.append(identity)
        peer = login(app, "equivalence-peer", "local-review-password")
        clients.append(peer)
        sources = PublicSourceStore(source_dir)
        items = [(app, owner, sources, item[3], item[4], copy.deepcopy(item[5]), sources.verified_package(item[3]))
                 for item in evidence[0]]
        value = (items, identity, peer)
        # The real endpoint verifies complete current source/identity histories
        # and physical source bytes afresh. No verdict or HTTP cookie is reused.
        from test_decision_equivalence import endpoint
        current = owner.get(endpoint(value))
        assert current.status_code == 200 and current.json()["inputs_ready"], current.text
        yield value
    finally:
        for client in clients:
            client.close()
        lifetime.__exit__(None, None, None)
        app.state.store.engine.dispose()


@contextmanager
def cloned_signed_snapshot(seed, destination):
    root, original = seed
    with cloned_equivalence((root, original["evidence"]), destination) as evidence:
        app, owner = evidence[0][0][:2]
        reviewer = login(app, "signed-reviewer", "local-review-password")
        try:
            key = destination / original["key"].relative_to(root)
            app.state.settings.graph_b_review_trusted_key = str(key)
            signed = (app, owner, reviewer, original["signed"][3], key, copy.deepcopy(original["signed"][5]))
            from test_graph_b_snapshot import opened

            from app.graph_b_snapshot import SnapshotRequest
            from app.release_snapshot import readonly_store
            value = {"app": app, "evidence": evidence, "signed": signed,
                "request": SnapshotRequest.model_validate(original["request"].model_dump()),
                "operator_id": original["operator_id"], "key": key, "audience": original["audience"], "sources": evidence[0][0][2]}
            # Real trust, appointment, active roles, rights and original bytes are
            # revalidated against this case's independent database and key copy.
            with readonly_store(app.state.settings) as reader, opened(value, reader):
                pass
            yield value
        finally:
            reviewer.close()
