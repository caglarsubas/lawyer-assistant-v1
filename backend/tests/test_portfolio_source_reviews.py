"""Authorized portfolio metadata, bounded coverage and immutable legal history."""

import pytest
from sqlalchemy import delete, select
from test_analysis_comparisons import login
from test_analysis_workbench import build_workbench
from test_portfolio import customer, workspace
from test_source_analysis_reviews import freeze, reviewed, setup
from test_source_analysis_reviews import workbench as workbench_fixture
from test_source_review_readiness import no_public_reads

from app import portfolio_source_reviews as queue
from app.db import CustomerAssignment, EmployeeRole, Membership, Record, User, WorkspaceCustomerLink

workbench = workbench_fixture
ENDPOINT = '/api/v1/work/source-reviews'


def read(client, **params):
    response = client.get(ENDPOINT, params=params)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    value = response.json()
    assert value['recipe'] == queue.RECIPE and value['coverage']['total_count'] is None
    assert value['legal_readiness'] == 'not_established' and not value['qualification_granted']
    for item in value['items']:
        assert item['source_verification'] == 'not_checked' and item['legal_readiness'] == 'not_established'
    for secret in ['TEST ONLY 📄', 'PRIVATE REVIEW NOTE', 'PRIVATE SOURCE NOTE', 'analysis_content', 'target_snapshots', 'source_candidates']:
        assert secret not in response.text
    return value


def other_case(workbench, monkeypatch, title='TEST ONLY other private case'):
    app, client, *_ = workbench
    login(client)
    matter = workspace(client, title)
    bench = build_workbench((app, client, matter['id']))
    endpoint, spec, analysis, reader, _ = setup(bench, monkeypatch)
    saved, _ = freeze(client, endpoint, spec)
    return matter['id'], bench, endpoint, spec, analysis, reader, saved


def link(app, matter_id, customer_ids):
    with app.state.store.session() as session:
        row = session.get(Record, matter_id)
        value = app.state.store.decode(row)
        value['customer_ids'] = customer_ids
        app.state.store.update(row, value)
        for ident in customer_ids:
            session.add(WorkspaceCustomerLink(matter_id=matter_id, customer_id=ident, firm_id=row.firm_id))
        session.commit()


