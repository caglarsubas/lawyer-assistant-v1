"""Invented comparisons and reviewer declarations; no real legal adjudication."""

import copy
import io
import json
from threading import Event
from uuid import uuid4

import pytest
from docx import Document
from sqlalchemy import select
from test_analysis_reviews import prepare, review_request
from test_analysis_workbench import workbench as workbench_fixture

from app import analysis_adjudication as adjudication
from app import analysis_workbench
from app.analysis_reviews import ReviewInput, _input_value
from app.db import Membership, Record, User, digest
from app.evidence_prompt import canonical


@pytest.fixture
def workbench(tmp_path):
    yield from workbench_fixture.__wrapped__(tmp_path)


def pair(workbench, *, unchanged=False, reviewed=True):
    _, client, base, payload, *_ = workbench
    original, endpoint = prepare(workbench)
    event = None
    if reviewed:
        body, _ = review_request(client, endpoint, original, decision='changes_requested')
        body['findings'].append({'target_id': 'application:a1', 'severity': 'major',
                                 'text': 'SYNTHETIC — İstisnanın uygulanması açıklanmalı.',
                                 'evidence_ids': ['synthetic-clause']})
        response = client.post(endpoint, json=body)
        assert response.status_code == 201, response.text
        event = response.json()
    changed = copy.deepcopy(payload)
    if not unchanged:
        changed['applications'][0]['rationale'] = 'SYNTHETIC — Teslim ve yazılı kabul birbirinden ayrı incelenmelidir.'
        changed['conclusion']['text'] = 'SYNTHETIC — Kabulün kapsamı bilinmeden kesin ödeme sonucu çıkarılamaz.'
    response = client.post(base + '/analyses/' + original['id'] + '/versions', json={
        **changed, 'expected_revision': original['revision'], 'change_note': 'SYNTHETIC explicit revision'})
    assert response.status_code == 201, response.text
    return original, response.json(), endpoint, event


def assessment_body(client, endpoint, record, *, decision='reviewed_conditional'):
    body, context = review_request(client, endpoint, record, decision=decision)
    comparison = context['revision_comparison']
    body['revision_assessment'] = {
        'comparison_sha256': comparison['comparison_sha256'], 'review_seconds': 90,
        'observations': [{'dimension': key, 'outcome': 'confirmed',
                          'note': 'SYNTHETIC — Bu boyut, alıntıyla ayrıca karşılaştırıldı.',
                          'target_ids': ['conclusion', 'application:a1'], 'source_refs': ['after:synthetic-clause']}
                         for key in adjudication.DIMENSIONS],
        'finding_dispositions': [{'finding_index': item['finding_index'], 'outcome': 'repaired',
                                  'note': 'SYNTHETIC — Değişen metin alıntıyla karşılaştırıldı.',
                                  'target_ids': [item['target_id']], 'source_refs': ['after:synthetic-clause']}
                                 for item in comparison['findings']],
    }
    # Private selected documents cannot establish public adverse-authority coverage.
    body['revision_assessment']['observations'][4].update(outcome='not_assessed', source_refs=[],
                                                        note='SYNTHETIC — Bağımsız karşı otorite araştırması eksik.')
    return body, comparison


def predecessor_only_pair(workbench):
    app, client, base, payload, *_ = workbench
    extra_text = 'SYNTHETIC — Önceki taslakta seçilen ayrı yazılı beyan.'
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        extra = app.state.store.add(session, 'document', user, {
            'name': 'SYNTHETIC-before-only.txt', 'status': 'extracted', 'sha256': digest(extra_text),
            'passages': [{'id': 'before-only', 'text': extra_text, 'locator': 'SYNTHETIC §2'}]}, base.rsplit('/', 1)[1])
        session.commit()
    previous_payload = copy.deepcopy(payload)
    previous_payload['evidence'].append({'evidence_id': 'before-only', 'passage_sha256': digest(extra_text),
                                        'document_revision': extra.revision, 'start': 0, 'end': len(extra_text)})
    original, endpoint = prepare(workbench, previous_payload)
    body, _ = review_request(client, endpoint, original, decision='changes_requested')
    assert client.post(endpoint, json=body).status_code == 201
    changed = copy.deepcopy(payload)
    changed['conclusion']['text'] = 'SYNTHETIC — Güncel seçimin sınırları açık tutulmalıdır.'
    revised = client.post(base + '/analyses/' + original['id'] + '/versions', json={
        **changed, 'expected_revision': original['revision'], 'change_note': 'SYNTHETIC narrower sources'}).json()
    return revised, endpoint, extra.id


