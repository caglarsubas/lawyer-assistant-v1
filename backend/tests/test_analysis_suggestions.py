"""Invented private evidence and event-controlled local-model proposals only."""

import copy
import io
import json
import time
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import uuid4

import httpx
import pytest
from docx import Document
from sqlalchemy import func, select
from test_analysis_workbench import workbench as workbench_fixture

from app.analysis_proposals import apply_patch, parse_patch, prompt_measurement, proposal_messages
from app.db import Membership, Record
from app.provider import ProviderError


@pytest.fixture
def workbench(tmp_path):
    yield from workbench_fixture.__wrapped__(tmp_path)


def prepare(workbench, monkeypatch, *, incomplete=True):
    app, client, base, payload, *_ = workbench
    body = copy.deepcopy(payload)
    if incomplete:
        body['applications'][0]['assessments'].pop()
    record = client.post(base + '/analyses', json=body).json()
    settings = app.state.settings
    settings.provider_base_url = 'https://10.20.0.8/v1'
    settings.provider_api_key = 'SYNTHETIC-NOT-A-REAL-KEY'
    settings.provider_model = 'SYNTHETIC-local-model'
    settings.provider_context_limit = 32768
    settings.provider_identity_verified = True
    settings.provider_cloud_fallback_disabled = True
    monkeypatch.setattr(app.state.provider, 'probe', lambda: {'ready': True})
    return record, base + '/analyses/' + record['id'] + '/suggestions'


def patch():
    return {'application_updates': [{'id': 'a1', 'rationale': 'SYNTHETIC — Koşul ve istisna avukat tarafından ayrıca incelenmeli.',
                                    'assessments': [{'condition_id': 'c2', 'status': 'not_met', 'premise_ids': ['p1']}]}],
            'conclusion_update': {'text': 'SYNTHETIC — Talep ek incelemeye bağlıdır.', 'uncertainty': ['Özel belge yorumu doğrulanmadı.'],
                                  'next_step': 'Özgün belgeyi ve karşı kaynakları inceleyin.'},
            'review_notes': [{'target_id': 'a1', 'text': 'Bu öneri hukuki inceleme değildir.', 'evidence_ids': ['synthetic-clause']}]}


def start(client, endpoint, record, *, mode='single', request_id=None):
    body = {'expected_revision': record['revision'], 'version_id': record['latest_version_id'],
            'request_id': request_id or uuid4().hex, 'mode': mode}
    response = client.post(endpoint, json=body)
    assert response.status_code == 202, response.text
    return response.json(), body


def finished(client, endpoint, ident):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(endpoint + '/' + ident)
        assert response.status_code == 200, response.text
        data = response.json()
        if data['status'] not in {'queued', 'running', 'cancelling'}:
            return data
        time.sleep(.01)
    pytest.fail('Synthetic proposal did not finish')


def adopt(client, endpoint, record, job):
    return client.post(endpoint + '/' + job['id'] + '/adopt', json={
        'expected_revision': record['revision'], 'candidate_sha256': job['candidate_sha256'],
        'change_note': 'SYNTHETIC — Model önerisi yeni taslak için incelendi.',
    })


