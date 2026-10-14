"""Invented RDF and HTTP responses; no actual law or legal qualification."""

import copy
import json
import time
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest
from rdflib import RDF, XSD, Graph, Literal, URIRef
from test_search_index import INDEX, RELEASE, Server
from test_source_corpus import passage, release

from app import retrieval_benchmark as module
from app.graph import GraphService
from app.graph_release import LA
from app.policy import POLICY_VERSION
from app.qualification_scoring import digest
from app.retrieval_benchmark import DiscoveryBenchmark, capture_discovery, score_discovery
from app.search import PublicSearchService
from app.search_index import build_index
from app.search_normalization import normalization_metadata
from app.source_corpus import SourceCorpusService, _project


@pytest.fixture
def discovery(tmp_path, monkeypatch):
    reader = release()
    reader.root = tmp_path
    (tmp_path / "publication.lock").touch()
    linked, _ = passage(reader, "linked", "TEST ONLY linked source")
    unlinked, _ = passage(reader, "unlinked", "TEST ONLY source without a graph path")
    subject, target, assertion = (URIRef("urn:test:" + name) for name in ("authority", "concept", "assertion"))
    for node in (subject, target):
        reader._resources.add((node, LA.scope, Literal("public")))
        reader._resources.add((node, LA.synthetic, Literal(False)))
    data = Graph()
    for key, value in {RDF.type: LA.Assertion, LA.graphFamily: Literal("structure"), LA.scope: Literal("public"),
        LA.synthetic: Literal(False), LA.validityStatus: Literal("known"), LA.claimStatus: Literal("legally_reviewed"),
        LA.subject: subject, LA.object: target, LA.predicate: LA.relatedConcept, LA.evidence: URIRef(linked),
        LA.validFrom: Literal("2010-01-01", datatype=XSD.date), LA.validTo: Literal("2012-01-01", datatype=XSD.date),
        LA.recordedAt: Literal("2026-01-01T00:00:00Z", datatype=XSD.dateTime),
        LA.reviewedAt: Literal("2026-01-01T00:00:00Z", datatype=XSD.dateTime), LA.reviewer: Literal("TEST ONLY")}.items():
        data.add((assertion, key, value))
    reader._graphs = {"structure": data, "jurisprudence": Graph()}
    reader.active = True
    @contextmanager
    def guard():
        if not reader.active:
            raise ValueError("PRIVATE PERMISSION")
        yield reader.info
        if not reader.active:
            raise ValueError("PRIVATE PERMISSION")
    reader.current_guard = guard
    reader.require_current = lambda: reader.info if reader.active else (_ for _ in ()).throw(ValueError("PRIVATE PERMISSION"))
    server = Server()
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(server.response), **kwargs))
    monkeypatch.setattr("app.search_index.secrets.token_hex", lambda _: "b" * 32)
    built = build_index(reader, "http://opensearch:9200", RELEASE)
    exact = _project(reader, URIRef(linked))
    evidence = {"id": linked, "artifact_id": exact["document_id"], "text_representation_id": exact["source_version_id"],
        "sha256": exact["source_sha256"], **{key: exact[key] for key in (
            "text", "locator", "text_sha256", "locator_map_sha256", "start_offset", "end_offset")}}
    response = {"mode": "fuseki", "snapshot": {"release_id": RELEASE, "serving_sha256": reader.info["serving_sha256"],
        "ontology_sha256": reader.info["ontology_sha256"], "graph": "structure", "as_of": "2011-01-01",
        "known_at": "2026-10-14T00:00:00Z"}, "edges": [{"id": str(assertion), "source": str(subject),
        "target": str(target), "predicate": str(LA.relatedConcept), "status": "legally_reviewed", "evidence": [evidence]}]}
    graph = GraphService.__new__(GraphService)
    graph.release = reader
    graph.tool = lambda *args: copy.deepcopy(response)
    benchmark = DiscoveryBenchmark.model_validate({"schema_version": "source-graph-discovery-benchmark-v1",
        "dataset_id": "synthetic-discovery", "purpose": "development", "origin": "synthetic",
        "adjudication_status": "pending", "adjudication_evidence_sha256": None,
        "snapshot": {"release_id": RELEASE, "serving_sha256": reader.info["serving_sha256"],
            "ontology_sha256": reader.info["ontology_sha256"], "activation_sequence": 2,
            "index": INDEX, "documents_sha256": built["documents_sha256"], "index_schema": "public-search-index-v3",
            "normalization": normalization_metadata(), "citation_profile": "tr-literal-citations-v1", "fusion": "rrf-k60-v1",
            "known_at": "2026-10-14T00:00:00Z", "source_recipe": "source-qualified-corpus-v1", "policy": POLICY_VERSION},
        "queries": [{"id": "q-one", "query": "TEST ONLY", "graph_query": "TEST ONLY", "graph_family": "structure",
            "family_sha256": "f" * 64, "practice": "contracts", "period": "2002_2015", "slices": ["adverse"],
            "as_of": "2011-01-01", "corpus_coverage": "covered", "source_coverage": "covered",
            "judgments": [{"authority_id": str(subject), "relevance": 3, "adverse": True}], "exact_target": str(subject),
            "passage_judgments": [{"passage_id": linked, "relevance": 3, "adverse": False},
                                  {"passage_id": unlinked, "relevance": 2, "adverse": True}]}]})
    return benchmark, PublicSearchService("http://opensearch:9200", INDEX, RELEASE, reader), graph, SourceCorpusService(reader), server, response


