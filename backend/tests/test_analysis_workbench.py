"""Synthetic private documents; no provider calls, public authority or legal review."""

import copy
import io

import pytest
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import select

from app import analysis_workbench as analysis
from app.auth import hash_password
from app.config import Settings
from app.db import Membership, Record, User, digest
from app.main import create_app


@pytest.fixture
def workbench(tmp_path):
    app = create_app(Settings(
        _env_file=None, demo_mode=True, cookie_secure=False, data_dir=tmp_path,
        public_source_dir=tmp_path / 'public-sources', graph_url='', graph_release_dir='',
        opensearch_url='', gateway_enabled=False, gateway_url='', gateway_token='',
        encryption_key='', clamav_host='', extraction_url='', extraction_token='',
        LLM_PROVIDER_BASE_URL="", LLM_PROVIDER_API_KEY="", LLM_PROVIDER_MODEL="",
        LLM_PROVIDER_TUNNEL_URL='', LLM_PROVIDER_TUNNEL_APPROVED=False,
    ))
    with TestClient(app) as client:
        login = client.post('/api/v1/auth/login', json={'username': 'demo', 'password': 'demo-local-only'})
        assert login.status_code == 200
        client.headers['X-CSRF-Token'] = login.json()['csrf_token']
        matter = client.get('/api/v1/matters').json()[0]['id']
        base = f'/api/v1/matters/{matter}'
        with app.state.store.session() as session:
            user = session.scalar(select(User).where(User.username == 'demo'))
            text = '📄 Sözleşme örneği\r\nTeslim yapılmadıkça ödeme istenemez. İstisna: yazılı kabul.\r\n'
            doc = app.state.store.add(session, 'document', user, {
                'name': 'SYNTHETIC.docx', 'status': 'extracted', 'sha256': digest(text),
                'passages': [{'id': 'synthetic-clause', 'text': text, 'locator': 'SYNTHETIC §1'}],
            }, matter)
            session.commit()
        fact = client.post(base + '/facts', json={
            'text': 'Teslimin yapıldığına dair kayıt mevcut.', 'status': 'documented', 'evidence_id': 'synthetic-clause',
        }).json()
        payload = {
            'title': 'SYNTHETIC ödeme incelemesi', 'issue': 'Ödeme talebinin dayanakları nelerdir?',
            'posture': 'Sözleşme incelemesi', 'event_date': '2024-03-01',
            'evidence': [{'evidence_id': 'synthetic-clause', 'passage_sha256': digest(text), 'document_revision': doc.revision, 'start': 2, 'end': len(text)}],
            'premises': [{'id': 'p1', 'kind': 'fact', 'fact_id': fact['id'], 'fact_revision': fact['revision']}],
            'rules': [{'id': 'r1', 'kind': 'contract_clause', 'text': 'Ödeme, teslimin gerçekleşmesine bağlı olabilir.',
                       'evidence_ids': ['synthetic-clause'], 'conditions': [
                           {'id': 'c1', 'text': 'Teslimin gerçekleşmesi', 'kind': 'element', 'required_status': 'met'},
                           {'id': 'c2', 'text': 'Ayrı yazılı kabul istisnası', 'kind': 'exception', 'required_status': 'not_met'},
                       ]}],
            'applications': [{'id': 'a1', 'rule_id': 'r1', 'premise_ids': ['p1'],
                              'rationale': 'Belgedeki teslim koşulu ile olgu arasındaki ilişki ayrıca incelenmelidir.',
                              'assessments': [{'condition_id': 'c1', 'status': 'met', 'premise_ids': ['p1']},
                                              {'condition_id': 'c2', 'status': 'not_met', 'premise_ids': ['p1']}]}],
            'alternatives': [{'id': 'alt1', 'kind': 'search_gap', 'text': 'Karşı içtihat ve yazılı kabul araştırılmalı.'}],
            'conclusion': {'text': 'Ödeme talebi koşullu olarak değerlendirilebilir.', 'application_ids': ['a1'],
                           'alternative_ids': ['alt1'], 'uncertainty': ['Kabulün kapsamı bilinmiyor.'],
                           'next_step': 'Özgün kabul belgesini ve ilgili kamu otoritelerini inceleyin.'},
        }
        yield app, client, base, payload, fact, doc.id, text


