"""Synthetic lifecycle records; no test attests any legal review."""

import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hash_password
from app.config import Settings
from app.db import Audit, Membership, Record, User, digest
from app.governance import dependency_ids
from app.main import create_app


@pytest.fixture
def workspace(tmp_path):
    app = create_app(
        Settings(
            _env_file=None,
            demo_mode=True,
            cookie_secure=False,
            data_dir=tmp_path,
            LLM_PROVIDER_BASE_URL="",
            LLM_PROVIDER_API_KEY="",
            LLM_PROVIDER_MODEL="",
        )
    )
    with TestClient(app) as client:
        login(client)
        yield app, client, client.get("/api/v1/matters").json()[0]["id"]


def login(client, username="demo", password="demo-local-only"):
    result = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]


def revision(client, matter):
    return client.get(f"/api/v1/matters/{matter}/governance").json()["matter_revision"]


def archive(client, matter):
    return client.post(
        f"/api/v1/matters/{matter}/archive",
        json={"reason": "Synthetic archive test", "expected_revision": revision(client, matter)},
    )


def add_user(app, username, *, firm="demo-firm", role="admin", member_of=None):
    with app.state.store.session() as session:
        user = User(
            username=username,
            name=username,
            firm_id=firm,
            role=role,
            password_hash=hash_password("test-password-123"),
        )
        session.add(user)
        session.flush()
        if member_of:
            session.add(Membership(matter_id=member_of, user_id=user.id))
        session.commit()
        return user.id


def seed_product(app, matter, *, payload=None, owner="demo"):
    data = {
        "title": "SYNTHETIC reviewed product",
        "status": "reviewed",
        "summary": "Original summary",
        "claims": [{"id": "synthetic-claim", "text": "Original claim", "review_status": "approved"}],
        "snapshots": {"sources": {"doc-old": 2}, "corpus": {"release_id": "release-old"}},
        "evidence": [{"document_id": "doc-old", "text": "Original quotation"}],
        "graph_paths": [{"edges": [{"id": "assertion-old", "source": "node-a", "target": "node-b"}]}],
        "version": 1,
    }
    data.update(payload or {})
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == owner))
        product = app.state.store.add(session, "product", user, data, matter)
        session.commit()
        return product.id, deepcopy(data)


def test_hold_blocks_archive_and_release_preserves_hold(workspace):
    app, client, matter = workspace
    base = f"/api/v1/matters/{matter}"
    old_revision = revision(client, matter)
    created = client.post(
        base + "/legal-holds", json={"reason": "Synthetic preservation", "authority_reference": "TEST-ONLY"}
    )
    assert created.status_code == 201
    hold_id = created.json()["id"]
    assert revision(client, matter) == old_revision + 1
    plan = client.post(base + "/erasure-plan").json()
    assert plan["active_hold_ids"] == [hold_id]
    assert not plan["archive_allowed"] and not plan["purge_allowed"]
    assert archive(client, matter).status_code == 409
    with app.state.store.session() as session:
        original = app.state.store.decode(session.get(Record, hold_id))
    release = {"reason": "Synthetic release instruction", "authority_reference": "TEST-RELEASE"}
    assert client.post(base + f"/legal-holds/{hold_id}/release", json=release).status_code == 200
    assert client.post(base + f"/legal-holds/{hold_id}/release", json=release).status_code == 409
    with app.state.store.session() as session:
        assert app.state.store.decode(session.get(Record, hold_id)) == original
    assert client.get(base + "/governance").json()["holds"][0]["status"] == "released"
    assert archive(client, matter).status_code == 200


def test_retention_is_immutable_unqualified_and_never_expires(workspace):
    app, client, matter = workspace
    base = f"/api/v1/matters/{matter}"
    default = client.get(base + "/governance").json()["retention_policy"]
    assert default["retention_days"] is None and not default["automatic_expiry"]
    payload = {
        "reason": "Synthetic policy",
        "policy_reference": "TEST",
        "retention_days": 1,
        "trigger": "matter_closed",
        "review_due_at": "2000-01-01",
    }
    first = client.put(base + "/retention-policy", json=payload)
    assert first.status_code == 201
    second = client.put(base + "/retention-policy", json={**payload, "retention_days": None}).json()
    assert second["supersedes_policy_id"] == first.json()["id"]
    assert second["qualification_status"] == "operator_recorded_unqualified"
    assert not second["automatic_expiry"] and not second["automatic_erasure"]
    with app.state.store.session() as session:
        assert app.state.store.decode(session.get(Record, first.json()["id"]))["retention_days"] == 1
    assert client.get(base).status_code == 200
    assert (
        client.put(base + "/retention-policy", json={**payload, "automatic_erasure": True}).status_code == 422
    )
    assert (
        client.put(base + "/retention-policy", json={**payload, "review_due_at": "2025-02-31"}).status_code
        == 422
    )


