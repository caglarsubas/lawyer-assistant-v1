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

from .qualification_scoring import digest, unique
from .research_qualification import Digest, Practice, RecordId, StrictRecord
from .search import PublicSearchService, _entity_id
from .search_index_contract import MANAGED, ready_metadata
from .search_normalization import normalization_metadata

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
