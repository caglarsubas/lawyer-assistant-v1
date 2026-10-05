import json

import httpx
import pytest
from sqlalchemy import delete, select
from test_workspace import workspace as workspace_fixture

from app import extraction_client
from app.db import LoginSession, Record, User
from app.extraction_client import MAX_DOCUMENT_BYTES, ExtractionClient
from app.scanner import MalwareDetected, ScannerUnavailable

workspace = workspace_fixture
READY_SCANNER = {'status': 'ready', 'issues': [], 'version': '1.5.0', 'signature_date': '2026-10-04T00:00:00+00:00'}


def setup_intake(app, monkeypatch, scanner=None, extractor_status='ready'):
    app.state.settings.demo_mode = False
    app.state.settings.clamav_host = 'scanner'
    monkeypatch.setattr('app.readiness.probe_scanner', lambda *a, **k: scanner or READY_SCANNER)
    class Extractor:
        def probe(self):
            return {'status': extractor_status, 'issues': [] if extractor_status == 'ready' else [{'code': 'extractor_unavailable', 'message': 'Unavailable'}]}
    app.state.extractor = Extractor()


def test_readiness_requires_authenticated_session(workspace):
    _, client, _ = workspace
    client.cookies.clear()
    assert client.get('/api/v1/readiness').status_code == 401
    assert client.get('/api/v1/intake/readiness').status_code == 401


def test_intake_readiness_is_independent_of_inference(workspace, monkeypatch):
    app, client, _ = workspace
    setup_intake(app, monkeypatch)
    monkeypatch.setattr(app.state.provider, 'probe', lambda: pytest.fail('Upload readiness must not use inference'))
    result = client.get('/api/v1/intake/readiness').json()
    assert result['status'] == 'ready' and result['scanner']['version'] == '1.5.0'
    assert result['checked_at'] and result['demo_mode'] is False


@pytest.mark.parametrize('scanner,extractor,status', [
    ({'status':'blocked','issues':[{'code':'stale','message':'Stale signatures'}]}, 'ready', 'blocked'),
    ({'status':'unavailable','issues':[]}, 'ready', 'unavailable'),
    (READY_SCANNER, 'unavailable', 'unavailable'),
])
def test_intake_readiness_fails_closed(workspace, monkeypatch, scanner, extractor, status):
    app, client, _ = workspace
    setup_intake(app, monkeypatch, scanner, extractor)
    assert client.get('/api/v1/intake/readiness').json()['status'] == status


def test_readiness_reports_runtime_model_metadata_without_claiming_inference(workspace, monkeypatch):
    app, client, _ = workspace
    setup_intake(app, monkeypatch)
    monkeypatch.setattr(app.state.provider, 'probe', lambda: {'ready':True,'issues':[], 'model':{'id':'synthetic-local-model'}, 'checks':{'configuration':True,'connection':True,'model':True}})
    result = client.get('/api/v1/readiness').json()
    assert result['provider']['model'] == 'synthetic-local-model'
    assert result['provider']['status'] == 'ready'
    assert result['provider']['qualification'] == 'runtime-connectivity-only'
    assert 'api_key' not in json.dumps(result).lower()


def test_readiness_exposes_transport_exception_without_origin_or_route_fingerprint(workspace, monkeypatch):
    from test_provider_tunnel import HOST, ROUTE, settings
    app, client, _ = workspace
    for name, value in vars(settings()).items():
        setattr(app.state.settings, name, value)
    monkeypatch.setattr(app.state.provider, 'probe', lambda: {'ready': True, 'issues': [],
                        'model': {'id': 'test-local-model'},
                        'checks': {'configuration': True, 'connection': True, 'model': True}})
    expected = {'mode': 'approved_laptop_tunnel', 'uses_public_network': True, 'air_gapped': False}
    readiness = client.get('/api/v1/readiness')
    assert readiness.status_code == 200 and readiness.json()['provider']['transport'] == expected
    status = client.get('/api/v1/status')
    assert status.json()['provider']['readiness']['transport'] == expected
    rendered = readiness.text + status.text
    assert HOST not in rendered and ROUTE['route_sha256'] not in rendered
    assert 'SYNTHETIC-NOT-A-REAL-KEY' not in rendered


