import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hash_password
from app.config import Settings
from app.db import Membership, Record, User
from app.main import create_app
from app.practice import practice_router


@pytest.fixture
def practice(tmp_path):
    app = create_app(Settings(
        _env_file=None, demo_mode=True, cookie_secure=False, data_dir=tmp_path,
        LLM_PROVIDER_BASE_URL="", LLM_PROVIDER_API_KEY="", LLM_PROVIDER_MODEL="",
    ))
    if not any(getattr(route, "path", "") == "/api/v1/playbooks" for route in app.routes):
        app.include_router(practice_router())
    with TestClient(app) as client:
        _login(client, "demo", "demo-local-only")
        matter = client.get("/api/v1/matters").json()[0]["id"]
        base = f"/api/v1/matters/{matter}"
        doc = client.get(base).json()["documents"][0]
        evidence = client.get(base + "/documents/" + doc["id"]).json()["passages"][1]["id"]
        facts = [client.post(base + "/facts", json={"text": text, "status": "alleged"}).json()
                 for text in ["Taraf teslimin yapıldığını beyan ediyor.", "Diğer taraf teslimi kabul etmiyor."]]
        yield app, client, matter, facts, evidence


def _login(client, username, password):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]


def _new_user(app, username, firm="demo-firm", role="lawyer", matter=None):
    with app.state.store.session() as session:
        user = User(username=username, name=username, firm_id=firm, role=role,
                    password_hash=hash_password("test-only-long-password"))
        session.add(user)
        session.flush()
        if matter:
            session.add(Membership(matter_id=matter, user_id=user.id))
        session.commit()
        return user.id


def _product(app, matter, **payload):
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == "demo"))
        product = app.state.store.add(session, "product", user,
                                      {"status": "reviewed", "claims": [], **payload}, matter)
        session.commit()
        return product.id


