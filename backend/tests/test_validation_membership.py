"""Fresh scratch membership must preserve native inference and SHACL reports."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from pyshacl import validate
from rdflib import RDF, RDFS, BNode, Graph, Literal, Namespace
from rdflib.compare import isomorphic
from test_validation_queries import fingerprint, inputs, validation

EX = Namespace('urn:synthetic:membership:')


def native_view(graph):
    return Graph(store=graph.store, identifier=graph.identifier)


def test_store_writes_bulk_additions_and_wildcards_match_native_membership():
    graph = validation._ValidationGraph()
    triples = [(EX.first, EX.value, Literal('first')), (BNode(), EX.value, Literal('second'))]
    graph.add(triples[0])
    graph.addN([(*triples[1], graph)])
    direct = (EX.direct, RDF.type, EX.Kind)
    graph.store.add(direct, graph)
    for triple in [*triples, direct, (EX.absent, EX.value, Literal('absent')),
                   (None, EX.value, None), (None, None, None), (EX.absent, None, None)]:
        assert (triple in graph) == (triple in native_view(graph))
    assert graph.store._exact == set(graph)


@pytest.mark.parametrize('method', ['graph', 'store', 'wildcard', 'clear'])
def test_every_removal_disables_index_and_observes_current_graph(method):
    graph = validation._ValidationGraph()
    triple = (EX.item, EX.value, Literal('before'))
    graph.add(triple)
    if method == 'graph':
        graph.remove(triple)
    elif method == 'store':
        graph.store.remove(triple, graph)
    else:
        graph.remove((EX.item if method == 'wildcard' else None, None, None))
    assert graph.store._exact is None
    assert triple not in graph
    graph.add((EX.item, EX.value, Literal('after')))
    assert graph.store._exact is None
    assert (EX.item, EX.value, Literal('after')) in graph


@pytest.mark.parametrize('other_context', ['different', 'same_identifier', 'quoted'])
def test_unexpected_contexts_disable_index_without_changing_native_behavior(other_context):
    graph = validation._ValidationGraph()
    first, second = (EX.first, EX.value, Literal(1)), (EX.second, EX.value, Literal(2))
    graph.add(first)
    context = Graph(store=graph.store, identifier=graph.identifier if other_context == 'same_identifier' else None)
    graph.store.add(second, graph if other_context == 'quoted' else context, quoted=other_context == 'quoted')
    assert graph.store._exact is None
    for triple in [first, second, (None, EX.value, None)]:
        assert (triple in graph) == (triple in native_view(graph))


def test_capacity_falls_back_permanently_without_discarding_graph_data(monkeypatch):
    monkeypatch.setattr(validation, '_MAX_MEMBERSHIP_TRIPLES', 2)
    graph = validation._ValidationGraph()
    triples = [(EX[str(i)], EX.value, Literal(i)) for i in range(3)]
    for triple in triples:
        graph.add(triple)
    assert graph.store._exact is None
    assert all(triple in graph for triple in triples)
    graph.remove(triples[0])
    assert graph.store._exact is None
    assert len(graph) == 2


def test_exact_probes_reduce_native_pattern_work_but_queries_still_run(monkeypatch):
    graph = validation._ValidationGraph()
    present, absent = (EX.item, EX.value, Literal('present')), (EX.missing, EX.value, Literal('absent'))
    graph.add(present)
    probes = []
    original = graph.store.triples

    def counted(*args, **kwargs):
        probes.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(graph.store, 'triples', counted)
    for _ in range(100):
        assert present in graph and absent not in graph
    assert probes == []
    assert (None, EX.value, None) in graph
    assert probes
    query = 'SELECT ?value WHERE { ?item ?property ?value . }'
    assert list(graph.query(query)) == [(Literal('present'),)]
    # Direct store removal cannot leave an earlier exact-membership answer live.
    graph.store.remove(present, graph)
    assert list(graph.query(query)) == [] and present not in graph


@pytest.mark.parametrize('variant', ['catalog', 'cycles', 'literals'])
def test_complete_inferred_triples_and_shacl_reports_match_native(monkeypatch, variant):
    data, shapes, schema = inputs()
    if variant == 'cycles':
        data.add((EX.A, RDFS.subClassOf, EX.B))
        data.add((EX.B, RDFS.subClassOf, EX.A))
        data.add((EX.item, RDF.type, EX.A))
        data.add((EX.p, RDFS.subPropertyOf, EX.q))
        data.add((EX.q, RDFS.subPropertyOf, EX.p))
        data.add((EX.q, RDFS.domain, EX.B))
        data.add((EX.q, RDFS.range, EX.A))
        data.add((EX.item, EX.p, BNode()))
    elif variant == 'literals':
        data.add((EX.item, EX.p, Literal(1)))
        data.add((EX.other, EX.q, Literal('1', datatype=Namespace('http://www.w3.org/2001/XMLSchema#').integer)))
        data.add((EX.Container, RDF.type, RDFS.ContainerMembershipProperty))
        data.add((EX.Type, RDF.type, RDFS.Datatype))
    original = [fingerprint(g) for g in (data, shapes, schema)]
    baseline = data + Graph()
    expected = validate(baseline, shacl_graph=shapes + Graph(), ont_graph=schema,
                        inference='rdfs', advanced=True, inplace=True)
    captured = []
    native_validate = validation.validate

    def capture(graph, **kwargs):
        result = native_validate(graph, **kwargs)
        captured.append(graph)
        return result

    monkeypatch.setattr(validation, 'validate', capture)
    actual = validation.validate_graph(data, shapes, schema)
    assert actual[0] == expected[0]
    assert isomorphic(actual[1], expected[1])
    assert isomorphic(captured[0], baseline)
    assert [fingerprint(g) for g in (data, shapes, schema)] == original


def test_parallel_invocations_cannot_share_membership():
    barrier = Barrier(4)

    def worker(index):
        graph = validation._ValidationGraph()
        triple = (EX.item, EX.value, Literal(index))
        graph.add(triple)
        barrier.wait(timeout=10)
        for _ in range(100):
            assert triple in graph
            assert (EX.item, EX.value, Literal((index + 1) % 4)) not in graph
        return graph

    with ThreadPoolExecutor(max_workers=4) as pool:
        graphs = list(pool.map(worker, range(4)))
    assert len({id(graph.store._exact) for graph in graphs}) == 4
