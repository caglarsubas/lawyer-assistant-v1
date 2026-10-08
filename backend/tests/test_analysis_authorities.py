"""Synthetic private/public boundaries. In-memory release simulations are not approval."""

import copy
import io
from contextlib import contextmanager
from uuid import uuid4

import pytest
from docx import Document
from fastapi import Response
from pypdf import PdfReader
from rdflib import RDF, XSD, Graph, Literal
from sqlalchemy import select
from test_analysis_workbench import create
from test_analysis_workbench import workbench as workbench_fixture
from test_graph import FX, LA, corpus_for_query_tests

from app import analysis_authorities as authorities
from app.db import Audit, Membership, Record, User, digest
from app.graph_release import RuntimeGraphRelease

workbench = workbench_fixture


class Permit:
    active = True
    fail_exit = False

    def __init__(self, reader):
        self.reader = reader

    @contextmanager
    def guard(self):
        if not self.active:
            raise ValueError('PRIVATE SOURCE OWNER')
        yield self.reader.info
        if self.fail_exit or not self.active:
            raise ValueError('PRIVATE SOURCE OWNER')


def public_fixture(app, client, base, monkeypatch, *, point='2023-03-01'):
    """Exercise real RDF matching; signature/acquisition tested separately."""
    corpus = corpus_for_query_tests()
    for node in list(corpus.subjects(RDF.type, LA.Assertion)):
        corpus.set((node, LA.claimStatus, Literal('legally_reviewed')))
        corpus.set((node, LA.reviewer, Literal('SYNTHETIC ONLY')))
        corpus.set((node, LA.reviewedAt, Literal('2026-01-01T00:00:00Z', datatype=XSD.dateTime)))
    reader = RuntimeGraphRelease()
    reader.info = {'release_id': 'a' * 64, 'serving_sha256': 'b' * 64, 'pointer': {'sequence': 1}}
    reader._resources = corpus
    reader._graphs = {'structure': Graph(), 'jurisprudence': Graph()}
    for node in corpus.subjects(RDF.type, LA.Assertion):
        family = str(reader._one(corpus, node, LA.graphFamily))
        for triple in corpus.triples((node, None, None)):
            reader._graphs[family].add(triple)
    permit = Permit(reader)
    monkeypatch.setattr(reader, 'current_guard', permit.guard)
    monkeypatch.setattr(app.state.graph, 'release', reader)
    monkeypatch.setattr(app.state.provider, 'generate', lambda *_: pytest.fail('No inference in authority context'))
    monkeypatch.setattr(app.state.provider, 'suggest_analysis', lambda *_args, **_kwargs: pytest.fail('No proposal call'))
    hits = [reader._search_document('structure', FX['version-link-a'], FX.passage, str(FX.provision)),
            reader._search_document('jurisprudence', FX['cites-a'], FX.passage, str(FX.decision))]
    pin = {'status': 'verified', 'release_id': reader.info['release_id'],
           'serving_sha256': reader.info['serving_sha256'], 'activation_sequence': 1}
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        row = app.state.store.add(session, 'product', user, {'title': 'SYNTHETIC retained public candidates',
            'status': 'needs_review', 'snapshots': {'graph_release_pin': pin},
            'authority_candidates': {'hits': hits, 'snapshot': {'release_id': pin['release_id'], 'as_of': point},
                                     'limitations': ['SYNTHETIC — no real corpus or legal approval']}}, base.split('/')[-1])
        session.commit()
    return reader, permit, row.id, hits


def ready(workbench, monkeypatch):
    app, client, base, *_ = workbench
    analysis = create(workbench)
    reader, permit, product_id, hits = public_fixture(app, client, base, monkeypatch)
    endpoint = base + '/analyses/' + analysis['id'] + '/authority-contexts'
    body = {'version_id': analysis['latest_version_id'], 'product_id': product_id,
        'title': 'SYNTHETIC historical authority context', 'purpose': 'SYNTHETIC — Inspect date and role differences.',
        'selections': [{**{key: hits[0][key] for key in authorities.IDENTITY},
            'target_ids': ['rule:r1', 'application:a1'], 'relationship': 'unresolved',
            'note': 'SYNTHETIC — No applicability or entailment determination.'}]}
    return endpoint, body, analysis, reader, permit


