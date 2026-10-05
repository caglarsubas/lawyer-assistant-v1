import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update
from test_public_sources import source as source_fixture
from test_source_reviews import another_client, assess, assign, revoke
from test_workspace import workspace as workspace_fixture

from app import provision_mappings
from app.db import Record, User
from app.provision_mapping_models import ProvisionMappingEvent, ProvisionMappingHead
from app.public_sources import PublicSourceStore

source = source_fixture
workspace = workspace_fixture
TEXT = "SENTETİK TEST METNİ\r\nMADDE 1 — Birinci test hükmü.\r\nTürkçe ıİ ⚖️.\r\nGEÇİCİ MADDE 1 — Test geçiş metni.\r\n"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def mapping(workspace, source):
    app, client, _ = workspace
    store, inputs, _, locators = source
    inputs["text_path"].write_bytes(TEXT.encode())
    locators["text_sha256"] = sha(TEXT)
    locators["passages"] = [{"id": "p1", "start": 0, "end": len(TEXT), "text_sha256": sha(TEXT), "locator": "Test 1"}]
    inputs["locators_path"].write_text(json.dumps(locators), encoding="utf-8")
    source_id = store.import_package(**inputs)["id"]
    app.state.settings.public_source_dir = store.root
    base = f"/api/v1/public-sources/{source_id}"
    return app, client, store, source_id, base


def claim(mapping):
    return assign(mapping[1], mapping[4] + "/review")


def ready(mapping, *, uses=None):
    client, base = mapping[1], mapping[4]
    assert claim(mapping).status_code == 200
    for revision, category in enumerate(("rights", "source_identity", "extraction", "legal"), start=1):
        options = {"permitted_uses": uses or ["local_processing", "internal_display"]} if category == "rights" else {}
        assert assess(client, base + "/review", revision, category, **options).status_code == 200


def propose(mapping, revision=0, source_revision=1, **changes):
    _, client, _, _, base = mapping
    candidate = client.get(base + "/provision-candidates").json()["items"][0]
    return client.post(base + "/provision-mappings", json={
        "expected_revision": revision, "expected_source_review_revision": source_revision,
        "candidate_id": candidate["id"], "start": candidate["proposed_span"]["start"],
        "end": candidate["proposed_span"]["end"], "kind": candidate["kind"], "label": candidate["label"],
        "rationale": "Test metnindeki madde başlığı elle incelenecek", **changes})


def review(mapping, identifier, revision=1, source_revision=5, decision="accepted", **changes):
    _, client, _, _, base = mapping
    candidate = client.get(base + "/provision-candidates").json()["items"][0]
    resolution = {"start": candidate["proposed_span"]["start"], "end": candidate["proposed_span"]["end"],
                  "instrument_ref": "Synthetic test instrument", "provision_ref": "Synthetic test article 1",
                  "provision_version_ref": "Synthetic test article v1", "text_role": "unknown",
                  "valid_from": None, "valid_until": None}
    return client.post(base + f"/provision-mappings/{identifier}/review", json={
        "expected_revision": revision, "expected_source_review_revision": source_revision,
        "decision": decision, "rationale": "Synthetic test review only", "evidence_refs": [
            {"reference": "Test support reference", "sha256": "a" * 64}],
        "resolution": resolution if decision == "accepted" else None, **changes})


def counts(app):
    with app.state.store.session() as session:
        return tuple(session.scalar(select(func.count()).select_from(model))
                     for model in (ProvisionMappingHead, ProvisionMappingEvent))


def test_reads_are_virtual_exact_and_side_effect_free(mapping):
    app, client, store, source_id, base = mapping
    original = {path.name: path.read_bytes() for path in (store.root / source_id).iterdir()}
    state = client.get(base + "/provision-mappings").json()
    assert state["revision"] == state["source_review_revision"] == 0
    assert state["items"] == state["history"] == []
    assert state["assigned_to"] is None and not state["handoff_ready"]
    candidates = client.get(base + "/provision-candidates").json()
    assert candidates["total"] == 2 and candidates["items"][0]["status"] == "machine_proposed"
    span = client.get(base + "/provision-span", params={"start": 0, "end": len(TEXT)}).json()
    assert span["span"] == {"start": 0, "end": len(TEXT), "text": TEXT, "sha256": sha(TEXT)}
    assert span["passage_ids"] == ["p1"] and span["non_whitespace_covered"]
    assert counts(app) == (0, 0)
    assert original == {path.name: path.read_bytes() for path in (store.root / source_id).iterdir()}