def test_proposal_is_separate_and_adoption_preserves_inputs_provenance_and_history(workbench, monkeypatch):
    app, client, base, _, *_ = workbench
    record, endpoint = prepare(workbench, monkeypatch)
    calls = []

    def suggest(content, **options):
        calls.append((content, options))
        return json.dumps(patch(), ensure_ascii=False)

    monkeypatch.setattr(app.state.provider, 'suggest_analysis', suggest)
    monkeypatch.setattr(app.state.provider, 'generate', lambda *_: pytest.fail('Quotation provider not used'))
    monkeypatch.setattr(app.state.graph, 'tool', lambda *_: pytest.fail('No graph authority search'))
    queued, request = start(client, endpoint, record, mode='repair')
    job = finished(client, endpoint, queued['id'])
    assert job['status'] == 'completed' and job['can_adopt']
    assert job['candidate']['authorship'] == 'model_proposal' and job['candidate']['authored_by'] is None
    assert len(calls) == 1 and len(job['iterations']) == 1
    assert job['candidate']['checks']['effective_disposition'] == 'conditional'
    assert job['candidate']['checks']['legal_approval'] == 'not_granted'
    current = client.get(base + '/analyses').json()[0]
    assert current['version'] == 1 and current['checks']['effective_disposition'] == 'withheld'
    assert client.get(base).json()['research_runs'] == []
    assert client.get('/api/v1/workspaces/' + base.rsplit('/', 1)[1]).json()['research_runs'] == []
    for key in ('premises', 'rules', 'evidence', 'fact_snapshots', 'source_snapshots', 'alternatives', 'issue', 'event_date'):
        assert job['candidate'][key] == record[key]
    assert record['conclusion']['uncertainty'][0] in job['candidate']['conclusion']['uncertainty']
    response = adopt(client, endpoint, record, job)
    assert response.status_code == 201, response.text
    adopted = response.json()
    assert adopted['authorship'] == 'user_with_ai_assistance' and adopted['status'] == 'needs_review'
    assert adopted['ai_assistance']['job_id'] == job['id']
    assert adopted['ai_assistance']['provider']['model'] == 'SYNTHETIC-local-model'
    assert adopted['ai_assistance']['review_notes'] == job['review_notes']
    assert 'SYNTHETIC-NOT-A-REAL-KEY' not in json.dumps(adopted)
    history = client.get(base + '/analyses/' + record['id'] + '/versions').json()
    assert [item['version'] for item in history] == [2, 1]
    assert history[1]['content']['checks'] == record['checks']
    assert adopt(client, endpoint, record, job).status_code == 409
    replay = client.post(endpoint, json=request)
    assert replay.status_code == 202 and replay.json()['id'] == job['id']
    assert replay.json()['adopted_version_id'] == adopted['latest_version_id']
    assert len(calls) == 1
    export = client.get(base + '/analyses/' + record['id'] + '/export')
    text = '\n'.join(item.text for item in Document(io.BytesIO(export.content)).paragraphs)
    assert 'MODEL ÖNERİSİNDEN UYARLANMIŞ' in text and 'Model katkısı' in text
    assert 'Hukuki onay verilmedi' in text and 'SYNTHETIC-local-model' in text
    assert 'doğrulanmamış inceleme notu' in text and patch()['review_notes'][0]['text'] in text


def test_one_additional_pass_rechecks_structural_defects_and_keeps_frozen_inputs(workbench, monkeypatch):
    app, client, *_ = workbench
    record, endpoint = prepare(workbench, monkeypatch)
    seen = []

    def suggest(content, **options):
        seen.append((content, options))
        if not options['repair']:
            return json.dumps({'application_updates': [{'id': 'a1', 'rationale': 'SYNTHETIC first proposal'}]})
        return json.dumps(patch())

    monkeypatch.setattr(app.state.provider, 'suggest_analysis', suggest)
    queued, _ = start(client, endpoint, record, mode='repair')
    job = finished(client, endpoint, queued['id'])
    assert job['status'] == 'completed' and len(job['iterations']) == 2
    assert [item[1]['repair'] for item in seen] == [False, True]
    assert all(0 < item[1]['budget_seconds'] <= 120 for item in seen)
    assert seen[1][0]['applications'][0]['rationale'] == 'SYNTHETIC first proposal'
    assert seen[1][0]['rules'] == record['rules']
    assert job['candidate']['checks']['critical_count'] == 0
    assert all('provider_seconds' in item for item in job['iterations'])


def test_new_critical_defect_is_rejected_and_cannot_be_adopted_as_a_change(workbench, monkeypatch):
    app, client, *_ = workbench
    record, endpoint = prepare(workbench, monkeypatch, incomplete=False)
    output = patch()
    output['application_updates'][0]['assessments'][0]['status'] = 'met'
    monkeypatch.setattr(app.state.provider, 'suggest_analysis', lambda *_a, **_k: json.dumps(output))
    queued, _ = start(client, endpoint, record)
    job = finished(client, endpoint, queued['id'])
    assert job['status'] == 'completed' and not job['can_adopt']
    assert job['iterations'][0]['outcome'] == 'rejected_new_critical_checks'
    assert job['candidate']['applications'] == record['applications']
    assert job['candidate']['revision_comparison']['changed_sections'] == []
    assert adopt(client, endpoint, record, job).status_code == 409


