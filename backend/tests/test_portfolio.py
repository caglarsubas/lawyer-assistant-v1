from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hash_password
from app.config import Settings
from app.db import Membership, Record, User
from app.main import create_app
from app.portfolio import list_workspaces


@pytest.fixture
def portfolio(tmp_path):
    settings = Settings(
        _env_file=None, demo_mode=True, cookie_secure=False, data_dir=tmp_path,
        LLM_PROVIDER_BASE_URL="", LLM_PROVIDER_API_KEY="", LLM_PROVIDER_MODEL="",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        login(client)
        yield app, client


def login(client, username="demo", password="demo-local-only"):
    result = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert result.status_code == 200
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]


def add_user(app, username="peer", firm_id="demo-firm", role="lawyer"):
    with app.state.store.session() as session:
        user = User(username=username, name="Avukat " + username, firm_id=firm_id,
                    role=role, password_hash=hash_password("peer-long-password"))
        session.add(user)
        session.commit()
        return user.id


def customer(client, name="Müşteri A"):
    result = client.post("/api/v1/customers", json={"name": name, "notes": "Özel ilişki notu"})
    assert result.status_code == 201, result.text
    return result.json()


def workspace(client, title="Sözleşme incelemesi", customer_ids=None, **fields):
    result = client.post("/api/v1/workspaces", json={
        "title": title, "domain": "contracts", "customer_ids": customer_ids or [], **fields,
    })
    assert result.status_code == 201, result.text
    return result.json()


def ids(response):
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}


def test_many_to_many_customers_filter_or_and_preserve_existing_matters(portfolio):
    app, client = portfolio
    legacy = client.get("/api/v1/matters").json()[0]
    converted = client.get("/api/v1/workspaces/" + legacy["id"]).json()
    assert converted["id"] == legacy["id"]
    assert converted["document_count"] == 1 and len(converted["documents"]) == 1
    assert converted["customers"] == [] and converted["customer_ids"] == []
    assert converted["updated_at"] == converted["created_at"]
    a, b = customer(client), customer(client, "Müşteri B")
    shared = workspace(client, "Birlikte", [a["id"], b["id"], a["id"]])
    first = workspace(client, "A dosyası", [a["id"]])
    second = workspace(client, "B dosyası", [b["id"]])
    assert shared["customer_ids"] == [a["id"], b["id"]]
    assert shared["customers"] == [{"id": a["id"], "name": a["name"]},
                                    {"id": b["id"], "name": b["name"]}]
    assert ids(client.get("/api/v1/workspaces", params={"customer_ids": a["id"]})) == {
        shared["id"], first["id"],
    }
    assert ids(client.get("/api/v1/workspaces", params={"customer_ids": a["id"] + "," + b["id"]})) == {
        shared["id"], first["id"], second["id"],
    }
    assert client.get("/api/v1/workspaces?customer_ids=unavailable-id").json() == []
    counts = {row["id"]: row["workspace_count"] for row in client.get("/api/v1/customers").json()}
    assert counts == {a["id"]: 2, b["id"]: 2}
    assert client.get("/api/v1/matters/" + shared["id"]).json()["title"] == "Birlikte"
    with app.state.store.session() as session:
        assert session.get(Record, shared["id"]).kind == "matter"
        assert a["name"] not in session.get(Record, a["id"]).payload


@pytest.mark.parametrize("firm_id", ["demo-firm", "foreign-firm"])
def test_customer_metadata_and_tags_never_grant_workspace_access(portfolio, firm_id):
    app, client = portfolio
    a = customer(client)
    one = workspace(client, customer_ids=[a["id"]])
    peer = add_user(app, firm_id=firm_id, role="admin")
    login(client, "peer", "peer-long-password")
    assert client.get("/api/v1/customers").json() == []
    assert client.get("/api/v1/workspaces").json() == []
    assert client.get("/api/v1/workspaces", params={"customer_ids": a["id"]}).json() == []
    assert client.get("/api/v1/workspaces/" + one["id"]).status_code == 404
    own = workspace(client)
    for customer_id in (a["id"], "missing-id"):
        result = client.post("/api/v1/workspaces", json={
            "title": "Forbidden", "domain": "contracts", "customer_ids": [customer_id],
        })
        assert result.status_code == 404 and result.json()["detail"] == "Müşteri bulunamadı"
        result = client.put("/api/v1/workspaces/" + own["id"] + "/customers", json={
            "customer_ids": [customer_id], "revision": own["revision"],
        })
        assert result.status_code == 404 and result.json()["detail"] == "Müşteri bulunamadı"
    # Even an inconsistent cross-firm membership does not grant access.
    if firm_id == "foreign-firm":
        with app.state.store.session() as session:
            session.add(Membership(matter_id=one["id"], user_id=peer))
            session.commit()
        assert client.get("/api/v1/customers").json() == []
        assert client.get("/api/v1/workspaces/" + one["id"]).status_code == 404