def test_full_mapping_review_handoff_is_encrypted_and_never_publication(mapping):
    app, client, store, source_id, base = mapping
    ready(mapping)
    with app.state.store.session() as session:
        records_before = session.scalar(select(func.count()).select_from(Record))
    proposed = propose(mapping, source_revision=5)
    assert proposed.status_code == 200, proposed.text
    item = proposed.json()["items"][0]
    assert item["status"] == "machine_proposed" and item["reviewed_source_revision"] is None
    response = review(mapping, item["id"])
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["revision"] == 2 and state["handoff_ready"] and not state["publication_eligible"]
    assert state["items"][0]["resolution"]["valid_from"] is None
    assert state["items"][0]["reviewed_source_revision"] == 5
    assert not state["items"][0]["stale"]
    assert client.get(base + "/provision-mappings").json() == state
    with app.state.store.session() as session:
        head = session.scalar(select(ProvisionMappingHead))
        for row in [head, *session.scalars(select(ProvisionMappingEvent))]:
            assert "Synthetic test" not in row.payload and "Demo Avukat" not in row.payload
            assert app.state.store.decode(row)["source_binding"]["source_id"] == source_id
        assert session.scalar(select(func.count()).select_from(Record)) == records_before
    export = client.get(base + "/provision-mappings/export")
    assert export.status_code == 200 and export.headers["content-disposition"].startswith("attachment;")
    assert export.headers["cache-control"] == "no-store"
    assert export.json()["mappings"] == state
    assert export.json()["signed"] is False and export.json()["publication_eligible"] is False
    assert export.json()["confidentiality"] == "firm_confidential"
    assert store.detail(source_id)["publication_status"] == "staged"


def test_all_source_review_changes_stale_and_reaffirmation_is_explicit(mapping):
    _, client, _, _, base = mapping
    ready(mapping)
    identifier = propose(mapping, source_revision=5).json()["items"][0]["id"]
    assert review(mapping, identifier).status_code == 200
    assert assess(client, base + "/review", 5, "legal").status_code == 200
    state = client.get(base + "/provision-mappings").json()
    assert state["source_review_revision"] == 6 and state["items"][0]["stale"]
    assert not state["handoff_ready"] and state["revision"] == 2
    assert review(mapping, identifier, 2, 5).status_code == 409
    reaffirmed = review(mapping, identifier, 2, 6)
    assert reaffirmed.status_code == 200 and reaffirmed.json()["handoff_ready"]
    assert assess(client, base + "/review", 6, "legal", "rejected").status_code == 200
    assert review(mapping, identifier, 3, 7).status_code == 409
    rejected = review(mapping, identifier, 3, 7, decision="needs_changes", evidence_refs=[])
    assert rejected.status_code == 200
    assert rejected.json()["items"][0]["resolution"] is None
    assert rejected.json()["history"][1]["snapshot"]["resolution"] is not None


@pytest.mark.parametrize("approved,uses", [(False, None), (True, ["storage"]), (True, ["local_processing"])])
def test_acceptance_requires_four_reviews_and_local_processing_display(mapping, approved, uses):
    if approved:
        ready(mapping, uses=uses)
    else:
        claim(mapping)
    source_revision = 5 if approved else 1
    identifier = propose(mapping, source_revision=source_revision).json()["items"][0]["id"]
    assert review(mapping, identifier, source_revision=source_revision).status_code == 409
    assert counts(mapping[0]) == (1, 1)


def test_owner_required_admin_cannot_override_and_both_revisions_conflict(mapping):
    app, client, _, _, base = mapping
    assert propose(mapping, source_revision=0).status_code == 409
    claim(mapping)
    assert propose(mapping, source_revision=0).status_code == 409
    owner = another_client(app, username="new-owner")
    assert propose((app, owner, *mapping[2:])).status_code == 409
    item = propose(mapping).json()["items"][0]
    assert propose(mapping).status_code == 409
    assert propose(mapping, 1).status_code == 409  # duplicate span
    assert review((app, owner, *mapping[2:]), item["id"], source_revision=1, decision="rejected").status_code == 409
    assert assign(client, base + "/review", 1, "release").status_code == 200
    assert review(mapping, item["id"], source_revision=2, decision="rejected").status_code == 409
    assert assign(owner, base + "/review", 2).status_code == 200
    assert review((app, owner, *mapping[2:]), item["id"], source_revision=3, decision="rejected").status_code == 200