def test_research_snapshot_labels_tunnel_inference_distinctly(workspace, monkeypatch):
    from test_provider_tunnel import settings
    from test_workspace import research_product
    app, client, matter = workspace
    for name, value in vars(settings()).items():
        setattr(app.state.settings, name, value)
    def generate(question, passages):
        return json.dumps({'summary': '', 'claims': [{'text': passages[0]['text'],
                                                     'evidence_ids': [passages[0]['id']]}]})
    monkeypatch.setattr(app.state.provider, 'generate', generate)
    product = research_product(client, matter)
    assert product['snapshots']['provider'] == 'approved-laptop-tunnel-validated-quotes'


def test_demo_intake_is_explicitly_synthetic(workspace):
    _, client, _ = workspace
    result = client.get('/api/v1/intake/readiness').json()
    assert result['demo_mode'] and result['scanner']['status'] == 'demo-bypass'
    assert result['issues'][0]['code'] == 'synthetic_demo_only'


def test_revoked_session_during_probe_does_not_return_result(workspace, monkeypatch):
    app, client, _ = workspace
    setup_intake(app, monkeypatch)
    def revoke():
        with app.state.store.session() as db:
            user = db.scalar(select(User).where(User.username == 'demo'))
            user.active = False
            db.commit()
        return {'status':'ready','issues':[]}
    monkeypatch.setattr(app.state.extractor, 'probe', revoke)
    assert client.get('/api/v1/intake/readiness').status_code == 401


@pytest.mark.parametrize('error,status', [(MalwareDetected('bad'),422),(ScannerUnavailable('secret endpoint'),503)])
def test_rejected_scan_never_stores_original_or_record(workspace, monkeypatch, error, status):
    app, client, matter = workspace
    setup_intake(app, monkeypatch)
    def reject(*args, **kwargs):
        raise error
    monkeypatch.setattr('app.main.scan_document', reject)
    with app.state.store.session() as db:
        before = len(db.scalars(select(Record).where(Record.kind=='document')).all())
    result = client.post(f'/api/v1/matters/{matter}/documents', files={'file':('test.txt',b'synthetic content','text/plain')})
    assert result.status_code == status
    assert 'secret endpoint' not in result.text
    assert not list((app.state.settings.data_dir / 'documents').glob('*.enc'))
    with app.state.store.session() as db:
        assert len(db.scalars(select(Record).where(Record.kind=='document')).all()) == before


def test_session_revoked_during_extraction_cannot_commit_intake(workspace, monkeypatch):
    app, client, matter = workspace
    setup_intake(app, monkeypatch)
    monkeypatch.setattr('app.main.scan_document', lambda *args, **kwargs: None)
    with app.state.store.session() as db:
        before = len(db.scalars(select(Record).where(Record.kind == 'document')).all())
    def extract(*args):
        with app.state.store.session() as db:
            db.execute(delete(LoginSession))
            db.commit()
        return {'passages': [{'text': 'Synthetic content', 'locator': 'Paragraph 1'}], 'warnings': []}
    app.state.extractor.execute = extract
    response = client.post(f'/api/v1/matters/{matter}/documents', files={'file': ('fixture.txt', b'Synthetic content', 'text/plain')})
    assert response.status_code == 401
    assert not list((app.state.settings.data_dir / 'documents').glob('*.enc'))
    with app.state.store.session() as db:
        assert len(db.scalars(select(Record).where(Record.kind == 'document')).all()) == before


@pytest.mark.parametrize('status,payload,expected', [
    (200, {'status':'ready','protocol':'isolated-extraction-v1','max_document_bytes':MAX_DOCUMENT_BYTES}, 'ready'),
    (401, {'detail':'Unauthorized'}, 'unavailable'),
    (200, {'status':'ok'}, 'unavailable'),
    (302, {}, 'unavailable'),
])
def test_extractor_readiness_uses_authenticated_bounded_protocol(monkeypatch,status,payload,expected):
    original = httpx.Client
    def respond(request):
        assert request.method == 'GET' and request.url.path == '/ready'
        assert request.headers['authorization'] == 'Bearer synthetic-worker-token-of-32-characters'
        assert request.content == b''
        return httpx.Response(status,json=payload)
    def client(**kwargs):
        assert not kwargs['follow_redirects'] and not kwargs['trust_env']
        return original(transport=httpx.MockTransport(respond), **kwargs)
    monkeypatch.setattr(extraction_client.httpx,'Client',client)
    worker=ExtractionClient('http://extractor:8002','synthetic-worker-token-of-32-characters')
    assert worker.probe()['status'] == expected