def freeze(client, endpoint, body):
    preview = client.post(endpoint + '/preview', json=body)
    assert preview.status_code == 200, preview.text
    request = {**body, 'expected_preview_sha256': preview.json()['preview_sha256'], 'request_id': uuid4().hex}
    response = client.post(endpoint, json=request)
    assert response.status_code == 201, response.text
    return response.json(), request


def count(app, kind=authorities.KIND):
    with app.state.store.session() as session:
        return len(session.scalars(select(Record).where(Record.kind == kind)).all())


def payload(app, ident):
    with app.state.store.session() as session:
        return session.get(Record, ident).payload


def mutate(app, ident, change):
    with app.state.store.session() as session:
        row = session.get(Record, ident)
        data = app.state.store.decode(row)
        change(data)
        app.state.store.update(row, data)
        session.commit()


def test_preview_freeze_exact_source_history_and_unknown_applicability(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, body, analysis, reader, permit = ready(workbench, monkeypatch)
    preview = client.post(endpoint + '/preview', json=body)
    assert preview.status_code == 200 and count(app) == 0
    source = preview.json()['manifest']['sources'][0]
    assert source['evidence']['predicate'] == str(LA.hasProvisionVersion)
    assert source['evidence']['target_provision_version']['id'] == str(FX['version-a'])
    assert source['evidence']['target_provision_version']['version_of'] == str(FX.provision)
    assert source['evidence']['quote_sha256'] == digest(source['evidence']['text'])
    assert source['temporal_alignment']['dates_equal'] is False
    assert source['temporal_alignment']['within_assertion_interval'] is False
    assert source['temporal_alignment']['target_version_within_interval'] is False
    assert source['temporal_alignment']['applicability'] == 'not_assessed'
    value, request = freeze(client, endpoint, body)
    assert value['freshness']['status'] == 'current' and value['public_source_access']
    assert value['manifest']['analysis_content'] == reader_analysis(client, base, analysis)['content']
    assert value['manifest']['runtime_authorization'] == value['manifest']['model_use'] == 'none'
    assert not value['qualification_granted'] and value['manifest']['legal_approval'] == 'not_granted'
    assert count(app) == count(app, authorities.ADMISSION) == 1
    assert value['manifest']['sources'][0]['evidence']['text'] not in payload(app, value['id'])
    assert client.post(endpoint, json=request).json()['id'] == value['id']
    altered = copy.deepcopy(request)
    altered['purpose'] += ' Changed'
    assert client.post(endpoint, json=altered).status_code == 409
    assert client.get(endpoint + '/research-products').json()[0]['id'] == body['product_id']
    candidates = client.get(endpoint + '/candidates', params={'version_id': body['version_id'], 'product_id': body['product_id']})
    assert candidates.status_code == 200 and len(candidates.json()['sources']) == 2
    assert 'rule:r1' in candidates.json()['targets']
    original = next(item for item in client.get(base + '/analyses').json() if item['id'] == analysis['id'])
    assert original['version'] == 1 and original['checks']['legal_approval'] == 'not_granted'
    inventory = client.post(base + '/erasure-plan').json()
    assert inventory['record_counts'][authorities.KIND] == inventory['record_counts'][authorities.ADMISSION] == 1


def reader_analysis(client, base, analysis):
    versions = client.get(base + '/analyses/' + analysis['id'] + '/versions').json()
    return next(item for item in versions if item['id'] == analysis['latest_version_id'])


def test_source_link_does_not_clear_unqualified_legal_norm_blocker(workbench, monkeypatch):
    app, client, base, original, *_ = workbench
    body = copy.deepcopy(original)
    body['rules'][0]['kind'] = 'legal_norm'
    analysis = create(workbench, body)
    _, _, product_id, hits = public_fixture(app, client, base, monkeypatch)
    endpoint = base + '/analyses/' + analysis['id'] + '/authority-contexts'
    spec = {'version_id': analysis['latest_version_id'], 'product_id': product_id,
        'title': 'SYNTHETIC rule candidate', 'purpose': 'SYNTHETIC pending applicability',
        'selections': [{**{key: hits[0][key] for key in authorities.IDENTITY}, 'target_ids': ['rule:r1'],
            'relationship': 'support_candidate', 'note': 'SYNTHETIC lawyer hypothesis only.'}]}
    freeze(client, endpoint, spec)
    record = next(item for item in client.get(base + '/analyses').json() if item['id'] == analysis['id'])
    assert any(item['code'] == 'unqualified_legal_norm' for item in record['checks']['defects'])
    assert record['checks']['effective_disposition'] == 'withheld'


@pytest.mark.parametrize('kind', ['json', 'docx', 'pdf'])
def test_private_export_preserves_exact_pins_and_roles(workbench, monkeypatch, kind):
    app, client, base, *_ = workbench
    endpoint, body, *_ = ready(workbench, monkeypatch)
    value, _ = freeze(client, endpoint, body)
    response = client.get(endpoint + '/' + value['id'] + '/export', params={'format': kind})
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    if kind == 'json':
        assert response.json()['manifest'] == value['manifest']
    elif kind == 'docx':
        text = '\n'.join(p.text for p in Document(io.BytesIO(response.content)).paragraphs)
        assert value['manifest_sha256'] in text and 'hasProvisionVersion' in text
        assert value['manifest']['sources'][0]['evidence']['text'] in text
        assert 'rule:r1' in text and 'SYNTHETIC' in text
    else:
        assert response.content.startswith(b'%PDF')
        text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)
        assert value['manifest_sha256'] in text and 'hasProvisionVersion' in text
        assert ''.join(value['manifest']['sources'][0]['evidence']['text'].split()) in ''.join(text.split())


