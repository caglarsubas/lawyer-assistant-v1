"""Development retrieval comparisons over one frozen public snapshot.

Captures use the existing authorized source projection. Offline observations and
judgments remain supplied evidence, not authenticated legal approval. No provider,
private matter, graph mutation, index build or selection is performed here.
"""

import math
import random
import time
from collections import Counter, defaultdict
from statistics import mean
from typing import Literal

from pydantic import Field, model_validator
from rdflib import RDF, URIRef

from .graph import GraphService, _datetime
from .graph_release import LA
from .policy import POLICY_VERSION
from .qualification_scoring import digest, unique
from .research_qualification import Digest, Practice, RecordId, StrictRecord
from .search import PublicSearchService, _entity_id
from .search_index_contract import MANAGED, ready_metadata
from .search_normalization import normalization_metadata
from .source_corpus import RECIPE as SOURCE_RECIPE
from .source_corpus import SourceCorpusService, _project

PROFILES = ("lexical", "turkish", "all")
SLICES = Literal["citation", "temporal_transition", "adverse", "ocr", "concept_confusion", "missing_coverage", "roles"]
METRICS = ("recall_at_20", "ndcg_at_10", "adverse_recall_at_20", "exact_target_hit_at_20")
BOOTSTRAP_SAMPLES = 500


class BenchmarkSnapshot(StrictRecord):
    release_id: Digest
    serving_sha256: Digest
    activation_sequence: int = Field(ge=1)
    index: str = Field(min_length=1, max_length=160)
    documents_sha256: Digest
    index_schema: Literal["public-search-index-v3"]
    normalization: dict[str, str]
    citation_profile: Literal["tr-literal-citations-v1"]
    fusion: Literal["rrf-k60-v1"]

    @model_validator(mode="after")
    def bound_index(self):
        match = MANAGED.fullmatch(self.index)
        if not match or match[1] != self.release_id or self.normalization != normalization_metadata():
            raise ValueError("Benchmark index or normalization differs")
        return self


class Judgment(StrictRecord):
    authority_id: str = Field(min_length=1, max_length=512)
    relevance: int = Field(ge=0, le=3)
    adverse: bool

    @model_validator(mode="after")
    def valid(self):
        if not _entity_id(self.authority_id) or (self.adverse and not self.relevance):
            raise ValueError("Invalid judged authority or adverse relevance")
        return self


class BenchmarkQuery(StrictRecord):
    id: RecordId
    query: str = Field(min_length=1, max_length=4000)
    family_sha256: Digest
    practice: Practice
    period: Literal["earlier", "1920_1981", "1982_2001", "2002_2015", "2016_onward", "unknown"]
    slices: list[SLICES] = Field(max_length=7)
    as_of: str | None
    corpus_coverage: Literal["covered", "outside", "unknown"]
    judgments: list[Judgment] = Field(max_length=100)
    exact_target: str | None

    @model_validator(mode="after")
    def valid(self):
        from .search import _iso_date
        if not self.query.strip():
            raise ValueError("Empty benchmark query")
        if self.as_of is not None:
            _iso_date(self.as_of)
        unique(self.slices)
        unique([row.authority_id for row in self.judgments])
        if self.exact_target is not None and self.exact_target not in {
            row.authority_id for row in self.judgments if row.relevance
        }:
            raise ValueError("Exact target requires a positive judgment")
        return self


class RetrievalBenchmark(StrictRecord):
    schema_version: Literal["retrieval-development-benchmark-v1"]
    dataset_id: RecordId
    purpose: Literal["development"]
    origin: Literal["real", "synthetic"]
    adjudication_status: Literal["pending", "adjudicated"]
    adjudication_evidence_sha256: Digest | None
    snapshot: BenchmarkSnapshot
    queries: list[BenchmarkQuery] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def valid(self):
        unique([row.id for row in self.queries])
        unique([digest({"query": row.query, "as_of": row.as_of}) for row in self.queries])
        if self.adjudication_status == "adjudicated" and self.adjudication_evidence_sha256 is None:
            raise ValueError("Adjudication evidence is required")
        return self


