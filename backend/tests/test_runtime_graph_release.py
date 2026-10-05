"""Synthetic release trust and query-pinning checks; no production review is created."""
import base64
import json
from contextlib import contextmanager

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from rdflib import Dataset
from test_graph import ONTOLOGY, corpus_for_query_tests
from test_workspace import workspace as workspace_fixture

from app.graph import GraphBackendError, GraphService
from app.graph_release import RuntimeGraphRelease, _load_serving

workspace = workspace_fixture


@contextmanager
def synthetic_authorization(info, action):
    assert action in {'read', 'install', 'activate', 'rollback'}
    yield {'release_id': info['release_id'], 'current': True}


def test_static_signature_without_private_authorization_cannot_serve(active_release, monkeypatch):
    root, key, _ = active_release
    service = GraphService(ONTOLOGY, 'http://127.0.0.1', release_root=root, trusted_review_key=key)
    monkeypatch.setattr(service, '_transport_select', lambda *args: pytest.fail('Unauthorized graph query'))
    assert service.release_status()['status'] == 'unavailable'
    assert service.explore()['edges'] == []


@pytest.mark.parametrize('failure', ['before_query', 'after_query', 'database_failure'])
def test_private_authorization_revocation_discards_graph_results(active_release, monkeypatch, failure):
    root, key, _ = active_release
    revoked = False
    @contextmanager
    def guard(info, action):
        if revoked:
            raise RuntimeError('PRIVATE-FIRM-HEAD-DO-NOT-EXPOSE')
        yield
        if revoked:
            raise ValueError('PRIVATE-FIRM-HEAD-DO-NOT-EXPOSE')
    service = GraphService(ONTOLOGY, 'http://127.0.0.1', release_root=root, trusted_review_key=key,
                           authorization_guard=guard)
    assert service.release_status()['status'] == 'verified'
    calls = []
    def select(family, query):
        nonlocal revoked
        calls.append(query)
        if len(calls) == 1:
            info = service.release.info
            return [{name: {'value': value} for name, value in {
                'bundle': info['release_id'], 'ontology': info['ontology_sha256'],
                'key': info['review']['key_sha256'], 'family': family,
                'graph': info['graphs'][family]['graph_iri'],
            }.items()}]
        revoked = True
        return []
    monkeypatch.setattr(service, '_transport_select', select)
    if failure != 'after_query':
        revoked = True
    result = service.explore()
    assert result['mode'] == 'unavailable' and not result['edges']
    assert len(calls) == (2 if failure == 'after_query' else 0)
    assert service.release_pin()['status'] == 'unavailable'
    assert 'PRIVATE-FIRM' not in json.dumps(result) + json.dumps(service.release_status())


def test_guard_exit_failure_during_startup_is_unavailable(active_release):
    root, key, _ = active_release
    @contextmanager
    def guard(info, action):
        yield
        raise ValueError('PRIVATE-PROJECTION-DIGEST')
    status = RuntimeGraphRelease(root, key, authorization_guard=guard).status()
    assert status['status'] == 'unavailable'
    assert 'PRIVATE' not in json.dumps(status)


@pytest.fixture
def active_release(tmp_path):
    serving = _load_serving()
    release = serving._release
    paths = {}
    for family in serving.FAMILIES:
        paths[family] = tmp_path / (family + '.ttl')
        paths[family].write_text('# EMPTY ENGINEERING FIXTURE; no actual law or legal review\n')
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    key = Ed25519PrivateKey.generate()
    public = tmp_path / 'test-only-key.pem'
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    body = {'reviewer': 'TEST ONLY CRYPTOGRAPHIC FIXTURE', 'reviewed_at': '2026-01-01T00:00:00Z',
            'decision': 'approve', 'scope': 'national_ontology_and_assertions',
            'ontology_sha256': release.ontology_digest(ONTOLOGY),
            'input_graphs_sha256': {family: release.file_hash(path) for family, path in paths.items()}}
    attestation = tmp_path / 'test-attestation.json'
    attestation.write_text(json.dumps({'algorithm': 'Ed25519', 'body': body,
                                      'signature': base64.b64encode(key.sign(release.canonical(body))).decode()}))
    bundle = tmp_path / 'bundle'
    release.create_bundle(ONTOLOGY, paths, evidence, bundle, attestation, public)
    prepared = tmp_path / 'prepared'
    serving.prepare(bundle, public, prepared)
    root = tmp_path / 'serving'
    installed = serving.install(root, prepared, public, authorization_guard=synthetic_authorization)
    serving.activate(root, installed['release_id'], public, expected_current=None, authorization_guard=synthetic_authorization)
    return root, public, installed