def test_customer_counts_scope_to_visible_workspaces_and_unlinked_creator(portfolio):
    app, client = portfolio
    a, unlinked = customer(client), customer(client, "Bağlanmamış müşteri")
    shared = workspace(client, customer_ids=[a["id"]])
    private = workspace(client, customer_ids=[a["id"]])
    peer = add_user(app)
    with app.state.store.session() as session:
        session.add(Membership(matter_id=shared["id"], user_id=peer))
        session.commit()
    login(client, "peer", "peer-long-password")
    listed = client.get("/api/v1/customers").json()
    assert len(listed) == 1 and listed[0]["id"] == a["id"] and listed[0]["workspace_count"] == 1
    assert client.get("/api/v1/workspaces/" + private["id"]).status_code == 404
    peer_workspace = workspace(client, customer_ids=[a["id"]])
    assert client.get("/api/v1/customers").json()[0]["workspace_count"] == 2
    login(client)
    listed = {row["id"]: row for row in client.get("/api/v1/customers").json()}
    assert listed[a["id"]]["workspace_count"] == 2  # Private peer workspace is not counted.
    assert listed[unlinked["id"]]["workspace_count"] == 0
    assert client.get("/api/v1/workspaces/" + peer_workspace["id"]).status_code == 404


def test_replace_tags_requires_current_revision_and_does_not_change_membership(portfolio):
    app, client = portfolio
    a, b = customer(client), customer(client, "Müşteri B")
    item = workspace(client, customer_ids=[a["id"]])
    endpoint = "/api/v1/workspaces/" + item["id"] + "/customers"
    assert client.put(endpoint, json={"customer_ids": [b["id"]]}).status_code == 422
    changed = client.put(endpoint, json={"customer_ids": [b["id"]], "revision": item["revision"]})
    assert changed.status_code == 200
    assert changed.json()["customer_ids"] == [b["id"]]
    assert changed.json()["revision"] == item["revision"] + 1
    assert client.put(endpoint, json={"customer_ids": [], "revision": item["revision"]}).status_code == 409
    current = client.get("/api/v1/workspaces/" + item["id"]).json()
    assert current["customer_ids"] == [b["id"]]
    cleared = client.put(endpoint, json={"customer_ids": [], "revision": current["revision"]})
    assert cleared.status_code == 200 and cleared.json()["customers"] == []
    with app.state.store.session() as session:
        assert len(session.scalars(select(Membership).where(Membership.matter_id == item["id"])).all()) == 1


def test_comments_encrypted_append_only_and_workspace_scoped(portfolio):
    app, client = portfolio
    item = workspace(client)
    endpoint = "/api/v1/workspaces/" + item["id"] + "/comments"
    text = "Müşteri gizli yorumu 7219564."
    result = client.post(endpoint, json={"text": text})
    assert result.status_code == 201, result.text
    comment = result.json()
    assert comment["text"] == text and comment["author_name"] == "Demo Avukat"
    assert comment["created_at"]
    client.post(endpoint, json={"text": "Takip notu"})
    assert [row["text"] for row in client.get(endpoint).json()] == [text, "Takip notu"]
    detail = client.get("/api/v1/workspaces/" + item["id"]).json()
    assert detail["revision"] == item["revision"] + 2
    assert detail["updated_at"] >= comment["created_at"]
    assert detail["comments"] == client.get(endpoint).json()
    assert client.put(endpoint + "/" + comment["id"], json={"text": "replace"}).status_code in (404, 405)
    assert client.delete(endpoint + "/" + comment["id"]).status_code in (404, 405)
    with app.state.store.session() as session:
        row = session.get(Record, comment["id"])
        assert row.kind == "workspace_comment" and row.matter_id == item["id"]
        assert "7219564" not in row.payload and "Demo Avukat" not in row.payload
    add_user(app)
    login(client, "peer", "peer-long-password")
    assert client.get(endpoint).status_code == 404
    assert client.post(endpoint, json={"text": "Unauthorized"}).status_code == 404
    login(client)
    client.headers.pop("X-CSRF-Token")
    assert client.post(endpoint, json={"text": "No CSRF"}).status_code == 403


