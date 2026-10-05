import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from test_workspace import workspace as workspace_fixture

from app import assistant as assistant_module
from app.assistant import calendar_period, exact_claims
from app.auth import hash_password
from app.db import Audit, LoginSession, Membership, Record, User
from app.provider import ProviderError

workspace = workspace_fixture


@pytest.mark.parametrize('mode', ['guide', 'chat'])
def test_source_review_guide_reads_no_portfolio_or_provider(workspace, monkeypatch, mode):
    app, client, _ = workspace
    monkeypatch.setattr(assistant_module, 'list_workspaces', lambda *a, **kw: pytest.fail('Unrelated portfolio read'))
    class NoInference:
        configured = True
        def generate(self, *args):
            pytest.fail('Pending source review must not invoke inference')
    app.state.provider = NoInference()
    result = ask(client, mode, question='Kaynağı nasıl incelemeliyim?', context={'page': 'sources'})
    assert result.status_code == 200
    assert not result.json()['provider_used']
    assert 'graf yayımlama onayı değildir' in result.json()['answer']
    assert [item['id'] for item in result.json()['sources']] == ['guide:source-review']
    assert 'inceleme notları' in result.json()['limitations'][0]


def test_source_review_rejects_mixed_private_context(workspace):
    _, client, matter_id = workspace
    assert ask(client, workspace_id=matter_id, context={'page': 'sources'}).status_code == 422


def ask(client, mode='guide', workspace_id=None, **kwargs):
    context = {'workspace_id': workspace_id, **kwargs.pop('context', {})}
    return client.post('/api/v1/assistant/respond', json={'mode': mode, 'context': context, **kwargs})


def test_guide_tracks_saved_workspace_section(workspace):
    app, client, matter_id = workspace
    r = ask(client, workspace_id=matter_id, context={'section': 'comments'})
    assert r.status_code == 200
    assert 'yorum' in r.json()['answer'].lower()
    assert r.json()['sources'][0]['workspace_id'] == matter_id
    assert not r.json()['provider_used']
    assert ask(client, workspace_id='unknown').status_code == 404


def test_summary_uses_selected_customer_and_current_access(workspace):
    app, client, matter_id = workspace
    customer = client.post('/api/v1/customers', json={'name': 'Özet müvekkili'}).json()
    new = client.post('/api/v1/workspaces', json={'title': 'İlgili çalışma', 'domain': 'contracts', 'customer_ids': [customer['id']]}).json()
    client.post(f"/api/v1/workspaces/{new['id']}/comments", json={'text': 'Toplantı hazırlığı.'})
    response = ask(client, 'monthly', context={'customer_ids': [customer['id']]}).json()
    assert '1 çalışma alanı' in response['answer']
    assert 'İlgili çalışma' in response['answer']
    assert 'Örnek hizmet' not in response['answer']
    assert all(item['workspace_id'] == new['id'] for item in response['sources'])
    assert response['period']['from'].endswith('-01')
    # A different same-firm admin cannot discover private workspace counts/titles.
    with app.state.store.session() as db:
        db.add(User(username='other', name='Other', firm_id='demo-firm', role='admin', password_hash=hash_password('other-password')))
        db.commit()
    login = client.post('/api/v1/auth/login', json={'username':'other','password':'other-password'}).json()
    client.headers['X-CSRF-Token'] = login['csrf_token']
    assert ask(client, workspace_id=new['id']).status_code == 404
    response = ask(client, 'monthly', context={'customer_ids':[customer['id']]}).json()
    assert '0 çalışma alanı' in response['answer']
    assert response['sources'] == []


def test_periods_follow_turkish_calendar():
    instant = datetime(2026, 10, 3, 22, 0, tzinfo=timezone.utc)
    assert tuple(map(str, calendar_period('daily', instant))) == ('2026-10-04', '2026-10-04')
    assert tuple(map(str, calendar_period('weekly', instant))) == ('2026-09-28', '2026-10-04')
    assert tuple(map(str, calendar_period('monthly', instant))) == ('2026-10-01', '2026-10-04')


def test_unknown_or_inverted_dates_rejected(workspace):
    _, client, _ = workspace
    assert ask(client, 'daily', context={'date_from':'2026-10-04','date_to':'2026-10-03'}).status_code == 422
    assert ask(client, 'daily', context={'date_from':'garbage'}).status_code == 422
    assert ask(client, 'daily', context={'date_field':'fake'}).status_code == 422


def test_model_claims_must_match_their_sources():
    good = json.dumps({'summary':'IGNORED UNSUPPORTED SUMMARY', 'claims':[{'text':'Kayıtlı yorum','evidence_ids':['a']}]})
    assert exact_claims(good, [{'id':'a','text':'Kayıtlı yorum burada.'}]) == [('Kayıtlı yorum',['a'])]
    for claims in [[], [{'text':'invented','evidence_ids':['a']}], [{'text':'Kayıtlı','evidence_ids':['foreign']}], [{'text':'','evidence_ids':['a']}]]:
        with pytest.raises(ProviderError):
            exact_claims(json.dumps({'claims':claims}), [{'id':'a','text':'Kayıtlı yorum burada.'}])


def test_chat_has_real_provider_provenance_and_no_free_summary(workspace):
    app, client, matter_id = workspace
    class FakeProvider:
        configured = True
        def generate(self, question, evidence):
            selected = evidence[1]
            return json.dumps({'summary':'INVENTED', 'claims':[{'text':selected['text'],'evidence_ids':[selected['id']]}]})
    app.state.provider = FakeProvider()
    r = ask(client, 'chat', matter_id, question='Çalışma amacım ne?')
    assert r.status_code == 200
    assert r.json()['provider_used']
    assert 'INVENTED' not in r.json()['answer']
    assert r.json()['sources'][0]['workspace_id'] == matter_id


