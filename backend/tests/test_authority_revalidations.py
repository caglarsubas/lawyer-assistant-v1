"""Invented sources and mocked inference; binding freshness is not legal approval."""
import copy
import io
from contextlib import contextmanager
from uuid import uuid4

import pytest
from docx import Document
from fastapi import HTTPException
from test_analysis_authorities import mutate, payload
from test_analysis_suggestions import adopt, finished
from test_authority_proposals import complete
from test_authority_proposals import workbench as workbench_fixture
from test_firm_admin import PASSWORD, login

from app import authority_proposals as proposals
from app import authority_revalidations as renewals
from app.auth import hash_password
from app.db import Membership, Record, User

workbench = workbench_fixture


def ready(workbench, monkeypatch, *, stale=True):
    app, client, base, *_ = workbench
    endpoint, _, analysis, review, permit, reviews, reader, job = complete(workbench, monkeypatch)
    adopted = adopt(client, endpoint, analysis, job).json()
    # Genuine account loss for the original reviewer, followed by another lawyer.
    with app.state.store.session() as session:
        peer = User(username='synthetic-renewal-lawyer', name='SYNTHETIC second lawyer', firm_id='demo-firm',
                    role='lawyer', password_hash=hash_password(PASSWORD))
        session.add(peer)
        session.flush()
        session.add(Membership(matter_id=base.split('/')[-1], user_id=peer.id))
        if stale:
            session.delete(session.get(Membership, (base.split('/')[-1], review['reviewer_id'])))
        session.commit()
    login(client, 'synthetic-renewal-lawyer', PASSWORD)
    path = base + '/analyses/' + analysis['id'] + '/lineage-reviews'
    return path, adopted, permit, reader, endpoint


def request(client, path):
    response = client.get(path + '/preview')
    assert response.status_code == 200, response.text
    preview = response.json()
    value = preview['preview']
    body = {'version_id': value['version_id'], 'expected_revision': value['expected_revision'],
        'expected_preview_sha256': preview['preview_sha256'], 'request_id': uuid4().hex,
        'change_note': 'SYNTHETIC explicit retained-binding review', 'decision': 'retain_for_review',
        'renewals': [{'dependency_sha256': entry['dependency_sha256'],
            'note': 'SYNTHETIC retained for review, unresolved merits', 'review_seconds': 30,
            'sources': [{**{key: source['selection'][key] for key in ('assertion_id', 'passage_id', 'authority_id')},
                'target_ids': ['conclusion'], 'observations': [{'dimension': dimension, 'outcome': 'unresolved',
                    'note': 'SYNTHETIC still requires legal examination'} for dimension in value['dimensions']]}
                for source in entry['manifest']['sources']]} for entry in value['entries']]}
    return body, preview


def saved(client, path):
    body, _ = request(client, path)
    result = client.post(path, json=body)
    assert result.status_code == 201, result.text
    return result.json(), body


def test_genuine_reviewer_loss_explicit_renewal_keeps_all_original_provenance(workbench, monkeypatch):
    app, client, base, *_ = workbench
    path, original, *_ = ready(workbench, monkeypatch)
    old_bytes = payload(app, original['latest_version_id'])
    assert client.get(base + '/analyses').json()[0]['status'] == 'stale'
    assert client.get(base + '/analyses/' + original['id'] + '/export').status_code == 409
    result, body = saved(client, path)
    new = result['analysis']
    assert new['status'] == 'needs_review' and new['freshness']['status'] == 'current'
    assert new['authority_dependencies'] == original['authority_dependencies']
    assert new['authority_contributions'] == original['authority_contributions']
    assert new['ai_assistance'] == original['ai_assistance']
    assert new['review']['effective_state'] == 'unreviewed'
    assert payload(app, original['latest_version_id']) == old_bytes
    history = client.get(path).json()
    assert history[-1]['snapshot']['renewals'] == body['renewals']
    assert history[-1]['snapshot']['legal_approval'] == 'not_granted'
    assert history[-1]['snapshot']['qualification_granted'] is False
    export = client.get(base + '/analyses/' + original['id'] + '/export')
    assert export.status_code == 200, export.text
    text = '\n'.join(p.text for p in Document(io.BytesIO(export.content)).paragraphs)
    assert original['authority_contributions'][0]['job_id'] in text and result['id'] in text
    assert 'SYNTHETIC still requires legal examination' in text
    replay = client.post(path, json=body)
    assert replay.status_code == 201 and replay.json()['replayed']
    assert replay.json()['version_id'] == result['version_id']
    assert client.post(path, json={**body, 'change_note': 'SYNTHETIC changed nonce payload'}).status_code == 409
    assert client.get(base + '/analyses/' + original['id'] + '/export?version_id=' + original['latest_version_id']).status_code == 409