def create(workbench, payload=None):
    _, client, base, original, *_ = workbench
    response = client.post(base + '/analyses', json=payload or original)
    assert response.status_code == 201, response.text
    return response.json()


def codes(body):
    return {item['code'] for item in body['checks']['defects']}


def test_preview_is_not_a_write_and_saved_quotes_are_exact_and_encrypted(workbench, monkeypatch):
    app, client, base, payload, fact, _, text = workbench
    monkeypatch.setattr(app.state.provider, 'generate', lambda *_: pytest.fail('No model in the workbench'))
    before = client.get(base).json()['facts']
    preview = client.post(base + '/analyses/check', json=payload)
    assert preview.status_code == 200, preview.text
    assert client.get(base + '/analyses').json() == []
    record = create(workbench)
    assert record['authorship'] == 'user' and record['legal_authority'] is False
    assert record['status'] == 'needs_review' and record['freshness']['status'] == 'current'
    assert record['checks']['legal_approval'] == 'not_granted'
    assert record['checks']['effective_disposition'] == 'conditional'
    assert record['checks']['critical_count'] == 0
    assert {'semantic_review_required', 'adverse_search_gap'} <= codes(record)
    evidence = record['evidence'][0]
    assert evidence['text'] == text[2:] and evidence['text'].endswith('\r\n')
    assert evidence['quote_sha256'] == digest(text[2:])
    assert evidence['passage_sha256'] == digest(text)
    assert record['fact_snapshots'][0]['status'] == 'documented'
    assert record['fact_snapshots'][0]['revision'] == fact['revision']
    assert client.get(base).json()['facts'] == before
    with app.state.store.session() as session:
        for key in (record['id'], record['latest_version_id']):
            assert text[2:] not in session.get(Record, key).payload


@pytest.mark.parametrize('status', ['alleged', 'disputed', 'assumption', 'inference'])
def test_ledger_roles_are_not_promoted(workbench, status):
    _, client, base, _, fact, *_ = workbench
    response = client.patch(base + '/facts/' + fact['id'], json={
        'text': fact['text'], 'status': status, 'evidence_id': fact['evidence_id'], 'reason': 'SYNTHETIC role test',
    })
    assert response.status_code == 200
    updated_payload = copy.deepcopy(workbench[3])
    updated_payload['premises'][0]['fact_revision'] = response.json()['revision']
    record = create(workbench, updated_payload)
    assert record['fact_snapshots'][0]['status'] == status
    assert 'unsettled_premise' in codes(record)
    assert record['checks']['effective_disposition'] == 'conditional'


@pytest.mark.parametrize('change,expected', [
    ('no_evidence', 'missing_rule_evidence'), ('no_conditions', 'missing_conditions'),
    ('unassessed', 'unassessed_condition'), ('no_premises', 'missing_premises'),
    ('unsupported_assessment', 'unsupported_assessment'), ('exception_conflict', 'condition_conflict'),
    ('legal_norm', 'unqualified_legal_norm'), ('no_application', 'missing_application'),
    ('no_alternative', 'missing_alternative'), ('unsupported_alternative', 'unsupported_alternative'),
])
def test_critical_structural_defects_withhold_dependent_conclusion(workbench, change, expected):
    payload = copy.deepcopy(workbench[3])
    payload['conclusion']['requested_disposition'] = 'supported_candidate'
    rule, app = payload['rules'][0], payload['applications'][0]
    if change == 'no_evidence':
        rule['evidence_ids'] = []
    elif change == 'no_conditions':
        rule['conditions'] = []
        app['assessments'] = []
    elif change == 'unassessed':
        app['assessments'].pop()
    elif change == 'no_premises':
        app['premise_ids'] = []
        for item in app['assessments']:
            item['premise_ids'] = []
    elif change == 'unsupported_assessment':
        app['assessments'][0]['premise_ids'] = []
    elif change == 'exception_conflict':
        app['assessments'][1]['status'] = 'met'
    elif change == 'legal_norm':
        rule['kind'] = 'legal_norm'
    elif change == 'no_application':
        payload['conclusion']['application_ids'] = []
    elif change == 'no_alternative':
        payload['conclusion']['alternative_ids'] = []
    elif change == 'unsupported_alternative':
        payload['alternatives'][0]['kind'] = 'adverse_argument'
    record = create(workbench, payload)
    assert expected in codes(record)
    assert record['checks']['effective_disposition'] == 'withheld'
    assert record['conclusion']['text'] == payload['conclusion']['text']
    assert record['status'] != 'reviewed'


