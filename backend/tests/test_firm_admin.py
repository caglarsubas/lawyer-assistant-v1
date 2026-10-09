"""Synthetic accounts only; no source approval or live provider calls."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.db import Employee, EmployeeRole, FirmRole, LoginSession, Membership, Record, User
from app.firm_rbac import FirmAuthorization, route_permissions
from app.main import create_app

PASSWORD = "synthetic-new-lawyer-12345"


@pytest.fixture
def firm(tmp_path):
    app = create_app(Settings(_env_file=None, demo_mode=True, cookie_secure=False, data_dir=tmp_path,
                              LLM_PROVIDER_BASE_URL="", LLM_PROVIDER_API_KEY="", LLM_PROVIDER_MODEL=""))
    with TestClient(app) as client:
        login(client)
        yield app, client


def login(client, username="demo", password="demo-local-only"):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response.json()["user"]


def snapshot(client):
    response = client.get("/api/v1/firm-admin")
    assert response.status_code == 200, response.text
    return response.json()


def create_employee(client, name="peer", role="Avukat", manager=None):
    role_id = next(item["id"] for item in snapshot(client)["roles"] if item["name"] == role)
    response = client.post("/api/v1/firm-admin/employees", json={
        "username": name, "name": name, "password": PASSWORD, "role_ids": [role_id], "manager_id": manager,
    })
    assert response.status_code == 201, response.text
    return response.json()


def edit(client, employee, **values):
    return client.put("/api/v1/firm-admin/employees/" + employee["id"], json={
        **{key: employee[key] for key in ("name", "active", "manager_id", "role_ids", "revision")}, **values,
    })


def test_migration_keeps_credentials_memberships_and_source_status(firm):
    app, client = firm
    with app.state.store.session() as session:
        user = session.scalar(select(User))
        password, members = user.password_hash, session.scalars(select(Membership)).all()
        assert session.get(Employee, user.id).manager_id is None
        assert len(list(session.scalars(select(EmployeeRole)))) == 1
    a, b = snapshot(client), snapshot(client)
    assert a == b and a["hierarchy_grants_access"] is False
    assert a["content_access"] == "explicit_assignments_only"
    with app.state.store.session() as session:
        assert session.get(User, user.id).password_hash == password
        assert {(m.matter_id, m.user_id) for m in session.scalars(select(Membership))} == {
            (m.matter_id, m.user_id) for m in members}
        assert not list(session.scalars(select(Record).where(Record.kind == "source_review")))


def test_administrator_without_assignment_cannot_see_cases_or_documents(firm):
    app, client = firm
    case = client.get("/api/v1/matters").json()[0]
    administrator = create_employee(client, "config", "Büro yöneticisi (yapılandırma)")
    user = login(client, "config", PASSWORD)
    assert user["permissions"] == ["firm.manage", "system.read"]
    assert len(snapshot(client)["employees"]) == 2
    for path in ("/matters", "/customers", "/workspaces", "/matters/" + case["id"]):
        assert client.get("/api/v1" + path).status_code == 403
    with app.state.store.session() as session:
        assert not list(session.scalars(select(Membership).where(Membership.user_id == administrator["id"])))


def test_manager_relationship_never_grants_case_content(firm):
    app, client = firm
    manager = create_employee(client, "manager")
    child = create_employee(client, "child", manager=manager["id"])
    login(client, "child", PASSWORD)
    case = client.post("/api/v1/matters", json={"title": "Secret subordinate matter", "domain": "contracts"}).json()
    login(client, "manager", PASSWORD)
    assert client.get("/api/v1/matters").json() == []
    assert client.get("/api/v1/matters/" + case["id"]).status_code == 404
    assert client.get("/api/v1/firm-admin").status_code == 403
    assert child["manager_id"] == manager["id"]


@pytest.mark.parametrize("self_link", [True, False])
def test_reject_self_reporting_and_cycles_atomically(firm, self_link):
    app, client = firm
    a = create_employee(client, "a")
    b = create_employee(client, "b", manager=a["id"])
    response = edit(client, a, manager_id=a["id"] if self_link else b["id"])
    assert response.status_code == 422
    with app.state.store.session() as session:
        assert session.get(Employee, a["id"]).manager_id is None
        assert session.get(Employee, a["id"]).revision == a["revision"]


def test_cross_firm_employee_manager_and_role_are_denied(firm):
    app, client = firm
    a = create_employee(client)
    with app.state.store.session() as session:
        foreign = User(id="foreign", username="foreign", name="foreign", firm_id="other", role="admin",
                       password_hash="never-used")
        session.add(foreign)
        role = FirmRole(id="foreign-role", firm_id="other", name="other", permissions='["firm.manage"]')
        session.add(role)
        session.commit()
    assert edit(client, a, manager_id="foreign").status_code == 404
    assert edit(client, a, role_ids=["foreign-role"]).status_code == 404
    assert client.put("/api/v1/firm-admin/employees/foreign", json={
        "name": "replacement", "active": True, "role_ids": [], "manager_id": None, "revision": 1,
    }).status_code == 404
    assert "foreign" not in json.dumps(snapshot(client))


@pytest.mark.parametrize("permissions", [["network.all"], ["matter.write"], ["matter.read", "matter.read"]])
def test_invalid_permission_catalog_and_dependencies_denied(firm, permissions):
    _, client = firm
    assert client.post("/api/v1/firm-admin/roles", json={"name": "invalid", "permissions": permissions}).status_code == 422


def test_readonly_custom_role_enforced_on_direct_api_and_empty_roles_fail_closed(firm):
    app, client = firm
    case = client.get("/api/v1/matters").json()[0]
    target = create_employee(client)
    role = client.post("/api/v1/firm-admin/roles", json={
        "name": "Inspect only", "permissions": ["matter.read", "portfolio.read", "system.read"],
    }).json()
    assert edit(client, target, role_ids=[role["id"]]).status_code == 200
    with app.state.store.session() as session:
        session.add(Membership(matter_id=case["id"], user_id=target["id"]))
        session.commit()
    login(client, "peer", PASSWORD)
    assert client.get("/api/v1/matters/" + case["id"]).status_code == 200
    assert client.post("/api/v1/matters/" + case["id"] + "/facts", json={"text": "x", "status": "alleged"}).status_code == 403
    assert client.post("/api/v1/matters", json={"title": "x", "domain": "contracts"}).status_code == 403
    assert client.get("/api/v1/public-sources").status_code == 403
    login(client)
    target = next(item for item in snapshot(client)["employees"] if item["id"] == target["id"])
    assert edit(client, target, role_ids=[]).status_code == 200
    login(client, "peer", PASSWORD)
    assert client.get("/api/v1/matters/" + case["id"]).status_code == 403


def test_role_edits_revoke_sessions_increment_employee_revision_and_audit_no_secrets(firm):
    app, client = firm
    target = create_employee(client)
    role = client.post("/api/v1/firm-admin/roles", json={"name": "R", "permissions": ["system.read"]}).json()
    target = edit(client, target, role_ids=[role["id"]]).json()
    peer = TestClient(app)
    try:
        login(peer, "peer", PASSWORD)
        assert peer.get("/api/v1/auth/me").status_code == 200
        response = client.put("/api/v1/firm-admin/roles/" + role["id"], json={
            "name": "R", "permissions": [], "revision": role["revision"],
        })
        assert response.status_code == 200
        assert peer.get("/api/v1/auth/me").status_code == 401
    finally:
        peer.close()
    current = next(item for item in snapshot(client)["employees"] if item["id"] == target["id"])
    assert current["revision"] == target["revision"] + 1
    changes = client.get("/api/v1/firm-admin/changes").json()
    assert {item["action"] for item in changes["items"]} >= {"firm_role_updated", "firm_employee_created"}
    assert PASSWORD not in json.dumps(changes)
    with app.state.store.session() as session:
        assert not list(session.scalars(select(LoginSession).where(LoginSession.user_id == target["id"])))
        for record in session.scalars(select(Record).where(Record.kind == "firm_change")):
            assert "peer" not in record.payload


def test_conflicts_last_administrator_starter_roles_and_credentials(firm):
    _, client = firm
    data = snapshot(client)
    admin = data["employees"][0]
    assert edit(client, admin, role_ids=[]).status_code == 409
    peer = create_employee(client)
    assert edit(client, peer, name="Updated").status_code == 200
    assert edit(client, peer, name="Older stale edit").status_code == 409
    role = next(role for role in data["roles"] if role["name"] == "Avukat")
    assert client.put("/api/v1/firm-admin/roles/" + role["id"], json={
        "name": "Overwrite", "permissions": [], "revision": role["revision"],
    }).status_code == 409
    duplicate = client.post("/api/v1/firm-admin/employees", json={
        "username": "peer", "name": "Overwrite", "password": PASSWORD, "role_ids": [],
    })
    assert duplicate.status_code == 409
    invalid = client.post("/api/v1/firm-admin/employees", json={
        "username": "secret", "name": "secret", "password": "secret", "role_ids": [],
    })
    assert '"input"' not in invalid.text
    login(client, "peer", PASSWORD)


def test_deactivation_and_manager_reassignment(firm):
    _, client = firm
    manager = create_employee(client, "manager")
    child = create_employee(client, "child", manager=manager["id"])
    assert edit(client, manager, active=False).status_code == 409
    assert edit(client, child, manager_id=None).status_code == 200
    assert edit(client, manager, active=False).status_code == 200
    assert client.post("/api/v1/auth/login", json={"username": "manager", "password": PASSWORD}).status_code == 401
    manager = next(item for item in snapshot(client)["employees"] if item["id"] == manager["id"])
    assert edit(client, manager, active=True).status_code == 200
    login(client, "manager", PASSWORD)


def test_corrupt_role_reference_fails_closed(firm):
    app, client = firm
    target = create_employee(client)
    with app.state.store.session() as session:
        role = session.scalar(select(FirmRole).join(EmployeeRole, EmployeeRole.role_id == FirmRole.id)
                              .where(EmployeeRole.user_id == target["id"]))
        role.permissions = '["matter.read", "unsupported"]'
        session.commit()
    assert login(client, "peer", PASSWORD)["permissions"] == []
    assert client.get("/api/v1/matters").status_code == 403


def test_sensitive_routes_have_additional_action_gates():
    assert "matter.export" in route_permissions("/api/v1/matters/id/analyses/a/export", "GET")
    assert "matter.review" in route_permissions("/api/v1/matters/id/analyses/a/reviews", "POST")
    assert "matter.lifecycle" in route_permissions("/api/v1/matters/id/legal-holds", "POST")
    assert route_permissions("/api/v1/firm-admin/roles", "POST") == {"firm.manage"}


def test_revoked_worker_write_permission_blocks_publication_with_membership_retained(firm):
    from fastapi import HTTPException

    from app.firm_rbac import guard_job_write

    app, client = firm
    target = create_employee(client)
    case = client.get('/api/v1/matters').json()[0]
    with app.state.store.session() as session:
        owner = session.get(User, target['id'])
        session.add(Membership(matter_id=case['id'], user_id=owner.id))
        run = app.state.store.add(session, 'research', owner, {'synthetic': True}, case['id'])
        session.commit()
        run_id = run.id
    writes = []

    @guard_job_write
    def publication(application, ident):
        writes.append(ident)

    publication(app, run_id)
    role = next(item for item in snapshot(client)['roles'] if item['name'] == 'Salt okuma')
    assert edit(client, target, role_ids=[role['id']]).status_code == 200
    with pytest.raises(HTTPException) as failure:
        publication(app, run_id)
    assert failure.value.status_code == 403 and writes == [run_id]
    with app.state.store.session() as session:
        assert session.get(Membership, (case['id'], target['id'])) is not None


def test_configuration_guide_reads_no_portfolio_or_provider(firm, monkeypatch):
    app, client = firm
    create_employee(client, 'config-guide', 'Büro yöneticisi (yapılandırma)')
    login(client, 'config-guide', PASSWORD)
    monkeypatch.setattr(app.state.provider, 'generate', lambda *args: pytest.fail('No model in configuration guide'))
    response = client.post('/api/v1/assistant/respond', json={'mode': 'guide', 'context': {'page': 'firm-admin'}})
    assert response.status_code == 200
    assert response.json()['provider_used'] is False and response.json()['sources'] == []
    denied = client.post('/api/v1/assistant/respond', json={'mode': 'daily', 'context': {'page': 'firm-admin'}})
    assert denied.status_code == 403


def test_local_authorization_lock_coordinates_active_request_with_change(firm):
    import threading

    app, _ = firm
    locks = FirmAuthorization(app.state.store.engine)
    started, admitted = threading.Event(), threading.Event()

    def change():
        started.set()
        with locks.guard("demo-firm", exclusive=True):
            admitted.set()

    with locks.guard("demo-firm"):
        worker = threading.Thread(target=change)
        worker.start()
        assert started.wait(1)
        assert not admitted.wait(0.05)
    worker.join(1)
    assert admitted.is_set() and not worker.is_alive()
