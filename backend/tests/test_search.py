"""Synthetic public-corpus responses; no live OpenSearch or provider connections."""

import json

import httpx
import pytest

from app.search import SOURCE_FIELDS, PublicSearchService

RELEASE = "fixture-release-1"
INDEX = "law-public-passages"


def source(passage_id, **changes):
    result = {
        "passage_id": passage_id, "document_id": "synthetic-document", "source_version_id": "version-1",
        "source_sha256": "a" * 64, "text": "Synthetic legal source text, not authoritative law.",
        "title": "Synthetic test source", "source_url": "https://example.gov.tr/source",
        "locator": "Page 1, paragraph 2", "authority_id": "synthetic-authority", "release_id": RELEASE,
        "visibility": "public", "rights_status": "permitted", "review_status": "legally_reviewed",
        "valid_from": "2020-01-01", "valid_to": "2030-01-01",
    }
    result.update(changes)
    return {"_id": passage_id, "_index": INDEX, "_source": result}


def payload(hits, **changes):
    result = {"timed_out": False, "_shards": {"failed": 0}, "hits": {"hits": hits}}
    result.update(changes)
    return result


class SyntheticAuthorizedRelease:
    def require_current(self):
        return {'release_id': RELEASE}

    def project_search_hit(self, candidate, **kwargs):
        # This test double isolates OpenSearch transport/fusion behavior. Actual
        # signed physical evidence matching is exercised in runtime integration.
        return {key: candidate.get(key) for key in SOURCE_FIELDS}


def service():
    return PublicSearchService("http://opensearch:9200", release_id=RELEASE,
                               graph_release=SyntheticAuthorizedRelease())


