"""Confidential metadata observations; public evidence always stays guarded."""

import copy
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from test_analysis_authorities import mutate
from test_analysis_comparisons import login
from test_authority_adjudications import reviewer
from test_source_analysis_reviews import freeze, record, review_request, reviewed, setup
from test_source_analysis_reviews import workbench as workbench_fixture
from test_source_context_renewals import renewal_spec

from app import source_analysis_reviews as reviews
from app import source_review_readiness as readiness
from app.db import EmployeeRole, Membership, Record, User, WorkspaceCustomerLink

workbench = workbench_fixture


def page(client, endpoint, **params):
    response = client.get(endpoint + '/readiness', params=params)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['legal_readiness'] == 'not_established' and not value['qualification_granted']
    assert value['coverage']['total_count'] is None
    for item in value['items']:
        assert item['source_verification'] == 'not_checked'
        assert item['legal_readiness'] == 'not_established'
    for secret in ['TEST ONLY 📄', 'PRIVATE SOURCE NOTE', 'PRIVATE REVIEW NOTE', 'target_snapshots', 'analysis_content', 'source_candidates']:
        assert secret not in response.text
    return value


def no_public_reads(monkeypatch, reader):
    monkeypatch.setattr(reader, 'current_guard', lambda *_a, **_k: pytest.fail('Queue cannot run or reuse source guards'))
    monkeypatch.setattr('app.source_corpus._project', lambda *_a, **_k: pytest.fail('Queue cannot read source evidence'))