def test_exact_source_linked_review_retains_both_versions_and_prior_findings(workbench, monkeypatch):
    app, client, base, *_ = workbench
    original, revised, endpoint, previous_review = pair(workbench)
    monkeypatch.setattr(app.state.provider, 'suggest_analysis', lambda *_a, **_k: pytest.fail('No inference'))
    monkeypatch.setattr(app.state.graph, 'tool', lambda *_a, **_k: pytest.fail('No public authority query'))
    body, comparison = assessment_body(client, endpoint, revised)
    assert comparison['base_version_id'] == original['latest_version_id']
    assert comparison['candidate_version_id'] == revised['latest_version_id']
    assert comparison['base_review_id'] == previous_review['id']
    assert comparison['base_content_sha256'] == previous_review['content_sha256']
    assert comparison['public_adverse_authority_qualified'] is False and comparison['benefit_established'] is False
    assert {item['target_id'] for item in comparison['changes']} == {'application:a1', 'conclusion'}
    assert comparison['changes'][0]['before']['rationale'] == original['applications'][0]['rationale']
    assert [item['text'] for item in comparison['sources']] == [original['evidence'][0]['text']] * 2
    assert comparison['sources'][0]['text'].endswith('\r\n')
    frozen_ids = (original['latest_version_id'], revised['latest_version_id'], previous_review['id'])
    with app.state.store.session() as session:
        frozen = {ident: session.get(Record, ident).payload for ident in frozen_ids}
    response = client.post(endpoint, json=body)
    assert response.status_code == 201, response.text
    event = response.json()
    assert event['revision_assessment'] == body['revision_assessment']
    assert event['revision_comparison_snapshot'] == comparison
    assert client.post(endpoint, json=body).json()['id'] == event['id']
    changed = {**body, 'revision_assessment': {**body['revision_assessment'], 'review_seconds': 91}}
    assert client.post(endpoint, json=changed).status_code == 409
    listed = client.get(base + '/analyses').json()[0]
    assert listed['review']['effective_state'] == 'reviewed_conditional'
    assert listed['checks']['legal_approval'] == 'not_granted'
    history = client.get(base + '/analyses/' + original['id'] + '/versions').json()
    assert history[1]['review']['latest']['findings'] == previous_review['findings']
    export = client.get(base + '/analyses/' + original['id'] + '/export')
    assert export.status_code == 200
    text = '\n'.join(item.text for item in Document(io.BytesIO(export.content)).paragraphs)
    for value in ('Kaynak bağlı sürüm değerlendirmesi', 'zaman kazanımı ölçülmedi', '90',
                  comparison['comparison_sha256'], 'after:synthetic-clause',
                  previous_review['findings'][1]['text']):
        assert value in text
    with app.state.store.session() as session:
        assert all(session.get(Record, ident).payload == encrypted for ident, encrypted in frozen.items())
        assert 'SYNTHETIC — Değişen' not in session.get(Record, event['id']).payload