@pytest.mark.parametrize('failure', [False, True])
def test_revoked_access_during_provider_call_never_returns_private_fallback(workspace, failure):
    app, client, matter_id = workspace
    class RevokingProvider:
        configured = True
        def generate(self, question, evidence):
            with app.state.store.session() as db:
                user = db.scalar(select(User).where(User.username == 'demo'))
                member = db.get(Membership, (matter_id, user.id))
                db.delete(member)
                db.commit()
            if failure:
                raise ProviderError('Failed')
            return json.dumps({'claims':[{'text':evidence[1]['text'],'evidence_ids':[matter_id]}]})
    app.state.provider = RevokingProvider()
    response = ask(client, 'chat', matter_id, question='Çalışma amacım ne?')
    assert response.status_code == 404
    assert 'Örnek hizmet' not in response.text


def test_missing_provider_chat_explains_fallback(workspace):
    _, client, matter_id = workspace
    r = ask(client, 'chat', matter_id, question='Nereden başlamalıyım?')
    assert r.status_code == 200
    assert not r.json()['provider_used']
    assert r.json()['limitations']


@pytest.mark.parametrize('failure', [False, True])
@pytest.mark.parametrize(('mutation', 'expected_status'), [
    ('workspace_revision', 409), ('comment_revision', 409), ('comment_deleted', 409),
    ('workspace_archived', 404), ('user_deactivated', 401), ('session_revoked', 401),
])
def test_changed_or_revoked_context_never_returns_old_quotes_or_fallback(workspace, failure, mutation, expected_status):
    app, client, matter_id = workspace
    comment = client.post(f'/api/v1/workspaces/{matter_id}/comments', json={'text': 'Özel kaynak notu.'}).json()

    class ChangingProvider:
        configured = True

        def generate(self, question, evidence):
            with app.state.store.session() as db:
                if mutation == 'workspace_revision':
                    record = db.get(Record, matter_id)
                    app.state.store.update(record, {**app.state.store.decode(record), 'title': 'Değişen çalışma'})
                elif mutation == 'comment_revision':
                    record = db.get(Record, comment['id'])
                    app.state.store.update(record, {**app.state.store.decode(record), 'text': 'Değişen kaynak notu.'})
                elif mutation == 'comment_deleted':
                    db.delete(db.get(Record, comment['id']))
                elif mutation == 'workspace_archived':
                    db.get(Record, matter_id).kind = 'archived_matter'
                elif mutation == 'user_deactivated':
                    db.scalar(select(User).where(User.username == 'demo')).active = False
                elif mutation == 'session_revoked':
                    db.delete(db.scalar(select(LoginSession)))
                db.commit()
            if failure:
                raise ProviderError('Sensitive internal provider details must remain hidden')
            selected = evidence[-1]
            return json.dumps({'claims': [{'text': selected['text'], 'evidence_ids': [selected['id']]}]})

    app.state.provider = ChangingProvider()
    response = ask(client, 'chat', matter_id, question='Kayıtlı yorum nedir?')
    assert response.status_code == expected_status
    assert 'Özel kaynak notu' not in response.text
    assert 'Örnek hizmet' not in response.text
    assert 'Sensitive internal' not in response.text


def test_summary_counts_only_events_inside_turkish_calendar_boundaries(workspace, monkeypatch):
    app, client, matter_id = workspace
    from datetime import date
    monkeypatch.setattr(assistant_module, 'calendar_period', lambda mode: (date(2035, 1, 15), date(2035, 1, 15)))
    with app.state.store.session() as db:
        for stamp in ['2035-01-14T20:59:59+00:00', '2035-01-14T21:00:00+00:00',
                      '2035-01-15T20:59:59+00:00', '2035-01-15T21:00:00+00:00']:
            db.add(Audit(actor_id='synthetic-reviewer', action='synthetic-event', object_id=matter_id,
                         matter_id=matter_id, created_at=stamp))
        db.commit()
    response = ask(client, 'daily').json()
    assert '2 kayıtlı işlem' in response['answer']
    assert response['period'] == {'from': '2035-01-15', 'to': '2035-01-15'}
    assert [item['workspace_id'] for item in response['sources']] == [matter_id]


def test_chat_source_boundary_excludes_document_payloads_and_other_workspaces(workspace):
    app, client, matter_id = workspace
    other = client.post('/api/v1/workspaces', json={
        'title': 'Diğer çalışma', 'domain': 'contracts', 'objective': 'DIĞER_ÇALIŞMA_ÖZEL_AMACI',
    }).json()
    private_other = client.post(f"/api/v1/workspaces/{other['id']}/comments", json={'text': 'DIĞER_ÖZEL_YORUM'}).json()
    comments = [client.post(f'/api/v1/workspaces/{matter_id}/comments', json={'text': f'Yerel not {number}'}).json()
                for number in range(5)]
    captured = []

    class InspectingProvider:
        configured = True

        def generate(self, question, evidence):
            captured.extend(evidence)
            return json.dumps({'claims': [{'text': evidence[0]['text'], 'evidence_ids': ['guide']}]})

    app.state.provider = InspectingProvider()
    assert ask(client, 'chat', matter_id, question='Nasıl ilerlemeliyim?').status_code == 200
    assert {item['id'] for item in captured} == {'guide', matter_id, *(item['id'] for item in comments[-4:])}
    assert private_other['id'] not in str(captured)
    assert 'DIĞER_' not in str(captured)
    with app.state.store.session() as db:
        document_ids = set(db.scalars(select(Record.id).where(Record.kind == 'document')).all())
    assert document_ids.isdisjoint(item['id'] for item in captured)
