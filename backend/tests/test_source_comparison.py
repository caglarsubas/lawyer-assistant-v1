"""Synthetic mechanical comparisons only; no actual source or legal judgments."""

import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import select
from test_public_sources import source as source_fixture
from test_source_reviews import counts
from test_workspace import workspace as workspace_fixture

from app.db import User
from app.public_sources import PublicSourceStore
from app.source_comparison import compare_sources, literal_difference

source = source_fixture
workspace = workspace_fixture


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def pair(source, workspace):
    store, args, metadata, locators = source
    app, client, _ = workspace
    left = store.import_package(**args)['id']

    def make(text='Türkçe hukuk: ıİğĞşŞçÇöÖüÜ.\r\nİkinci satır ⚖️.😀İ\u0120', raw=b'<html>synthetic other original</html>'):
        Path(args['raw_path']).write_bytes(raw)
        Path(args['text_path']).write_bytes(text.encode())
        metadata.update(source_version_id='other-version', raw_media_type='text/html')
        Path(args['metadata_path']).write_text(json.dumps(metadata))
        locators.update(raw_sha256=sha(raw), text_sha256=sha(text.encode()), passages=[
            {'id': 'other_p1', 'start': 0, 'end': len(text), 'text_sha256': sha(text.encode()), 'locator': 'synthetic HTML block 1'},
        ])
        Path(args['locators_path']).write_text(json.dumps(locators))
        return store.import_package(**args)['id']

    right = make()
    app.state.settings.public_source_dir = store.root
    params = {'other_source_id': right, 'passage_id': 'p1', 'other_passage_id': 'other_p1'}
    return app, client, store, left, right, params, make


def get(pair, **changes):
    _, client, _, left, _, params, _ = pair
    return client.get(f'/api/v1/public-sources/{left}/comparison', params={**params, **changes})


def receipt(response):
    assert response.status_code == 200, response.text
    data = response.json()
    assert sha(data['evidence_json'].encode()) == data['evidence_sha256']
    return json.loads(data['evidence_json'])


def test_reproducible_exact_unicode_evidence_no_reviews_no_provider_or_normalization(pair, monkeypatch):
    app, _, store, left, right, _, _ = pair
    def forbidden(*args, **kwargs):
        raise AssertionError('Comparison must not parse originals or access any network/provider')
    monkeypatch.setattr('pypdf.PdfReader', forbidden)
    monkeypatch.setattr('httpx.HTTPTransport.handle_request', forbidden)
    before = {side: {p.name: p.read_bytes() for p in (store.root / side).iterdir()} for side in (left, right)}
    response = get(pair)
    body = receipt(response)
    assert get(pair).content == response.content  # No inferred time or reviewer identity.
    assert body['left']['text'] == store.verified_package(left).text
    assert '\r\n' in body['right']['text'] and '😀İ\u0120' in body['right']['text']
    assert not body['extracted_text_equal'] and not body['raw_bytes_equal']
    assert body['legal_identity_status'] == body['legal_version_status'] == 'unresolved'
    for flag in ('independent_originals_verified', 'current_law_verified', 'human_review_recorded'):
        assert body[flag] is False
    assert body['normalization'] == 'none'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['content-security-policy'] == "sandbox; default-src 'none'; frame-ancestors 'none'"
    assert counts(app) == (0, 0)
    assert before == {side: {p.name: p.read_bytes() for p in (store.root / side).iterdir()} for side in (left, right)}
    for side in (left, right):
        state = app.state.store  # Reads create no firm review or graph record.
        assert state is not None and store.detail(side)['publication_status'] == 'staged'


def test_same_text_is_not_same_original_or_reviewed_identity(pair):
    _, _, store, left, _, _, make = pair
    right = make(store.verified_package(left).text)
    body = receipt(get(pair, other_source_id=right))
    assert body['extracted_text_equal'] and body['difference']['equal']
    assert not body['raw_bytes_equal'] and not body['independent_originals_verified']
    assert body['difference']['left_range'][0] == body['difference']['left_range'][1]


def test_same_original_bytes_with_changed_transcription_remains_unresolved(pair):
    _, _, store, left, _, _, make = pair
    right = make(raw=store.verified_package(left).raw)
    body = receipt(get(pair, other_source_id=right))
    assert body['raw_bytes_equal'] and not body['extracted_text_equal']
    assert body['legal_version_status'] == 'unresolved'


def test_window_scope_unicode_offsets_and_digest_change_without_inventing_alignment(pair):
    first = get(pair, offset=1, other_offset=2, limit=4)
    body = receipt(first)
    assert body['left']['text'] == 'ürkç' and body['right']['text'] == 'rkçe'
    assert body['left']['next_offset'] == 5 and body['right']['next_offset'] == 6
    assert body['difference']['scope'] == 'selected_windows_only'
    assert get(pair, offset=2, other_offset=2, limit=4).json()['evidence_sha256'] != first.json()['evidence_sha256']
    assert body['left']['artifacts']['raw.bin']['sha256'] != body['right']['artifacts']['raw.bin']['sha256']