def test_unsigned_unconfigured_runtime_never_reads_mutable_graph(monkeypatch):
    service = GraphService(ONTOLOGY, 'http://127.0.0.1:3030')
    monkeypatch.setattr(service, '_transport_select', lambda *a: pytest.fail('Unverified data was queried'))
    result = service.explore()
    assert result['mode'] == 'unavailable' and not result['edges']
    assert service.coverage()['serving_release']['status'] == 'unconfigured'


def test_independent_release_validation_and_named_graph_isolation(active_release, monkeypatch):
    root, key, installed = active_release
    service = GraphService(ONTOLOGY, 'http://127.0.0.1:3030', release_root=root, trusted_review_key=key, authorization_guard=synthetic_authorization)
    assert service.release_status()['status'] == 'verified'
    datasets = {}
    for family in ('structure', 'jurisprudence'):
        data = Dataset()
        data.parse(root / 'releases' / installed['release_id'] / f'{family}.nq', format='nquads')
        # A mutable default graph must not bleed into the pinned family.
        for triple in corpus_for_query_tests():
            data.default_graph.add(triple)
        datasets[family] = data
    queries = []
    def select(family, query):
        queries.append(query)
        return json.loads(datasets[family].query(query).serialize(format='json'))['results']['bindings']
    monkeypatch.setattr(service, '_transport_select', select)
    result = service.explore(as_of='2023-01-01')
    assert result['mode'] == 'fuseki' and result['edges'] == []
    assert result['snapshot']['release_id'] == installed['release_id']
    assert result['snapshot']['reproducibility'] == 'immutable_verified_release'
    assert any('FROM <' + installed['graphs']['structure']['graph_iri'] + '>' in q for q in queries)
    assert service.coverage()['assertion']['observed_count'] == 0


@pytest.mark.parametrize('failure', ['empty', 'mixed_release', 'duplicate', 'wrong_family'])
def test_runtime_receipt_must_match_before_data_query(active_release, monkeypatch, failure):
    root, key, installed = active_release
    service = GraphService(ONTOLOGY, 'http://127.0.0.1', release_root=root, trusted_review_key=key, authorization_guard=synthetic_authorization)
    values = {'bundle': installed['release_id'], 'ontology': installed['ontology_sha256'],
              'key': installed['review']['key_sha256'], 'family': 'structure',
              'graph': installed['graphs']['structure']['graph_iri']}
    if failure == 'mixed_release':
        values['bundle'] = 'a' * 64
    if failure == 'wrong_family':
        values['family'] = 'jurisprudence'
    row = {k: {'value': v} for k, v in values.items()}
    rows = [] if failure == 'empty' else [row, row] if failure == 'duplicate' else [row]
    calls = []
    monkeypatch.setattr(service, '_transport_select', lambda *a: calls.append(a) or rows)
    with pytest.raises(GraphBackendError):
        service._select('structure', 'SELECT ?s WHERE { ?s ?p ?o }')
    assert len(calls) == 1