class RetrievalObservation(StrictRecord):
    query_id: RecordId
    profile: Literal["lexical", "turkish", "all"]
    status: Literal["available", "partial", "unavailable", "not_run"]
    authority_ids: list[str] = Field(max_length=20)
    returned_passages: int = Field(ge=0, le=20)
    rejected_hits: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0)

    @model_validator(mode="after")
    def valid(self):
        unique(self.authority_ids)
        if (not all(_entity_id(value) for value in self.authority_ids)
                or len(self.authority_ids) > self.returned_passages
                or (self.status in {"unavailable", "not_run"} and (self.authority_ids or self.returned_passages))
                or (self.status == "available" and self.rejected_hits)):
            raise ValueError("Invalid retrieval observation")
        return self


class RetrievalRun(StrictRecord):
    schema_version: Literal["retrieval-development-run-v1"]
    benchmark_sha256: Digest
    snapshot: BenchmarkSnapshot
    observations: list[RetrievalObservation] = Field(min_length=3, max_length=3000)


def _graph_pin(search):
    info = search.graph_release.require_current()
    return {"release_id": info["release_id"], "serving_sha256": info["serving_sha256"],
            "activation_sequence": info["pointer"]["sequence"]}


def _check_receipt(search, expected):
    meta = ready_metadata(search.index, search._read_json("GET", "", None, time.monotonic() + 12), search.release_id)
    if any(meta.get(key) != expected[key] for key in
           ("documents_sha256", "normalization", "citation_profile")) or meta["schema"] != expected["index_schema"]:
        raise ValueError("Benchmark index receipt differs")


def capture_run(benchmark, search, *, seconds=120):
    """Run sequentially with a cooperative total budget; keep every planned cell.

    The injected service must be bound to a currently authorized signed release.
    No guard is held across the entire benchmark: each search checks permission,
    and revocation/snapshot changes discard the capture rather than hold writers.
    """
    benchmark = RetrievalBenchmark.model_validate(benchmark).model_copy(deep=True)
    if (not isinstance(search, PublicSearchService) or not search.managed or not search.configured
            or type(seconds) is not int or not 1 <= seconds <= 7200):
        raise ValueError("Invalid benchmark service or execution budget")
    expected = benchmark.snapshot.model_dump(mode="json")
    graph_pin = {key: expected[key] for key in ("release_id", "serving_sha256", "activation_sequence")}
    if search.index != expected["index"] or _graph_pin(search) != graph_pin:
        raise ValueError("Benchmark graph/index differs")
    _check_receipt(search, expected)
    deadline = time.monotonic() + seconds
    rows = []
    for position, query in enumerate(benchmark.queries):
        # Rotate the first profile to reduce a fixed warm-cache ordering bias.
        rotation = position % len(PROFILES)
        for profile in PROFILES[rotation:] + PROFILES[:rotation]:
            if time.monotonic() >= deadline:
                rows.append(RetrievalObservation(query_id=query.id, profile=profile, status="not_run",
                    authority_ids=[], returned_passages=0, rejected_hits=0, elapsed_seconds=0.0))
                continue
            if _graph_pin(search) != graph_pin:
                raise ValueError("Benchmark authorization or graph snapshot changed")
            started = time.monotonic()
            result = search.search(query.query, as_of=query.as_of, limit=20, profile=profile)
            if _graph_pin(search) != graph_pin:
                raise ValueError("Benchmark authorization or graph snapshot changed")
            actual = result["snapshot"]
            # An unavailable receipt is not a measurement on the frozen index.
            if any(actual.get(key) != value for key, value in expected.items() if key not in graph_pin):
                raise ValueError("Benchmark search receipt differs")
            status = result["coverage"]["status"]
            if status not in {"available", "partial", "unavailable"}:
                raise ValueError("Invalid benchmark search coverage")
            authorities = list(dict.fromkeys(hit["authority_id"] for hit in result["hits"]))
            rows.append(RetrievalObservation(query_id=query.id, profile=profile, status=status,
                authority_ids=authorities, returned_passages=len(result["hits"]),
                rejected_hits=result["coverage"]["rejected_hits"], elapsed_seconds=time.monotonic() - started))
    if _graph_pin(search) != graph_pin:
        raise ValueError("Benchmark authorization or graph snapshot changed")
    _check_receipt(search, expected)
    if _graph_pin(search) != graph_pin:
        raise ValueError("Benchmark authorization or graph snapshot changed")
    return RetrievalRun(schema_version="retrieval-development-run-v1",
        benchmark_sha256=digest(benchmark.model_dump(mode="json")), snapshot=benchmark.snapshot, observations=rows)


