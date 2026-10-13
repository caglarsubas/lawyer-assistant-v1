"""TEST-ONLY mixed preparation: no publication grant or national corpus."""
import copy

import pytest
from sqlalchemy import event, update
from test_graph_b_snapshot import current as current_fixture
from test_public_sources import source as source_fixture
from test_release_snapshot_set import make_source_set, request_for
from test_source_reviews import assess

from app.config import ROOT
from app.db import User
from app.mixed_graph_snapshot import MixedGraphRequest, locked_mixed_snapshot
from app.release_snapshot import REQUIRED_USES, SnapshotError, readonly_store

current = current_fixture


def prepare(current, tmp_path):
    root = tmp_path / 'mixed-structure-fixture'
    root.mkdir()
    _, inputs, metadata, locators = source_fixture.__wrapped__(root)
    app, owner = current['evidence'][0][0][:2]
    sources = make_source_set((app, owner, None), (current['sources'], inputs, metadata, locators))
    request = MixedGraphRequest(schema_version='legal-mixed-graph-selection-v1',
        structure=request_for(sources), jurisprudence=[current['request']])
    return current, sources, request


def add_second_context(fixture, tmp_path):
    """Actual independent APIs, shared register, distinct canonical proceeding."""
    import json
    from datetime import datetime, timezone

    from test_decision_equivalence import claims, opinion, pins, proof, propose, reference
    from test_decision_identities import mapped, proposal, propose_identity, review_identity
    from test_graph_b_review import accept
    from test_jurisprudence_candidates import incoming
    from test_source_reviews import another_client

    from app.graph_b_snapshot import SnapshotRequest

    current, _, request = fixture
    root = tmp_path / 'second-context-fixture'
    root.mkdir()
    _, inputs, metadata, locators = source_fixture.__wrapped__(root)
    store, make = incoming.__wrapped__((current['sources'], inputs, metadata, locators))
    app, owner = current['evidence'][0][0][:2]
    register = current['evidence'][0][2]
    items = []
    for index in range(2):
        identifier, package = make('Başvuru Numarası: 2020/7\nKarar Tarihi: 12/1/2021\n', version=f'mixed-second-{index}')
        base = f'/api/v1/public-sources/{identifier}'
        candidates = json.loads(owner.get(base+'/jurisprudence-candidates?passage_id=p2').json()['evidence_json'])['items']
        item = app, owner, store, identifier, base, candidates, package
        from app.release_preparation import digest
        mapped(item, export=True, permitted_uses=sorted(REQUIRED_USES), rights_evidence=[
            {"reference": "PRIVATE TEST-ONLY independent source audience proof", "sha256": digest(current["audience"])}])
        identity = {**proposal(item)['identity'], 'decision_id': f'urn:tr-law:decision:mixed-second-{index}',
            'proceeding_id': 'urn:tr-law:proceeding:mixed-second', 'identity_evidence': reference(item),
            'institution_evidence': reference(register)}
        assert propose_identity(item, expected_source_review_revision=6, identity=identity).status_code == 200
        assert review_identity(item, current['evidence'][1], expected_source_review_revision=6, evidence_refs=reference(item)).status_code == 200
        items.append(item)
    evidence = [*items, register], current['evidence'][1], current['evidence'][2]
    assert propose(evidence, claims=claims(evidence, canonical_decision_id='urn:tr-law:decision:mixed-second-0')).status_code == 200
    assert opinion(evidence).status_code == 200
    reviewer = another_client(app, username='mixed-second-signed-reviewer')
    try:
        body = copy.deepcopy(current['signed'][5])
        body.update(pins=pins(evidence), reviewer_id=reviewer.get('/api/v1/auth/me').json()['user']['id'],
            reviewed_at=datetime.now(timezone.utc).isoformat())
        body['qualifications']['decision_date_evidence'] = [proof(item) for item in items]
        originals = current['evidence'][0][:2]
        replacements = {originals[index][3]: items[index][3] for index in range(2)}
        for relation in body['qualifications']['relations']:
            relation['source_id'] = replacements[relation['source_id']]
        signed = app, owner, reviewer, current['signed'][3], current['key'], body
        response = accept(evidence, signed)
        assert response.status_code == 200, response.text
        body = response.json()['current']['envelope']['body']
    finally:
        reviewer.close()
    second = SnapshotRequest(schema_version='signed-graph-b-selection-v1',
        decision_source_ids=sorted(item[3] for item in items), register_source_id=register[3],
        reviewer_id=body['reviewer_id'], expected_review_revision=1, expected_equivalence_revision=2, pins=pins(evidence))
    return (current, fixture[1], MixedGraphRequest.model_validate({**request.model_dump(),
        'jurisprudence': [*request.model_dump()['jurisprudence'], second.model_dump()]})), items


@pytest.fixture
def mixed(current, tmp_path):
    return prepare(current, tmp_path)


def opened(fixture, reader, **changes):
    current, _, request = fixture
    return locked_mixed_snapshot(reader, current['sources'], operator_id=current['operator_id'],
        request=request, trusted_key=current['key'], ontology_root=ROOT / 'ontology', **changes)