def test_firm_selections_notes_and_export_do_not_leak(mapping):
    app, client, _, _, base = mapping
    claim(mapping)
    propose(mapping, rationale="Private first firm note")
    foreign = another_client(app, username="foreign", firm="other-firm", role="admin")
    foreign_mapping = (app, foreign, *mapping[2:])
    state = foreign.get(base + "/provision-mappings").json()
    assert state["revision"] == 0 and state["items"] == []
    assert "Private first firm" not in foreign.get(base + "/provision-mappings/export").text
    claim(foreign_mapping)
    propose(foreign_mapping, rationale="Private second firm note")
    assert "Private second firm" not in client.get(base + "/provision-mappings/export").text
    assert counts(app) == (2, 2)


@pytest.mark.parametrize("changes", [
    {"start": True}, {"end": 1}, {"end": 20001}, {"candidate_id": "f" * 64}, {"label": "wrong"},
    {"kind": "additional_article"}, {"start": len(TEXT) - 2, "end": len(TEXT), "candidate_id": None},
    {"rationale": " "}, {"expected_revision": True}, {"expected_source_review_revision": True},
    {"reviewer": {"id": "fake"}}, {"source_id": "f" * 64}, {"signature": "fake"},
    {"text": "forged"}, {"label": "hello\nworld"},
])
def test_proposal_rejects_unbound_or_invalid_inputs(mapping, changes):
    claim(mapping)
    assert propose(mapping, **changes).status_code == 422
    assert counts(mapping[0]) == (0, 0)


def test_manual_exact_span_supported_but_does_not_infer_identity(mapping):
    claim(mapping)
    response = propose(mapping, candidate_id=None, start=0, end=18, label="İnceleme konusu")
    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["candidate_id"] is None and item["resolution"] is None
    assert item["span"]["text"] == TEXT[:18]
    assert not response.json()["handoff_ready"]


@pytest.mark.parametrize("changes", [{"evidence_refs": []}, {"resolution": None},
                                     {"reviewer": {"id": "fake"}}, {"decision": "publish"},
                                     {"evidence_refs": [{"reference": "ref", "sha256": "A" * 64}]}])
def test_review_strict_fields(mapping, changes):
    ready(mapping)
    identifier = propose(mapping, source_revision=5).json()["items"][0]["id"]
    assert review(mapping, identifier, **changes).status_code == 422


@pytest.mark.parametrize("changes", [
    {"valid_from": "20250101"}, {"valid_from": "2025-02-30"},
    {"valid_from": "2025-02-01", "valid_until": "2025-01-01"}, {"text_role": "binding_law"},
    {"instrument_ref": ""}, {"provision_ref": "bad\nreference"}, {"start": 0, "end": 18},
    {"start": True}, {"end": len(TEXT) + 1}, {"resolved_graph_id": "fake"},
])
def test_resolution_validates_dates_refs_roles_bounds_and_heading(mapping, changes):
    ready(mapping)
    identifier = propose(mapping, source_revision=5).json()["items"][0]["id"]
    candidate = mapping[1].get(mapping[4] + "/provision-candidates").json()["items"][0]
    resolution = {"start": candidate["proposed_span"]["start"], "end": candidate["proposed_span"]["end"],
                  "instrument_ref": "Test instrument", "provision_ref": "Test provision",
                  "provision_version_ref": "Test exact version", "text_role": "unknown",
                  "valid_from": None, "valid_until": None, **changes}
    assert review(mapping, identifier, resolution=resolution).status_code == 422


@pytest.mark.parametrize("endpoint,method", [("/provision-candidates", "get"), ("/provision-mappings", "get"),
                                             ("/provision-mappings/export", "get"), ("/provision-mappings", "post"),
                                             ("/provision-span?start=0&end=5", "get")])
