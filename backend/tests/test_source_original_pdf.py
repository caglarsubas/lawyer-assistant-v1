"""Invented page mappings only; preview bindings do not establish source fidelity."""

import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import select
from test_public_sources import source as source_fixture
from test_workspace import workspace as workspace_fixture

from app.db import User
from app.public_sources import PublicSourceError, PublicSourceStore
from app.source_original_text import MAX_ORIGINAL_BYTES, OriginalTextUnavailable

source = source_fixture
workspace = workspace_fixture


@pytest.fixture
def pdf_source(source):
    store, args, metadata, locators = source

    def make(*, raw=b'%PDF-1.4 SYNTHETIC original; no server parser', media='application/pdf', change=None):
        pages = ['SYNTHETIC page one İ😀', 'SYNTHETIC page two & <script>']
        text = '\n\n'.join(pages)
        offset, spans = 0, []
        for number, page in enumerate(pages, 1):
            spans.append({'id': f'pdf_page_{number:04d}', 'start': offset, 'end': offset + len(page),
                          'text_sha256': hashlib.sha256(page.encode()).hexdigest(),
                          'locator': f'PDF page {number}; extracted page code points [0,{len(page)})'})
            offset += len(page) + 2
        if change:
            change(spans)
        Path(args['raw_path']).write_bytes(raw)
        Path(args['text_path']).write_text(text, encoding='utf-8')
        metadata['raw_media_type'] = media
        locators.update(raw_sha256=hashlib.sha256(raw).hexdigest(),
                        text_sha256=hashlib.sha256(text.encode()).hexdigest(), passages=spans)
        Path(args['metadata_path']).write_text(json.dumps(metadata), encoding='utf-8')
        Path(args['locators_path']).write_text(json.dumps(locators), encoding='utf-8')
        identifier = store.import_package(**args)['id']
        return identifier, raw

    return store, make


def test_exact_pdf_binding_both_pages_and_no_review_side_effects(pdf_source):
    store, make = pdf_source
    identifier, raw = make()
    for number in (1, 2):
        result = store.original_pdf(identifier, f'pdf_page_{number:04d}')
        assert result == {'source_id': identifier, 'source_version_id': 'operator-version-1',
                          'passage_id': f'pdf_page_{number:04d}', 'raw_sha256': hashlib.sha256(raw).hexdigest(),
                          'text_sha256': store.passages(identifier)['text_sha256'], 'raw_bytes': len(raw),
                          'raw_media_type': 'application/pdf', 'page': number, 'page_count': 2,
                          'integrity_scope': 'all_artifacts_verified',
                          'locator_coordinate_status': 'consistent_not_fidelity_reviewed',
                          'extraction_fidelity_verified': False}
    assert store.detail(identifier)['review_status'] == 'legal_review_pending'
    assert store.detail(identifier)['rights_status'] == 'rights_pending'


@pytest.mark.parametrize('locator', ['page 1', 'PDF page 0; extracted page code points [0,20)',
                                    'PDF page 51; extracted page code points [0,20)',
                                    'PDF page 1; extracted page code points [1,20)',
                                    'PDF page 1; extracted page code points [0,20001)',
                                    'PDF page 1; extracted page code points [0,1)',
                                    'PDF page 2; extracted page code points [0,20)',
                                    'PDF page 1; extracted page code points [0,20) trailing'])
def test_unknown_or_changed_mapping_not_guessed(pdf_source, locator):
    store, make = pdf_source
    identifier, _ = make(change=lambda spans: spans[0].update(locator=locator))
    with pytest.raises(OriginalTextUnavailable):
        store.original_pdf(identifier, 'pdf_page_0002')  # Validate the whole map, not just selected page.


@pytest.mark.parametrize('change', ['id', 'partial', 'missing_page', 'unmapped_tail'])
def test_complete_page_mapping_required(pdf_source, change):
    store, make = pdf_source
    def alter(spans):
        if change == 'id':
            spans[0]['id'] = 'arbitrary'
        elif change == 'missing_page':
            spans[1]['locator'] = spans[1]['locator'].replace('page 2;', 'page 3;')
        else:
            spans.pop(0 if change == 'partial' else 1)
    identifier, _ = make(change=alter)
    with pytest.raises(OriginalTextUnavailable):
        store.original_pdf(identifier, 'pdf_page_0002')


