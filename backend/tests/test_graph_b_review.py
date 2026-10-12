"""Invented appointments and TEST-ONLY signatures, never professional approval."""
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from test_decision_equivalence import (  # noqa: F401
    endpoint,
    incoming,
    opinion,
    pins,
    proof,
    propose,
    source,
    workspace,
)
from test_decision_equivalence import evidence_set as evidence_fixture
from test_source_reviews import another_client, assess

from app.graph_b_review_models import GraphBReviewEvent
from app.release_preparation import canonical, digest

evidence_set = evidence_fixture


def path(evidence_set, suffix=""):
    return endpoint(evidence_set).replace("/decision-equivalence?", "/graph-b-review" + suffix + "?")


def prepare(evidence_set, tmp_path):
    assert propose(evidence_set).status_code == opinion(evidence_set).status_code == 200
    app, owner = evidence_set[0][0][:2]
    reviewer = another_client(app, username="signed-reviewer")
    reviewer_id = reviewer.get("/api/v1/auth/me").json()["user"]["id"]
    key = Ed25519PrivateKey.generate()
    public = tmp_path / "TEST-ONLY-graph-b-review.pem"
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    app.state.settings.graph_b_review_trusted_key = str(public)
    credential = b"TEST-ONLY invented internal reviewer appointment; no actual licence"
    credential_data = base64.b64encode(credential).decode()
    timestamp = datetime.now(timezone.utc).isoformat()
    unknown = {"end_status": "unknown", "valid_from": None, "valid_until": None, "checked_through": None,
               "evidence": [], "rationale": "Temporal applicability unknown; never borrowed from institutional identity"}
    body = {"expected_review_revision": 0, "expected_equivalence_revision": 2, "pins": pins(evidence_set),
            "reviewer_id": reviewer_id, "public_reviewer": "TEST-ONLY PUBLIC REVIEWER", "reviewed_at": timestamp,
            "credential_data": credential_data, "appointment": {"scope": "TR_decision_identity_institution_temporal_review",
                "valid_from": "2020-01-01", "valid_until": (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat(),
                "evidence_sha256": digest(credential), "statement": "Invented appointment for engineering verification only"},
            "qualifications": {"decision_on": "2021-01-12", "decision_date_evidence": [proof(i) for i in evidence_set[0][:2]],
                "institution": {"institution_id": "urn:tr-law:institution:synthetic-court",
                    "registered_name": "Synthetic identity-only court", "register_record_id": "synthetic register record 7",
                    "scope": "historical_identity_only", "identity_window": {"end_status": "closed", "valid_from": "2020-01-01",
                        "valid_until": "2022-01-01", "checked_through": None, "evidence": [proof(evidence_set[0][2])],
                        "rationale": "Invented register identity window, not establishment or competence"}},
                "relations": [{**unknown, "source_id": i[3], "relation": relation} for i in evidence_set[0][:2]
                              for relation in ("decidedIn", "issuedBy", "hasDecisionVersion")]}}
    return app, owner, reviewer, key, public, body


@pytest.fixture
def signed_review(evidence_set, tmp_path):
    return prepare(evidence_set, tmp_path)


def request_body(evidence_set, fixture, **changes):
    return fixture[1].post(path(evidence_set, "/request"), json={**fixture[5], **changes})


def accept(evidence_set, fixture, body=None, client=None, key=None, **changes):
    if body is None:
        response = request_body(evidence_set, fixture)
        assert response.status_code == 200, response.text
        body = json.loads(response.json()["body_json"])
    body = {**body, **changes}
    signature = base64.b64encode((key or fixture[3]).sign(canonical(body))).decode()
    return (client or fixture[2]).post(path(evidence_set, "/accept"), json={"envelope": {
        "algorithm": "Ed25519", "body": body, "signature": signature}, "credential_data": fixture[5]["credential_data"]})


def test_exact_signed_review_private_encrypted_complete_and_unknown_dates_preserved(evidence_set, signed_review):
    app, owner, _, _, _, _ = signed_review
    result = request_body(evidence_set, signed_review)
    assert result.status_code == 200, result.text
    assert digest(result.json()["body_json"].encode()) == result.json()["body_sha256"]
    assert result.json()["signed"] is False and result.json()["publication_eligible"] is False
    state = accept(evidence_set, signed_review)
    assert state.status_code == 200, state.text
    data = state.json()
    assert data["signed_review_current"] and data["revision"] == 1 and data["history_complete"]
    assert not data["stale"] and data["confidentiality"] == "firm_confidential"
    assert "credential_data" not in state.text and "accepted_key" not in state.text
    assert all(entry["end_status"] == "unknown" for entry in data["current"]["envelope"]["body"]["qualifications"]["relations"])
    assert all(data[key] is False for key in ("graph_updated", "publication_eligible", "legal_truth_verified", "institutional_competence_verified", "finality_verified"))
    with app.state.store.session() as session:
        row = session.scalar(select(GraphBReviewEvent))
        assert "Invented appointment" not in row.payload and "TEST-ONLY" not in row.payload
        row.created_at = "changed"
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
    assert owner.get(path(evidence_set)).json()["history"] == data["history"]


def test_signed_rejection_supersedes_approval_and_cannot_be_hidden_by_old_signature(evidence_set, signed_review):
    first = request_body(evidence_set, signed_review)
    body = json.loads(first.json()["body_json"])
    assert accept(evidence_set, signed_review, body).status_code == 200
    assert accept(evidence_set, signed_review, body, expected_review_revision=1, decision="reject").status_code == 409
    signed_review[5]["expected_review_revision"] = 1
    signed_review[5]["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    response = accept(evidence_set, signed_review, decision="reject")
    assert response.status_code == 200, response.text
    assert not response.json()["signed_review_current"] and response.json()["revision"] == 2
    assert accept(evidence_set, signed_review, body).status_code == 409
    assert [e["envelope"]["body"]["decision"] for e in response.json()["history"]] == ["reject", "approve"]


@pytest.mark.parametrize("change", ["foreign-key", "self-review", "identity-contributor", "equivalence-contributor",
    "wrong-firm", "wrong-context", "snapshot", "ontology", "key", "sequence", "equivalence", "future-time", "expired-appointment"])
def test_signature_and_current_qualified_context_never_self_authorize(evidence_set, signed_review, change):
    result = request_body(evidence_set, signed_review)
    body = json.loads(result.json()["body_json"])
    client, key = signed_review[2], signed_review[3]
    if change == "foreign-key":
        key = Ed25519PrivateKey.generate()
    if change == "self-review":
        body["reviewer_id"] = body["operator_id"]
        client = signed_review[1]
    if change in {"identity-contributor", "equivalence-contributor"}:
        client = evidence_set[1 if change == "identity-contributor" else 2]
        body["reviewer_id"] = client.get("/api/v1/auth/me").json()["user"]["id"]
    if change == "wrong-firm":
        body["firm_id"] = "other-firm"
    if change == "wrong-context":
        body["context_id"] = "f" * 64
    if change in {"snapshot", "ontology", "key"}:
        body[{"snapshot": "source_snapshot_sha256", "ontology": "ontology_sha256", "key": "review_key_sha256"}[change]] = "f" * 64
    if change == "sequence":
        body["expected_review_revision"] = 1
    if change == "equivalence":
        body["equivalence_revision"] = 1
    if change == "future-time":
        body["reviewed_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    if change == "expired-appointment":
        body["appointment"]["valid_until"] = "2021-01-01"
    response = accept(evidence_set, signed_review, body, client, key)
    assert response.status_code in {403, 409, 422}, response.text
    assert signed_review[1].get(path(evidence_set)).json()["revision"] == 0


@pytest.mark.parametrize("index", [0, 1, 2])
def test_any_source_change_withholds_prior_signature_and_preserves_old_history(evidence_set, signed_review, index):
    assert accept(evidence_set, signed_review).status_code == 200
    item = evidence_set[0][index]
    assert assess(item[1], item[4] + "/review", 6, "legal").status_code == 200
    state = signed_review[1].get(path(evidence_set))
    assert state.status_code == 200, state.text
    assert state.json()["revision"] == 1 and state.json()["stale"] and not state.json()["signed_review_current"]


def test_rotation_and_missing_trust_preserve_historical_signature_without_current_approval(evidence_set, signed_review):
    assert accept(evidence_set, signed_review).status_code == 200
    another_key = Ed25519PrivateKey.generate()
    signed_review[4].write_bytes(another_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    result = signed_review[1].get(path(evidence_set))
    assert result.status_code == 200 and result.json()["stale"] and not result.json()["signed_review_current"]
    assert len(result.json()["history"]) == 1
    signed_review[0].state.settings.graph_b_review_trusted_key = ""
    assert signed_review[1].get(path(evidence_set)).json()["trust_configured"] is False
    assert request_body(evidence_set, signed_review).status_code == 503


@pytest.mark.parametrize("change", ["register-gap", "register-hash", "institution", "decision-date-future",
    "missing-decision-source", "relation-missing", "unknown-bounds", "inverted", "future-horizon", "borrowed-relation"])
def test_explicit_institution_and_six_separate_temporal_assessments(evidence_set, signed_review, change):
    body = json.loads(json.dumps(signed_review[5]))
    qualification = body["qualifications"]
    interval = qualification["institution"]["identity_window"]
    if change == "register-gap":
        interval["valid_from"] = "2021-02-01"
    if change == "register-hash":
        interval["evidence"][0]["sha256"] = "f" * 64
    if change == "institution":
        qualification["institution"]["institution_id"] = "urn:tr-law:institution:other"
    if change == "decision-date-future":
        qualification["decision_on"] = "2099-01-01"
    if change == "missing-decision-source":
        qualification["decision_date_evidence"] = [proof(evidence_set[0][0]), {**proof(evidence_set[0][0]), "passage_id": "p1"}]
    if change == "relation-missing":
        qualification["relations"].pop()
    if change == "unknown-bounds":
        qualification["relations"][0]["valid_from"] = "2020-01-01"
    if change == "inverted":
        interval["valid_until"] = interval["valid_from"]
    if change == "future-horizon":
        interval.update(end_status="open_ended", valid_until=None, checked_through="2099-01-01")
    if change == "borrowed-relation":
        qualification["relations"][0].update(end_status="closed", valid_from="2020-01-01", valid_until="2022-01-01", evidence=[proof(evidence_set[0][2])])
    result = signed_review[1].post(path(evidence_set, "/request"), json=body)
    assert result.status_code in {409, 422}, result.text


def test_credential_bytes_csrf_and_role_boundaries(evidence_set, signed_review):
    result = request_body(evidence_set, signed_review, credential_data=base64.b64encode(b"different appointment").decode())
    assert result.status_code == 409
    body = json.loads(request_body(evidence_set, signed_review).json()["body_json"])
    reviewer = signed_review[2]
    reviewer.headers.pop("X-CSRF-Token")
    assert accept(evidence_set, signed_review, body).status_code == 403
    lawyer = another_client(signed_review[0], username="lawyer-reader", role="lawyer")
    assert lawyer.get(path(evidence_set)).status_code == 403


def test_appointment_expiry_and_reviewer_deactivation_make_approval_unavailable(evidence_set, signed_review):
    from sqlalchemy import update

    from app.db import User
    assert accept(evidence_set, signed_review).status_code == 200
    body = signed_review[1].get(path(evidence_set)).json()["current"]["envelope"]["body"]
    with signed_review[0].state.store.session() as session:
        session.execute(update(User).where(User.id == body["reviewer_id"]).values(active=False))
        session.commit()
    state = signed_review[1].get(path(evidence_set)).json()
    assert state["stale"] and not state["signed_review_current"] and len(state["history"]) == 1


@pytest.mark.parametrize("end_status", ["closed", "open_ended"])
def test_each_known_relation_keeps_its_own_supported_interval(evidence_set, signed_review, end_status):
    body = signed_review[5]
    for entry in body["qualifications"]["relations"]:
        item = next(i for i in evidence_set[0][:2] if i[3] == entry["source_id"])
        entry.update(end_status=end_status, valid_from="2021-01-12", valid_until="2023-01-01" if end_status == "closed" else None,
                     checked_through="2024-01-01" if end_status == "open_ended" else None,
                     evidence=[proof(item)] + ([proof(evidence_set[0][2])] if entry["relation"] == "issuedBy" else []))
    state = accept(evidence_set, signed_review)
    assert state.status_code == 200, state.text
    assert {entry["valid_from"] for entry in state.json()["current"]["envelope"]["body"]["qualifications"]["relations"]} == {"2021-01-12"}
    assert state.json()["current"]["envelope"]["body"]["qualifications"]["institution"]["identity_window"]["valid_from"] == "2020-01-01"


@pytest.mark.parametrize("change", ["credential-budget", "ledger-budget", "missing-event", "projection"])
def test_review_storage_is_bounded_complete_and_not_projection_only(evidence_set, signed_review, monkeypatch, change):
    from sqlalchemy import delete, update

    from app import graph_b_review as review
    from app.graph_b_review_models import GraphBReviewHead
    if change == "credential-budget":
        monkeypatch.setattr(review, "MAX_CREDENTIAL_BYTES", 4)
        assert request_body(evidence_set, signed_review).status_code == 409
        return
    assert accept(evidence_set, signed_review).status_code == 200
    if change == "ledger-budget":
        monkeypatch.setattr(review, "MAX_LEDGER_BYTES", 1)
    else:
        with signed_review[0].state.store.session() as session:
            if change == "missing-event":
                session.execute(delete(GraphBReviewEvent))  # Deliberate corrupt-storage fixture.
            else:
                session.execute(update(GraphBReviewHead).values(payload=signed_review[0].state.store.encode({"forged": True})))
            session.commit()
    response = signed_review[1].get(path(evidence_set))
    assert response.status_code == 409 and "history" not in response.json()


@pytest.mark.parametrize("route", ["get", "request", "accept"])
def test_key_change_during_action_withholds_output_and_rolls_back_acceptance(evidence_set, signed_review, monkeypatch, route):
    from app import graph_b_review as review
    body = json.loads(request_body(evidence_set, signed_review).json()["body_json"])
    verify = review.eq.verify
    def rotate(*args):
        verify(*args)
        key = Ed25519PrivateKey.generate()
        signed_review[4].write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    if route == "request":
        # Rotate after the first verified snapshot, before the final key check.
        capture = review.context_data
        count = 0
        def changed(*args, **kwargs):
            nonlocal count
            result = capture(*args, **kwargs)
            count += 1
            if count == 2:
                rotate(args[0], result[0], args[4])
            return result
        monkeypatch.setattr(review, "context_data", changed)
        response = request_body(evidence_set, signed_review)
    else:
        monkeypatch.setattr(review.eq, "verify", rotate)
        response = signed_review[1].get(path(evidence_set)) if route == "get" else accept(evidence_set, signed_review, body)
    assert response.status_code == 409, response.text
    with signed_review[0].state.store.session() as session:
        assert session.scalar(select(GraphBReviewEvent)) is None
