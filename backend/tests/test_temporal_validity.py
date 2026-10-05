"""Explicit temporal states tested with synthetic in-memory records only."""
import json

import pytest
from rdflib import RDF, XSD, Graph, Literal, URIRef
from test_graph import FX, LA, ONTOLOGY, conforms, corpus_for_query_tests, local_adapter

from app.graph_release import RuntimeGraphRelease, _load_serving, temporal

A, V, PROOF = FX['version-link-b'], FX['version-b'], FX['validity-proof']


def opened():
    graph = corpus_for_query_tests()
    for _, prop, value in list(graph.triples((FX.passage, None, None))):
        graph.add((PROOF, prop, value))
    for node in (A, V):
        graph.remove((node, LA.validTo, None))
        graph.set((node, LA.validityEndStatus, Literal('open_ended')))
        graph.set((node, LA.validityCheckedThrough, Literal('2025-06-01', datatype=XSD.date)))
        graph.add((node, LA.validityEvidence, PROOF))
    graph.set((A, LA.claimStatus, Literal('legally_reviewed')))
    graph.set((A, LA.reviewer, Literal('SYNTHETIC TEST REVIEWER')))
    graph.set((A, LA.reviewedAt, Literal('2026-01-01T00:00:00Z', datatype=XSD.dateTime)))
    return graph


def runtime(graph):
    proof = RuntimeGraphRelease()
    proof.info = {'release_id': 'test-only'}
    proof._graphs = {'structure': graph}
    proof._resources = graph
    return proof


@pytest.mark.parametrize('point,history,expected', [
    ('2023-12-31', False, False), ('2024-01-01', False, True),
    ('2025-06-01', False, True), ('2025-06-02', False, False),
    ('2025-06-02', True, True), ('2023-12-31', True, False),
])
def test_explicit_horizon_inclusive_and_history_keeps_start(point, history, expected):
    graph = opened()
    assert runtime(graph)._eligible('structure', A, as_of=point, history=history) is expected
    assert temporal.valid_at(temporal.interval_state(graph, A), point, history=history) is expected


@pytest.mark.parametrize('mutation', [
    'private_proof', 'revoked_rights', 'missing_artifact', 'missing_representation',
    'wrong_representation_artifact', 'private_representation', 'private_artifact',
    'duplicate_cutoff', 'duplicate_start', 'wrong_status_type', 'unreviewed',
    'review_before_cutoff', 'recorded_before_cutoff', 'version_cutoff_mismatch', 'version_proof_mismatch',
])
def test_runtime_rejects_bad_temporal_proof_independently(mutation):
    graph = opened()
    if mutation == 'private_proof':
        graph.set((PROOF, LA.scope, Literal('private')))
    elif mutation == 'revoked_rights':
        graph.set((FX.artifact, LA.rightsStatus, Literal('revoked')))
    elif mutation == 'missing_artifact':
        graph.remove((PROOF, LA.artifact, None))
    elif mutation == 'missing_representation':
        graph.remove((PROOF, LA.textRepresentation, None))
    elif mutation == 'wrong_representation_artifact':
        graph.set((FX['text-representation'], LA.artifact, URIRef('urn:test:wrong')))
    elif mutation == 'private_representation':
        graph.set((FX['text-representation'], LA.scope, Literal('private')))
    elif mutation == 'private_artifact':
        graph.set((FX.artifact, LA.scope, Literal('private')))
    elif mutation == 'duplicate_cutoff':
        graph.add((A, LA.validityCheckedThrough, Literal('2025-07-01', datatype=XSD.date)))
    elif mutation == 'duplicate_start':
        graph.add((A, LA.validFrom, Literal('2024-02-01', datatype=XSD.date)))
    elif mutation == 'wrong_status_type':
        graph.set((A, LA.validityEndStatus, URIRef('open_ended')))
    elif mutation == 'unreviewed':
        graph.set((A, LA.claimStatus, Literal('unreviewed')))
    elif mutation == 'review_before_cutoff':
        graph.set((A, LA.reviewedAt, Literal('2025-06-01T00:00:00+03:00', datatype=XSD.dateTime)))
    elif mutation == 'recorded_before_cutoff':
        graph.set((A, LA.recordedAt, Literal('2025-06-01T00:00:00+03:00', datatype=XSD.dateTime)))
    elif mutation == 'version_cutoff_mismatch':
        graph.set((V, LA.validityCheckedThrough, Literal('2025-07-01', datatype=XSD.date)))
    elif mutation == 'version_proof_mismatch':
        graph.set((V, LA.validityEvidence, FX.passage))
    assert not runtime(graph)._eligible('structure', A, as_of='2025-01-01')
    assert not runtime(graph)._eligible('structure', A, as_of='2027-01-01', history=True)


