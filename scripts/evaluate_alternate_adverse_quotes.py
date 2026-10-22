"""Fixed synthetic source nomination evaluation; no model/HTTP/private input."""

import argparse
import json
from pathlib import Path

from alternate_adverse_quote_cases import CASES, SUITE, SUITE_SHA256, originals_for
from budgeted_quote_bundles import plan_bundles, resolve_bundles, sha
from disposable_bundle_adapter import messages_for_plan

from app.evidence_prompt import canonical


def evaluate():
    report = {"schema": "alternate-adverse-bundles-evaluation-v1", "suite": SUITE, "suite_sha256": SUITE_SHA256,
              "inference_calls": 0, "http_calls": 0, "private_documents": 0, "review_decisions": 0,
              "production_changes": 0, "native_or_legal_qualification": False, "cases": []}
    for case in CASES:
        sources = originals_for(case)
        sealed = canonical(sources)
        limit = case.get("context_limit", 8192)
        plan = plan_bundles(case["question"], sources, context_limit=limit)
        messages = messages_for_plan(case["question"], sources, plan, limit)
        groups = []
        for key, side, texts in case["groups"]:
            ident = case["id"] + "-" + key
            available = any(all(any(p["evidence_id"] == ident and text in p["text"] for p in b["parts"])
                                for text in texts) for b in plan["bundles"])
            groups.append({"source_id": ident, "side": side, "available_in_one_bundle": available})
        resolved = resolve_bundles([b["id"] for b in plan["bundles"]], plan, case["question"], sources, context_limit=limit)
        for b in resolved:
            for p in b["parts"]:
                original = next(s for s in sources if s["id"] == p["evidence_id"])
                assert p["text"] == original["text"][p["original_start"]:p["original_end"]]
                assert sha(p["text"]) == p["text_sha256"]
        assert canonical(sources) == sealed
        report["cases"].append({"case": case["id"], "kind": case["kind"], "source_inventory_sha256": sha(sealed),
            "source_pins": plan["source_pins"], "plan_sha256": plan["plan_sha256"],
            "measurement": plan["measurement"], "adapter_messages_sha256": sha(canonical(messages)), "groups": groups,
            "bundles": len(plan["bundles"]), "omissions": plan["omitted_candidates"],
            "unused_initial_evidence_ids": plan["unused_initial_evidence_ids"],
            "all_declared_groups_available": bool(groups) and all(g["available_in_one_bundle"] for g in groups),
            "source_versions_spans_and_originals_exact": True, "selection_quality_measured": False})
    groups = [g for c in report["cases"] for g in c["groups"]]
    adverse = [c for c in report["cases"] if any(g["side"] == "adverse" for g in c["groups"])]
    report["summary"] = {"cases": len(CASES), "expected_groups": len(groups),
        "available_groups": sum(g["available_in_one_bundle"] for g in groups),
        "alternate_wording_cases": sum(c["kind"] == "alternate_wording" for c in report["cases"]),
        "alternate_wording_all_groups_available": sum(c["kind"] == "alternate_wording" and c["all_declared_groups_available"]
                                                    for c in report["cases"]),
        "adverse_source_cases": len(adverse), "both_sides_available_cases": sum(c["all_declared_groups_available"] for c in adverse),
        "within_budget": sum(c["measurement"]["within_budget"] for c in report["cases"])}
    report["conclusion"] = "offline_nomination_and_adapter_envelope_only_not_native_or_legal_qualification"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = evaluate()
    with args.output.open("x") as f:
        f.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"summary": report["summary"], "inference_calls": 0, "http_calls": 0}))


if __name__ == "__main__":
    main()