def mock_search(monkeypatch, responses):
    original = httpx.Client
    seen = []

    def serve(request):
        seen.append(request)
        value = responses[len(seen) - 1]
        if isinstance(value, int):
            return httpx.Response(value, json={"error": "fixture"})
        return httpx.Response(200, json=value)

    def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        return original(transport=httpx.MockTransport(serve), **kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    return seen


def test_missing_release_is_explicit_unknown_without_network(monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("No release must mean no network call")
    monkeypatch.setattr(httpx, "Client", forbidden)
    for search in (PublicSearchService(), PublicSearchService("http://opensearch:9200")):
        assert not search.configured
        result = search.search("fixture question")
        assert result["hits"] == []
        assert result["coverage"]["status"] == "no_qualified_corpus"
        assert result["coverage"]["completeness"] == "unknown"


@pytest.mark.parametrize("index", ["*", "_all", "private-matters", "law-public-passages,private", "../private"])
def test_index_cannot_select_private_or_arbitrary_data(index):
    with pytest.raises(ValueError):
        PublicSearchService("http://opensearch:9200", index=index, release_id=RELEASE)


@pytest.mark.parametrize("origin", [
    "https://public.example", "http://169.254.169.254", "http://0.0.0.0",
    "http://opensearch:bad", "http://secret@opensearch", "http://opensearch/private",
])
def test_search_has_a_private_fixed_origin(origin):
    with pytest.raises(ValueError):
        PublicSearchService(origin, release_id=RELEASE)


def test_lexical_filters_are_built_before_retrieval_and_results_are_projected(monkeypatch):
    hit = source("passage-a", secret_extra="must not escape projection")
    seen = mock_search(monkeypatch, [payload([hit])])
    result = service().search('{"match_all": {}}', as_of="2024-01-01")
    body = json.loads(seen[0].content)
    assert seen[0].url.path == f"/{INDEX}/_search"
    filters = body["query"]["bool"]["filter"]
    for field, value in (("release_id", RELEASE), ("visibility", "public"), ("rights_status", "permitted"),
                         ("review_status", "legally_reviewed")):
        assert {"term": {field: value}} in filters
    assert body["query"]["bool"]["must"][0]["multi_match"]["query"] == '{"match_all": {}}'
    assert "secret_extra" not in result["hits"][0]
    assert result["hits"][0]["source_sha256"] == "a" * 64
    assert result["snapshot"]["release_id"] == RELEASE
    assert result["coverage"]["status"] == "available"


@pytest.mark.parametrize("authority", ["https://lawyer-assistant.local/authority/synthetic-1", "urn:legal:synthetic:1"])
def test_absolute_graph_id_resolves_exactly_without_lexical_or_vector_recall_loss(monkeypatch, authority):
    item = source("https://lawyer-assistant.local/passage/synthetic-1", authority_id=authority,
                  document_id="urn:legal:document:synthetic-1",
                  source_version_id="https://lawyer-assistant.local/version/synthetic-1")
    seen = mock_search(monkeypatch, [payload([item])])
    result = service().search("terms absent from the source", authority_id=authority, vector=[1.0])
    assert len(seen) == 1
    query = json.loads(seen[0].content)["query"]["bool"]
    assert query["must"] == [{"match_all": {}}]
    assert {"term": {"authority_id": authority}} in query["filter"]
    assert result["hits"][0]["authority_id"] == authority
    assert result["snapshot"]["resolution"] == "exact_authority_identifier"


@pytest.mark.parametrize("identifier", ["https://secret@local/item", "https://local:bad/item", "urn:x:bad value", "a" * 513])
def test_unsafe_entity_identifiers_are_rejected(identifier):
    with pytest.raises(ValueError):
        service().search("fixture", authority_id=identifier)


def test_release_ids_remain_stricter_than_entity_iris():
    with pytest.raises(ValueError):
        PublicSearchService("http://opensearch:9200", release_id="https://local/release/1")


def test_lexical_and_vector_candidates_are_unioned_not_intersected(monkeypatch):
    seen = mock_search(monkeypatch, [payload([source("a"), source("b")]), payload([source("b"), source("c")])])
    result = service().search("fixture question", vector=[0.1, 0.2], limit=3)
    assert [hit["passage_id"] for hit in result["hits"]] == ["b", "a", "c"]
    assert result["hits"][0]["channels"] == ["lexical", "vector"]
    lexical, vector = [json.loads(request.content) for request in seen]
    assert vector["query"]["knn"]["embedding"]["filter"]["bool"]["filter"] == lexical["query"]["bool"]["filter"]
    assert "post_filter" not in vector


@pytest.mark.parametrize("changes", [
    {"visibility": "private"}, {"release_id": "another-release"}, {"rights_status": "unverified"},
    {"review_status": "proposed"}, {"source_sha256": "not-a-hash"}, {"source_version_id": None},
    {"valid_from": "2025-01-01"}, {"valid_to": "2024-01-01"}, {"authority_id": "other-authority"},
])
def test_server_returned_fields_are_revalidated(monkeypatch, changes):
    mock_search(monkeypatch, [payload([source("a", **changes)])])
    result = service().search("fixture", as_of="2024-01-01", authority_id="synthetic-authority")
    assert result["hits"] == []
    assert result["coverage"]["rejected_hits"] == 1
    assert result["coverage"]["status"] == "partial"


def test_hit_id_must_match_passage_id(monkeypatch):
    wrong = source("a")
    wrong["_id"] = "another-passage"
    mock_search(monkeypatch, [payload([wrong])])
    assert service().search("fixture")["hits"] == []


def test_conflicting_source_versions_are_not_silently_fused(monkeypatch):
    mock_search(monkeypatch, [payload([source("a")]), payload([source("a", source_version_id="version-2")])])
    result = service().search("fixture", vector=[1.0])
    assert result["hits"] == []
    assert result["coverage"]["status"] == "partial"


def test_unavailable_vector_channel_does_not_erase_lexical_candidates(monkeypatch):
    mock_search(monkeypatch, [payload([source("a")]), 400])
    result = service().search("fixture", vector=[1.0])
    assert result["hits"][0]["passage_id"] == "a"
    assert result["coverage"]["status"] == "partial"
    assert result["coverage"]["channels"]["vector"] == "unavailable"


@pytest.mark.parametrize("response", [
    payload([source("a")], timed_out=True), payload([source("a")], _shards={"failed": 1}),
    payload([source(str(index)) for index in range(5)]), {"hits": {"hits": []}}, [], 503,
])
def test_partial_malformed_or_over_limit_channel_response_is_not_complete(monkeypatch, response):
    mock_search(monkeypatch, [response])
    result = service().search("fixture", limit=1)
    assert result["hits"] == []
    assert result["coverage"]["status"] == "unavailable"


def test_response_bytes_are_bounded(monkeypatch):
    mock_search(monkeypatch, [payload([], unrelated_padding="x" * (1024 * 1024))])
    result = service().search("fixture")
    assert result["hits"] == []
    assert result["coverage"]["status"] == "unavailable"


def test_response_nodes_are_bounded(monkeypatch):
    mock_search(monkeypatch, [payload([], unrelated_nodes=[0] * 20001)])
    assert service().search("fixture")["coverage"]["status"] == "unavailable"


@pytest.mark.parametrize("arguments", [
    {"vector": [float("nan")]}, {"vector": [True]}, {"vector": []}, {"vector": [0.0] * 4097},
    {"as_of": "2024-02-31"}, {"as_of": "20240101"}, {"limit": 51}, {"limit": True},
    {"authority_id": "*/private"}, {"vector": [10 ** 400]},
])
def test_invalid_inputs_never_become_arbitrary_dsl(monkeypatch, arguments):
    mock_search(monkeypatch, [])
    with pytest.raises(ValueError):
        service().search("fixture", **arguments)


@pytest.mark.parametrize('failure', ['missing_guard', 'release_mismatch', 'revoked', 'database_unavailable'])
def test_configured_search_release_cannot_bypass_current_graph_authorization(monkeypatch, failure):
    class Release:
        def require_current(self):
            if failure in {'revoked', 'database_unavailable'}:
                raise RuntimeError('PRIVATE-REVIEW-DETAIL')
            return {'release_id': 'another-release'}
    search = PublicSearchService('http://opensearch:9200', release_id=RELEASE,
                                 graph_release=None if failure == 'missing_guard' else Release())
    seen = mock_search(monkeypatch, [])
    result = search.search('fixture')
    assert seen == [] and result['hits'] == []
    assert result['coverage']['status'] == 'unavailable'
    assert 'PRIVATE' not in json.dumps(result)


def test_matching_release_without_signed_evidence_projection_rejects_hit(monkeypatch):
    class IndexLabelOnly:
        def require_current(self):
            return {'release_id': RELEASE}
    search = PublicSearchService('http://opensearch:9200', release_id=RELEASE,
                                 graph_release=IndexLabelOnly())
    mock_search(monkeypatch, [payload([source('a', text='PRIVATE UNLICENSED INDEX TEXT')])])
    result = search.search('fixture')
    assert result['hits'] == [] and result['coverage']['rejected_hits'] == 1
    assert 'PRIVATE UNLICENSED' not in json.dumps(result)


@pytest.mark.parametrize('mutation', ['revoked', 'switched'])
def test_revocation_after_lexical_response_discards_candidates_and_skips_vector(monkeypatch, mutation):
    search = service()
    class Release(SyntheticAuthorizedRelease):
        current = True
        def require_current(self):
            if not self.current:
                if mutation == 'revoked':
                    raise ValueError('PRIVATE-PROJECTION')
                return {'release_id': 'other-release'}
            return {'release_id': RELEASE}
    release = Release()
    search.graph_release = release
    calls = []
    def request(*args):
        calls.append(args)
        release.current = False
        return [source('a')]
    monkeypatch.setattr(search, '_request', request)
    result = search.search('fixture', vector=[1.0])
    assert len(calls) == 1 and result['hits'] == []
    assert result['coverage']['status'] == 'unavailable'
    assert result['coverage']['returned_hits'] == 0
    assert 'PRIVATE' not in json.dumps(result)
