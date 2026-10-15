"""Invented private renewal/version comparisons; no legal qualification."""

import copy
import io
import json
from contextlib import contextmanager
from uuid import uuid4

import pytest
from docx import Document
from pypdf import PdfReader
from sqlalchemy import select
from test_analysis_authorities import mutate
from test_analysis_comparisons import login
from test_authority_adjudications import reviewer
from test_source_analysis_reviews import freeze, record, review_request, setup
from test_source_analysis_reviews import workbench as workbench_fixture
from test_source_corpus import passage

from app import source_analysis_reviews as reviews
from app.db import Record, User, digest
from app.evidence_prompt import canonical
from app.source_corpus import SourceCorpusService

workbench = workbench_fixture


def renewal_spec(client, endpoint, spec, parent_id):
    response = client.get(endpoint + '/' + parent_id + '/renewal-context')
    assert response.status_code == 200, response.text
    meta = response.json()
    value = copy.deepcopy(spec)
    value['renewal'] = {'parent_context_id': parent_id, 'expected_parent_manifest_sha256': meta['manifest_sha256'],
        'expected_parent_review_id': meta['review_id'], 'reason': 'TEST ONLY explicit replacement; old review is not inherited.',
        'mappings': [{'parent_passage_id': row['identity']['passage_id'], 'new_passage_ids': [row['identity']['passage_id']],
            'disposition': 'retained', 'note': 'TEST ONLY exact evidence retained, targets separately compared.'} for row in meta['sources']],
        'added_passage_ids': []}
    return value, meta


def reviewed_renewal(client, endpoint, context):
    path, body = review_request(client, endpoint, context['id'])
    body['renewal_assessment'] = {'expected_comparison_sha256': context['manifest']['renewal_comparison_sha256'],
        'outcome': 'confirmed', 'note': 'TEST ONLY explicit old/new mapping checked independently; no legal equivalence.'}
    return path, body


def fresh_product(workbench, reader):
    app, _, base, *_ = workbench
    candidates = SourceCorpusService(reader).search('sözleşme')
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        product = app.state.store.add(session, 'product', user, {'title': 'TEST ONLY new research capture', 'status': 'needs_review',
            'snapshots': {'graph_release_pin': {'status': 'verified', 'release_id': reader.info['release_id'],
                'serving_sha256': reader.info['serving_sha256'], 'activation_sequence': reader.info['pointer']['sequence']}},
            'source_candidates': candidates}, base.split('/')[-1])
        session.commit()
    return product.id


