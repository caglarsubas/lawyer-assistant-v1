"""Source-bound human judgments; synthetic fixtures cannot qualify Turkish law."""

import copy
import io
from uuid import uuid4

import pytest
from docx import Document
from pypdf import PdfReader
from sqlalchemy import func, select
from test_analysis_authorities import freeze, mutate, payload, ready
from test_analysis_authorities import workbench as workbench_fixture

from app import analysis_authorities as authorities
from app import authority_findings as findings
from app.db import Audit, Membership, Record, User

workbench = workbench_fixture


def setup(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, spec, analysis, reader, permit = ready(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    return endpoint + '/' + context['id'] + '/reviews', context, analysis, reader, permit


def request(client, endpoint, *, outcome='not_assessed'):
    response = client.get(endpoint + '/context')
    assert response.status_code == 200, response.text
    value = response.json()
    body = {'expected_basis_sha256': value['basis_sha256'], 'expected_review_id': value['expected_review_id'],
        'request_id': uuid4().hex, 'note': 'SYNTHETIC source-bound observation; not legal approval.',
        'review_seconds': None, 'sources': [{**source['selection'], 'observations': [
            {'dimension': key, 'outcome': outcome, 'note': 'SYNTHETIC — insufficient evidence and review pending.'}
            for key in value['dimensions']]} for source in value['authority_context']['manifest']['sources']]}
    for source in body['sources']:
        source.pop('relationship')
        source.pop('note')
    return body, value


def saved(client, endpoint, body=None):
    if body is None:
        body, _ = request(client, endpoint)
    response = client.post(endpoint, json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


def count(app, kind):
    with app.state.store.session() as session:
        return session.scalar(select(func.count()).select_from(Record).where(Record.kind == kind))


def test_record_exact_context_targets_original_quotes_unknowns_and_no_legal_promotion(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, context, analysis, *_ = setup(workbench, monkeypatch)
    original = payload(app, context['id'])
    value, _ = saved(client, endpoint)
    data = value['snapshot']
    assert value['freshness']['status'] == 'current' and value['is_latest_review']
    assert data['context_snapshot'] == context
    assert data['previous_review_id'] is None and data['sequence'] == 1
    assert data['assessment']['review_seconds'] is None
    assert {item['outcome'] for item in data['assessment']['sources'][0]['observations']} == {'not_assessed'}
    assert value['qualification_granted'] is False and value['legal_approval'] == 'not_granted'
    assert data['model_use'] == 'none' and data['context_snapshot']['manifest']['matter_applicability'] == 'not_assessed'
    assert payload(app, context['id']) == original
    current = client.get(base + '/analyses').json()[0]
    assert current['latest_version_id'] == analysis['latest_version_id']
    assert current['checks'] == analysis['checks']
    assert data['reviewer_id'] and data['reviewer_name'] and data['dimensions'] == findings.DIMENSIONS
    assert 'SYNTHETIC' not in payload(app, value['id'])


@pytest.mark.parametrize('bad', ['source', 'missing_dimension', 'duplicate_dimension', 'target', 'omit_target', 'duplicate_source', 'whitespace', 'clock_boolean', 'extra_quote'])
def test_malformed_or_incomplete_judgments_cannot_be_saved(workbench, monkeypatch, bad):
    app, client, *_ = workbench
    endpoint, *_ = setup(workbench, monkeypatch)
    body, _ = request(client, endpoint)
    source = body['sources'][0]
    if bad == 'source':
        source['assertion_id'] = 'urn:synthetic:unselected'
    if bad == 'missing_dimension':
        source['observations'].pop()
    if bad == 'duplicate_dimension':
        source['observations'][-1] = source['observations'][0]
    if bad == 'target':
        source['target_ids'] = ['conclusion']
    if bad == 'omit_target':
        source['target_ids'].pop()
    if bad == 'duplicate_source':
        body['sources'].append(copy.deepcopy(source))
    if bad == 'whitespace':
        source['observations'][0]['note'] = '   '
    if bad == 'clock_boolean':
        body['review_seconds'] = True
    if bad == 'extra_quote':
        source['text'] = 'SYNTHETIC fabricated quote'
    assert client.post(endpoint, json=body).status_code == 422
    assert count(app, findings.KIND) == count(app, findings.HEAD) == count(app, findings.ADMISSION) == 0


def test_supported_is_only_the_lawyers_declared_observation_and_preserves_blockers(workbench, monkeypatch):
    _, client, base, *_ = workbench
    workbench[3]['rules'][0]['kind'] = 'legal_norm'
    endpoint, context, analysis, *_ = setup(workbench, monkeypatch)
    body, _ = request(client, endpoint, outcome='supported')
    value, _ = saved(client, endpoint, body)
    assert value['snapshot']['legal_approval'] == 'not_granted'
    assert value['snapshot']['context_snapshot']['manifest']['matter_applicability'] == 'not_assessed'
    assert client.get(base + '/analyses').json()[0]['checks'] == analysis['checks']
    assert analysis['checks']['critical_count'] > 0
    assert client.get(base + '/analyses/' + analysis['id'] + '/authority-contexts/' + context['id']).json() == context


def test_retry_and_conflicting_head_preserve_immutable_prior_and_no_silent_merge(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, *_ = setup(workbench, monkeypatch)
    body, _ = request(client, endpoint)
    value, _ = saved(client, endpoint, body)
    prior = payload(app, value['id'])
    assert client.post(endpoint, json=body).json() == value
    assert client.post(endpoint, json={**body, 'note': 'SYNTHETIC different'}).status_code == 409
    assert client.post(endpoint, json={**body, 'request_id': uuid4().hex}).status_code == 409
    next_body, _ = request(client, endpoint, outcome='needs_change')
    second, _ = saved(client, endpoint, next_body)
    assert second['snapshot']['previous_review_id'] == value['id'] and second['sequence'] == 2
    stale = client.get(endpoint + '/' + value['id']).json()
    assert stale['freshness']['reasons'] == ['newer_review_exists'] and not stale['is_latest_review']
    assert stale['snapshot'] == value['snapshot'] and payload(app, value['id']) == prior
    assert client.get(endpoint + '/' + value['id'] + '/export').status_code == 409
    assert [item['sequence'] for item in client.get(endpoint).json()] == [2, 1]


@pytest.mark.parametrize('change', ['private', 'context_recipe', 'review_recipe', 'dimensions', 'reviewer_role'])
def test_dependencies_require_rereview_without_rewriting_judgments(workbench, monkeypatch, change):
    app, client, *_ = workbench
    endpoint, context, analysis, *_ = setup(workbench, monkeypatch)
    value, _ = saved(client, endpoint)
    prior = payload(app, value['id'])
    if change == 'private':
        mutate(app, analysis['id'], lambda data: data.update(title='SYNTHETIC changed analysis'))
    if change == 'context_recipe':
        monkeypatch.setattr(authorities, 'RECIPE', 'future-authority-context')
    if change == 'review_recipe':
        monkeypatch.setattr(findings, 'RECIPE', 'future-findings')
    if change == 'dimensions':
        monkeypatch.setattr(findings, 'DIMENSIONS', {**findings.DIMENSIONS, 'history': 'Changed wording'})
    if change == 'reviewer_role':
        with app.state.store.session() as session:
            session.get(User, value['reviewer_id']).role = 'reader'
            session.commit()
    stale = client.get(endpoint + '/' + value['id']).json()
    assert stale['freshness']['status'] == 'stale' and stale['snapshot'] == value['snapshot']
    assert payload(app, value['id']) == prior
    assert client.get(endpoint + '/' + value['id'] + '/export').status_code == 409
    assert payload(app, context['id'])


@pytest.mark.parametrize('failure', ['revoked', 'guard_exit', 'pin', 'missing_context'])
def test_withheld_has_no_original_quote_or_free_text_notes(workbench, monkeypatch, failure):
    app, client, *_ = workbench
    endpoint, context, _, reader, permit = setup(workbench, monkeypatch)
    body, _ = request(client, endpoint)
    body['note'] = 'SECRET NOTE copied from public text'
    value, _ = saved(client, endpoint, body)
    quote = value['snapshot']['context_snapshot']['manifest']['sources'][0]['evidence']['text']
    if failure == 'revoked':
        permit.active = False
    if failure == 'guard_exit':
        permit.fail_exit = True
    if failure == 'pin':
        reader.info['pointer']['sequence'] += 1
    if failure == 'missing_context':
        with app.state.store.session() as session:
            session.delete(session.get(Record, context['id']))
            session.commit()
    response = client.get(endpoint + '/' + value['id'])
    assert response.status_code == 200 and response.json()['snapshot'] is None
    assert response.json()['freshness']['status'] == 'withheld'
    assert 'SECRET NOTE' not in response.text and quote not in response.text
    assert client.get(endpoint + '/' + value['id'] + '/export').status_code == 409


def test_commit_then_guard_failure_keeps_truthful_pending_receipt_after_recovery(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, *_rest, permit = setup(workbench, monkeypatch)
    body, _ = request(client, endpoint)
    audit = findings._audit
    armed = [False]
    commit = app.state.store.session.class_.commit
    def lose_permission(*args):
        audit(*args)
        armed[0] = True
    def after_commit(session):
        commit(session)
        if armed[0]:
            armed[0] = False
            permit.fail_exit = True
    monkeypatch.setattr(findings, '_audit', lose_permission)
    monkeypatch.setattr(app.state.store.session.class_, 'commit', after_commit)
    response = client.post(endpoint, json=body)
    assert response.status_code == 409 and response.json()['outcome'] == 'committed_needs_revalidation'
    ident = response.json()['id']
    assert 'SYNTHETIC' not in response.text and count(app, findings.KIND) == 1
    permit.fail_exit = False
    monkeypatch.setattr(findings, '_audit', audit)
    assert client.get(endpoint + '/' + ident).json()['freshness']['reasons'] == ['post_commit_authorization_pending']
    assert client.post(endpoint, json=body).json()['snapshot'] is None
    assert client.get(endpoint + '/' + ident + '/export').status_code == 409
    next_value, _ = saved(client, endpoint)
    assert next_value['sequence'] == 2 and next_value['snapshot']['previous_review_id'] == ident


def test_unflushed_late_private_change_rolls_back_review_head_receipt_and_audit(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, _, analysis, *_ = setup(workbench, monkeypatch)
    body, _ = request(client, endpoint)
    original = payload(app, analysis['id'])
    audit = findings._audit
    def late_change(session, *args):
        audit(session, *args)
        row = session.get(Record, analysis['id'])
        data = app.state.store.decode(row)
        data['title'] = 'SYNTHETIC changed during save'
        app.state.store.update(row, data)
    monkeypatch.setattr(findings, '_audit', late_change)
    assert client.post(endpoint, json=body).status_code == 409
    assert count(app, findings.KIND) == count(app, findings.HEAD) == count(app, findings.ADMISSION) == 0
    assert payload(app, analysis['id']) == original
    with app.state.store.session() as session:
        assert not session.scalar(select(Audit).where(Audit.action == 'authority_findings_recorded'))


@pytest.mark.parametrize('format', ['json', 'docx', 'pdf'])
def test_authenticated_attachment_contains_original_source_and_human_judgment(workbench, monkeypatch, format):
    _, client, *_ = workbench
    endpoint, *_ = setup(workbench, monkeypatch)
    value, _ = saved(client, endpoint)
    response = client.get(endpoint + '/' + value['id'] + '/export?format=' + format)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff' and 'attachment' in response.headers['content-disposition']
    if format == 'json':
        text = response.text
    elif format == 'docx':
        text = '\n'.join(item.text for item in Document(io.BytesIO(response.content)).paragraphs)
    else:
        text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)
    assert value['review_sha256'] in text
    assert value['snapshot']['context_manifest_sha256'] in text
    assert value['snapshot']['context_snapshot']['manifest']['sources'][0]['evidence']['text'] in text
    assert 'not_assessed' in text


@pytest.mark.parametrize('failure', ['private', 'head', 'permission'])
def test_late_export_change_discards_rendered_bytes(workbench, monkeypatch, failure):
    app, client, *_ = workbench
    endpoint, _, analysis, _, permit = setup(workbench, monkeypatch)
    value, _ = saved(client, endpoint)
    render = findings.render_export
    def changed(*args):
        response = render(*args)
        if failure == 'private':
            mutate(app, analysis['id'], lambda data: data.update(title='SYNTHETIC later change'))
        if failure == 'permission':
            permit.active = False
        if failure == 'head':
            saved(client, endpoint)
        return response
    monkeypatch.setattr(findings, 'render_export', changed)
    response = client.get(endpoint + '/' + value['id'] + '/export?format=docx')
    assert response.status_code == 409 and not response.content.startswith(b'PK')


def test_account_scope_csrf_archive_integrity_and_bounds(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, context, *_ = setup(workbench, monkeypatch)
    body, _ = request(client, endpoint)
    headers = client.headers.pop('X-CSRF-Token')
    assert client.post(endpoint, json=body).status_code == 403
    client.headers['X-CSRF-Token'] = headers
    assert client.get(endpoint + '?limit=21').status_code == 422
    monkeypatch.setattr(findings, 'MAX_BYTES', 200)
    assert client.post(endpoint, json=body).status_code == 409 and count(app, findings.KIND) == 0
    monkeypatch.setattr(findings, 'MAX_BYTES', 2 * 1024 * 1024)
    value, _ = saved(client, endpoint)
    mutate(app, base.split('/')[-1], lambda data: data.update(status='archived'))
    assert client.get(endpoint + '/context').json()['can_record'] is False
    assert client.post(endpoint, json={**body, 'request_id': uuid4().hex}).status_code == 409
    mutate(app, value['id'], lambda data: data.update(note='SYNTHETIC tamper without resealing'))
    assert client.get(endpoint + '/' + value['id']).status_code == 409
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        session.delete(session.get(Membership, (base.split('/')[-1], user.id)))
        session.commit()
    assert client.get(endpoint).status_code == 404
    assert client.get(endpoint + '/' + value['id']).status_code == 404


def test_actual_signed_physical_source_and_current_rights_guard_review_notes(workbench, monkeypatch, tmp_path):
    from test_analysis_authority_release import signed_source

    _, client, *_ = workbench
    endpoint, spec, _, permission, prepared = signed_source(workbench, monkeypatch, tmp_path / 'signed-source')
    context, _ = freeze(client, endpoint, spec)
    reviews = endpoint + '/' + context['id'] + '/reviews'
    value, _ = saved(client, reviews)
    source = value['snapshot']['context_snapshot']['manifest']['sources'][0]['evidence']
    assert source['text'] == prepared['snapshot']['package'].text[source['start_offset']:source['end_offset']]
    assert value['snapshot']['context_snapshot']['manifest']['sources'][0]['temporal_alignment']['target_version_within_interval'] is False
    permission.active = False
    assert client.get(reviews + '/' + value['id']).json()['snapshot'] is None
    assert client.get(reviews + '/' + value['id'] + '/export').status_code == 409
