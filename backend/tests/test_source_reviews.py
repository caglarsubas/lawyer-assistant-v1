from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_public_sources import source as source_fixture
from test_workspace import workspace as workspace_fixture

from app import source_reviews
from app.auth import hash_password
from app.db import Audit, LoginSession, Record, User
from app.public_sources import PublicSourceStore
from app.source_review_models import SourceReviewEvent, SourceReviewHead

source = source_fixture
workspace = workspace_fixture


@pytest.fixture
def review(workspace, source):
    app, client, _ = workspace
    store, inputs, _, _ = source
    source_id = store.import_package(**inputs)["id"]
    app.state.settings.public_source_dir = store.root
    return app, client, store, source_id, f"/api/v1/public-sources/{source_id}/review"


def assign(client, base, revision=0, action="claim", rationale="İncelemeyi üstleniyorum"):
    return client.post(base + "/assignment", json={"expected_revision": revision, "action": action,
                                                    "rationale": rationale})


def assess(client, base, revision=1, category="source_identity", decision="accepted", **changes):
    data = {"expected_revision": revision, "category": category, "decision": decision,
            "rationale": "İnsan incelemeci kaynak dayanağını değerlendirdi", "passage_ids": [],
            "evidence_refs": [{"reference": "Yerel inceleme belgesi", "sha256": "a" * 64}],
            "permitted_uses": []}
    if category == "rights":
        data["permitted_uses"] = ["storage"]
    if category == "extraction":
        data["passage_ids"] = ["p1"]
    return client.post(base + "/assessments", json={**data, **changes})


def counts(app):
    with app.state.store.session() as session:
        return tuple(session.scalar(select(func.count()).select_from(model))
                     for model in (SourceReviewHead, SourceReviewEvent))


def another_client(app, *, username="another", role="curator", firm="demo-firm"):
    with app.state.store.session() as session:
        user = User(username=username, name="Second confidential reviewer", firm_id=firm, role=role,
                    password_hash=hash_password("local-review-password"))
        session.add(user)
        session.commit()
    client = TestClient(app)
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "local-review-password"})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


def test_virtual_state_does_not_create_review_or_promote_source(review):
    app, client, store, identifier, base = review
    state = client.get(base).json()
    assert state["revision"] == 0 and state["assigned_to"] is None
    assert state["history"] == state["assessments"] == []
    assert not state["handoff_ready"] and not state["publication_eligible"]
    assert state["source"] == store.detail(identifier)
    assert state["source"]["integrity_scope"] == "all_artifacts_verified"
    assert counts(app) == (0, 0)


def test_full_review_is_accountable_encrypted_and_only_a_handoff(review):
    app, client, public_store, identifier, base = review
    original = {path.name: path.read_bytes() for path in (public_store.root / identifier).iterdir()}
    before_records = None
    with app.state.store.session() as session:
        before_records = session.scalar(select(func.count()).select_from(Record))
    first = assign(client, base)
    assert first.status_code == 200, first.text
    assert first.json()["assigned_to"]["name"] == "Demo Avukat"
    for revision, category in enumerate(("rights", "source_identity", "extraction", "legal"), start=1):
        response = assess(client, base, revision, category)
        assert response.status_code == 200, response.text
    state = response.json()
    assert state["revision"] == 5 and state["handoff_ready"] is True
    assert state["publication_eligible"] is False and len(state["assessments"]) == 4
    assert [item["revision"] for item in state["history"]] == [5, 4, 3, 2, 1]
    assert state["source"]["rights_status"] == "rights_pending"
    assert state["source"]["review_status"] == "legal_review_pending"
    assert state["source"]["publication_status"] == "staged"
    assert original == {path.name: path.read_bytes() for path in (public_store.root / identifier).iterdir()}
    with app.state.store.session() as session:
        assert session.scalar(select(func.count()).select_from(Record)) == before_records
        head = session.scalar(select(SourceReviewHead))
        for row in [head, *session.scalars(select(SourceReviewEvent))]:
            assert "Demo Avukat" not in row.payload and "İnsan incelemeci" not in row.payload
            assert app.state.store.decode(row)["source_binding"]["source_id"] == identifier
        audits = list(session.scalars(select(Audit).where(Audit.action.like("source_review_%"))))
        assert audits == []  # Reviewer identities stay in encrypted review events, never generic plaintext audit.
    exported = client.get(base + "/export")
    assert exported.status_code == 200
    assert exported.headers["cache-control"] == "no-store"
    assert exported.headers["x-content-type-options"] == "nosniff"
    assert exported.headers["content-disposition"].startswith("attachment;")
    dossier = exported.json()
    assert dossier["signed"] is False and dossier["publication_eligible"] is False
    assert dossier["confidentiality"] == "firm_confidential"
    assert dossier["review"] == state


