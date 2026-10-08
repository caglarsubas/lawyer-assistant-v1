"""Fresh SHACL validation with bounded reuse of syntax, never verdicts.

Only query syntax/algebra is reused, never query results or validation decisions.
Frozen SHACL parser syntax is bounded and shared; mutable translated programs,
memory graphs and their query bindings belong to one validation invocation.
Ontology Turtle syntax is keyed by freshly read bytes and base URIs; each caller
receives an independent graph with fresh blank nodes, without inferred triples.
Exact triple membership uses a bounded index in the invocation's own Memory
store. Inference, source reads and every SHACL query still execute afresh.
"""
from __future__ import annotations

from collections import OrderedDict
from threading import Lock

from pyparsing import ParseResults
from pyshacl import validate
from rdflib import BNode, Graph, Literal, URIRef, Variable
from rdflib.plugins.sparql import prepareQuery, processor
from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.parserutils import CompValue, Expr
from rdflib.plugins.stores.memory import Memory

_MAX_QUERIES = 128
_MAX_QUERY_LENGTH = 64 * 1024
_MAX_NAMESPACES = 128
_MAX_CACHE_CHARACTERS = 1024 * 1024
_MAX_GRAPH_CACHE_ENTRIES = 4
_MAX_GRAPH_SOURCE_BYTES = 512 * 1024
_MAX_GRAPH_FILES = 32
_MAX_GRAPH_TRIPLES = 10_000
_MAX_MEMBERSHIP_TRIPLES = 16_384
_MAX_SYNTAX_ENTRIES = 64
_MAX_SYNTAX_BYTES = 1024 * 1024
_MAX_SYNTAX_NODES = 32_768
_MAX_PROGRAM_NODES = 4096


def _freeze_syntax(value, nodes):
    """Known parser nodes only; never retain an executable program or its context."""
    nodes[0] += 1
    if nodes[0] > _MAX_PROGRAM_NODES:
        raise ValueError('Parser tree exceeds retention bound')
    if type(value) in (CompValue, Expr):
        allowed = {'name', '_evalfn'} if type(value) is Expr else {'name'}
        if set(value.__dict__) - allowed:
            raise ValueError('Unknown parser state')
        function = None
        if type(value) is Expr and value._evalfn:
            if getattr(value._evalfn, '__self__', None) is not value:
                raise ValueError('Unknown parser evaluator')
            function = value._evalfn.__func__
        return ('expr' if type(value) is Expr else 'comp', value.name, function,
                tuple((key, _freeze_syntax(item, nodes)) for key, item in value.items()))
    if type(value) is ParseResults:
        # Named ParseResults may contain aliases to mutable nodes. Keep native
        # parsing rather than changing alias/translation behavior we do not model.
        if list(value.items()):
            raise ValueError('Named parser results use native preparation')
        return ('parse', tuple(_freeze_syntax(item, nodes) for item in value))
    if type(value) in (list, tuple):
        return ('list' if type(value) is list else 'tuple', tuple(_freeze_syntax(item, nodes) for item in value))
    if type(value) is BNode:
        return ('blank', str(value))
    if type(value) is Literal:
        return ('literal', str(value), value.language, value.datatype)
    if type(value) in (str, int, float, bool, type(None), URIRef, Variable):
        return ('atom', value)
    raise ValueError('Unsupported parser node')


def _restore_syntax(item, blanks):
    tag = item[0]
    if tag == 'atom':
        return item[1]
    if tag == 'blank':
        if item[1] not in blanks:
            blanks[item[1]] = BNode()
        return blanks[item[1]]
    if tag == 'literal':
        return Literal(item[1], lang=item[2], datatype=item[3], normalize=False)
    if tag in ('comp', 'expr'):
        values = {key: _restore_syntax(value, blanks) for key, value in item[3]}
        return Expr(item[1], item[2], **values) if tag == 'expr' else CompValue(item[1], **values)
    values = [_restore_syntax(value, blanks) for value in item[1]]
    return ParseResults(values) if tag == 'parse' else values if tag == 'list' else tuple(values)


