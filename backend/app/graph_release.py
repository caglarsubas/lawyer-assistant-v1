"""Independently verified, startup-pinned public graph release; no publication API."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from rdflib import RDF, RDFS, Graph, Literal, Namespace, URIRef

from .config import ROOT

LA = Namespace('https://lawyer-assistant.local/ontology/')
_temporal_spec = importlib.util.spec_from_file_location('lawyer_runtime_temporal', ROOT / 'ontology' / 'temporal.py')
temporal = importlib.util.module_from_spec(_temporal_spec)
_temporal_spec.loader.exec_module(temporal)



def _load_serving():
    spec = importlib.util.spec_from_file_location('lawyer_ontology_serving', ROOT / 'ontology' / 'serving.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pointer(root: Path) -> bytes:
    path = root / 'active.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
        raise ValueError('Invalid active release pointer')
    return path.read_bytes()


class RuntimeGraphRelease:
    """Publication integrity does not establish legal applicability to a matter."""

    def __init__(self, root: Path | None = None, trusted_key: Path | None = None,
                 authorization_guard=None):
        self.root = Path(root) if root else None
        self.trusted_key = Path(trusted_key) if trusted_key else None
        self.authorization_guard = authorization_guard
        self.info = None
        self._graphs = {}
        self._state = {'status': 'unconfigured', 'reason': 'Etkin, doğrulanmış graf sürümü yayımlanmadı.'}
        if not self.root:
            return
        try:
            if not (self.root / 'active.json').exists():
                return
            before = _pointer(self.root)
            if not self.trusted_key or not self.trusted_key.is_file() or self.trusted_key.is_symlink():
                raise ValueError('Missing independent review trust key')
            self._key_hash = hashlib.sha256(self.trusted_key.read_bytes()).hexdigest()
            info = _load_serving().load_active(self.root, self.trusted_key)
            if before != _pointer(self.root) or not info or not info['review']['verified']:
                raise ValueError('Release changed during validation')
            if not re.fullmatch('[0-9a-f]{64}', info['release_id']):
                raise ValueError('Invalid release identity')
            self._active_bytes = before
            self.info = info
            # A valid public signature cannot establish current private rights.
            with self.current_guard():
                pass
            # Verified source inputs are the independent allowlist for every returned edge.
            # Runtime RDF labels/metadata by themselves cannot establish source grounding.
            manifest_bytes = (info['bundle_path'] / 'manifest.json').read_bytes()
            if hashlib.sha256(manifest_bytes).hexdigest() != info['release_id']:
                raise ValueError('Verified manifest changed before source loading')
            manifest = json.loads(manifest_bytes)
            self.catalog_bytes = (info['bundle_path'] / 'ontology' / 'catalog.json').read_bytes()
            if hashlib.sha256(self.catalog_bytes).hexdigest() != manifest['files']['ontology/catalog.json']:
                raise ValueError('Verified catalog changed before source loading')
            for family in ('structure', 'jurisprudence'):
                raw = (info['bundle_path'] / 'inputs' / f'{family}.ttl').read_bytes()
                if hashlib.sha256(raw).hexdigest() != manifest['input_graphs_sha256'][family]:
                    raise ValueError('Verified graph changed before source loading')
                # Parse the exact captured bytes whose digest was verified, never reopen the path.
                self._graphs[family] = Graph().parse(data=raw, format='turtle')
            self._resources = Graph()
            assertions = {node for graph in self._graphs.values() for node in graph.subjects(RDF.type, LA.Assertion)}
            for graph in self._graphs.values():
                for triple in graph:
                    if triple[0] not in assertions:
                        self._resources.add(triple)
            self._state = {'status': 'verified', 'release_id': info['release_id'],
                           'ontology_sha256': info['ontology_sha256'],
                           'legal_review_verified': True,
                           'reason': 'İmzalı sürüm doğrulandı; somut olaya uygulanabilirlik ayrıca incelenmelidir.'}
            with self.current_guard():
                pass
        except Exception:
            self.info = None
            self._state = {'status': 'unavailable', 'reason': 'Graf sürümü, bağımsız inceleme anahtarı veya bütünlük denetimi doğrulanamadı.'}

    def status(self) -> dict:
        state = dict(self._state)
        if self.info:
            try:
                with self.current_guard():
                    pass
            except Exception:
                state.update(status='unavailable', reason='Graf sürümü, güncel yayın izni veya güven kaydı doğrulanamadı.')
        return state

    def _check_pointer(self):
        if (_pointer(self.root) != self._active_bytes
                or self.trusted_key.is_symlink()
                or hashlib.sha256(self.trusted_key.read_bytes()).hexdigest() != self._key_hash):
            raise ValueError('Release activation or trust changed')

    @contextmanager
    def current_guard(self):
        """Keep private authorization current across a bounded read/use operation."""
        if not self.info or self.authorization_guard is None:
            raise ValueError('Current private release authorization is required')
        try:
            self._check_pointer()
            with self.authorization_guard(self.info, 'read'):
                self._check_pointer()
                yield self.info
                self._check_pointer()
        except Exception:
            # Private ledger identifiers and error details never reach callers.
            raise ValueError('Current private release authorization is unavailable') from None

    def require_current(self) -> dict:
        if self.status()['status'] != 'verified':
            raise ValueError('No current independently verified graph release')
        return self.info

    @staticmethod
    def _one(graph, node, predicate):
        values = set(graph.objects(node, predicate))
        return next(iter(values)) if len(values) == 1 else None

    @staticmethod
    def _instant(value):
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('A timezone is required')
        return parsed.astimezone(timezone.utc)

    def _eligible(self, family, assertion, *, as_of=None, known_at=None, history=False, _basis=False):
        graph = self._graphs[family]
        resources = getattr(self, '_resources', graph)
        one = self._one
        if ((assertion, RDF.type, LA.Assertion) not in graph
                or one(graph, assertion, LA.graphFamily) != Literal(family)
                or one(graph, assertion, LA.scope) != Literal('public')
                or one(graph, assertion, LA.synthetic) != Literal(False)
                or one(graph, assertion, LA.validityStatus) != Literal('known')):
            return False
        status = str(one(graph, assertion, LA.claimStatus))
        if status not in {'unreviewed', 'source_verified', 'legally_reviewed', 'contested', 'superseded'}:
            return False
        subject, target, predicate = (one(graph, assertion, p) for p in (LA.subject, LA.object, LA.predicate))
        if subject is None or target is None or predicate is None:
            return False
        for node in (subject, target):
            if (one(resources, node, LA.scope) != Literal('public')
                    or (node, LA.synthetic, Literal(True)) in resources):
                return False
        try:
            state = temporal.interval_state(graph, assertion, evidence_graph=resources)
            if (not temporal.valid_at(state, as_of, history=history)
                    or not temporal.reviewed_open(graph, assertion, state, known_at=known_at)):
                return False
            recorded = self._instant(one(graph, assertion, LA.recordedAt))
            if state['kind'] == 'open_ended' and state['checked_through'] > recorded.date():
                return False
            superseded_value = one(graph, assertion, LA.supersededAt)
            superseded = self._instant(superseded_value) if superseded_value is not None else None
            if superseded and superseded <= recorded:
                return False
            known = self._instant(known_at) if known_at is not None else None
            if known is not None and (recorded > known or (superseded and known >= superseded)):
                return False
            if status == 'legally_reviewed':
                reviewer = one(graph, assertion, LA.reviewer)
                reviewed = self._instant(one(graph, assertion, LA.reviewedAt))
                if reviewer is None or not str(reviewer).strip() or (known and reviewed > known):
                    return False
            if predicate in {LA.hasProvisionVersion, LA.applies, LA.interprets}:
                if ((target, RDF.type, LA.ProvisionVersion) not in resources
                        or one(resources, target, LA.versionResolution) != Literal('resolved')):
                    return False
                provision = one(resources, target, LA.versionOf)
                if provision is None or (provision, RDF.type, LA.Provision) not in resources:
                    return False
                if predicate == LA.hasProvisionVersion and subject != provision:
                    return False
                version_state = temporal.interval_state(resources, target)
                if not temporal.valid_at(version_state, as_of, history=history):
                    return False
                if predicate == LA.hasProvisionVersion and (
                        state['kind'] == 'open_ended' or version_state['kind'] == 'open_ended'):
                    if state != version_state:
                        return False
                if version_state['kind'] == 'open_ended' and not _basis:
                    # A standalone version label cannot establish an observed horizon.
                    supported = False
                    for basis_family, basis_graph in self._graphs.items():
                        candidates = set(basis_graph.subjects(LA.object, target))
                        if len(candidates) > 400:
                            return False
                        for basis in candidates:
                            if (one(basis_graph, basis, LA.predicate) == LA.hasProvisionVersion
                                    and one(basis_graph, basis, LA.claimStatus) == Literal('legally_reviewed')
                                    and self._eligible(basis_family, basis, as_of=as_of, known_at=known_at,
                                                       history=history, _basis=True)):
                                supported = True
                                break
                        if supported:
                            break
                    if not supported:
                        return False
        except (ValueError, TypeError):
            return False
        return any(self._evidence_eligible(resources, evidence)
                   for evidence in graph.objects(assertion, LA.evidence))

    def _evidence_eligible(self, resources, evidence):
        return temporal.public_evidence(resources, evidence)

    def validity_evidence(self, family, assertion):
        graph, resources, one = self._graphs[family], self._resources, self._one
        nodes = sorted(set(graph.objects(assertion, LA.validityEvidence)), key=str)
        if len(nodes) > 25000:
            raise ValueError('Validity evidence exceeds its bounded budget')
        result, characters = [], 0
        for evidence in nodes:
            if not self._evidence_eligible(resources, evidence):
                raise ValueError('Validity evidence is not eligible')
            text = str(one(resources, evidence, LA.quotedText))
            characters += len(text)
            if characters > 20000:
                raise ValueError('Validity evidence exceeds its reviewed span budget')
            artifact, representation = (one(resources, evidence, p) for p in (LA.artifact, LA.textRepresentation))
            result.append({
                'id': str(evidence), 'artifact_id': str(artifact), 'locator': str(one(resources, evidence, LA.locator)),
                'text': text, 'sha256': str(one(resources, artifact, LA.contentHash)),
                'text_representation_id': str(representation), 'text_sha256': str(one(resources, representation, LA.contentHash)),
                'locator_map_sha256': str(one(resources, representation, LA.locatorMapHash)),
                'start_offset': int(one(resources, evidence, LA.startOffset)),
                'end_offset': int(one(resources, evidence, LA.endOffset)),
                'grounding_status': 'verified_release_quote',
            })
        return result

    def project_search_hit(self, candidate: dict, *, as_of=None, authority_id=None) -> dict:
        """Admit exact signed evidence only; index labels are not source authority.

        Startup bundle validation proves these RDF quote/locator spans against
        the hash-linked original, extracted UTF-8 text and physical locator map.
        The caller checks current private authorization before and after search.
        Index-specific passage/document/version IDs never leave this boundary.
        """
        if not self.info or candidate.get('release_id') != self.info['release_id']:
            raise ValueError('Search candidate has no verified source release')
        resources, one = self._resources, self._one
        requested = authority_id or candidate.get('authority_id')
        matches = []
        visited = 0
        for artifact in resources.subjects(LA.contentHash, Literal(candidate.get('source_sha256'))):
            if (artifact, RDF.type, LA.SourceArtifact) not in resources:
                continue
            for evidence in resources.subjects(LA.artifact, artifact):
                visited += 1
                if visited > 25_000:
                    raise ValueError('Search evidence matching exceeds its bounded budget')
                if ((evidence, RDF.type, LA.EvidencePassage) not in resources
                        or not self._evidence_eligible(resources, evidence)
                        or str(one(resources, evidence, LA.locator)) != candidate.get('locator')
                        or str(one(resources, evidence, LA.quotedText)) != candidate.get('text')):
                    continue
                representation = one(resources, evidence, LA.textRepresentation)
                for family, graph in self._graphs.items():
                    for assertion in graph.subjects(LA.evidence, evidence):
                        visited += 1
                        if visited > 25_000:
                            raise ValueError('Search evidence matching exceeds its bounded budget')
                        endpoints = {str(one(graph, assertion, prop)) for prop in (LA.subject, LA.object)}
                        if (requested not in endpoints
                                or one(graph, assertion, LA.claimStatus) != Literal('legally_reviewed')
                                or not self._eligible(family, assertion, as_of=as_of)):
                            continue
                        matches.append((str(evidence), str(assertion), {
                            'passage_id': str(evidence), 'document_id': str(artifact),
                            'source_version_id': str(representation),
                            'source_sha256': str(one(resources, artifact, LA.contentHash)),
                            'text': str(one(resources, evidence, LA.quotedText)),
                            'locator': str(one(resources, evidence, LA.locator)),
                            'title': 'Doğrulanmış kaynak pasajı', 'source_url': None,
                            'authority_id': requested, 'release_id': self.info['release_id'],
                            'visibility': 'public', 'rights_status': 'permitted',
                            'review_status': 'legally_reviewed',
                            'valid_from': str(one(graph, assertion, LA.validFrom)),
                            'valid_to': (str(one(graph, assertion, LA.validTo))
                                         if one(graph, assertion, LA.validTo) is not None else None),
                            'validity_end_status': temporal.interval_state(graph, assertion, evidence_graph=resources)['kind'],
                            'validity_checked_through': (str(one(graph, assertion, LA.validityCheckedThrough))
                                                        if one(graph, assertion, LA.validityCheckedThrough) is not None else None),
                            'validity_evidence_ids': sorted(str(value) for value in graph.objects(assertion, LA.validityEvidence)),
                            'validity_evidence': self.validity_evidence(family, assertion),
                        }))
        if not matches:
            raise ValueError('Search candidate is outside the signed evidence and authority scope')
        # A search nomination cannot select arbitrary index metadata when a quote
        # has multiple evidenced links. Exact authority/date filters apply above.
        return min(matches, key=lambda item: (item[0], item[1]))[2]

    def matches(self, family: str, row: dict, *, as_of=None, known_at=None, history=False,
                entity_id=None, hops=1, relations=None, identifier=None, assertion_id=None, query=None) -> bool:
        """Compare returned evidence and relationship fields to the signed source graph."""
        if not self.info:
            return False
        graph = self._graphs[family]
        resources = getattr(self, '_resources', graph)
        assertion = URIRef(row.get('a', ''))
        if assertion_id:
            expected = assertion_id[1:-1] if assertion_id.startswith('<') and assertion_id.endswith('>') else assertion_id
            if str(assertion) != expected:
                return False
        if identifier:
            nodes = {URIRef(row.get('s', '')), URIRef(row.get('o', ''))}
            if not any(str(node) == identifier or identifier in {str(v) for v in resources.objects(node, LA.canonicalId)}
                       for node in nodes):
                return False
        if query and not any(query.lower() in str(row.get(prefix + 'Label', '')).lower() for prefix in ('s', 'o')):
            return False
        if not self._eligible(family, assertion, as_of=as_of, known_at=known_at, history=history):
            return False
        if relations and str(row.get('p', '')) not in {str(LA[relation]) for relation in relations}:
            return False
        fields = {'s': LA.subject, 'p': LA.predicate, 'o': LA.object, 'claimStatus': LA.claimStatus,
                  'validFrom': LA.validFrom, 'validTo': LA.validTo, 'validityEndStatus': LA.validityEndStatus,
                  'validityCheckedThrough': LA.validityCheckedThrough, 'recordedAt': LA.recordedAt,
                  'supersededAt': LA.supersededAt, 'reviewer': LA.reviewer, 'reviewedAt': LA.reviewedAt}
        for name, predicate in fields.items():
            def comparable(value):
                if name in {'recordedAt', 'supersededAt', 'reviewedAt'}:
                    try:
                        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
                        if parsed.tzinfo is not None:
                            return parsed.astimezone(timezone.utc).isoformat()
                    except ValueError:
                        pass
                return str(value)
            values = {comparable(value) for value in graph.objects(assertion, predicate)}
            if row.get(name) is None:
                if values:
                    return False
            elif comparable(row[name]) not in values:
                return False
        evidence = URIRef(row.get('evidence', ''))
        if ((assertion, LA.evidence, evidence) not in graph
                or not self._evidence_eligible(resources, evidence)):
            return False
        if entity_id:
            anchor = URIRef(entity_id[1:-1] if entity_id.startswith('<') and entity_id.endswith('>') else entity_id)
            endpoints = {URIRef(row['s']), URIRef(row['o'])}
            if anchor not in endpoints:
                if hops != 2:
                    return False
                found = False
                candidates = set()
                for property_ in (LA.subject, LA.object):
                    for adjacent in graph.subjects(property_, anchor):
                        candidates.add(adjacent)
                        if len(candidates) > 400:
                            return False  # Bounded fail-closed independent path verification.
                for adjacent in candidates:
                    if relations and str(self._one(graph, adjacent, LA.predicate)) not in {str(LA[r]) for r in relations}:
                        continue
                    adjacent_endpoints = {self._one(graph, adjacent, LA.subject), self._one(graph, adjacent, LA.object)}
                    if (adjacent_endpoints & endpoints and self._eligible(
                            family, adjacent, as_of=as_of, known_at=known_at, history=history)):
                        found = True
                        break
                if not found:
                    return False
        for prefix in ('s', 'o'):
            node = URIRef(row[prefix])
            resolution = row.get('sourceVersionResolution' if prefix == 's' else 'targetVersionResolution')
            values = {str(value) for value in resources.objects(node, LA.versionResolution)}
            if resolution is not None and resolution not in values:
                return False
            for suffix, predicate in (('Label', RDFS.label), ('Type', RDF.type)):
                if row.get(prefix + suffix) is not None and row[prefix + suffix] not in {str(v) for v in resources.objects(node, predicate)}:
                    return False
        representation = URIRef(row.get('representation', ''))
        artifact = URIRef(row.get('artifact', ''))
        checks = [(evidence, LA.artifact, 'artifact'), (evidence, LA.locator, 'locator'),
                  (evidence, LA.quotedText, 'quotedText'), (evidence, LA.textRepresentation, 'representation'),
                  (evidence, LA.startOffset, 'startOffset'), (evidence, LA.endOffset, 'endOffset'),
                  (artifact, LA.contentHash, 'contentHash'), (representation, LA.contentHash, 'textHash'),
                  (representation, LA.locatorMapHash, 'locatorMapHash')]
        return all(str(row.get(name, '')) in {str(v) for v in resources.objects(subject, predicate)}
                   for subject, predicate, name in checks)

    def metadata_query(self, family: str) -> str:
        info = self.require_current()
        # Every interpolated value is locally regenerated from a validated release.
        ident = info['release_id']
        return f'''SELECT ?bundle ?ontology ?key ?family ?graph WHERE {{ GRAPH <{info['metadata_graph_iri']}> {{
          <urn:la:release:{ident}> <urn:la:serving:bundleSha256> ?bundle ;
            <urn:la:serving:ontologySha256> ?ontology ; <urn:la:serving:reviewKeySha256> ?key ;
            <urn:la:serving:family> ?family ; <urn:la:serving:graph> ?graph .
        }} }} LIMIT 2'''

    def metadata_matches(self, family: str, rows: list[dict]) -> bool:
        info = self.require_current()
        if len(rows) != 1 or not isinstance(rows[0], dict):
            return False
        actual = {k: cell.get('value') for k, cell in rows[0].items() if isinstance(cell, dict)}
        return actual == {'bundle': info['release_id'], 'ontology': info['ontology_sha256'],
                          'key': info['review']['key_sha256'], 'family': family,
                          'graph': info['graphs'][family]['graph_iri']}