def query_metrics(query, observation):
    """Repeated passages count once, in order of the first returned authority.

    Recall ranks at most 20 distinct authorities from the first 20 returned
    passage/assertion records. It does not retrieve extra passages to fill ranks.
    Unknown judgments receive no relevance gain, with their count reported.
    """
    grades = {row.authority_id: row.relevance for row in query.judgments}
    gold = {value for value, grade in grades.items() if grade}
    adverse = {row.authority_id for row in query.judgments if row.adverse}
    found = set(observation.authority_ids)
    measured = query.corpus_coverage == "covered"
    ideal = sum((2 ** grade - 1) / math.log2(rank + 2)
                for rank, grade in enumerate(sorted(grades.values(), reverse=True)[:10]))
    dcg = sum((2 ** grades.get(value, 0) - 1) / math.log2(rank + 2)
              for rank, value in enumerate(observation.authority_ids[:10]))
    return {
        "recall_at_20": len(gold & found) / len(gold) if measured and gold else None,
        "ndcg_at_10": dcg / ideal if measured and ideal else None,
        "adverse_recall_at_20": len(adverse & found) / len(adverse) if measured and adverse else None,
        "exact_target_hit_at_20": float(query.exact_target in found) if measured and query.exact_target else None,
        "unjudged_authorities": len(found - set(grades)),
    }


def _aggregate(rows):
    result = {"queries": len(rows), "statuses": dict(sorted(Counter(row[1].status for row in rows).items())),
              "coverage": dict(sorted(Counter(row[0].corpus_coverage for row in rows).items())),
              "unjudged_authorities": sum(row[2]["unjudged_authorities"] for row in rows),
              "returned_passages": sum(row[1].returned_passages for row in rows),
              "returned_unique_authorities": sum(len(row[1].authority_ids) for row in rows)}
    for metric in METRICS:
        # All covered answerable cases stay in the denominator: outage/not_run
        # cells carry empty rankings and count as missed authorities.
        values = [row[2][metric] for row in rows if row[2][metric] is not None]
        result[metric] = {"value": mean(values) if values else None, "queries": len(values)}
    times = [row[1].elapsed_seconds for row in rows if row[1].status != "not_run"]
    result["elapsed_seconds"] = {"mean": mean(times) if times else None, "executed_queries": len(times)}
    return result


def _percentile(values, probability):
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _paired(rows, baseline, candidate, seed):
    report = {"baseline": baseline, "candidate": candidate, "metrics": {}}
    for metric in METRICS:
        families = defaultdict(list)
        excluded = 0
        for query, observations, scores in rows:
            left, right = scores[baseline][metric], scores[candidate][metric]
            if observations[baseline].status != "available" or observations[candidate].status != "available" or left is None or right is None:
                excluded += 1
                continue
            families[query.family_sha256].append(right - left)
        values = [value for family in families.values() for value in family]
        result = {"candidate_minus_baseline": mean(values) if values else None,
                  "paired_queries": len(values), "independent_families_declared": len(families),
                  "excluded_queries": excluded, "improved": sum(value > 0 for value in values),
                  "regressed": sum(value < 0 for value in values), "unchanged": sum(value == 0 for value in values),
                  "interval_95": None}
        if len(families) >= 2:
            rng = random.Random(seed + metric)
            blocks = [families[key] for key in sorted(families)]
            samples = []
            for _ in range(BOOTSTRAP_SAMPLES):
                chosen = [blocks[rng.randrange(len(blocks))] for _ in blocks]
                samples.append(sum(sum(block) for block in chosen) / sum(len(block) for block in chosen))
            result["interval_95"] = [_percentile(samples, 0.025), _percentile(samples, 0.975)]
        report["metrics"][metric] = result
    return report


