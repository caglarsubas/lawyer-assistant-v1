"""Real sealed private authorization against an isolated synthetic source ledger."""

import json

import httpx
import test_search_index
from fastapi.testclient import TestClient
from rdflib import RDF, Literal
from test_release_authorization import authorized as authorized_fixture
from test_release_authorization import guard
from test_release_authorization import mapping as mapping_fixture
from test_release_authorization import source as source_fixture
from test_release_authorization import workspace as workspace_fixture
from test_source_reviews import assess

from app.graph_release import LA, _load_serving
from app.main import create_app
from app.search_index import IndexBuildError, build_index

authorized = authorized_fixture
mapping = mapping_fixture
source = source_fixture
workspace = workspace_fixture


def test_main_wires_real_private_guard_and_live_rights_revocation(authorized, tmp_path, monkeypatch):
    original, client, _, _, base = authorized['mapping']
    serving = _load_serving()
    root = tmp_path / 'runtime'
    def authorize(info, action):
        return guard(authorized, info=info, action=action)
    installed = serving.install(root, authorized['info']['bundle_path'].parent,
                                authorized['public_key'], authorization_guard=authorize)
    serving.activate(root, installed['release_id'], authorized['public_key'],
                     expected_current=None, authorization_guard=authorize)
    settings = original.state.settings.model_copy(update={
        'graph_release_dir': str(root), 'graph_trusted_review_key': str(authorized['public_key']),
        'opensearch_url': 'http://opensearch:9200', 'search_release_id': installed['release_id'],
    })
    assert authorized['root'] == settings.data_dir / 'release-authorizations'
    assert authorized['epoch_path'] == settings.data_dir / 'publication-epoch'
    # Stop the fixture API before restarting with its signed serving configuration.
    # Two independent coordinators must never share this private database.
    client.__exit__(None, None, None)
    app = create_app(settings)
    with TestClient(app) as restarted:
        restarted.cookies.update(client.cookies)
        restarted.headers['X-CSRF-Token'] = client.headers['X-CSRF-Token']
        assert app.state.graph.release_status()['status'] == 'verified'
        assert app.state.graph.release.require_current()['release_id'] == installed['release_id']
        pin = app.state.graph.release_pin()
        assert set(pin) == {'status', 'release_id', 'serving_sha256', 'activation_sequence'}
        assert 'PRIVATE' not in json.dumps(pin)

        # Matching release labels are untrusted. Only exact signed physical
        # evidence plus a signed authority relationship can reach the response.
        graph = app.state.graph.release._graphs['structure']
        assertion = next(graph.subjects(RDF.type, LA.Assertion))
        evidence = graph.value(assertion, LA.evidence)
        artifact = graph.value(evidence, LA.artifact)
        canonical_authority = str(graph.value(assertion, LA.subject))
        source = {
            'passage_id': 'PRIVATE-INDEX-PASSAGE', 'document_id': 'PRIVATE-INDEX-DOCUMENT',
            'source_version_id': 'PRIVATE-INDEX-VERSION',
            'source_sha256': str(graph.value(artifact, LA.contentHash)),
            'text': str(graph.value(evidence, LA.quotedText)),
            'title': 'PRIVATE-INDEX-TITLE', 'source_url': 'https://example.gov.tr/PRIVATE-INDEX-URL',
            'locator': str(graph.value(evidence, LA.locator)), 'authority_id': canonical_authority,
            'release_id': installed['release_id'], 'visibility': 'public',
            'rights_status': 'permitted', 'review_status': 'legally_reviewed',
            'valid_from': '2000-01-01', 'valid_to': '2030-01-01',
        }
        def hit(**changes):
            return {'_id': source['passage_id'], '_index': 'law-public-passages',
                    '_source': {**source, **changes}}
        forged = [hit(source_sha256='0' * 64), hit(text='PRIVATE UNLICENSED SOURCE'),
                  hit(text=source['text'][:-1]), hit(locator='PRIVATE DIFFERENT LOCATOR'),
                  hit(authority_id='urn:private:unlicensed-authority')]
        monkeypatch.setattr(app.state.search, '_request', lambda *args: [hit(), *forged])
        found = app.state.search.search('SYNTHETIC TEST ONLY', as_of='2011-06-01')
        assert len(found['hits']) == 1 and found['coverage']['rejected_hits'] == len(forged)
        result = found['hits'][0]
        assert result['passage_id'] == str(evidence) and result['document_id'] == str(artifact)
        assert result['source_version_id'] == str(graph.value(evidence, LA.textRepresentation))
        assert result['source_url'] is None and 'PRIVATE-INDEX' not in json.dumps(found)
        assert (result['valid_from'], result['valid_to']) == ('2011-01-01', '2012-01-01')
        # Even an existing raw hash does not license adjacent or fabricated text.
        monkeypatch.setattr(app.state.search, '_request', lambda *args: forged)
        assert app.state.search.search('SYNTHETIC TEST ONLY')['hits'] == []
        # A genuine passage cannot be redirected to a different legal authority.
        projected = dict(source, authority_id='urn:private:unlicensed-authority')
        try:
            app.state.graph.release.project_search_hit(projected, as_of='2011-06-01')
        except ValueError:
            pass
        else:
            raise AssertionError('Unverified authority identity was accepted')
        assert (assertion, LA.claimStatus, Literal('legally_reviewed')) in graph
        # Reuse this costly signed/private-ledger fixture for index admission.
        # Only HTTP is simulated; source projection, publication locks and the
        # application's live private authorization dispatcher remain real.
        server = test_search_index.Server()
        index_name = f"law-public-passages-{installed['release_id']}-{'b' * 32}"
        original_http = httpx.Client
        with monkeypatch.context() as patch:
            patch.setattr(test_search_index, 'INDEX', index_name)
            patch.setattr('app.search_index.secrets.token_hex', lambda _: 'b' * 32)
            patch.setattr(httpx, 'Client', lambda **kwargs: original_http(transport=httpx.MockTransport(server.response), **kwargs))
            built = build_index(app.state.graph.release, 'http://opensearch:9200', installed['release_id'])
            assert built['document_count'] == len(server.docs) > 0
            assert all(row['source_url'] is None and row['assertion_id'] for row in server.docs.values())
            assert 'PRIVATE' not in json.dumps(server.docs)
        changed = assess(restarted, base + '/review', 6, 'rights', decision='needs_changes')
        assert changed.status_code == 200
        assert app.state.graph.release_status()['status'] == 'unavailable'
        assert app.state.graph.legal_review_status == 'unreviewed'
        monkeypatch.setattr(app.state.search, '_request', lambda *args: (_ for _ in ()).throw(
            AssertionError('Revoked release must not query search')))
        response = app.state.search.search('SYNTHETIC TEST ONLY')
        assert response['hits'] == [] and response['coverage']['status'] == 'unavailable'
        assert 'PRIVATE' not in json.dumps(response)
        import pytest
        with pytest.raises(IndexBuildError) as denied:
            build_index(app.state.graph.release, 'http://opensearch:9200', installed['release_id'])
        assert denied.value.stage == 'authorization'