@pytest.mark.parametrize('change', ['rights', 'source', 'private', 'recipe', 'archive'])
def test_renewal_cannot_override_changed_or_denied_evidence(workbench, monkeypatch, change):
    app, client, base, _, fact, *_ = workbench
    path, original, permit, reader, _ = ready(workbench, monkeypatch)
    body, _ = request(client, path)
    if change == 'rights':
        permit.active = False
    elif change == 'source':
        reader.info['pointer']['sequence'] += 1
    elif change == 'private':
        mutate(app, fact['id'], lambda value: value.update(text='SYNTHETIC changed private fact'))
    elif change == 'recipe':
        monkeypatch.setattr(renewals.findings, 'RECIPE', 'SYNTHETIC unsupported new recipe')
    else:
        mutate(app, base.split('/')[-1], lambda value: value.update(status='archived'))
    assert client.get(path + '/preview').status_code == 409
    assert client.post(path, json=body).status_code == 409
    if change in {'rights', 'source'}:
        assert client.get(path).status_code == 409
    assert payload(app, original['latest_version_id'])


@pytest.mark.parametrize('bad', ['missing_source', 'missing_dimension', 'target', 'unbound_dependency', 'preview', 'version', 'decision', 'extra'])
def test_exact_inputs_and_complete_observations_required(workbench, monkeypatch, bad):
    _, client, *_ = workbench
    path, *_ = ready(workbench, monkeypatch)
    body, _ = request(client, path)
    if bad == 'missing_source':
        body['renewals'][0]['sources'].pop()
    elif bad == 'missing_dimension':
        body['renewals'][0]['sources'][0]['observations'].pop()
    elif bad == 'target':
        body['renewals'][0]['sources'][0]['target_ids'] = ['no-such-draft-target']
    elif bad == 'unbound_dependency':
        body['renewals'][0]['dependency_sha256'] = '0' * 64
    elif bad == 'preview':
        body['expected_preview_sha256'] = '0' * 64
    elif bad == 'version':
        body['version_id'] = 'different-version'
    elif bad == 'decision':
        body['decision'] = 'approved'
    else:
        body['legal_approval'] = 'granted'
    assert client.post(path, json=body).status_code in {409, 422}
    assert client.get(path).json() == []


def test_manual_and_model_edits_require_new_explicit_review(workbench, monkeypatch):
    app, client, base, manual, *_ = workbench
    path, original, _, _, endpoint = ready(workbench, monkeypatch)
    first, _ = saved(client, path)
    current = first['analysis']
    form = copy.deepcopy(manual)
    form['conclusion']['text'] = 'SYNTHETIC human revised argument'
    form.update(expected_revision=current['revision'], change_note='SYNTHETIC substantive change')
    response = client.post(base + '/analyses/' + original['id'] + '/versions', json=form)
    assert response.status_code == 201, response.text
    assert 'authority_revalidated_analysis_changed' in response.json()['freshness']['reasons']
    second, _ = saved(client, path)
    assert len(second['analysis']['authority_revalidations']) == 2
    monkeypatch.setattr(app.state.provider, 'suggest_analysis', lambda *_a, **_k: '{"conclusion_update":{"text":"SYNTHETIC later model argument","next_step":"SYNTHETIC review","uncertainty":[]}}')
    source = second['analysis']
    start = client.post(endpoint, json={'expected_revision': source['revision'], 'version_id': source['latest_version_id'], 'request_id': uuid4().hex})
    assert start.status_code == 202, start.text
    job = finished(client, endpoint, start.json()['id'])
    adopted = adopt(client, endpoint, source, job)
    assert adopted.status_code == 201, adopted.text
    assert adopted.json()['status'] == 'stale'
    assert adopted.json()['authority_revalidations'] == source['authority_revalidations']
    assert adopted.json()['authority_contributions'] == original['authority_contributions']
    assert client.get(base + '/analyses/' + original['id'] + '/export').status_code == 409