def score_run(benchmark, run):
    benchmark = RetrievalBenchmark.model_validate(benchmark)
    run = RetrievalRun.model_validate(run)
    pin = digest(benchmark.model_dump(mode="json"))
    if run.benchmark_sha256 != pin or run.snapshot != benchmark.snapshot:
        raise ValueError("Benchmark run differs from the frozen input")
    observations = {(row.query_id, row.profile): row for row in run.observations}
    expected = {(query.id, profile) for query in benchmark.queries for profile in PROFILES}
    if len(observations) != len(run.observations) or set(observations) != expected:
        raise ValueError("Missing, repeated or unknown query/profile cells")
    paired = []
    profiles = {}
    for profile in PROFILES:
        rows = [(query, observations[query.id, profile], query_metrics(query, observations[query.id, profile]))
                for query in benchmark.queries]
        profiles[profile] = _aggregate(rows)
        for field in ("practice", "period"):
            profiles[profile]["by_" + field] = {value: _aggregate([row for row in rows if getattr(row[0], field) == value])
                                               for value in sorted({getattr(row[0], field) for row in rows})}
        profiles[profile]["by_slice"] = {value: _aggregate([row for row in rows if value in row[0].slices])
                                         for value in sorted({value for row in rows for value in row[0].slices})}
    for query in benchmark.queries:
        cells = {profile: observations[query.id, profile] for profile in PROFILES}
        paired.append((query, cells, {profile: query_metrics(query, cells[profile]) for profile in PROFILES}))
    practices = Counter(query.practice for query in benchmark.queries)
    temporal = sum("temporal_transition" in query.slices for query in benchmark.queries)
    return {"schema_version": "retrieval-development-report-v1", "purpose": "development",
            "production_qualified": False, "runtime_authorization": "none",
            "origin": benchmark.origin, "adjudication_status": benchmark.adjudication_status,
            "benchmark_sha256": pin, "snapshot": benchmark.snapshot.model_dump(mode="json"),
            "queries": len(benchmark.queries), "practice_counts": dict(sorted(practices.items())),
            "temporal_transition_queries": temporal,
            "planned_inventory": {"queries": 360, "per_practice": 120, "temporal_fraction": 0.3},
            "profiles": profiles,
            "paired": [_paired(paired, "lexical", "turkish", pin), _paired(paired, "turkish", "all", pin)],
            "uncertainty": {"method": "paired_family_block_percentile_bootstrap", "samples": BOOTSTRAP_SAMPLES,
                            "seed": pin, "minimum_families": 2},
            "limitations": ["Supplied judgments and captured observations require independent evidence review; hashes do not authenticate them.",
                "Metrics concern containing authority IDs, not the targets or legal effects of citations.",
                "Partial, unavailable and unexecuted cells count as misses in aggregate recall; paired intervals use available cells only.",
                "Unknown/outside corpus coverage and empty positive gold sets are unmeasured, not successful retrieval.",
                "Unjudged authorities receive zero gain; nDCG depends on the judged relevance pool.",
                "Intervals use declared source/proceeding/duplicate families; they do not discover leakage or establish representative sample size.",
                "Three lexical profiles do not qualify vectors, rerankers, graph ablations, legal analysis or the held-out release suite."]}


# Separate schema and denominators: source passages never become authority IDs.
DISCOVERY_PROFILES = ("source_lexical", "authority_search", "graph_grounded")


class DiscoverySnapshot(BenchmarkSnapshot):
    ontology_sha256: Digest
    known_at: str = Field(min_length=20, max_length=40)
    source_recipe: Literal["source-qualified-corpus-v1"]
    policy: str

    @model_validator(mode="after")
    def policies(self):
        if (_datetime(self.known_at) != self.known_at
                or self.policy != POLICY_VERSION or self.source_recipe != SOURCE_RECIPE):
            raise ValueError("Discovery policy or source recipe differs")
        return self


class PassageJudgment(StrictRecord):
    passage_id: str = Field(min_length=1, max_length=512)
    relevance: int = Field(ge=0, le=3)
    adverse: bool

    @model_validator(mode="after")
    def valid(self):
        if not _entity_id(self.passage_id) or (self.adverse and not self.relevance):
            raise ValueError("Invalid source passage judgment")
        return self