@pytest.mark.parametrize('change', ['pointer', 'trust_key', 'unsigned_pointer'])
def test_activation_and_trust_changes_close_existing_reader(active_release, change):
    root, key, installed = active_release
    reader = RuntimeGraphRelease(root, key, authorization_guard=synthetic_authorization)
    assert reader.status()['status'] == 'verified'
    if change == 'trust_key':
        key.write_bytes(b'changed public trust key')
    else:
        pointer = json.loads((root / 'active.json').read_text())
        pointer['sequence'] += 1
        if change == 'unsigned_pointer':
            pointer['release_id'] = 'e' * 64
        # Simulate an offline owner replacing protected publication metadata.
        # Runtime containers never have a writable release mount.
        (root / 'active.json').chmod(0o644)
        (root / 'active.json').write_text(json.dumps(pointer))
    assert reader.status()['status'] == 'unavailable'
    with pytest.raises(ValueError):
        reader.require_current()


def test_tampered_bundle_fails_closed_at_startup(active_release):
    root, key, installed = active_release
    path = installed['bundle_path'] / 'inputs' / 'structure.ttl'
    path.chmod(0o644)
    path.write_text('# modified after publication')
    assert RuntimeGraphRelease(root, key, authorization_guard=synthetic_authorization).status()['status'] == 'unavailable'


def test_runtime_edge_cannot_change_verified_source_quote():
    from _pytest.monkeypatch import MonkeyPatch
    from test_graph import local_adapter

    from app.graph import _datetime
    corpus = corpus_for_query_tests()
    with MonkeyPatch.context() as patch:
        service = local_adapter(patch, corpus)
        query = service._build_query(graph='structure', query='', as_of='2023-01-01', limit=10,
                                     known_at=_datetime('2026-02-01T00:00:00Z'))
        raw = service._select('structure', query)[0]
        row = {name: cell['value'] for name, cell in raw.items()}
        proof = RuntimeGraphRelease()
        proof.info = {'synthetic_test_only': True}
        proof._graphs = {'structure': corpus}
        assert proof.matches('structure', row)
        row['quotedText'] = 'An invented legal assertion'
        assert not proof.matches('structure', row)


def test_research_cannot_publish_after_release_switch(workspace, monkeypatch):
    app, client, matter = workspace
    original = app.state.search.search
    def switch(*args, **kwargs):
        result = original(*args, **kwargs)
        monkeypatch.setattr(app.state.graph, 'release_pin', lambda: {'status': 'verified', 'release_id': 'b' * 64})
        return result
    monkeypatch.setattr(app.state.search, 'search', switch)
    import time
    response = client.post(f'/api/v1/matters/{matter}/research', json={'question': 'Ödeme koşulları'})
    assert response.status_code == 202
    for _ in range(100):
        state = client.get(f"/api/v1/matters/{matter}/research/{response.json()['id']}").json()
        if state['status'] in {'failed', 'completed'}:
            break
        time.sleep(0.01)
    assert state['status'] == 'failed' and state['error_code'] == 'GraphBackendError'
    assert not client.get(f'/api/v1/matters/{matter}').json()['products']


def _proof_row():
    from test_graph import FX

    from app.graph import _datetime
    corpus = corpus_for_query_tests()
    service = GraphService(ONTOLOGY)
    query = service._build_query(graph='structure', query='', as_of='2023-01-01', limit=10,
                                 known_at=_datetime('2026-02-01T00:00:00Z'))
    rows = json.loads(corpus.query(query).serialize(format='json'))['results']['bindings']
    raw = next(row for row in rows if row['a']['value'] == str(FX['version-link-a']))
    proof = RuntimeGraphRelease()
    proof.info = {'synthetic_test_only': True}
    proof._graphs = {'structure': corpus}
    return proof, corpus, {name: cell['value'] for name, cell in raw.items()}


@pytest.mark.parametrize('mutation', ['unknown_validity', 'wrong_family', 'private_assertion',
    'synthetic_assertion', 'private_endpoint', 'synthetic_endpoint', 'private_evidence',
    'revoked_rights', 'synthetic_artifact', 'private_representation', 'synthetic_representation',
    'wrong_representation_artifact', 'unresolved_version', 'target_starts_later', 'target_already_expired'])
