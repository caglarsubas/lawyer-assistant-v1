"""Syntax reuse must not retain mutable graphs, inferred facts or approval state."""

import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from rdflib import RDF, RDFS, BNode, Graph, Literal, Namespace, URIRef
from rdflib.compare import isomorphic
from rdflib.plugins.parsers.notation3 import TurtleParser
from test_serving_releases import bundle, serving
from test_serving_releases import trust as trust_fixture
from test_validation_queries import ONTOLOGY, load_module

EX = Namespace("urn:synthetic:syntax:")
validation = load_module("validation")
trust = trust_fixture


def parse_calls(monkeypatch):
    calls = []
    original = TurtleParser.parse

    def counted(self, source, graph, *args, **kwargs):
        calls.append(source.getPublicId())
        return original(self, source, graph, *args, **kwargs)

    monkeypatch.setattr(TurtleParser, "parse", counted)
    return calls


def source(tmp_path, name="schema.ttl", raw=b'<item> <value> [ <nested> "first" ] .'):
    path = tmp_path / name
    path.write_bytes(raw)
    return path


def test_warm_parse_matches_native_namespaces_relative_iris_and_blank_nodes(tmp_path, monkeypatch):
    paths = [source(tmp_path, "one.ttl", b'@prefix ex: <urn:one:> . ex:a ex:b ( <relative> "one" ) .'),
             source(tmp_path, "two.ttl", b'@prefix ex: <urn:two:> . ex:a ex:b [ ex:c "two" ] .')]
    expected = Graph()
    for path in paths:
        expected.parse(path, format="turtle")
    calls, cache = parse_calls(monkeypatch), validation._OntologySyntaxCache()
    first, second = cache.load(paths), cache.load(paths)
    assert len(calls) == len(paths)
    for graph in (first, second):
        assert isomorphic(graph, expected)
        assert dict(graph.namespaces()) == dict(expected.namespaces())
        assert graph.base == expected.base
    first_blanks = {term for triple in first for term in triple if isinstance(term, BNode)}
    second_blanks = {term for triple in second for term in triple if isinstance(term, BNode)}
    assert first_blanks and second_blanks and first_blanks.isdisjoint(second_blanks)
    # Neither mutations nor inferred triples may enter the stored syntax.
    first.add((EX.a, RDF.type, EX.Inferred))
    second.remove((None, None, None))
    third = cache.load(paths)
    assert isomorphic(third, expected)
    assert len(calls) == len(paths)


def test_same_size_same_mtime_edit_reparses_current_bytes(tmp_path, monkeypatch):
    path, cache = source(tmp_path), validation._OntologySyntaxCache()
    calls = parse_calls(monkeypatch)
    before = path.stat()
    first = cache.load([path])
    path.write_bytes(path.read_bytes().replace(b"first", b"later"))
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    second = cache.load([path])
    assert len(calls) == 2 and not isomorphic(first, second)
    assert Literal("later") in set(second.objects())


def test_identical_bytes_at_different_bases_do_not_share_resolved_iris(tmp_path):
    cache = validation._OntologySyntaxCache()
    first_dir, second_dir = tmp_path / "one", tmp_path / "two"
    first_dir.mkdir()
    second_dir.mkdir()
    paths = [source(directory) for directory in (first_dir, second_dir)]
    for path in paths:
        expected = Graph().parse(path, format="turtle")
        assert isomorphic(cache.load([path]), expected)
        assert isomorphic(cache.load([path]), expected)
    assert len(cache._entries) == 2


@pytest.mark.parametrize("change", ["missing", "unreadable", "invalid"])
def test_previous_success_does_not_mask_read_or_parse_failure(tmp_path, monkeypatch, change):
    path, cache = source(tmp_path), validation._OntologySyntaxCache()
    cache.load([path])
    if change == "missing":
        path.unlink()
        error = FileNotFoundError
    elif change == "unreadable":
        def denied(_path):
            raise PermissionError("TEST ONLY access denied")
        monkeypatch.setattr(Path, "read_bytes", denied)
        error = PermissionError
    else:
        path.write_bytes(b"this is not turtle")
        error = SyntaxError
    with pytest.raises(error):
        cache.load([path])


@pytest.mark.parametrize("limit,value", [
    ("_MAX_GRAPH_SOURCE_BYTES", 1), ("_MAX_GRAPH_FILES", 0), ("_MAX_GRAPH_TRIPLES", 1),
])
def test_oversized_templates_parse_normally_without_retention(tmp_path, monkeypatch, limit, value):
    path, cache = source(tmp_path), validation._OntologySyntaxCache()
    monkeypatch.setattr(validation, limit, value)
    calls = parse_calls(monkeypatch)
    first, second = cache.load([path]), cache.load([path])
    assert isomorphic(first, second)
    assert len(calls) == 2 and not cache._entries


