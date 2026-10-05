"""Pure review conversion fixtures; no real legal approval or deployment writes."""
import json

import pytest
from rdflib import RDF, XSD, Graph, Literal
from test_release_preparation import ONTOLOGY, preparation  # noqa: F401

from app.release_preparation import LA, compile_review
from app.release_promotion import promoted_graphs, signing_inputs


def prepared(preparation):  # noqa: F811
    return compile_review(preparation['snapshot'], preparation['registry'], preparation['resolutions'],
                          preparation['evidence'], ONTOLOGY)[0]


def test_conversion_is_exact_and_strips_private_workflow_time(preparation):  # noqa: F811
    files = prepared(preparation)
    result = promoted_graphs(files, 'Public engineering reviewer', '2026-01-01T00:00:00Z')
    assert result == promoted_graphs(dict(reversed(list(files.items()))), 'Public engineering reviewer', '2026-01-01T00:00:00Z')
    for family, raw in result.items():
        old = Graph().parse(data=files[f'candidate/{family}.ttl'], format='turtle')
        new = Graph().parse(data=raw, format='turtle')
        old.remove((None, LA.reviewPreparationOnly, None))
        for node in old.subjects(RDF.type, LA.Assertion):
            for predicate, value in ((LA.claimStatus, Literal('legally_reviewed')),
                                     (LA.reviewer, Literal('Public engineering reviewer')),
                                     (LA.reviewedAt, Literal('2026-01-01T00:00:00Z', datatype=XSD.dateTime)),
                                     (LA.recordedAt, Literal('2026-01-01T00:00:00Z', datatype=XSD.dateTime))):
                old.set((node, predicate, value))
        assert set(old) == set(new)
        assert b'PRIVATE' not in raw and b'2025-02-01' not in raw
        assert not list(new.triples((None, LA.reviewPreparationOnly, None)))


def test_signing_inputs_have_only_public_evidence_and_unsigned_notice(preparation):  # noqa: F811
    files = prepared(preparation)
    outputs = signing_inputs(files, ontology_sha256='a' * 64, public_reviewer='Explicit public reviewer',
                             reviewed_at='2026-01-01T00:00:00Z')
    assert len([name for name in outputs if name.startswith('evidence/')]) == 3
    assert json.loads(outputs['NOTICE.json'])['signed'] is False
    assert json.loads(outputs['NOTICE.json'])['publication_eligible'] is False
    assert set(json.loads(outputs['public-review-body.json'])) == {
        'reviewer','reviewed_at','decision','scope','ontology_sha256','input_graphs_sha256'}
    assert all(b'PRIVATE' not in raw for raw in outputs.values())


@pytest.mark.parametrize('reviewer,time', [('', '2026-01-01T00:00:00Z'), ('x\ny', '2026-01-01T00:00:00Z'),
                                         ('x' * 161, '2026-01-01T00:00:00Z'), ('Reviewer','2026-01-01'),
                                         ('Reviewer','2099-01-01T00:00:00Z')])
def test_invalid_review_metadata_rejected(preparation, reviewer, time):  # noqa: F811
    with pytest.raises(ValueError):
        promoted_graphs(prepared(preparation), reviewer, time)


@pytest.mark.parametrize('change', ['missing', 'unmarked', 'false_marker', 'already_reviewed', 'effect'])
def test_only_preparation_conversion_is_supported(preparation, change):  # noqa: F811
    files = prepared(preparation)
    if change == 'missing':
        del files['candidate/structure.ttl']
    else:
        graph = Graph().parse(data=files['candidate/structure.ttl'], format='turtle')
        assertion = next(graph.subjects(RDF.type, LA.Assertion))
        if change in {'unmarked', 'false_marker'}:
            marker = next(graph.subjects(LA.reviewPreparationOnly, None))
            graph.remove((marker, LA.reviewPreparationOnly, None))
            if change == 'false_marker':
                graph.add((marker, LA.reviewPreparationOnly, Literal(False)))
        elif change == 'already_reviewed':
            graph.set((assertion, LA.claimStatus, Literal('legally_reviewed')))
        else:
            graph.set((assertion, LA.predicate, LA.applies))
        files['candidate/structure.ttl'] = graph.serialize(format='nt').encode()
    with pytest.raises(ValueError):
        promoted_graphs(files, 'Reviewer', '2026-01-01T00:00:00Z')
