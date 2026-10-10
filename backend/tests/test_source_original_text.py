"""Invented source bytes only; coordinate consistency is not legal/fidelity review."""

import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import select
from test_public_sources import source as source_fixture
from test_workspace import workspace as workspace_fixture

from app.db import User
from app.public_sources import PublicSourceError, PublicSourceStore
from app.source_original_text import MAX_ORIGINAL_BYTES, MAX_WINDOW, OriginalTextUnavailable

source = source_fixture
workspace = workspace_fixture


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


@pytest.fixture
def original_source(source):
    store, args, metadata, locators = source

    def make(*, encoding='utf-8', declaration=None, bom=False, content=None, locator_change=None):
        label = declaration or {'cp1254': 'windows-1254', 'iso8859-9': 'iso-8859-9'}.get(encoding, encoding)
        content = content or '  İğüşöç Iı &amp; <b>İnceleme</b> <script>fetch("https://untrusted.invalid")</script>  '
        decoded = f'<meta charset="{label}">\r\n<p>{content}</p>'
        start, end = decoded.index(content), decoded.index(content) + len(content)
        raw = (b'\xef\xbb\xbf' if bom else b'') + decoded.encode(encoding)
        Path(args['raw_path']).write_bytes(raw)
        metadata['raw_media_type'] = 'text/html'
        write(args['metadata_path'], metadata)
        locators['raw_sha256'] = sha(raw)
        locators['passages'][0]['locator'] = locator_change or f'HTML source line 2, column 4; decoded code points [{start},{end})'
        write(args['locators_path'], locators)
        identifier = store.import_package(**args)['id']
        return identifier, decoded, content, start, end

    return store, make


@pytest.mark.parametrize('encoding,bom', [('utf-8', False), ('utf-8', True), ('cp1254', False), ('iso8859-9', False)])
def test_exact_unicode_original_bytes_ranges_and_hashes(original_source, encoding, bom):
    store, make = original_source
    identifier, decoded, content, start, end = make(encoding=encoding, bom=bom)
    result = store.original_text(identifier, 'p1')
    assert result['text'] == content  # No entity decoding, whitespace trim or HTML interpretation.
    assert (result['range_start'], result['range_end'], result['start'], result['end']) == (start, end, start, end)
    assert result['encoding'] == encoding
    assert result['offset_unit'] == 'unicode_code_points_excluding_initial_utf8_bom'
    assert result['decoded_original_sha256'] == sha(decoded.encode('utf-8'))
    assert result['window_sha256'] == sha(content.encode('utf-8'))
    assert result['raw_sha256'] == store.detail(identifier)['artifacts']['raw.bin']['sha256']
    assert result['extraction_fidelity_verified'] is False
    assert result['locator_coordinate_status'] == 'consistent_not_fidelity_reviewed'
    assert result['next_offset'] is None
    # Fixture extraction deliberately differs. Coordinates must not certify correspondence.
    assert store.passages(identifier)['items'][0]['text'] not in content
    assert store.detail(identifier)['rights_status'] == 'rights_pending'
    assert store.detail(identifier)['review_status'] == 'legal_review_pending'


def test_paging_preserves_crlf_combining_marks_astral_chars_and_whitespace(original_source):
    store, make = original_source
    identifier, _, content, start, end = make(content=' x😀İ\r\ne\u0301 ' * 3100)
    windows, offset = [], 0
    while True:
        result = store.original_text(identifier, 'p1', offset=offset)
        assert result['start'] == start + offset
        assert result['end'] <= min(start + offset + MAX_WINDOW, end)
        assert len(result['text']) <= MAX_WINDOW
        windows.append(result['text'])
        if result['next_offset'] is None:
            break
        offset = result['next_offset']
    assert len(windows) == 3
    assert ''.join(windows) == content
    with pytest.raises(OriginalTextUnavailable):
        store.original_text(identifier, 'p1', offset=len(content))


@pytest.mark.parametrize('bounds', [{'offset': -1}, {'offset': True}, {'offset': 1.1},
                                   {'offset': MAX_ORIGINAL_BYTES + 1}, {'limit': 0},
                                   {'limit': True}, {'limit': MAX_WINDOW + 1}])
def test_invalid_bounds_cannot_expand_original_range(original_source, bounds):
    store, make = original_source
    identifier, *_ = make()
    with pytest.raises(OriginalTextUnavailable):
        store.original_text(identifier, 'p1', **bounds)


@pytest.mark.parametrize('locator', ['page 1', 'HTML source line 1, column 4; decoded code points [26,30)',
                                    'HTML source line 2, column 5; decoded code points [26,30)',
                                    'HTML source line 2, column 4; decoded code points [26,9999999)',
                                    'HTML source line 2, column 4; decoded code points [26,26)',
                                    'HTML source line 2, column 4; decoded code points [-1,30)',
                                    'HTML source line 2, column 4; decoded code points [26,30) extra'])
def test_unknown_out_of_bounds_and_conflicting_coordinates_are_not_guessed(original_source, locator):
    store, make = original_source
    identifier, *_ = make(locator_change=locator)
    with pytest.raises(OriginalTextUnavailable):
        store.original_text(identifier, 'p1')