def test_both_families_use_one_session_no_writes_and_exact_originals(mixed):
    current, sources, _ = mixed
    connections, statements = set(), []
    with readonly_store(current['app'].state.settings) as reader:
        def capture(connection, cursor, statement, parameters, context, executemany):
            connections.add(id(connection))
            statements.append(statement)
        event.listen(reader.engine, 'before_cursor_execute', capture)
        with opened(mixed, reader, shared=True) as snapshot:
            from app.release_set_preparation import _snapshots
            assert len(_snapshots(snapshot['structure'])[0]) == 2
            assert snapshot['summary']['source_count'] == 5
            assert snapshot['summary']['context_count'] == 1
            assert snapshot['summary']['publication_eligible'] is False
            assert [value['binding']['source_id'] for value in snapshot['structure']['snapshots']] == sorted(item[3] for item in sources)
            assert snapshot['jurisprudence'][0]['binding']['selection'] == current['request'].model_dump()
            assert all(value['package'].artifacts == current['sources'].verified_package(value['binding']['source_id']).artifacts
                       for value in snapshot['structure']['snapshots'])
        assert len(connections) == 1
        assert statements and all(statement.lstrip().upper().startswith(('SELECT', 'SHOW')) for statement in statements)


@pytest.mark.parametrize('family', ['structure', 'jurisprudence'])
def test_either_source_family_revocation_withholds_entire_snapshot(mixed, family):
    current, sources, _ = mixed
    item = sources[0] if family == 'structure' else current['evidence'][0][2]
    assert assess(item[1], item[4]+'/review', 5 if family == 'structure' else 6, 'rights', decision='rejected').status_code == 200
    with readonly_store(current['app'].state.settings) as reader, pytest.raises(SnapshotError), opened(mixed, reader):
        pytest.fail('Every selected current source is required')


@pytest.mark.parametrize('change', ['structure-output', 'jurisprudence-output', 'summary', 'key', 'reviewer'])
def test_late_changes_withhold_dependent_output(mixed, change):
    current = mixed[0]
    with readonly_store(current['app'].state.settings) as reader, pytest.raises(SnapshotError):
        with opened(mixed, reader) as snapshot:
            if change == 'structure-output':
                snapshot['structure']['snapshots'][0]['state']['items'].clear()
            elif change == 'jurisprudence-output':
                snapshot['jurisprudence'][0]['reservations'].clear()
            elif change == 'summary':
                snapshot['summary']['publication_eligible'] = True
            elif change == 'key':
                current['key'].write_bytes(b'changed')
            else:
                with current['app'].state.store.session() as session:
                    session.execute(update(User).where(User.id == current['request'].reviewer_id).values(active=False))
                    session.commit()


def test_closed_selection_rejects_duplicate_and_incomplete_families(mixed):
    data = mixed[2].model_dump()
    for changes in ({'extra': True}, {'jurisprudence': []}, {'jurisprudence': [*data['jurisprudence'], *data['jurisprudence']]}):
        with pytest.raises(ValueError):
            MixedGraphRequest.model_validate({**data, **changes})
    mutated = copy.deepcopy(mixed[2])
    mutated.jurisprudence[0].pins.source_revisions.clear()
    with readonly_store(mixed[0]['app'].state.settings) as reader, pytest.raises(SnapshotError):
        with opened((mixed[0], mixed[1], mutated), reader):
            pytest.fail('Caller-mutated models must be validated again')


@pytest.mark.parametrize('budget', ['MAX_BYTES', 'MAX_PRIVATE_BYTES'])
def test_aggregate_budget_never_yields_partial_family(mixed, monkeypatch, budget):
    from app import mixed_graph_snapshot
    monkeypatch.setattr(mixed_graph_snapshot, budget, 1)
    with readonly_store(mixed[0]['app'].state.settings) as reader, pytest.raises(SnapshotError), opened(mixed, reader):
        pytest.fail('Aggregate limits must withhold the entire snapshot')


def test_sources_owned_by_different_operator_cannot_be_joined(mixed):
    current = mixed[0]
    with readonly_store(current['app'].state.settings) as reader, pytest.raises(SnapshotError):
        with locked_mixed_snapshot(reader, current['sources'], operator_id=current['request'].reviewer_id,
                request=mixed[2], trusted_key=current['key'], ontology_root=ROOT / 'ontology'):
            pytest.fail('Active role alone is insufficient for someone else’s source review')


def test_multiple_contexts_sorted_and_later_member_never_omitted(mixed, tmp_path):
    from app.mixed_graph_snapshot import _fingerprint
    fixture, items = add_second_context(mixed, tmp_path)
    current = fixture[0]
    reversed_request = fixture[2].model_copy(update={'jurisprudence': list(reversed(fixture[2].jurisprudence))})
    with readonly_store(current['app'].state.settings) as reader:
        with opened(fixture, reader, shared=True) as snapshot:
            assert snapshot['summary']['source_count'] == 7 and snapshot['summary']['context_count'] == 2
            before = _fingerprint(snapshot)
        with opened((current, fixture[1], reversed_request), reader, shared=True) as snapshot:
            assert _fingerprint(snapshot) == before
        assert assess(items[0][1], items[0][4]+'/review', 6, 'rights', decision='rejected').status_code == 200
        with pytest.raises(SnapshotError), opened(fixture, reader, shared=True):
            pytest.fail('A valid first member cannot bypass a revoked later member')