def test_archive_restore_preserves_bytes_reviews_and_cancels_jobs(workspace):
    app, client, matter = workspace
    store = app.state.store
    base = f"/api/v1/matters/{matter}"
    product_id, product = seed_product(app, matter)
    vault = app.state.settings.data_dir / "documents"
    vault.mkdir(exist_ok=True)
    original = vault / "synthetic-original.enc"
    original.write_bytes(b"SYNTHETIC ORIGINAL BYTES")
    with store.session() as session:
        user = session.scalar(select(User).where(User.username == "demo"))
        doc = store.add(
            session, "document", user, {"sha256": "synthetic", "original_path": original.name}, matter
        )
        # No executing worker owns this synthetic record, so only stop intent can be asserted.
        job = store.add(session, "research", user, {"status": "running", "question": "Synthetic"}, matter)
        session.commit()
        old_matter = store.decode(session.get(Record, matter))
    plan = client.post(base + "/erasure-plan").json()
    assert {item["document_id"]: item["state"] for item in plan["originals"]}[doc.id] == "present"
    assert plan["record_counts"]["product"] == 1 and str(original) not in json.dumps(plan)
    archived = archive(client, matter)
    assert archived.status_code == 200, archived.text
    body = archived.json()
    assert body["restorable"] and not body["physical_erasure"]
    assert original.read_bytes() == b"SYNTHETIC ORIGINAL BYTES"
    assert client.get(base).status_code == 404
    assert client.get(base + f"/products/{product_id}").status_code == 404
    assert matter not in {row["id"] for row in client.get("/api/v1/matters").json()}
    assert client.get("/api/v1/governance/archived-matters").json()[0]["id"] == matter
    with store.session() as session:
        assert store.decode(session.get(Record, product_id)) == product
        assert store.decode(session.get(Record, job.id))["status"] == "cancelling"
        assert store.decode(session.get(Record, matter)) == old_matter
        assert session.get(Record, body["tombstone_id"]).kind == "matter_tombstone"
    restore_url = f"/api/v1/governance/archived-matters/{matter}/restore"
    assert (
        client.post(restore_url, json={"reason": "Restore test", "expected_revision": 1}).status_code == 409
    )
    assert (
        client.post(
            restore_url, json={"reason": "Restore test", "expected_revision": body["revision"]}
        ).status_code
        == 200
    )
    assert client.get(base).status_code == 200
    assert client.get("/api/v1/governance/archived-matters").json() == []
    with store.session() as session:
        assert store.decode(session.get(Record, product_id)) == product
        assert store.decode(session.get(Record, job.id))["status"] == "cancelling"
        assert session.get(Record, body["tombstone_id"])


@pytest.mark.parametrize(
    "firm,role,membership,status",
    [
        ("demo-firm", "admin", False, 404),
        ("foreign-firm", "admin", True, 404),
        ("demo-firm", "lawyer", True, 403),
    ],
)
def test_admin_never_bypasses_membership_or_firm(workspace, firm, role, membership, status):
    app, client, matter = workspace
    add_user(app, "other", firm=firm, role=role, member_of=matter if membership else None)
    login(client, "other", "test-password-123")
    base = f"/api/v1/matters/{matter}"
    assert (
        client.post(
            base + "/legal-holds", json={"reason": "Synthetic hold", "authority_reference": "TEST"}
        ).status_code
        == status
    )
    assert (
        client.post(
            base + "/archive", json={"reason": "Synthetic archive", "expected_revision": 1}
        ).status_code
        == status
    )
    assert client.post(base + "/erasure-plan").status_code == status
    assert (
        client.post(
            base + "/dependencies/invalidate",
            json={"reason": "Synthetic change", "changes": [{"kind": "source", "old_id": "doc-old"}]},
        ).status_code
        == status
    )
    assert client.get("/api/v1/governance/archived-matters").json() == []


