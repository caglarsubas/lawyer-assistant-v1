"""Shared parser syntax must never share mutable programs, data or verdicts."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from pyparsing import ParseResults
from rdflib import BNode, Graph, Literal, Namespace
from rdflib.namespace import SH
from rdflib.plugins.sparql import processor
from test_validation_queries import inputs, parse_calls, validation

EX = Namespace('urn:synthetic:syntax:')


def graph(cache, value):
    result = validation._ValidationGraph(syntax_cache=cache)
    result.add((EX.item, EX.value, Literal(value)))
    return result


def test_repeated_syntax_has_independent_programs_and_fresh_data(monkeypatch):
    cache, calls = validation._SHACLSyntaxCache(), parse_calls(monkeypatch)
    query = 'SELECT ?value WHERE { $this ex:value ?value . FILTER (?value > 0) }'
    first, second = graph(cache, 1), graph(cache, 2)
    options = {'initNs': {'ex': EX}, 'initBindings': {'this': EX.item}}
    assert list(first.query(query, **options)) == [(Literal(1),)]
    assert list(second.query(query, **options)) == [(Literal(2),)]
    assert calls == [query]
    left, right = (next(iter(item._prepared_queries.values())) for item in (first, second))
    assert left is not right and left.algebra is not right.algebra and left.prologue is not right.prologue
    # Mutating one scratch program cannot damage the frozen template or the other.
    left.algebra.clear()
    third = graph(cache, 3)
    assert list(third.query(query, **options)) == [(Literal(3),)]
    second.set((EX.item, EX.value, Literal(-1)))
    assert list(second.query(query, **options)) == []
    assert calls == [query]


@pytest.mark.parametrize('query', [
    'SELECT ?value WHERE { ex:item ex:value ?value . }',
    'SELECT ?value WHERE { <item> <value> ?value . }',
    'BASE <urn:synthetic:syntax:> SELECT ?value WHERE { <item> <value> ?value . }',
])
def test_namespace_and_base_are_resolved_for_each_invocation(query):
    cache = validation._SHACLSyntaxCache()
    for index in range(2):
        namespace = EX if index == 0 else Namespace('urn:synthetic:other:')
        data = Graph().add((namespace.item, namespace.value, Literal(index)))
        options = {'initNs': {'ex': namespace}, 'base': str(namespace)}
        expected = list(data.query(query, **options))
        assert list(data.query(cache.prepare(query, options['initNs'], options['base']))) == expected
    with pytest.raises(Exception, match='Unknown namespace prefix'):
        cache.prepare('SELECT ?value WHERE { ex:item ex:value ?value . }', {}, None)


@pytest.mark.parametrize('query', [
    'SELECT ?value WHERE { ?s ex:value ?value FILTER (EXISTS { ?s ex:value ?value }) }',
    'SELECT ?value WHERE { { ?s ex:value ?value FILTER (?value >= 1) } UNION { VALUES ?value { 9 } } }',
    'SELECT ?value WHERE { OPTIONAL { ?s ex:value ?value } BIND (STR(?value) AS ?text) FILTER (?text != "0") }',
    'SELECT (COUNT(?value) AS ?count) WHERE { ?s ex:value ?value } GROUP BY ?s HAVING (COUNT(?value) > 0)',
    'SELECT ?value WHERE { { SELECT ?value WHERE { ?s ex:value ?value } } } ORDER BY ?value LIMIT 1',
    'SELECT ?s WHERE { ?s ex:value [] }',
    'SELECT ?value WHERE { ?s ex:value/ex:child ?value }',
])
def test_rich_syntax_and_warm_reconstruction_match_native(query):
    cache = validation._SHACLSyntaxCache()
    data = Graph().add((EX.item, EX.value, Literal(1))).add((EX.other, EX.value, Literal(2)))
    data.add((EX.parent, EX.value, EX.link)).add((EX.link, EX.child, Literal(3)))
    query = 'PREFIX ex: <urn:synthetic:syntax:> ' + query
    expected = list(data.query(query))
    for _ in range(3):
        assert list(data.query(cache.prepare(query, {}, None))) == expected


def test_blank_nodes_are_fresh_in_reconstructed_parser_trees():
    cache = validation._SHACLSyntaxCache()
    query = 'SELECT ?s WHERE { ?s <urn:p> [] }'
    first, second = cache.parse(query), cache.parse(query)

    def blanks(item):
        if isinstance(item, BNode):
            return {item}
        if isinstance(item, dict):
            return set().union(*(blanks(value) for value in item.values()))
        if isinstance(item, (tuple, list, ParseResults)):
            return set().union(*(blanks(value) for value in item))
        return set()

    assert blanks(first) and blanks(second) and blanks(first).isdisjoint(blanks(second))


@pytest.mark.parametrize('bound', ['entries', 'bytes', 'nodes', 'program_nodes', 'length'])
def test_limits_keep_native_semantics_without_unbounded_retention(monkeypatch, bound):
    limits = {'entries': ('_MAX_SYNTAX_ENTRIES', 1), 'bytes': ('_MAX_SYNTAX_BYTES', 40),
              'nodes': ('_MAX_SYNTAX_NODES', 1), 'program_nodes': ('_MAX_PROGRAM_NODES', 1),
              'length': ('_MAX_QUERY_LENGTH', 1)}
    monkeypatch.setattr(validation, *limits[bound])
    cache = validation._SHACLSyntaxCache()
    for index in (1, 2, 1, 3):
        query = f'SELECT ({index} AS ?value) WHERE {{}}'
        assert list(Graph().query(cache.prepare(query, {}, None))) == [(Literal(index),)]
    assert len(cache._entries) <= validation._MAX_SYNTAX_ENTRIES
    assert cache._bytes <= validation._MAX_SYNTAX_BYTES
    assert cache._nodes <= validation._MAX_SYNTAX_NODES
    if bound in ('nodes', 'program_nodes', 'length'):
        assert not cache._entries


def test_lru_eviction_reparses_current_program_and_malformed_queries_are_not_retained(monkeypatch):
    monkeypatch.setattr(validation, '_MAX_SYNTAX_ENTRIES', 2)
    cache, calls = validation._SHACLSyntaxCache(), parse_calls(monkeypatch)
    queries = [f'SELECT ({index} AS ?value) WHERE {{}}' for index in range(3)]
    for index in (0, 1, 0, 2, 1):
        assert list(Graph().query(cache.prepare(queries[index], {}, None))) == [(Literal(index),)]
    assert calls == [queries[0], queries[1], queries[2], queries[1]]
    for _ in range(2):
        with pytest.raises(Exception):
            cache.prepare('NOT VALID SPARQL', {}, None)
    assert 'NOT VALID SPARQL' not in cache._entries
    assert calls[-2:] == ['NOT VALID SPARQL', 'NOT VALID SPARQL']


@pytest.mark.parametrize('extension', ['named', 'attribute'])
def test_unknown_parser_state_falls_back_to_fresh_native_tree(monkeypatch, extension):
    native_parse = processor.parseQuery
    parsed = []

    def extended(query):
        value = native_parse(query)
        if extension == 'named':
            value['extension'] = value[1]
        else:
            value[1].extension = 'unknown parser implementation'
        parsed.append(value)
        return value

    monkeypatch.setattr(processor, 'parseQuery', extended)
    cache = validation._SHACLSyntaxCache()
    query = 'SELECT (1 AS ?value) WHERE {}'
    for _ in range(2):
        assert list(Graph().query(cache.prepare(query, {}, None))) == [(Literal(1),)]
    assert len(parsed) == 2 and not cache._entries


def test_parallel_cold_readers_parse_once_but_own_programs_and_results(monkeypatch):
    cache, calls = validation._SHACLSyntaxCache(), parse_calls(monkeypatch)
    barrier = Barrier(4)
    query = 'SELECT ?value WHERE { $this ex:value ?value FILTER (?value > 0) }'

    def worker(index):
        data = graph(cache, index)
        barrier.wait(timeout=10)
        for _ in range(4):
            assert list(data.query(query, initNs={'ex': EX}, initBindings={'this': EX.item})) == [(Literal(index),)]
        return next(iter(data._prepared_queries.values()))

    with ThreadPoolExecutor(max_workers=4) as pool:
        programs = list(pool.map(worker, range(1, 5)))
    assert calls == [query]
    assert len({id(program.algebra) for program in programs}) == 4
    assert len({id(program.prologue) for program in programs}) == 4


def test_warm_syntax_does_not_reuse_verdict_or_changed_shapes(monkeypatch):
    cache = validation._SHACLSyntaxCache()
    monkeypatch.setattr(validation, '_shacl_syntax', cache)
    data, shapes, schema = inputs()
    assert validation.validate_graph(data, shapes, schema)[0]
    query_node = next(shapes.subjects(SH.select, None))
    old = shapes.value(query_node, SH.select)
    shapes.set((query_node, SH.select, Literal('SELECT $this WHERE { $this ?p ?o }')))
    actual = validation.validate_graph(data, shapes, schema)
    from pyshacl import validate
    from rdflib.compare import isomorphic
    expected = validate(data, shacl_graph=shapes + Graph(), ont_graph=schema, inference='rdfs', advanced=True)
    assert not actual[0] and actual[0] == expected[0] and isomorphic(actual[1], expected[1])
    shapes.set((query_node, SH.select, old))
    assert validation.validate_graph(data, shapes, schema)[0]
