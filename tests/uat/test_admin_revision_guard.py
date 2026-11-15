"""Admin employee changes use the exact roles and account state reviewed."""

from test_delivered_workflows import uat  # noqa: F401 - pytest fixture
from test_firm_admin import create_employee, snapshot

from scripts.manage_users import operate

ADMIN = "/api/v1/firm-admin"


def test_employee_edit_rejects_stale_role_and_offline_account_decisions(uat):  # noqa: F811 - pytest fixture
    app, client, peer = uat
    actor = client.get("/api/v1/auth/me").json()["user"]
    employee = create_employee(client)
    proposed = client.post(ADMIN + "/roles", json={
        "name": "Synthetic review role", "permissions": ["system.read"],
    })
    assert proposed.status_code == 201
    role = proposed.json()
    endpoint = ADMIN + "/employees/" + employee["id"]
    draft = {
        "name": employee["name"], "active": True, "manager_id": None, "revision": employee["revision"],
        "role_ids": [role["id"]], "expected_active": True,
        "expected_role_revisions": {role["id"]: role["revision"]},
    }

    # The employee does not hold this role, so editing it does not advance
    # their employee revision. The original draft displayed weaker permissions.
    changed_role = client.put(ADMIN + "/roles/" + role["id"], json={
        "name": role["name"], "permissions": ["system.read", "firm.manage"], "revision": role["revision"],
    })
    assert changed_role.status_code == 200
    audit = client.get(ADMIN + "/changes").json()
    blocked = client.put(endpoint, json=draft)
    assert blocked.status_code == 409 and blocked.headers["Cache-Control"] == "no-store"
    assert blocked.json() == {
        "detail": "Çalışan veya seçili roller değişti; güncel kaydı açın.",
        "outcome": "revision_conflict", "target": "employee",
        "target_id": employee["id"], "current_revision": employee["revision"],
    }
    assert next(item for item in snapshot(client)["employees"] if item["id"] == employee["id"]) == employee
    assert client.get(ADMIN + "/changes").json() == audit
    denied = peer(employee["username"]).put(endpoint, json=draft)
    assert denied.status_code == 403
    assert set(denied.json()) == {"detail"}

    for invalid in ({}, {role["id"]: True}, {role["id"]: str(role["revision"])}, {role["id"]: 0}):
        assert client.put(endpoint, json={**draft, "expected_role_revisions": invalid}).status_code == 422
    assert client.put(endpoint, json={**draft, "expected_active": "true"}).status_code == 422

    draft["expected_role_revisions"] = {role["id"]: changed_role.json()["revision"]}
    saved = client.put(endpoint, json=draft)
    assert saved.status_code == 200
    fresh = saved.json()
    assert fresh["revision"] == employee["revision"] + 1
    assert fresh["role_ids"] == [role["id"]] and "firm.manage" in fresh["permissions"]
    changes = client.get(ADMIN + "/changes").json()["items"]
    update = next(item for item in changes if item["action"] == "firm_employee_updated")
    assert update["before"] == employee and update["after"] == fresh

    # The retained offline operator changes the account's active state
    # without advancing Employee.revision. An old form cannot reactivate it.
    assert operate(app.state.store, actor["id"], "deactivate", user_id=employee["id"])["sessions_revoked"]
    inactive = next(item for item in snapshot(client)["employees"] if item["id"] == employee["id"])
    assert not inactive["active"] and inactive["revision"] == fresh["revision"]
    stale = client.put(endpoint, json={**draft, "revision": fresh["revision"]})
    assert stale.status_code == 409 and stale.json()["current_revision"] == fresh["revision"]
    assert next(item for item in snapshot(client)["employees"] if item["id"] == employee["id"]) == inactive
    assert client.get(ADMIN + "/changes").json()["items"] == changes