class DiscoveryQuery(BenchmarkQuery):
    graph_query: str = Field(min_length=1, max_length=300)
    graph_family: Literal["structure", "jurisprudence"]
    source_coverage: Literal["covered", "outside", "unknown"]
    passage_judgments: list[PassageJudgment] = Field(max_length=100)

    @model_validator(mode="after")
    def sources(self):
        unique([item.passage_id for item in self.passage_judgments])
        if not self.graph_query.strip() or self.as_of is None:
            raise ValueError("A dated graph discovery query is required")
        return self


class DiscoveryBenchmark(StrictRecord):
    schema_version: Literal["source-graph-discovery-benchmark-v1"]
    dataset_id: RecordId
    purpose: Literal["development"]
    origin: Literal["real", "synthetic"]
    adjudication_status: Literal["pending", "adjudicated"]
    adjudication_evidence_sha256: Digest | None
    snapshot: DiscoverySnapshot
    queries: list[DiscoveryQuery] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def valid(self):
        unique([item.id for item in self.queries])
        unique([digest({"query": item.query, "as_of": item.as_of}) for item in self.queries])
        if self.adjudication_status == "adjudicated" and self.adjudication_evidence_sha256 is None:
            raise ValueError("Adjudication evidence is required")
        return self


class DiscoveryObservation(StrictRecord):
    query_id: RecordId
    profile: Literal["source_lexical", "authority_search", "graph_grounded"]
    status: Literal["available", "partial", "unavailable", "not_run"]
    passage_ids: list[str] = Field(max_length=20)
    authority_ids: list[str] = Field(max_length=20)
    truncated: bool
    elapsed_seconds: float = Field(ge=0)

    @model_validator(mode="after")
    def valid(self):
        for values in (self.passage_ids, self.authority_ids):
            unique(values)
            if not all(_entity_id(value) for value in values):
                raise ValueError("Invalid discovery identities")
        if (self.profile == "source_lexical" and self.authority_ids
                or self.status in {"unavailable", "not_run"} and (self.passage_ids or self.authority_ids)):
            raise ValueError("Source discovery cannot resolve authorities or emit withheld results")
        return self


class DiscoveryRun(StrictRecord):
    schema_version: Literal["source-graph-discovery-run-v1"]
    benchmark_sha256: Digest
    snapshot: DiscoverySnapshot
    observations: list[DiscoveryObservation] = Field(min_length=3, max_length=3000)


def _discovery_pin(info):
    return {"release_id": info["release_id"], "serving_sha256": info["serving_sha256"],
        "ontology_sha256": info["ontology_sha256"], "activation_sequence": info["pointer"]["sequence"]}


def _graph_discovery(graph, query, expected):
    result = graph.tool("locate_issues", {"query": query.graph_query, "graph": query.graph_family,
        "as_of": query.as_of, "known_at": expected["known_at"], "limit": 20})
    if result.get("mode") != "fuseki":
        return "unavailable", [], [], False
    snapshot = result.get("snapshot", {})
    if (any(snapshot.get(key) != expected[key] for key in ("release_id", "serving_sha256", "ontology_sha256", "known_at"))
            or snapshot.get("as_of") != query.as_of or snapshot.get("graph") != query.graph_family
            or not isinstance(result.get("edges"), list) or len(result["edges"]) > 20):
        raise ValueError("Graph discovery snapshot or budget differs")
    passages, authorities = [], []
    # Inspect signed inputs after graph transport, never nest a source guard
    # inside the transport's own checks or trust result labels/quotes alone.
    with graph.release.current_guard() as info:
        if any(_discovery_pin(info)[key] != expected[key] for key in _discovery_pin(info)):
            raise ValueError("Graph discovery changed")
        source_graph = graph.release._graphs[query.graph_family]
        for edge in result["edges"]:
            assertion = URIRef(edge["id"])
            if ((assertion, RDF.type, LA.Assertion) not in source_graph
                    or edge.get("status") != str(graph.release._one(source_graph, assertion, LA.claimStatus))):
                raise ValueError("Graph discovery assertion differs")
            if edge["status"] != "legally_reviewed":
                continue
            if not graph.release._eligible(query.graph_family, assertion, as_of=query.as_of, known_at=expected["known_at"]):
                raise ValueError("Graph discovery is outside its historical evidence scope")
            for key, predicate in (("source", LA.subject), ("target", LA.object), ("predicate", LA.predicate)):
                if edge.get(key) != str(graph.release._one(source_graph, assertion, predicate)):
                    raise ValueError("Graph discovery relationship differs")
            evidence = edge.get("evidence")
            if not isinstance(evidence, list) or not 1 <= len(evidence) <= 20:
                raise ValueError("Graph evidence exceeds its bounded inspection budget")
            for item in evidence:
                node = URIRef(item["id"])
                if ((assertion, LA.evidence, node) not in source_graph
                        or not graph.release._evidence_eligible(graph.release._resources, node)):
                    raise ValueError("Graph passage is not evidenced")
                exact = _project(graph.release, node)
                fields = {"artifact_id": "document_id", "text_representation_id": "source_version_id",
                    "sha256": "source_sha256", "text": "text", "locator": "locator", "text_sha256": "text_sha256",
                    "locator_map_sha256": "locator_map_sha256", "start_offset": "start_offset", "end_offset": "end_offset"}
                if any(str(item.get(key)) != str(exact[value]) for key, value in fields.items()):
                    raise ValueError("Graph evidence differs from the exact source")
                passages.append(exact["passage_id"])
            authorities.extend((edge["source"], edge["target"]))
    passages, authorities = list(dict.fromkeys(passages)), list(dict.fromkeys(authorities))
    truncated = len(passages) > 20 or len(authorities) > 20 or len(result["edges"]) == 20
    return "partial" if truncated else "available", passages[:20], authorities[:20], truncated


