"""Exact private handoff metadata is never evidence access or admission repair."""

import copy
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from test_analysis_authorities import mutate
from test_analysis_workbench import create
from test_authority_adjudications import reviewer
from test_portfolio_source_reviews import other_case
from test_source_analysis_reviews import freeze, reviewed, setup
from test_source_analysis_reviews import workbench as workbench_fixture
from test_source_review_readiness import no_public_reads

from app import source_analysis_reviews as reviews
from app.db import Membership, Record, User

workbench = workbench_fixture


def read(client, endpoint, context):
    response = client.get(endpoint + '/' + context['id'] + '/navigation-context')
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    value = response.json()
    assert value['context_id'] == value['context']['id'] == context['id']
    assert value['source_verification'] == 'not_checked' and value['legal_readiness'] == 'not_established'
    assert value['qualification_granted'] is False
    for secret in ['TEST ONLY 📄', 'PRIVATE SOURCE NOTE', 'PRIVATE REVIEW NOTE', 'target_snapshots', 'source_candidates',
                   'analysis_content', 'recorded_by', 'sources', 'purpose', 'legal_approval']:
        assert secret not in response.text
    return value


def test_exact_frozen_version_and_historical_review_do_not_revalidate_or_repair(workbench, monkeypatch):
    app, client, base, payload, *_ = workbench
    endpoint, _, analysis, reader, permit, context, _, *_ = reviewed(workbench, monkeypatch)
    old_review = client.get(endpoint + '/' + context['id']).json()['review']['id']
    changed = copy.deepcopy(payload)
    changed['rules'][0]['text'] = 'TEST ONLY changed private version'
    newer = client.post(base + '/analyses/' + analysis['id'] + '/versions', json={**changed,
        'expected_revision': analysis['revision'], 'change_note': 'TEST ONLY new version'})
    assert newer.status_code == 201, newer.text
    permit.active = False
    no_public_reads(monkeypatch, reader)
    value = read(client, endpoint, context)
    assert value['context']['manifest_sha256'] == context['manifest_sha256']
    assert value['context']['version_id'] == analysis['latest_version_id']
    assert value['analysis']['current_version_id'] == newer.json()['latest_version_id']
    assert value['version_relation'] == 'different' and value['tools_available']
    assert value['historical_review']['id'] == old_review
    assert value['historical_review']['state'] == 'reviewed_conditional'
    assert value['admission'] == {'context_state': 'complete', 'review_state': 'complete'}


def test_exact_record_outside_first_pages_without_list_scanning(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, analysis, reader, _ = setup(workbench, monkeypatch)
    oldest, _ = freeze(client, endpoint, spec)
    for _ in range(10):
        freeze(client, endpoint, spec)
    for _ in range(20):
        create(workbench)
    assert oldest['id'] not in {row['id'] for row in client.get(endpoint + '?limit=10').json()}
    assert analysis['id'] not in {row['id'] for row in client.get(endpoint.split('/analyses/')[0] + '/analyses?limit=20').json()}
    no_public_reads(monkeypatch, reader)
    value = read(client, endpoint, oldest)
    assert value['historical_review']['state'] == 'unreviewed'
    assert value['context']['manifest_sha256'] == oldest['manifest_sha256']


@pytest.mark.parametrize('fault', ['pending_context', 'missing_context', 'pending_review', 'missing_review', 'tampered_context'])
def test_pending_or_missing_admissions_stay_historical_and_unchanged(workbench, monkeypatch, fault):
    app, client, *_ = workbench
    endpoint, _, _, reader, _, context, _, *_ = reviewed(workbench, monkeypatch)
    review_id = client.get(endpoint + '/' + context['id']).json()['review']['id']
    target = context['id'] if 'context' in fault else review_id
    admission_id = reviews._id('saa-', target)
    if fault.startswith('pending'):
        mutate(app, admission_id, lambda packet: packet.update(guard_completed=False))
    elif fault.startswith('missing'):
        with app.state.store.session() as session:
            session.execute(delete(Record).where(Record.id == admission_id))
            session.commit()
    else:
        mutate(app, target, lambda packet: packet['manifest'].update(purpose='CORRUPTED PRIVATE NOTE'))
    no_public_reads(monkeypatch, reader)
    with app.state.store.session() as session:
        before = {row.id: row.revision for row in session.scalars(select(Record)).all()}
    value = read(client, endpoint, context)
    if fault in {'missing_context', 'tampered_context'}:
        assert not value['tools_available'] and value['integrity'] == 'unavailable'
        assert value['context']['manifest_sha256'] is None and value['context']['version_id'] is None
    elif fault == 'pending_context':
        assert value['admission']['context_state'] == 'pending'
    elif fault == 'pending_review':
        assert value['admission']['review_state'] == 'pending'
        assert value['historical_review']['id'] == review_id
    else:
        assert value['admission']['review_state'] == 'unavailable'
        assert value['historical_review']['state'] == 'unknown'
    with app.state.store.session() as session:
        assert before == {row.id: row.revision for row in session.scalars(select(Record)).all()}


def test_mixed_foreign_missing_ids_and_content_grant_loss_never_decrypt_foreign_packets(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, _, reader, _ = setup(workbench, monkeypatch)
    context, _ = freeze(client, endpoint, spec)
    _, _, foreign_endpoint, _, _, _, foreign = other_case(workbench, monkeypatch)
    reviewer(workbench)
    no_public_reads(monkeypatch, app.state.graph.release)
    decode = app.state.store.decode
    def scoped(record):
        if record.matter_id and record.matter_id != workbench[2].split('/')[-1]:
            pytest.fail('Foreign private packet decrypted')
        return decode(record)
    monkeypatch.setattr(app.state.store, 'decode', scoped)
    assert client.get(endpoint + '/' + foreign['id'] + '/navigation-context').status_code == 404
    assert client.get(foreign_endpoint + '/' + context['id'] + '/navigation-context').status_code == 404
    assert client.get(endpoint + '/' + reviews._prefix(workbench[2].split('/')[-1], endpoint.split('/')[-2]) + uuid4().hex + '/navigation-context').status_code == 404
    with app.state.store.session() as session:
        actor = session.scalar(select(User).where(User.username == 'reviewer'))
        session.execute(delete(Membership).where(Membership.user_id == actor.id))
        session.commit()
    assert client.get(endpoint + '/' + context['id'] + '/navigation-context').status_code == 404


@pytest.mark.parametrize('mode', ['guide', 'chat', 'daily', 'weekly', 'monthly'])
def test_handoff_assistant_is_a_guide_without_portfolio_or_inference(workbench, monkeypatch, mode):
    app, client, base, *_ = workbench
    monkeypatch.setattr('app.assistant.list_workspaces', lambda *_a, **_k: pytest.fail('No portfolio read'))
    monkeypatch.setattr(app.state.provider, 'generate', lambda *_a, **_k: pytest.fail('No inference'))
    response = client.post('/api/v1/assistant/respond', json={'mode': mode, 'question': 'How do I progress?',
        'context': {'page': 'matters', 'section': 'source-review', 'workspace_id': base.split('/')[-1]}})
    assert response.status_code == 200, response.text
    assert not response.json()['provider_used'] and response.json()['sources'] == [] and response.json()['period'] is None
    assert client.post('/api/v1/assistant/respond', json={'mode': mode, 'question': 'test',
        'context': {'page': 'matters', 'section': 'source-review', 'workspace_id': 'foreign-matter'}}).status_code == 404
