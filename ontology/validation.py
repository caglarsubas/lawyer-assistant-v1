"""Fresh SHACL validation with bounded reuse of syntax, never verdicts.

Only query syntax/algebra is reused, never query results or validation decisions.
The memory graph and its bounded cache belong to a single validation invocation.
Ontology Turtle syntax is keyed by freshly read bytes and base URIs; each caller
receives an independent graph with fresh blank nodes, without inferred triples.
"""
from __future__ import annotations

from collections import OrderedDict
from threading import Lock

from pyshacl import validate
from rdflib import BNode, Graph
from rdflib.plugins.sparql import prepareQuery

_MAX_QUERIES = 128
_MAX_QUERY_LENGTH = 64 * 1024
_MAX_NAMESPACES = 128
_MAX_CACHE_CHARACTERS = 1024 * 1024
_MAX_GRAPH_CACHE_ENTRIES = 4
_MAX_GRAPH_SOURCE_BYTES = 512 * 1024
_MAX_GRAPH_FILES = 32
_MAX_GRAPH_TRIPLES = 10_000


class _OntologySyntaxCache:
    """Only used for local ontology definitions, never matter or release records."""

    def __init__(self):
        self._entries = OrderedDict()
        self._lock = Lock()

    def load(self, paths):
        # Read on EVERY invocation. A pathname, mtime, signature or previous
        # success is not evidence that these are still the same source bytes.
        sources = tuple((path.absolute().as_uri(), path.read_bytes()) for path in paths)
        return self.parse(sources)

    def parse(self, sources):
        """Consume captured ontology bytes; callers retain all integrity checks."""
        cacheable = (len(sources) <= _MAX_GRAPH_FILES
                     and sum(len(uri.encode()) + len(raw) for uri, raw in sources) <= _MAX_GRAPH_SOURCE_BYTES)
        frozen = None
        if cacheable:
            with self._lock:
                frozen = self._entries.get(sources)
                if frozen is not None:
                    self._entries.move_to_end(sources)
        if frozen is None:
            graph = Graph()
            for uri, raw in sources:
                graph.parse(data=raw, publicID=uri, format="turtle")
            if cacheable and len(graph) <= _MAX_GRAPH_TRIPLES:
                frozen = (tuple(graph), tuple(graph.namespaces()))
                with self._lock:
                    self._entries[sources] = frozen
                    self._entries.move_to_end(sources)
                    while len(self._entries) > _MAX_GRAPH_CACHE_ENTRIES:
                        self._entries.popitem(last=False)
            return graph
        # Never return a mutable graph held by the cache. Remap anonymous nodes
        # just as a fresh parse would, including nodes shared by RDF lists.
        graph, blank_nodes = Graph(), {}
        for prefix, namespace in frozen[1]:
            graph.bind(prefix, namespace, override=True, replace=True)
        for triple in frozen[0]:
            graph.add(tuple(blank_nodes.setdefault(term, BNode()) if isinstance(term, BNode) else term
                            for term in triple))
        return graph


_ontology_syntax = _OntologySyntaxCache()


def load_ontology_graph(paths):
    return _ontology_syntax.load(paths)


def parse_ontology_graph(sources):
    return _ontology_syntax.parse(tuple(sources))


class _ValidationGraph(Graph):
    """Private memory-only scratch graph, not a general store/query adapter."""

    def __init__(self):
        super().__init__(bind_namespaces="core")
        self._prepared_queries = {}
        self._cache_characters = 0

    def query(self, query_object, processor="sparql", result="sparql", initNs=None,
              initBindings=None, use_store_provided=True, **kwargs):
        # Preserve RDFLib's fallback for prepared/custom queries or unknown options.
        # This graph always has its own Memory store; no remote/store query is replaced.
        if (isinstance(query_object, str) and processor == "sparql"
                and len(query_object) <= _MAX_QUERY_LENGTH and set(kwargs) <= {"base"}):
            namespaces = dict(initNs or self.namespaces())
            base = kwargs.get("base")
            namespace_size = sum(len(str(prefix)) + len(str(uri)) for prefix, uri in namespaces.items())
            if (len(namespaces) <= _MAX_NAMESPACES
                    and namespace_size <= _MAX_QUERY_LENGTH
                    and (base is None or isinstance(base, str) and len(base) <= _MAX_QUERY_LENGTH)):
                key = (query_object, tuple(namespaces.items()), base)
                try:
                    prepared = self._prepared_queries.get(key)
                except TypeError:
                    # Unusual, unhashable namespace values retain native behavior.
                    prepared = None
                    key = None
                size = len(query_object) + namespace_size + len(base or "")
                if (prepared is None and key is not None and len(self._prepared_queries) < _MAX_QUERIES
                        and self._cache_characters + size <= _MAX_CACHE_CHARACTERS):
                    prepared = prepareQuery(query_object, initNs=namespaces, base=base)
                    self._prepared_queries[key] = prepared
                    self._cache_characters += size
                if prepared is not None:
                    query_object = prepared
        return super().query(query_object, processor, result, initNs, initBindings,
                             use_store_provided, **kwargs)


def _copy_into(source: Graph, target: Graph) -> Graph:
    # Match pySHACL's normal graph clone, including prefix replacement semantics.
    for prefix, namespace in source.namespaces():
        target.bind(prefix, namespace, override=True, replace=True)
    target += source
    return target


def validate_graph(data: Graph, shapes: Graph, schema: Graph):
    """Run the full production policy without modifying any caller-owned graph."""
    scratch = _copy_into(data, _ValidationGraph())
    # pySHACL also adds system triples to its shapes graph during initialization.
    shape_copy = _copy_into(shapes, Graph(bind_namespaces="core"))
    # inplace applies only to this private clone so inference cannot alter the
    # original release data, and pySHACL retains the prepared-query-aware graph.
    return validate(scratch, shacl_graph=shape_copy, ont_graph=schema,
                    inference="rdfs", advanced=True, inplace=True)
