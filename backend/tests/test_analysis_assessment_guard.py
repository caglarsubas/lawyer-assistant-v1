"""Invented ledger-state transitions only; no legal or model quality gold labels."""
import copy
import json

import pytest

from app.analysis_proposals import apply_patch, parse_patch
from app.analysis_workbench import AnalysisInput
from app.db import digest


def source(kind='unknown', status='alleged'):
    premise = {'id': 'p1', 'kind': kind, 'text': 'SYNTHETIC unresolved event.'}
    if kind == 'fact':
        premise = {'id': 'p1', 'kind': 'fact', 'fact_id': 'synthetic-fact', 'fact_revision': 1}
    text = 'SYNTHETIC: a declared condition, not an actual legal rule.'
    value = AnalysisInput.model_validate({
        'title': 'SYNTHETIC transition', 'issue': 'SYNTHETIC source-state check',
        'evidence': [{'evidence_id': 'synthetic-source', 'document_revision': 1,
                      'passage_sha256': digest(text), 'start': 0, 'end': len(text)}],
        'premises': [premise],
        'rules': [{'id': 'r1', 'kind': 'contract_clause', 'text': text,
                   'evidence_ids': ['synthetic-source'], 'conditions': [
                       {'id': 'c1', 'text': 'SYNTHETIC event condition.'}]}],
        'applications': [{'id': 'a1', 'rule_id': 'r1', 'premise_ids': ['p1'],
                          'rationale': 'SYNTHETIC condition remains unresolved.',
                          'assessments': [{'condition_id': 'c1', 'status': 'unknown', 'premise_ids': ['p1']}]}],
        'conclusion': {'text': 'SYNTHETIC uncertainty remains.', 'application_ids': ['a1'],
                       'uncertainty': ['SYNTHETIC original uncertainty.'], 'next_step': 'Inspect the original.'},
    }).model_dump()
    value.update(checks={'defects': []}, fact_snapshots=[{
        'id': 'synthetic-fact', 'revision': 1, 'status': status, 'evidence_id': 'synthetic-source'}])
    return value


def patch(status, premises=None):
    return parse_patch(json.dumps({'application_updates': [{'id': 'a1',
        'rationale': 'SYNTHETIC proposal.', 'assessments': [
            {'condition_id': 'c1', 'status': status, 'premise_ids': ['p1'] if premises is None else premises}]}]}))


@pytest.mark.parametrize('kind,status', [
    ('unknown', 'alleged'), ('assumption', 'alleged'), ('fact', 'alleged'),
    ('fact', 'disputed'), ('fact', 'assumption'), ('fact', 'inference'),
])
@pytest.mark.parametrize('assessment', ['met', 'not_met'])
def test_model_cannot_settle_conditions_from_unsettled_declared_premises(kind, status, assessment):
    content = source(kind, status)
    before = copy.deepcopy(content)
    with pytest.raises(ValueError):
        apply_patch(content, patch(assessment))
    assert content == before


@pytest.mark.parametrize('assessment', ['met', 'not_met'])
def test_documented_selected_exact_revision_is_only_a_declared_state_precondition(assessment):
    content = source('fact', 'documented')
    before = copy.deepcopy(content)
    result = apply_patch(content, patch(assessment))
    assert result.applications[0].assessments[0].status == assessment
    assert result.conclusion.uncertainty == before['conclusion']['uncertainty']
    assert result.premises[0].fact_revision == 1 and content == before


@pytest.mark.parametrize('change', ['missing_snapshot', 'duplicate_snapshot', 'wrong_revision', 'missing_evidence', 'unselected_evidence'])
def test_documented_label_without_exact_selected_source_binding_is_insufficient(change):
    content = source('fact', 'documented')
    fact = content['fact_snapshots'][0]
    if change == 'missing_snapshot':
        content['fact_snapshots'] = []
    elif change == 'duplicate_snapshot':
        content['fact_snapshots'].append(copy.deepcopy(fact))
    elif change == 'wrong_revision':
        fact['revision'] = 2
    elif change == 'missing_evidence':
        fact['evidence_id'] = None
    else:
        fact['evidence_id'] = 'synthetic-unselected'
    before = copy.deepcopy(content)
    with pytest.raises(ValueError) as caught:
        apply_patch(content, patch('met'))
    assert caught.value.code == 'proposal_unsettled_assessment'
    assert 'synthetic' not in str(caught.value).lower() and content == before


@pytest.mark.parametrize('kind,status', [('unknown', 'alleged'), ('assumption', 'alleged'), ('fact', 'disputed')])
def test_unknown_assessment_is_preserved_and_can_replace_a_more_certain_one(kind, status):
    content = source(kind, status)
    content['applications'][0]['assessments'][0]['status'] = 'met'
    result = apply_patch(content, patch('unknown', []))
    assert result.applications[0].assessments[0].status == 'unknown'
    assert result.conclusion.uncertainty == content['conclusion']['uncertainty']


def test_empty_support_cannot_settle_a_condition():
    with pytest.raises(ValueError) as caught:
        apply_patch(source('fact', 'documented'), patch('not_met', []))
    assert caught.value.code == 'proposal_unsettled_assessment'


def test_exact_unchanged_assessment_is_not_rewritten_or_reendorsed():
    content = source('assumption')
    content['applications'][0]['assessments'][0]['status'] = 'met'
    before = copy.deepcopy(content)
    result = apply_patch(content, patch('met'))
    assert result.applications[0].assessments[0].model_dump() == before['applications'][0]['assessments'][0]
    assert content == before


def test_one_documented_premise_does_not_launder_a_second_unknown_premise():
    content = source('fact', 'documented')
    content['premises'].append({'id': 'p2', 'kind': 'unknown', 'text': 'SYNTHETIC missing separate event.',
                                'fact_id': None, 'fact_revision': None})
    content['applications'][0]['premise_ids'].append('p2')
    with pytest.raises(ValueError) as caught:
        apply_patch(content, patch('met', ['p1', 'p2']))
    assert caught.value.code == 'proposal_unsettled_assessment'


def test_invalid_second_edit_rejects_the_whole_patch_without_partial_application():
    content = source('fact', 'documented')
    content['premises'].append({'id': 'p2', 'kind': 'unknown', 'text': 'SYNTHETIC separate unknown.',
                                'fact_id': None, 'fact_revision': None})
    content['applications'].append({'id': 'a2', 'rule_id': 'r1', 'premise_ids': ['p2'],
                                     'rationale': 'SYNTHETIC original.', 'assessments': []})
    value = patch('met').model_dump()
    value['application_updates'].append({'id': 'a2', 'rationale': 'SYNTHETIC second edit.', 'assessments': [
        {'condition_id': 'c1', 'status': 'not_met', 'premise_ids': ['p2']}]})
    before = copy.deepcopy(content)
    with pytest.raises(ValueError):
        apply_patch(content, parse_patch(json.dumps(value)))
    assert content == before
