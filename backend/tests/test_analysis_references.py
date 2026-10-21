"""Invented labels only: page and clause identities must never be conflated."""
import copy
import json

import pytest

from app.analysis_output_contract import analysis_response_format, validate_analysis_output
from app.analysis_proposals import parse_patch
from app.analysis_reference_contract import (
    ReferenceValidationError,
    reference_labels,
    validate_patch_references,
)


def content():
    return {'evidence': [{'evidence_id': 'synthetic-a', 'text': '73. SYNTHETIC koşul başlığı\nÖzgün örnek.', 'locator': 'Sayfa 24'},
                         {'evidence_id': 'synthetic-b', 'text': 'SYNTHETIC devam metni.', 'locator': 'Sayfa 25'}],
            'rules': [{'id': 'r1', 'kind': 'contract_clause', 'text': 'm.73 için inceleme adayı.',
                       'evidence_ids': ['synthetic-a', 'synthetic-b'], 'conditions': [{'id': 'c1'}]}],
            'applications': [{'id': 'a1', 'rule_id': 'r1'}], 'conclusion': {'application_ids': ['a1']}}


def patch(value):
    return parse_patch(json.dumps({'application_updates': [{'id': 'a1', 'rationale': value, 'assessments': []}]}))


def test_exact_quote_heading_and_extractor_page_keep_distinct_reference_types():
    source = content()
    before = copy.deepcopy(source)
    assert reference_labels(source, {'synthetic-a', 'synthetic-b'}) == {('m', '73'), ('s', '24'), ('s', '25')}
    validate_patch_references(source, patch('m.73 ile s.24 ve s.25 birlikte incelenmelidir.'))
    assert source == before


@pytest.mark.parametrize('value', ['m.24 incelenmelidir.', 'm.25 incelenmelidir.', 's.73 incelenmelidir.', 'm.74 incelenmelidir.',
                                 'm.123456789 incelenmelidir.', 'm.73a incelenmelidir.'])
def test_page_to_clause_swaps_and_invented_labels_fail_closed(value):
    with pytest.raises(ReferenceValidationError) as caught:
        validate_patch_references(content(), patch(value))
    assert caught.value.code == 'proposal_reference_unqualified' and value not in str(caught.value)


@pytest.mark.parametrize('change', ['heading', 'declared', 'kind', 'page', 'source_link'])
def test_unqualified_metadata_never_becomes_a_reference(change):
    source = content()
    if change == 'heading':
        source['evidence'][0]['text'] = 'SYNTHETIC prose mentioning 73 elsewhere.'
    elif change == 'declared':
        source['rules'][0]['text'] = 'SYNTHETIC unnamed clause.'
    elif change == 'kind':
        source['rules'][0]['kind'] = 'legal_hypothesis'
    elif change == 'page':
        source['evidence'][0]['locator'] = 'SYNTHETIC filename 24.pdf'
    else:
        source['rules'][0]['evidence_ids'] = ['synthetic-b']
    value = 's.24 incelenmelidir.' if change == 'page' else 'm.73 incelenmelidir.'
    with pytest.raises(ReferenceValidationError):
        validate_patch_references(source, patch(value))


def test_valid_numbered_labels_pass_wire_but_still_require_source_qualification():
    value = {'application_updates': [{'id': 'a1', 'rationale': 'm.73 ile s.24 birlikte incelenmelidir.', 'assessments': []}],
             'conclusion_update': None, 'review_notes': []}
    raw = json.dumps(value)
    validate_analysis_output(raw, analysis_response_format())
    validate_patch_references(content(), parse_patch(raw))
    value['application_updates'][0]['rationale'] = 'm.24 birlikte incelenmelidir.'
    raw = json.dumps(value)
    validate_analysis_output(raw, analysis_response_format())
    with pytest.raises(ReferenceValidationError):
        validate_patch_references(content(), parse_patch(raw))
