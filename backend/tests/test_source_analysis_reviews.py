"""Invented private/source documents and separate test accounts, not legal approval."""

import copy
import io
import json
from contextlib import contextmanager
from uuid import uuid4

import pytest
from docx import Document
from pypdf import PdfReader
from sqlalchemy import select
from test_analysis_authorities import Permit, mutate, payload
from test_analysis_comparisons import login
from test_analysis_workbench import create
from test_analysis_workbench import workbench as workbench_fixture
from test_authority_adjudications import reviewer
from test_source_corpus import passage, release

from app import source_analysis_reviews as reviews
from app.db import Membership, Record, User
from app.source_corpus import SourceCorpusService

workbench = workbench_fixture


def nominate(workbench, product_id, source, snapshot, *, analysis=None):
    analysis = analysis or create(workbench)
    endpoint = workbench[2] + '/analyses/' + analysis['id'] + '/source-contexts'
    spec = {'version_id': analysis['latest_version_id'], 'product_id': product_id,
        'expected_release_id': snapshot['release_id'], 'expected_serving_sha256': snapshot['serving_sha256'],
        'title': 'TEST ONLY exact source context', 'purpose': 'TEST ONLY private analysis link with unknown applicability.',
        'selections': [{**{key: source[key] for key in reviews.IDENTITY}, 'target_ids': ['rule:r1', 'application:a1'],
            'relationship': 'unresolved', 'note': 'TEST ONLY source nomination; no authority or legal promotion.'}]}
    return endpoint, spec, analysis


def setup(workbench, monkeypatch):
    app, client, base, *_ = workbench
    analysis = create(workbench)
    reader = release()
    passage(reader, 'unlinked', 'TEST ONLY 📄 sözleşme\r\n  Özgün alıntı.\r\n')
    passage(reader, 'private', 'PRIVATE CANARY', scope='private')
    candidates = SourceCorpusService(reader).search('sözleşme', as_of='1921-01-01')
    assert len(candidates['hits']) == 1
    permit = Permit(reader)
    monkeypatch.setattr(reader, 'current_guard', permit.guard)
    monkeypatch.setattr(app.state.graph, 'release', reader)
    monkeypatch.setattr(app.state.provider, 'generate', lambda *_: pytest.fail('No inference'))
    monkeypatch.setattr(app.state.provider, 'suggest_analysis', lambda *_a, **_k: pytest.fail('No inference'))
    monkeypatch.setattr(app.state.graph, 'tool', lambda *_a, **_k: pytest.fail('No graph search'))
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        product = app.state.store.add(session, 'product', user, {'title': 'TEST ONLY retained source capture',
            'status': 'needs_review', 'critical_gaps': ['legal_corpus_unqualified'],
            'snapshots': {'graph_release_pin': {'status': 'verified', 'release_id': reader.info['release_id'],
                'serving_sha256': reader.info['serving_sha256'], 'activation_sequence': 2}},
            'source_candidates': candidates}, base.split('/')[-1])
        session.commit()
    endpoint, spec, analysis = nominate(workbench, product.id, candidates['hits'][0], candidates['snapshot'], analysis=analysis)
    return endpoint, spec, analysis, reader, permit


def freeze(client, endpoint, spec):
    response = client.post(endpoint + '/preview', json=spec)
    assert response.status_code == 200, response.text
    body = {**spec, 'expected_preview_sha256': response.json()['preview_sha256'], 'request_id': uuid4().hex}
    saved = client.post(endpoint, json=body)
    assert saved.status_code == 201, saved.text
    return saved.json(), body


def review_request(client, endpoint, context_id, *, decision='reviewed_conditional', relationship='adverse_candidate'):
    path = endpoint + '/' + context_id + '/reviews'
    response = client.get(path + '/context')
    assert response.status_code == 200, response.text
    context = response.json()
    body = {key: context[key] for key in ('expected_manifest_sha256', 'expected_review_id')}
    body.update(request_id=uuid4().hex, decision=decision, note='PRIVATE REVIEW NOTE — separate conditional declaration.',
        sources=[{**source['selection'], 'relationship': relationship,
            'note': 'PRIVATE SOURCE NOTE — independent interpretation differs from nomination.',
            'observations': [{'dimension': key, 'outcome': 'confirmed', 'note': 'TEST ONLY checked; unknown effects remain unknown.'}
                             for key in context['dimensions']]} for source in context['manifest']['sources']])
    if decision == 'changes_requested':
        body['sources'][0]['observations'][1].update(outcome='needs_change', note='TEST ONLY target interpretation needs correction.')
    return path, body