def test_latest_negative_assessment_preserves_history_and_revokes_handoff(review):
    _, client, _, _, base = review
    assign(client, base)
    for revision, category in enumerate(("rights", "source_identity", "extraction", "legal"), start=1):
        assert assess(client, base, revision, category).status_code == 200
    result = assess(client, base, 5, "legal", "needs_changes").json()
    assert result["handoff_ready"] is False
    assert len(result["assessments"]) == 4 and len(result["history"]) == 6
    assert [event["decision"] for event in result["history"] if event.get("category") == "legal"] == [
        "needs_changes", "accepted"]


def test_stale_and_repeated_writes_do_not_append_history(review):
    app, client, _, _, base = review
    assert assign(client, base).status_code == 200
    assert assign(client, base).status_code == 409
    assert assign(client, base, 1).status_code == 409  # Same owner cannot produce duplicate claims.
    assert assess(client, base, 0).status_code == 409
    assert assess(client, base, 1).status_code == 200
    assert assess(client, base, 1).status_code == 409
    assert counts(app) == (1, 2)


def test_assignment_owner_rules_and_reasoned_admin_release(review):
    app, client, _, _, base = review
    owner = another_client(app, username="owner")
    other = another_client(app, username="other")
    assert assign(owner, base).status_code == 200
    assert assign(other, base, 1).status_code == 409
    assert assess(other, base, 1).status_code == 409
    assert assign(other, base, 1, "release").status_code == 403
    assert assign(client, base, 1, "release", rationale=" ").status_code == 422
    assert assign(client, base, 1, "release", rationale="İncelemeci bu görevden ayrıldı").status_code == 200
    assert assess(owner, base, 2).status_code == 409
    assert assign(other, base, 2).status_code == 200
    assert assess(other, base, 3).status_code == 200
    assert assign(other, base, 4, "release").status_code == 200
    assert assign(other, base, 5, "release").status_code == 409
    assert counts(app) == (1, 5)


def test_firm_isolation_of_assignment_notes_history_and_export(review):
    app, client, _, _, base = review
    assert assign(client, base, rationale="Firm one confidential note").status_code == 200
    foreign = another_client(app, firm="foreign-firm", role="admin")
    initial = foreign.get(base).json()
    assert initial["revision"] == 0 and initial["history"] == []
    assert "Firm one" not in foreign.get(base + "/export").text
    assert assign(foreign, base, rationale="Firm two secret review").status_code == 200
    assert "Firm two" not in client.get(base).text
    assert "Firm two" not in client.get(base + "/export").text
    assert "Firm one" not in foreign.get(base).text
    assert counts(app) == (2, 2)


@pytest.mark.parametrize("endpoint,method", [("", "get"), ("/export", "get"), ("/assignment", "post"),
                                             ("/assessments", "post")])
def test_lawyer_role_denied_before_source_read(review, monkeypatch, endpoint, method):
    app, client, _, _, base = review
    with app.state.store.session() as session:
        session.scalar(select(User).where(User.username == "demo")).role = "lawyer"
        session.commit()
    monkeypatch.setattr(PublicSourceStore, "verified_package", lambda *_: pytest.fail("Must not read source"))
    response = getattr(client, method)(base + endpoint, **({"json": {}} if method == "post" else {}))
    assert response.status_code == 403
    assert counts(app) == (0, 0)