def test_entry_budget_evicts_least_recently_used_template(tmp_path, monkeypatch):
    cache = validation._OntologySyntaxCache()
    monkeypatch.setattr(validation, "_MAX_GRAPH_CACHE_ENTRIES", 2)
    paths = [source(tmp_path, f"{i}.ttl") for i in range(3)]
    calls = parse_calls(monkeypatch)
    for index in (0, 1, 0, 2, 0):
        cache.load([paths[index]])
    assert len(calls) == 3 and len(cache._entries) == 2
    cache.load([paths[1]])
    assert len(calls) == 4 and len(cache._entries) == 2


def test_concurrent_readers_receive_isolated_graphs(tmp_path):
    cache, path = validation._OntologySyntaxCache(), source(tmp_path)
    expected = cache.load([path])
    def read(index):
        graph = cache.load([path])
        assert isomorphic(graph, expected)
        graph.add((EX.reader, EX["index"], Literal(index)))
        return graph
    with ThreadPoolExecutor(max_workers=4) as pool:
        graphs = list(pool.map(read, range(12)))
    for index, graph in enumerate(graphs):
        assert list(graph.objects(EX.reader, EX["index"])) == [Literal(index)]
    assert isomorphic(cache.load([path]), expected)


def test_real_release_reuses_only_syntax_and_rechecks_changed_schema_and_shapes(tmp_path, monkeypatch):
    releases = load_module("releases")
    ontology = tmp_path / "ontology"
    shutil.copytree(ONTOLOGY, ontology)
    calls = parse_calls(monkeypatch)
    executions = []
    original = releases._validation.validate_graph
    def checked(*args):
        executions.append(True)
        return original(*args)
    monkeypatch.setattr(releases._validation, "validate_graph", checked)
    graphs, review = {"structure": Graph(), "jurisprudence": Graph()}, {"verified": False}
    assert releases.check_data(graphs, ontology, review)["assertions"] == 0
    initial_parses = len(calls)
    assert initial_parses == len(list((ontology / "modules").glob("*.ttl"))) + 2
    assert releases.check_data(graphs, ontology, review)["assertions"] == 0
    assert len(calls) == initial_parses and len(executions) == 2
    # A new type axiom must affect fresh RDFS inference, despite a warm schema.
    module = ontology / "modules" / "foundation.ttl"
    module.write_bytes(module.read_bytes() + b'\n<urn:test:NewClass> '
                       b'<http://www.w3.org/2000/01/rdf-schema#subClassOf> '
                       b'<https://lawyer-assistant.local/ontology/SourceArtifact> .\n')
    graphs["structure"].add((URIRef("urn:test:record"), RDF.type, URIRef("urn:test:NewClass")))
    with pytest.raises(ValueError, match="Snapshot violates SHACL"):
        releases.check_data(graphs, ontology, review)
    assert len(calls) > initial_parses and len(executions) == 3
    graphs["structure"].remove((None, None, None))
    shapes = ontology / "shapes.ttl"
    shapes.write_bytes(shapes.read_bytes() + b'\n<urn:test:shape> a sh:NodeShape ; '
                       b'sh:targetNode <urn:test:record> ; sh:class <urn:test:Required> .\n')
    before = len(calls)
    with pytest.raises(ValueError, match="Snapshot violates SHACL"):
        releases.check_data(graphs, ontology, review)
    assert len(calls) == before + 1 and len(executions) == 4


def test_serving_code_import_is_stable_while_schema_files_remain_live(tmp_path, monkeypatch):
    from app.graph_release import _load_serving

    serving = _load_serving()
    assert _load_serving() is serving
    ontology = tmp_path / "ontology"
    shutil.copytree(ONTOLOGY, ontology)
    calls = parse_calls(monkeypatch)
    first = serving._release.load_schema(ontology)
    assert isomorphic(_load_serving()._release.load_schema(ontology), first)
    assert len(calls) == 10
    path = ontology / "domains.ttl"
    path.write_bytes(path.read_bytes() + b'\n<urn:test:class> a <http://www.w3.org/2000/01/rdf-schema#Class> .\n')
    assert (URIRef("urn:test:class"), RDF.type, RDFS.Class) in _load_serving()._release.load_schema(ontology)
    assert len(calls) == 20


def test_both_serving_families_reuse_schema_syntax_but_reparse_source_records(tmp_path, trust, monkeypatch):
    source = bundle(tmp_path, trust)
    result = serving._release.validate_bundle(source, trust[1])
    calls = parse_calls(monkeypatch)
    first = {family: serving._payload(source, result, family) for family in serving.FAMILIES}
    second = {family: serving._payload(source, result, family) for family in serving.FAMILIES}
    assert first == second
    assert len(calls) == 8  # Both source inputs are freshly parsed for each family, each time.
    assert all("/inputs/" in uri for uri in calls)  # No repeated ontology parsing.
