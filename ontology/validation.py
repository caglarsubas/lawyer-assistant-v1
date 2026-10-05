"""Fresh SHACL validation with per-call reuse of parsed SPARQL programs.

Only query syntax/algebra is reused, never query results or validation decisions.
The memory graph and its bounded cache belong to a single validation invocation.
"""
from __future__ import annotations

from pyshacl import validate
from rdflib import Graph
from rdflib.plugins.sparql import prepareQuery

_MAX_QUERIES = 128
_MAX_QUERY_LENGTH = 64 * 1024
_MAX_NAMESPACES = 128
_MAX_CACHE_CHARACTERS = 1024 * 1024


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
