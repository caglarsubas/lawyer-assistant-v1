"""Native rules and fresh checks, with bounded immutable identifier bindings."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import FunctionType

import pytest
from owlrl import DeductiveClosure
from owlrl.RDFSClosure import RDFS_Semantics
from pyshacl import validate as native_validate
from pyshacl.inference import CustomRDFSSemantics
from pyshacl.validator import Validator
from rdflib import RDF, RDFS, BNode, Graph, Literal, Namespace
from rdflib.compare import isomorphic
from test_validation_queries import fingerprint, inputs, load_module, validation

identifiers = load_module('rdfs_identifiers')
EX = Namespace('urn:synthetic:identifier-binding:')


def test_binding_reuses_native_code_and_exact_immutable_identifiers():
    native = CustomRDFSSemantics.rules
    bound = identifiers.bind_rule_identifiers(native)
    assert bound is not native and bound.__code__ is native.__code__
    assert native.__globals__['RDF'] is RDF and native.__globals__['RDFS'] is RDFS
    for name in ('RDF', 'RDFS'):
        terms = bound.__globals__[name]
        for field in terms._fields:
            assert getattr(terms, field) is getattr(native.__globals__[name], field)
            with pytest.raises(AttributeError):
                setattr(terms, field, EX.replacement)
    assert validation.validate is not native_validate
    assert validation.validate.__code__ is native_validate.__code__
    assert native_validate.__globals__['Validator'] is Validator
    assert identifiers.IdentifierBoundRDFS.one_time_rules is CustomRDFSSemantics.one_time_rules


@pytest.mark.parametrize('variant', ['callable', 'module', 'new_name', 'defaults', 'keyword', 'namespace'])
def test_unknown_rule_programs_keep_native_fallback(variant):
    native = CustomRDFSSemantics.rules
    if variant == 'callable':
        value = object()
    else:
        code = native.__code__
        globals_copy = dict(native.__globals__)
        if variant == 'new_name':
            code = code.replace(co_names=(*code.co_names, 'new_dependency'))
        if variant == 'namespace':
            globals_copy['RDF'] = object()
        value = FunctionType(code, globals_copy, native.__name__)
        if variant == 'module':
            value.__module__ = 'foreign.program'
        if variant == 'defaults':
            value.__defaults__ = (1,)
        if variant == 'keyword':
            value.__kwdefaults__ = {'cycle_num': 1}
    assert identifiers.bind_rule_identifiers(value) is None


def test_unknown_entry_point_and_plain_graph_keep_native_execution(monkeypatch):
    foreign = lambda *args, **kwargs: None  # noqa: E731
    monkeypatch.setattr(identifiers, 'native_validate', foreign)
    assert identifiers.validate_for(validation._ValidationGraph) is foreign
    seen = []

    def native(cls, *args):
        seen.append(args)

    monkeypatch.setattr(Validator, '_run_pre_inference', classmethod(native))
    runner = identifiers.validator_for(validation._ValidationGraph)
    from pyshacl.graph_abstraction import DataGraph
    adapter = DataGraph.from_rdflib(Graph())
    runner._run_pre_inference(adapter, 'rdfs')
    assert seen and seen[0][0] is adapter
    monkeypatch.setattr(identifiers, '_bound_rules', None)
    scratch = DataGraph.from_rdflib(validation._ValidationGraph())
    runner._run_pre_inference(scratch, 'rdfs')
    assert len(seen) == 2


def test_dependency_update_requires_requalification_and_keeps_native_path(monkeypatch):
    monkeypatch.setattr(identifiers, 'version', lambda name: 'unevaluated-version')
    assert identifiers.validate_for(validation._ValidationGraph) is native_validate


@pytest.mark.parametrize('variant', ['taxonomy', 'cycles', 'literals', 'domains', 'invalid'])
def test_inferred_triples_and_reports_match_native_with_inputs_unchanged(variant):
    data, shapes, schema = inputs()
    data.add((EX.item, RDF.type, EX.A))
    schema.add((EX.A, RDFS.subClassOf, EX.B))
    if variant == 'cycles':
        schema.add((EX.B, RDFS.subClassOf, EX.A))
        schema.add((EX.p, RDFS.subPropertyOf, EX.q))
        schema.add((EX.q, RDFS.subPropertyOf, EX.p))
        data.add((EX.item, EX.p, BNode()))
    elif variant == 'literals':
        data.add((EX.item, EX.p, Literal('same')))
        data.add((EX.other, EX.p, Literal(1)))
        schema.add((EX.Container, RDF.type, RDFS.ContainerMembershipProperty))
        schema.add((EX.Type, RDF.type, RDFS.Datatype))
    elif variant == 'domains':
        schema.add((EX.p, RDFS.domain, EX.A))
        schema.add((EX.p, RDFS.range, EX.B))
        data.add((EX.item, EX.p, EX.other))
    elif variant == 'invalid':
        from test_validation_queries import FX, LA
        data.remove((FX['version-link-a'], LA.evidence, None))
    original = [fingerprint(graph) for graph in (data, shapes, schema)]
    baseline = data + Graph()
    expected = native_validate(baseline, shacl_graph=shapes + Graph(), ont_graph=schema,
                               inference='rdfs', advanced=True, inplace=True)
    actual_graph = validation._copy_into(data, validation._ValidationGraph(syntax_cache=validation._shacl_syntax))
    actual = identifiers.validate_for(validation._ValidationGraph)(
        actual_graph, shacl_graph=shapes + Graph(), ont_graph=schema,
        inference='rdfs', advanced=True, inplace=True)
    assert actual[0] == expected[0] == (variant != 'invalid')
    assert isomorphic(actual[1], expected[1]) and isomorphic(actual_graph, baseline)
    assert [fingerprint(graph) for graph in (data, shapes, schema)] == original


def inference_work_counts(monkeypatch):
    data, shapes, schema = inputs()
    counts = {'native': {'rules': 0, 'resolutions': 0, 'queries': 0},
              'bound': {'rules': 0, 'resolutions': 0, 'queries': 0}}
    state = {'mode': 'native', 'in_rule': False}
    native_rules = RDFS_Semantics.rules
    bound_rules = identifiers.IdentifierBoundRDFS.rules
    resolve = type(RDF).__getattr__
    query = Graph.query

    def counted_rule(rule):
        def run(self, *args):
            counts[state['mode']]['rules'] += 1
            state['in_rule'] = True
            try:
                return rule(self, *args)
            finally:
                state['in_rule'] = False
        return run

    def counted_resolve(cls, name):
        if state['in_rule'] and cls in (RDF, RDFS):
            counts[state['mode']]['resolutions'] += 1
        return resolve(cls, name)

    def counted_query(self, *args, **kwargs):
        counts[state['mode']]['queries'] += 1
        return query(self, *args, **kwargs)

    monkeypatch.setattr(RDFS_Semantics, 'rules', counted_rule(native_rules))
    monkeypatch.setattr(identifiers.IdentifierBoundRDFS, 'rules', counted_rule(bound_rules))
    monkeypatch.setattr(type(RDF), '__getattr__', counted_resolve)
    monkeypatch.setattr(Graph, 'query', counted_query)
    scratch = lambda: validation._copy_into(data, validation._ValidationGraph(syntax_cache=validation._shacl_syntax))  # noqa: E731
    assert native_validate(scratch(), shacl_graph=shapes + Graph(), ont_graph=schema,
                           inference='rdfs', advanced=True, inplace=True)[0]
    state['mode'] = 'bound'
    assert identifiers.validate_for(validation._ValidationGraph)(
        scratch(), shacl_graph=shapes + Graph(), ont_graph=schema,
        inference='rdfs', advanced=True, inplace=True)[0]
    return counts


def test_work_budget_removes_resolution_without_reducing_rules_or_queries(monkeypatch):
    counts = inference_work_counts(monkeypatch)
    assert counts['native']['rules'] == counts['bound']['rules'] > 0
    assert counts['native']['queries'] == counts['bound']['queries'] > 0
    assert counts['native']['resolutions'] > counts['native']['rules'] * 5
    assert counts['bound']['resolutions'] == 0


def test_parallel_closures_keep_inferred_state_private():
    barrier = Barrier(4)

    def worker(index):
        graph = validation._ValidationGraph()
        graph.add((EX.item, RDF.type, EX[str(index)]))
        graph.add((EX[str(index)], RDFS.subClassOf, EX['parent-' + str(index)]))
        barrier.wait(timeout=10)
        DeductiveClosure(identifiers.IdentifierBoundRDFS).expand(graph)
        assert (EX.item, RDF.type, EX['parent-' + str(index)]) in graph
        assert (EX.item, RDF.type, EX['parent-' + str((index + 1) % 4)]) not in graph
        return graph

    with ThreadPoolExecutor(max_workers=4) as pool:
        graphs = list(pool.map(worker, range(4)))
    assert len({id(graph.store) for graph in graphs}) == 4