@pytest.mark.parametrize('change', ['fact', 'document', 'version', 'review', 'recipe', 'research'])
def test_later_private_changes_make_stale_without_rewriting(workbench, monkeypatch, change):
    app, client, base, original, fact, doc_id, *_ = workbench
    endpoint, body, analysis, _, _ = ready(workbench, monkeypatch)
    value, _ = freeze(client, endpoint, body)
    before = payload(app, value['id'])
    if change == 'fact':
        mutate(app, fact['id'], lambda data: data.update(text='SYNTHETIC changed fact'))
    elif change == 'document':
        mutate(app, doc_id, lambda data: data['passages'][0].update(text='SYNTHETIC changed passage'))
    elif change == 'version':
        response = client.post(base + '/analyses/' + analysis['id'] + '/versions', json={**original, 'title': 'SYNTHETIC next version', 'expected_revision': analysis['revision'], 'change_note': 'SYNTHETIC next draft'})
        assert response.status_code == 201
    elif change == 'review':
        from test_analysis_reviews import review_request
        reviews = base + '/analyses/' + analysis['id'] + '/reviews'
        request, _ = review_request(client, reviews, analysis)
        response = client.post(reviews, json=request)
        assert response.status_code == 201, response.text
    elif change == 'recipe':
        monkeypatch.setattr(authorities, 'RECIPE', 'SYNTHETIC-next-context')
    else:
        mutate(app, body['product_id'], lambda data: data.update(title='SYNTHETIC changed research'))
    shown = client.get(endpoint + '/' + value['id'])
    assert shown.status_code == 200, shown.text
    assert shown.json()['freshness']['status'] == 'stale' and shown.json()['manifest'] == value['manifest']
    assert payload(app, value['id']) == before
    assert client.get(endpoint + '/' + value['id'] + '/export').status_code == 409


