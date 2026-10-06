"""Fast deterministic index-write/read boundaries, without Docker or legal approval."""

import copy
import json
from contextlib import contextmanager

import httpx
import pytest

from app import search_index
from app.search import PublicSearchService
from app.search_index import IndexBuildError, build_index
from app.search_index_contract import FIELDS, SCHEMA, canonical, document_id, properties

RELEASE = "a" * 64
INDEX = f"law-public-passages-{RELEASE}-{'b' * 32}"


def source(assertion="urn:test:assertion:1"):
    return dict(zip(FIELDS, ("urn:test:passage", assertion, "urn:test:document", "urn:test:version", "c" * 64,
        "Sözleşmeler hakkında TEST ONLY metin.", "Doğrulanmış kaynak pasajı", None, "page 1", "urn:test:authority",
        RELEASE, "public", "permitted", "legally_reviewed", "2010-01-01", "2012-01-01", "closed", None), strict=True))


class Release:
    info = {"release_id": RELEASE}
    fail_entry = fail_exit = False
    active = True

    def __init__(self, root, rows=None):
        self.root = root
        self.rows = rows if rows is not None else [source()]

    @contextmanager
    def current_guard(self):
        if self.fail_entry or not self.active:
            raise ValueError("PRIVATE REVIEW")
        yield self.info
        if self.fail_exit or not self.active:
            raise ValueError("PRIVATE REVIEW")

    def require_current(self):
        if not self.active:
            raise ValueError("PRIVATE REVIEW")
        return self.info

    def iter_search_documents(self):
        yield from self.rows

    def project_search_hit(self, candidate, **kwargs):
        # Isolate index transport here. Real signed evidence and private guards
        # are exercised by the separate runtime integration and opt-in drill.
        return copy.deepcopy(candidate)


class Server:
    def __init__(self):
        self.calls, self.docs = [], {}
        self.mapping = None
        self.aliases = {}
        self.blocked = False
        self.failure = None

    def response(self, request):
        self.calls.append(request)
        method, path = request.method, request.url.path
        data = json.loads(request.content) if request.content and not path.endswith("/_bulk") else None
        if path == "/" + INDEX and method == "PUT":
            if self.failure == "collision":
                return httpx.Response(400, json={"error": "PRIVATE SERVER DETAIL"})
            self.mapping = data["mappings"]
            value = {"acknowledged": True}
        elif path.endswith("/_bulk"):
            lines = request.content.splitlines()
            items = []
            for position in range(0, len(lines), 2):
                ident = json.loads(lines[position])["create"]["_id"]
                self.docs[ident] = json.loads(lines[position + 1])
                items.append({"create": {"_index": INDEX, "_id": ident, "status": 201}})
            value = {"errors": False, "items": items}
            if self.failure == "bulk":
                value["items"][0]["create"]["status"] = 409
            if self.failure == "truncated_bulk":
                value["items"] = []
        elif path.endswith("/_settings"):
            self.blocked = data["index.blocks.write"]
            value = {"acknowledged": True}
        elif path.endswith("/_refresh"):
            value = {"_shards": {"failed": 1 if self.failure == "refresh" else 0}}
        elif path.endswith("/_count"):
            value = {"count": len(self.docs) + (self.failure == "count"), "_shards": {"failed": 0}}
        elif path.endswith("/_mget"):
            docs = [{"_id": ident, "_index": INDEX, "found": True, "_source": copy.deepcopy(self.docs[ident])} for ident in data["ids"]]
            if self.failure == "readback":
                docs[0]["_source"]["text"] = "not the original source"
            value = {"docs": docs}
        elif path.endswith("/_mapping"):
            self.mapping["_meta"] = data["_meta"]
            value = {"acknowledged": True}
        elif path == "/" + INDEX and method == "GET":
            value = self.metadata()
        elif path.endswith("/_search"):
            value = {"timed_out": False, "_shards": {"failed": 0}, "hits": {"hits": [
                {"_index": INDEX, "_id": ident, "_source": row} for ident, row in self.docs.items()]}}
        else:
            raise AssertionError((method, path))
        return httpx.Response(200, json=value)

    def metadata(self):
        return {INDEX: {"aliases": self.aliases, "mappings": self.mapping, "settings": {"index": {"blocks": {"write": str(self.blocked).lower()}}}}}