def test_date_filters_are_inclusive_in_turkiye_calendar_and_combine_with_customer(portfolio):
    app, client = portfolio
    a, b = customer(client), customer(client, "Müşteri B")
    left = workspace(client, "Gece yarısından önce", [a["id"]], relevant_date="2026-10-03")
    right = workspace(client, "Gece yarısından sonra", [a["id"]], relevant_date="2026-10-04")
    other = workspace(client, "Diğer müşteri", [b["id"]])
    with app.state.store.session() as session:
        for entry, stamp in ((left, "2026-10-03T20:59:59+00:00"),
                             (right, "2026-10-03T21:00:00+00:00"),
                             (other, "2026-10-04T12:00:00+00:00")):
            row = session.get(Record, entry["id"])
            row.created_at = stamp
            data = app.state.store.decode(row)
            data["updated_at"] = stamp
            app.state.store.update(row, data)
        session.commit()
    for field in ("created_at", "updated_at", "relevant_date"):
        params = {"customer_ids": a["id"], "date_from": "2026-10-04", "date_to": "2026-10-04",
                  "date_field": field}
        assert ids(client.get("/api/v1/workspaces", params=params)) == {right["id"]}
    assert ids(client.get("/api/v1/workspaces", params={
        "customer_ids": a["id"], "date_from": "2026-10-03", "date_to": "2026-10-04",
    })) == {left["id"], right["id"]}
    assert client.get("/api/v1/workspaces", params={
        "customer_ids": b["id"], "date_from": "2026-01-01", "date_field": "relevant_date",
    }).json() == []
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == "demo"))
        result = list_workspaces(app.state.store, session, user, [a["id"]],
                                 date(2026, 10, 4), date(2026, 10, 4), "updated_at")
        assert [row["id"] for row in result] == [right["id"]]


@pytest.mark.parametrize("params", [
    {"date_from": "20261004"}, {"date_from": "2026-02-30"}, {"date_to": ""},
    {"date_from": "2026-10-05", "date_to": "2026-10-04"}, {"date_field": "made_up"},
    {"customer_ids": "a" * 65},
])
def test_invalid_filters_are_rejected(portfolio, params):
    _, client = portfolio
    assert client.get("/api/v1/workspaces", params=params).status_code == 422


def test_archived_workspaces_do_not_leak_through_customers_or_comments(portfolio):
    app, client = portfolio
    a = customer(client)
    item = workspace(client, customer_ids=[a["id"]])
    peer = add_user(app)
    with app.state.store.session() as session:
        session.add(Membership(matter_id=item["id"], user_id=peer))
        session.get(Record, item["id"]).kind = "archived_matter"
        session.commit()
    assert item["id"] not in ids(client.get("/api/v1/workspaces"))
    assert client.get("/api/v1/customers").json()[0]["workspace_count"] == 0
    assert client.get("/api/v1/workspaces/" + item["id"]).status_code == 404
    assert client.get("/api/v1/workspaces/" + item["id"] + "/comments").status_code == 404
    login(client, "peer", "peer-long-password")
    assert client.get("/api/v1/customers").json() == []


def test_inconsistent_cross_firm_customer_and_file_records_are_not_exposed(portfolio):
    app, client = portfolio
    item = workspace(client)
    add_user(app, "foreign", "foreign-firm")
    with app.state.store.session() as session:
        foreign = session.scalar(select(User).where(User.username == "foreign"))
        secret = app.state.store.add(session, "customer", foreign, {"name": "Hidden customer"})
        app.state.store.add(session, "document", foreign, {"name": "Hidden file"}, item["id"])
        row = session.get(Record, item["id"])
        app.state.store.update(row, {**app.state.store.decode(row), "customer_ids": [secret.id]})
        session.commit()
    result = client.get("/api/v1/workspaces/" + item["id"]).json()
    assert result["customer_ids"] == [] and result["customers"] == []
    assert result["documents"] == [] and result["document_count"] == 0
    assert "Hidden" not in client.get("/api/v1/workspaces").text


@pytest.mark.parametrize("endpoint,body", [
    ("/customers", {"name": "   "}),
    ("/workspaces", {"title": "X", "domain": "contracts", "relevant_date": "20261004"}),
    ("/workspaces", {"title": "X", "domain": "contracts", "relevant_date": ""}),
])
def test_invalid_input_does_not_create_records(portfolio, endpoint, body):
    _, client = portfolio
    assert client.post("/api/v1" + endpoint, json=body).status_code == 422