def test_historical_positive_preserved_and_withdrawal_still_requires_original_guard(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, _, analysis, reader, permit, context, *_ = reviewed(workbench, monkeypatch)
    permit.active = False
    before = read(client)
    item = before['items'][0]
    assert item['id'] == context['id'] and item['matter_id'] == base.split('/')[-1] and item['analysis_id'] == analysis['id']
    assert item['historical_review']['state'] == 'reviewed_conditional' and item['state'] == 'inspection_required'
    assert client.get(endpoint + '/' + context['id']).json()['manifest'] is None
    assert client.get(endpoint + '/' + context['id'] + '/export').status_code == 409
    no_public_reads(monkeypatch, reader)
    assert read(client)['items'] == before['items']
    assert read(client, bucket='action_required')['items'] == []
    with app.state.store.session() as session:
        assert app.state.store.decode(session.get(Record, context['id']))['manifest'] == context['manifest']


def test_customer_or_matching_and_details_assignment_do_not_grant_other_case(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, spec, _, _, _ = setup(workbench, monkeypatch)
    first, _ = freeze(client, endpoint, spec)
    other, _, _, _, _, reader, second = other_case(workbench, monkeypatch)
    a, b = customer(client), customer(client, 'TEST ONLY customer B')
    link(app, base.split('/')[-1], [a['id']])
    link(app, other, [b['id']])
    assert {item['id'] for item in read(client, customer_ids=a['id'] + ',' + b['id'])['items']} == {first['id'], second['id']}
    assert [item['id'] for item in read(client, customer_ids=a['id'])['items']] == [first['id']]
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        session.delete(session.get(Membership, (other, user.id)))
        # Ownership and a customer-detail grant still confer no case grant.
        assert session.get(CustomerAssignment, (b['id'], user.id)).scope == 'details'
        session.commit()
    no_public_reads(monkeypatch, reader)
    value = read(client, customer_ids=a['id'] + ',' + b['id'] + ',' + a['id'])
    assert value['filters']['customer_ids'] == sorted([a['id'], b['id']])
    assert value['coverage']['scanned_count'] == 1 and len(value['items']) == 1
    assert value['items'][0]['id'] == first['id'] and other not in str(value)
    # An explicit all_cases assignment supplies the independent content grant.
    with app.state.store.session() as session:
        session.get(CustomerAssignment, (b['id'], user.id)).scope = 'all_cases'
        session.commit()
    assert {item['id'] for item in read(client, customer_ids=b['id'])['items']} == {second['id']}


def test_foreign_and_ungranted_inventories_are_not_decrypted_or_counted(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    first, _ = freeze(client, endpoint, spec)
    other, _, _, other_spec, _, reader, second = other_case(workbench, monkeypatch)
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        session.delete(session.get(Membership, (other, user.id)))
        foreign = app.state.store.add(session, 'source_analysis_context', user, {'analysis_id': 'FOREIGN CANARY'}, other)
        foreign.firm_id = 'foreign-firm'
        session.commit()
    decode = app.state.store.decode
    def guarded(row):
        assert row.id not in {other, second['id'], foreign.id, other_spec['product_id']}
        return decode(row)
    monkeypatch.setattr(app.state.store, 'decode', guarded)
    no_public_reads(monkeypatch, reader)
    value = read(client)
    assert value['coverage']['scanned_count'] == value['coverage']['locked_matter_count'] == 1
    assert value['items'][0]['id'] == first['id'] and 'FOREIGN' not in str(value)
    assert value['items'][0]['matter_id'] == base.split('/')[-1]


@pytest.mark.parametrize('loss', ['role', 'membership', 'archive', 'firm'])
def test_current_authority_loss_precedes_all_private_payloads(workbench, monkeypatch, loss):
    app, client, base, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    freeze(client, endpoint, spec)
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        if loss == 'role':
            session.execute(delete(EmployeeRole).where(EmployeeRole.user_id == user.id))
        elif loss == 'membership':
            session.delete(session.get(Membership, (base.split('/')[-1], user.id)))
        elif loss == 'archive':
            session.get(Record, base.split('/')[-1]).kind = 'archived_matter'
        else:
            user.firm_id = 'foreign-firm'
        session.commit()
    monkeypatch.setattr(app.state.store, 'decode', lambda *_: pytest.fail('Unauthorized records cannot be decrypted'))
    result = client.get(ENDPOINT)
    if loss in {'membership', 'archive'}:
        assert result.status_code == 200 and result.json()['coverage']['scanned_count'] == 0
    else:
        assert result.status_code in {401, 403}
        assert 'scanned_count' not in result.text


def test_customer_missing_or_foreign_uses_same_denial_without_inventory_reads(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    freeze(client, endpoint, spec)
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        foreign = app.state.store.add(session, 'customer', user, {'name': 'FOREIGN CUSTOMER CANARY'})
        foreign.firm_id = 'foreign-firm'
        session.commit()
    monkeypatch.setattr(app.state.store, 'decode', lambda *_: pytest.fail('Customer validation uses only authorized routing'))
    absent = client.get(ENDPOINT, params={'customer_ids': 'not-existing'})
    hidden = client.get(ENDPOINT, params={'customer_ids': foreign.id})
    assert absent.status_code == hidden.status_code == 404 and absent.json() == hidden.json()


def test_two_date_axes_and_unknown_workspace_dates_remain_distinct(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    saved, _ = freeze(client, endpoint, spec)
    with app.state.store.session() as session:
        matter = session.get(Record, base.split('/')[-1])
        matter.created_at = '2024-01-01T00:00:00+00:00'
        data = app.state.store.decode(matter)
        data.update(updated_at='2025-10-13T21:00:00+00:00', relevant_date='2023-03-01')
        app.state.store.update(matter, data)
        session.get(Record, saved['id']).created_at = '2026-10-13T21:00:00+00:00'
        session.commit()
    assert len(read(client, date_from='2024-01-01', date_to='2024-01-01',
        source_date_from='2026-10-14', source_date_to='2026-10-14')['items']) == 1
    assert not read(client, source_date_to='2026-10-13')['items']
    assert not read(client, date_from='2026-10-14')['items']
    assert len(read(client, date_field='updated_at', date_from='2025-10-14', date_to='2025-10-14')['items']) == 1
    assert len(read(client, date_field='relevant_date', date_from='2023-03-01', date_to='2023-03-01')['items']) == 1
    with app.state.store.session() as session:
        matter = session.get(Record, base.split('/')[-1])
        data = app.state.store.decode(matter)
        data['relevant_date'] = None
        app.state.store.update(matter, data)
        session.commit()
    assert not read(client, date_field='relevant_date', date_from='1920-01-01')['items']


def test_filtered_empty_window_does_not_hide_remaining_candidates(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    first, _ = freeze(client, endpoint, spec)
    other, _, _, _, _, _, second = other_case(workbench, monkeypatch)
    with app.state.store.session() as session:
        for ident, relevant in [(base.split('/')[-1], '2024-01-01'), (other, None)]:
            matter = session.get(Record, ident)
            data = app.state.store.decode(matter)
            data['relevant_date'] = relevant
            app.state.store.update(matter, data)
        session.commit()
    value = read(client, window=1, date_field='relevant_date', date_from='2024-01-01', date_to='2024-01-01')
    assert value['items'] == [] and value['coverage']['has_more'] and value['coverage']['next_offset'] == 1
    after = read(client, window=1, offset=1, date_field='relevant_date', date_from='2024-01-01', date_to='2024-01-01')
    assert [item['id'] for item in after['items']] == [first['id']] and not after['coverage']['has_more']
    assert second['id'] not in str(after)


def test_contradiction_and_private_observation_budgets_stay_unknown(workbench, monkeypatch):
    app, client, base, _, fact, *_ = workbench
    endpoint, spec, *_ = setup(workbench, monkeypatch)
    freeze(client, endpoint, spec)
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        app.state.store.add(session, 'practice_contradiction', user,
            {'fact_ids': [fact['id']], 'status': 'open'}, base.split('/')[-1])
        session.commit()
    monkeypatch.setattr(queue, 'MAX_CONTRADICTIONS', 0)
    item = read(client)['items'][0]
    assert item['state'] == 'unavailable' and item['private_observation']['state'] == 'unknown'
    assert 'observation_budget_exhausted' in item['private_observation']['reasons']


def test_missing_analysis_route_is_visible_without_foreign_identity_or_notes(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, analysis, _, _ = setup(workbench, monkeypatch)
    saved, _ = freeze(client, endpoint, spec)
    with app.state.store.session() as session:
        session.get(Record, analysis['id']).matter_id = 'foreign-matter'
        session.commit()
    value = read(client)['items'][0]
    assert value['id'] == saved['id'] and value['analysis_id'] is None
    assert value['state'] == 'unavailable' and value['historical_review']['state'] == 'unknown'
    assert 'foreign-matter' not in str(value)


@pytest.mark.parametrize('params', [{'window': 11}, {'offset': 10001}, {'bucket': 'ready'}, {'date_field': 'deadline'},
    {'source_date_from': '20261014'}, {'source_date_to': '9999-12-31'},
    {'date_from': '2025-01-01', 'date_to': '2024-01-01'}, {'source_date_from': '2025-01-01', 'source_date_to': '2024-01-01'},
    {'customer_ids': ','.join('case-' + str(i) for i in range(101))}])
def test_invalid_or_unbounded_filters_are_rejected(workbench, params):
    assert workbench[1].get(ENDPOINT, params=params).status_code == 422
