"""Bind immutable identifiers in native RDFS rules, with no global monkeypatch.

The rule bytecode, closure cycles, inference writes and SHACL checks stay native.
Only the repeated DefinedNamespace attribute resolution is replaced with reads
from immutable tuples of the very same URIRef objects. Unknown programs or graph
adapters retain the ordinary pySHACL path.
"""

from collections import namedtuple
from importlib.metadata import version
from types import FunctionType

from owlrl import DeductiveClosure
from pyshacl import validate as native_validate
from pyshacl.inference import CustomRDFSSemantics
from pyshacl.validator import Validator
from rdflib import RDF, RDFS

_RDF_NAMES = ('type', 'Property')
_RDFS_NAMES = ('Resource', 'domain', 'range', 'subPropertyOf', 'Class', 'subClassOf',
               'ContainerMembershipProperty', 'member', 'Datatype', 'Literal')
_RULE_NAMES = {'store_triple', 'graph', 'triples', 'RDF', 'RDFS', *_RDF_NAMES, *_RDFS_NAMES}
_QUALIFIED_DEPENDENCIES = {'pyshacl': '0.40.1', 'owlrl': '7.6.2', 'rdflib': '7.6.0'}


def bind_rule_identifiers(rules):
    """Copy the dependency's existing function with private constant bindings."""
    if (type(rules) is not FunctionType or rules.__module__ != 'owlrl.RDFSClosure'
            or set(rules.__code__.co_names) != _RULE_NAMES
            or rules.__code__.co_argcount != 3 or rules.__code__.co_kwonlyargcount
            or rules.__code__.co_flags & 12 or rules.__closure__ is not None
            or rules.__globals__.get('RDF') is not RDF or rules.__globals__.get('RDFS') is not RDFS
            or rules.__defaults__ or rules.__kwdefaults__):
        return None
    globals_copy = dict(rules.__globals__)
    for name, fields in (('RDF', _RDF_NAMES), ('RDFS', _RDFS_NAMES)):
        namespace = globals_copy[name]
        globals_copy[name] = namedtuple('Bound' + name, fields)(*(getattr(namespace, field) for field in fields))
    # Reuse the native function's code object; no copied/reimplemented rules,
    # generated source, eval, package mutation or cached inference is involved.
    return FunctionType(rules.__code__, globals_copy, rules.__name__)


_bound_rules = bind_rule_identifiers(CustomRDFSSemantics.rules)


class IdentifierBoundRDFS(CustomRDFSSemantics):
    rules = _bound_rules or CustomRDFSSemantics.rules


def validator_for(graph_type):
    class LocalValidator(Validator):
        @classmethod
        def _run_pre_inference(cls, target_graph, inference_option,
                               destination_graph_identifier=None, logger=None):
            if (_bound_rules is not None and inference_option == 'rdfs'
                    and not target_graph.is_oxigraph and not target_graph.is_multigraph()
                    and type(target_graph.impl) is graph_type):
                # Same CustomRDFSSemantics ancestry and DeductiveClosure defaults
                # as pySHACL; each call creates a fresh engine over this graph.
                # Native pySHACL ignores destination identifiers on single graphs.
                DeductiveClosure(IdentifierBoundRDFS).expand(target_graph.impl)
                return
            return super()._run_pre_inference(target_graph, inference_option,
                                               destination_graph_identifier, logger)
    return LocalValidator


def validate_for(graph_type):
    """Keep pySHACL's entire entry point, using one private validator class.

    Its imports, parsing, options, shape initialization, advanced rules, report
    generation and error handling execute as before. Every invocation still
    creates its own validator. Other library users see the unmodified globals.
    """
    if (any(version(name) != supported for name, supported in _QUALIFIED_DEPENDENCIES.items())
            or type(native_validate) is not FunctionType
            or native_validate.__globals__.get('Validator') is not Validator
            or 'Validator' not in native_validate.__code__.co_names):
        return native_validate
    globals_copy = {**native_validate.__globals__, 'Validator': validator_for(graph_type)}
    result = FunctionType(native_validate.__code__, globals_copy, native_validate.__name__,
                          native_validate.__defaults__, native_validate.__closure__)
    result.__kwdefaults__ = native_validate.__kwdefaults__
    return result
