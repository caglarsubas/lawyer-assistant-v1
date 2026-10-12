"""Synthetic retained registers and separate-account review; no actual legal approval."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select, update
from test_decision_identities import mapped, proposal, propose_identity, review_identity
from test_decision_mappings import ready
from test_decision_mappings import review as mapping_review
from test_jurisprudence_candidates import incoming as incoming_fixture
from test_public_sources import source as source_fixture
from test_source_reviews import another_client, assess, assign
from test_workspace import workspace as workspace_fixture

from app import decision_equivalence as equivalence
from app.decision_equivalence_models import DecisionEquivalenceEvent, DecisionEquivalenceHead
from app.decision_identity_models import DecisionIdentityReservation

workspace = workspace_fixture
incoming = incoming_fixture
source = source_fixture


def proof(mapping):
    p = next(p for p in mapping[6].locators.passages if p.id == "p2")
    return {"source_id": mapping[3], "passage_id": p.id, "sha256": p.text_sha256}


def reference(mapping):
    p = proof(mapping)
    return [{"reference": f"source:{p['source_id']}:passage:{p['passage_id']}", "sha256": p["sha256"]}]


def prepare(app, client, store, make, *, permitted_uses=None, rights_evidence=None):
    app.state.settings.public_source_dir = store.root
    mappings = []
    for index in range(3):
        text = "Başvuru Numarası: 2020/5\nKarar Tarihi: 12/1/2021\n" if index < 2 else "Synthetic retained court identity register record 7; no competence rule.\n"
        source_id, package = make(text, version=f"equivalence-synthetic-{index}")
        base = f"/api/v1/public-sources/{source_id}"
        candidates = json.loads(client.get(base + "/jurisprudence-candidates?passage_id=p2").json()["evidence_json"])["items"]
        item = (app, client, store, source_id, base, candidates, package)
        source_rights = rights_evidence(index, item) if callable(rights_evidence) else rights_evidence
        if index < 2:
            mapped(item, export=True, permitted_uses=permitted_uses, rights_evidence=source_rights)
        else:
            ready(item)
            assert assess(client, base + "/review", 5, "rights", permitted_uses=permitted_uses or ["local_processing", "internal_display", "export"],
                          **({"evidence_refs": source_rights} if source_rights else {})).status_code == 200
        mappings.append(item)
    identity_reviewer = another_client(app, username="identity-peer")
    for index, item in enumerate(mappings[:2]):
        identity = {**proposal(item)["identity"], "decision_id": f"urn:tr-law:decision:synthetic-{index}",
                    "identity_evidence": reference(item), "institution_evidence": reference(mappings[2])}
        result = propose_identity(item, expected_source_review_revision=6, identity=identity)
        assert result.status_code == 200, result.text
        assert review_identity(item, identity_reviewer, expected_source_review_revision=6, evidence_refs=reference(item)).status_code == 200
    reviewer = another_client(app, username="equivalence-peer")
    return mappings, identity_reviewer, reviewer


@pytest.fixture
def evidence_set(tmp_path, synthetic_equivalence_seed):
    from graph_b_test_seeds import cloned_equivalence
    with cloned_equivalence(synthetic_equivalence_seed, tmp_path) as value:
        yield value


def endpoint(evidence_set, *, review=False, reverse=False):
    items = evidence_set[0]
    left, right = (items[1], items[0]) if reverse else (items[0], items[1])
    return left[4] + "/decision-equivalence" + ("/review" if review else "") + f"?peer_source_id={right[3]}&register_source_id={items[2][3]}"


def pins(evidence_set):
    items = evidence_set[0]
    return {"source_revisions": {item[3]: 6 for item in items}, "mapping_revisions": {item[3]: 2 if i < 2 else 0 for i, item in enumerate(items)},
            "identity_revisions": {item[3]: 2 for item in items[:2]}}


def claims(evidence_set, **changes):
    return {"relation": "same_decision", "canonical_decision_id": "urn:tr-law:decision:synthetic-0" if changes.get("relation", "same_decision") == "same_decision" else None,
            "institution_id": "urn:tr-law:institution:synthetic-court",
            "registered_name": "Synthetic identity-only court", "register_record_id": "synthetic register record 7",
            "evidence": [proof(item) for item in evidence_set[0]], **changes}


def propose(evidence_set, client=None, **changes):
    client = client or evidence_set[0][0][1]
    return client.post(endpoint(evidence_set), json={"expected_revision": 0, "pins": pins(evidence_set),
        "rationale": "Synthetic source-version comparison with retained institutional identity evidence", "claims": claims(evidence_set), **changes})


def opinion(evidence_set, client=None, **changes):
    return (client or evidence_set[2]).post(endpoint(evidence_set, review=True), json={"expected_revision": 1, "pins": pins(evidence_set),
        "rationale": "Synthetic independent comparison; not legal competence approval", "decision": "accepted",
        "evidence": [proof(item) for item in evidence_set[0]], **changes})


def test_private_reversible_pair_full_history_register_and_reservations_unchanged(evidence_set):
    items, _, reviewer = evidence_set
    app, client, store = items[0][:3]
    original = {item[3]: dict(item[6].artifacts) for item in items}
    with app.state.store.session() as session:
        reservations = {r.canonical_id: r.payload for r in session.scalars(select(DecisionIdentityReservation))}
    assert client.get(endpoint(evidence_set)).json()["revision"] == 0
    assert propose(evidence_set).status_code == 200
    response = opinion(evidence_set)
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["same_decision_supported"] and state["review_accepted"] and state["history_complete"]
    assert state["current"]["proposal"]["claims"]["canonical_decision_id"] == "urn:tr-law:decision:synthetic-0"
    assert {value["decision_id"] for value in state["decisions"].values()} == {"urn:tr-law:decision:synthetic-0", "urn:tr-law:decision:synthetic-1"}
    assert state["confidentiality"] == "firm_confidential" and state["firm_id"] == "demo-firm"
    assert state["history"][0]["actor"]["id"] != state["history"][1]["actor"]["id"]
    for key in ("identity_reservations_changed", "global_registry_qualified", "legal_effect_verified", "institutional_competence_verified", "publication_eligible"):
        assert state[key] is False
    reverse = reviewer.get(endpoint(evidence_set, reverse=True)).json()
    assert reverse["context_id"] == state["context_id"] and reverse["history"] == state["history"]
    with app.state.store.session() as session:
        assert reservations == {r.canonical_id: r.payload for r in session.scalars(select(DecisionIdentityReservation))}
        for row in [session.scalar(select(DecisionEquivalenceHead)), *session.scalars(select(DecisionEquivalenceEvent))]:
            assert "Synthetic identity-only court" not in row.payload
        with pytest.raises(ValueError, match="append-only"):
            row = session.scalar(select(DecisionEquivalenceEvent))
            row.created_at = "changed"
            session.flush()
    assert original == {item[3]: store.verified_package(item[3]).artifacts for item in items}


def test_independence_includes_prior_identity_reviewers_and_proposer(evidence_set):
    assert propose(evidence_set).status_code == 200
    assert opinion(evidence_set, evidence_set[0][0][1]).status_code == 403
    assert opinion(evidence_set, evidence_set[1]).status_code == 403
    assert opinion(evidence_set).status_code == 200


def test_disagreement_and_unknown_relation_are_preserved_without_merge(evidence_set):
    assert propose(evidence_set, claims=claims(evidence_set, relation="undetermined")).status_code == 200
    first = opinion(evidence_set, decision="needs_changes")
    assert first.status_code == 200 and not first.json()["same_decision_supported"]
    rejected = opinion(evidence_set, expected_revision=2, decision="rejected")
    assert rejected.status_code == 200
    assert propose(evidence_set, expected_revision=3, claims=claims(evidence_set, relation="different_decision")).status_code == 200
    result = opinion(evidence_set, expected_revision=4)
    assert result.status_code == 200 and result.json()["review_accepted"] and not result.json()["same_decision_supported"]
    assert [e["decision"] for e in result.json()["history"]] == ["accepted", None, "rejected", "needs_changes", None]


@pytest.mark.parametrize("index", [0, 1, 2])
def test_every_source_review_change_makes_equivalence_stale(evidence_set, index):
    assert propose(evidence_set).status_code == opinion(evidence_set).status_code == 200
    item = evidence_set[0][index]
    assert assess(item[1], item[4] + "/review", 6, "legal").status_code == 200
    state = item[1].get(endpoint(evidence_set)).json()
    assert state["stale"] and not state["review_accepted"] and not state["same_decision_supported"]
    assert opinion(evidence_set, expected_revision=2).status_code == 409


def test_ownership_transfer_cannot_erase_register_contributors(evidence_set):
    item = evidence_set[0][2]
    client = item[1]
    assert assign(client, item[4] + "/review", 6, "release").status_code == 200
    assert assign(evidence_set[2], item[4] + "/review", 7).status_code == 200
    new_pins = pins(evidence_set)
    new_pins["source_revisions"][item[3]] = 8
    assert propose(evidence_set, pins=new_pins).status_code == 200
    assert opinion(evidence_set, pins=new_pins).status_code == 403


@pytest.mark.parametrize("change", ["wrong_hash", "missing_register", "unknown_source", "unreviewed_passage", "duplicate"])
def test_exact_all_source_passage_proofs_required(evidence_set, change):
    refs = claims(evidence_set)["evidence"]
    if change == "wrong_hash":
        refs[0]["sha256"] = "f" * 64
    if change == "missing_register":
        refs[2] = {**refs[0], "passage_id": "p1"}
    if change == "unknown_source":
        refs[2]["source_id"] = "f" * 64
    if change == "unreviewed_passage":
        refs[2]["passage_id"] = "absent"
    if change == "duplicate":
        refs[2] = refs[0]
    assert propose(evidence_set, claims=claims(evidence_set, evidence=refs)).status_code in {409, 422}
    assert evidence_set[0][0][1].get(endpoint(evidence_set)).json()["revision"] == 0


@pytest.mark.parametrize("change", ["boolean", "huge_identity", "wrong_pin", "extra", "unknown_relation", "wrong_institution", "control_name"])
def test_closed_bounded_typed_contract(evidence_set, change):
    body = {}
    values = pins(evidence_set)
    first = evidence_set[0][0][3]
    if change == "boolean":
        values["identity_revisions"][first] = True
    if change == "huge_identity":
        values["identity_revisions"][first] = 10**18
    if change == "wrong_pin":
        values["source_revisions"][first] = 5
    if change == "extra":
        body["publish"] = True
    if change == "unknown_relation":
        body["claims"] = claims(evidence_set, relation="owl:sameAs")
    if change == "wrong_institution":
        body["claims"] = claims(evidence_set, institution_id="urn:tr-law:institution:other")
    if change == "control_name":
        body["claims"] = claims(evidence_set, registered_name="name\nsecret")
    assert propose(evidence_set, pins=values, **body).status_code in {409, 422}


def test_ledger_projection_and_contributor_forgery_withheld(evidence_set):
    assert propose(evidence_set).status_code == 200
    app, client = evidence_set[0][0][:2]
    store = app.state.store
    with store.session() as session:
        head = session.scalar(select(DecisionEquivalenceHead))
        row = session.scalar(select(DecisionEquivalenceEvent))
        data = store.decode(row)
        data["event"]["proposal"]["contributors"] = []
        session.execute(update(DecisionEquivalenceEvent).where(DecisionEquivalenceEvent.id == row.id).values(payload=store.encode(data)))
        projection = store.decode(head)
        projection["event"] = data["event"]
        head.payload = store.encode(projection)
        session.commit()
    assert client.get(endpoint(evidence_set)).status_code == 409
    assert opinion(evidence_set).status_code == 409


def test_role_firm_csrf_and_source_selection_boundaries(evidence_set):
    assert propose(evidence_set).status_code == 200
    app, client = evidence_set[0][0][:2]
    foreign = another_client(app, username="foreign", firm="foreign-firm")
    result = foreign.get(endpoint(evidence_set))
    assert result.status_code == 200 and result.json()["history"] == []
    assert opinion(evidence_set, foreign).status_code == 409
    lawyer = another_client(app, username="lawyer", role="lawyer")
    assert lawyer.get(endpoint(evidence_set)).status_code == 403
    client.headers.pop("X-CSRF-Token")
    assert propose(evidence_set, expected_revision=1).status_code == 403
    register = evidence_set[0][2][3]
    assert evidence_set[2].get(endpoint(evidence_set).replace(register, evidence_set[0][0][3])).status_code == 422


def test_optimistic_duplicate_proposal_only_one_wins(evidence_set):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: propose(evidence_set), range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert evidence_set[0][0][1].get(endpoint(evidence_set)).json()["revision"] == 1


@pytest.mark.parametrize("budget", ["MAX_CAPTURE_BYTES", "MAX_LEDGER_BYTES"])
def test_full_history_budgets_fail_closed(evidence_set, monkeypatch, budget):
    assert propose(evidence_set).status_code == 200
    monkeypatch.setattr(equivalence, budget, 1)
    assert evidence_set[0][0][1].get(endpoint(evidence_set)).status_code == 409


def test_mapping_and_identity_reapproval_do_not_silently_refresh_equivalence(evidence_set):
    assert propose(evidence_set).status_code == opinion(evidence_set).status_code == 200
    item = evidence_set[0][1]
    mapping_id = item[1].get(item[4] + "/decision-mappings").json()["items"][0]["id"]
    assert mapping_review(item, mapping_id, revision=2, source_revision=6).status_code == 200
    state = item[1].get(endpoint(evidence_set)).json()
    assert state["stale"] and not state["inputs_ready"]
    identity = {**proposal(item)["identity"], "decision_id": "urn:tr-law:decision:synthetic-1", "identity_evidence": reference(item), "institution_evidence": reference(evidence_set[0][2])}
    assert propose_identity(item, expected_revision=2, expected_mapping_revision=3, expected_source_review_revision=6, identity=identity).status_code == 200
    assert review_identity(item, evidence_set[1], expected_revision=3, expected_mapping_revision=3, expected_source_review_revision=6, evidence_refs=reference(item)).status_code == 200
    state = item[1].get(endpoint(evidence_set)).json()
    assert state["stale"] and state["inputs_ready"] and not state["review_accepted"]


def test_same_decision_cannot_hide_different_proceedings(evidence_set):
    item = evidence_set[0][1]
    identity = {**proposal(item)["identity"], "decision_id": "urn:tr-law:decision:synthetic-other", "proceeding_id": "urn:tr-law:proceeding:other",
                "identity_evidence": reference(item), "institution_evidence": reference(evidence_set[0][2])}
    assert propose_identity(item, expected_revision=2, expected_source_review_revision=6, identity=identity).status_code == 200
    assert review_identity(item, evidence_set[1], expected_revision=3, expected_source_review_revision=6, evidence_refs=reference(item)).status_code == 200
    values = pins(evidence_set)
    values["identity_revisions"][item[3]] = 4
    assert propose(evidence_set, pins=values).status_code == 409
    assert propose(evidence_set, pins=values, claims=claims(evidence_set, relation="different_decision")).status_code == 200


def test_unresolved_identity_register_reference_withholds_comparison(evidence_set):
    item = evidence_set[0][1]
    identity = {**proposal(item)["identity"], "decision_id": "urn:tr-law:decision:synthetic-1", "identity_evidence": reference(item)}
    assert propose_identity(item, expected_revision=2, expected_source_review_revision=6, identity=identity).status_code == 200
    assert review_identity(item, evidence_set[1], expected_revision=3, expected_source_review_revision=6, evidence_refs=reference(item)).status_code == 200
    values = pins(evidence_set)
    values["identity_revisions"][item[3]] = 4
    assert propose(evidence_set, pins=values).status_code == 409


def test_changed_original_during_proposal_rolls_back_private_event(evidence_set, monkeypatch):
    original = equivalence.verify
    item = evidence_set[0][2]
    def changed(request, packages, user):
        original_path = item[2].root / item[3] / "raw.bin"
        original_path.chmod(0o600)  # Simulate an operator tampering outside the application.
        original_path.write_bytes(b"changed synthetic original")
        return original(request, packages, user)
    monkeypatch.setattr(equivalence, "verify", changed)
    assert propose(evidence_set).status_code == 409
    with item[0].state.store.session() as session:
        assert session.scalar(select(DecisionEquivalenceHead)) is None


def test_missing_old_event_or_projection_cannot_hide_later_rejection(evidence_set):
    assert propose(evidence_set).status_code == opinion(evidence_set).status_code == 200
    assert opinion(evidence_set, expected_revision=2, decision="rejected").status_code == 200
    app, client = evidence_set[0][0][:2]
    with app.state.store.session() as session:
        head = session.scalar(select(DecisionEquivalenceHead))
        old = session.scalar(select(DecisionEquivalenceEvent).where(DecisionEquivalenceEvent.revision == 2))
        payload = app.state.store.decode(head)
        payload["event"] = app.state.store.decode(old)["event"]
        head.payload = app.state.store.encode(payload)
        session.commit()
    assert client.get(endpoint(evidence_set)).status_code == 409


@pytest.mark.parametrize("value", [None, "urn:tr-law:decision:not-one-of-the-reviewed-identities"])
def test_same_decision_requires_explicit_existing_canonical_candidate(evidence_set, value):
    assert propose(evidence_set, claims=claims(evidence_set, canonical_decision_id=value)).status_code in {409, 422}