def test_large_passage_is_bounded_at_default_2000_code_points(pair):
    _, _, _, _, _, _, make = pair
    right = make('😀' * 5000)
    body = receipt(get(pair, other_source_id=right, other_offset=1))
    assert len(body['right']['text']) == 2000 and body['right']['next_offset'] == 2001
    assert body['right']['end'] == 2001


@pytest.mark.parametrize('left,right,edges', [
    ('', '', (0, 0, [0, 0], [0, 0])), ('a', '', (0, 0, [0, 1], [0, 0])),
    ('😀İXş', '😀İYş', (2, 1, [2, 3], [2, 3])),
    ('İ', 'I\u0307', (0, 0, [0, 1], [0, 2])),
    ('aaa', 'aaaa', (3, 0, [3, 3], [3, 4])),
    ('a\r\nb', 'a\nb', (1, 2, [1, 2], [1, 1])),
])
def test_common_edges_preserve_code_points_and_do_not_normalize(left, right, edges):
    value = literal_difference(left, right)
    assert (value['common_prefix_code_points'], value['common_suffix_code_points'], value['left_range'], value['right_range']) == edges
    assert value['equal'] == (left == right)


@pytest.mark.parametrize('changes', [
    {'other_source_id': '../private'}, {'other_source_id': 'https://external.example'},
    {'passage_id': 'missing'}, {'other_passage_id': 'p1'}, {'passage_id': '../p1'},
    {'offset': -1}, {'offset': 20001}, {'offset': 20000}, {'offset': 'one'},
    {'other_offset': -1}, {'other_offset': 20000}, {'limit': 0}, {'limit': 2001}, {'limit': 'bad'},
])
def test_invalid_unknown_or_overbudget_pair_never_returns_partial_text(pair, changes):
    response = get(pair, **changes)
    assert response.status_code == 422
    assert 'evidence_json' not in response.text


def test_same_package_and_missing_package_rejected(pair):
    _, client, _, left, _, params, _ = pair
    assert get(pair, other_source_id=left).status_code == 422
    assert get(pair, other_source_id='f' * 64).status_code == 409
    assert client.get('/api/v1/public-sources/not-valid/comparison', params=params).status_code == 404


@pytest.mark.parametrize('side', [3, 4])
@pytest.mark.parametrize('artifact', ['raw.bin', 'text.txt', 'locators.json', 'source.json', 'manifest.json'])
def test_complete_integrity_for_both_sources(pair, side, artifact):
    _, _, store, _, _, _, _ = pair
    path = store.root / pair[side] / artifact
    path.chmod(0o600)  # Only this synthetic test's disposable package.
    path.write_bytes(b'changed')
    response = get(pair)
    assert response.status_code == 409 and 'evidence_json' not in response.text


@pytest.mark.parametrize('after_read', [1, 2])
@pytest.mark.parametrize('change', ['inactive', 'lawyer', 'other_firm'])
def test_revocation_rechecked_between_sources_and_before_response(pair, monkeypatch, after_read, change):
    app, _, _, _, _, _, _ = pair
    original = PublicSourceStore.verified_package
    reads = []
    def read(self, identifier):
        result = original(self, identifier)
        reads.append(identifier)
        if len(reads) == after_read:
            with app.state.store.session() as session:
                user = session.scalar(select(User).where(User.username == 'demo'))
                if change == 'inactive':
                    user.active = False
                elif change == 'lawyer':
                    user.role = 'lawyer'
                else:
                    user.firm_id = 'foreign-firm'
                session.commit()
        return result
    monkeypatch.setattr(PublicSourceStore, 'verified_package', read)
    response = get(pair)
    assert response.status_code in (401, 403) and 'evidence_json' not in response.text
    assert len(reads) == after_read


def test_no_role_or_action_permission_cannot_probe_sources(pair):
    app, client, _, _, _, _, _ = pair
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        user.role = 'lawyer'
        session.commit()
    assert get(pair).status_code == 403
    client.cookies.clear()
    assert get(pair).status_code == 401


def test_pure_comparator_rejects_boolean_or_non_integer_offsets(pair):
    _, _, store, left, right, _, _ = pair
    from app.source_comparison import SourceComparisonUnavailable
    for value in (True, 1.5, '1'):
        with pytest.raises(SourceComparisonUnavailable):
            compare_sources(store.verified_package(left), store.verified_package(right), passage_id='p1', other_passage_id='other_p1', offset=value)
