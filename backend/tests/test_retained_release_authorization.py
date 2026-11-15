"""Synthetic retained-work authorization; no public-source approval or live write."""

import time
from contextlib import contextmanager

import pytest
from fastapi import Response
from test_workspace import research_product
from test_workspace import workspace as workspace_fixture

from app.db import Record

workspace = workspace_fixture


class SyntheticPermit:
    active = True
    info = {'release_id': 'a' * 64, 'serving_sha256': 'b' * 64, 'pointer': {'sequence': 1}}

    @contextmanager
    def guard(self):
        if not self.active:
            raise ValueError('PRIVATE-REVIEW-IDENTITY')
        yield self.info
        if not self.active:
            raise ValueError('PRIVATE-REVIEW-IDENTITY')


def pinned_product(workspace, monkeypatch):
    app, client, matter = workspace
    product = research_product(client, matter)
    permit = SyntheticPermit()
    monkeypatch.setattr(app.state.graph.release, 'current_guard', permit.guard)
    pin = {'status': 'verified', 'release_id': permit.info['release_id'],
           'serving_sha256': permit.info['serving_sha256'], 'activation_sequence': 1}
    with app.state.store.session() as session:
        record = session.get(Record, product['id'])
        data = app.state.store.decode(record)
        data['snapshots']['graph_release_pin'] = pin
        data['critical_gaps'] = []
        for claim in data['claims']:
            claim['review_status'] = 'approved'
        app.state.store.update(record, data)
        session.commit()
    return permit, product['id'], f'/api/v1/matters/{matter}/products/{product["id"]}'


def test_retained_approved_work_becomes_effectively_stale_without_rewriting(workspace, monkeypatch):
    app, client, matter = workspace
    permit, product_id, url = pinned_product(workspace, monkeypatch)
    approved = client.post(url + '/review', json={'decision': 'approve'})
    assert approved.status_code == 200 and approved.json()['status'] == 'reviewed'
    with app.state.store.session() as session:
        record = session.get(Record, product_id)
        before = (record.payload, record.revision)
    permit.active = False
    shown = client.get(url)
    assert shown.status_code == 200
    assert shown.json()['status'] == 'stale' and shown.json()['stored_status'] == 'reviewed'
    assert shown.json()['summary'] == approved.json()['summary']
    listed = client.get(f'/api/v1/matters/{matter}').json()['products']
    assert next(item for item in listed if item['id'] == product_id)['status'] == 'stale'
    assert client.post(url + '/review', json={'decision': 'reject'}).status_code == 409
    assert client.get(url + '/export').status_code == 409
    assert 'PRIVATE-REVIEW' not in shown.text
    with app.state.store.session() as session:
        record = session.get(Record, product_id)
        assert (record.payload, record.revision) == before


@pytest.mark.parametrize('mutation', ['revoke', 'change_sequence', 'change_release'])
def test_retained_export_requires_exact_current_authorization(workspace, monkeypatch, mutation):
    _, client, _ = workspace
    permit, _, url = pinned_product(workspace, monkeypatch)
    if mutation == 'revoke':
        permit.active = False
    elif mutation == 'change_sequence':
        permit.info = {**permit.info, 'pointer': {'sequence': 3}}
    else:
        permit.info = {**permit.info, 'release_id': 'c' * 64}
    assert client.get(url + '/export').status_code == 409


def test_revocation_during_export_render_does_not_deliver_file(workspace, monkeypatch):
    from app import main
    _, client, _ = workspace
    permit, _, url = pinned_product(workspace, monkeypatch)
    def render(*args):
        permit.active = False
        return Response(b'CONFIDENTIAL-EXPORT-BYTES')
    monkeypatch.setattr(main, 'render_export', render)
    response = client.get(url + '/export')
    assert response.status_code == 409
    assert 'CONFIDENTIAL-EXPORT' not in response.text and 'PRIVATE-REVIEW' not in response.text


def test_legacy_public_candidates_without_pin_cannot_be_reviewed_or_exported(workspace, monkeypatch):
    app, client, _ = workspace
    _, product_id, url = pinned_product(workspace, monkeypatch)
    with app.state.store.session() as session:
        record = session.get(Record, product_id)
        data = app.state.store.decode(record)
        data['snapshots'].pop('graph_release_pin')
        data['authority_candidates']['hits'] = [{'text': 'SYNTHETIC PUBLIC CANDIDATE'}]
        app.state.store.update(record, data)
        session.commit()
    assert client.get(url).json()['status'] == 'stale'
    assert client.post(url + '/review', json={'decision': 'approve'}).status_code == 409
    assert client.get(url + '/export').status_code == 409