def test_csrf_origin_and_missing_login_block_writes(review):
    app, client, _, _, base = review
    csrf = client.headers.pop("X-CSRF-Token")
    assert assign(client, base).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    client.headers["Origin"] = "https://foreign.invalid"
    assert assign(client, base).status_code == 403
    client.headers.pop("Origin")
    client.cookies.clear()
    assert assign(client, base).status_code == 401
    assert client.get(base).status_code == 401
    assert counts(app) == (0, 0)


@pytest.mark.parametrize("endpoint,method", [("", "get"), ("/export", "get"), ("/assignment", "post"),
                                             ("/assessments", "post")])
def test_source_tamper_denies_all_review_endpoints(review, endpoint, method):
    app, client, public_store, identifier, base = review
    artifact = public_store.root / identifier / "text.txt"
    artifact.chmod(0o600)
    artifact.write_bytes(artifact.read_bytes() + b"Changed")
    if method == "get":
        result = client.get(base + endpoint)
    elif endpoint == "/assignment":
        result = assign(client, base)
    else:
        result = assess(client, base, 0)
    assert result.status_code == 409
    assert counts(app) == (0, 0)


def revoke(app, kind):
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == "demo"))
        if kind == "inactive":
            user.active = False
        elif kind == "role":
            user.role = "lawyer"
        elif kind == "firm":
            user.firm_id = "changed-firm"
        elif kind == "downgrade":
            user.role = "curator"
        else:
            login = session.scalar(select(LoginSession).where(LoginSession.user_id == user.id))
            if kind == "session":
                session.delete(login)
            elif kind == "expired":
                login.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
            elif kind == "csrf":
                login.csrf = "changed-secret"
        session.commit()


@pytest.mark.parametrize("kind,status", [("inactive", 401), ("role", 403), ("firm", 401),
                                         ("session", 401), ("expired", 401), ("csrf", 403)])
@pytest.mark.parametrize("write", [False, True])
def test_authorization_revoked_during_source_read(review, monkeypatch, kind, status, write):
    app, client, _, _, base = review
    original = PublicSourceStore.verified_package

    def verified_then_revoke(store, identifier):
        package = original(store, identifier)
        revoke(app, kind)
        return package

    monkeypatch.setattr(PublicSourceStore, "verified_package", verified_then_revoke)
    response = assign(client, base) if write else client.get(base)
    # Read requests do not rely on the mutation-only CSRF token.
    assert response.status_code == (200 if kind == "csrf" and not write else status)
    assert counts(app) == (0, 0)


@pytest.mark.parametrize("kind,status", [("inactive", 401), ("role", 403), ("firm", 401),
                                         ("session", 401), ("expired", 401), ("csrf", 403), ("downgrade", 403)])
def test_authorization_rechecked_immediately_before_commit(review, monkeypatch, kind, status):
    app, client, _, _, base = review
    original = source_reviews._transition

    def transition_then_revoke(projection, event, user):
        original(projection, event, user)
        revoke(app, kind)

    monkeypatch.setattr(source_reviews, "_transition", transition_then_revoke)
    assert assign(client, base).status_code == status
    assert counts(app) == (0, 0)


@pytest.mark.parametrize("changes", [
    {"evidence_refs": []}, {"evidence_refs": [{"reference": "x", "sha256": "A" * 64}]},
    {"evidence_refs": [{"reference": "x", "sha256": "a" * 64, "verified": True}]},
    {"passage_ids": ["unknown"]}, {"passage_ids": ["p1", "p1"]}, {"passage_ids": ["a" * 10000]},
    {"rationale": " "}, {"rationale": "x" * 4001}, {"expected_revision": True},
    {"reviewer": {"id": "another"}}, {"reviewed_at": "2020-01-01"}, {"signature": "forged"},
    {"source_id": "0" * 64}, {"category": "binding_law"}, {"decision": "publish"},
    {"permitted_uses": ["storage"]},
])
def test_assessment_strict_inputs_reject_unbound_or_unsupported_claims(review, changes):
    app, client, _, _, base = review
    assign(client, base)
    assert assess(client, base, **changes).status_code == 422
    assert counts(app) == (1, 1)


