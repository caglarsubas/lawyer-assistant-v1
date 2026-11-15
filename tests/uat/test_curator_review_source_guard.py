"""Use disposable source packages to exercise the curator commit boundary."""

import pytest
import test_decision_mappings as decisions
import test_provision_mappings as provisions
import test_source_relationships as relationships
from app.config import Settings
from app.decision_mapping_models import DecisionMappingEvent, DecisionMappingHead
from app.provision_mapping_models import ProvisionMappingEvent, ProvisionMappingHead
from app.runtime import create_app
from app.source_review_models import (
    SourceRelationshipEvent,
    SourceRelationshipHead,
    SourceReviewEvent,
    SourceReviewHead,
)
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from test_jurisprudence_candidates import incoming as incoming_fixture
from test_public_sources import source as source_fixture
from test_source_comparison import pair as source_pair
from test_source_reviews import another_client, assess, assign

incoming = incoming_fixture
source = source_fixture


@pytest.fixture
def workspace(tmp_path):
    app = create_app(Settings.model_construct(demo_mode=True, cookie_secure=False, data_dir=tmp_path / "workspace"))
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/login", json={"username": "demo", "password": "demo-local-only"})
        assert login.status_code == 200
        client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        yield app, client, None


def prepare_assessment(workspace, source, incoming):
    app, client, _ = workspace
    store, inputs, _, _ = source
    source_id = store.import_package(**inputs)["id"]
    app.state.settings.public_source_dir = store.root
    base = f"/api/v1/public-sources/{source_id}/review"
    assert assign(client, base).status_code == 200
    assert assess(client, base, category="legal").status_code == 200
    return store, (source_id,), base, lambda: assess(client, base, revision=2, category="legal", decision="rejected")


def prepare_provision(workspace, source, incoming):
    mapping = provisions.mapping.__wrapped__(workspace, source)
    provisions.ready(mapping)
    _, _, store, source_id, base = mapping
    identifier = provisions.propose(mapping, source_revision=5).json()["items"][0]["id"]
    return store, (source_id,), base + "/provision-mappings", lambda: provisions.review(mapping, identifier)


def prepare_decision(workspace, source, incoming):
    mapping = decisions.mapping.__wrapped__(workspace, incoming)
    decisions.ready(mapping)
    _, _, store, source_id, base, _, _ = mapping
    identifier = decisions.propose(mapping).json()["items"][0]["id"]
    return store, (source_id,), base + "/decision-mappings", lambda: decisions.review(mapping, identifier)


def prepare_relationship(workspace, source, incoming):
    pair = source_pair.__wrapped__(source, workspace)
    value = relationships.relationship.__wrapped__(pair)
    relationships.prepare(value)
    _, client, store, left, right, base, body = value
    assert client.post(base, json=body).status_code == 200
    next_review = {**body, "expected_revision": 1, "classification": "unresolved", "identities": []}
    return store, (left, right), base, lambda: client.post(base, json=next_review)


@pytest.mark.parametrize(("prepare", "head", "ledger_event", "role"), [
    pytest.param(prepare_assessment, SourceReviewHead, SourceReviewEvent, "curator", id="curator-assessment"),
    pytest.param(prepare_provision, ProvisionMappingHead, ProvisionMappingEvent, "admin", id="admin-provision"),
    pytest.param(prepare_decision, DecisionMappingHead, DecisionMappingEvent, "curator", id="curator-decision"),
    pytest.param(prepare_relationship, SourceRelationshipHead, SourceRelationshipEvent, "admin", id="admin-relationship"),
])
def test_curator_review_reopens_exact_source_after_autoflush(workspace, source, incoming,
                                                           prepare, head, ledger_event, role):
    app, admin, _ = workspace
    client = another_client(app) if role == "curator" else admin
    try:
        store, source_ids, read_path, write = prepare((app, client, None), source, incoming)
        paths = [store.root / identifier for identifier in source_ids]
        original = paths[-1]
        held = store.root / ".incoming-quarantined"

        def original_bytes():
            return {path.name: {item.name: item.read_bytes() for item in path.iterdir()} for path in paths}

        def encrypted_ledger():
            with app.state.store.session() as session:
                return [
                    [tuple(row) for row in session.execute(select(model.id, model.revision, model.payload).order_by(model.id))]
                    for model in (head, ledger_event)
                ]

        def interrupt_after_event_admission(session, *_):
            if any(isinstance(record, ledger_event) for record in session.new):
                original.rename(held)

        before_bytes = original_bytes()
        before_ledger = encrypted_ledger()
        before_review = client.get(read_path).json()
        event.listen(app.state.store.session, "before_flush", interrupt_after_event_admission)
        try:
            rejected = write()
        finally:
            event.remove(app.state.store.session, "before_flush", interrupt_after_event_admission)
            if held.exists():
                held.rename(original)
        assert rejected.status_code == 409
        assert rejected.headers["Cache-Control"] == "no-store"
        assert set(rejected.json()) == {"detail"}
        assert encrypted_ledger() == before_ledger
        assert original_bytes() == before_bytes
        assert client.get(read_path).json() == before_review

        response = write()
        assert response.status_code == 200
        advanced = response.json()
        assert advanced["revision"] == before_review["revision"] + 1
        assert advanced["history"][1:] == before_review["history"]
        assert write().status_code == 409
        assert client.get(read_path).json() == advanced
        assert original_bytes() == before_bytes
        assert len(encrypted_ledger()[1]) == len(before_ledger[1]) + 1
        outsider = another_client(app, username="isolated-curator", firm="isolated-test-firm")
        try:
            isolated = outsider.get(read_path)
            assert isolated.status_code == 200
            assert isolated.json()["revision"] == 0 and isolated.json()["history"] == []
        finally:
            outsider.close()
    finally:
        if client is not admin:
            client.close()