def test_unknown_conditions_and_a_strong_request_never_gain_legal_approval(workbench):
    payload = copy.deepcopy(workbench[3])
    payload['applications'][0]['assessments'][0]['status'] = 'unknown'
    payload['conclusion']['requested_disposition'] = 'supported_candidate'
    record = create(workbench, payload)
    assert {'unknown_condition', 'strong_conclusion_unverified'} <= codes(record)
    assert record['checks']['effective_disposition'] == 'conditional'
    assert record['checks']['legal_approval'] == 'not_granted'


def test_unlinked_branch_is_reported_without_withholding_another_branch(workbench):
    payload = copy.deepcopy(workbench[3])
    payload['rules'].append({'id': 'unused_rule', 'kind': 'legal_norm', 'text': 'Unlinked rule candidate'})
    record = create(workbench, payload)
    assert 'unlinked_steps' in codes(record)
    assert 'unqualified_legal_norm' not in codes(record)
    assert record['checks']['effective_disposition'] == 'conditional'


def test_two_applications_of_one_rule_have_unambiguous_check_identifiers(workbench):
    payload = copy.deepcopy(workbench[3])
    second = copy.deepcopy(payload['applications'][0])
    second['id'] = 'a2'
    for item in second['assessments']:
        item['status'] = 'unknown'
    payload['applications'].append(second)
    payload['conclusion']['application_ids'].append('a2')
    record = create(workbench, payload)
    defects = record['checks']['defects']
    assert len({item['id'] for item in defects}) == len(defects)
    assert {item['target_id'] for item in defects if item['code'] == 'unknown_condition'} == {'a2:c1', 'a2:c2'}


@pytest.mark.parametrize('kind', ['total_quotes', 'nodes', 'input_bytes'])
def test_finite_input_budgets_reject_oversized_drafts(workbench, kind):
    _, client, base, original, *_ = workbench
    payload = copy.deepcopy(original)
    if kind == 'total_quotes':
        payload['evidence'].extend({'evidence_id': f'synthetic-{index}', 'passage_sha256': 'a' * 64, 'document_revision': 1, 'start': 0, 'end': 4000} for index in range(5))
    elif kind == 'nodes':
        payload['alternatives'].extend({'id': f'alt{index}', 'kind': 'search_gap', 'text': 'SYNTHETIC'} for index in range(2, 15))
    else:
        payload['premises'] = [{'id': f'p{index}', 'kind': 'assumption', 'text': 'a' * 4000} for index in range(1, 21)]
        payload['rules'][0]['text'] = 'b' * 4000
        payload['alternatives'] = [{'id': f'alt{index}', 'kind': 'search_gap', 'text': 'c' * 4000} for index in range(1, 13)]
    assert client.post(base + '/analyses', json=payload).status_code == 422
    assert client.get(base + '/analyses').json() == []