@pytest.mark.parametrize('mutation', ['rules', 'facts', 'unknown_application', 'foreign_condition', 'foreign_premise',
                                     'duplicate_application', 'duplicate_assessment', 'invented_evidence', 'duplicate_json', 'oversize'])
def test_untrusted_output_cannot_escape_the_pinned_draft(workbench, monkeypatch, mutation):
    app, client, base, *_ = workbench
    record, endpoint = prepare(workbench, monkeypatch)
    output = patch()
    if mutation == 'rules':
        output['rules'] = []
    elif mutation == 'facts':
        output['premises'] = [{'id': 'p1', 'role': 'established_fact'}]
    elif mutation == 'unknown_application':
        output['application_updates'][0]['id'] = 'invented'
    elif mutation == 'foreign_condition':
        output['application_updates'][0]['assessments'][0]['condition_id'] = 'invented'
    elif mutation == 'foreign_premise':
        output['application_updates'][0]['assessments'][0]['premise_ids'] = ['invented']
    elif mutation == 'duplicate_application':
        output['application_updates'] *= 2
    elif mutation == 'duplicate_assessment':
        output['application_updates'][0]['assessments'] *= 2
    elif mutation == 'invented_evidence':
        output['review_notes'][0]['evidence_ids'] = ['invented']
    raw = json.dumps(output)
    if mutation == 'duplicate_json':
        raw = '{"application_updates":[],"application_updates":[]}'
    elif mutation == 'oversize':
        raw = 'x' * 32769
    monkeypatch.setattr(app.state.provider, 'suggest_analysis', lambda *_a, **_k: raw)
    queued, _ = start(client, endpoint, record)
    job = finished(client, endpoint, queued['id'])
    assert job['status'] == 'failed' and not job['can_adopt']
    assert 'candidate' not in job
    assert len(client.get(base + '/analyses/' + record['id'] + '/versions').json()) == 1
    assert client.get(base).json()['products'] == []


def test_request_receipt_replays_without_inference_and_rejects_changed_payload(workbench, monkeypatch):
    app, client, *_ = workbench
    record, endpoint = prepare(workbench, monkeypatch)
    entered, release = Event(), Event()
    calls = []

    def suggest(*_a, **_k):
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return json.dumps(patch())

    monkeypatch.setattr(app.state.provider, 'suggest_analysis', suggest)
    try:
        queued, request = start(client, endpoint, record)
        assert entered.wait(5)
        replay = client.post(endpoint, json=request)
        assert replay.status_code == 202 and replay.json()['id'] == queued['id']
        assert client.post(endpoint, json={**request, 'mode': 'repair'}).status_code == 409
        assert len(calls) == 1
    finally:
        release.set()
    assert finished(client, endpoint, queued['id'])['status'] == 'completed'