def test_exact_renewal_preserves_parent_history_and_requires_fresh_mapping_review(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    parent, _ = freeze(client, endpoint, spec)
    reviewer(workbench)
    path, body = review_request(client, endpoint, parent['id'])
    original = record(client, path, body)
    login(client)
    value, meta = renewal_spec(client, endpoint, spec, parent['id'])
    assert 'TEST ONLY 📄' not in json.dumps(meta, ensure_ascii=False) and 'PRIVATE REVIEW NOTE' not in json.dumps(meta)
    new, nonce = freeze(client, endpoint, value)
    assert new['id'] != parent['id'] and new['review']['effective_state'] == 'unreviewed'
    comparison = new['manifest']['renewal_comparison']
    assert comparison['parent_review_id'] == original['review']['id']
    assert comparison['entries'][0]['successors'][0]['exact_evidence_same'] is True
    assert comparison['entries'][0]['successors'][0]['exact_targets_same'] is True
    assert comparison['review_inheritance'] == 'none' and comparison['legal_equivalence'] == 'not_assessed'
    assert new['manifest']['renewal_comparison_sha256'] == digest(canonical(comparison))
    assert client.get(endpoint + '/' + new['id'] + '/export').status_code == 409
    assert client.get(endpoint + '/' + new['id'] + '/reviews/context').status_code == 403
    assert client.post(endpoint, json=nonce).json()['id'] == new['id']
    assert client.get(endpoint + '/' + parent['id']).json() == original
    login(client, 'reviewer')
    fresh_path, fresh_body = reviewed_renewal(client, endpoint, new)
    incomplete = {key: val for key, val in fresh_body.items() if key != 'renewal_assessment'}
    assert client.post(fresh_path, json=incomplete).status_code == 422
    for changes in [{'expected_comparison_sha256': '0' * 64}, {'outcome': 'not_assessed'}, {'note': '   '}]:
        bad = copy.deepcopy(fresh_body)
        bad['renewal_assessment'].update(changes)
        assert client.post(fresh_path, json=bad).status_code == 422
    assert client.get(fresh_path).json() == []
    fresh = record(client, fresh_path, fresh_body)
    assert fresh['review']['snapshot']['sequence'] == 1 and fresh['review']['snapshot']['previous_review_id'] is None
    assert fresh['review']['id'] != original['review']['id']
    exported = client.get(endpoint + '/' + new['id'] + '/export').json()
    assert exported['manifest']['renewal_comparison'] == comparison
    assert exported['manifest']['sources'][0]['evidence']['text'].endswith('\r\n')
    for format in ('docx', 'pdf'):
        response = client.get(endpoint + '/' + new['id'] + '/export?format=' + format)
        assert response.status_code == 200
        text = ('\n'.join(item.text for item in Document(io.BytesIO(response.content)).paragraphs) if format == 'docx'
                else '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages))
        assert new['manifest']['renewal_comparison_sha256'] in text
        assert parent['id'] in text and fresh_body['renewal_assessment']['note'] in ' '.join(text.split())
    assert client.get(path).json()[0]['id'] == original['review']['id']
    with app.state.store.session() as session:
        row = session.get(Record, new['id'])
        assert value['renewal']['reason'] not in row.payload


def test_changed_analysis_targets_are_compared_without_exposing_old_private_text(workbench, monkeypatch):
    _, client, base, payload, *_ = workbench
    endpoint, spec, analysis, reader, _ = setup(workbench, monkeypatch)
    parent, _ = freeze(client, endpoint, spec)
    changed = copy.deepcopy(payload)
    changed['rules'][0]['text'] = 'TEST ONLY changed target, separately investigated.'
    response = client.post(base + '/analyses/' + analysis['id'] + '/versions', json={**changed,
        'expected_revision': analysis['revision'], 'change_note': 'TEST ONLY explicit new version.'})
    assert response.status_code == 201, response.text
    assert client.get(endpoint + '/' + parent['id']).json()['manifest'] is None
    value, meta = renewal_spec(client, endpoint, {**spec, 'version_id': response.json()['latest_version_id']}, parent['id'])
    value['product_id'] = fresh_product(workbench, reader)
    new, _ = freeze(client, endpoint, value)
    comparison = new['manifest']['renewal_comparison']
    assert comparison['analysis_changed'] and not comparison['entries'][0]['successors'][0]['exact_targets_same']
    assert payload['rules'][0]['text'] not in json.dumps(meta, ensure_ascii=False)
    assert new['review']['snapshot'] is None


@pytest.mark.parametrize('bad', ['parent_hash', 'review_head', 'missing_parent', 'undeclared_new', 'same_version_lie', 'old_target', 'cross_analysis', 'pending'])
def test_partial_unbound_or_pending_replacements_fail_closed(workbench, monkeypatch, bad):
    app, client, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    parent, _ = freeze(client, endpoint, spec)
    value, _ = renewal_spec(client, endpoint, spec, parent['id'])
    if bad == 'parent_hash':
        value['renewal']['expected_parent_manifest_sha256'] = '0' * 64
    elif bad == 'review_head':
        value['renewal']['expected_parent_review_id'] = 'absent'
    elif bad == 'missing_parent':
        value['renewal']['mappings'][0]['parent_passage_id'] = 'urn:test:absent'
    elif bad == 'undeclared_new':
        value['renewal']['mappings'][0].update(disposition='omitted', new_passage_ids=[])
    elif bad == 'same_version_lie':
        value['renewal']['mappings'][0].update(disposition='retained', new_passage_ids=[])
    elif bad == 'old_target':
        value['selections'][0]['target_ids'] = ['rule:old-absent']
    elif bad == 'cross_analysis':
        from test_analysis_workbench import create
        other = create(workbench)
        endpoint = endpoint.replace(parent['manifest']['analysis_id'], other['id'])
        value['version_id'] = other['latest_version_id']
    else:
        mutate(app, reviews._id('saa-', parent['id']), lambda data: data.update(guard_completed=False))
    response = client.post(endpoint + '/preview', json=value)
    assert response.status_code in {404, 409, 422}, response.text


def test_new_representation_requires_explicit_replacement_and_independent_review(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, spec, _, reader, _ = setup(workbench, monkeypatch)
    parent, _ = freeze(client, endpoint, spec)
    passage(reader, 'new-version', 'TEST ONLY sözleşme — different 📄 source\r\n')
    candidates = SourceCorpusService(reader).search('sözleşme', passage_id='urn:test:new-version')
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        product = app.state.store.add(session, 'product', user, {'title': 'TEST ONLY fresh source capture', 'status': 'needs_review',
            'snapshots': {'graph_release_pin': parent['manifest']['graph_release_pin']}, 'source_candidates': candidates}, base.split('/')[-1])
        session.commit()
    hit = candidates['hits'][0]
    value, _ = renewal_spec(client, endpoint, spec, parent['id'])
    value.update(product_id=product.id, selections=[{**value['selections'][0], **{key: hit[key] for key in reviews.IDENTITY}}])
    value['renewal']['mappings'][0]['new_passage_ids'] = [hit['passage_id']]
    assert client.post(endpoint + '/preview', json=value).status_code == 422
    value['renewal']['mappings'][0]['disposition'] = 'replaced'
    new, _ = freeze(client, endpoint, value)
    after = new['manifest']['renewal_comparison']['entries'][0]['successors'][0]
    assert not after['exact_evidence_same'] and new['review']['effective_state'] == 'unreviewed'
    assert new['manifest']['sources'][0]['evidence']['text'] == hit['text']
    assert client.get(endpoint + '/' + parent['id']).json()['manifest']['sources'][0]['evidence']['text'] != hit['text']


def test_parent_head_change_invalidates_preview_and_renewed_exports_without_rewriting_history(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    parent, _ = freeze(client, endpoint, spec)
    value, _ = renewal_spec(client, endpoint, spec, parent['id'])
    preview = client.post(endpoint + '/preview', json=value).json()
    new, _ = freeze(client, endpoint, value)
    reviewer(workbench)
    path, body = reviewed_renewal(client, endpoint, new)
    record(client, path, body)
    parent_path, parent_body = review_request(client, endpoint, parent['id'])
    record(client, parent_path, parent_body)
    login(client)
    saved = client.post(endpoint, json={**value, 'expected_preview_sha256': preview['preview_sha256'], 'request_id': uuid4().hex})
    assert saved.status_code == 409
    current = client.get(endpoint + '/' + new['id']).json()
    assert current['manifest'] is None and current['review']['snapshot'] is None
    assert client.get(endpoint + '/' + new['id'] + '/export').status_code == 409
    assert len(client.get(path).json()) == 1


def test_withdrawal_withholds_bodies_but_keeps_authorized_metadata_and_history(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, spec, _, _, permit = setup(workbench, monkeypatch)
    parent, _ = freeze(client, endpoint, spec)
    value, _ = renewal_spec(client, endpoint, spec, parent['id'])
    permit.active = False
    meta = client.get(endpoint + '/' + parent['id'] + '/renewal-context')
    assert meta.status_code == 200 and 'TEST ONLY 📄' not in meta.text
    assert client.post(endpoint + '/preview', json=value).status_code == 409
    assert client.get(endpoint + '/' + parent['id']).json()['manifest'] is None
    assert client.get(endpoint).json()[0]['id'] == parent['id']


def test_release_change_requires_explicit_new_selection_and_never_reauthorizes_parent(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, spec, _, reader, _ = setup(workbench, monkeypatch)
    parent, _ = freeze(client, endpoint, spec)
    value, _ = renewal_spec(client, endpoint, spec, parent['id'])
    reader.info.update(release_id='1' * 64, serving_sha256='2' * 64, pointer={'sequence': 3})
    value.update(product_id=fresh_product(workbench, reader), expected_release_id='1' * 64, expected_serving_sha256='2' * 64)
    assert client.post(endpoint + '/preview', json=value).status_code == 409
    value['renewal']['mappings'][0]['disposition'] = 'replaced'
    current, _ = freeze(client, endpoint, value)
    assert current['manifest']['renewal_comparison']['release_changed']
    assert current['manifest']['sources'][0]['evidence']['release_id'] == '1' * 64
    assert current['review']['effective_state'] == 'unreviewed'
    assert client.get(endpoint + '/' + parent['id']).json()['manifest'] is None


def test_membership_removal_withholds_even_private_lineage_metadata(workbench, monkeypatch):
    from app.db import Membership

    app, client, base, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    parent, _ = freeze(client, endpoint, spec)
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        row = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.matter_id == base.split('/')[-1]))
        session.delete(row)
        session.commit()
    response = client.get(endpoint + '/' + parent['id'] + '/renewal-context')
    assert response.status_code in {403, 404}
    assert 'urn:test:unlinked' not in response.text


def test_postcommit_renewal_failure_stays_pending_and_does_not_replay_admission(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, _, reader, permit = setup(workbench, monkeypatch)
    parent, _ = freeze(client, endpoint, spec)
    value, _ = renewal_spec(client, endpoint, spec, parent['id'])
    preview = client.post(endpoint + '/preview', json=value).json()
    guard = permit.guard
    @contextmanager
    def fail_exit_after_write():
        with guard() as info:
            yield info
            with app.state.store.session() as session:
                count = len(list(session.scalars(select(Record).where(Record.kind == reviews.KIND))))
            if count > 1:
                raise ValueError('TEST ONLY committed source guard failure')
    monkeypatch.setattr(reader, 'current_guard', fail_exit_after_write)
    body = {**value, 'expected_preview_sha256': preview['preview_sha256'], 'request_id': uuid4().hex}
    response = client.post(endpoint, json=body)
    assert response.status_code == 409 and response.json()['outcome'] == 'committed_needs_revalidation'
    ident = response.json()['id']
    monkeypatch.setattr(reader, 'current_guard', guard)
    assert client.get(endpoint + '/' + ident).json()['manifest'] is None
    assert client.post(endpoint, json=body).json()['manifest'] is None
    assert len(client.get(endpoint).json()) == 2


def reconciliation_receipt(body, parent):
    return {'request_id': body['request_id'],
        'expected_request_sha256': digest(canonical({key: value for key, value in body.items() if key != 'request_id'})),
        'expected_preview_sha256': body['expected_preview_sha256'], 'parent_context_id': parent['id'],
        'expected_parent_manifest_sha256': parent['manifest_sha256'], 'parent_version_id': parent['manifest']['version_id'],
        'version_id': body['version_id'], **({'expected_parent_review_id': body['renewal']['expected_parent_review_id']} if body['renewal']['expected_parent_review_id'] else {})}


def reconcile(client, endpoint, receipt):
    response = client.get(endpoint + '/renewal-reconciliation', params=receipt)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    for text in ['TEST ONLY 📄', 'PRIVATE SOURCE NOTE', 'PRIVATE REVIEW NOTE', 'target_snapshots', 'selections', 'recorded_by', 'sources', 'purpose']:
        assert text not in response.text
    return response.json()


def test_read_only_reconciliation_matches_exact_actor_request_and_historical_parent(workbench, monkeypatch):
    from test_source_review_readiness import no_public_reads
    _, client, *_ = workbench
    endpoint, spec, _, reader, permit = setup(workbench, monkeypatch)
    parent, _ = freeze(client, endpoint, spec)
    reviewer(workbench)
    path, body = review_request(client, endpoint, parent['id'])
    old = record(client, path, body)
    login(client)
    value, _ = renewal_spec(client, endpoint, spec, parent['id'])
    child, sent = freeze(client, endpoint, value)
    login(client, 'reviewer')
    path, body = review_request(client, endpoint, parent['id'], decision='changes_requested')
    later = record(client, path, body)
    assert later['review']['id'] != old['review']['id']
    login(client)
    permit.active = False
    no_public_reads(monkeypatch, reader)
    monkeypatch.setattr(reviews, '_finalize', lambda *_a, **_k: pytest.fail('Reconciliation cannot finalize a write'))
    with workbench[0].state.store.session() as session:
        before = {row.id: (row.revision, row.payload) for row in session.scalars(select(Record))}
    result = reconcile(client, endpoint, reconciliation_receipt(sent, parent))
    assert result['outcome'] == 'verified' and result['successor']['id'] == child['id']
    assert result['lineage']['parent_review_id'] == old['review']['id']
    assert result['lineage']['current_parent_head'] == 'not_checked'
    assert result['lineage']['scope'] == 'one_historical_link'
    assert result['admission'] == {'successor': 'complete', 'parent': 'complete', 'parent_review': 'complete'}
    assert result['source_verification'] == 'not_checked' and result['legal_readiness'] == 'not_established'
    assert not result['qualification_granted'] and not result['effects_replayed'] and result['review_inheritance'] == 'none'
    with workbench[0].state.store.session() as session:
        assert before == {row.id: (row.revision, row.payload) for row in session.scalars(select(Record))}


@pytest.mark.parametrize('fault', ['pending', 'pending_parent', 'missing_admission', 'parent_hash', 'request_hash', 'preview_hash', 'version', 'parent_version', 'unknown_nonce', 'comparison'])
def test_reconciliation_pending_unknown_or_mismatched_receipts_do_not_repair_or_replay(workbench, monkeypatch, fault):
    from test_source_review_readiness import no_public_reads
    app, client, *_ = workbench
    endpoint, spec, _, reader, _ = setup(workbench, monkeypatch)
    parent, _ = freeze(client, endpoint, spec)
    value, _ = renewal_spec(client, endpoint, spec, parent['id'])
    child, sent = freeze(client, endpoint, value)
    receipt = reconciliation_receipt(sent, parent)
    if fault in {'pending', 'pending_parent'}:
        target = child['id'] if fault == 'pending' else parent['id']
        mutate(app, reviews._id('saa-', target), lambda packet: packet.update(guard_completed=False))
    elif fault == 'missing_admission':
        from sqlalchemy import delete
        with app.state.store.session() as session:
            session.execute(delete(Record).where(Record.id == reviews._id('saa-', child['id'])))
            session.commit()
    elif fault == 'comparison':
        # Re-sign an internally inconsistent comparison: the immutable parent must still win.
        with app.state.store.session() as session:
            row = session.get(Record, child['id'])
            packet = app.state.store.decode(row)
            packet['manifest']['renewal_comparison']['parent_packet_sha256'] = '0' * 64
            packet['manifest']['renewal_comparison_sha256'] = digest(canonical(packet['manifest']['renewal_comparison']))
            packet['manifest_sha256'] = digest(canonical(packet['manifest']))
            packet['request_sha256'] = digest(canonical({**value, 'expected_preview_sha256': packet['manifest_sha256']}))
            packet['packet_sha256'] = digest(canonical({k: v for k, v in packet.items() if k != 'packet_sha256'}))
            app.state.store.update(row, packet)
            admission = session.get(Record, reviews._id('saa-', child['id']))
            proof = app.state.store.decode(admission)
            proof['packet_sha256'] = packet['packet_sha256']
            app.state.store.update(admission, proof)
            session.commit()
        receipt.update(expected_preview_sha256=packet['manifest_sha256'], expected_request_sha256=packet['request_sha256'])
    else:
        key = {'parent_hash': 'expected_parent_manifest_sha256', 'request_hash': 'expected_request_sha256', 'preview_hash': 'expected_preview_sha256', 'version': 'version_id', 'parent_version': 'parent_version_id', 'unknown_nonce': 'request_id'}[fault]
        receipt[key] = '0' * (32 if fault == 'unknown_nonce' else 64) if 'hash' in fault or fault == 'unknown_nonce' else 'different'
    no_public_reads(monkeypatch, reader)
    monkeypatch.setattr(reviews, '_finalize', lambda *_a, **_k: pytest.fail('No finalization'))
    with app.state.store.session() as session:
        before = {row.id: (row.revision, row.payload) for row in session.scalars(select(Record))}
    result = reconcile(client, endpoint, receipt)
    if fault.startswith('pending'):
        assert result['outcome'] == 'verified'
        assert result['admission']['successor' if fault == 'pending' else 'parent'] == 'pending'
    else:
        assert result['outcome'] == ('not_observed' if fault == 'unknown_nonce' else 'unavailable')
        assert result['successor'] is result['lineage'] is result['admission'] is None
    with app.state.store.session() as session:
        assert before == {row.id: (row.revision, row.payload) for row in session.scalars(select(Record))}


def test_reconciliation_requires_original_actor_and_explicit_matter_content_access(workbench, monkeypatch):
    from sqlalchemy import delete

    from app.db import Membership
    app, client, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    parent, _ = freeze(client, endpoint, spec)
    value, _ = renewal_spec(client, endpoint, spec, parent['id'])
    _, sent = freeze(client, endpoint, value)
    receipt = reconciliation_receipt(sent, parent)
    reviewer(workbench)
    assert reconcile(client, endpoint, receipt)['outcome'] == 'not_observed'
    with app.state.store.session() as session:
        actor = session.scalar(select(User).where(User.username == 'reviewer'))
        session.execute(delete(Membership).where(Membership.user_id == actor.id))
        session.commit()
    assert client.get(endpoint + '/renewal-reconciliation', params=receipt).status_code == 404
    login(client)
    receipt['parent_context_id'] = 'sac-' + 'f' * 20 + '-' + 'e' * 32
    assert reconcile(client, endpoint, receipt)['outcome'] == 'unavailable'
    for params in [{**receipt, 'note': 'PRIVATE'}, list(receipt.items()) + [('request_id', receipt['request_id'])], {**receipt, 'request_id': 'bad'}]:
        assert client.get(endpoint + '/renewal-reconciliation', params=params).status_code == 422
