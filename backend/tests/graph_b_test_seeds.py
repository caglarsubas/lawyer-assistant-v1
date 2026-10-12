"""Isolated TEST-ONLY bytes, never cached authorization or legal-review verdicts."""
import copy
import shutil
from contextlib import contextmanager
from pathlib import Path

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
        database_url=f"sqlite:///{destination / 'workspace.db'}", public_source_dir=destination / "public-only", provider_base_url="", provider_api_key="", provider_model="")
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


@contextmanager
def cloned_component_grant(seed, destination):
    root, original, original_grant = seed
    with cloned_signed_snapshot((root, original['current']), destination) as current:
        from test_graph_b_component_grants import command_module
        settings = current['app'].state.settings
        for field in ('graph_trusted_review_key', 'graph_b_component_trusted_key'):
            setattr(settings, field, str(destination / Path(getattr(original['settings'], field)).relative_to(root)))
        paths = {name: destination / original[name].relative_to(root)
                 for name in ('prepared', 'packet', 'public', 'epoch', 'envelope', 'request')}
        value = {**paths, 'command': command_module(), 'current': current, 'settings': settings,
                 'key': original['key'], 'body': copy.deepcopy(original['body'])}
        grant = destination / original_grant.relative_to(root)
        # The actual gate freshly verifies every signed envelope, public byte,
        # private original source/ledger, account, proof, appointment and key copy.
        assert value['command'].validate(settings, value['prepared'], grant=grant)['current_component_grant']
        yield value, grant


@contextmanager
def cloned_analysis_workbench(seed, destination):
    root, original = seed
    with cloned_empty_workspace(root, destination) as (app, client, matter):
        base = f'/api/v1/matters/{matter}'
        payload, fact = copy.deepcopy(original[3]), copy.deepcopy(original[4])
        document, text = original[5:]
        # Inspect only copied setup bytes here. Authentication and every subject's
        # current evidence/permission checks still execute through the real app.
        # Avoid three redundant HTTP retrievals before every analysis case.
        from sqlalchemy import select

        from app.db import Record, digest
        with app.state.store.session() as session:
            rows = list(session.scalars(select(Record).where(Record.matter_id == matter)))
            doc = next(row for row in rows if row.id == document)
            actual_doc = app.state.store.decode(doc)
            assert actual_doc['passages'][0]['text'] == text and actual_doc['sha256'] == digest(text)
            assert doc.revision == payload['evidence'][0]['document_revision']
            assert app.state.store.view(next(row for row in rows if row.id == fact['id'])) == fact
            assert not any(row.kind in {'analysis', 'analysis_version', 'analysis_review'} for row in rows)
        yield app, client, base, payload, fact, document, text


@contextmanager
def cloned_unsigned_graph_b(seed, destination):
    root, original_evidence, original_inputs = seed
    with cloned_equivalence((root, original_evidence), destination) as evidence:
        from sqlalchemy import func, select
        from test_graph_b_review import request_body

        from app.graph_b_review_models import GraphBReviewEvent, GraphBReviewHead
        app, owner = evidence[0][0][:2]
        reviewer = login(app, 'signed-reviewer', 'local-review-password')
        try:
            key = destination / original_inputs[4].relative_to(root)
            app.state.settings.graph_b_review_trusted_key = str(key)
            inputs = (app, owner, reviewer, original_inputs[3], key, copy.deepcopy(original_inputs[5]))
            with app.state.store.session() as session:
                assert session.scalar(select(func.count()).select_from(GraphBReviewHead)) == 0
                assert session.scalar(select(func.count()).select_from(GraphBReviewEvent)) == 0
            # Current unsigned request verification executes against these case
            # bytes and active independent accounts. Every acceptance test still
            # creates its own actual external signature and review event.
            checked = request_body(evidence, inputs)
            assert checked.status_code == 200 and checked.json()['signed'] is False, checked.text
            yield evidence, inputs
        finally:
            reviewer.close()