def test_ambiguous_passage_ids_fail_closed(workbench):
    app, client, base, _, _, document_id, _ = workbench
    with app.state.store.session() as session:
        document = session.get(Record, document_id)
        data = app.state.store.decode(document)
        data['passages'] *= 2
        app.state.store.update(document, data)
        session.commit()
    assert client.post(base + '/analyses', json=workbench[3]).status_code == 422
    assert client.get(base + '/analyses').json() == []


@pytest.mark.parametrize('change', ['fact_revision', 'passage_text', 'document_revision'])
def test_editor_pins_reject_changed_inputs_before_check_or_save(workbench, change):
    app, client, base, payload, fact, document_id, _ = workbench
    record = create(workbench)
    if change == 'fact_revision':
        response = client.patch(base + '/facts/' + fact['id'], json={
            'text': 'Yeni SYNTHETIC beyan', 'status': 'disputed', 'reason': 'SYNTHETIC concurrent edit',
        })
        assert response.status_code == 200
    else:
        with app.state.store.session() as session:
            row = session.get(Record, document_id)
            content = app.state.store.decode(row)
            if change == 'passage_text':
                content['passages'][0]['text'] = content['passages'][0]['text'].replace('yapılmadıkça', 'yapıldığında')
            else:
                content['name'] = 'SYNTHETIC-changed.docx'
            app.state.store.update(row, content)
            session.commit()
    assert client.post(base + '/analyses/check', json=payload).status_code == 409
    revised = {**payload, 'expected_revision': record['revision'], 'change_note': 'SYNTHETIC stale editor'}
    endpoint = base + '/analyses/' + record['id'] + '/versions'
    assert client.post(endpoint, json=revised).status_code == 409
    assert len(client.get(endpoint).json()) == 1


def test_refreshing_changed_facts_records_dependency_changes_without_rewriting_old_text(workbench):
    _, client, base, payload, fact, *_ = workbench
    original = create(workbench)
    changed = client.patch(base + '/facts/' + fact['id'], json={
        'text': 'Teslim reddediliyor.', 'status': 'disputed', 'reason': 'SYNTHETIC correction',
    }).json()
    refreshed = copy.deepcopy(payload)
    refreshed['premises'][0]['fact_revision'] = changed['revision']
    response = client.post(base + '/analyses/' + original['id'] + '/versions', json={
        **refreshed, 'expected_revision': original['revision'], 'change_note': 'Yeni beyan açıkça yeniden incelendi.',
    })
    assert response.status_code == 201, response.text
    record = response.json()
    assert 'fact_snapshots' in record['revision_comparison']['changed_dependency_groups']
    assert record['fact_snapshots'][0]['status'] == 'disputed'
    assert 'unsettled_premise' in codes(record)
    history = client.get(base + '/analyses/' + original['id'] + '/versions').json()
    assert history[1]['content']['fact_snapshots'][0]['text'] == fact['text']
    assert history[1]['freshness']['status'] == 'stale'


@pytest.mark.parametrize('kind', ['blank_quote', 'passage_scan', 'character_scan'])
def test_quote_and_lookup_budgets_fail_closed(workbench, kind):
    app, client, base, original, _, document_id, _ = workbench
    payload = copy.deepcopy(original)
    if kind == 'blank_quote':
        payload['evidence'][0].update(start=1, end=2)  # A space after the emoji.
    else:
        with app.state.store.session() as session:
            row = session.get(Record, document_id)
            content = app.state.store.decode(row)
            content['passages'].extend(
                {'id': f'synthetic-unused-{index}', 'text': 'x', 'locator': 'unused'}
                for index in range(2001 if kind == 'passage_scan' else 0)
            )
            if kind == 'character_scan':
                content['passages'].append({'id': 'synthetic-huge', 'text': 'x' * 2000001, 'locator': 'unused'})
            app.state.store.update(row, content)
            payload['evidence'][0]['document_revision'] = row.revision
            session.commit()
    assert client.post(base + '/analyses', json=payload).status_code == 422
    assert client.get(base + '/analyses').json() == []


