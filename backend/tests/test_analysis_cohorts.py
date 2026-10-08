"""Invented workspace inventories; no expert, provider or benefit qualification."""

import copy
import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_analysis_comparisons import effort, login, observation, register, run
from test_analysis_workbench import workbench as workbench_fixture

from app import analysis_cohorts as cohorts
from app.db import Audit, Membership, Record, User, digest
from app.evidence_prompt import canonical


@pytest.fixture
def workbench(tmp_path):
    yield from workbench_fixture.__wrapped__(tmp_path)


def pair(workbench, monkeypatch, *, different_family=False, different_rubric=False):
    _, client, base, *_ = workbench
    record, endpoint, first, body, calls = register(workbench, monkeypatch)
    second_body = {**body, 'request_id': uuid4().hex,
                   'title': 'SYNTHETIC second selected comparison',
                   'split_family_sha256': 'b' * 64 if different_family else body['split_family_sha256']}
    if different_rubric:
        second_body['rubric_text'] += ' SYNTHETIC different rubric; never pooled.'
    second = client.post(endpoint, json=second_body)
    assert second.status_code == 201, second.text
    spec = {'title': 'SYNTHETIC confidential development inventory', 'purpose': 'SYNTHETIC binding and gap checks only',
            'selections': [{'analysis_id': record['id'], 'comparison_id': item['id']} for item in (first, second.json())],
            'reserved_family_sha256': []}
    return base + '/analysis-cohorts', spec, endpoint, calls


def complete(client, endpoint, spec, *, disagree=False):
    for selected in spec['selections']:
        detail = endpoint + '/' + selected['comparison_id']
        run(client, endpoint, client.get(detail).json())
        for index in range(2):
            login(client, f'SYNTHETIC-reviewer-{index}')
            value = client.get(detail).json()
            body = observation(value)
            if disagree:
                for arm in body['arms']:
                    item = arm['assessment']['observations'][0]
                    item['outcome'] = 'needs_change' if index == 0 else 'confirmed'
                    if index == 1:
                        item['source_refs'] = [value['arms'][arm['arm']]['comparison']['sources'][-1]['source_ref']]
            response = client.post(detail + '/observations', json=body)
            assert response.status_code == 201, response.text
        login(client)
        response = client.post(detail + '/effort', json=effort(client.get(detail).json()))
        assert response.status_code == 201, response.text


def freeze(client, endpoint, spec):
    preview = client.post(endpoint + '/preview', json=spec)
    assert preview.status_code == 200, preview.text
    body = {**spec, 'request_id': uuid4().hex, 'expected_preview_sha256': preview.json()['preview_sha256']}
    result = client.post(endpoint, json=body)
    assert result.status_code == 201, result.text
    return result.json(), body


def count(app, model=Record, kind=cohorts.KIND):
    with app.state.store.session() as session:
        query = select(func.count()).select_from(model)
        if model is Record:
            query = query.where(Record.kind == kind)
        return session.scalar(query)