@pytest.mark.parametrize('change', ['cancel', 'fact', 'analysis', 'provider', 'deadline', 'membership'])
def test_inflight_changes_prevent_publication_and_adoption(workbench, monkeypatch, change):
    app, client, base, payload, fact, *_ = workbench
    record, endpoint = prepare(workbench, monkeypatch)
    entered, release = Event(), Event()

    def suggest(*_a, **_k):
        entered.set()
        assert release.wait(5)
        return json.dumps(patch())

    monkeypatch.setattr(app.state.provider, 'suggest_analysis', suggest)
    try:
        queued, _ = start(client, endpoint, record, mode='repair')
        assert entered.wait(5)
        if change == 'cancel':
            response = client.post(endpoint + '/' + queued['id'] + '/cancel')
            assert response.status_code == 200 and response.json()['status'] == 'cancelling'
            assert queued['id'] in app.state.research_jobs._jobs
        elif change == 'fact':
            assert client.patch(base + '/facts/' + fact['id'], json={'text': 'SYNTHETIC changed fact', 'status': 'disputed', 'reason': 'SYNTHETIC correction'}).status_code == 200
        elif change == 'analysis':
            assert client.post(base + '/analyses/' + record['id'] + '/versions', json={**payload, 'expected_revision': record['revision'], 'change_note': 'SYNTHETIC competing edit'}).status_code == 201
        elif change == 'provider':
            app.state.settings.provider_model = 'SYNTHETIC-changed-model'
        else:
            with app.state.store.session() as session:
                row = session.get(Record, queued['id'])
                if change == 'deadline':
                    state = app.state.store.decode(row)
                    state['deadline_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
                    app.state.store.update(row, state)
                else:
                    session.delete(session.get(Membership, (base.rsplit('/', 1)[1], row.owner_id)))
                session.commit()
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while queued['id'] in app.state.research_jobs._jobs and time.monotonic() < deadline:
        time.sleep(.01)
    with app.state.store.session() as session:
        state = app.state.store.decode(session.get(Record, queued['id']))
    assert state['status'] == ('cancelled' if change == 'cancel' else 'timed_out' if change == 'deadline' else 'failed')
    assert 'candidate' not in state
    assert state['status'] != 'completed'
    if change == 'membership':
        assert client.get(endpoint + '/' + queued['id']).status_code == 404


def test_completed_proposal_becomes_stale_without_rewriting_and_manual_revision_keeps_ai_lineage(workbench, monkeypatch):
    app, client, base, payload, fact, *_ = workbench
    record, endpoint = prepare(workbench, monkeypatch)
    monkeypatch.setattr(app.state.provider, 'suggest_analysis', lambda *_a, **_k: json.dumps(patch()))
    queued, _ = start(client, endpoint, record)
    job = finished(client, endpoint, queued['id'])
    with app.state.store.session() as session:
        encrypted = session.get(Record, job['id']).payload
    response = adopt(client, endpoint, record, job)
    adopted = response.json()
    updated = client.post(base + '/analyses/' + record['id'] + '/versions', json={
        **payload, 'expected_revision': adopted['revision'], 'change_note': 'SYNTHETIC explicit manual rewrite',
    }).json()
    assert updated['authorship'] == 'user_with_ai_assistance'
    assert updated['ai_assistance'] == adopted['ai_assistance']
    # A separate, unadopted receipt becomes stale after its source changes.
    next_job, _ = start(client, endpoint, updated)
    completed = finished(client, endpoint, next_job['id'])
    with app.state.store.session() as session:
        encrypted = session.get(Record, completed['id']).payload
    assert client.patch(base + '/facts/' + fact['id'], json={'text': 'SYNTHETIC stale source', 'status': 'disputed', 'reason': 'SYNTHETIC correction'}).status_code == 200
    stale = client.get(endpoint + '/' + completed['id']).json()
    assert stale['status'] == 'completed' and stale['freshness']['status'] == 'stale' and not stale['can_adopt']
    assert stale['candidate'] == completed['candidate']
    with app.state.store.session() as session:
        assert session.get(Record, completed['id']).payload == encrypted
    assert adopt(client, endpoint, updated, completed).status_code == 409


def test_provider_admission_and_scoped_history_remain_private(workbench, monkeypatch):
    app, client, base, *_ = workbench
    record, endpoint = prepare(workbench, monkeypatch)
    request = {'expected_revision': record['revision'], 'version_id': record['latest_version_id'], 'request_id': uuid4().hex}
    app.state.settings.provider_identity_verified = False
    assert client.post(endpoint, json=request).status_code == 503
    assert client.get(endpoint).json() == []
    app.state.settings.provider_identity_verified = True
    monkeypatch.setattr(app.state.provider, 'suggest_analysis', lambda *_a, **_k: json.dumps(patch()))
    queued, _ = start(client, endpoint, record)
    job = finished(client, endpoint, queued['id'])
    assert client.get(endpoint).json()[0]['id'] == job['id']
    assert client.get(endpoint + '?limit=21').status_code == 422
    other = client.post('/api/v1/matters', json={'title': 'Other SYNTHETIC', 'domain': 'contracts'}).json()['id']
    foreign = f'/api/v1/matters/{other}/analyses/{record["id"]}/suggestions'
    assert client.get(foreign).status_code == 404
    assert client.get(foreign + '/' + job['id']).status_code == 404
    assert client.post(foreign + '/' + job['id'] + '/cancel').status_code == 404
    with app.state.store.session() as session:
        assert session.scalar(select(func.count()).select_from(Record).where(Record.kind == 'analysis_suggestion_receipt')) == 1
        assert 'SYNTHETIC — Talep' not in session.get(Record, job['id']).payload


def test_prompt_is_minimal_accounted_and_does_not_promote_ledger_roles(workbench, monkeypatch):
    app, client, base, payload, fact, *_ = workbench
    record, _ = prepare(workbench, monkeypatch)
    changed = client.patch(base + '/facts/' + fact['id'], json={'text': 'SYNTHETIC party allegation', 'status': 'alleged', 'reason': 'SYNTHETIC role'}).json()
    body = copy.deepcopy(payload)
    body['premises'][0]['fact_revision'] = changed['revision']
    record = client.post(base + '/analyses', json=body).json()
    messages = proposal_messages(record)
    data = json.loads(messages[1]['content'])
    assert data['facts'][0]['status'] == 'alleged'
    assert data['evidence'][0]['text'] == record['evidence'][0]['text']
    for text in (record['evidence'][0]['name'], record['id'], 'org-lawyer', 'SYNTHETIC-NOT-A-REAL-KEY'):
        assert text not in json.dumps(messages, ensure_ascii=False)
    measured = prompt_measurement(messages)
    assert measured['utf8_bytes'] == len(json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())
    assert measured['completion_tokens'] == 1000
    patched = apply_patch(record, parse_patch(json.dumps(patch())))
    assert patched.premises[0].text == ''


def test_provider_sends_exact_measured_envelope_accepted_by_existing_relay(workbench, monkeypatch):
    from test_provider_runtime import relay

    app, *_ = workbench
    record, _ = prepare(workbench, monkeypatch)
    seen = []
    client_type = httpx.Client

    def serve(request):
        seen.append(request)
        return httpx.Response(200, json={'model': 'SYNTHETIC-local-model', 'choices': [
            {'finish_reason': 'stop', 'message': {'content': json.dumps(patch())}}]})

    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: client_type(transport=httpx.MockTransport(serve), **kwargs))
    assert parse_patch(app.state.provider.suggest_analysis(record, budget_seconds=10)).application_updates
    assert len(seen) == 1 and seen[0].url.path == '/v1/chat/completions'
    body = json.loads(seen[0].content)
    assert relay.valid_completion(body, 'SYNTHETIC-local-model')
    assert body['messages'] == proposal_messages(record)
    assert prompt_measurement(body['messages']) == prompt_measurement(proposal_messages(record))
    assert body['max_completion_tokens'] == 1000 and body['temperature'] == 0
    assert seen[0].headers['x-engine-model-substitution'] == 'off'