@pytest.mark.parametrize('change', ['cross_condition', 'missing_rule', 'missing_premise', 'duplicate_node',
                                    'duplicate_selection', 'role_override', 'missing_fact', 'forged_review',
                                    'invalid_date', 'duplicate_refs', 'outside_span', 'excess_span'])
def test_invalid_and_invented_references_cannot_create_versions(workbench, change):
    _, client, base, original, *_ = workbench
    payload = copy.deepcopy(original)
    app = payload['applications'][0]
    if change == 'cross_condition':
        app['assessments'][0]['condition_id'] = 'missing_condition'
    elif change == 'missing_rule':
        app['rule_id'] = 'missing_rule'
    elif change == 'missing_premise':
        app['premise_ids'] = ['unknown_premise']
    elif change == 'duplicate_node':
        payload['premises'][0]['id'] = 'r1'
    elif change == 'duplicate_selection':
        payload['evidence'] *= 2
    elif change == 'role_override':
        payload['premises'][0]['role'] = 'established_fact'
    elif change == 'missing_fact':
        payload['premises'][0]['fact_id'] = 'invented'
    elif change == 'forged_review':
        payload['legal_approval'] = 'granted'
    elif change == 'invalid_date':
        payload['event_date'] = '2024-2-01'
    elif change == 'duplicate_refs':
        app['premise_ids'] *= 2
    elif change == 'outside_span':
        payload['evidence'][0]['end'] = 2000
    elif change == 'excess_span':
        payload['evidence'][0]['end'] = 6000
    assert client.post(base + '/analyses', json=payload).status_code in (404, 422)
    assert client.get(base + '/analyses').json() == []


def test_corrections_are_immutable_and_compare_structural_checks(workbench):
    app, client, base, payload, *_ = workbench
    first_payload = copy.deepcopy(payload)
    first_payload['applications'][0]['assessments'].pop()
    first = create(workbench, first_payload)
    endpoint = base + '/analyses/' + first['id'] + '/versions'
    with app.state.store.session() as session:
        encrypted = session.get(Record, first['latest_version_id']).payload
    assert client.post(endpoint, json=payload).status_code == 409
    revised = {**payload, 'expected_revision': first['revision'], 'change_note': 'İstisna değerlendirmesi eklendi.'}
    assert client.post(endpoint, json={**revised, 'change_note': ''}).status_code == 422
    response = client.post(endpoint, json=revised)
    assert response.status_code == 201, response.text
    second = response.json()
    assert second['version'] == 2 and second['checks']['effective_disposition'] == 'conditional'
    assert second['revision_comparison']['previous_version_id'] == first['latest_version_id']
    assert second['revision_comparison']['checks_no_longer_triggered']
    assert 'applications' in second['revision_comparison']['changed_sections']
    assert client.post(endpoint, json=revised).status_code == 409
    history = client.get(endpoint).json()
    assert len(history) == 2 and history[1]['content']['checks'] == first['checks']
    with app.state.store.session() as session:
        assert session.get(Record, first['latest_version_id']).payload == encrypted
    assert client.patch(endpoint, json=revised).status_code == 405