def test_historical_positive_never_means_ready_or_checked_and_withdrawal_requires_explicit_inspection(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, _, _, reader, permit, context, _, *_ = reviewed(workbench, monkeypatch)
    permit.active = False
    item = page(client, endpoint)['items'][0]
    assert item['id'] == context['id']
    assert item['historical_review']['state'] == 'reviewed_conditional'
    assert item['state'] == 'inspection_required' and item['private_observation']['state'] == 'unchanged'
    assert client.get(endpoint + '/' + context['id']).json()['manifest'] is None
    assert client.get(endpoint + '/' + context['id'] + '/export').status_code == 409
    no_public_reads(monkeypatch, reader)
    assert page(client, endpoint, bucket='action_required')['items'] == []
    assert page(client, endpoint)['items'][0] == item


def test_priority_and_window_counts_are_not_a_global_inventory(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, _, reader, _ = setup(workbench, monkeypatch)
    unreviewed, _ = freeze(client, endpoint, spec)
    needs_change, _ = freeze(client, endpoint, spec)
    reviewer(workbench)
    path, body = review_request(client, endpoint, needs_change['id'], decision='changes_requested')
    record(client, path, body)
    no_public_reads(monkeypatch, reader)
    value = page(client, endpoint, window=1)
    assert len(value['items']) == value['coverage']['scanned_count'] == 1
    assert value['coverage']['has_more'] and value['coverage']['next_offset'] == 1
    second = page(client, endpoint, window=1, offset=1)
    assert not second['coverage']['has_more'] and second['coverage']['next_offset'] is None
    all_items = page(client, endpoint)['items']
    assert [item['state'] for item in all_items] == ['changes_requested', 'awaiting_review']
    assert {item['id'] for item in all_items} == {unreviewed['id'], needs_change['id']}
    # No writes/admission repair occur in observation.
    with app.state.store.session() as session:
        assert len(session.scalars(select(Record).where(Record.kind == reviews.REVIEW)).all()) == 1


@pytest.mark.parametrize('change,reason', [
    ('fact', 'private_dependency_changed'), ('missing_fact', 'private_dependency_unavailable'),
    ('product', 'research_basis_changed'), ('missing_product', 'research_basis_unavailable'),
    ('pending_context', 'context_admission_pending'), ('pending_review', 'review_admission_pending'),
    ('reviewer_access', 'reviewer_access_changed'), ('version', 'analysis_version_changed'),
])
def test_confirmed_dependency_changes_without_old_quotes_or_notes(workbench, monkeypatch, change, reason):
    app, client, base, body, fact, *_ = workbench
    endpoint, spec, analysis, reader, _, context, saved, *_ = reviewed(workbench, monkeypatch)
    if change == 'fact':
        mutate(app, fact['id'], lambda value: value.update(text='PRIVATE UPDATED CANARY'))
    elif change == 'product':
        mutate(app, spec['product_id'], lambda value: value.update(title='PRIVATE UPDATED CANARY'))
    elif change in {'missing_fact', 'missing_product'}:
        with app.state.store.session() as session:
            session.delete(session.get(Record, fact['id'] if change == 'missing_fact' else spec['product_id']))
            session.commit()
    elif change.startswith('pending_'):
        ident = context['id'] if change == 'pending_context' else saved['review']['id']
        mutate(app, reviews._id('saa-', ident), lambda value: value.update(guard_completed=False))
    elif change == 'reviewer_access':
        with app.state.store.session() as session:
            user = session.scalar(select(User).where(User.username == 'reviewer'))
            session.delete(session.get(Membership, (base.split('/')[-1], user.id)))
            session.commit()
        login(client)
    else:
        login(client)
        changed = copy.deepcopy(body)
        changed['rules'][0]['text'] = 'PRIVATE UPDATED CANARY'
        response = client.post(base + '/analyses/' + analysis['id'] + '/versions',
            json={**changed, 'expected_revision': analysis['revision'], 'change_note': 'TEST ONLY exact new private version'})
        assert response.status_code == 201, response.text
    no_public_reads(monkeypatch, reader)
    item = page(client, endpoint)['items'][0]
    assert reason in item['private_observation']['reasons']
    assert item['state'] == ('pending' if change.startswith('pending_') else 'needs_renewal')
    assert item['historical_review']['state'] == 'reviewed_conditional'
    assert 'PRIVATE UPDATED CANARY' not in str(item)


def test_parent_review_change_is_observed_without_inheriting_or_rewriting_old_decisions(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, spec, _, reader, _ = setup(workbench, monkeypatch)
    parent, _ = freeze(client, endpoint, spec)
    replacement, _ = renewal_spec(client, endpoint, spec, parent['id'])
    child, _ = freeze(client, endpoint, replacement)
    reviewer(workbench)
    path, body = review_request(client, endpoint, parent['id'])
    record(client, path, body)
    no_public_reads(monkeypatch, reader)
    items = {item['id']: item for item in page(client, endpoint)['items']}
    assert items[child['id']]['state'] == 'needs_renewal'
    assert 'parent_basis_changed_or_unavailable' in items[child['id']]['private_observation']['reasons']
    assert items[child['id']]['historical_review']['state'] == 'unreviewed'
    assert items[parent['id']]['historical_review']['state'] == 'reviewed_conditional'


@pytest.mark.parametrize('loss', ['membership', 'role', 'tag_only', 'foreign'])
def test_scope_loss_is_denied_before_decryption_or_counts(workbench, monkeypatch, loss):
    app, client, base, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    freeze(client, endpoint, spec)
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        if loss in {'membership', 'tag_only'}:
            session.delete(session.get(Membership, (base.split('/')[-1], user.id)))
            if loss == 'tag_only':
                customer = app.state.store.add(session, 'customer', user, {'name': 'PRIVATE TAG CANARY'})
                session.add(WorkspaceCustomerLink(matter_id=base.split('/')[-1], customer_id=customer.id, firm_id=user.firm_id))
        elif loss == 'role':
            session.execute(delete(EmployeeRole).where(EmployeeRole.user_id == user.id))
        else:
            user.firm_id = 'foreign-firm'
        session.commit()
    decode = app.state.store.decode
    seen = []
    def guarded(row):
        seen.append(row.kind)
        assert row.kind != reviews.KIND
        return decode(row)
    monkeypatch.setattr(app.state.store, 'decode', guarded)
    response = client.get(endpoint + '/readiness')
    assert response.status_code in {401, 403, 404}
    assert not any(key in response.text for key in ['scanned_count', 'PRIVATE', 'sac-'])


def test_foreign_rows_and_dependencies_never_get_decrypted_or_counted(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, spec, analysis, reader, _ = setup(workbench, monkeypatch)
    saved, _ = freeze(client, endpoint, spec)
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        foreign = app.state.store.add(session, reviews.KIND, user, {'secret': 'FOREIGN CANARY'}, 'other-matter',
            record_id=reviews._prefix(base.split('/')[-1], analysis['id']) + uuid4().hex)
        foreign.firm_id = 'foreign-firm'
        product = session.get(Record, spec['product_id'])
        product.matter_id = 'other-matter'
        session.commit()
    decode = app.state.store.decode
    def guarded(row):
        assert row.id not in {foreign.id, spec['product_id']}
        return decode(row)
    monkeypatch.setattr(app.state.store, 'decode', guarded)
    no_public_reads(monkeypatch, reader)
    value = page(client, endpoint)
    assert value['coverage']['scanned_count'] == 1 and value['items'][0]['id'] == saved['id']
    assert 'research_basis_unavailable' in value['items'][0]['private_observation']['reasons']
    assert 'FOREIGN CANARY' not in str(value)


def test_observation_budget_is_unknown_and_never_borrows_historical_approval(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, _, _, reader, _, *_ = reviewed(workbench, monkeypatch)
    monkeypatch.setattr(readiness, 'MAX_DEPENDENCIES', 0)
    no_public_reads(monkeypatch, reader)
    item = page(client, endpoint)['items'][0]
    assert item['state'] == 'unavailable' and item['private_observation']['state'] == 'unknown'
    assert item['private_observation']['reasons'] == ['observation_budget_exhausted']
    assert item['historical_review']['state'] == 'reviewed_conditional'


def test_turkey_calendar_boundaries_and_invalid_or_excessive_filters(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, _, reader, _ = setup(workbench, monkeypatch)
    saved, _ = freeze(client, endpoint, spec)
    with app.state.store.session() as session:
        session.get(Record, saved['id']).created_at = '2026-10-13T21:00:00+00:00'
        session.commit()
    no_public_reads(monkeypatch, reader)
    assert page(client, endpoint, date_from='2026-10-14', date_to='2026-10-14')['coverage']['scanned_count'] == 1
    assert page(client, endpoint, date_to='2026-10-13')['items'] == []
    for params in [{'date_from': '2026-10-15', 'date_to': '2026-10-14'}, {'date_to': '9999-12-31'},
                   {'date_from': '0001-01-01'}, {'date_from': '20261014'}, {'window': 11}, {'offset': 10001}, {'bucket': 'ready'}]:
        assert client.get(endpoint + '/readiness', params=params).status_code == 422


def test_missing_admission_is_unavailable_and_never_repaired(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, _, reader, _ = setup(workbench, monkeypatch)
    saved, _ = freeze(client, endpoint, spec)
    with app.state.store.session() as session:
        session.delete(session.get(Record, reviews._id('saa-', saved['id'])))
        session.commit()
    no_public_reads(monkeypatch, reader)
    item = page(client, endpoint)['items'][0]
    assert item['state'] == 'unavailable' and item['historical_review']['state'] == 'unknown'
    assert 'manifest_sha256' not in item
    with app.state.store.session() as session:
        assert session.get(Record, reviews._id('saa-', saved['id'])) is None


def test_contradiction_budget_returns_explicit_unknown(workbench, monkeypatch):
    app, client, base, _, fact, *_ = workbench
    endpoint, _, _, reader, _, *_ = reviewed(workbench, monkeypatch)
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        app.state.store.add(session, 'practice_contradiction', user,
            {'fact_ids': [fact['id']], 'status': 'open', 'text': 'PRIVATE CONTRADICTION CANARY'}, base.split('/')[-1])
        session.commit()
    monkeypatch.setattr(readiness, 'MAX_CONTRADICTIONS', 0)
    no_public_reads(monkeypatch, reader)
    item = page(client, endpoint)['items'][0]
    assert item['private_observation']['state'] == 'unknown'
    assert 'observation_budget_exhausted' in item['private_observation']['reasons']
