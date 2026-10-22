"""Grade only the frozen invented suite; expected groups never enter planners."""

import argparse
import json
from collections import Counter
from pathlib import Path

from budgeted_quote_bundles import plan_bundles, sha
from diverse_quote_bundles import plan_diverse, resolve_diverse
from source_diversity_cases import CASES, SUITE, SUITE_SHA256, originals_for

from app.evidence_prompt import canonical


def grade(case, sources, plan):
    versions = {p["id"]: (p["document_id"], p["document_revision"]) for p in sources}
    groups = []
    for key, revision, side, texts in case["groups"]:
        expected = (case["id"] + "-doc-" + key, revision)
        present = any(all(any(versions[p["evidence_id"]] == expected and text in p["text"] for p in b["parts"])
                          for text in texts) for b in plan["bundles"])
        groups.append({"document_id": expected[0], "document_revision": revision, "side": side, "available_in_one_bundle": present})
    for b in plan["bundles"]:
        for part in b["parts"]:
            original = next(p for p in sources if p["id"] == part["evidence_id"])
            assert part["text"] == original["text"][part["original_start"]:part["original_end"]]
            assert part["text_sha256"] == sha(part["text"])
    return {"recipe": plan["recipe"], "plan_sha256": plan["plan_sha256"], "groups": groups,
        "all_groups_available": bool(groups) and all(g["available_in_one_bundle"] for g in groups),
        "measurement": plan["measurement"], "selected_bundles": len(plan["bundles"]),
        "selected_source_versions": len({versions[p["evidence_id"]] for b in plan["bundles"] for p in b["parts"]}),
        "unmatched_fallback_bundles": sum(b.get("nomination") == "unmatched_source_fallback" for b in plan["bundles"]),
        "omission_counts": dict(sorted(Counter(o["reason"] for o in plan["omitted_candidates"]).items())),
        "boundary_flags": sorted({f for b in plan["bundles"] for f in b["boundary_flags"]}),
        "source_spans_versions_and_originals_exact": True, "model_relevance_or_legal_quality_measured": False}


def evaluate():
    report = {"schema": "offline-source-diversity-evaluation-v1", "suite": SUITE, "suite_sha256": SUITE_SHA256,
        "inference_calls": 0, "http_calls": 0, "private_documents": 0, "review_decisions": 0,
        "production_changes": 0, "native_or_legal_qualification": False, "cases": []}
    for case in CASES:
        sources = originals_for(case)
        before = canonical(sources)
        limit = case.get("context_limit", 8192)
        prior = plan_bundles(case["question"], sources, context_limit=limit)
        candidate = plan_diverse(case["question"], sources, context_limit=limit)
        if candidate["measurement"]["within_budget"]:
            resolved = resolve_diverse([b["id"] for b in candidate["bundles"]], candidate, case["question"], sources, context_limit=limit)
            assert len(resolved) == len(candidate["bundles"])
        assert before == canonical(sources)
        report["cases"].append({"case": case["id"], "kind": case["kind"], "context_limit_units": limit,
            "source_inventory_sha256": sha(before), "source_pins": candidate["source_pins"],
            "unrepresented_source_versions": candidate["unrepresented_source_versions"],
            "unrepresented_evidence_ids": candidate["unrepresented_evidence_ids"], "candidate_inventory": candidate["inventory"],
            "v1": grade(case, sources, prior), "v2": grade(case, sources, candidate)})
    summary = {"cases": len(CASES), "expected_groups": sum(len(c["groups"]) for c in CASES)}
    for recipe in ("v1", "v2"):
        rows = report["cases"]
        adverse = [c for c in rows if any(g["side"] == "adverse" for g in c[recipe]["groups"])]
        alternate = [c for c in rows if c["kind"] in {"alternate_wording", "late_paraphrase"}]
        summary[recipe] = {"available_groups": sum(g["available_in_one_bundle"] for c in rows for g in c[recipe]["groups"]),
            "alternate_wording_cases": len(alternate), "alternate_all_groups_available": sum(c[recipe]["all_groups_available"] for c in alternate),
            "adverse_source_cases": len(adverse), "both_sides_available": sum(c[recipe]["all_groups_available"] for c in adverse),
            "prompts_within_budget": sum(c[recipe]["measurement"]["within_budget"] for c in rows),
            "blocked_envelopes": sum(not c[recipe]["measurement"]["within_budget"] for c in rows),
            "unmatched_fallback_bundles": sum(c[recipe]["unmatched_fallback_bundles"] for c in rows)}
    report["summary"] = summary
    report["conclusion"] = "offline_candidate_comparison_only_not_semantic_native_or_legal_qualification"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = evaluate()
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"summary": report["summary"], "inference_calls": 0, "http_calls": 0}))


if __name__ == "__main__":
    main()