@pytest.mark.parametrize('change', ['revoke', 'guard_exit', 'sequence', 'source', 'pending'])
def test_public_failures_withhold_all_quotes_and_exports(workbench, monkeypatch, change):
    app, client, base, *_ = workbench
    endpoint, body, _, reader, permit = ready(workbench, monkeypatch)
    value, _ = freeze(client, endpoint, body)
    before = payload(app, value['id'])
    if change == 'revoke':
        permit.active = False
    elif change == 'guard_exit':
        permit.fail_exit = True
    elif change == 'sequence':
        reader.info['pointer']['sequence'] = 2
    elif change == 'source':
        reader._resources.set((FX.passage, LA.quotedText, Literal('SYNTHETIC tampered public quote')))
    else:
        mutate(app, authorities._admission_id(value['id']), lambda data: data.update(publication_guard_completed=False))
    shown = client.get(endpoint + '/' + value['id'])
    assert shown.status_code == 200, shown.text
    assert shown.json()['manifest'] is None and not shown.json()['public_source_access']
    assert shown.json()['freshness']['status'] == 'withheld'
    assert value['manifest']['sources'][0]['evidence']['text'] not in shown.text and 'PRIVATE SOURCE OWNER' not in shown.text
    assert client.get(endpoint + '/' + value['id'] + '/export').status_code == 409
    assert payload(app, value['id']) == before
    assert client.get(endpoint).json()[0]['id'] == value['id']


@pytest.mark.parametrize('phase', ['guard_exit', 'finalize'])
def test_post_commit_failure_keeps_truthful_receipt_and_pending_after_recovery(workbench, monkeypatch, phase):
    app, client, *_ = workbench
    endpoint, body, _, _, permit = ready(workbench, monkeypatch)
    preview = client.post(endpoint + '/preview', json=body).json()
    audit = authorities._audit
    def fail_after_save(*args, **kwargs):
        audit(*args, **kwargs)
        permit.fail_exit = True
    if phase == 'guard_exit':
        monkeypatch.setattr(authorities, '_audit', fail_after_save)
    else:
        monkeypatch.setattr(authorities, '_finalize', lambda *_: (_ for _ in ()).throw(RuntimeError('PRIVATE FINALIZATION')))
    request = {**body, 'request_id': uuid4().hex, 'expected_preview_sha256': preview['preview_sha256']}
    response = client.post(endpoint, json=request)
    assert response.status_code == 409 and response.json()['outcome'] == 'committed_needs_revalidation', response.text
    ident = response.json()['id']
    assert count(app) == count(app, authorities.ADMISSION) == 1 and 'PRIVATE' not in response.text
    permit.fail_exit = False
    shown = client.get(endpoint + '/' + ident).json()
    assert shown['manifest'] is None and shown['freshness']['reasons'] == ['post_commit_authorization_pending']
    retried = client.post(endpoint, json=request)
    assert retried.status_code == 201 and retried.json()['manifest'] is None
    assert client.get(endpoint + '/' + ident + '/export').status_code == 409


@pytest.mark.parametrize('phase', ['render_revoke', 'render_fact', 'save_fact', 'save_product'])
def test_final_save_and_export_checks_discard_partial_output(workbench, monkeypatch, phase):
    app, client, *_rest, fact, _doc, _text = workbench
    endpoint, body, _, _, permit = ready(workbench, monkeypatch)
    value = None
    preview = client.post(endpoint + '/preview', json=body).json()
    if phase.startswith('save'):
        audit = authorities._audit
        def late(*args, **kwargs):
            audit(*args, **kwargs)
            session = args[0]
            ident = fact['id'] if phase == 'save_fact' else body['product_id']
            row = session.get(Record, ident)
            data = app.state.store.decode(row)
            data.update(text='SYNTHETIC changed') if phase == 'save_fact' else data.update(title='SYNTHETIC changed')
            app.state.store.update(row, data)
        monkeypatch.setattr(authorities, '_audit', late)
        response = client.post(endpoint, json={**body, 'request_id': uuid4().hex, 'expected_preview_sha256': preview['preview_sha256']})
        assert response.status_code == 409 and count(app) == count(app, authorities.ADMISSION) == 0
        with app.state.store.session() as session:
            assert not session.scalar(select(Audit).where(Audit.action == 'analysis_authority_context_frozen'))
    else:
        value, _ = freeze(client, endpoint, body)
        def render(*args):
            if phase == 'render_revoke':
                permit.active = False
            else:
                mutate(app, fact['id'], lambda data: data.update(text='SYNTHETIC changed during render'))
            return Response(b'PRIVATE PARTIAL EXPORT')
        monkeypatch.setattr(authorities, 'render_export', render)
        response = client.get(endpoint + '/' + value['id'] + '/export?format=docx')
        assert response.status_code == 409 and 'PRIVATE PARTIAL EXPORT' not in response.text