@pytest.mark.parametrize('cutoff,expected', [('2025-05-31', True), ('2025-06-01', False)])
def test_review_cutoff_uses_utc_calendar_day(cutoff, expected):
    graph = opened()
    for node in (A, V):
        graph.set((node, LA.validityCheckedThrough, Literal(cutoff, datatype=XSD.date)))
    graph.set((A, LA.reviewedAt, Literal('2025-06-01T00:30:00+03:00', datatype=XSD.dateTime)))
    assert runtime(graph)._eligible('structure', A, as_of='2025-01-01') is expected


def test_open_version_requires_reviewed_consistent_link_even_for_application():
    graph = opened()
    citation = FX['cites-a']
    graph.set((citation, LA.predicate, LA.applies))
    graph.set((citation, LA.object, V))
    graph.set((citation, LA.graphFamily, Literal('structure')))
    assert runtime(graph)._eligible('structure', citation, as_of='2025-01-01')
    graph.set((A, LA.claimStatus, Literal('unreviewed')))
    assert not runtime(graph)._eligible('structure', citation, as_of='2025-01-01')
    assert not runtime(graph)._eligible('structure', citation, as_of='2027-01-01', history=True)


def test_standalone_version_and_wrong_provision_cannot_support_open_validity():
    graph = opened()
    graph.set((A, LA.subject, FX.institution))
    assert not runtime(graph)._eligible('structure', A, as_of='2025-01-01')


@pytest.mark.parametrize('mutation', ['private', 'revoked', 'missing_representation', 'mismatched_artifact',
                                    'duplicate_date', 'mismatched_horizon', 'mismatched_proof'])
def test_shacl_temporal_proof_constraints(mutation):
    graph = opened()
    assert conforms(graph)
    if mutation == 'private':
        graph.set((PROOF, LA.scope, Literal('private')))
    elif mutation == 'revoked':
        graph.set((FX.artifact, LA.rightsStatus, Literal('revoked')))
    elif mutation == 'missing_representation':
        graph.remove((PROOF, LA.textRepresentation, None))
    elif mutation == 'mismatched_artifact':
        graph.set((FX['text-representation'], LA.artifact, URIRef('urn:test:wrong')))
    elif mutation == 'duplicate_date':
        graph.add((A, LA.validityCheckedThrough, Literal('2025-07-01', datatype=XSD.date)))
    elif mutation == 'mismatched_horizon':
        graph.set((V, LA.validityCheckedThrough, Literal('2025-07-01', datatype=XSD.date)))
    else:
        graph.set((V, LA.validityEvidence, FX.passage))
    assert not conforms(graph)


def public_copy(graph):
    """Change only fixture IRIs so the release validator can be exercised offline."""
    def mapped(value):
        if isinstance(value, URIRef) and str(value).startswith(str(FX)):
            return URIRef(str(value).replace(str(FX), 'urn:test-only:temporal:'))
        return value
    result = Graph()
    for triple in graph:
        result.add(tuple(mapped(value) for value in triple))
    return result, mapped


@pytest.mark.parametrize('owner', [A, V])
@pytest.mark.parametrize('mutation', ['private', 'revoked', 'missing_representation', 'mismatched_artifact', 'duplicate_date'])
def test_raw_publication_rejects_invalid_validity_evidence_on_both_owners(owner, mutation):
    graph = opened()
    # A separate proof isolates validation of either the assertion or the version.
    graph.set((owner, LA.validityEvidence, PROOF))
    if mutation == 'private':
        graph.set((PROOF, LA.scope, Literal('private')))
    elif mutation == 'revoked':
        graph.set((FX.artifact, LA.rightsStatus, Literal('revoked')))
    elif mutation == 'missing_representation':
        graph.remove((PROOF, LA.textRepresentation, None))
    elif mutation == 'mismatched_artifact':
        graph.set((FX['text-representation'], LA.artifact, URIRef('urn:test:wrong')))
    else:
        graph.add((owner, LA.validityCheckedThrough, Literal('2025-07-01', datatype=XSD.date)))
    graph, _ = public_copy(graph)
    # Every fixture assertion is classified to the test input's family.
    for assertion in graph.subjects(RDF.type, LA.Assertion):
        graph.set((assertion, LA.graphFamily, Literal('structure')))
    with pytest.raises(ValueError):
        _load_serving()._release.check_data({'structure': graph, 'jurisprudence': Graph()}, ONTOLOGY, {'verified': True})