@pytest.mark.parametrize('change', ['fact', 'passage', 'document', 'missing_doc', 'new_contradiction', 'recipe'])
def test_dependency_changes_project_stale_without_rewriting_history(workbench, change, monkeypatch):
    app, client, base, payload, fact, document_id, _ = workbench
    changed_payload = copy.deepcopy(payload)
    other = None
    if change == 'new_contradiction':
        other = client.post(base + '/facts', json={'text': 'Teslim reddediliyor.', 'status': 'disputed'}).json()
        changed_payload['premises'].append({'id': 'p2', 'kind': 'fact', 'fact_id': other['id'], 'fact_revision': other['revision']})
        changed_payload['applications'][0]['premise_ids'].append('p2')
    record = create(workbench, changed_payload)
    with app.state.store.session() as session:
        original_version = session.get(Record, record['latest_version_id']).payload
    if change == 'fact':
        assert client.patch(base + '/facts/' + fact['id'], json={
            'text': 'Teslimin yapılmadığı beyan edildi.', 'status': 'disputed', 'reason': 'SYNTHETIC correction',
        }).status_code == 200
    elif change in {'passage', 'document', 'missing_doc'}:
        with app.state.store.session() as session:
            document = session.get(Record, document_id)
            if change == 'missing_doc':
                document.kind = 'removed_document'
            else:
                content = app.state.store.decode(document)
                if change == 'passage':
                    content['passages'][0]['text'] += 'SYNTHETIC amendment'
                else:
                    content['sha256'] = 'c' * 64
                app.state.store.update(document, content)
            session.commit()
    elif change == 'new_contradiction':
        assert client.post(base + '/practice/contradictions', json={
            'fact_ids': [fact['id'], other['id']], 'reason': 'Teslim konusunda yeni uyuşmazlık.',
        }).status_code == 201
    else:
        monkeypatch.setattr(analysis, 'RECIPE', 'future-recipe')
    current = client.get(base + '/analyses').json()[0]
    assert current['status'] == 'stale' and current['freshness']['reasons']
    assert current['checks'] == record['checks']
    with app.state.store.session() as session:
        assert session.get(Record, record['latest_version_id']).payload == original_version
    history = client.get(base + '/analyses/' + record['id'] + '/versions').json()
    assert history[0]['freshness']['status'] == 'stale'


def test_open_contradiction_is_scoped_to_the_used_premises(workbench):
    _, client, base, payload, fact, *_ = workbench
    other = client.post(base + '/facts', json={'text': 'Teslim reddediliyor.', 'status': 'disputed'}).json()
    assert client.post(base + '/practice/contradictions', json={'fact_ids': [fact['id'], other['id']], 'reason': 'Teslim konusunda uyuşmazlık.'}).status_code == 201
    expanded = copy.deepcopy(payload)
    expanded['premises'].append({'id': 'p2', 'kind': 'fact', 'fact_id': other['id'], 'fact_revision': other['revision']})
    expanded['applications'][0]['premise_ids'].append('p2')
    record = create(workbench, expanded)
    assert 'open_contradiction' in codes(record)
    assert record['checks']['effective_disposition'] == 'withheld'
    assert 'open_contradiction' not in codes(create(workbench))


def test_cross_matter_sources_history_and_exports_are_denied(workbench):
    _, client, base, payload, *_ = workbench
    record = create(workbench)
    other = client.post('/api/v1/matters', json={'title': 'Other SYNTHETIC', 'domain': 'contracts'}).json()['id']
    endpoint = f'/api/v1/matters/{other}/analyses'
    assert client.post(endpoint, json=payload).status_code == 404  # foreign fact
    assert client.get(endpoint + '/' + record['id'] + '/versions').status_code == 404
    assert client.get(endpoint + '/' + record['id'] + '/export').status_code == 404
    assert client.get(base + '/analyses/' + record['id'] + '/export?version_id=invented').status_code == 404
    assert client.get(base + '/analyses?limit=101').status_code == 422


def test_membership_csrf_and_active_user_are_required(workbench):
    app, client, base, _, *_ = workbench
    record = create(workbench)
    csrf = client.headers.pop('X-CSRF-Token')
    assert client.post(base + '/analyses/check', json=workbench[3]).status_code == 403
    client.headers['X-CSRF-Token'] = csrf
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        user_id = user.id
        session.delete(session.get(Membership, (base.rsplit('/', 1)[1], user.id)))
        session.commit()
    assert client.get(base + '/analyses').status_code == 404
    assert client.get(base + '/analyses/' + record['id'] + '/versions').status_code == 404
    assert client.get(base + '/analyses/' + record['id'] + '/export').status_code == 404
    with app.state.store.session() as session:
        session.get(User, user_id).active = False
        session.commit()
    assert client.get(base + '/analyses').status_code == 401