def test_rights_and_extraction_have_required_specific_support(review):
    _, client, _, _, base = review
    assign(client, base)
    assert assess(client, base, category="rights", permitted_uses=[]).status_code == 422
    assert assess(client, base, category="rights", permitted_uses=["storage", "storage"]).status_code == 422
    assert assess(client, base, category="extraction", passage_ids=[]).status_code == 422
    assert assess(client, base, category="extraction", decision="rejected", passage_ids=[]).status_code == 200
    assert assess(client, base, revision=2, decision="needs_changes", evidence_refs=[]).status_code == 200


def test_export_history_cap_and_event_hard_limit_are_explicit(review, monkeypatch):
    app, client, _, _, base = review
    monkeypatch.setattr(source_reviews, "HISTORY_LIMIT", 2)
    monkeypatch.setattr(source_reviews, "MAX_EVENTS", 4)
    assign(client, base)
    for revision in (1, 2, 3):
        assert assess(client, base, revision).status_code == 200
    state = client.get(base).json()
    assert len(state["history"]) == 2 and state["history_truncated"] is True
    assert state["assessments"][0]["revision"] == 4
    assert len(client.get(base + "/export").json()["review"]["history"]) == 2
    assert assess(client, base, 4).status_code == 409
    assert counts(app) == (1, 4)


def test_event_rows_cannot_be_modified_or_deleted_through_orm(review):
    app, client, _, _, base = review
    assign(client, base)
    with app.state.store.session() as session:
        event = session.scalar(select(SourceReviewEvent))
        event.payload = app.state.store.encode({"fake": True})
        with pytest.raises(ValueError, match="append-only"):
            session.commit()
        session.rollback()
        session.delete(session.scalar(select(SourceReviewEvent)))
        with pytest.raises(ValueError, match="append-only"):
            session.commit()
    assert counts(app) == (1, 1)
    assert client.delete(base).status_code == 405
    assert client.put(base, json={}).status_code == 405


def test_different_package_cannot_reuse_review_binding(review):
    app, client, _, _, base = review
    assign(client, base)
    with app.state.store.session() as session:
        head = session.scalar(select(SourceReviewHead))
        projection = app.state.store.decode(head)
        projection["source_binding"]["source_id"] = "0" * 64
        head.payload = app.state.store.encode(projection)
        session.commit()
    assert client.get(base).status_code == 409
    assert assign(client, base, 1, "release").status_code == 409
    assert counts(app) == (1, 1)


@pytest.mark.parametrize("existing", [False, True])
def test_simultaneous_writes_have_one_winner_no_lost_events(review, monkeypatch, existing):
    app, client, _, _, base = review
    if existing:
        assign(client, base)
    barrier = Barrier(2)
    original = source_reviews._head

    def synchronize_head(*args):
        result = original(*args)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(source_reviews, "_head", synchronize_head)

    def write():
        worker = TestClient(app)
        worker.cookies.update(client.cookies)
        worker.headers.update(client.headers)
        return (assess(worker, base, 1) if existing else assign(worker, base)).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: write(), range(2)))
    assert sorted(responses) == [200, 409]
    assert counts(app) == (1, 2 if existing else 1)


def test_empty_or_invalid_source_identifier_has_no_review_side_effects(review):
    app, client, _, _, _ = review
    assert client.get("/api/v1/public-sources/bad/review").status_code == 404
    assert assign(client, "/api/v1/public-sources/" + "0" * 64 + "/review").status_code == 409
    assert counts(app) == (0, 0)


@pytest.mark.parametrize("kind", ["head_swap", "event_swap", "event_missing", "event_binding", "event_revision",
                                   "head_structure", "event_structure", "head_ciphertext"])