def test_runtime_filters_cannot_override_signed_eligibility(mutation):
    from rdflib import XSD, Literal, URIRef
    from test_graph import LA
    proof, corpus, row = _proof_row()
    assert proof.matches('structure', row, as_of='2023-01-01', known_at='2026-02-01T00:00:00Z')
    assertion, target = URIRef(row['a']), URIRef(row['o'])
    evidence, artifact, representation = (URIRef(row[key]) for key in ('evidence', 'artifact', 'representation'))
    changes = {
        'unknown_validity': (assertion, LA.validityStatus, Literal('unknown')),
        'wrong_family': (assertion, LA.graphFamily, Literal('jurisprudence')),
        'private_assertion': (assertion, LA.scope, Literal('private')),
        'synthetic_assertion': (assertion, LA.synthetic, Literal(True)),
        'private_endpoint': (target, LA.scope, Literal('private')),
        'synthetic_endpoint': (target, LA.synthetic, Literal(True)),
        'private_evidence': (evidence, LA.scope, Literal('private')),
        'revoked_rights': (artifact, LA.rightsStatus, Literal('revoked')),
        'synthetic_artifact': (artifact, LA.synthetic, Literal(True)),
        'private_representation': (representation, LA.scope, Literal('private')),
        'synthetic_representation': (representation, LA.synthetic, Literal(True)),
        'wrong_representation_artifact': (representation, LA.artifact, URIRef('urn:synthetic:different-artifact')),
        'unresolved_version': (target, LA.versionResolution, Literal('unresolved')),
        'target_starts_later': (target, LA.validFrom, Literal('2030-01-01', datatype=XSD.date)),
        'target_already_expired': (target, LA.validTo, Literal('2022-01-01', datatype=XSD.date)),
    }
    corpus.set(changes[mutation])
    assert not proof.matches('structure', row, as_of='2023-01-01', known_at='2026-02-01T00:00:00Z')


def test_runtime_request_dates_and_identity_restrictions_are_independent():
    proof, _, row = _proof_row()
    assert proof.matches('structure', row, as_of='2023-01-01', known_at='2026-02-01T00:00:00Z',
                         entity_id='<' + row['s'] + '>', assertion_id='<' + row['a'] + '>', identifier=row['s'])
    for kwargs in ({'as_of': '1900-01-01'}, {'as_of': '2030-01-01'},
                   {'known_at': '2025-12-31T00:00:00Z'}, {'known_at': '2026-01-01'},
                   {'entity_id': '<urn:synthetic:not-connected>'},
                   {'entity_id': '<urn:synthetic:not-connected>', 'hops': 2},
                   {'assertion_id': '<urn:synthetic:other-assertion>'}, {'identifier': 'unrelated'},
                   {'query': 'no such source label'}, {'relations': {'amends'}}):
        assert not proof.matches('structure', row, **kwargs), kwargs
    assert proof.matches('structure', row, as_of='2030-01-01', history=True)


@pytest.mark.parametrize('changed', ['inputs/structure.ttl', 'ontology/catalog.json'])
def test_source_changed_between_signature_check_and_memory_load_is_rejected(active_release, monkeypatch, changed):
    from types import SimpleNamespace

    from app import graph_release
    root, key, installed = active_release
    serving = _load_serving()
    def racing_load(*args):
        info = serving.load_active(*args)
        path = info['bundle_path'] / changed
        path.chmod(0o644)
        path.write_bytes(path.read_bytes() + b' ')
        return info
    monkeypatch.setattr(graph_release, '_load_serving', lambda: SimpleNamespace(load_active=racing_load))
    assert RuntimeGraphRelease(root, key, authorization_guard=synthetic_authorization).status()['status'] == 'unavailable'