def test_preview_has_no_writes_calls_or_actor_clock_dependence_and_preserves_unknowns(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, _, calls = pair(workbench, monkeypatch)
    audits = count(app, Audit)
    first = client.post(endpoint + '/preview', json=spec)
    assert first.status_code == 200, first.text
    login(client, 'SYNTHETIC-reviewer-0')
    second = client.post(endpoint + '/preview', json=spec)
    assert first.json() == second.json() and not calls
    assert not count(app) and count(app, Audit) == audits
    report = first.json()['manifest']['reconciliation']
    assert report['counts']['selected_records'] == 2 and report['counts']['declared_families'] == 1
    assert report['counts']['complete_capture_records'] == 0
    assert len(report['duplicate_inputs']) == len(report['repeated_versions']) == 1
    assert not report['cross_family_sources'] and not report['reserved_overlaps']
    assert report['preparation_time_gain'] is None and report['legal_verdict'] is None
    for row in report['rows']:
        assert row['unknown_assessment_observations'] == 24
        assert all(item['status'] == 'not_started' and item['active_effort'] is None
                   and item['elapsed_seconds'] is None and item['gpu_compute_seconds'] is None
                   for item in row['arms'].values())


def test_immutable_encrypted_freeze_idempotent_private_export_and_original_draft_preserved(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, spec, comparisons_endpoint, calls = pair(workbench, monkeypatch)
    complete(client, comparisons_endpoint, spec)
    assert len(calls) == 6
    view, body = freeze(client, endpoint, spec)
    assert view['freshness']['status'] == 'current'
    report = view['manifest']['reconciliation']
    assert report['counts']['complete_capture_records'] == report['counts']['accounted_effort_records'] == 2
    assert report['counts']['records_with_unknown_assessments'] == report['counts']['records_with_unresolved_findings'] == 2
    assert not report['qualification_granted'] and not view['production_qualified'] and not view['benefit_established']
    with app.state.store.session() as session:
        frozen = session.get(Record, view['id']).payload
    assert spec['title'] not in frozen and 'SYNTHETIC-NOT-A-REAL-KEY' not in json.dumps(view)
    assert client.post(endpoint, json=body).json()['id'] == view['id'] and count(app) == 1
    altered = {**body, 'purpose': 'SYNTHETIC different request under same nonce'}
    assert client.post(endpoint, json=altered).status_code == 409
    assert client.get(endpoint).json()[0]['id'] == view['id']
    download = client.get(endpoint + '/' + view['id'] + '/export')
    assert download.status_code == 200 and 'attachment;' in download.headers['content-disposition']
    assert download.headers['cache-control'] == 'no-store' and download.headers['x-content-type-options'] == 'nosniff'
    assert download.json()['manifest_sha256'] == view['manifest_sha256']
    assert digest(canonical(download.json()['manifest'])) == view['manifest_sha256']
    assert len(calls) == 6 and client.get(base + '/analyses').json()[0]['version'] == 1
    inventory = client.post(base + '/erasure-plan')
    assert inventory.status_code == 200, inventory.text
    assert {'id': view['id'], 'kind': cohorts.KIND} in inventory.json()['records']
    assert inventory.json()['record_counts'][cohorts.KIND] == 1 and not inventory.json()['physical_erasure_available']
    with app.state.store.session() as session:
        assert session.get(Record, view['id']).payload == frozen


def test_separate_profiles_family_conflicts_and_different_outcomes_are_retained_not_resolved(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, spec, comparisons_endpoint, _ = pair(workbench, monkeypatch, different_family=True, different_rubric=True)
    complete(client, comparisons_endpoint, spec, disagree=True)
    spec['reserved_family_sha256'] = ['b' * 64]
    preview = client.post(endpoint + '/preview', json=spec)
    assert preview.status_code == 200, preview.text
    report = preview.json()['manifest']['reconciliation']
    assert report['counts']['profile_groups'] == report['counts']['declared_families'] == 2
    assert report['counts']['records_with_outcome_differences'] == 2
    assert all(len(item['comparison_ids']) == 1 for item in report['profiles'])
    assert len(report['duplicate_inputs']) == 1 and len(report['cross_family_sources']) == 1
    assert report['reserved_overlaps'] == ['b' * 64]
    assert {item['family_sha256']: item['reserved_overlap'] for item in report['families']} == {'a' * 64: False, 'b' * 64: True}
    for row in report['rows']:
        for arm in row['arms'].values():
            first = arm['dimensions'][0]
            assert first['outcome_difference'] and {item['outcome'] for item in first['observations']} == {'confirmed', 'needs_change'}
            assert all(item['unresolved_or_missing'] for item in arm['findings'])
    assert report['legal_verdict'] is None and not report['held_out_qualified'] and not report['reviewer_expertise_verified']


@pytest.mark.parametrize('change', ['provider', 'observations', 'effort', 'fact', 'participant', 'job', 'recipe'])
def test_later_changes_mark_projection_stale_without_rewriting_frozen_report(workbench, monkeypatch, change):
    app, client, base, _, fact, *_ = workbench
    endpoint, spec, comparisons_endpoint, calls = pair(workbench, monkeypatch)
    complete(client, comparisons_endpoint, spec)
    view, _ = freeze(client, endpoint, spec)
    original = copy.deepcopy(view['manifest'])
    detail = comparisons_endpoint + '/' + spec['selections'][0]['comparison_id']
    if change == 'provider':
        app.state.settings.provider_model += '-changed'
    elif change == 'observations':
        login(client, 'SYNTHETIC-reviewer-0')
        response = client.post(detail + '/observations', json=observation(client.get(detail).json()))
        assert response.status_code == 201
        login(client)
    elif change == 'effort':
        response = client.post(detail + '/effort', json=effort(client.get(detail).json()))
        assert response.status_code == 201
    elif change in {'fact', 'participant', 'job'}:
        with app.state.store.session() as session:
            if change == 'fact':
                row = session.get(Record, fact['id'])
                app.state.store.update(row, {**app.state.store.decode(row), 'text': 'SYNTHETIC changed basis'})
            elif change == 'participant':
                user = session.scalar(select(User).where(User.username == 'SYNTHETIC-reviewer-0'))
                session.delete(session.get(Membership, (base.rsplit('/', 1)[1], user.id)))
            else:
                job_id = original['captures'][0]['capture']['arms']['single_pass']['job']['id']
                row = session.get(Record, job_id)
                app.state.store.update(row, {**app.state.store.decode(row), 'status': 'interrupted'})
            session.commit()
    else:
        monkeypatch.setattr(cohorts, 'RECIPE', 'SYNTHETIC-next-reconciliation-recipe')
    updated = client.get(endpoint + '/' + view['id'])
    assert updated.status_code == 200, updated.text
    assert updated.json()['manifest'] == original and updated.json()['manifest_sha256'] == view['manifest_sha256']
    assert updated.json()['freshness']['status'] == 'stale' and updated.json()['freshness']['reasons']
    assert not updated.json()['qualification_granted'] and len(calls) == 6
    download = client.get(endpoint + '/' + view['id'] + '/export')
    assert download.status_code == 200 and download.json()['freshness']['status'] == 'stale'


def test_preview_change_and_late_save_change_both_reject_with_atomic_rollback(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, _, calls = pair(workbench, monkeypatch)
    preview = client.post(endpoint + '/preview', json=spec).json()
    body = {**spec, 'request_id': uuid4().hex, 'expected_preview_sha256': preview['preview_sha256']}
    app.state.settings.provider_model += '-changed'
    assert client.post(endpoint, json=body).status_code == 409 and count(app) == 0
    preview = client.post(endpoint + '/preview', json=spec).json()
    body.update(request_id=uuid4().hex, expected_preview_sha256=preview['preview_sha256'])
    prior_audits = count(app, Audit)
    audit = cohorts._audit

    def late_change(*args, **kwargs):
        audit(*args, **kwargs)
        app.state.settings.provider_model += '-late'

    monkeypatch.setattr(cohorts, '_audit', late_change)
    response = client.post(endpoint, json=body)
    assert response.status_code == 409 and count(app) == 0 and count(app, Audit) == prior_audits and not calls


@pytest.mark.parametrize('kind', ['fact', 'document'])
def test_second_change_to_already_stale_evidence_invalidates_preview_and_rolls_back(workbench, monkeypatch, kind):
    app, client, _, _, fact, document, *_ = workbench
    endpoint, spec, _, calls = pair(workbench, monkeypatch)
    ident = fact['id'] if kind == 'fact' else document

    def change(session):
        row = session.get(Record, ident)
        body = app.state.store.decode(row)
        if kind == 'fact':
            body['text'] += ' SYNTHETIC changed'
        else:
            body['passages'][0]['text'] += ' SYNTHETIC changed'
        app.state.store.update(row, body)
        session.flush()

    with app.state.store.session() as session:
        change(session)
        session.commit()
    preview = client.post(endpoint + '/preview', json=spec).json()
    assert preview['manifest']['reconciliation']['counts']['current_source_records'] == 0
    body = {**spec, 'request_id': uuid4().hex, 'expected_preview_sha256': preview['preview_sha256']}
    audit = cohorts._audit
    prior = count(app, Audit)

    def late_change(session, *args, **kwargs):
        audit(session, *args, **kwargs)
        change(session)

    monkeypatch.setattr(cohorts, '_audit', late_change)
    assert client.post(endpoint, json=body).status_code == 409
    assert count(app) == 0 and count(app, Audit) == prior and not calls


@pytest.mark.parametrize('invalid', ['one', 'thirteen', 'duplicate', 'wrong_parent', 'unknown', 'raw_capture', 'reserved', 'repeated_reserved', 'override'])
def test_strict_selection_and_family_bounds_fail_without_partial_capture(workbench, monkeypatch, invalid):
    app, client, *_ = workbench
    endpoint, spec, _, calls = pair(workbench, monkeypatch)
    if invalid == 'one':
        spec['selections'].pop()
    elif invalid == 'thirteen':
        spec['selections'] *= 7
    elif invalid == 'duplicate':
        spec['selections'][1] = spec['selections'][0]
    elif invalid == 'wrong_parent':
        spec['selections'][0]['analysis_id'] = 'SYNTHETIC-wrong-parent'
    elif invalid == 'unknown':
        spec['selections'][0]['comparison_id'] = 'SYNTHETIC-missing'
    elif invalid == 'raw_capture':
        spec['captures'] = [{'qualification_granted': True}]
    elif invalid == 'reserved':
        spec['reserved_family_sha256'] = ['SYNTHETIC-invalid']
    elif invalid == 'repeated_reserved':
        spec['reserved_family_sha256'] = ['a' * 64, 'a' * 64]
    else:
        spec['cloud_provider'] = 'forbidden'
    response = client.post(endpoint + '/preview', json=spec)
    assert response.status_code in {404, 422} and count(app) == 0 and not calls


def test_byte_limit_blocks_preview_save_read_export_without_truncating_retained_data(workbench, monkeypatch):
    app, client, *_ = workbench
    endpoint, spec, _, _ = pair(workbench, monkeypatch)
    view, body = freeze(client, endpoint, spec)
    with app.state.store.session() as session:
        original = session.get(Record, view['id']).payload
    monkeypatch.setattr(cohorts, 'MAX_BYTES', 500)
    assert client.post(endpoint + '/preview', json=spec).status_code == 409
    assert client.post(endpoint, json={**body, 'request_id': uuid4().hex}).status_code == 409
    assert client.get(endpoint + '/' + view['id']).status_code == 409
    assert client.get(endpoint + '/' + view['id'] + '/export').status_code == 409
    assert count(app) == 1
    with app.state.store.session() as session:
        assert session.get(Record, view['id']).payload == original


def test_workspace_access_csrf_parent_boundaries_and_revocation(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, spec, _, calls = pair(workbench, monkeypatch)
    view, body = freeze(client, endpoint, spec)
    other_response = client.post('/api/v1/matters', json={'title': 'SYNTHETIC other workspace', 'domain': 'contracts'})
    assert other_response.status_code == 201, other_response.text
    other = other_response.json()['id']
    other_endpoint = '/api/v1/matters/' + other + '/analysis-cohorts'
    assert client.post(other_endpoint + '/preview', json=spec).status_code == 404
    assert client.get(other_endpoint + '/' + view['id']).status_code == 404
    assert client.get(other_endpoint + '/candidates').json() == []
    assert client.get(other_endpoint).json() == []
    csrf = client.headers.pop('X-CSRF-Token')
    assert client.post(endpoint + '/preview', json=spec).status_code == 403
    client.headers['X-CSRF-Token'] = csrf
    login(client, 'SYNTHETIC-reviewer-0')
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'SYNTHETIC-reviewer-0'))
        session.delete(session.get(Membership, (base.rsplit('/', 1)[1], user.id)))
        session.commit()
    for path in ('', '/candidates', '/' + view['id'], '/' + view['id'] + '/export'):
        assert client.get(endpoint + path).status_code == 404
    assert client.post(endpoint, json=body).status_code == 404
    client.cookies.clear()
    assert client.get(endpoint + '/' + view['id'] + '/export').status_code == 401 and not calls


@pytest.mark.parametrize('change', ['delete', 'move', 'source_move', 'corrupt_protocol', 'corrupt_cohort', 'substitute_cohort'])
def test_missing_integrity_and_routing_changes_never_silently_substitute_records(workbench, monkeypatch, change):
    app, client, base, *_ = workbench
    endpoint, spec, _, _ = pair(workbench, monkeypatch)
    view, _ = freeze(client, endpoint, spec)
    with app.state.store.session() as session:
        selected = session.get(Record, spec['selections'][0]['comparison_id'])
        row = session.get(Record, view['id'])
        if change == 'delete':
            session.delete(selected)
        elif change == 'move':
            selected.matter_id = 'SYNTHETIC-foreign-workspace'
        elif change == 'source_move':
            document = session.get(Record, workbench[5])
            document.matter_id = 'SYNTHETIC-foreign-workspace'
        elif change == 'corrupt_protocol':
            app.state.store.update(selected, {**app.state.store.decode(selected), 'title': 'SYNTHETIC tampered'})
        elif change == 'corrupt_cohort':
            value = app.state.store.decode(row)
            value['manifest']['title'] = 'SYNTHETIC tampered'
            app.state.store.update(row, value)
        else:
            value = app.state.store.decode(row)
            value['manifest']['matter_id'] = 'SYNTHETIC-foreign-workspace'
            value['manifest_sha256'] = digest(canonical(value['manifest']))
            value['cohort_sha256'] = digest(canonical({key: item for key, item in value.items() if key != 'cohort_sha256'}))
            app.state.store.update(row, value)
        session.commit()
    response = client.get(endpoint + '/' + view['id'])
    if change == 'delete':
        assert response.status_code == 200 and response.json()['freshness']['status'] == 'stale'
        assert response.json()['manifest'] == view['manifest'] and response.json()['live_captures'][0]['capture_sha256'] is None
    else:
        assert response.status_code == (404 if change == 'move' else 403 if change == 'source_move' else 409)
        assert client.get(endpoint + '/' + view['id'] + '/export').status_code == response.status_code
    if change in {'corrupt_cohort', 'substitute_cohort'}:
        assert client.get(endpoint).status_code == 409


def test_candidates_and_cohort_lists_are_bounded_and_archived_freeze_is_withheld(workbench, monkeypatch):
    app, client, base, *_ = workbench
    endpoint, spec, _, calls = pair(workbench, monkeypatch)
    candidates = client.get(endpoint + '/candidates?limit=1').json()
    assert len(candidates) == 1 and 'capture' not in candidates[0]
    assert client.get(endpoint + '/candidates?offset=1&limit=1').json()[0]['comparison_id'] != candidates[0]['comparison_id']
    assert client.get(endpoint + '/candidates?limit=21').status_code == 422
    assert client.get(endpoint + '?offset=-1').status_code == 422
    view, _ = freeze(client, endpoint, spec)
    assert len(client.get(endpoint + '?limit=1').json()) == 1
    with app.state.store.session() as session:
        matter = session.get(Record, base.rsplit('/', 1)[1])
        app.state.store.update(matter, {**app.state.store.decode(matter), 'status': 'archived'})
        session.commit()
    preview = client.post(endpoint + '/preview', json=spec)
    assert preview.status_code == 200
    response = client.post(endpoint, json={**spec, 'request_id': uuid4().hex,
                                          'expected_preview_sha256': preview.json()['preview_sha256']})
    assert response.status_code == 409 and count(app) == 1 and not calls
    assert client.get(endpoint + '/' + view['id']).status_code == 200


def test_pure_reconciliation_keeps_real_synthetic_model_budget_and_feedback_profiles_separate(workbench, monkeypatch):
    _, client, *_ = workbench
    endpoint, spec, _, _ = pair(workbench, monkeypatch)
    entries = client.post(endpoint + '/preview', json=spec).json()['manifest']['captures']
    for change in ('origin', 'model', 'budget', 'feedback'):
        values = copy.deepcopy(entries)
        plan = values[1]['capture']['protocol']
        if change == 'origin':
            plan['sample_kind'] = values[1]['capture']['sample_kind'] = 'real'
        elif change == 'model':
            plan['provider_pin']['model'] = 'SYNTHETIC-other'
        elif change == 'budget':
            plan['arms']['single_pass']['budget_seconds'] += 1
        else:
            plan['review_feedback'] = {'recipe': 'SYNTHETIC-feedback-recipe'}
        report = cohorts.reconcile(values, [])
        assert report['counts']['profile_groups'] == 2 and not report['production_qualified']
        assert report['preparation_time_gain'] is None