def capture(value, **kwargs):
    return capture_discovery(*value[:4], **kwargs)


def test_independent_source_paths_keep_distinct_passage_and_entity_denominators(discovery):
    run = capture(discovery)
    report = score_discovery(discovery[0], run)
    profiles = report["profiles"]
    assert profiles["source_lexical"]["passage_recall_at_20"] == {"value": 1.0, "queries": 1}
    assert profiles["source_lexical"]["candidate_entity_recall_at_20"] == {"value": None, "queries": 0}
    assert profiles["graph_grounded"]["passage_recall_at_20"]["value"] == 0.5
    assert profiles["authority_search"]["passage_recall_at_20"]["value"] == 0.5
    assert profiles["graph_grounded"]["adverse_passage_recall_at_20"]["value"] == 0.0
    assert profiles["source_lexical"]["adverse_passage_recall_at_20"]["value"] == 1.0
    assert report["production_qualified"] is False and report["observations_authenticated"] is False
    assert "TEST ONLY" not in json.dumps(report) and "PRIVATE" not in json.dumps(report)


def test_cli_scores_new_schema_without_claiming_authenticated_approval(discovery, tmp_path, capsys):
    from test_retrieval_benchmark import cli
    benchmark, run = tmp_path / "benchmark.json", tmp_path / "run.json"
    benchmark.write_text(discovery[0].model_dump_json())
    run.write_text(capture(discovery).model_dump_json())
    assert cli.main([str(benchmark), "--run", str(run)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema_version"] == "source-graph-discovery-report-v1"
    assert report["observations_authenticated"] is False and report["runtime_authorization"] == "none"


@pytest.mark.parametrize("change", ["rights", "pointer", "receipt", "quote", "edge", "date"])
def test_capture_discards_changes_or_forged_graph_evidence(discovery, change):
    benchmark, search, graph, sources, server, response = discovery
    original = sources.search
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if change == "rights":
            graph.release.active = False
        elif change == "pointer":
            graph.release.info["pointer"]["sequence"] += 1
        elif change == "receipt":
            server.mapping["_meta"]["documents_sha256"] = "0" * 64
        elif change == "quote":
            response["edges"][0]["evidence"][0]["text"] = "PRIVATE FORGED QUOTE"
        elif change == "edge":
            response["edges"][0]["predicate"] = str(LA.applies)
        else:
            response["snapshot"]["as_of"] = "2026-10-14"
        return result
    sources.search = changed
    with pytest.raises(ValueError):
        capture(discovery)


def test_total_budget_keeps_not_run_cells_and_unknown_coverage_is_unmeasured(discovery, monkeypatch):
    clock = iter(range(100))
    started = time.monotonic()
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: started + next(clock) * 1000.0))
    run = capture(discovery, seconds=1)
    assert len(run.observations) == 3 and all(item.status == "not_run" for item in run.observations)
    assert score_discovery(discovery[0], run)["profiles"]["source_lexical"]["passage_recall_at_20"]["value"] == 0.0
    raw = discovery[0].model_dump()
    raw["queries"][0].update(source_coverage="unknown", corpus_coverage="outside")
    changed = DiscoveryBenchmark.model_validate(raw)
    run = run.model_copy(update={"benchmark_sha256": digest(changed.model_dump(mode="json"))})
    report = score_discovery(changed, run)
    assert report["profiles"]["source_lexical"]["passage_recall_at_20"]["value"] is None
    assert report["profiles"]["graph_grounded"]["candidate_entity_recall_at_20"]["value"] is None


@pytest.mark.parametrize("change", ["missing", "duplicate", "source_authority", "run_hash", "snapshot", "constructed"])
def test_mixed_or_incomplete_runs_and_source_authority_promotion_are_rejected(discovery, change):
    run = capture(discovery).model_dump()
    if change == "missing":
        run["observations"].pop()
    elif change == "duplicate":
        run["observations"].append(copy.deepcopy(run["observations"][0]))
    elif change == "source_authority":
        run["observations"][0]["authority_ids"] = ["urn:test:invented"]
    elif change == "run_hash":
        run["benchmark_sha256"] = "0" * 64
    elif change == "snapshot":
        run["snapshot"]["ontology_sha256"] = "0" * 64
    else:
        from app.retrieval_benchmark import DiscoveryRun
        run["snapshot"]["known_at"] = ""
        run = DiscoveryRun.model_construct(**run)
    with pytest.raises(ValueError):
        score_discovery(discovery[0], run)