@pytest.mark.parametrize('change', ['unsupported_encoding', 'conflicting_encoding', 'invalid_utf8', 'oversized', 'non_html'])
def test_unsupported_originals_stay_downloadable_but_not_previewed(source, change):
    store, args, metadata, locators = source
    raw = {'unsupported_encoding': b'<meta charset="shift-jis"><p>text</p>',
           'conflicting_encoding': b'<meta charset="utf-8"><meta charset="windows-1254"><p>text</p>',
           'invalid_utf8': b'<p>\xff</p>', 'oversized': b'x' * (MAX_ORIGINAL_BYTES + 1),
           'non_html': b'opaque PDF bytes'}[change]
    metadata['raw_media_type'] = 'application/pdf' if change == 'non_html' else 'text/html'
    Path(args['raw_path']).write_bytes(raw)
    write(args['metadata_path'], metadata)
    locators['raw_sha256'] = sha(raw)
    locators['passages'][0]['locator'] = 'HTML source line 1, column 1; decoded code points [0,1)'
    write(args['locators_path'], locators)
    identifier = store.import_package(**args)['id']
    with pytest.raises(OriginalTextUnavailable):
        store.original_text(identifier, 'p1')
    assert store.verified_package(identifier).raw == raw


def test_response_is_inert_json_with_no_store_and_no_network_or_parser(workspace, original_source, monkeypatch):
    import socket
    from html.parser import HTMLParser
    app, client, _ = workspace
    store, make = original_source
    identifier, _, content, *_ = make()
    app.state.settings.public_source_dir = store.root
    def unexpected(*args, **kwargs):
        pytest.fail('Original preview must not resolve, fetch or parse HTML')
    monkeypatch.setattr(socket, 'getaddrinfo', unexpected)
    monkeypatch.setattr(HTMLParser, '__init__', unexpected)
    response = client.get(f'/api/v1/public-sources/{identifier}/original-text?passage_id=p1')
    assert response.status_code == 200
    assert response.json()['text'] == content
    assert response.headers['content-type'] == 'application/json'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['content-security-policy'] == "sandbox; default-src 'none'; frame-ancestors 'none'"
    assert 'content-disposition' not in response.headers


@pytest.mark.parametrize('artifact', ['raw.bin', 'text.txt', 'locators.json', 'source.json', 'manifest.json'])
def test_all_artifacts_checked_before_preview(workspace, original_source, artifact):
    app, client, _ = workspace
    store, make = original_source
    identifier, *_ = make()
    app.state.settings.public_source_dir = store.root
    path = store.root / identifier / artifact
    path.chmod(0o600)
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(PublicSourceError):
        store.original_text(identifier, 'p1')
    response = client.get(f'/api/v1/public-sources/{identifier}/original-text?passage_id=p1')
    assert response.status_code == 409
    assert 'untrusted.invalid' not in response.text and str(store.root) not in response.text


@pytest.mark.parametrize('change,status', [('role', 403), ('active', 401), ('firm', 401)])
def test_access_revoked_during_verified_read_discards_original(workspace, original_source, monkeypatch, change, status):
    app, client, _ = workspace
    store, make = original_source
    identifier, *_ = make()
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
    response = client.get(f'/api/v1/public-sources/{identifier}/original-text?passage_id=p1')
    assert response.status_code == status
    assert 'untrusted.invalid' not in response.text


def test_preview_requires_curator_and_authenticated_session(workspace, original_source):
    app, client, _ = workspace
    store, make = original_source
    identifier, *_ = make()
    app.state.settings.public_source_dir = store.root
    route = f'/api/v1/public-sources/{identifier}/original-text?passage_id=p1'
    with app.state.store.session() as db:
        user = db.scalar(select(User).where(User.username == 'demo'))
        user.role = 'lawyer'
        db.commit()
    assert client.get(route).status_code == 403
    client.cookies.clear()
    assert client.get(route).status_code == 401


@pytest.mark.parametrize('query', ['passage_id=../secret', 'passage_id=p1&offset=-1', 'passage_id=p1&offset=1048577',
                                 'passage_id=p1&limit=12001', 'passage_id=p1&limit=0', 'passage_id=p1&offset=1.5'])
def test_api_rejects_unbounded_or_arbitrary_window_inputs(workspace, original_source, query):
    app, client, _ = workspace
    store, make = original_source
    identifier, *_ = make()
    app.state.settings.public_source_dir = store.root
    assert client.get(f'/api/v1/public-sources/{identifier}/original-text?{query}').status_code == 422


def test_unavailable_locator_and_missing_identity_errors_are_fixed(workspace, original_source):
    app, client, _ = workspace
    store, make = original_source
    identifier, *_ = make()
    app.state.settings.public_source_dir = store.root
    response = client.get(f'/api/v1/public-sources/{identifier}/original-text?passage_id=unknown')
    assert response.status_code == 422
    assert 'özgün dosyayı indirerek' in response.json()['detail']
    assert client.get('/api/v1/public-sources/not-a-package/original-text?passage_id=p1').status_code == 404
    assert client.get(f'/api/v1/public-sources/{"0" * 64}/original-text?passage_id=p1').status_code == 409