def _playbook(client, **overrides):
    data = {"title": "Müzakere kontrolü", "domain": "contracts", "text": "Kurum tercihlerini ayrı yazın.",
            "curation_status": "curated", "curation_note": "Küratör tarafından açıkça incelendi."}
    response = client.post("/api/v1/playbooks", json={**data, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def test_scenario_preserves_facts_and_keeps_immutable_versions(practice):
    app, client, matter, facts, _ = practice
    base = f"/api/v1/matters/{matter}"
    product_id = _product(app, matter)
    before = client.get(base).json()["facts"]
    payload = {"title": "Teslim varsayımı", "assumptions": ["Teslim kabulünün yapıldığı varsayılsın."],
               "fact_ids": [facts[0]["id"]], "notes": "Olguyu değiştirmez."}
    created = client.post(base + "/practice/scenarios", json=payload)
    assert created.status_code == 201, created.text
    scenario = created.json()
    assert scenario["authorship"] == "user" and scenario["legal_authority"] is False
    assert scenario["fact_snapshots"][0]["revision"] == facts[0]["revision"]
    assert client.get(base).json()["facts"] == before
    assert client.get(base + "/products/" + product_id).json()["status"] == "stale"
    with app.state.store.session() as session:
        original = session.get(Record, scenario["latest_version_id"])
        original_payload = original.payload
        assert payload["assumptions"][0] not in original_payload
    endpoint = base + "/practice/scenarios/" + scenario["id"] + "/versions"
    revised = client.post(endpoint, json={**payload, "assumptions": ["Teslim kabulü yapılmadığı varsayılsın."],
                                         "expected_revision": scenario["revision"],
                                         "change_note": "Alternatif varsayım kaydedildi."})
    assert revised.status_code == 201, revised.text
    assert revised.json()["version"] == 2
    history = client.get(endpoint).json()
    assert len(history) == 2
    assert history[1]["content"]["assumptions"] == payload["assumptions"]
    assert history[0]["immutable"] is True
    with app.state.store.session() as session:
        assert session.get(Record, scenario["latest_version_id"]).payload == original_payload
    assert client.get(base).json()["facts"] == before


def test_draft_history_conflicts_and_no_automatic_review(practice):
    _, client, matter, _, _ = practice
    base = f"/api/v1/matters/{matter}/practice/drafts"
    payload = {"title": "Hazırlık notu", "text": "Avukat tarafından yazılmış ilk metin."}
    created = client.post(base, json=payload).json()
    assert created["status"] == "working"
    endpoint = base + "/" + created["id"] + "/versions"
    assert client.post(endpoint, json=payload).status_code == 409
    assert client.post(endpoint, json={**payload, "expected_revision": 1}).status_code == 422
    updated = {**payload, "text": "İkinci metin.", "expected_revision": 1,
               "change_note": "İnceleme notu eklendi.", "review_note": "Karşı argüman araştırılmalı."}
    assert client.post(endpoint, json=updated).status_code == 201
    assert client.post(endpoint, json=updated).status_code == 409
    assert client.get(endpoint).json()[1]["content"]["text"] == payload["text"]
    assert client.post(base, json={**payload, "status": "approved"}).status_code == 422
    assert client.patch(endpoint, json={"text": "Geçmişi değiştir"}).status_code == 405


def test_contradictions_validate_distinct_same_matter_facts_and_resolution_history(practice):
    _, client, matter, facts, _ = practice
    base = f"/api/v1/matters/{matter}/practice/contradictions"
    payload = {"fact_ids": [fact["id"] for fact in facts], "reason": "Teslim konusunda farklı beyanlar var."}
    created = client.post(base, json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "open"
    assert len(created.json()["fact_snapshots"]) == 2
    assert client.post(base, json={**payload, "fact_ids": [facts[0]["id"]] * 2}).status_code == 422
    foreign = client.post("/api/v1/matters", json={"title": "Başka dosya", "domain": "employment"}).json()
    other_fact = client.post(f"/api/v1/matters/{foreign['id']}/facts",
                             json={"text": "Başka dosyanın olgusu", "status": "alleged"}).json()
    assert client.post(base, json={**payload, "fact_ids": [facts[0]["id"], other_fact["id"]]}).status_code == 404
    endpoint = base + "/" + created.json()["id"] + "/versions"
    resolved = client.post(endpoint, json={**payload, "status": "resolved", "reason": "Tutanakla açıklandı.",
                                          "expected_revision": 1, "change_note": "Avukat değerlendirmesi."})
    assert resolved.status_code == 201
    assert client.get(endpoint).json()[1]["content"]["status"] == "open"


def test_arguments_require_local_evidence_or_recorded_authority_candidates(practice):
    app, client, matter, _, evidence = practice
    base = f"/api/v1/matters/{matter}/practice/arguments"
    payload = {"issue": "Teslim kabulü", "position": "adverse", "text": "Kabulün kanıtlanması tartışmalı."}
    assert client.post(base, json=payload).status_code == 422
    assert client.post(base, json={**payload, "evidence_ids": ["invented"]}).status_code == 422
    accepted = client.post(base, json={**payload, "evidence_ids": [evidence]})
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["evidence_snapshots"][0]["id"] == evidence
    assert accepted.json()["legal_authority"] is False
    hit = {"passage_id": "public-passage", "authority_id": "authority-1", "source_version_id": "v1",
           "source_sha256": "source-hash", "review_status": "unreviewed"}
    product_id = _product(app, matter, authority_candidates={"hits": [hit]})
    ref = {"product_id": product_id, "passage_id": "public-passage"}
    result = client.post(base, json={**payload, "authority_refs": [ref]})
    assert result.status_code == 201, result.text
    assert result.json()["authority_snapshots"][0]["candidate_only"] is True
    assert result.json()["authority_snapshots"][0]["review_status"] == "unreviewed"
    assert client.post(base, json={**payload, "authority_refs": [{**ref, "passage_id": "invented"}]}).status_code == 422


def test_arguments_cannot_borrow_references_from_another_accessible_matter(practice):
    app, client, matter, _, evidence = practice
    other = client.post("/api/v1/matters", json={"title": "Diğer", "domain": "commercial"}).json()["id"]
    product_id = _product(app, matter, authority_candidates={"hits": [{"passage_id": "pub"}]})
    base = f"/api/v1/matters/{other}/practice/arguments"
    data = {"issue": "Ödeme", "text": "Kaynağı başka dosyadan alma.", "position": "supporting"}
    assert client.post(base, json={**data, "evidence_ids": [evidence]}).status_code == 422
    assert client.post(base, json={**data, "authority_refs": [{"product_id": product_id,
                                                               "passage_id": "pub"}]}).status_code == 404


@pytest.mark.parametrize("firm", ["demo-firm", "foreign-firm"])
def test_practice_records_and_history_require_actual_matter_membership(practice, firm):
    app, client, matter, _, _ = practice
    base = f"/api/v1/matters/{matter}/practice/drafts"
    body = {"title": "Özel çalışma", "text": "Yalnızca dosya üyelerine açık."}
    record = client.post(base, json=body).json()
    _new_user(app, "outsider", firm=firm, role="admin")
    _login(client, "outsider", "test-only-long-password")
    assert client.get(base).status_code == 404
    assert client.post(base, json=body).status_code == 404
    assert client.get(base + "/" + record["id"] + "/versions").status_code == 404
    assert client.post(base + "/" + record["id"] + "/versions",
                       json={**body, "expected_revision": 1, "change_note": "Yetkisiz değişiklik"}).status_code == 404
    assert client.get(f"/api/v1/matters/{matter}/practice/playbooks").status_code == 404


def test_csrf_origin_and_anonymous_boundaries(practice):
    _, client, matter, _, _ = practice
    base = f"/api/v1/matters/{matter}/practice/drafts"
    body = {"title": "Not", "text": "Taslak"}
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post(base, json=body).status_code == 403
    assert client.post(base, json=body, headers={"X-CSRF-Token": csrf,
                                                "Origin": "https://external.invalid"}).status_code == 403
    client.cookies.clear()
    assert client.get(base).status_code == 401
    assert client.get("/api/v1/playbooks").status_code == 401


def test_playbooks_require_explicit_curation_and_adoptions_pin_an_immutable_version(practice):
    app, client, matter, _, _ = practice
    draft = _playbook(client, curation_status="draft", curation_note="")
    endpoint = f"/api/v1/matters/{matter}/practice/playbooks"
    adoption = {"playbook_id": draft["id"], "version_id": draft["latest_version_id"],
                "purpose": "Müzakere hazırlığında kullanılacak."}
    assert client.post(endpoint, json=adoption).status_code == 409
    body = {"title": draft["title"], "domain": draft["domain"], "text": draft["text"],
            "curation_status": "curated", "curation_note": "İçerik gözden geçirildi.",
            "expected_revision": 1, "change_note": "Küratör incelemesi tamamlandı."}
    curated = client.post(f"/api/v1/playbooks/{draft['id']}/versions", json=body)
    assert curated.status_code == 201, curated.text
    product = _product(app, matter)
    adoption["version_id"] = curated.json()["latest_version_id"]
    adopted = client.post(endpoint, json=adoption)
    assert adopted.status_code == 201, adopted.text
    assert adopted.json()["classification"] == "firm_preference"
    assert adopted.json()["legal_authority"] is False
    assert client.get(f"/api/v1/matters/{matter}/products/{product}").json()["status"] == "stale"
    changed = client.post(f"/api/v1/playbooks/{draft['id']}/versions", json={**body,
                          "text": "Yeni kurum tercihi.", "expected_revision": 2})
    assert changed.status_code == 201
    assert client.get(endpoint).json()[0]["text"] == draft["text"]
    assert client.get(endpoint).json()[0]["version"] == 2


def test_playbook_curator_and_firm_isolation(practice):
    app, client, matter, _, _ = practice
    guide = _playbook(client)
    _new_user(app, "member", matter=matter)
    _login(client, "member", "test-only-long-password")
    assert client.get("/api/v1/playbooks").json()[0]["id"] == guide["id"]
    payload = {"title": "Rehber", "domain": "general", "text": "Açık insan katkısı."}
    assert client.post("/api/v1/playbooks", json=payload).status_code == 403
    assert client.post(f"/api/v1/playbooks/{guide['id']}/versions",
                       json={**payload, "expected_revision": 1, "change_note": "Yetkisiz düzenleme"}).status_code == 403
    adoption = {"playbook_id": guide["id"], "version_id": guide["latest_version_id"], "purpose": "Dosya hazırlığı"}
    assert client.post(f"/api/v1/matters/{matter}/practice/playbooks", json=adoption).status_code == 201
    _new_user(app, "foreign", firm="another-firm", role="admin")
    _login(client, "foreign", "test-only-long-password")
    assert client.get("/api/v1/playbooks").json() == []
    assert client.get(f"/api/v1/playbooks/{guide['id']}/versions").status_code == 404
    own = client.post("/api/v1/matters", json={"title": "Kendi dosyası", "domain": "contracts"}).json()["id"]
    assert client.post(f"/api/v1/matters/{own}/practice/playbooks", json=adoption).status_code == 404


def test_playbook_version_must_belong_to_selected_playbook_and_matter_requires_membership(practice):
    app, client, matter, _, _ = practice
    first, second = _playbook(client), _playbook(client, title="Başka rehber")
    endpoint = f"/api/v1/matters/{matter}/practice/playbooks"
    assert client.post(endpoint, json={"playbook_id": first["id"], "version_id": second["latest_version_id"],
                                      "purpose": "Yanlış sürüm"}).status_code == 404
    _new_user(app, "same-firm-admin", role="admin")
    _login(client, "same-firm-admin", "test-only-long-password")
    assert client.post(endpoint, json={"playbook_id": first["id"], "version_id": first["latest_version_id"],
                                      "purpose": "Üyelik yok"}).status_code == 404


def test_revoked_membership_and_foreign_kind_cannot_read_version_history(practice):
    app, client, matter, _, _ = practice
    base = f"/api/v1/matters/{matter}/practice"
    draft = client.post(base + "/drafts", json={"title": "Not", "text": "Metin"}).json()
    assert client.get(base + f"/scenarios/{draft['id']}/versions").status_code == 404
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == "demo"))
        session.delete(session.get(Membership, (matter, user.id)))
        session.commit()
    assert client.get(base + f"/drafts/{draft['id']}/versions").status_code == 404


@pytest.mark.parametrize("kind,payload", [
    ("scenarios", {"title": "Varsayım", "assumptions": []}),
    ("scenarios", {"title": "Varsayım", "assumptions": [" "]}),
    ("drafts", {"title": "Not", "text": "x" * 30001}),
    ("drafts", {"title": "Not", "text": "Metin", "legal_authority": True}),
    ("contradictions", {"fact_ids": ["1", "2"], "status": "auto_resolved", "reason": "Yok"}),
])
def test_bounded_strict_inputs(practice, kind, payload):
    _, client, matter, _, _ = practice
    assert client.post(f"/api/v1/matters/{matter}/practice/{kind}", json=payload).status_code == 422


def test_list_bounds_and_history_pages(practice):
    _, client, matter, _, _ = practice
    base = f"/api/v1/matters/{matter}/practice/drafts"
    payload = {"title": "Not", "text": "Birinci metin"}
    created = client.post(base, json=payload).json()
    endpoint = base + f"/{created['id']}/versions"
    assert client.post(endpoint, json={**payload, "expected_revision": 1,
                                      "change_note": "Metin değişti", "text": "İkinci metin"}).status_code == 201
    assert client.get(endpoint + "?limit=1").json()[0]["version"] == 2
    assert client.get(endpoint + "?limit=1&offset=1").json()[0]["version"] == 1
    assert client.get(base + "?limit=101").status_code == 422
    assert client.get(endpoint + "?offset=-1").status_code == 422