def capture_discovery(benchmark, search, graph, sources, *, seconds=120):
    """Development only; independently bounded channels, no private matters/inference.

    Every channel uses the same signed public release and final index receipt.
    Source/pointer/receipt change discards the capture, never creates a partial
    authority verdict or a repeat request. Unexecuted planned cells are retained.
    """
    benchmark = DiscoveryBenchmark.model_validate(benchmark.model_dump(warnings=False) if isinstance(benchmark, DiscoveryBenchmark) else benchmark)
    if (not isinstance(search, PublicSearchService) or not search.managed or not search.configured
            or not isinstance(graph, GraphService) or not isinstance(sources, SourceCorpusService)
            or graph.release is not sources.release or graph.release is not search.graph_release
            or type(seconds) is not int or not 1 <= seconds <= 7200):
        raise ValueError("Invalid discovery services or execution budget")
    expected = benchmark.snapshot.model_dump(mode="json")
    def check():
        with graph.release.current_guard() as info:
            if any(_discovery_pin(info)[key] != expected[key] for key in _discovery_pin(info)):
                raise ValueError("Discovery release or authorization differs")
    check()
    if search.index != expected["index"]:
        raise ValueError("Discovery index differs")
    _check_receipt(search, expected)
    deadline, rows = time.monotonic() + seconds, []
    for position, query in enumerate(benchmark.queries):
        rotation = position % len(DISCOVERY_PROFILES)
        for profile in DISCOVERY_PROFILES[rotation:] + DISCOVERY_PROFILES[:rotation]:
            if time.monotonic() >= deadline:
                rows.append(DiscoveryObservation(query_id=query.id, profile=profile, status="not_run",
                    passage_ids=[], authority_ids=[], truncated=False, elapsed_seconds=0.0))
                continue
            check()
            started = time.monotonic()
            if profile == "graph_grounded":
                status, passages, authorities, truncated = _graph_discovery(graph, query, expected)
            else:
                result = (sources.search(query.query, as_of=query.as_of, limit=20) if profile == "source_lexical"
                    else search.search(query.query, as_of=query.as_of, limit=20))
                if result["snapshot"].get("release_id") != expected["release_id"]:
                    raise ValueError("Discovery channel release differs")
                if profile == "authority_search" and any(result["snapshot"].get(key) != expected[key] for key in (
                        "index", "documents_sha256", "index_schema", "normalization", "citation_profile", "fusion")):
                    raise ValueError("Discovery search receipt differs")
                status = result["coverage"]["status"]
                hits = result["hits"]
                if profile == "authority_search":
                    eligible = []
                    with graph.release.current_guard() as info:
                        if any(_discovery_pin(info)[key] != expected[key] for key in _discovery_pin(info)):
                            raise ValueError("Authority discovery changed")
                        for hit in hits:
                            assertion = URIRef(hit["assertion_id"])
                            families = [family for family, data in graph.release._graphs.items()
                                if (assertion, RDF.type, LA.Assertion) in data]
                            if len(families) != 1:
                                raise ValueError("Authority assertion family is ambiguous")
                            if graph.release._eligible(families[0], assertion, as_of=query.as_of, known_at=expected["known_at"]):
                                eligible.append(hit)
                    hits = eligible
                passages = list(dict.fromkeys(hit["passage_id"] for hit in hits))
                authorities = ([] if profile == "source_lexical" else
                    list(dict.fromkeys(hit["authority_id"] for hit in hits)))
                truncated = bool(result["coverage"].get("result_limit_reached")) or len(result["hits"]) == 20
            check()
            rows.append(DiscoveryObservation(query_id=query.id, profile=profile, status=status,
                passage_ids=passages, authority_ids=authorities, truncated=truncated,
                elapsed_seconds=time.monotonic() - started))
    _check_receipt(search, expected)
    check()
    return DiscoveryRun(schema_version="source-graph-discovery-run-v1",
        benchmark_sha256=digest(benchmark.model_dump(mode="json")), snapshot=benchmark.snapshot, observations=rows)