def test_corrupt_or_swapped_authenticated_payloads_fail_closed(review, kind):
    from sqlalchemy import delete, update

    app, client, _, _, base = review
    assign(client, base, rationale="Firm one confidential finding")
    foreign = another_client(app, firm="foreign-firm", username="foreign", role="admin")
    assign(foreign, base, rationale="Firm two protected finding")
    with app.state.store.session() as session:
        first = session.scalar(select(SourceReviewHead).where(SourceReviewHead.firm_id == "demo-firm"))
        second = session.scalar(select(SourceReviewHead).where(SourceReviewHead.firm_id == "foreign-firm"))
        first_event = session.scalar(select(SourceReviewEvent).where(SourceReviewEvent.head_id == first.id))
        second_event = session.scalar(select(SourceReviewEvent).where(SourceReviewEvent.head_id == second.id))
        if kind == "head_swap":
            first.payload = second.payload
        elif kind == "head_ciphertext":
            first.payload = "corrupt encrypted payload"
        elif kind == "head_structure":
            projection = app.state.store.decode(first)
            projection["assessments"] = []
            first.payload = app.state.store.encode(projection)
        elif kind == "event_missing":
            session.execute(delete(SourceReviewEvent).where(SourceReviewEvent.id == first_event.id))
        else:
            data = app.state.store.decode(first_event)
            if kind == "event_swap":
                payload = second_event.payload
            else:
                if kind == "event_binding":
                    data["source_binding"]["source_id"] = "0" * 64
                elif kind == "event_revision":
                    data["event"]["revision"] = 17
                elif kind == "event_structure":
                    data["event"] = {"id": first_event.id}
                payload = app.state.store.encode(data)
            # Direct SQL models database corruption, bypassing the append-only ORM guard.
            session.execute(update(SourceReviewEvent).where(SourceReviewEvent.id == first_event.id).values(payload=payload))
        session.commit()
    for endpoint in ("", "/export"):
        result = client.get(base + endpoint)
        assert result.status_code == 409, result.text
        assert "Firm two" not in result.text
    assert assign(client, base, 1, "release").status_code == 409


def test_current_assessment_older_than_history_window_must_resolve_immutable_event(review, monkeypatch):
    from sqlalchemy import delete

    app, client, _, _, base = review
    monkeypatch.setattr(source_reviews, "HISTORY_LIMIT", 2)
    assign(client, base)
    assess(client, base, 1, "rights")
    assess(client, base, 2, "source_identity")
    assess(client, base, 3, "legal")
    state = client.get(base).json()
    assert state["history_truncated"] and len(state["assessments"]) == 3
    assert {event["revision"] for event in state["history"]} == {3, 4}
    with app.state.store.session() as session:
        session.execute(delete(SourceReviewEvent).where(SourceReviewEvent.revision == 2))
        session.commit()
    assert client.get(base).status_code == 409
    assert client.get(base + "/export").status_code == 409
    assert assign(client, base, 4, "release").status_code == 409


@pytest.mark.parametrize("kind", ["older_acceptance", "older_assignment", "head_rollback"])
def test_current_projection_cannot_hide_later_rejection_or_release(review, monkeypatch, kind):
    app, client, _, _, base = review
    monkeypatch.setattr(source_reviews, "HISTORY_LIMIT", 1)
    assigned = assign(client, base).json()["assigned_to"]
    accepted = assess(client, base, 1, "legal").json()["assessments"][0]
    assert assess(client, base, 2, "legal", "rejected").status_code == 200
    assert assign(client, base, 3, "release").status_code == 200
    with app.state.store.session() as session:
        head = session.scalar(select(SourceReviewHead))
        projection = app.state.store.decode(head)
        if kind == "older_acceptance":
            projection["assessments"]["legal"] = accepted
        elif kind == "older_assignment":
            projection["assigned_to"] = assigned
        else:
            head.revision = 2
            projection["context"]["revision"] = 2
            projection["assigned_to"] = assigned
            projection["assessments"]["legal"] = accepted
        head.payload = app.state.store.encode(projection)
        session.commit()
    assert client.get(base).status_code == 409
    assert client.get(base + "/export").status_code == 409
    assert assign(client, base, 4).status_code == 409