@pytest.mark.parametrize('mutation', [
    'hash', 'missing_finding', 'invented_finding', 'boolean_index', 'duplicate_finding', 'missing_dimension',
    'duplicate_dimension', 'invented_target', 'invented_source', 'repeated_source', 'no_source', 'before_only',
    'unchanged_repair', 'false_withheld', 'unresolved_major', 'semantic_defect', 'unassessed_repair', 'unlinked_semantics',
    'split_semantics', 'time_bool', 'time_overflow', 'extra',
])
def test_invalid_or_unresolved_comparison_cannot_be_accepted(workbench, mutation):
    _, client, base, *_ = workbench
    _, revised, endpoint, _ = pair(workbench)
    body, _ = assessment_body(client, endpoint, revised)
    assessment = body['revision_assessment']
    finding = assessment['finding_dispositions'][0]
    observation = assessment['observations'][0]
    if mutation == 'hash':
        assessment['comparison_sha256'] = '0' * 64
    elif mutation == 'missing_finding':
        assessment['finding_dispositions'].pop()
    elif mutation == 'invented_finding':
        finding['finding_index'] = 19
    elif mutation == 'boolean_index':
        finding['finding_index'] = False
    elif mutation == 'duplicate_finding':
        assessment['finding_dispositions'][1]['finding_index'] = 0
    elif mutation == 'missing_dimension':
        assessment['observations'].pop()
    elif mutation == 'duplicate_dimension':
        observation['dimension'] = 'certainty'
    elif mutation == 'invented_target':
        observation['target_ids'] = ['conclusion:foreign']
    elif mutation == 'invented_source':
        observation['source_refs'] = ['after:foreign']
    elif mutation == 'repeated_source':
        observation['source_refs'] *= 2
    elif mutation == 'no_source':
        observation['source_refs'] = []
    elif mutation == 'before_only':
        observation['source_refs'] = ['before:synthetic-clause']
    elif mutation == 'unchanged_repair':
        finding['target_ids'] = ['premise:p1']
    elif mutation == 'false_withheld':
        finding['outcome'] = 'withheld'
    elif mutation == 'unresolved_major':
        finding['outcome'] = 'unresolved'
    elif mutation == 'semantic_defect':
        observation['outcome'] = 'needs_change'
    elif mutation == 'unassessed_repair':
        observation['outcome'] = 'not_assessed'
    elif mutation == 'unlinked_semantics':
        observation['target_ids'] = ['premise:p1']
    elif mutation == 'split_semantics':
        finding['target_ids'] = ['application:a1', 'conclusion']
        observation['target_ids'] = ['application:a1']
        assessment['observations'][5]['target_ids'] = ['conclusion']
    elif mutation == 'time_bool':
        assessment['review_seconds'] = True
    elif mutation == 'time_overflow':
        assessment['review_seconds'] = 28801
    elif mutation == 'extra':
        assessment['public_adverse_authority_qualified'] = True
    result = client.post(endpoint, json=body)
    assert result.status_code in {409, 422}, result.text
    assert client.get(base + '/analyses').json()[0]['review']['effective_state'] == 'unreviewed'


def test_unchanged_version_cannot_claim_repair_but_can_record_unresolved_findings(workbench):
    _, client, base, *_ = workbench
    _, revised, endpoint, _ = pair(workbench, unchanged=True)
    body, comparison = assessment_body(client, endpoint, revised)
    assert comparison['changes'] == []
    assert client.post(endpoint, json=body).status_code == 422
    body['decision'] = 'changes_requested'
    body['findings'] = [{'target_id': 'conclusion', 'severity': 'major', 'text': 'SYNTHETIC still unresolved'}]
    for finding in body['revision_assessment']['finding_dispositions']:
        finding.update(outcome='unresolved', source_refs=[])
    body['revision_assessment']['review_seconds'] = None
    result = client.post(endpoint, json=body)
    assert result.status_code == 201, result.text
    assert client.get(base + '/analyses').json()[0]['review']['effective_state'] == 'changes_requested'


def test_withholding_requires_actual_withheld_candidate_not_just_a_review_label(workbench):
    _, client, base, payload, *_ = workbench
    original, endpoint = prepare(workbench)
    body, _ = review_request(client, endpoint, original, decision='changes_requested')
    assert client.post(endpoint, json=body).status_code == 201
    changed = copy.deepcopy(payload)
    changed['conclusion']['requested_disposition'] = 'withheld'
    revised = client.post(base + '/analyses/' + original['id'] + '/versions', json={
        **changed, 'expected_revision': original['revision'], 'change_note': 'SYNTHETIC explicitly withheld'}).json()
    body, _ = assessment_body(client, endpoint, revised)
    body['revision_assessment']['finding_dispositions'][0]['outcome'] = 'withheld'
    assert client.post(endpoint, json=body).status_code == 201
    assert client.get(base + '/analyses').json()[0]['checks']['effective_disposition'] == 'withheld'