def test_role_denied_before_public_source_read(mapping, monkeypatch, endpoint, method):
    app, client, _, _, base = mapping
    with app.state.store.session() as session:
        session.scalar(select(User).where(User.username == "demo")).role = "lawyer"
        session.commit()
    monkeypatch.setattr(PublicSourceStore, "verified_package", lambda *_: pytest.fail("Must not read source"))
    assert getattr(client, method)(base + endpoint, **({"json": {}} if method == "post" else {})).status_code == 403


@pytest.mark.parametrize("kind,status", [("inactive", 401), ("role", 403), ("firm", 401), ("session", 401),
                                         ("expired", 401), ("csrf", 403)])
def test_revocation_during_source_verification_denies_write(mapping, monkeypatch, kind, status):
    app, client, _, _, base = mapping
    claim(mapping)
    original = PublicSourceStore.verified_package
    candidate = client.get(base + "/provision-candidates").json()["items"][0]

    def verify_then_revoke(store, source_id):
        package = original(store, source_id)
        revoke(app, kind)
        return package

    monkeypatch.setattr(PublicSourceStore, "verified_package", verify_then_revoke)
    response = client.post(base + "/provision-mappings", json={
        "expected_revision": 0, "expected_source_review_revision": 1, "candidate_id": candidate["id"],
        "start": candidate["proposed_span"]["start"], "end": candidate["proposed_span"]["end"],
        "kind": candidate["kind"], "label": candidate["label"], "rationale": "Test revision boundary"})
    assert response.status_code == status and counts(app) == (0, 0)


@pytest.mark.parametrize("kind,status", [("inactive", 401), ("role", 403), ("firm", 401), ("session", 401),
                                         ("expired", 401), ("csrf", 403), ("downgrade", 403)])
def test_identity_rechecked_before_commit(mapping, monkeypatch, kind, status):
    app = mapping[0]
    claim(mapping)
    original = provision_mappings._transition

    def transition_then_revoke(*args):
        result = original(*args)
        revoke(app, kind)
        return result

    monkeypatch.setattr(provision_mappings, "_transition", transition_then_revoke)
    assert propose(mapping).status_code == status
    assert counts(app) == (0, 0)


def test_source_review_changes_before_mapping_commit_roll_back(mapping, monkeypatch):
    app, client, _, _, base = mapping
    claim(mapping)
    original = provision_mappings._transition

    def transition_then_release(*args):
        result = original(*args)
        assert assign(client, base + "/review", 1, "release").status_code == 200
        return result

    monkeypatch.setattr(provision_mappings, "_transition", transition_then_release)
    assert propose(mapping).status_code == 409
    assert counts(app) == (0, 0)


@pytest.mark.parametrize("endpoint", ["/provision-mappings", "/provision-mappings/export"])
def test_read_detects_source_revision_change(mapping, monkeypatch, endpoint):
    _, client, _, _, base = mapping
    claim(mapping)
    original = provision_mappings._state

    def state_then_release(*args):
        result = original(*args)
        assert assign(client, base + "/review", 1, "release").status_code == 200
        return result

    monkeypatch.setattr(provision_mappings, "_state", state_then_release)
    assert client.get(base + endpoint).status_code == 409


@pytest.mark.parametrize("existing", [False, True])
def test_concurrent_mapping_writes_only_one_wins(mapping, monkeypatch, existing):
    app, client, _, _, base = mapping
    claim(mapping)
    identifier = propose(mapping).json()["items"][0]["id"] if existing else None
    barrier = Barrier(2)
    original = provision_mappings._head

    def sync_head(*args):
        result = original(*args)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(provision_mappings, "_head", sync_head)

    def write():
        worker = TestClient(app)
        worker.cookies.update(client.cookies)
        worker.headers.update(client.headers)
        own = (app, worker, *mapping[2:])
        return (review(own, identifier, source_revision=1, decision="rejected") if existing else propose(own)).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: write(), range(2)))
    assert sorted(responses) == [200, 409]
    assert counts(app) == (1, 2 if existing else 1)


@pytest.mark.parametrize("kind", ["ciphertext", "head_binding", "event_binding", "event_missing", "event_structure",
                                 "head_swap", "event_swap", "wrong_span", "wrong_revision"])
