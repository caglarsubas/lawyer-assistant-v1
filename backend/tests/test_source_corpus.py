"""Invented source corpus; no law, live providers or permission grants."""

import json
from contextlib import contextmanager

import pytest
from rdflib import RDF, Graph, Literal, URIRef
from sqlalchemy import select
from test_workspace import workspace as workspace_fixture

from app import source_corpus
from app.db import Membership, User
from app.graph_release import LA, RuntimeGraphRelease
from app.source_corpus import SourceCorpusService

workspace = workspace_fixture


def release():
    value = RuntimeGraphRelease.__new__(RuntimeGraphRelease)
    value.info = {"release_id": "a" * 64, "serving_sha256": "b" * 64,
                  "ontology_sha256": "c" * 64, "pointer": {"sequence": 2}}
    value._resources = Graph()
    value.calls = []
    @contextmanager
    def guard():
        value.calls.append("entry")
        yield value.info
        value.calls.append("exit")
    value.current_guard = guard
    return value


def passage(value, name, text="TEST ONLY sözleşme örneği", scope="public", synthetic=False):
    graph = value._resources
    node, artifact, representation = (URIRef("urn:test:" + name + suffix) for suffix in ("", ":artifact", ":text"))
    for subject, fields in (
        (node, {RDF.type: LA.EvidencePassage, LA.artifact: artifact, LA.textRepresentation: representation,
                LA.scope: Literal(scope), LA.quotedText: Literal(text), LA.locator: Literal("page 1"),
                LA.startOffset: Literal(0), LA.endOffset: Literal(len(text))}),
        (artifact, {RDF.type: LA.SourceArtifact, LA.scope: Literal(scope), LA.synthetic: Literal(synthetic),
                    LA.rightsStatus: Literal("permitted"), LA.contentHash: Literal("d" * 64)}),
        (representation, {RDF.type: LA.SourceRepresentation, LA.scope: Literal(scope), LA.synthetic: Literal(synthetic),
                          LA.artifact: artifact, LA.contentHash: Literal("e" * 64), LA.locatorMapHash: Literal("f" * 64)}),
    ):
        for predicate, obj in fields.items():
            graph.add((subject, predicate, obj))
    return str(node), str(representation)


def test_source_discovery_preserves_quotes_without_assertions_dates_or_guessed_authorities():
    value = release()
    original = "TEST ONLY İş SÖZLEŞME örneği\n  Aynen alıntı."
    ident, version = passage(value, "unlinked", original)
    passage(value, "private", "PRIVATE-MATTER-CANARY sözleşme", scope="private")
    passage(value, "synthetic", "PRIVATE-SYNTHETIC-CANARY sözleşme", synthetic=True)
    before = set(value._resources)
    result = SourceCorpusService(value).search("sözleşme", as_of="1921-01-01")
    assert value.calls == ["entry", "exit"]
    assert result["coverage"]["eligible_passages"] == 1
    assert result["coverage"]["total_expected"] is None
    hit = result["hits"][0]
    assert (hit["passage_id"], hit["source_version_id"], hit["text"]) == (ident, version, original)
    assert hit["assertion_id"] is None and hit["authority_id"] is None
    assert hit["temporal_applicability"] == "not_assessed" and hit["finality"] == "unknown"
    assert hit["end_offset"] == len(original) and "PRIVATE" not in json.dumps(result)
    assert set(value._resources) == before
    assert SourceCorpusService(value).search("unmatched", passage_id=ident, source_version_id=version)["hits"]
    assert not SourceCorpusService(value).search("unmatched", passage_id=ident, source_version_id="urn:test:wrong")["hits"]


@pytest.mark.parametrize("boundary", ["entry", "exit"])
def test_guard_failure_withholds_all_results_and_private_details(boundary):
    value = release()
    passage(value, "one")
    @contextmanager
    def denied():
        if boundary == "entry":
            raise ValueError("PRIVATE-SOURCE-REVIEW-ID")
        yield value.info
        raise ValueError("PRIVATE-SOURCE-REVIEW-ID")
    value.current_guard = denied
    result = SourceCorpusService(value).search("sözleşme")
    assert not result["hits"] and result["coverage"]["status"] == "unavailable"
    assert result["snapshot"]["release_id"] is None and "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("budget", ["MAX_PASSAGES", "MAX_SCAN_BYTES", "SCAN_SECONDS", "MAX_RESPONSE_BYTES"])
def test_budget_limits_are_visible_and_never_claim_complete_corpus(monkeypatch, budget):
    value = release()
    passage(value, "one")
    passage(value, "two")
    monkeypatch.setattr(source_corpus, budget, 0 if budget == "SCAN_SECONDS" else 1)
    result = SourceCorpusService(value).search("sözleşme")
    assert result["coverage"]["status"] == "partial"
    assert result["coverage"]["total_expected"] is None
    assert result["coverage"]["budget_exhausted"] or result["coverage"]["result_limit_reached"]
    assert value.calls == ["entry", "exit"]


def test_oversized_quotes_remain_exactly_addressable_without_silent_lexical_omission():
    value = release()
    text = "sözleşme " * 2000
    ident, _ = passage(value, "long", text)
    service = SourceCorpusService(value)
    result = service.search("sözleşme")
    assert result["coverage"]["status"] == "partial"
    assert result["coverage"]["oversized_passages"] == 1
    assert service.search("identity lookup", passage_id=ident)["hits"][0]["text"] == text


@pytest.mark.parametrize("changes", [{"limit": True}, {"limit": 51}, {"query": " "},
    {"as_of": "2020-2-1"}, {"as_of": "2020-02-30"}, {"passage_id": "private id"}])
def test_invalid_typed_inputs_never_start_source_transaction(changes):
    value = release()
    with pytest.raises(ValueError):
        SourceCorpusService(value).search(**{"query": "test", **changes})
    assert not value.calls


def test_matter_authorization_precedes_retrieval_and_is_rechecked_before_return(workspace, monkeypatch):
    app, client, matter = workspace
    path = f"/api/v1/matters/{matter}/corpus/search"
    initial = client.post(path, json={"query": "private question"})
    assert initial.json()["coverage"]["status"] == "no_qualified_corpus"
    assert initial.headers["cache-control"] == "no-store"
    assert client.post(path, json={"query": "private question", "limit": True}).status_code == 422
    calls = []
    def search(*args, **kwargs):
        calls.append(kwargs)
        with app.state.store.session() as session:
            user = session.scalar(select(User).where(User.username == "demo"))
            membership = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.matter_id == matter))
            session.delete(membership)
            session.commit()
        return {"hits": [{"text": "must not escape after membership withdrawal"}]}
    monkeypatch.setattr(SourceCorpusService, "search", search)
    response = client.post(path, json={"query": "private question"})
    assert response.status_code == 404 and "must not escape" not in response.text
    assert len(calls) == 1
    assert client.post(path, json={"query": "private question"}).status_code == 404
    assert len(calls) == 1