def score_discovery(benchmark, run):
    benchmark = DiscoveryBenchmark.model_validate(benchmark.model_dump(warnings=False) if isinstance(benchmark, DiscoveryBenchmark) else benchmark)
    run = DiscoveryRun.model_validate(run.model_dump(warnings=False) if isinstance(run, DiscoveryRun) else run)
    if (run.benchmark_sha256 != digest(benchmark.model_dump(mode="json")) or run.snapshot != benchmark.snapshot):
        raise ValueError("Discovery inputs or snapshot differ")
    observations = {(item.query_id, item.profile): item for item in run.observations}
    planned = {(query.id, profile) for query in benchmark.queries for profile in DISCOVERY_PROFILES}
    if len(observations) != len(run.observations) or set(observations) != planned:
        raise ValueError("Every planned discovery cell is required exactly once")
    profiles = {}
    for profile in DISCOVERY_PROFILES:
        passage_scores, authority_scores, adverse_scores = [], [], []
        statuses = Counter()
        for query in benchmark.queries:
            row = observations[query.id, profile]
            statuses[row.status] += 1
            gold = {item.passage_id for item in query.passage_judgments if item.relevance}
            adverse = {item.passage_id for item in query.passage_judgments if item.adverse}
            if query.source_coverage == "covered" and gold:
                passage_scores.append(len(gold & set(row.passage_ids)) / len(gold))
            if query.source_coverage == "covered" and adverse:
                adverse_scores.append(len(adverse & set(row.passage_ids)) / len(adverse))
            authorities = {item.authority_id for item in query.judgments if item.relevance}
            if profile != "source_lexical" and query.corpus_coverage == "covered" and authorities:
                authority_scores.append(len(authorities & set(row.authority_ids)) / len(authorities))
        def metric(values):
            return {"value": mean(values) if values else None, "queries": len(values)}
        profiles[profile] = {"statuses": dict(sorted(statuses.items())),
            "passage_recall_at_20": metric(passage_scores), "adverse_passage_recall_at_20": metric(adverse_scores),
            "candidate_entity_recall_at_20": metric(authority_scores)}
    return {"schema_version": "source-graph-discovery-report-v1", "origin": benchmark.origin,
        "benchmark_sha256": run.benchmark_sha256, "snapshot": run.snapshot.model_dump(mode="json"),
        "profiles": profiles, "queries": len(benchmark.queries), "observations_authenticated": False,
        "production_qualified": False, "legal_qualification": False, "runtime_authorization": "none",
        "limitations": ["Passage and candidate entity denominators are independent; source passages do not resolve authorities.",
            "Graph endpoints and source matches nominate candidates, not endorsement, binding effect or matter applicability.",
            "Unknown/outside coverage and empty positive gold are unmeasured; unavailable and unexecuted covered cells are misses.",
            "Judgments, provenance labels and offline observations require independent review; scoring does not authenticate them.",
            "This development comparison does not establish legal correctness, nationwide recall, productivity or held-out acceptance."]}
