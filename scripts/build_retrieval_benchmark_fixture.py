#!/usr/bin/env python3
"""Generate invented benchmark inputs/rankings; does not execute retrieval."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.qualification_scoring import digest  # noqa: E402
from app.retrieval_benchmark import RetrievalBenchmark, RetrievalRun  # noqa: E402
from app.search_normalization import normalization_metadata  # noqa: E402


def fixture_inputs():
    release = "a" * 64
    snapshot = {"release_id": release, "serving_sha256": "c" * 64, "activation_sequence": 1,
                "index": f"law-public-passages-{release}-{'b' * 32}", "documents_sha256": "d" * 64,
                "index_schema": "public-search-index-v3", "normalization": normalization_metadata(),
                "citation_profile": "tr-literal-citations-v1", "fusion": "rrf-k60-v1"}
    queries = []
    for position, (practice, query) in enumerate(zip(("contracts", "commercial", "employment"),
            ("sentetik sozlesme", "E. 2099/0012", "SENTETİK karşı görüş"), strict=True)):
        queries.append({"id": f"synthetic-{position}", "query": query,
            "family_sha256": digest({"invented_family": position}), "practice": practice, "period": "unknown",
            "slices": ["citation"] if position == 1 else ["adverse"], "as_of": "2011-01-01",
            "corpus_coverage": "covered", "judgments": [
                {"authority_id": f"urn:test:positive:{position}", "relevance": 3, "adverse": False},
                {"authority_id": f"urn:test:adverse:{position}", "relevance": 2, "adverse": True},
                {"authority_id": "urn:test:irrelevant", "relevance": 0, "adverse": False}],
            "exact_target": f"urn:test:positive:{position}" if position == 1 else None})
    benchmark = RetrievalBenchmark.model_validate({"schema_version": "retrieval-development-benchmark-v1",
        "dataset_id": "invented-development-example", "purpose": "development", "origin": "synthetic",
        "adjudication_status": "pending", "adjudication_evidence_sha256": None, "snapshot": snapshot, "queries": queries})
    observations = []
    for position, query in enumerate(queries):
        for profile in ("lexical", "turkish", "all"):
            ranked = ["urn:test:irrelevant", f"urn:test:positive:{position}"] if profile == "lexical" else [
                f"urn:test:positive:{position}", f"urn:test:adverse:{position}"]
            observations.append({"query_id": query["id"], "profile": profile, "status": "available",
                "authority_ids": ranked, "returned_passages": len(ranked), "rejected_hits": 0, "elapsed_seconds": 1.0})
    run = RetrievalRun.model_validate({"schema_version": "retrieval-development-run-v1",
        "benchmark_sha256": digest(benchmark.model_dump(mode="json")), "snapshot": snapshot, "observations": observations})
    return benchmark, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    benchmark, run = fixture_inputs()
    for name, model in (("benchmark", benchmark), ("run", run)):
        (args.output / f"{name}.json").write_text(json.dumps(model.model_dump(mode="json"), indent=2,
            ensure_ascii=False, allow_nan=False) + "\n")
    print("Invented benchmark and rankings written; retrieval was not executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