@pytest.mark.parametrize('phase', ['guard_exit', 'finalize'])
def test_review_post_commit_failure_returns_truthful_receipt_and_persistent_stale_marker(workspace, monkeypatch, phase):
    from app import main
    app, client, _ = workspace
    permit, product_id, url = pinned_product(workspace, monkeypatch)
    observed = []
    def fail_after_commit():
        with app.state.store.session() as session:
            record = session.get(Record, product_id)
            data = app.state.store.decode(record)
            assert data['status'] == 'reviewed'
            assert data['authorization_revalidation'] == {'status': 'pending', 'operation': 'review'}
            observed.append(record.revision)
        raise ValueError('PRIVATE-POST-COMMIT-FAILURE')
    @contextmanager
    def failing_guard():
        yield permit.info
        fail_after_commit()
    if phase == 'guard_exit':
        monkeypatch.setattr(app.state.graph.release, 'current_guard', failing_guard)
    else:
        monkeypatch.setattr(main, 'finalize_product_authorization', lambda *args: fail_after_commit())
    response = client.post(url + '/review', json={'decision': 'approve'})
    assert response.status_code == 409 and len(observed) == 1
    body = response.json()
    assert body['outcome'] == 'committed_needs_revalidation' and body['needs_revalidation'] is True
    assert body['product_id'] == product_id and body['revision'] == observed[0]
    assert body['recorded_status'] == 'reviewed' and 'PRIVATE' not in response.text
    # A transient outage recovering must not erase the unresolved completion.
    monkeypatch.setattr(app.state.graph.release, 'current_guard', permit.guard)
    shown = client.get(url).json()
    assert shown['status'] == 'stale' and shown['stored_status'] == 'reviewed'
    assert shown['authorization_revalidation']['operation'] == 'review'
    assert client.post(url + '/review', json={'decision': 'approve'}).status_code == 409
    assert client.get(url + '/export').status_code == 409


@pytest.mark.parametrize('phase', ['guard_exit', 'finalize'])
def test_research_post_commit_failure_retains_saved_product_and_reports_completion_uncertainty(workspace, monkeypatch, phase):
    from app import research
    app, client, matter = workspace
    permit = SyntheticPermit()
    pin = {'status': 'verified', 'release_id': permit.info['release_id'],
           'serving_sha256': permit.info['serving_sha256'], 'activation_sequence': 1}
    monkeypatch.setattr(app.state.graph, 'release_pin', lambda: pin)
    observed = []
    def fail_after_commit():
        with app.state.store.session() as session:
            records = session.query(Record).filter_by(kind='product', matter_id=matter).all()
            assert len(records) == 1
            record = records[0]
            data = app.state.store.decode(record)
            assert data['authorization_revalidation'] == {'status': 'pending', 'operation': 'research'}
            observed.append(record.id)
        raise ValueError('PRIVATE-POST-COMMIT-FAILURE')
    @contextmanager
    def failing_guard():
        yield permit.info
        fail_after_commit()
    monkeypatch.setattr(app.state.graph.release, 'current_guard', failing_guard if phase == 'guard_exit' else permit.guard)
    if phase == 'finalize':
        monkeypatch.setattr(research, 'finalize_product_authorization', lambda *args: fail_after_commit())
    response = client.post(f'/api/v1/matters/{matter}/research', json={'question': 'Sentetik test araştırması'})
    assert response.status_code == 202
    run_url = f'/api/v1/matters/{matter}/research/{response.json()["id"]}'
    for _ in range(150):
        state = client.get(run_url).json()
        if state.get('outcome') == 'committed_needs_revalidation' or state['status'] == 'failed':
            break
        time.sleep(0.02)
    assert state['status'] == 'completed' and state['outcome'] == 'committed_needs_revalidation'
    assert state['needs_revalidation'] is True and state['product_id'] == observed[0]
    assert 'error' not in state and 'yayımlanmadı' not in state.get('warning', '')
    assert 'PRIVATE' not in str(state)
    monkeypatch.setattr(app.state.graph.release, 'current_guard', permit.guard)
    product_url = f'/api/v1/matters/{matter}/products/{state["product_id"]}'
    saved = client.get(product_url).json()
    assert saved['status'] == 'stale' and saved['authorization_revalidation']['operation'] == 'research'
    assert client.get(product_url + '/export').status_code == 409