def test_initial_and_unreviewed_predecessor_comparisons_are_explicit(workbench):
    _, client, _, *_ = workbench
    original, endpoint = prepare(workbench)
    _, context = review_request(client, endpoint, original)
    assert context['revision_comparison'] is None
    body, _ = review_request(client, endpoint, original)
    body['revision_assessment'] = {'comparison_sha256': 'a' * 64, 'observations': [
        {'dimension': key, 'outcome': 'not_assessed', 'note': 'SYNTHETIC no predecessor', 'target_ids': ['conclusion']}
        for key in adjudication.DIMENSIONS]}
    assert client.post(endpoint, json=body).status_code == 409
    _, revised, endpoint, _ = pair(workbench, reviewed=False)
    body, comparison = assessment_body(client, endpoint, revised)
    assert comparison['base_review_id'] is None and not comparison['findings']
    assert client.post(endpoint, json=body).status_code == 201


@pytest.mark.parametrize('dependency', ['fact', 'document', 'comparison_recipe', 'review_recipe', 'base_review'])
def test_dependency_changes_stale_projection_preserve_declarations_and_block_new_assessment(workbench, monkeypatch, dependency):
    from app import analysis_reviews

    app, client, base, _, fact, document, *_ = workbench
    _, revised, endpoint, previous_review = pair(workbench)
    body, _ = assessment_body(client, endpoint, revised)
    event = client.post(endpoint, json=body).json()
    with app.state.store.session() as session:
        frozen = session.get(Record, event['id']).payload
    if dependency == 'fact':
        assert client.patch(base + '/facts/' + fact['id'], json={
            'text': 'SYNTHETIC changed fact', 'status': 'alleged', 'reason': 'SYNTHETIC corrected role'}).status_code == 200
    elif dependency in {'document', 'base_review'}:
        # Simulate out-of-band substitution, not an authorized API mutation.
        with app.state.store.session() as session:
            row = session.get(Record, document if dependency == 'document' else previous_review['id'])
            data = app.state.store.decode(row)
            if dependency == 'document':
                data['passages'][0]['text'] += ' SYNTHETIC changed bytes'
            else:
                data['findings'][0]['text'] += ' SYNTHETIC substituted finding'
            app.state.store.update(row, data)
            session.commit()
    elif dependency == 'comparison_recipe':
        monkeypatch.setattr(adjudication, 'RECIPE', 'SYNTHETIC new comparison recipe')
    else:
        monkeypatch.setattr(analysis_reviews, 'RECIPE', 'SYNTHETIC new human-review recipe')
    record = client.get(base + '/analyses').json()[0]
    assert record['status'] == 'stale' and record['review']['effective_state'] == 'stale'
    body['request_id'] = uuid4().hex
    body['expected_review_id'] = event['id']
    body['decision'] = 'changes_requested'
    body['findings'] = [{'target_id': 'conclusion', 'severity': 'major', 'text': 'SYNTHETIC stale comparison'}]
    assert client.post(endpoint, json=body).status_code == 409
    with app.state.store.session() as session:
        assert session.get(Record, event['id']).payload == frozen


def test_changed_comparison_during_export_rejects_response(workbench, monkeypatch):
    _, client, base, *_ = workbench
    _, revised, endpoint, _ = pair(workbench)
    body, _ = assessment_body(client, endpoint, revised)
    assert client.post(endpoint, json=body).status_code == 201
    original_render = analysis_workbench.render_export

    def render(*args, **kwargs):
        result = original_render(*args, **kwargs)
        monkeypatch.setattr(adjudication, 'RECIPE', 'SYNTHETIC changed comparison policy')
        return result

    monkeypatch.setattr(analysis_workbench, 'render_export', render)
    assert client.get(base + '/analyses/' + revised['id'] + '/export').status_code == 409