def test_corrupt_or_swapped_payloads_fail_closed(mapping, kind):
    app, client, _, _, base = mapping
    claim(mapping)
    propose(mapping)
    foreign = another_client(app, username="foreign", firm="foreign-firm", role="admin")
    own = (app, foreign, *mapping[2:])
    claim(own)
    propose(own, rationale="Other firm protected content")
    with app.state.store.session() as session:
        head = session.scalar(select(ProvisionMappingHead).where(ProvisionMappingHead.firm_id == "demo-firm"))
        other = session.scalar(select(ProvisionMappingHead).where(ProvisionMappingHead.firm_id == "foreign-firm"))
        row = session.scalar(select(ProvisionMappingEvent).where(ProvisionMappingEvent.head_id == head.id))
        other_row = session.scalar(select(ProvisionMappingEvent).where(ProvisionMappingEvent.head_id == other.id))
        if kind == "ciphertext":
            head.payload = "corrupt"
        elif kind == "head_swap":
            head.payload = other.payload
        elif kind == "head_binding":
            payload = app.state.store.decode(head)
            payload["source_binding"]["source_id"] = "0" * 64
            head.payload = app.state.store.encode(payload)
        elif kind == "event_missing":
            session.execute(delete(ProvisionMappingEvent).where(ProvisionMappingEvent.id == row.id))
        else:
            payload = app.state.store.decode(row)
            if kind == "event_binding":
                payload["context"]["firm_id"] = "other"
            elif kind == "event_structure":
                payload["event"] = {}
            elif kind == "wrong_span":
                payload["event"]["snapshot"]["span"]["text"] = "Invented text"
            elif kind == "wrong_revision":
                payload["event"]["source_review_revision"] = True
            encrypted = other_row.payload if kind == "event_swap" else app.state.store.encode(payload)
            session.execute(update(ProvisionMappingEvent).where(ProvisionMappingEvent.id == row.id).values(payload=encrypted))
        session.commit()
    for suffix in ("", "/export"):
        response = client.get(base + "/provision-mappings" + suffix)
        assert response.status_code == 409 and "Other firm" not in response.text
    assert propose(mapping, 1, candidate_id=None, start=0, end=18, label="Other manual").status_code == 409


def test_history_truncation_keeps_current_event_integrity_and_caps(mapping, monkeypatch):
    app, client, _, _, base = mapping
    monkeypatch.setattr(provision_mappings, "HISTORY_LIMIT", 2)
    monkeypatch.setattr(provision_mappings, "MAX_EVENTS", 4)
    claim(mapping)
    first = propose(mapping).json()["items"][0]["id"]
    response = propose(mapping, 1, candidate_id=None, start=0, end=18, label="Manual test")
    second = response.json()["items"][1]["id"]
    assert review(mapping, second, 2, 1, "rejected").status_code == 200
    assert review(mapping, second, 3, 1, "needs_changes").status_code == 200
    state = client.get(base + "/provision-mappings").json()
    assert state["history_truncated"] and len(state["history"]) == 2
    assert state["items"][0]["id"] == first
    assert review(mapping, second, 4, 1, "rejected").status_code == 409
    with app.state.store.session() as session:
        session.execute(delete(ProvisionMappingEvent).where(ProvisionMappingEvent.revision == 1))
        session.commit()
    assert client.get(base + "/provision-mappings/export").status_code == 409


def test_events_cannot_be_updated_or_deleted_through_orm(mapping):
    app = mapping[0]
    claim(mapping)
    propose(mapping)
    with app.state.store.session() as session:
        row = session.scalar(select(ProvisionMappingEvent))
        row.payload = app.state.store.encode({"fake": True})
        with pytest.raises(ValueError, match="append-only"):
            session.commit()
        session.rollback()
        session.delete(session.scalar(select(ProvisionMappingEvent)))
        with pytest.raises(ValueError, match="append-only"):
            session.commit()


