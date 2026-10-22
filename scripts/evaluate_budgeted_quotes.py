"""Fixed synthetic-only offline comparison; no provider/private input option."""

import argparse
import json
from collections import Counter
from pathlib import Path

from budgeted_quote_bundles import plan_bundles, sha
from budgeted_quote_cases import CASES, SUITE, suite_sha256
from evaluate_quotation_boundaries import availability, fixture

from app.context_packing import pack_private_context
from app.evidence_prompt import canonical, quote_catalog


def evaluate():
    report = {"schema": "offline-budgeted-quote-evaluation-v1", "suite": SUITE, "suite_sha256": suite_sha256(),
        "inference_calls": 0, "http_calls": 0, "private_documents": 0, "review_decisions": 0, "production_changes": 0,
        "native_or_legal_qualification": False, "cases": []}
    for case in CASES:
        originals, original_hash = fixture(case)
        sealed = canonical(originals)
        limit = case.get("context_limit", 8192)
        plan = plan_bundles(case["question"], originals, context_limit=limit)
        pack = pack_private_context(case["question"], originals, context_limit=limit, candidate_profile=True)
        baseline = availability(case["groups"], quote_catalog(pack["evidence"]))
        covered = [any(all(any(text in part["text"] for part in bundle["parts"]) for text in group)
                       for bundle in plan["bundles"]) for group in case["groups"]]
        for bundle in plan["bundles"]:
            for part in bundle["parts"]:
                original = next(p for p in originals if p["id"] == part["evidence_id"])
                assert part["text"] == original["text"][part["original_start"]:part["original_end"]]
                assert part["text_sha256"] == sha(part["text"])
        assert canonical(originals) == sealed
        report["cases"].append({"case": case["id"], "format": "text_pdf" if case.get("pdf") else "exact_text_fixture",
            "context_limit_units": limit, "original_bytes_sha256": original_hash, "source_inventory_sha256": sha(sealed),
            "source_pins": plan["source_pins"], "initial_pack_inventory": plan["initial_pack"]["inventory"],
            "initial_pack_sha256": sha(canonical(plan["initial_pack"])), "plan_sha256": plan["plan_sha256"],
            "baseline_single_quote_groups": baseline, "bundle_group_availability": covered,
            "expected_groups": len(covered), "available_groups": sum(covered), "measurement": plan["measurement"],
            "selected_bundles": len(plan["bundles"]), "proposed_bundles": plan["proposed_bundles"],
            "selected_parts": sum(len(b["parts"]) for b in plan["bundles"]),
            "fallback_bundles": sum(b["fallback"] is not None for b in plan["bundles"]),
            "boundary_flags": sorted({f for b in plan["bundles"] for f in b["boundary_flags"]}),
            "omission_counts": dict(sorted(Counter(o["reason"] for o in plan["omitted_candidates"]).items())),
            "unused_initial_evidence_ids": plan["unused_initial_evidence_ids"], "nomination_inventory": plan["nomination_inventory"],
            "source_spans_versions_and_originals_exact": True,
            "model_relevance_abstention_instruction_resistance_or_legal_correctness_measured": False})
    report["summary"] = {"cases": len(CASES), "expected_groups": sum(c["expected_groups"] for c in report["cases"]),
        "available_bundle_groups": sum(c["available_groups"] for c in report["cases"]),
        "planned_prompts_within_declared_budget": sum(c["measurement"]["within_budget"] for c in report["cases"]),
        "blocked_envelopes": sum(not c["measurement"]["within_budget"] for c in report["cases"]),
        "fallback_bundles": sum(c["fallback_bundles"] for c in report["cases"])}
    report["conclusion"] = "offline_bundle_contract_only_not_production_qualified"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = evaluate()
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"suite": SUITE, "summary": report["summary"], "inference_calls": 0, "conclusion": report["conclusion"]}))


if __name__ == "__main__":
    main()