@pytest.mark.parametrize('options', [{'media': 'text/html'}, {'raw': b'x' * (MAX_ORIGINAL_BYTES + 1)}])
def test_unsupported_original_remains_downloadable(pdf_source, options):
    store, make = pdf_source
    identifier, raw = make(**options)
    with pytest.raises(OriginalTextUnavailable):
        store.original_pdf(identifier, 'pdf_page_0001')
    assert store.verified_package(identifier).raw == raw


def test_api_is_inert_and_does_not_parse_fetch_or_create_review(workspace, pdf_source, monkeypatch):
    import socket

    import pypdf
    app, client, _ = workspace
    store, make = pdf_source
    identifier, raw = make()
    app.state.settings.public_source_dir = store.root
    def unexpected(*args, **kwargs):
        pytest.fail('Server preview must not parse PDF or use network')
    monkeypatch.setattr(pypdf, 'PdfReader', unexpected)
    monkeypatch.setattr(socket, 'getaddrinfo', unexpected)
    response = client.get(f'/api/v1/public-sources/{identifier}/original-pdf?passage_id=pdf_page_0002')
    assert response.status_code == 200
    assert response.json()['page'] == 2
    assert response.headers['content-type'] == 'application/json'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['content-security-policy'] == "sandbox; default-src 'none'; frame-ancestors 'none'"
    assert client.get(f'/api/v1/public-sources/{identifier}/original').content == raw
    state = client.get(f'/api/v1/public-sources/{identifier}/review').json()
    assert state['revision'] == 0 and state['history'] == []


@pytest.mark.parametrize('artifact', ['raw.bin', 'text.txt', 'locators.json', 'source.json', 'manifest.json'])
def test_all_artifacts_verified_before_binding(workspace, pdf_source, artifact):
    app, client, _ = workspace
    store, make = pdf_source
    identifier, _ = make()
    app.state.settings.public_source_dir = store.root
    path = store.root / identifier / artifact
    path.chmod(0o600)
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(PublicSourceError):
        store.original_pdf(identifier, 'pdf_page_0001')
    response = client.get(f'/api/v1/public-sources/{identifier}/original-pdf?passage_id=pdf_page_0001')
    assert response.status_code == 409
    assert 'SYNTHETIC' not in response.text and str(store.root) not in response.text


@pytest.mark.parametrize('change,status', [('role', 403), ('active', 401), ('firm', 401)])
def test_revoked_access_during_verified_read_is_rechecked(workspace, pdf_source, monkeypatch, change, status):
    app, client, _ = workspace
    store, make = pdf_source
    identifier, _ = make()
    app.state.settings.public_source_dir = store.root
    original = PublicSourceStore.verified_package
    def revoke(self, source_id):
        package = original(self, source_id)
        with app.state.store.session() as db:
            user = db.scalar(select(User).where(User.username == 'demo'))
            if change == 'role':
                user.role = 'lawyer'
            elif change == 'active':
                user.active = False
            else:
                user.firm_id = 'other-firm'
            db.commit()
        return package
    monkeypatch.setattr(PublicSourceStore, 'verified_package', revoke)
    assert client.get(f'/api/v1/public-sources/{identifier}/original-pdf?passage_id=pdf_page_0001').status_code == status


def test_authenticated_curator_required(workspace, pdf_source):
    app, client, _ = workspace
    store, make = pdf_source
    identifier, _ = make()
    app.state.settings.public_source_dir = store.root
    with app.state.store.session() as db:
        user = db.scalar(select(User).where(User.username == 'demo'))
        user.role = 'lawyer'
        db.commit()
    route = f'/api/v1/public-sources/{identifier}/original-pdf?passage_id=pdf_page_0001'
    assert client.get(route).status_code == 403
    client.cookies.clear()
    assert client.get(route).status_code == 401


@pytest.mark.parametrize('passage', ['../secret', 'p1', 'pdf_page_0001?query', 'pdf_page_1', 'pdf_page_0003'])
def test_invalid_or_absent_passage_returns_fixed_failure(workspace, pdf_source, passage):
    app, client, _ = workspace
    store, make = pdf_source
    identifier, _ = make()
    app.state.settings.public_source_dir = store.root
    response = client.get(f'/api/v1/public-sources/{identifier}/original-pdf', params={'passage_id': passage})
    assert response.status_code == 422
    assert 'SYNTHETIC' not in response.text
    assert client.get('/api/v1/public-sources/invalid/original-pdf?passage_id=pdf_page_0001').status_code == 404