def test_version_prefix_does_not_admit_another_entity_or_record_kind(workbench):
    app, client, base, *_ = workbench
    record = create(workbench)
    ids = []
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        for index, (entity, kind) in enumerate([('other-entity', 'practice_analysis'), (record['id'], 'practice_argument')]):
            item = app.state.store.add(session, 'practice_version', user, {
                'entity_id': entity, 'entity_kind': kind, 'content': {}, 'version': 1,
            }, base.rsplit('/', 1)[1], record_id=record['id'] + f'-synthetic-{index}')
            ids.append(item.id)
        session.commit()
    endpoint = base + '/analyses/' + record['id']
    history = client.get(endpoint + '/versions')
    assert history.status_code == 200
    assert [item['id'] for item in history.json()] == [record['latest_version_id']]
    for version_id in ids:
        assert client.get(endpoint + '/export', params={'version_id': version_id}).status_code == 404


@pytest.mark.parametrize('format', ['docx', 'pdf'])
def test_exact_version_exports_show_sources_checks_and_stale_withholding(workbench, format):
    _, client, base, payload, fact, *_ = workbench
    record = create(workbench)
    assert client.patch(base + '/facts/' + fact['id'], json={'text': 'Olgu değişti.', 'status': 'disputed', 'reason': 'SYNTHETIC change'}).status_code == 200
    url = base + '/analyses/' + record['id'] + '/export'
    response = client.get(url, params={'version_id': record['latest_version_id'], 'format': format})
    assert response.status_code == 200, response.text
    content = '\n'.join(item.text for item in Document(io.BytesIO(response.content)).paragraphs) if format == 'docx' else '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)
    assert payload['conclusion']['text'] in content
    assert 'Sonuç değerlendirmesi: withheld' in content
    assert 'Güncellik: stale' in content
    assert 'Hukuki onay verilmedi' in content
    assert 'semantic_review_required' in content and 'private-rationale-checks-v1' in content
    assert 'Unicode aralığı: [2,' in content and 'Alıntı SHA-256:' in content
    assert 'İstisna: yazılı kabul.' in content
    assert fact['text'] in content and 'Olgu değişti.' not in content


@pytest.mark.parametrize('change', ['membership', 'fact'])
def test_export_rechecks_after_rendering(workbench, monkeypatch, change):
    app, client, base, _, fact, *_ = workbench
    record = create(workbench)
    render = analysis.render_export

    def interrupted(*args):
        response = render(*args)
        with app.state.store.session() as session:
            if change == 'membership':
                user = session.scalar(select(User).where(User.username == 'demo'))
                session.delete(session.get(Membership, (base.rsplit('/', 1)[1], user.id)))
            else:
                row = session.get(Record, fact['id'])
                app.state.store.update(row, {**app.state.store.decode(row), 'status': 'disputed'})
            session.commit()
        return response

    monkeypatch.setattr(analysis, 'render_export', interrupted)
    response = client.get(base + '/analyses/' + record['id'] + '/export')
    assert response.status_code == (404 if change == 'membership' else 409)
    assert 'application/vnd.openxmlformats' not in response.headers.get('content-type', '')


def test_other_firm_and_same_firm_nonmember_cannot_read(workbench):
    app, _, base, *_ = workbench
    for firm in ('demo-firm', 'other-firm'):
        username = 'SYNTHETIC-' + firm
        with app.state.store.session() as session:
            session.add(User(username=username, name='Synthetic Lawyer', firm_id=firm, role='lawyer', password_hash=hash_password('synthetic-test-password')))
            session.commit()
        other = TestClient(app)
        try:
            assert other.post('/api/v1/auth/login', json={'username': username, 'password': 'synthetic-test-password'}).status_code == 200
            assert other.get(base + '/analyses').status_code == 404
        finally:
            other.close()