def test_predecessor_only_source_changes_stale_assessment_even_when_candidate_is_current(workbench):
    app, client, base, *_ = workbench
    revised, endpoint, extra_id = predecessor_only_pair(workbench)
    body, _ = assessment_body(client, endpoint, revised)
    event = client.post(endpoint, json=body).json()
    with app.state.store.session() as session:
        row = session.get(Record, extra_id)
        data = app.state.store.decode(row)
        data['passages'][0]['text'] += ' SYNTHETIC new representation'
        app.state.store.update(row, data)
        session.commit()
    _, context = review_request(client, endpoint, revised)
    assert context['freshness']['status'] == 'current'
    assert context['revision_comparison']['freshness']['status'] == 'stale'
    assert context['review']['effective_state'] == 'stale'
    assert context['review']['latest']['id'] == event['id']
    body['request_id'] = uuid4().hex
    body['expected_review_id'] = event['id']
    assert client.post(endpoint, json=body).status_code == 409


def test_substituted_stored_comparison_cannot_remain_effectively_reviewed(workbench):
    app, client, base, *_ = workbench
    _, revised, endpoint, _ = pair(workbench)
    body, _ = assessment_body(client, endpoint, revised)
    event = client.post(endpoint, json=body).json()
    with app.state.store.session() as session:
        row = session.get(Record, event['id'])
        data = app.state.store.decode(row)
        data['revision_comparison_snapshot']['sources'][0]['text'] = 'SYNTHETIC substituted quote'
        app.state.store.update(row, data)
        session.commit()
    current = client.get(base + '/analyses').json()[0]
    assert current['status'] == 'stale' and current['review']['effective_state'] == 'stale'


def test_change_after_validation_rolls_back_review_head_audit_and_invalidation(workbench, monkeypatch):
    from app import analysis_reviews

    app, client, base, *_ = workbench
    revised, endpoint, document = predecessor_only_pair(workbench)
    body, _ = assessment_body(client, endpoint, revised)
    invalidate = analysis_reviews._invalidate

    def change(store, session, *args):
        invalidate(store, session, *args)
        # Inject a post-validation representation change in the active transaction.
        # This tests the final guard/rollback; real lock contention is tested separately.
        row = session.get(Record, document)
        data = store.decode(row)
        data['passages'][0]['text'] += ' SYNTHETIC after validation'
        store.update(row, data)

    monkeypatch.setattr(analysis_reviews, '_invalidate', change)
    with app.state.store.session() as session:
        frozen = {ident: session.get(Record, ident).payload for ident in (document, base.rsplit('/', 1)[1])}
    result = client.post(endpoint, json=body)
    assert result.status_code == 409 and 'Kayıt sırasında' in result.text
    assert client.get(endpoint, params={'version_id': revised['latest_version_id']}).json() == []
    assert client.get(base + '/analyses').json()[0]['review']['effective_state'] == 'unreviewed'
    with app.state.store.session() as session:
        assert all(session.get(Record, ident).payload == encrypted for ident, encrypted in frozen.items())


def test_legacy_receipts_remain_identical_and_new_versions_do_not_inherit_assessments(workbench):
    _, client, base, payload, *_ = workbench
    _, revised, endpoint, _ = pair(workbench)
    legacy, _ = review_request(client, endpoint, revised)
    value = ReviewInput.model_validate(legacy)
    old_value = value.model_dump(exclude={'request_id', 'revision_assessment'})
    assert _input_value(value, {'request_id'}) == old_value
    # An absent optional field must not consume the old receipt's byte allowance.
    maximum = {**_input_value(value, set()), 'decision': 'changes_requested', 'findings': [
        {'target_id': 'conclusion', 'severity': 'major', 'text': 'S' * 2000,
         'suggested_change': 'S' * 2000, 'evidence_ids': []} for _ in range(20)]}
    remaining = 100000 - len(canonical(maximum).encode())
    assert remaining > 0
    for finding in maximum['findings']:
        added_bytes = min(remaining, 2000)
        finding['text'] = 'ş' * added_bytes + 'S' * (2000 - added_bytes)
        remaining -= added_bytes
    assert remaining == 0 and len(canonical(maximum).encode()) == 100000
    assert len(ReviewInput.model_validate(maximum).findings) == 20
    assert len(ReviewInput.model_validate({**maximum, 'revision_assessment': None}).findings) == 20
    maximum['findings'][0]['suggested_change'] = 'ş' + 'S' * 1999
    with pytest.raises(ValueError, match='Review input exceeds its byte budget'):
        ReviewInput.model_validate(maximum)
    event = client.post(endpoint, json=legacy).json()
    assert event['request_sha256'] == digest(canonical(old_value))
    assert 'revision_assessment' not in event
    assert client.post(endpoint, json={**legacy, 'revision_assessment': None}).json()['id'] == event['id']
    body, _ = assessment_body(client, endpoint, revised)
    assert client.post(endpoint, json=body).status_code == 201
    next_version = client.post(base + '/analyses/' + revised['id'] + '/versions', json={
        **payload, 'expected_revision': revised['revision'], 'change_note': 'SYNTHETIC next manual version'}).json()
    assert next_version['review']['effective_state'] == 'unreviewed'
    history = client.get(base + '/analyses/' + revised['id'] + '/versions').json()
    assert history[1]['review']['latest']['revision_assessment']['review_seconds'] == 90