@pytest.mark.parametrize("kind", ["older_acceptance", "head_rollback", "missing_mapping"])
def test_projection_cannot_hide_newer_immutable_events(mapping, kind):
    app, client, _, _, base = mapping
    ready(mapping)
    identifier = propose(mapping, source_revision=5).json()["items"][0]["id"]
    accepted = review(mapping, identifier).json()["items"][0]["last_event"]
    assert review(mapping, identifier, 2, 5, "rejected").status_code == 200
    with app.state.store.session() as session:
        head = session.scalar(select(ProvisionMappingHead))
        payload = app.state.store.decode(head)
        if kind == "older_acceptance":
            payload["mappings"][identifier] = accepted
        elif kind == "head_rollback":
            head.revision = 2
            payload["context"]["revision"] = 2
            payload["mappings"][identifier] = accepted
        else:
            payload["mappings"].clear()
        head.payload = app.state.store.encode(payload)
        session.commit()
    assert client.get(base + "/provision-mappings").status_code == 409
    assert client.get(base + "/provision-mappings/export").status_code == 409


def test_locator_gaps_are_visible_and_block_mapping_acceptance(mapping):
    app, client, store, source_id, _ = mapping
    package = store.verified_package(source_id)
    locators = package.locators.model_dump()
    gap = TEXT.index("Birinci")
    locators["passages"] = [
        {"id": "p1", "start": 0, "end": gap, "text_sha256": sha(TEXT[:gap]), "locator": "Test 1"},
        {"id": "p2", "start": gap + 1, "end": len(TEXT), "text_sha256": sha(TEXT[gap + 1:]), "locator": "Test 2"}]
    path = app.state.settings.data_dir / "gapped-locators.json"
    path.write_text(json.dumps(locators), encoding="utf-8")
    original = store.root / source_id
    source_id = store.import_package(metadata_path=original / "source.json", raw_path=original / "raw.bin",
                                     text_path=original / "text.txt", locators_path=path)["id"]
    base = f"/api/v1/public-sources/{source_id}"
    own = (app, client, store, source_id, base)
    ready(own)
    preview = client.get(base + "/provision-span", params={"start": 0, "end": len(TEXT)}).json()
    assert preview["non_whitespace_covered"] is False
    proposed = propose(own, source_revision=5)
    assert proposed.status_code == 200
    assert not proposed.json()["items"][0]["non_whitespace_covered"]
    assert review(own, proposed.json()["items"][0]["id"]).status_code == 422


def test_mapping_mutations_require_csrf_session_and_safe_origin(mapping):
    app, client, _, _, base = mapping
    claim(mapping)
    token = client.headers.pop("X-CSRF-Token")
    assert client.post(base + "/provision-mappings", json={}).status_code == 403
    client.headers["X-CSRF-Token"] = token
    client.headers["Origin"] = "https://foreign.invalid"
    assert client.post(base + "/provision-mappings", json={}).status_code == 403
    client.headers.pop("Origin")
    client.cookies.clear()
    assert client.get(base + "/provision-mappings").status_code == 401
    assert client.post(base + "/provision-mappings", json={}).status_code == 401
    assert counts(app) == (0, 0)


@pytest.mark.parametrize("endpoint", ["/provision-candidates", "/provision-mappings", "/provision-mappings/export",
                                     "/provision-span?start=0&end=10"])
def test_source_tamper_denies_every_inspection_route(mapping, endpoint):
    _, client, store, source_id, base = mapping
    path = store.root / source_id / "raw.bin"
    path.chmod(0o600)
    path.write_bytes(b"tampered")
    assert client.get(base + endpoint).status_code == 409


def test_mapping_count_and_preview_bounds_are_bounded(mapping, monkeypatch):
    app, client, _, _, base = mapping
    monkeypatch.setattr(provision_mappings, "MAX_MAPPINGS", 1)
    claim(mapping)
    assert propose(mapping).status_code == 200
    assert propose(mapping, 1, candidate_id=None, start=0, end=18, label="manual").status_code == 409
    for params in ({"start": 0, "end": 20001}, {"start": -1, "end": 5}, {"start": 5, "end": 5},
                   {"start": 1, "end": "true"}, {"start": len(TEXT) - 2, "end": len(TEXT)}):
        assert client.get(base + "/provision-span", params=params).status_code == 422
    assert client.get(base + "/provision-candidates?offset=501").status_code == 422
    assert client.get(base + "/provision-candidates?limit=21").status_code == 422
    assert counts(app) == (1, 1)
