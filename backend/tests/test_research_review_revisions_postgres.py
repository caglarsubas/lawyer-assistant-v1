"""Exercise the served research review API against disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_snapshot_set_postgres import postgres_database as database_fixture

from app.config import Settings
from app.db import Audit, Record, User
from app.runtime import create_app


@pytest.fixture
def postgres_database():
    yield from database_fixture.__wrapped__()


@pytest.fixture
def workspace(postgres_database, tmp_path):
    app = create_app(Settings.model_construct(
        demo_mode=True, cookie_secure=False, data_dir=tmp_path,
        public_source_dir=tmp_path / 'public-only',
        database_url=postgres_database.render_as_string(hide_password=False)))
    with TestClient(app) as client:
        login = client.post('/api/v1/auth/login', json={'username': 'demo', 'password': 'demo-local-only'})
        assert login.status_code == 200
        client.headers['X-CSRF-Token'] = login.json()['csrf_token']
        yield app, client, client.get('/api/v1/matters').json()[0]['id']


def test_competing_research_claim_reviews_preserve_winning_decision(workspace, monkeypatch):
    app, client, matter = workspace
    store = app.state.store
    original = {'version': 3, 'status': 'needs_review', 'snapshots': {'documents': {'doc': 2}},
                'evidence': [{'id': 'passage', 'text': 'SYNTHETIC exact passage', 'document_revision': 2}],
                'claims': [{'id': 'claim', 'text': 'SYNTHETIC claim', 'evidence_ids': ['passage'],
                            'review_status': 'pending'}]}
    with store.session() as session:
        actor = session.scalar(select(User).where(User.username == 'demo'))
        record = store.add(session, 'product', actor, original, matter)
        session.commit()
        product_id, revision = record.id, record.revision
    url = f'/api/v1/matters/{matter}/products/{product_id}'
    edit = {'expected_revision': revision, 'claim_id': 'claim', 'decision': 'approve'}
    unauthorized = client.post(url.replace(f'/matters/{matter}/', '/matters/different-matter/') + '/review', json=edit)
    assert unauthorized.status_code == 404
    assert 'current_revision' not in unauthorized.json()
    for invalid in ({}, {'expected_revision': True}, {'expected_revision': str(revision)}, {'expected_revision': 0}):
        invalid_body = {key: value for key, value in edit.items() if key != 'expected_revision'} | invalid
        assert client.post(url + '/review', json=invalid_body).status_code == 422

    barrier = Barrier(2)
    update = store.update

    def pause_before_write(record, body):
        if record.id == product_id:
            assert record.revision == revision
            barrier.wait(timeout=5)
        update(record, body)

    peer = TestClient(app)  # The workspace fixture owns the application lifespan.
    try:
        login = peer.post('/api/v1/auth/login', json={'username': 'demo', 'password': 'demo-local-only'})
        assert login.status_code == 200
        peer.headers['X-CSRF-Token'] = login.json()['csrf_token']
        assert peer.get(url).json()['revision'] == client.get(url).json()['revision'] == revision
        with monkeypatch.context() as concurrent, ThreadPoolExecutor(max_workers=2) as pool:
            concurrent.setattr(store, 'update', pause_before_write)
            first = pool.submit(client.post, url + '/review', json={**edit, 'note': 'SYNTHETIC first review'})
            second = pool.submit(peer.post, url + '/review', json={**edit, 'decision': 'reject', 'note': 'SYNTHETIC second review'})
            winner, loser = sorted((first.result(timeout=10), second.result(timeout=10)), key=lambda r: r.status_code)
        assert (winner.status_code, loser.status_code) == (200, 409)
        conflict = loser.json()
        assert set(conflict) == {'detail', 'outcome', 'product_id', 'current_revision'}
        saved = winner.json()
        assert conflict['outcome'] == 'revision_conflict' and conflict['product_id'] == product_id
        assert conflict['current_revision'] == saved['revision'] == revision + 1
        assert client.get(url).json() == saved

        stale = peer.post(url + '/review', json={**edit, 'note': 'SYNTHETIC stale retry'})
        assert stale.status_code == 409 and stale.json() == conflict
        with store.session() as session:
            events = session.scalars(select(Audit).filter_by(action='product_reviewed', object_id=product_id)).all()
            assert len(events) == 1

        reread = peer.get(url).json()
        renewed = peer.post(url + '/review', json={**edit, 'expected_revision': reread['revision'],
                                                  'note': 'SYNTHETIC fresh review'})
        assert renewed.status_code == 200
        current = renewed.json()
        previous = saved['claims'][0]
        assert current['claims'][0]['review_note'] == 'SYNTHETIC fresh review'
        assert current['claims'][0]['review_history'] == [{
            'product_revision': saved['revision'],
            **{key: previous[key] for key in ('review_status', 'review_note', 'reviewed_by', 'reviewed_at')},
        }]
        for key in ('version', 'snapshots', 'evidence'):
            assert current[key] == saved[key] == original[key]
        assert current['claims'][0]['evidence_ids'] == original['claims'][0]['evidence_ids']
        with store.session() as session:
            encrypted = session.get(Record, product_id).payload
            assert previous['review_note'] not in encrypted and 'SYNTHETIC fresh review' not in encrypted
    finally:
        peer.close()


def test_revision_guard_preserves_committed_revalidation_receipt(workspace, monkeypatch):
    app, client, matter = workspace
    store = app.state.store
    pin = {'status': 'verified', 'release_id': 'a' * 64, 'serving_sha256': 'b' * 64, 'activation_sequence': 1}
    with store.session() as session:
        actor = session.scalar(select(User).where(User.username == 'demo'))
        product = store.add(session, 'product', actor, {
            'version': 3, 'status': 'needs_review', 'snapshots': {'graph_release_pin': pin},
            'claims': [{'id': 'claim', 'review_status': 'approved'}],
        }, matter)
        session.commit()
        ident, revision = product.id, product.revision

    @contextmanager
    def guard():
        yield {'release_id': pin['release_id'], 'serving_sha256': pin['serving_sha256'], 'pointer': {'sequence': 1}}
        raise ValueError('synthetic post-commit guard failure')

    monkeypatch.setattr(app.state.graph.release, 'current_guard', guard)
    url = f'/api/v1/matters/{matter}/products/{ident}'
    review = {'expected_revision': revision, 'decision': 'approve'}
    response = client.post(url + '/review', json=review)
    assert response.status_code == 409 and response.json()['outcome'] == 'committed_needs_revalidation'
    saved = response.json()
    assert saved['product_id'] == ident and saved['revision'] == revision + 1
    assert saved['needs_revalidation'] is True
    shown = client.get(url).json()
    assert (shown['status'], shown['stored_status']) == ('stale', 'reviewed')
    assert shown['revision'] == saved['revision']
    replay = client.post(url + '/review', json=review)
    assert replay.status_code == 409 and replay.json()['outcome'] == 'revision_conflict'
    with store.session() as session:
        events = session.scalars(select(Audit).filter_by(action='product_reviewed', object_id=ident)).all()
        assert len(events) == 1