def test_comparison_sources_are_authorized_before_join_and_post(workbench):
    app, client, base, *_ = workbench
    _, revised, endpoint, _ = pair(workbench)
    body, _ = assessment_body(client, endpoint, revised)
    other = client.post('/api/v1/matters', json={'title': 'SYNTHETIC other', 'domain': 'contracts'}).json()['id']
    foreign = f'/api/v1/matters/{other}/analyses/{revised["id"]}/reviews'
    assert client.get(foreign + '/context', params={'version_id': revised['latest_version_id']}).status_code == 404
    assert client.post(foreign, json=body).status_code == 404
    with app.state.store.session() as session:
        owner = session.scalar(select(User).where(User.username == 'demo'))
        session.delete(session.get(Membership, (base.rsplit('/', 1)[1], owner.id)))
        session.commit()
    assert client.get(endpoint + '/context', params={'version_id': revised['latest_version_id']}).status_code == 404
    assert client.post(endpoint, json=body).status_code == 404


@pytest.mark.parametrize('completed', [False, True])
def test_adjudication_recipe_changes_invalidate_generic_proposals_without_sending_review_prose(workbench, monkeypatch, completed):
    from test_analysis_suggestions import adopt, finished, patch, start

    from app.analysis_proposals import proposal_messages

    app, client, base, *_ = workbench
    _, revised, reviews, _ = pair(workbench)
    body, _ = assessment_body(client, reviews, revised)
    assert client.post(reviews, json=body).status_code == 201
    settings = app.state.settings
    settings.provider_base_url = 'https://10.20.0.8/v1'
    settings.provider_api_key = 'SYNTHETIC-NOT-A-REAL-KEY'
    settings.provider_model = 'SYNTHETIC-local-model'
    settings.provider_context_limit = 32768
    settings.provider_identity_verified = True
    settings.provider_cloud_fallback_disabled = True
    monkeypatch.setattr(app.state.provider, 'probe', lambda: {'ready': True})
    entered, release = Event(), Event()
    calls = []

    def suggest(content, **_kwargs):
        prompt = canonical(proposal_messages(content))
        assert 'revision_assessment' not in prompt and 'review_seconds' not in prompt
        assert body['revision_assessment']['observations'][0]['note'] not in prompt
        calls.append(prompt)
        entered.set()
        if not completed:
            assert release.wait(5)
        return json.dumps(patch())

    monkeypatch.setattr(app.state.provider, 'suggest_analysis', suggest)
    endpoint = base + '/analyses/' + revised['id'] + '/suggestions'
    try:
        queued, _ = start(client, endpoint, revised)
        assert entered.wait(5)
        if completed:
            result = finished(client, endpoint, queued['id'])
            assert result['can_adopt']
        monkeypatch.setattr(adjudication, 'RECIPE', 'SYNTHETIC newer comparison policy')
    finally:
        release.set()
    result = finished(client, endpoint, queued['id'])
    assert result['status'] == ('completed' if completed else 'failed')
    assert result['freshness']['status'] == 'stale' and not result['can_adopt']
    assert 'sürüm değerlendirmesi' in result['freshness']['reasons'][0]
    if completed:
        assert adopt(client, endpoint, revised, result).status_code == 409
    response = client.post(endpoint, json={'expected_revision': revised['revision'],
                           'version_id': revised['latest_version_id'], 'request_id': uuid4().hex})
    assert response.status_code == 409 and len(calls) == 1