def test_late_guard_failure_retains_pending_version_without_retry_finalization(workbench, monkeypatch):
    app, client, base, *_ = workbench
    path, original, *_ = ready(workbench, monkeypatch)
    body, _ = request(client, path)
    guard = proposals.dependency_guard
    failed = False

    @contextmanager
    def late(*args):
        nonlocal failed
        with guard(*args) as result:
            yield result
            # The save commit has happened; earlier preview guard exits are safe.
            with app.state.store.session() as session:
                row = session.get(Record, original['id'])
                changed = app.state.store.decode(row)['latest_version_id'] != original['latest_version_id']
            if changed and not failed:
                failed = True
                raise HTTPException(409, 'SYNTHETIC late source admission rejection')
    monkeypatch.setattr(proposals, 'dependency_guard', late)
    result = client.post(path, json=body)
    assert result.status_code == 409 and result.json()['needs_revalidation']
    monkeypatch.setattr(proposals, 'dependency_guard', guard)
    assert client.get(base + '/analyses').status_code == 409
    assert client.get(path).status_code == 409
    assert client.post(path, json=body).status_code == 409


@pytest.mark.parametrize('damage', ['snapshot', 'admission', 'overlay_strip', 'overlay_seal', 'version_link'])
def test_corrupt_or_pending_lineage_is_withheld(workbench, monkeypatch, damage):
    app, client, base, *_ = workbench
    path, original, *_ = ready(workbench, monkeypatch)
    result, _ = saved(client, path)
    record = result['analysis']
    with app.state.store.session() as session:
        row = session.get(Record, result['id'])
        value = app.state.store.decode(row)
        proof_id = value['admission_id']
    if damage == 'snapshot':
        mutate(app, result['id'], lambda data: data['snapshot'].update(review_seconds=999))
    elif damage == 'admission':
        mutate(app, proof_id, lambda data: data.update(completed=False))
    elif damage == 'version_link':
        mutate(app, result['id'], lambda data: data.update(version_id=original['latest_version_id']))
    elif damage == 'overlay_strip':
        mutate(app, original['id'], lambda data: data.update(authority_revalidations=[]))
    else:
        mutate(app, original['id'], lambda data: data['authority_revalidations'][0].update(sha256='0' * 64))
    assert client.get(base + '/analyses').status_code == 409
    assert client.get(path).status_code == 409
    if damage not in {'overlay_strip', 'overlay_seal'}:
        assert client.get(base + '/analyses/' + original['id'] + '/export?version_id=' + record['latest_version_id']).status_code == 409


def test_renewal_reviewer_and_head_changes_stale_not_rewrite_records(workbench, monkeypatch):
    app, client, base, *_ = workbench
    path, original, *_ = ready(workbench, monkeypatch, stale=False)
    result, _ = saved(client, path)
    frozen = payload(app, result['id'])
    head = renewals.findings._head
    monkeypatch.setattr(renewals.findings, '_head', lambda *args: {**head(*args), 'latest_review_id': 'SYNTHETIC later head'})
    current = client.get(base + '/analyses').json()[0]
    assert current['status'] == 'stale' and 'authority_revalidation_review_changed' in current['freshness']['reasons']
    monkeypatch.setattr(renewals.findings, '_head', head)
    login(client)
    with app.state.store.session() as session:
        data = app.state.store.decode(session.get(Record, result['id']))
        reviewer = session.get(User, data['snapshot']['reviewer_id'])
        session.delete(session.get(Membership, (base.split('/')[-1], reviewer.id)))
        session.commit()
    assert 'authority_revalidation_reviewer_access_changed' in client.get(base + '/analyses').json()[0]['freshness']['reasons']
    assert client.get(base + '/analyses/' + original['id'] + '/export').status_code == 409
    saved(client, path)
    assert payload(app, result['id']) == frozen
    assert client.get(base + '/analyses/' + original['id'] + '/export').status_code == 200


def test_retained_renewal_cannot_clear_stale_new_proposal_input(workbench, monkeypatch):
    app, client, base, *_ = workbench
    path, *_ = ready(workbench, monkeypatch)
    result, _ = saved(client, path)
    source = result['analysis']
    incoming = {**source['authority_dependencies'][0], 'review_id': 'SYNTHETIC newly selected review'}
    guard = proposals.dependency_guard

    @contextmanager
    def distinguish(*args):
        if args[-1] == incoming:
            yield ['authority_reviewer_access_changed']
        else:
            with guard(*args) as reasons:
                yield reasons
    monkeypatch.setattr(proposals, 'dependency_guard', distinguish)
    with app.state.store.session() as session:
        user = session.get(User, result['analysis']['authored_by'])
        with proposals.scope(app, session, base.split('/')[-1], user,
                {'source_content': source, 'authority_feedback': {'dependency': incoming}}) as reasons:
            assert reasons == ['authority_reviewer_access_changed']