@pytest.fixture
def case(tmp_path, monkeypatch):
    (tmp_path / "publication.lock").touch()
    release, server = Release(tmp_path), Server()
    original = httpx.Client
    monkeypatch.setattr(search_index.secrets, "token_hex", lambda _: "b" * 32)

    def client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return original(transport=httpx.MockTransport(server.response), **kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    return release, server


def test_build_is_create_only_sealed_verified_and_never_selected(case):
    release, server = case
    result = build_index(release, "http://opensearch:9200", RELEASE)
    assert result["status"] == "ready" and result["selected_for_search"] is False
    assert result["document_count"] == 1 and server.blocked
    assert server.docs == {document_id(source()): source()}
    assert all(request.url.path.startswith("/" + INDEX) for request in server.calls)
    assert not any(request.method == "DELETE" or "_aliases" in request.url.path for request in server.calls)
    body = json.loads(server.calls[0].content)
    assert body["mappings"]["properties"] == properties()
    assert body["mappings"]["_meta"]["status"] == "building"
    search = PublicSearchService("http://opensearch:9200", INDEX, RELEASE, release)
    result = search.search("sözleşme")
    assert result["hits"][0]["text"] == source()["text"] and result["hits"][0]["source_url"] is None
    assert result["snapshot"]["index_schema"] == SCHEMA


@pytest.mark.parametrize("failure,stage", [("collision", "create"), ("bulk", "write"), ("truncated_bulk", "write"),
                                          ("refresh", "seal"), ("count", "verify"), ("readback", "verify")])
def test_partial_or_ambiguous_results_do_not_mark_ready_or_retry(case, failure, stage):
    release, server = case
    server.failure = failure
    with pytest.raises(IndexBuildError) as caught:
        build_index(release, "http://opensearch:9200", RELEASE)
    assert caught.value.stage == stage and caught.value.index == INDEX
    assert "PRIVATE" not in str(caught.value)
    assert not any(request.url.path.endswith("/_mapping") or request.method == "DELETE" for request in server.calls)
    assert sum(request.method == "PUT" and request.url.path == "/" + INDEX for request in server.calls) == 1


@pytest.mark.parametrize("when", ["entry", "exit"])
def test_authorization_failure_never_reports_a_successful_build(case, when):
    release, server = case
    setattr(release, "fail_" + when, True)
    with pytest.raises(IndexBuildError) as caught:
        build_index(release, "http://opensearch:9200", RELEASE)
    assert caught.value.stage == ("authorization" if when == "entry" else "authorization_exit")
    if when == "entry":
        assert server.calls == []
    else:
        assert server.mapping["_meta"]["status"] == "ready"  # Explicit completion uncertainty; no automatic selection.


@pytest.mark.parametrize("kind", ["empty", "too_many", "too_large", "conflict", "invalid_date"])
def test_preparation_failures_make_no_network_writes(case, monkeypatch, kind):
    release, server = case
    if kind == "empty":
        release.rows = []
    elif kind == "too_many":
        monkeypatch.setattr(search_index, "MAX_DOCUMENTS", 1)
        release.rows.append(source("urn:test:assertion:2"))
    elif kind == "too_large":
        monkeypatch.setattr(search_index, "MAX_BYTES", 1)
    elif kind == "conflict":
        release.rows.append({**source(), "text": "different"})
    else:
        release.rows[0]["valid_to"] = "unknown"
    with pytest.raises(IndexBuildError):
        build_index(release, "http://opensearch:9200", RELEASE)
    assert not server.calls


@pytest.mark.parametrize("mutation", ["building", "writable", "mapping", "release", "alias", "digest"])
def test_reader_refuses_unsealed_or_foreign_managed_indexes_before_search(case, mutation):
    release, server = case
    build_index(release, "http://opensearch:9200", RELEASE)
    if mutation == "writable":
        server.blocked = False
    elif mutation == "mapping":
        server.mapping["properties"]["text"]["analyzer"] = "standard"
    elif mutation == "alias":
        server.aliases = {"unexpected": {}}
    else:
        key, value = {"building": ("status", "building"), "release": ("release_id", "d" * 64),
                      "digest": ("documents_sha256", "invalid")}[mutation]
        server.mapping["_meta"][key] = value
    server.calls.clear()
    result = PublicSearchService("http://opensearch:9200", INDEX, RELEASE, release).search("sözleşme")
    assert not result["hits"] and result["coverage"]["status"] == "unavailable"
    assert [request.method for request in server.calls] == ["GET"]


def test_multiple_historical_assertions_for_one_passage_are_not_false_conflicts(case):
    release, server = case
    release.rows.append({**source("urn:test:assertion:2"), "valid_from": "2012-01-01", "valid_to": "2014-01-01"})
    build_index(release, "http://opensearch:9200", RELEASE)
    result = PublicSearchService("http://opensearch:9200", INDEX, RELEASE, release).search("sözleşme")
    assert len(result["hits"]) == 2 and result["coverage"]["rejected_hits"] == 0
    assert {row["assertion_id"] for row in result["hits"]} == {row["assertion_id"] for row in release.rows}


def test_deadline_and_release_mismatch_prevent_writes(case, monkeypatch):
    release, server = case
    with pytest.raises(IndexBuildError):
        build_index(release, "http://opensearch:9200", "d" * 64)
    assert not server.calls
    monkeypatch.setattr(search_index, "BUILD_SECONDS", -1)
    with pytest.raises(IndexBuildError):
        build_index(release, "http://opensearch:9200", RELEASE)
    assert not server.calls


def test_managed_index_name_must_bind_exact_release_and_cannot_be_an_alias():
    for index in (INDEX + ",private", INDEX + "/_all", "law-public-passages-" + RELEASE, INDEX.replace(RELEASE, "d" * 64)):
        with pytest.raises(ValueError):
            PublicSearchService("http://opensearch:9200", index, RELEASE)
    assert canonical(source()).decode().find("Sözleşmeler") > 0


def test_index_changed_after_retrieval_discards_even_valid_passages(case, monkeypatch):
    release, server = case
    build_index(release, "http://opensearch:9200", RELEASE)
    search = PublicSearchService("http://opensearch:9200", INDEX, RELEASE, release)
    original = search._request

    def changed(*args):
        result = original(*args)
        server.blocked = False
        return result

    monkeypatch.setattr(search, "_request", changed)
    result = search.search("sözleşme")
    assert not result["hits"] and result["coverage"]["status"] == "unavailable"
