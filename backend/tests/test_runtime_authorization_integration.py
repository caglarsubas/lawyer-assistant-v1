"""Real sealed private authorization against an isolated synthetic source ledger."""

import io
import json
import time

import httpx
import test_search_index
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfReader
from rdflib import RDF, Dataset, Literal
from test_release_authorization import authorized as authorized_fixture
from test_release_authorization import guard
from test_release_authorization import mapping as mapping_fixture
from test_release_authorization import source as source_fixture
from test_release_authorization import workspace as workspace_fixture
from test_source_reviews import assess

from app.graph_release import LA, _load_serving
from app.main import create_app
from app.policy import POLICY_VERSION
from app.retrieval_benchmark import DiscoveryBenchmark, capture_discovery, score_discovery
from app.search import PublicSearchService
from app.search_index import IndexBuildError, build_index
from app.search_normalization import normalization_metadata
from app.source_corpus import EvidenceLookup, SourceCorpusService

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
        # Independent source discovery uses the actual signed physical quote
        # and actual current private ledger, without relying on graph paths or
        # guessing applicability from this deliberately different date.
        source_result = SourceCorpusService(app.state.graph.release).search('SYNTHETIC',
            passage_id=str(evidence), as_of='1921-01-01')
        assert source_result['coverage']['status'] == 'available'
        exact = source_result['hits'][0]
        assert exact['text'] == source['text'] and exact['passage_id'] == str(evidence)
        assert exact['authority_id'] is None and exact['temporal_applicability'] == 'not_assessed'
        assert source_result['snapshot']['release_id'] == installed['release_id']
        lookup = EvidenceLookup(passage_id=exact['passage_id'], source_version_id=exact['source_version_id'],
            expected_release_id=installed['release_id'], expected_serving_sha256=source_result['snapshot']['serving_sha256'],
            as_of='1921-01-01')
        assert SourceCorpusService(app.state.graph.release).get_evidence(lookup)['hit']['text'] == source['text']
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
            # Reuse actual signed source bytes and private grants. Only graph
            # transport runs locally through RDFLib rather than a live server.
            datasets = {}
            for family in ('structure', 'jurisprudence'):
                datasets[family] = Dataset()
                datasets[family].parse(root / 'releases' / installed['release_id'] / (family + '.nq'), format='nquads')
            patch.setattr(app.state.graph, 'fuseki_url', 'http://127.0.0.1:3030')
            patch.setattr(app.state.graph, '_transport_select', lambda family, query:
                json.loads(datasets[family].query(query).serialize(format='json'))['results']['bindings'])
            benchmark = DiscoveryBenchmark.model_validate({
                'schema_version': 'source-graph-discovery-benchmark-v1', 'dataset_id': 'test-only-signed-discovery',
                'purpose': 'development', 'origin': 'synthetic', 'adjudication_status': 'pending',
                'adjudication_evidence_sha256': None, 'snapshot': {
                    'release_id': installed['release_id'], 'serving_sha256': source_result['snapshot']['serving_sha256'],
                    'ontology_sha256': source_result['snapshot']['ontology_sha256'], 'activation_sequence': 1,
                    'index': index_name, 'documents_sha256': built['documents_sha256'], 'index_schema': 'public-search-index-v3',
                    'normalization': normalization_metadata(), 'citation_profile': 'tr-literal-citations-v1', 'fusion': 'rrf-k60-v1',
                    'known_at': '2026-10-14T00:00:00Z', 'source_recipe': 'source-qualified-corpus-v1', 'policy': POLICY_VERSION},
                'queries': [{'id': 'signed-one', 'query': 'test', 'graph_query': 'test', 'graph_family': 'structure',
                    'family_sha256': 'f' * 64, 'practice': 'contracts', 'period': '2002_2015', 'slices': ['citation'],
                    'as_of': '2011-06-01', 'corpus_coverage': 'unknown', 'source_coverage': 'covered',
                    'judgments': [], 'exact_target': None,
                    'passage_judgments': [{'passage_id': str(evidence), 'relevance': 3, 'adverse': False}]}]})
            observed = capture_discovery(benchmark,
                PublicSearchService('http://opensearch:9200', index_name, installed['release_id'], app.state.graph.release),
                app.state.graph, SourceCorpusService(app.state.graph.release))
            measured = score_discovery(benchmark, observed)
            assert measured['profiles']['source_lexical']['passage_recall_at_20']['value'] == 1.0
            assert measured['production_qualified'] is False and len(observed.observations) == 3
        # Real saved research and exports retain independently grounded source
        # quotes even when authority retrieval cannot qualify this old date.
        matter = restarted.get('/api/v1/matters').json()[0]['id']
        matter_base = '/api/v1/matters/' + matter
        from test_analysis_workbench import build_workbench, create
        from test_authority_adjudications import reviewer
        from test_source_analysis_reviews import freeze, nominate, record, review_request

        private_workbench = build_workbench((app, restarted, matter))
        analysis = create(private_workbench)
        submitted = restarted.post(matter_base + '/research', json={'question': source['text'][:100], 'as_of': '1921-01-01'})
        assert submitted.status_code == 202, submitted.text
        for _ in range(600):
            state = restarted.get(matter_base + '/research/' + submitted.json()['id']).json()
            if state['status'] in {'completed', 'failed'}:
                break
            time.sleep(0.05)
        assert state['status'] == 'completed', state
        product_path = matter_base + '/products/' + state['product_id']
        # The committed job state precedes the source guard's exit. Wait for
        # its independent callback, never infer authorization from completion.
        for _ in range(600):
            saved = restarted.get(product_path).json()
            if not saved.get('authorization_revalidation'):
                break
            time.sleep(0.05)
        assert saved['source_candidates']['hits'] and saved['critical_gaps'] == ['legal_corpus_unqualified'], {
            'status': saved['status'], 'withheld': saved.get('public_results_withheld'),
            'coverage': saved['source_candidates']['coverage'], 'snapshot': saved['source_candidates']['snapshot']}
        assert any(item['text'] == source['text'] for item in saved['source_candidates']['hits'])
        assert not saved['authority_candidates']['hits']
        assert all(claim['kind'] == 'document_quote' for claim in saved['claims'])
        public_ids = {item['passage_id'] for item in saved['source_candidates']['hits']}
        assert not public_ids & {ref for claim in saved['claims'] for ref in claim['evidence_ids']}
        docx = restarted.get(product_path + '/export?format=docx')
        assert docx.status_code == 200, docx.text if docx.status_code != 200 else ''
        exported = '\n'.join(item.text for item in Document(io.BytesIO(docx.content)).paragraphs)
        assert source['text'].replace('\r\n', '\n') in exported and exact['quote_sha256'] in exported
        pdf = restarted.get(product_path + '/export?format=pdf')
        assert pdf.status_code == 200
        pdf_text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
        assert str(evidence) in pdf_text and 'ulusal derlemin tamlığı bilinmiyor' in pdf_text
        # Actual signed bytes/current private grants also qualify the new private
        # source nomination and independent reviewer boundary. No new fixture.
        source_context_path, spec, _ = nominate(private_workbench, state['product_id'],
            saved['source_candidates']['hits'][0], saved['source_candidates']['snapshot'], analysis=analysis)
        source_context, _ = freeze(restarted, source_context_path, spec)
        assert restarted.get(source_context_path + '/' + source_context['id'] + '/export').status_code == 409
        reviewer(private_workbench)
        review_path, review_body = review_request(restarted, source_context_path, source_context['id'])
        reviewed = record(restarted, review_path, review_body)
        assert reviewed['review']['effective_state'] == 'reviewed_conditional'
        assert reviewed['manifest']['sources'][0]['evidence']['text'] == saved['source_candidates']['hits'][0]['text']
        assert restarted.get(source_context_path + '/' + source_context['id'] + '/export').status_code == 200
        from test_analysis_comparisons import login

        login(restarted)
        from test_source_context_renewals import renewal_spec, reviewed_renewal

        replacement_spec, _ = renewal_spec(restarted, source_context_path, spec, source_context['id'])
        replacement, _ = freeze(restarted, source_context_path, replacement_spec)
        assert replacement['review']['snapshot'] is None
        login(restarted, 'reviewer')
        renewal_review_path, renewal_review_body = reviewed_renewal(restarted, source_context_path, replacement)
        replacement_review = record(restarted, renewal_review_path, renewal_review_body)
        assert replacement_review['review']['snapshot']['input']['renewal_assessment']['outcome'] == 'confirmed'
        assert restarted.get(source_context_path + '/' + replacement['id'] + '/export').status_code == 200
        login(restarted)
        changed = assess(restarted, base + '/review', 6, 'rights', decision='needs_changes')
        assert changed.status_code == 200
        assert app.state.graph.release_status()['status'] == 'unavailable'
        assert app.state.graph.legal_review_status == 'unreviewed'
        monkeypatch.setattr(app.state.search, '_request', lambda *args: (_ for _ in ()).throw(
            AssertionError('Revoked release must not query search')))
        response = app.state.search.search('SYNTHETIC TEST ONLY')
        assert response['hits'] == [] and response['coverage']['status'] == 'unavailable'
        assert 'PRIVATE' not in json.dumps(response)
        denied_sources = SourceCorpusService(app.state.graph.release).search('SYNTHETIC')
        assert denied_sources['hits'] == [] and denied_sources['coverage']['status'] == 'unavailable'
        assert SourceCorpusService(app.state.graph.release).get_evidence(lookup)['status'] == 'unavailable'
        withheld = restarted.get(product_path)
        assert withheld.status_code == 200 and withheld.headers['cache-control'] == 'no-store'
        assert withheld.json()['status'] == 'stale' and withheld.json()['public_results_withheld'] is True
        assert not withheld.json()['source_candidates']['hits']
        assert restarted.get(product_path + '/export?format=docx').status_code == 409
        withdrawn = restarted.get(source_context_path + '/' + source_context['id'])
        assert withdrawn.status_code == 200 and withdrawn.json()['manifest'] is None
        assert withdrawn.json()['review']['snapshot'] is None
        assert 'PRIVATE REVIEW NOTE' not in withdrawn.text
        assert restarted.get(source_context_path + '/' + source_context['id'] + '/export').status_code == 409
        renewed_withdrawn = restarted.get(source_context_path + '/' + replacement['id'])
        assert renewed_withdrawn.json()['manifest'] is None and renewed_withdrawn.json()['review']['snapshot'] is None
        assert restarted.get(source_context_path + '/' + replacement['id'] + '/export').status_code == 409
        import pytest
        with pytest.raises(IndexBuildError) as denied:
            build_index(app.state.graph.release, 'http://opensearch:9200', installed['release_id'])
        assert denied.value.stage == 'authorization'
