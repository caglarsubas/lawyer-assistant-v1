"""Private historical review identity/ancestry is not current evidence access."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from test_analysis_authorities import mutate
from test_analysis_comparisons import login
from test_authority_adjudications import reviewer
from test_portfolio_source_reviews import other_case
from test_source_analysis_reviews import freeze, record, review_request, reviewed, setup
from test_source_analysis_reviews import workbench as workbench_fixture
from test_source_review_readiness import no_public_reads

from app import source_analysis_reviews as reviews
from app.db import Membership, Record, User, digest

workbench = workbench_fixture


def review_receipt(body, context):
    from app.evidence_prompt import canonical
    return {'request_id': body['request_id'], 'expected_request_sha256': digest(canonical({key: value for key, value in body.items() if key != 'request_id'})),
        'expected_manifest_sha256': context['manifest_sha256'], 'version_id': context['manifest']['version_id'],
        **({'expected_review_id': body['expected_review_id']} if body['expected_review_id'] else {})}


def reconcile_review(client, endpoint, context, receipt):
    response = client.get(endpoint + '/' + context['id'] + '/reviews/reconciliation', params=receipt)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    for secret in ['PRIVATE SOURCE NOTE', 'PRIVATE REVIEW NOTE', 'TEST ONLY 📄', 'sources', 'recorded_by', 'target_snapshots', 'purpose']:
        assert secret not in response.text
    result = response.json()
    assert result['source_verification'] == 'not_checked' and result['current_head'] == 'not_checked'
    assert result['legal_readiness'] == 'not_established' and not result['qualification_granted'] and not result['effects_replayed']
    return result


def no_reconciliation_effects(app, monkeypatch, reader):
    no_public_reads(monkeypatch, reader)
    monkeypatch.setattr(reviews, '_head', lambda *_a, **_k: pytest.fail('Do not substitute or read the current head'))
    monkeypatch.setattr(reviews, '_finalize', lambda *_a, **_k: pytest.fail('No admission repair'))
    monkeypatch.setattr(app.state.store, 'add', lambda *_a, **_k: pytest.fail('No new records'))
    monkeypatch.setattr(app.state.store, 'update', lambda *_a, **_k: pytest.fail('No record changes'))


def test_review_reconciliation_finds_exact_request_after_later_opposing_head_and_source_withdrawal(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, _, reader, permit = setup(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    reviewer(workbench)
    path, first = review_request(client, endpoint, context['id'])
    original = record(client, path, first)
    path, second = review_request(client, endpoint, context['id'], decision='changes_requested')
    selected = record(client, path, second)
    path, third = review_request(client, endpoint, context['id'])
    later = record(client, path, third)
    assert later['review']['id'] != selected['review']['id']
    permit.active = False
    with app.state.store.session() as session:
        before = {row.id: (row.revision, row.payload) for row in session.scalars(select(Record))}
    no_reconciliation_effects(app, monkeypatch, reader)
    value = reconcile_review(client, endpoint, context, review_receipt(second, context))
    assert value['outcome'] == 'verified' and value['review']['id'] == selected['review']['id']
    assert value['review']['packet_sha256'] == selected['review']['snapshot']['packet_sha256']
    assert value['review']['previous_review_id'] == original['review']['id']
    assert value['review']['previous_review_packet_sha256'] == original['review']['snapshot']['packet_sha256']
    assert value['review']['state'] == 'changes_requested' and value['review']['sequence'] == 2
    assert value['context']['version_id'] == context['manifest']['version_id']
    assert value['admission'] == {'context': 'complete', 'review': 'complete', 'predecessor': 'complete'}
    with app.state.store.session() as session:
        assert before == {row.id: (row.revision, row.payload) for row in session.scalars(select(Record))}


@pytest.mark.parametrize('fault', ['pending_context', 'pending_review', 'pending_predecessor', 'invalid_context_proof', 'invalid_review_proof', 'invalid_predecessor_proof', 'immutable', 'prior_immutable', 'missing_admission', 'tampered', 'request_hash', 'manifest_hash', 'version', 'nonce', 'predecessor', 'sequence', 'request_nonce', 'request_rehash', 'owner', 'recipe'])
def test_review_reconciliation_withholds_unknown_mismatch_and_pending_without_replay(workbench, monkeypatch, fault):
    app, client, *_ = workbench
    endpoint, spec, _, reader, _ = setup(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    reviewer(workbench)
    path, body = review_request(client, endpoint, context['id'])
    first = record(client, path, body)
    path, sent = review_request(client, endpoint, context['id'])
    event = record(client, path, sent)
    ident = event['review']['id']
    receipt = review_receipt(sent, context)
    if fault.startswith('pending_'):
        target = {'pending_context': context['id'], 'pending_review': ident, 'pending_predecessor': first['review']['id']}[fault]
        mutate(app, reviews._id('saa-', target), lambda p: p.update(guard_completed=False))
    elif fault.startswith('invalid_'):
        target = {'invalid_context_proof': context['id'], 'invalid_review_proof': ident, 'invalid_predecessor_proof': first['review']['id']}[fault]
        mutate(app, reviews._id('saa-', target), lambda p: p.update(guard_completed='unknown'))
    elif fault == 'immutable':
        reseal(app, ident, lambda p: p.update(immutable=False))
    elif fault == 'prior_immutable':
        reseal(app, first['review']['id'], lambda p: p.update(immutable=False))
    elif fault == 'missing_admission':
        with app.state.store.session() as session:
            session.execute(delete(Record).where(Record.id == reviews._id('saa-', ident)))
            session.commit()
    elif fault == 'tampered':
        mutate(app, ident, lambda p: p['input'].update(note='CORRUPTED PRIVATE REVIEW NOTE'))
    elif fault in {'sequence', 'request_nonce', 'request_rehash', 'recipe'}:
        def change(p):
            if fault == 'sequence':
                p['sequence'] = 40
            elif fault == 'request_nonce':
                p['input']['request_id'] = uuid4().hex
            elif fault == 'request_rehash':
                p['input']['note'] = 'PRIVATE changed input with stale digest'
            else:
                p['recipe'] = 'unknown-review-recipe'
        reseal(app, ident, change)
    elif fault == 'owner':
        with app.state.store.session() as session:
            row = session.get(Record, ident)
            row.owner_id = session.scalar(select(User).where(User.username == 'demo')).id
            session.commit()
        decode = app.state.store.decode
        def scoped(row):
            assert row.id != ident, 'Foreign-owner event must not be decrypted'
            return decode(row)
        monkeypatch.setattr(app.state.store, 'decode', scoped)
    elif fault == 'predecessor':
        receipt.pop('expected_review_id')
    else:
        key = {'request_hash': 'expected_request_sha256', 'manifest_hash': 'expected_manifest_sha256', 'version': 'version_id', 'nonce': 'request_id'}[fault]
        receipt[key] = '0' * (32 if fault == 'nonce' else 64) if fault != 'version' else 'different'
    no_reconciliation_effects(app, monkeypatch, reader)
    value = reconcile_review(client, endpoint, context, receipt)
    if fault.startswith('pending_'):
        assert value['outcome'] == 'verified' and value['admission'][fault.removeprefix('pending_')] == 'pending'
    else:
        assert value['outcome'] == ('not_observed' if fault == 'nonce' else 'unavailable')
        assert value['context'] is value['review'] is value['admission'] is None


def test_review_reconciliation_original_actor_membership_and_closed_query_boundary(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, _, reader, _ = setup(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    reviewer(workbench)
    path, sent = review_request(client, endpoint, context['id'])
    event = record(client, path, sent)
    receipt = review_receipt(sent, context)
    decode = app.state.store.decode
    def scoped(row):
        assert row.id != event['review']['id'], 'Other actor must not decrypt the submitted event'
        return decode(row)
    monkeypatch.setattr(app.state.store, 'decode', scoped)
    login(client)  # Admin and source author cannot resolve another lawyer's request.
    assert reconcile_review(client, endpoint, context, receipt)['outcome'] == 'not_observed'
    login(client, 'reviewer')
    with app.state.store.session() as session:
        actor = session.scalar(select(User).where(User.username == 'reviewer'))
        session.execute(delete(Membership).where(Membership.user_id == actor.id))
        session.commit()
    target = endpoint + '/' + context['id'] + '/reviews/reconciliation'
    assert client.get(target, params=receipt).status_code == 404
    for params in [{**receipt, 'note': 'PRIVATE'}, list(receipt.items()) + [('request_id', receipt['request_id'])], {**receipt, 'request_id': 'bad'}]:
        assert client.get(target, params=params).status_code == 422


def test_pending_review_committed_before_finalize_is_observed_without_admission_repair(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, _, reader, _ = setup(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    reviewer(workbench)
    path, sent = review_request(client, endpoint, context['id'])
    def fail(*_a, **_k):
        raise RuntimeError('TEST ONLY lost post-commit response')
    monkeypatch.setattr(reviews, '_finalize', fail)
    response = client.post(path, json=sent)
    assert response.status_code == 409 and response.json()['outcome'] == 'committed_needs_revalidation'
    no_reconciliation_effects(app, monkeypatch, reader)
    value = reconcile_review(client, endpoint, context, review_receipt(sent, context))
    assert value['outcome'] == 'verified' and value['review']['id'] == response.json()['id']
    assert value['review']['sequence'] == 1 and value['review']['previous_review_id'] is None
    assert value['admission'] == {'context': 'complete', 'review': 'pending', 'predecessor': 'not_recorded'}


def test_review_reconciliation_rejects_mixed_context_or_foreign_routing_before_decryption(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    other, _ = freeze(client, endpoint, spec)
    reviewer(workbench)
    path, sent = review_request(client, endpoint, context['id'])
    record(client, path, sent)
    receipt = review_receipt(sent, context)
    receipt['expected_review_id'] = 'sar-' + digest(context['id'])[:20] + '-' + uuid4().hex
    monkeypatch.setattr(app.state.store, 'decode', lambda *_: pytest.fail('Routing must close before decryption'))
    assert client.get(endpoint + '/' + other['id'] + '/reviews/reconciliation', params=receipt).status_code == 404
    foreign = 'sac-' + 'f' * 20 + '-' + uuid4().hex
    assert client.get(endpoint + '/' + foreign + '/reviews/reconciliation', params=receipt).status_code == 404


def read(client, endpoint, context_id, review_id, **params):
    response = client.get(endpoint + '/' + context_id + '/reviews/' + review_id + '/navigation-context', params=params)
    assert response.status_code == 200, response.text
    value = response.json()
    assert response.headers['cache-control'] == 'no-store'
    assert value['source_verification'] == 'not_checked' and value['legal_readiness'] == 'not_established'
    assert not value['qualification_granted']
    for secret in ['TEST ONLY 📄', 'PRIVATE SOURCE NOTE', 'PRIVATE REVIEW NOTE', 'recorded_by', 'target_snapshots',
                   'source_candidates', 'analysis_content', 'sources', 'purpose']:
        assert secret not in response.text
    return value


def chain(workbench, monkeypatch, size=3):
    endpoint, spec, analysis, reader, permit, context, first, *_ = reviewed(workbench, monkeypatch)
    events = [first['review']['id']]
    for index in range(1, size):
        path, body = review_request(workbench[1], endpoint, context['id'],
            decision='changes_requested' if index % 2 else 'reviewed_conditional')
        events.append(record(workbench[1], path, body)['review']['id'])
    return endpoint, context, events, reader, permit


def test_selected_positive_is_separate_from_later_conflict_and_keeps_its_exact_hash(workbench, monkeypatch):
    endpoint, context, events, reader, permit = chain(workbench, monkeypatch, 2)
    client = workbench[1]
    original = client.get(endpoint + '/' + context['id'] + '/reviews/' + events[0]).json()
    assert original['review']['is_latest'] is False and original['manifest_sha256'] == context['manifest_sha256']
    permit.active = False
    assert client.get(endpoint + '/' + context['id'] + '/reviews/' + events[0]).json()['manifest'] is None
    no_public_reads(monkeypatch, reader)
    value = read(client, endpoint, context['id'], events[0])
    assert value['selected_review']['state'] == 'reviewed_conditional'
    assert value['current_head']['state'] == 'changes_requested'
    assert value['current_head']['id'] == events[1]
    assert value['head_relationship'] == 'different_from_head'
    assert value['selected_review']['packet_sha256'] == original['review']['snapshot']['packet_sha256']
    assert value['selected_review']['manifest_sha256'] == context['manifest_sha256']
    assert value['lineage']['items'] == [value['selected_review']]
    assert value['lineage']['head_reachability'] == 'not_checked' and value['lineage']['total_count'] is None


@pytest.mark.parametrize('window', [1, 3, 10])
def test_bounded_ancestry_truncates_without_scanning_or_claiming_full_history(workbench, monkeypatch, window):
    endpoint, context, events, reader, _ = chain(workbench, monkeypatch, 11)
    no_public_reads(monkeypatch, reader)
    value = read(workbench[1], endpoint, context['id'], events[-1], window=window)
    assert value['lineage']['status'] == 'truncated'
    assert [row['id'] for row in value['lineage']['items']] == list(reversed(events))[:window]
    assert value['lineage']['next_review_id'] == events[-window - 1]
    assert value['head_relationship'] == 'current_head'
    older = read(workbench[1], endpoint, context['id'], events[1])
    assert [row['sequence'] for row in older['lineage']['items']] == [2, 1]
    assert older['lineage']['status'] == 'complete_to_first_event'


@pytest.mark.parametrize('fault', ['pending_selected', 'missing_selected', 'pending_head', 'missing_predecessor', 'tampered_selected', 'tampered_head'])
def test_admission_and_integrity_gaps_do_not_repair_or_replace_events(workbench, monkeypatch, fault):
    app, client, *_ = workbench
    endpoint, context, events, reader, _ = chain(workbench, monkeypatch)
    selected = events[1]
    if fault.startswith('pending'):
        target = selected if fault == 'pending_selected' else events[-1]
        mutate(app, reviews._id('saa-', target), lambda packet: packet.update(guard_completed=False))
    elif fault.startswith('missing'):
        target = selected if fault == 'missing_selected' else events[0]
        with app.state.store.session() as session:
            session.execute(delete(Record).where(Record.id == reviews._id('saa-', target)))
            session.commit()
    else:
        target = selected if fault == 'tampered_selected' else events[-1]
        mutate(app, target, lambda packet: packet['input'].update(note='CORRUPTED PRIVATE NOTE'))
    no_public_reads(monkeypatch, reader)
    with app.state.store.session() as session:
        before = {row.id: row.revision for row in session.scalars(select(Record)).all()}
    value = read(client, endpoint, context['id'], selected)
    assert value['review_id'] == value['selected_review']['id'] == selected
    if fault == 'pending_selected':
        assert value['selected_review']['admission'] == 'pending' and not value['tools_available']
    elif fault in {'missing_selected', 'tampered_selected'}:
        assert value['selected_review']['integrity'] == 'unavailable' and not value['tools_available']
        assert value['selected_review']['packet_sha256'] is None and value['lineage']['status'] == 'unavailable'
    elif fault == 'pending_head':
        assert value['current_head']['admission'] == 'pending'
        assert value['selected_review']['admission'] == 'complete'
    elif fault == 'missing_predecessor':
        assert value['lineage']['status'] == 'unavailable' and len(value['lineage']['items']) == 1
    else:
        assert value['current_head'] is None and value['head_relationship'] == 'unestablished'
        assert value['selected_review']['integrity'] == 'verified'
    with app.state.store.session() as session:
        assert before == {row.id: row.revision for row in session.scalars(select(Record)).all()}


def reseal(app, ident, change):
    with app.state.store.session() as session:
        row = session.get(Record, ident)
        value = app.state.store.decode(row)
        change(value)
        value['packet_sha256'] = digest(reviews.canonical({key: item for key, item in value.items() if key != 'packet_sha256'}))
        app.state.store.update(row, value)
        proof_row = session.get(Record, reviews._id('saa-', ident))
        proof = app.state.store.decode(proof_row)
        proof['packet_sha256'] = value['packet_sha256']
        app.state.store.update(proof_row, proof)
        session.commit()


@pytest.mark.parametrize('fault', ['sequence_gap', 'cycle', 'wrong_recipe', 'foreign_predecessor'])
def test_resealed_but_inconsistent_history_is_not_promoted_to_verified_ancestry(workbench, monkeypatch, fault):
    endpoint, context, events, reader, _ = chain(workbench, monkeypatch)
    if fault == 'sequence_gap':
        reseal(workbench[0], events[1], lambda value: value.update(sequence=30))
    elif fault == 'wrong_recipe':
        reseal(workbench[0], events[1], lambda value: value.update(recipe='future-unknown'))
    else:
        def change(value):
            pointer = events[1] if fault == 'cycle' else 'sar-' + 'f' * 20 + '-' + uuid4().hex
            value.update(previous_review_id=pointer)
            value['input']['expected_review_id'] = pointer
        reseal(workbench[0], events[1], change)
    no_public_reads(monkeypatch, reader)
    value = read(workbench[1], endpoint, context['id'], events[1])
    assert value['lineage']['status'] == 'unavailable' and value['lineage']['next_review_id'] is None
    assert value['review_id'] == events[1]


def test_mixed_cross_context_foreign_missing_ids_and_lost_content_grant_never_decrypt_foreign_events(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, _, reader, _ = setup(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    other_context, _ = freeze(client, endpoint, spec)
    reviewer(workbench)
    path, body = review_request(client, endpoint, context['id'])
    event = record(client, path, body)['review']['id']
    _, _, foreign_endpoint, _, _, _, foreign = other_case(workbench, monkeypatch)
    login(client, 'reviewer')
    decode = app.state.store.decode
    def scoped(row):
        if row.matter_id and row.matter_id != workbench[2].split('/')[-1]:
            pytest.fail('Foreign packet decrypted')
        return decode(row)
    monkeypatch.setattr(app.state.store, 'decode', scoped)
    assert client.get(endpoint + '/' + other_context['id'] + '/reviews/' + event + '/navigation-context').status_code == 404
    assert client.get(foreign_endpoint + '/' + foreign['id'] + '/reviews/' + event + '/navigation-context').status_code == 404
    absent = 'sar-' + digest(context['id'])[:20] + '-' + uuid4().hex
    assert client.get(endpoint + '/' + context['id'] + '/reviews/' + absent + '/navigation-context').status_code == 404
    with app.state.store.session() as session:
        actor = session.scalar(select(User).where(User.username == 'reviewer'))
        session.execute(delete(Membership).where(Membership.user_id == actor.id))
        session.commit()
    assert client.get(endpoint + '/' + context['id'] + '/reviews/' + event + '/navigation-context').status_code == 404


@pytest.mark.parametrize('window', [0, 11, -1, 'all'])
def test_unsupported_work_windows_are_rejected(workbench, monkeypatch, window):
    endpoint, context, events, _, _ = chain(workbench, monkeypatch, 1)
    assert workbench[1].get(endpoint + '/' + context['id'] + '/reviews/' + events[0] + '/navigation-context', params={'window': window}).status_code == 422


def test_historical_actor_grant_loss_does_not_erase_history_or_authorize_quote_read(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, context, events, reader, _ = chain(workbench, monkeypatch, 1)
    login(client)
    with app.state.store.session() as session:
        actor = session.scalar(select(User).where(User.username == 'reviewer'))
        session.execute(delete(Membership).where(Membership.user_id == actor.id))
        session.commit()
    guarded = client.get(endpoint + '/' + context['id'] + '/reviews/' + events[0])
    assert guarded.status_code == 200 and guarded.json()['manifest'] is None
    no_public_reads(monkeypatch, reader)
    value = read(client, endpoint, context['id'], events[0])
    assert value['selected_review']['state'] == 'reviewed_conditional'
    assert value['source_verification'] == 'not_checked'


def test_missing_context_admission_leaves_selected_identity_unknown_without_event_decode(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, context, events, reader, _ = chain(workbench, monkeypatch, 1)
    with app.state.store.session() as session:
        session.execute(delete(Record).where(Record.id == reviews._id('saa-', context['id'])))
        session.commit()
    no_public_reads(monkeypatch, reader)
    decode = app.state.store.decode
    def scoped(row):
        if row.id == events[0]:
            pytest.fail('Unadmitted context cannot expose event contents')
        return decode(row)
    monkeypatch.setattr(app.state.store, 'decode', scoped)
    value = read(client, endpoint, context['id'], events[0])
    assert value['selected_review']['state'] == 'unknown' and not value['tools_available']
    assert value['selected_review']['packet_sha256'] is None