def test_restore_rejects_non_matter_record_and_unknown_archive(workspace):
    app, client, matter = workspace
    product_id, _ = seed_product(app, matter)
    payload = {"reason": "Unknown archive provenance", "expected_revision": 1}
    assert (
        client.post(f"/api/v1/governance/archived-matters/{product_id}/restore", json=payload).status_code
        == 404
    )
    with app.state.store.session() as session:
        record = session.get(Record, matter)
        record.kind = "archived_matter"
        session.commit()
    assert (
        client.post(f"/api/v1/governance/archived-matters/{matter}/restore", json=payload).status_code == 409
    )


def test_archived_hold_allows_restoration_but_prevents_rearchive(workspace):
    app, client, matter = workspace
    assert archive(client, matter).status_code == 200
    assert (
        client.post(
            f"/api/v1/matters/{matter}/legal-holds",
            json={"reason": "Hold discovered during archive", "authority_reference": "TEST"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/v1/governance/archived-matters/{matter}/restore",
            json={"reason": "Preserve and inspect", "expected_revision": revision(client, matter)},
        ).status_code
        == 200
    )
    assert archive(client, matter).status_code == 409


@pytest.mark.parametrize(
    "kind,old_id", [("source", "doc-old"), ("assertion", "assertion-old"), ("release", "release-old")]
)
def test_exact_invalidation_preserves_claims_evidence_and_reviews(workspace, kind, old_id):
    app, client, matter = workspace
    product_id, before = seed_product(app, matter)
    unrelated_id, _ = seed_product(
        app,
        matter,
        payload={"snapshots": {}, "evidence": [], "graph_paths": [], "summary": f"Prose mentions {old_id}"},
    )
    base = f"/api/v1/matters/{matter}/dependencies"
    payload = {
        "reason": "Synthetic dependency changed",
        "changes": [{"kind": kind, "old_id": old_id, "new_id": "new-id"}],
    }
    planned = client.post(base + "/impact", json=payload).json()
    assert planned["dry_run"] and [x["product_id"] for x in planned["products"]] == [product_id]
    with app.state.store.session() as session:
        assert app.state.store.decode(session.get(Record, product_id)) == before
    assert client.post(base + "/invalidate", json=payload).status_code == 200
    with app.state.store.session() as session:
        updated = app.state.store.decode(session.get(Record, product_id))
        assert updated["status"] == "stale"
        assert {
            k: v for k, v in updated.items() if k not in {"status", "stale_reason", "stale_event_id"}
        } == {k: v for k, v in before.items() if k != "status"}
        assert app.state.store.decode(session.get(Record, unrelated_id))["status"] == "reviewed"
        assert session.get(Record, updated["stale_event_id"]).kind == "governance_event"


def test_release_invalidation_is_scoped_and_handles_archived_products(workspace):
    app, client, matter = workspace
    own_id, _ = seed_product(app, matter)
    other_id = add_user(app, "other")
    with app.state.store.session() as session:
        user = session.get(User, other_id)
        other = app.state.store.add(session, "matter", user, {"title": "SECRET MATTER"})
        session.add(Membership(matter_id=other.id, user_id=other_id))
        session.commit()
    secret_id, _ = seed_product(app, other.id, owner="other")
    assert archive(client, matter).status_code == 200
    payload = {
        "reason": "Synthetic corpus update",
        "old_release_id": "release-old",
        "new_release_id": "release-new",
    }
    plan = client.post("/api/v1/governance/releases/impact", json=payload).json()
    assert plan["scope"] == "caller_memberships_only"
    assert [m["matter_id"] for m in plan["matters"]] == [matter]
    assert "SECRET" not in json.dumps(plan) and other.id not in json.dumps(plan)
    result = client.post("/api/v1/governance/releases/invalidate", json=payload)
    assert result.status_code == 200 and not result.json()["release_installed"]
    with app.state.store.session() as session:
        assert app.state.store.decode(session.get(Record, own_id))["status"] == "stale"
        assert app.state.store.decode(session.get(Record, secret_id))["status"] == "reviewed"
        assert not session.scalar(select(Audit).where(Audit.matter_id == other.id))
    assert (
        client.post(
            "/api/v1/governance/releases/invalidate", json={**payload, "new_release_id": "release-old"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/governance/releases/invalidate", json={**payload, "old_release_id": " "}
        ).status_code
        == 422
    )


def test_dependency_extraction_only_declared_provenance():
    ids = dependency_ids(
        {
            "snapshots": {
                "sources": {"source-a": 1},
                "ontology": "ontology-a",
                "model": "model-a",
                "policy": "policy-a",
                "graphs": [{"release_id": "graph-a", "ontology_sha256": "ontology-hash"}],
                "practice_versions": {"practice-a": {"version_id": "practice-a-v1"}},
            },
            "evidence": [{"artifact_sha256": "hash-a", "text": "unrelated-id"}],
            "graph_paths": [
                {
                    "snapshot": {"bundle_sha256": "bundle-a"},
                    "edges": [{"id": "edge-a", "evidence_id": "evidence-a"}],
                }
            ],
            "authority_candidates": {"snapshot": {"release_id": "corpus-a"}},
        }
    )
    assert ids == {
        "source": {"source-a", "hash-a", "evidence-a", "practice-a", "practice-a-v1"},
        "assertion": {"edge-a"},
        "release": {"ontology-a", "graph-a", "bundle-a", "corpus-a", "model-a", "policy-a", "ontology-hash"},
    }


def test_audit_ledger_chain_and_csrf(workspace):
    app, client, matter = workspace
    base = f"/api/v1/matters/{matter}"
    csrf = client.headers.pop("X-CSRF-Token")
    assert (
        client.post(
            base + "/legal-holds", json={"reason": "Synthetic", "authority_reference": "TEST"}
        ).status_code
        == 403
    )
    client.headers["X-CSRF-Token"] = csrf
    for n in range(2):
        assert (
            client.put(
                base + "/retention-policy",
                json={"reason": "Synthetic policy", "policy_reference": f"TEST-{n}"},
            ).status_code
            == 201
        )
    ledger = client.get(base + "/governance").json()["ledger"]
    assert [event["sequence"] for event in ledger] == [1, 2]
    assert ledger[1]["previous_event_id"] == ledger[0]["id"]
    assert ledger[1]["previous_event_digest"] == ledger[0]["event_digest"]
    for event in ledger:
        content = {
            k: v for k, v in event.items() if k not in {"id", "revision", "created_at", "event_digest"}
        }
        assert (
            digest(json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            == event["event_digest"]
        )
        with app.state.store.session() as session:
            assert session.scalar(
                select(Audit).where(Audit.object_id == event["id"], Audit.matter_id == matter)
            )


@pytest.mark.parametrize(
    "firm,role,member,status",
    [
        ("demo-firm", "admin", False, 404),
        ("foreign-firm", "admin", True, 404),
        ("demo-firm", "lawyer", True, 403),
    ],
)
def test_archived_list_and_restore_do_not_bypass_access(workspace, firm, role, member, status):
    app, client, matter = workspace
    archived = archive(client, matter).json()
    add_user(app, "restore-other", firm=firm, role=role, member_of=matter if member else None)
    login(client, "restore-other", "test-password-123")
    listing = client.get("/api/v1/governance/archived-matters").json()
    if member and firm == "demo-firm":
        assert [entry["id"] for entry in listing] == [matter]
        assert not listing[0]["can_restore"]
    else:
        assert listing == []
    result = client.post(
        f"/api/v1/governance/archived-matters/{matter}/restore",
        json={
            "reason": "Unauthorized restoration",
            "expected_revision": archived["revision"],
        },
    )
    assert result.status_code == status
    with app.state.store.session() as session:
        assert session.get(Record, matter).kind == "archived_matter"


def test_original_inventory_rejects_path_escape_and_does_not_claim_erasure(workspace):
    app, client, matter = workspace
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == "demo"))
        record = app.state.store.add(session, "document", user, {"original_path": "../../secret"}, matter)
        session.commit()
    plan = client.post(f"/api/v1/matters/{matter}/erasure-plan").json()
    assert {item["document_id"]: item["state"] for item in plan["originals"]}[record.id] == "unsafe_reference"
    assert "../../secret" not in json.dumps(plan)
    assert not plan["physical_erasure_available"]
    assert plan["external_stores"]["backups"] == "not_inventoried"