@pytest.mark.parametrize('change', ['duplicate', 'wrong_target', 'foreign_source', 'too_many', 'text_override', 'unknown_field', 'blank_reason', 'bad_nonce'])
def test_strict_selection_and_no_client_source_overrides(workbench, monkeypatch, change):
    app, client, *_ = workbench
    endpoint, body, *_ = ready(workbench, monkeypatch)
    if change == 'duplicate':
        body['selections'] *= 2
    elif change == 'wrong_target':
        body['selections'][0]['target_ids'] = ['rule:invented']
    elif change == 'foreign_source':
        body['selections'][0]['assertion_id'] = 'urn:other:assertion'
    elif change == 'too_many':
        body['selections'] *= 9
    elif change == 'text_override':
        body['selections'][0]['text'] = 'SYNTHETIC forged source'
    elif change == 'unknown_field':
        body['approval'] = True
    elif change == 'blank_reason':
        body['selections'][0]['note'] = '   '
    else:
        body.update(request_id='bad', expected_preview_sha256='c' * 64)
    response = client.post(endpoint if change == 'bad_nonce' else endpoint + '/preview', json=body)
    assert response.status_code == 422, response.text
    assert count(app) == 0


@pytest.mark.parametrize('field', ['text', 'source_version_id', 'authority_id', 'valid_from', 'validity_checked_through', 'assertion_id'])
def test_retained_research_metadata_cannot_substitute_canonical_source(workbench, monkeypatch, field):
    app, client, *_ = workbench
    endpoint, body, *_ = ready(workbench, monkeypatch)
    def change(data):
        hit = data['authority_candidates']['hits'][0]
        hit[field] = 'SYNTHETIC forged ' + field
    mutate(app, body['product_id'], change)
    response = client.post(endpoint + '/preview', json=body)
    assert response.status_code in {409, 422}, response.text
    assert count(app) == 0


