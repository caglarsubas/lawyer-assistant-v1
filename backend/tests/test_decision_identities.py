"""Synthetic canonical identities; no actual legal or publication approval."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select, update
from test_decision_mappings import mapping as mapping_fixture
from test_decision_mappings import propose, ready, resolution, review
from test_jurisprudence_candidates import incoming as incoming_fixture
from test_public_sources import source as source_fixture
from test_source_reviews import another_client, assess, assign
from test_workspace import workspace as workspace_fixture

from app import decision_identities as identities
from app.decision_identity_models import (
    DecisionIdentityEvent,
    DecisionIdentityHead,
    DecisionIdentityReservation,
)

mapping = mapping_fixture
incoming = incoming_fixture
source = source_fixture
workspace = workspace_fixture


def mapped(mapping, *, export=False):
    ready(mapping)
    revision = 5
    if export:
        assert assess(mapping[1], mapping[4] + "/review", 5, "rights",
                      permitted_uses=["local_processing", "internal_display", "export"]).status_code == 200
        revision = 6
    identifier = propose(mapping, source_revision=revision).json()["items"][0]["id"]
    assert review(mapping, identifier, source_revision=revision).status_code == 200
    return identifier


def proposal(mapping, **changes):
    return {"expected_revision": 0, "expected_mapping_revision": 2, "expected_source_review_revision": 5,
            "rationale": "Synthetic explicit canonical assignment",
            "identity": {"institution_id": "urn:tr-law:institution:synthetic-court",
                         "proceeding_id": "urn:tr-law:proceeding:synthetic-proceeding",
                         "decision_id": "urn:tr-law:decision:synthetic-decision",
                         "identity_evidence": [{"reference": "Synthetic identity register", "sha256": "b" * 64}],
                         "institution_evidence": [{"reference": "Synthetic institution register", "sha256": "c" * 64}]}, **changes}


def propose_identity(mapping, **changes):
    return mapping[1].post(mapping[4] + "/decision-identities", json=proposal(mapping, **changes))


def review_identity(mapping, client, **changes):
    return client.post(mapping[4] + "/decision-identities/review", json={
        "expected_revision": 1, "expected_mapping_revision": 2, "expected_source_review_revision": 5,
        "decision": "accepted", "rationale": "Synthetic separate-account identity review",
        "evidence_refs": [{"reference": "Synthetic independent evidence", "sha256": "d" * 64}], **changes})


def test_separate_reviewer_canonical_version_and_immutable_private_history(mapping):
    mapped(mapping)
    original = {p.name: p.read_bytes() for p in (mapping[2].root / mapping[3]).iterdir()}
    response = propose_identity(mapping)
    assert response.status_code == 200, response.text
    first = response.json()
    assert not first["can_independently_review"] and not first["staged_handoff_ready"]
    assert review_identity(mapping, mapping[1]).status_code == 403
    peer = another_client(mapping[0])
    result = review_identity(mapping, peer)
    assert result.status_code == 200, result.text
    state = result.json()
    assert state["canonical_identity_reviewed"] and state["staged_handoff_ready"] and not state["stale"]
    assert not state["publication_eligible"] and not state["global_registry_qualified"] and not state["legal_effect_verified"]
    assert state["current"]["proposal"]["version_id"] == identities.version_id(mapping[6], proposal(mapping)["identity"]["decision_id"])
    assert state["history"][1] == first["current"]
    assert peer.get(mapping[4] + "/decision-identities").json() == state
    with mapping[0].state.store.session() as session:
        assert len(list(session.scalars(select(DecisionIdentityReservation)))) == 3
        for row in [*session.scalars(select(DecisionIdentityEvent)), session.scalar(select(DecisionIdentityHead))]:
            assert "synthetic-decision" not in row.payload
    assert original == {p.name: p.read_bytes() for p in (mapping[2].root / mapping[3]).iterdir()}


def test_historical_contributor_cannot_review_after_ownership_transfer(mapping):
    mapped(mapping)
    assert assign(mapping[1], mapping[4] + "/review", 5, action="release").status_code == 200
    owner = another_client(mapping[0], username="new-owner")
    assert assign(owner, mapping[4] + "/review", 6).status_code == 200
    owned = (mapping[0], owner, *mapping[2:])
    identifier = mapping[1].get(mapping[4] + "/decision-mappings").json()["items"][0]["id"]
    assert review(owned, identifier, 2, 7).status_code == 200
    assert propose_identity(owned, expected_mapping_revision=3, expected_source_review_revision=7).status_code == 200
    assert review_identity(mapping, mapping[1], expected_mapping_revision=3, expected_source_review_revision=7).status_code == 403
    independent = another_client(mapping[0], username="independent")
    assert review_identity(mapping, independent, expected_mapping_revision=3, expected_source_review_revision=7).status_code == 200


def test_stale_reproposal_keeps_prior_approval_without_reusing_it(mapping):
    identifier = mapped(mapping)
    assert propose_identity(mapping).status_code == 200
    peer = another_client(mapping[0])
    assert review_identity(mapping, peer).status_code == 200
    assert assess(mapping[1], mapping[4] + "/review", 5, "legal").status_code == 200
    state = peer.get(mapping[4] + "/decision-identities").json()
    assert state["stale"] and not state["canonical_identity_reviewed"] and not state["staged_handoff_ready"]
    assert review_identity(mapping, peer, expected_revision=2, expected_source_review_revision=6).status_code == 409
    assert review(mapping, identifier, 2, 6).status_code == 200
    fresh = propose_identity(mapping, expected_revision=2, expected_mapping_revision=3, expected_source_review_revision=6)
    assert fresh.status_code == 200, fresh.text
    assert not fresh.json()["staged_handoff_ready"] and len(fresh.json()["history"]) == 3
    assert review_identity(mapping, peer, expected_revision=3, expected_mapping_revision=3, expected_source_review_revision=6).status_code == 200


@pytest.mark.parametrize("changes", [
    {"expected_revision": True}, {"expected_mapping_revision": 1}, {"expected_source_review_revision": 4},
    {"expected_source_review_revision": 1001}, {"unexpected": "no"},
    {"identity": {"decision_id": "https://untrusted.invalid/decision"}},
])
def test_strict_revisions_and_explicit_identifiers(mapping, changes):
    mapped(mapping)
    assert propose_identity(mapping, **changes).status_code in {409, 422}
    assert mapping[1].get(mapping[4] + "/decision-identities").json()["revision"] == 0


def test_nonowner_unreviewed_multidecision_and_cross_firm_no_disclosure(mapping):
    assert propose_identity(mapping).status_code == 409
    mapped(mapping)
    other = another_client(mapping[0])
    assert propose_identity((mapping[0], other, *mapping[2:])).status_code == 409
    date = propose(mapping, revision=2, index=1).json()["items"][-1]
    candidate = mapping[5][1]
    assert review(mapping, date["id"], revision=3, resolution=resolution(mapping, start=candidate["start"],
                  end=candidate["end"], decision_ref="second-decision", event_role="decision", event_date="2021-01-12")).status_code == 200
    assert propose_identity(mapping, expected_mapping_revision=4).status_code == 409
    foreign = another_client(mapping[0], username="foreign", firm="other-firm")
    assert foreign.get(mapping[4] + "/decision-identities").json()["current"] is None
    lawyer = another_client(mapping[0], username="lawyer", role="lawyer")
    assert lawyer.get(mapping[4] + "/decision-identities").status_code == 403


@pytest.mark.parametrize("field", ["contributors", "snapshot_sha256", "version_id", "mapping_revision"])
def test_forged_proposal_and_head_fail_closed(mapping, field):
    mapped(mapping)
    assert propose_identity(mapping).status_code == 200
    store = mapping[0].state.store
    with store.session() as session:
        row = session.scalar(select(DecisionIdentityEvent))
        data = store.decode(row)
        data["event"]["proposal"][field] = {"contributors": [], "snapshot_sha256": "e" * 64,
                                            "version_id": "urn:tr-law:decision-version:forged", "mapping_revision": 10**30}[field]
        session.execute(update(DecisionIdentityEvent).where(DecisionIdentityEvent.id == row.id).values(payload=store.encode(data)))
        session.commit()
    assert mapping[1].get(mapping[4] + "/decision-identities").status_code == 409


def test_accepted_reservation_tampering_detected(mapping):
    mapped(mapping)
    propose_identity(mapping)
    peer = another_client(mapping[0])
    assert review_identity(mapping, peer).status_code == 200
    store = mapping[0].state.store
    with store.session() as session:
        row = session.scalar(select(DecisionIdentityReservation))
        row.payload = store.encode({"binding": "forged"})
        session.commit()
    assert peer.get(mapping[4] + "/decision-identities").status_code == 409


def test_cross_source_reuse_rejected_but_separate_decisions_can_share_proceeding(mapping, incoming):
    mapped(mapping)
    propose_identity(mapping)
    peer = another_client(mapping[0])
    assert review_identity(mapping, peer).status_code == 200
    store, make = incoming
    source_id, package = make("Başvuru Numarası: 2020/5\nKarar No: 2022/7\n", version="second-representation")
    base = f"/api/v1/public-sources/{source_id}"
    candidates = store.jurisprudence_candidates(source_id, "p2")["items"]
    second = (mapping[0], mapping[1], store, source_id, base, candidates, package)
    mapped(second)
    assert propose_identity(second).status_code == 200
    assert review_identity(second, peer).status_code == 409
    changed = {**proposal(second)["identity"], "decision_id": "urn:tr-law:decision:second-decision"}
    assert propose_identity(second, expected_revision=1, identity=changed).status_code == 200
    assert review_identity(second, peer, expected_revision=2).status_code == 200


def test_reservation_not_recycled_after_rejection(mapping):
    mapped(mapping)
    propose_identity(mapping)
    peer = another_client(mapping[0])
    assert review_identity(mapping, peer).status_code == 200
    assert review_identity(mapping, peer, expected_revision=2, decision="rejected").status_code == 200
    changed = {**proposal(mapping)["identity"], "institution_id": "urn:tr-law:institution:another-court"}
    assert propose_identity(mapping, expected_revision=3, identity=changed).status_code == 200
    assert review_identity(mapping, peer, expected_revision=4).status_code == 409


def test_compare_and_swap_and_csrf(mapping):
    mapped(mapping)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: propose_identity(mapping), range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    peer = another_client(mapping[0])
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: review_identity(mapping, peer), range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    peer.headers.pop("X-CSRF-Token")
    assert review_identity(mapping, peer, expected_revision=2).status_code == 403


def test_modified_original_and_mid_write_validation_rollback(mapping, monkeypatch):
    mapped(mapping)
    original = identities.verify_package
    def corrupt(request, source_id, package):
        raw = mapping[2].root / mapping[3] / "raw.bin"
        raw.chmod(0o600)
        raw.write_bytes(b"modified")
        original(request, source_id, package)
    monkeypatch.setattr(identities, "verify_package", corrupt)
    assert propose_identity(mapping).status_code == 409
    with mapping[0].state.store.session() as session:
        assert session.scalar(select(DecisionIdentityHead)) is None
