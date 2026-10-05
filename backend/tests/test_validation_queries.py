"""SPARQL syntax reuse must preserve full SHACL checks and fresh evidence reads."""

import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from pyshacl import validate
from rdflib import OWL, RDF, XSD, Graph, Literal, Namespace
from rdflib.compare import isomorphic
from rdflib.plugins.sparql import processor

ONTOLOGY = Path(__file__).resolve().parents[2] / "ontology"
LA = Namespace("https://lawyer-assistant.local/ontology/")
FX = Namespace("urn:synthetic:lawyer-assistant:")
EX = Namespace("urn:synthetic:query-validation:")


def load_module(name):
    spec = importlib.util.spec_from_file_location("test_query_" + name, ONTOLOGY / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validation = load_module("validation")


def inputs():
    schema = Graph()
    for path in sorted((ONTOLOGY / "modules").glob("*.ttl")):
        schema.parse(path, format="turtle")
    schema.parse(ONTOLOGY / "domains.ttl", format="turtle")
    fixture = Graph().parse(ONTOLOGY / "fixtures" / "competency.ttl", format="turtle")
    shapes = Graph().parse(ONTOLOGY / "shapes.ttl", format="turtle")
    return fixture, shapes, schema


def fingerprint(graph):
    return frozenset(graph), dict(graph.namespaces()), graph.identifier, graph.base


def parse_calls(monkeypatch):
    calls = []
    original = processor.parseQuery

    def counted(query):
        calls.append(query)
        return original(query)

    monkeypatch.setattr(processor, "parseQuery", counted)
    return calls


@pytest.mark.parametrize("mutation", [
    None, "missing_evidence", "unreviewed_approval", "invalid_interval",
    "unknown_version", "private_scope", "wrong_range", "type_instance",
])
def test_complete_validation_and_reports_match_without_mutating_inputs(mutation):
    data, shapes, schema = inputs()
    assertion = FX["version-link-a"]
    if mutation == "missing_evidence":
        data.remove((assertion, LA.evidence, None))
    elif mutation == "unreviewed_approval":
        data.set((assertion, LA.claimStatus, Literal("legally_reviewed")))
    elif mutation == "invalid_interval":
        data.set((assertion, LA.validTo, Literal("1919-01-01", datatype=XSD.date)))
    elif mutation == "unknown_version":
        data.set((FX["cites-a"], LA.predicate, LA.applies))
        data.set((FX["cites-a"], LA.object, FX.unknown))
    elif mutation == "private_scope":
        data.set((FX.provision, LA.scope, Literal("private")))
    elif mutation == "wrong_range":
        data.set((assertion, LA.object, FX.institution))
    elif mutation == "type_instance":
        data.add((LA.Institution, RDF.type, LA.Institution))
        data.add((LA.Institution, RDF.type, OWL.Class))
    original = [fingerprint(graph) for graph in (data, shapes, schema)]
    # pySHACL itself adds two entailment triples to a supplied shapes graph.
    # Give the baseline its own copy; the wrapper promises input isolation.
    expected = validate(data, shacl_graph=shapes + Graph(), ont_graph=schema, inference="rdfs", advanced=True)
    actual = validation.validate_graph(data, shapes, schema)
    assert bool(expected[0]) is (mutation is None)
    assert actual[0] == expected[0]
    assert isomorphic(actual[1], expected[1])
    assert [fingerprint(graph) for graph in (data, shapes, schema)] == original


def test_parse_work_scales_with_query_programs_and_revalidates_changed_evidence(monkeypatch):
    data, shapes, schema = inputs()
    calls = parse_calls(monkeypatch)
    executions = []
    original_query = Graph.query

    def counted_query(graph, query, *args, **kwargs):
        executions.append(query)
        return original_query(graph, query, *args, **kwargs)

    monkeypatch.setattr(Graph, "query", counted_query)
    assert validate(data, shacl_graph=shapes, ont_graph=schema, inference="rdfs", advanced=True)[0]
    baseline_calls = len(calls)
    baseline_programs = set(calls)
    baseline_executions = len(executions)
    calls.clear()
    executions.clear()
    assert validation.validate_graph(data, shapes, schema)[0]
    assert set(calls) == baseline_programs
    assert len(calls) == len(baseline_programs) < baseline_calls
    assert len(executions) == baseline_executions  # Every focus-node query still executes.
    # The second invocation must compile independently and inspect current data.
    data.remove((FX["version-link-a"], LA.evidence, None))
    calls.clear()
    assert not validation.validate_graph(data, shapes, schema)[0]
    assert calls and len(calls) == len(set(calls))


def test_release_check_data_cannot_bypass_prepared_query_validation(monkeypatch):
    releases = load_module("releases")
    calls = parse_calls(monkeypatch)
    # Empty graphs exercise the real 135-class schema validation without inventing
    # reviewed records, credentials, permissions or a publication authorization.
    result = releases.check_data({"structure": Graph(), "jurisprudence": Graph()}, ONTOLOGY, {"verified": False})
    assert result["assertions"] == 0
    assert calls and len(calls) == len(set(calls))


def test_bindings_and_graph_mutation_are_never_cached(monkeypatch):
    graph = validation._ValidationGraph()
    graph.add((EX.first, EX.value, Literal("first")))
    graph.add((EX.second, EX.value, Literal("second")))
    query = "SELECT ?value WHERE { $this ex:value ?value . }"
    calls = parse_calls(monkeypatch)
    options = {"initNs": {"ex": EX}}
    assert list(graph.query(query, initBindings={"this": EX.first}, **options)) == [(Literal("first"),)]
    assert list(graph.query(query, initBindings={"this": EX.second}, **options)) == [(Literal("second"),)]
    graph.remove((EX.first, EX.value, None))
    assert list(graph.query(query, initBindings={"this": EX.first}, **options)) == []
    graph.add((EX.first, EX.value, Literal("corrected")))
    assert list(graph.query(query, initBindings={"this": EX.first}, **options)) == [(Literal("corrected"),)]
    assert calls == [query]


def test_namespace_and_base_changes_select_current_meaning(monkeypatch):
    graph = validation._ValidationGraph()
    first, second = Namespace("https://synthetic.invalid/first/"), Namespace("https://synthetic.invalid/second/")
    for namespace, text in ((first, "first"), (second, "second")):
        graph.add((namespace.item, namespace.property, Literal(text)))
    calls = parse_calls(monkeypatch)
    query = "SELECT ?value WHERE { ex:item ex:property ?value . }"
    for namespace, text in ((first, "first"), (second, "second")):
        assert list(graph.query(query, initNs={"ex": namespace})) == [(Literal(text),)]
    graph.bind("ex", first, replace=True)
    assert list(graph.query(query)) == [(Literal("first"),)]
    assert list(graph.query(query, initNs={})) == [(Literal("first"),)]
    graph.bind("ex", second, replace=True)
    assert list(graph.query(query)) == [(Literal("second"),)]
    relative = "SELECT ?value WHERE { <item> <property> ?value . }"
    for namespace, text in ((first, "first"), (second, "second")):
        assert list(graph.query(relative, base=str(namespace))) == [(Literal(text),)]
    assert len(calls) == 6  # Four namespace contexts, two base URIs; {} reuses graph prefixes.


def test_prepared_programs_are_local_to_each_graph(monkeypatch):
    first, second = validation._ValidationGraph(), validation._ValidationGraph()
    query = "SELECT ?value WHERE { ?item ?property ?value . }"
    first.add((EX.item, EX.value, Literal("first")))
    second.add((EX.item, EX.value, Literal("second")))
    calls = parse_calls(monkeypatch)
    assert list(first.query(query)) == [(Literal("first"),)]
    assert list(second.query(query)) == [(Literal("second"),)]
    assert calls == [query, query]
    assert first._prepared_queries is not second._prepared_queries


def test_parallel_graphs_keep_their_programs_and_results_isolated():
    barrier = Barrier(4)
    query = "SELECT ?value WHERE { $this ex:value ?value . }"

    def worker(index):
        graph = validation._ValidationGraph()
        graph.add((EX.item, EX.value, Literal(index)))
        barrier.wait(timeout=10)
        for _ in range(3):
            assert list(graph.query(query, initNs={"ex": EX}, initBindings={"this": EX.item})) == [(Literal(index),)]
        return graph

    with ThreadPoolExecutor(max_workers=4) as pool:
        graphs = list(pool.map(worker, range(4)))
    assert all(len(graph._prepared_queries) == 1 for graph in graphs)
    assert len({id(next(iter(graph._prepared_queries.values()))) for graph in graphs}) == 4


def test_cache_capacity_falls_back_without_skipping_queries(monkeypatch):
    monkeypatch.setattr(validation, "_MAX_QUERIES", 2)
    graph = validation._ValidationGraph()
    calls = parse_calls(monkeypatch)
    queries = [f"SELECT ({index} AS ?value) WHERE {{}}" for index in range(3)]
    for index in (0, 1, 2, 2, 0):
        assert list(graph.query(queries[index])) == [(Literal(index),)]
    assert len(graph._prepared_queries) == 2
    assert calls == [queries[0], queries[1], queries[2], queries[2]]


def test_aggregate_cache_text_budget_is_bounded_and_existing_programs_still_work(monkeypatch):
    graph = validation._ValidationGraph()
    first, second = "SELECT (1 AS ?value) WHERE {}", "SELECT (2 AS ?value) WHERE {}"
    options = {"initNs": {"ex": EX}}
    first_size = len(first) + len("ex") + len(str(EX))
    monkeypatch.setattr(validation, "_MAX_CACHE_CHARACTERS", first_size)
    calls = parse_calls(monkeypatch)
    assert list(graph.query(first, **options)) == [(Literal(1),)]
    assert list(graph.query(second, **options)) == [(Literal(2),)]
    assert list(graph.query(first, **options)) == [(Literal(1),)]
    assert list(graph.query(second, **options)) == [(Literal(2),)]
    assert calls == [first, second, second]
    assert len(graph._prepared_queries) == 1
    assert graph._cache_characters == first_size


@pytest.mark.parametrize("fallback", [
    "length", "namespaces", "namespace_text", "base_length", "processor", "option", "prepared",
])
def test_unsupported_or_large_inputs_retain_native_query_behavior(monkeypatch, fallback):
    graph = validation._ValidationGraph()
    query = "SELECT (1 AS ?value) WHERE {}"
    options = {}
    if fallback == "length":
        monkeypatch.setattr(validation, "_MAX_QUERY_LENGTH", 10)
    elif fallback == "namespaces":
        monkeypatch.setattr(validation, "_MAX_NAMESPACES", 1)
        options["initNs"] = {"a": EX, "b": LA}
    elif fallback == "namespace_text":
        monkeypatch.setattr(validation, "_MAX_QUERY_LENGTH", 128)
        options["initNs"] = {"ex": "urn:synthetic:" + "a" * 128}
    elif fallback == "base_length":
        monkeypatch.setattr(validation, "_MAX_QUERY_LENGTH", 128)
        options["initNs"] = {"ex": EX}
        options["base"] = "https://synthetic.invalid/" + "a" * 128
    elif fallback == "processor":
        options["processor"] = processor.SPARQLProcessor(graph)
    elif fallback == "option":
        options["DEBUG"] = False
    elif fallback == "prepared":
        query = processor.prepareQuery(query)
    calls = parse_calls(monkeypatch)
    assert list(graph.query(query, **options)) == [(Literal(1),)]
    assert list(graph.query(query, **options)) == [(Literal(1),)]
    assert not graph._prepared_queries
    assert len(calls) == (0 if fallback == "prepared" else 2)