def test_version_overlap_treats_cutoff_as_observation_not_expiry():
    graph = opened()
    temporal.validate_graph_temporality(graph)  # Closed A ends exactly at B start.
    graph.set((FX['version-a'], LA.validTo, Literal('2024-01-02', datatype=XSD.date)))
    with pytest.raises(ValueError, match='conflict'):
        temporal.validate_graph_temporality(graph)
    graph = opened()
    future = FX['future-version']
    for prop, value in ((RDF.type, LA.ProvisionVersion), (LA.versionOf, FX.provision),
                        (LA.validFrom, Literal('2026-01-01', datatype=XSD.date)),
                        (LA.validTo, Literal('2027-01-01', datatype=XSD.date))):
        graph.add((future, prop, value))
    with pytest.raises(ValueError, match='conflict'):
        temporal.validate_graph_temporality(graph)


@pytest.mark.parametrize('point,expected', [('2025-06-01', True), ('2025-06-02', False)])
def test_sparql_horizon_is_bounded(monkeypatch, point, expected):
    service = local_adapter(monkeypatch, opened())
    result = service.tool('resolve_authority', {'identifier': str(V), 'as_of': point, 'known_at': '2026-02-01T00:00:00Z'})
    assert bool(result['edges']) is expected


def test_history_evidence_inspection_retains_proof_without_current_applicability(monkeypatch):
    service = local_adapter(monkeypatch, opened())
    payload = {'as_of': '2027-01-01', 'known_at': '2026-02-01T00:00:00Z'}
    history = service.tool('trace_norm_history', {'entity_id': str(V), **payload})
    assert any(edge['id'] == str(A) for edge in history['edges'])
    result = service.tool('get_evidence', {'assertion_id': str(A), **payload})
    assert len(result['edges']) == 1 and result['edges'][0]['evidence']
    assert result['snapshot']['temporal_mode'] == 'history_inspection'
    assert result['snapshot']['applicability'] == 'not_established'
    assert result['edges'][0]['legal_usable'] is False
    assert any('applicability at the requested date is not established' in text for text in result['limitations'])
    assert not service.tool('get_evidence', {'assertion_id': str(A), **payload, 'as_of': '2023-01-01'})['edges']


@pytest.mark.parametrize('mutation', ['unknown', 'unreviewed', 'mismatched_horizon', 'missing_proof'])
def test_sparql_does_not_treat_unproven_open_version_as_applicable(monkeypatch, mutation):
    graph = opened()
    if mutation == 'unknown':
        graph.remove((V, LA.validityEndStatus, None))
    elif mutation == 'unreviewed':
        graph.set((A, LA.claimStatus, Literal('unreviewed')))
    elif mutation == 'mismatched_horizon':
        graph.set((V, LA.validityCheckedThrough, Literal('2025-07-01', datatype=XSD.date)))
    else:
        graph.remove((V, LA.validityEvidence, None))
    result = local_adapter(monkeypatch, graph).tool('resolve_authority', {
        'identifier': str(V), 'as_of': '2025-01-01', 'known_at': '2026-02-01T00:00:00Z'})
    assert not result['edges']


def test_validity_projection_is_separate_from_body_quote():
    graph = opened()
    result = runtime(graph).validity_evidence('structure', A)
    assert len(result) == 1 and result[0]['id'] == str(PROOF)
    assert result[0]['id'] not in {str(item) for item in graph.objects(A, LA.evidence)}
    assert result[0]['grounding_status'] == 'verified_release_quote'
    assert isinstance(result[0]['start_offset'], int)
    assert 'reviewer' not in json.dumps(result)


@pytest.mark.parametrize('changes,point,expected', [
    ({'valid_to': None}, '2024-01-01', False),
    ({'valid_to': None, 'validity_end_status': 'open_ended'}, '2024-01-01', False),
    ({'valid_to': None, 'validity_end_status': 'open_ended', 'validity_checked_through': '2025-06-01'}, '2025-06-01', True),
    ({'valid_to': None, 'validity_end_status': 'open_ended', 'validity_checked_through': '2025-06-01'}, '2025-06-02', False),
    ({'valid_to': None, 'validity_end_status': 'open_ended', 'validity_checked_through': '2019-01-01'}, '2024-01-01', False),
    ({'valid_to': '2030-01-01', 'validity_end_status': 'open_ended', 'validity_checked_through': '2025-06-01'}, '2024-01-01', False),
    ({'valid_to': '2030-01-01', 'validity_end_status': 'closed'}, '2030-01-01', False),
])
def test_search_index_temporal_prefilter_cannot_reclassify_unknown_end(monkeypatch, changes, point, expected):
    from test_search import mock_search, payload, service, source
    seen = mock_search(monkeypatch, [payload([source('temporal-test', **changes)])])
    result = service().search('SYNTHETIC', as_of=point)
    assert bool(result['hits']) is expected
    filters = json.loads(seen[0].content)['query']['bool']['filter']
    assert 'validity_end_status' in json.dumps(filters)
    assert 'validity_checked_through' in json.dumps(filters)