def record(client, path, body):
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def reviewed(workbench, monkeypatch):
    endpoint, spec, analysis, reader, permit = setup(workbench, monkeypatch)
    context, request = freeze(workbench[1], endpoint, spec)
    reviewer(workbench)
    path, body = review_request(workbench[1], endpoint, context['id'])
    value = record(workbench[1], path, body)
    return endpoint, spec, analysis, reader, permit, context, value, path, body, request


def test_exact_version_nomination_independent_interpretation_and_no_mutation(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, spec, analysis, reader, _, context, value, path, body, _ = reviewed(workbench, monkeypatch)
    before = set(reader._resources)
    assert value['freshness']['status'] == 'current' and value['review']['is_latest']
    evidence = value['manifest']['sources'][0]['evidence']
    assert evidence['text'] == 'TEST ONLY 📄 sözleşme\r\n  Özgün alıntı.\r\n'
    assert evidence['authority_id'] is None and evidence['assertion_id'] is None
    assert evidence['source_version_id'] == spec['selections'][0]['source_version_id']
    assert value['manifest']['sources'][0]['selection']['relationship'] == 'unresolved'
    event = value['review']['snapshot']
    assert event['input']['sources'][0]['relationship'] == 'adverse_candidate'
    assert event['recorded_by'] != value['manifest']['analysis_author_id']
    assert value['recorded_by'] != event['recorded_by']
    assert event['legal_approval'] == value['legal_approval'] == 'not_granted'
    assert value['manifest']['coverage']['total_expected'] is None
    assert value['manifest']['event_date'] != value['manifest']['research_snapshot']['as_of']
    assert value['manifest']['temporal_applicability'] == 'not_assessed'
    assert client.post(path, json=body).json() == value
    assert client.post(path, json={**body, 'note': 'TEST ONLY different body'}).status_code == 409
    assert client.get(endpoint + '/' + context['id']).json() == value
    assert set(reader._resources) == before
    assert 'TEST ONLY' not in payload(app, context['id'])
    assert 'PRIVATE REVIEW NOTE' not in payload(app, value['review']['id'])
    assert client.get(base + '/analyses').json()[0]['checks'] == analysis['checks']
    login(client)
    response = client.post(base + '/erasure-plan')
    assert response.status_code == 200, response.text
    inventory = response.json()['record_counts']
    assert inventory[reviews.KIND] == inventory[reviews.REVIEW] == 1


@pytest.mark.parametrize('bad', ['version', 'quote', 'passage', 'release', 'serving', 'target', 'duplicate', 'authority', 'whitespace'])
def test_invalid_source_selection_never_freezes(workbench, monkeypatch, bad):
    _, client, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    item = spec['selections'][0]
    if bad == 'version':
        item['source_version_id'] = 'urn:test:current-but-wrong'
    elif bad == 'quote':
        item['quote_sha256'] = '0' * 64
    elif bad == 'passage':
        item['passage_id'] = 'urn:test:private'
    elif bad in {'release', 'serving'}:
        spec['expected_' + ('release_id' if bad == 'release' else 'serving_sha256')] = '0' * 64
    elif bad == 'target':
        item['target_ids'] = ['rule:absent']
    elif bad == 'duplicate':
        spec['selections'].append(copy.deepcopy(item))
    elif bad == 'authority':
        item['authority_id'] = 'urn:test:invented'
    else:
        item['note'] = '   '
    response = client.post(endpoint + '/preview', json=spec)
    assert response.status_code in {409, 422}, response.text
    assert client.get(endpoint).json() == []


def test_source_selector_and_analysis_author_cannot_review_their_own_packet(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    path = endpoint + '/' + context['id'] + '/reviews'
    assert client.get(path + '/context').status_code == 403
    reviewer(workbench)
    _, body = review_request(client, endpoint, context['id'])
    login(client)
    assert client.post(path, json=body).status_code == 403
    assert client.get(path).json() == []
    # A different selector still cannot make the analysis author independent.
    login(client, 'reviewer')
    second, _ = freeze(client, endpoint, spec)
    login(client)
    assert client.get(endpoint + '/' + second['id'] + '/reviews/context').status_code == 403


@pytest.mark.parametrize('bad', ['hash', 'head', 'identity', 'target', 'missing_dimension', 'missing_source', 'affirm_unassessed', 'empty_change', 'extra'])
def test_unbound_or_incomplete_independent_decisions_rejected(workbench, monkeypatch, bad):
    _, client, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    reviewer(workbench)
    path, body = review_request(client, endpoint, context['id'])
    if bad == 'hash':
        body['expected_manifest_sha256'] = '0' * 64
    elif bad == 'head':
        body['expected_review_id'] = 'test-only-absent'
    elif bad == 'identity':
        body['sources'][0]['source_version_id'] = 'urn:test:wrong'
    elif bad == 'target':
        body['sources'][0]['target_ids'] = ['conclusion']
    elif bad == 'missing_dimension':
        body['sources'][0]['observations'].pop()
    elif bad == 'missing_source':
        body['sources'] = []
    elif bad == 'affirm_unassessed':
        body['sources'][0]['observations'][0]['outcome'] = 'not_assessed'
    elif bad == 'empty_change':
        body['decision'] = 'changes_requested'
    else:
        body['legal_approval'] = 'granted'
    assert client.post(path, json=body).status_code in {409, 422}
    assert client.get(path).json() == []


def test_later_decision_keeps_history_and_requires_explicit_current_head(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, _, _, _, _, context, first, path, body, _ = reviewed(workbench, monkeypatch)
    first_id = first['review']['id']
    encrypted = payload(app, first_id)
    assert client.post(path, json={**body, 'request_id': uuid4().hex}).status_code == 409
    _, body = review_request(client, endpoint, context['id'], decision='changes_requested')
    second = record(client, path, body)
    assert second['review']['snapshot']['previous_review_id'] == first_id
    assert second['review']['snapshot']['sequence'] == 2
    old = client.get(path + '/' + first_id).json()
    assert not old['review']['is_latest'] and old['review']['snapshot'] == first['review']['snapshot']
    assert payload(app, first_id) == encrypted
    assert len(client.get(path).json()) == 2
    assert client.get(endpoint + '/' + context['id'] + '/export').status_code == 409


@pytest.mark.parametrize('change', ['fact', 'document', 'analysis', 'product', 'reviewer', 'recipe', 'dimension'])
def test_changed_basis_withholds_quotes_and_decisions_without_rewriting(workbench, monkeypatch, change):
    app, client, _, _, fact, document, *_ = workbench
    endpoint, spec, analysis, _, _, context, value, path, *_ = reviewed(workbench, monkeypatch)
    immutable = payload(app, value['review']['id'])
    if change in {'fact', 'document', 'analysis', 'product'}:
        ident = {'fact': fact['id'], 'document': document, 'analysis': analysis['id'], 'product': spec['product_id']}[change]
        mutate(app, ident, lambda data: data.update(name='TEST ONLY changed', title='TEST ONLY changed'))
    elif change == 'reviewer':
        with app.state.store.session() as session:
            session.get(User, value['review']['snapshot']['recorded_by']).role = 'reader'
            session.commit()
        login(client)
    elif change == 'recipe':
        monkeypatch.setattr(reviews, 'REVIEW_RECIPE', 'test-only-new-recipe')
    else:
        monkeypatch.setattr(reviews, 'DIMENSIONS', {**reviews.DIMENSIONS, 'target_alignment': 'TEST ONLY changed'})
    response = client.get(endpoint + '/' + context['id'])
    assert response.status_code == 200, response.text
    assert response.json()['manifest'] is None and response.json()['review']['snapshot'] is None
    assert not response.json()['public_source_access']
    assert 'PRIVATE REVIEW NOTE' not in response.text and 'Özgün alıntı' not in response.text
    assert payload(app, value['review']['id']) == immutable
    assert client.get(endpoint + '/' + context['id'] + '/export').status_code == 409
    assert value['review']['id'] in json.dumps(client.get(path).json())


@pytest.mark.parametrize('failure', ['withdrawal', 'exit', 'pointer', 'quote'])
def test_current_source_failures_withhold_complete_results(workbench, monkeypatch, failure):
    _, client, *_ = workbench
    endpoint, _, _, reader, permit, context, _, path, *_ = reviewed(workbench, monkeypatch)
    if failure == 'withdrawal':
        permit.active = False
    elif failure == 'exit':
        permit.fail_exit = True
    elif failure == 'pointer':
        reader.info['pointer']['sequence'] += 1
    else:
        from rdflib import Literal, URIRef

        from app.graph_release import LA
        reader._resources.set((URIRef(context['manifest']['sources'][0]['evidence']['passage_id']), LA.quotedText, Literal('TEST ONLY tampered')))
    response = client.get(endpoint + '/' + context['id'])
    assert response.status_code == 200 and response.json()['manifest'] is None
    assert response.json()['review']['snapshot'] is None
    assert 'PRIVATE REVIEW NOTE' not in response.text and 'PRIVATE SOURCE OWNER' not in response.text
    assert client.get(endpoint + '/' + context['id'] + '/export').status_code == 409
    assert 'PRIVATE REVIEW NOTE' not in client.get(path).text


@pytest.mark.parametrize('format', ['json', 'docx', 'pdf'])
def test_export_requires_independent_review_and_preserves_evidence(workbench, monkeypatch, format):
    _, client, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    path = endpoint + '/' + context['id'] + '/export'
    assert client.get(path, params={'format': format}).status_code == 409
    reviewer(workbench)
    review_path, body = review_request(client, endpoint, context['id'])
    value = record(client, review_path, body)
    response = client.get(path, params={'format': format})
    assert response.status_code == 200, response.text if response.status_code != 200 else ''
    assert response.headers['cache-control'] == 'no-store'
    source = value['manifest']['sources'][0]['evidence']
    if format == 'json':
        assert response.json()['manifest']['sources'][0]['evidence'] == source
    else:
        text = ('\n'.join(item.text for item in Document(io.BytesIO(response.content)).paragraphs) if format == 'docx'
                else '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages))
        assert source['quote_sha256'] in text and source['source_version_id'] in text
        assert 'adverse_candidate' in text and value['review']['snapshot']['recorded_by'] in text


def test_single_guard_and_post_commit_exit_failure_is_persistently_pending(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, _, reader, permit = setup(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    reviewer(workbench)
    path, body = review_request(client, endpoint, context['id'])
    active = False
    @contextmanager
    def failing_exit():
        nonlocal active
        assert not active, 'Source guards must never nest'
        active = True
        try:
            yield reader.info
            raise ValueError('PRIVATE SOURCE OWNER')
        finally:
            active = False
    monkeypatch.setattr(reader, 'current_guard', failing_exit)
    response = client.post(path, json=body)
    assert response.status_code == 409 and response.json()['outcome'] == 'committed_needs_revalidation'
    ident = response.json()['id']
    assert payload(app, ident)
    monkeypatch.setattr(reader, 'current_guard', permit.guard)
    value = client.get(endpoint + '/' + context['id']).json()
    assert value['review']['effective_state'] == 'stale' and value['review']['snapshot'] is None
    assert client.post(path, json=body).json()['review']['snapshot'] is None
    _, next_body = review_request(client, endpoint, context['id'])
    fresh = record(client, path, next_body)
    assert fresh['review']['snapshot']['previous_review_id'] == ident


def test_cross_matter_and_exit_membership_denial_never_returns_evidence(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, _, _, reader, _, context, value, _, *_ = reviewed(workbench, monkeypatch)
    assert client.get(endpoint.replace(analysis_id := endpoint.split('/analyses/')[1].split('/')[0], 'foreign-analysis') + '/' + context['id']).status_code == 404
    assert analysis_id
    @contextmanager
    def revoke_at_exit():
        yield reader.info
        with app.state.store.session() as session:
            session.delete(session.get(Membership, (base.split('/')[-1], value['review']['snapshot']['recorded_by'])))
            session.commit()
    monkeypatch.setattr(reader, 'current_guard', revoke_at_exit)
    response = client.get(endpoint + '/' + context['id'])
    assert response.status_code == 404 and 'Özgün alıntı' not in response.text


@pytest.mark.parametrize('boundary', ['source_exit', 'private_during_render'])
def test_export_discards_constructed_bytes_after_boundary_change(workbench, monkeypatch, boundary):
    from fastapi import Response

    app, client, *_ = workbench
    endpoint, spec, _, _, permit, context, _, _, *_ = reviewed(workbench, monkeypatch)
    if boundary == 'source_exit':
        permit.fail_exit = True
    else:
        def render(*_args):
            mutate(app, spec['product_id'], lambda data: data.update(title='TEST ONLY changed during export'))
            return Response('PRIVATE EXPORT BYTES')
        monkeypatch.setattr(reviews, 'render_export', render)
    response = client.get(endpoint + '/' + context['id'] + '/export', params={'format': 'docx'})
    assert response.status_code == 409
    assert 'PRIVATE EXPORT BYTES' not in response.text


def test_existing_public_analysis_dependencies_are_checked_without_nested_source_guard(workbench, monkeypatch):
    from test_analysis_suggestions import adopt
    from test_authority_proposals import complete

    app, client, base, *_ = workbench
    suggestion_path, _, original, _, _, _, reader, job = complete(workbench, monkeypatch)
    response = adopt(client, suggestion_path, original, job)
    assert response.status_code == 201, response.text
    analysis = response.json()
    assert analysis['authority_dependencies']
    reader.info['ontology_sha256'] = 'c' * 64
    candidates = SourceCorpusService(reader).search('SYNTHETIC', as_of='1921-01-01')
    assert candidates['hits']
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        product = app.state.store.add(session, 'product', user, {'title': 'TEST ONLY public dependent analysis research',
            'status': 'needs_review', 'source_candidates': candidates,
            'snapshots': {'graph_release_pin': {'status': 'verified', 'release_id': reader.info['release_id'],
                'serving_sha256': reader.info['serving_sha256'], 'activation_sequence': reader.info['pointer']['sequence']}}},
            base.split('/')[-1])
        session.commit()
    endpoint, spec, _ = nominate(workbench, product.id, candidates['hits'][0], candidates['snapshot'], analysis=analysis)
    active = False
    original_guard = reader.current_guard
    @contextmanager
    def nonnested():
        nonlocal active
        assert not active, 'Public analysis checks cannot nest in the source review guard'
        active = True
        try:
            with original_guard() as info:
                yield info
        finally:
            active = False
    monkeypatch.setattr(reader, 'current_guard', nonnested)
    context, _ = freeze(client, endpoint, spec)
    assert context['manifest']['analysis_content']['authority_dependencies'] == analysis['authority_dependencies']
    reviewer(workbench)
    path, body = review_request(client, endpoint, context['id'])
    value = record(client, path, body)
    assert value['review']['effective_state'] == 'reviewed_conditional'
    assert client.get(endpoint + '/' + context['id'] + '/export').status_code == 200


def test_private_change_at_source_guard_exit_discards_inspection(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, _, reader, _, context, _, _, *_ = reviewed(workbench, monkeypatch)
    @contextmanager
    def private_change():
        yield reader.info
        mutate(app, spec['product_id'], lambda data: data.update(title='TEST ONLY changed at source guard exit'))
    monkeypatch.setattr(reader, 'current_guard', private_change)
    response = client.get(endpoint + '/' + context['id'])
    assert response.status_code == 200 and response.json()['manifest'] is None
    assert response.json()['review']['snapshot'] is None and 'PRIVATE REVIEW NOTE' not in response.text


def test_reviewer_access_change_at_source_guard_exit_discards_review_for_other_reader(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, _, _, reader, _, context, value, _, *_ = reviewed(workbench, monkeypatch)
    login(client)
    @contextmanager
    def revoke_reviewer():
        yield reader.info
        with app.state.store.session() as session:
            session.get(User, value['review']['snapshot']['recorded_by']).role = 'reader'
            session.commit()
    monkeypatch.setattr(reader, 'current_guard', revoke_reviewer)
    response = client.get(endpoint + '/' + context['id'])
    assert response.status_code == 200 and response.json()['manifest'] is None
    assert response.json()['review']['snapshot'] is None and 'PRIVATE REVIEW NOTE' not in response.text


def test_latest_version_author_differs_from_initial_owner_and_cannot_review(workbench, monkeypatch):
    app, client, base, original, *_ = workbench
    endpoint, spec, analysis, *_ = setup(workbench, monkeypatch)
    author = reviewer(workbench)
    response = client.post(base + '/analyses/' + analysis['id'] + '/versions', json={**copy.deepcopy(original),
        'expected_revision': analysis['revision'], 'change_note': 'TEST ONLY another lawyer authored this exact version'})
    assert response.status_code == 201, response.text
    spec['version_id'] = response.json()['latest_version_id']
    login(client)
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        data = app.state.store.decode(session.get(Record, spec['product_id']))
        data['status'] = 'needs_review'
        product = app.state.store.add(session, 'product', user, data, base.split('/')[-1])
        session.commit()
    spec['product_id'] = product.id
    context, _ = freeze(client, endpoint, spec)
    assert context['manifest']['analysis_author_id'] == author
    assert context['manifest']['analysis_owner_id'] != author
    login(client, 'reviewer')
    assert client.get(endpoint + '/' + context['id'] + '/reviews/context').status_code == 403
    reviewer(workbench, 'reviewer2')
    review_path, body = review_request(client, endpoint, context['id'])
    assert record(client, review_path, body)['review']['effective_state'] == 'reviewed_conditional'


def test_reviewer_inputs_expose_archived_read_only_state_without_granting_record_permission(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    reviewer(workbench)
    path, body = review_request(client, endpoint, context['id'])
    assert client.get(path + '/context').json()['can_record'] is True
    mutate(app, base.split('/')[-1], lambda data: data.update(status='archived'))
    response = client.get(path + '/context')
    assert response.status_code == 200 and response.json()['can_record'] is False
    assert client.post(path, json=body).status_code == 409
    assert client.get(path).json() == []