def test_byte_limit_cross_workspace_auth_and_archive(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, body, analysis, reader, permit = ready(workbench, monkeypatch)
    foreign = client.post('/api/v1/matters', json={'title': 'SYNTHETIC foreign', 'domain': 'contracts'}).json()['id']
    foreign_endpoint = f'/api/v1/matters/{foreign}/analyses/{analysis["id"]}/authority-contexts'
    assert client.post(foreign_endpoint + '/preview', json=body).status_code == 404
    monkeypatch.setattr(authorities, 'MAX_BYTES', 500)
    assert client.post(endpoint + '/preview', json=body).status_code == 409
    assert count(app) == 0

    monkeypatch.undo()
    monkeypatch.setattr(app.state.graph, 'release', reader)
    preview = client.post(endpoint + '/preview', json=body)
    assert preview.status_code == 409  # No synthetic permit survives undo.
    monkeypatch.setattr(reader, 'current_guard', permit.guard)
    preview = client.post(endpoint + '/preview', json=body)
    assert preview.status_code == 200
    request = {**body, 'request_id': uuid4().hex, 'expected_preview_sha256': preview.json()['preview_sha256']}
    token = client.headers.pop('X-CSRF-Token')
    assert client.post(endpoint, json=request).status_code == 403
    client.headers['X-CSRF-Token'] = token
    mutate(app, base.split('/')[-1], lambda data: data.update(status='archived'))
    assert client.post(endpoint, json=request).status_code == 409
    assert count(app) == 0


def test_citation_interval_does_not_promote_expired_target_version_to_applicability(workbench, monkeypatch):
    _, client, _, *_ = workbench
    endpoint, body, _, reader, _ = ready(workbench, monkeypatch)
    candidate = reader._search_document('jurisprudence', FX['cites-a'], FX.passage, str(FX.decision))
    body['selections'][0].update({key: candidate[key] for key in authorities.IDENTITY})
    value, _ = freeze(client, endpoint, body)
    source = value['manifest']['sources'][0]
    assert source['evidence']['predicate'] == str(LA.cites)
    assert source['temporal_alignment']['within_assertion_interval'] is True
    assert source['temporal_alignment']['target_version_within_interval'] is False
    assert source['evidence']['binding_effect'] == source['temporal_alignment']['applicability'] == 'not_assessed'


def test_unresolved_citation_target_remains_unknown_and_ambiguous_assertion_is_rejected(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, body, _, reader, _ = ready(workbench, monkeypatch)
    candidate = reader._search_document('jurisprudence', FX['cites-a'], FX.passage, str(FX.decision))
    body['selections'][0].update({key: candidate[key] for key in authorities.IDENTITY})
    for prop in (LA.versionOf, LA.versionResolution, LA.validFrom, LA.validTo):
        reader._resources.remove((FX['version-a'], prop, None))
    response = client.post(endpoint + '/preview', json=body)
    assert response.status_code == 200, response.text
    source = response.json()['manifest']['sources'][0]
    assert source['evidence']['target_provision_version']['version_of'] is None
    assert source['evidence']['target_provision_version']['validity']['kind'] == 'unknown'
    assert source['temporal_alignment']['target_version_within_interval'] is None
    for triple in reader._graphs['jurisprudence'].triples((FX['cites-a'], None, None)):
        reader._graphs['structure'].add(triple)
    assert client.post(endpoint + '/preview', json=body).status_code == 409
    assert count(workbench[0]) == 0


@pytest.mark.parametrize('phase', ['before_read', 'during_export', 'during_save'])
def test_current_membership_loss_never_returns_private_or_public_content(workbench, monkeypatch, phase):
    app, client, base, *_ = workbench
    endpoint, body, *_ = ready(workbench, monkeypatch)
    value, _ = freeze(client, endpoint, body)
    def revoke(session):
        session.query(Membership).filter(Membership.matter_id == base.split('/')[-1]).delete()
        session.flush()
    if phase == 'before_read':
        with app.state.store.session() as session:
            revoke(session)
            session.commit()
        for path in (endpoint, endpoint + '/' + value['id'], endpoint + '/' + value['id'] + '/export', endpoint + '/research-products'):
            response = client.get(path)
            assert response.status_code == 404 and 'SYNTHETIC' not in response.text
    elif phase == 'during_save':
        preview = client.post(endpoint + '/preview', json=body).json()
        audit = authorities._audit
        def late(*args, **kwargs):
            audit(*args, **kwargs)
            revoke(args[0])
        monkeypatch.setattr(authorities, '_audit', late)
        response = client.post(endpoint, json={**body, 'request_id': uuid4().hex, 'expected_preview_sha256': preview['preview_sha256']})
        assert response.status_code == 404 and 'SYNTHETIC' not in response.text
        assert count(app) == 1
    else:
        def render(*args):
            with app.state.store.session() as session:
                revoke(session)
                session.commit()
            return Response(b'PRIVATE PARTIAL EXPORT')
        monkeypatch.setattr(authorities, 'render_export', render)
        response = client.get(endpoint + '/' + value['id'] + '/export?format=docx')
        assert response.status_code == 404 and 'PRIVATE PARTIAL EXPORT' not in response.text


@pytest.mark.parametrize('kind', [authorities.KIND, authorities.ADMISSION])
def test_corrupt_sealed_binding_fails_before_any_quote_is_displayed(workbench, monkeypatch, kind):
    app, client, *_ = workbench
    endpoint, body, *_ = ready(workbench, monkeypatch)
    value, _ = freeze(client, endpoint, body)
    ident = value['id'] if kind == authorities.KIND else authorities._admission_id(value['id'])
    mutate(app, ident, lambda data: data.update(manifest_sha256='0' * 64))
    for path in (endpoint, endpoint + '/' + value['id'], endpoint + '/' + value['id'] + '/export'):
        response = client.get(path)
        assert response.status_code == 409 and 'SYNTHETIC' not in response.text