@pytest.mark.parametrize('boundary', ['context', 'identity', 'fallback', 'budget'])
def test_proposal_provider_fails_before_transport_at_invalid_boundary(workbench, monkeypatch, boundary):
    app, *_ = workbench
    record, _ = prepare(workbench, monkeypatch)
    if boundary == 'context':
        app.state.settings.provider_context_limit = prompt_measurement(proposal_messages(record))['total_upper_bound_units'] - 1
    elif boundary == 'identity':
        app.state.settings.provider_identity_verified = False
    elif boundary == 'fallback':
        app.state.settings.provider_cloud_fallback_disabled = False
    monkeypatch.setattr(httpx, 'Client', lambda **_kwargs: pytest.fail('No HTTP before valid admission'))
    with pytest.raises(ProviderError):
        app.state.provider.suggest_analysis(record, budget_seconds=121 if boundary == 'budget' else 120)


def test_second_pass_cancellation_preserves_partial_candidate_without_allowing_adoption(workbench, monkeypatch):
    app, client, *_ = workbench
    record, endpoint = prepare(workbench, monkeypatch)
    entered, release = Event(), Event()

    def suggest(_content, *, repair, **_kwargs):
        if not repair:
            return json.dumps({'application_updates': [{'id': 'a1', 'rationale': 'SYNTHETIC partial'}]})
        entered.set()
        assert release.wait(5)
        return json.dumps(patch())

    monkeypatch.setattr(app.state.provider, 'suggest_analysis', suggest)
    try:
        queued, _ = start(client, endpoint, record, mode='repair')
        assert entered.wait(5)
        assert client.post(endpoint + '/' + queued['id'] + '/cancel').json()['status'] == 'cancelling'
    finally:
        release.set()
    job = finished(client, endpoint, queued['id'])
    assert job['status'] == 'cancelled' and len(job['iterations']) == 1 and not job['can_adopt']
    assert job['candidate']['applications'][0]['rationale'] == 'SYNTHETIC partial'
    assert adopt(client, endpoint, record, job).status_code == 409