class _SHACLSyntaxCache:
    """Bounded immutable parser syntax; translate anew for each scratch graph.

    Only validate_graph opts in. Direct/custom graph queries keep the ordinary
    per-graph preparation path. The cache has no data, inferred triples, results,
    signatures, source identities, permissions or validation verdicts.
    """

    def __init__(self):
        self._entries = OrderedDict()
        self._bytes = self._nodes = 0
        self._lock = Lock()

    def parse(self, query):
        size = len(query.encode())
        if size > _MAX_SYNTAX_BYTES or len(query) > _MAX_QUERY_LENGTH:
            return processor.parseQuery(query)
        with self._lock:
            entry = self._entries.get(query)
            if entry is not None:
                self._entries.move_to_end(query)
                return _restore_syntax(entry[0], {})
            parsed, nodes = processor.parseQuery(query), [0]
            try:
                frozen = _freeze_syntax(parsed, nodes)
            except (ValueError, RecursionError):
                return parsed
            if (not _MAX_SYNTAX_ENTRIES or size > _MAX_SYNTAX_BYTES
                    or nodes[0] > _MAX_SYNTAX_NODES):
                return parsed
            self._entries[query] = (frozen, size, nodes[0])
            self._bytes += size
            self._nodes += nodes[0]
            while (len(self._entries) > _MAX_SYNTAX_ENTRIES or self._bytes > _MAX_SYNTAX_BYTES
                   or self._nodes > _MAX_SYNTAX_NODES):
                _, (_, evicted_bytes, evicted_nodes) = self._entries.popitem(last=False)
                self._bytes -= evicted_bytes
                self._nodes -= evicted_nodes
            return parsed

    def prepare(self, query, namespaces, base):
        program = translateQuery(self.parse(query), base, namespaces)
        program._original_args = (query, namespaces, base)
        return program


_shacl_syntax = _SHACLSyntaxCache()


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


class _ValidationMemory(Memory):
    """Exact membership only, for one private scratch graph; no shared state.

    Native RDFS repeatedly probes the same complete triples through RDFLib's
    pattern iterator. Store-level writes maintain this index, including addN and
    direct store.add. Removal, quoted/different contexts or the size limit disable
    it permanently for this invocation, preserving the native fallback.
    """

    def __init__(self):
        super().__init__()
        self._exact = set()
        self._context = None

    def add(self, triple, context, quoted=False):
        super().add(triple, context, quoted=quoted)
        if self._exact is not None:
            if quoted or self._context is not None and context is not self._context:
                self._exact = None
            else:
                self._context = context
                self._exact.add(triple)
                if len(self._exact) > _MAX_MEMBERSHIP_TRIPLES:
                    self._exact = None

    def remove(self, triple, context=None):
        self._exact = None
        super().remove(triple, context=context)

    def contains_exact(self, triple, context):
        if self._exact is not None and context is self._context and all(term is not None for term in triple):
            return tuple(triple) in self._exact
        return None


class _ValidationGraph(Graph):
    """Private memory-only scratch graph, not a general store/query adapter."""

    def __init__(self, *, syntax_cache=None):
        super().__init__(store=_ValidationMemory(), bind_namespaces="core")
        self._prepared_queries = {}
        self._cache_characters = 0
        self._syntax_cache = syntax_cache

    def __contains__(self, triple):
        if len(triple) == 3:
            result = self.store.contains_exact(triple, self)
            if result is not None:
                return result
        return super().__contains__(triple)

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
                    prepared = (self._syntax_cache.prepare(query_object, namespaces, base) if self._syntax_cache
                                else prepareQuery(query_object, initNs=namespaces, base=base))
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
    scratch = _copy_into(data, _ValidationGraph(syntax_cache=_shacl_syntax))
    # pySHACL also adds system triples to its shapes graph during initialization.
    shape_copy = _copy_into(shapes, Graph(bind_namespaces="core"))
    # inplace applies only to this private clone so inference cannot alter the
    # original release data, and pySHACL retains the prepared-query-aware graph.
    return validate(scratch, shacl_graph=shape_copy, ont_graph=schema,
                    inference="rdfs", advanced=True, inplace=True)
