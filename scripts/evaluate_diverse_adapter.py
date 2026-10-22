"""Fresh fixed synthetic adapter/coverage evaluation over in-process mock HTTP."""

import argparse
import json
from pathlib import Path

from bundle_adapter_fixture import ControlledExchange, settings
from disposable_diverse_adapter import MARKER, DisposableDiverseAdapter, prepare_diverse_selection
from diverse_adapter_cases import CASES, SUITE, SUITE_SHA256, originals_for
from diverse_quote_bundles import plan_diverse, sha
from evaluate_source_diversity import grade

from app.evidence_prompt import canonical
from app.provider import Provider


def evaluate():
    rows = []
    with ControlledExchange() as exchange:
        for case in CASES:
            sources = originals_for(case)
            before = canonical(sources)
            limit = case.get("context_limit", 8192)
            plan = plan_diverse(case["question"], sources, context_limit=limit)
            wire = prepare_diverse_selection(case["question"], sources, plan, context_limit=limit)
            if wire["measurement"]["within_budget"]:
                adapter = DisposableDiverseAdapter(Provider(settings(provider_context_limit=limit)), mode=MARKER)
                result = adapter.select(case["question"], sources, plan, wire, context_limit=limit)
                assert len(result["bundles"]) == len(plan["bundles"])
                selection = {"state": result["state"], "result_sha256": sha(canonical(result)),
                    "all_nominated_bundles_copied": True, "selection_policy": "controlled_select_all_not_a_model"}
            else:
                selection = {"state": "blocked_before_transport", "selection_policy": "no_call"}
            assert before == canonical(sources)
            rows.append({"case": case["id"], "kind": case["kind"], "source_inventory_sha256": sha(before),
                "source_pins": plan["source_pins"], "inventory": plan["inventory"],
                "unrepresented_source_versions": plan["unrepresented_source_versions"],
                "unrepresented_evidence_ids": plan["unrepresented_evidence_ids"], "wire": wire, "selection": selection,
                "coverage": grade(case, sources, plan), "originals_unchanged": True})
        groups = [g for row in rows for g in row["coverage"]["groups"]]
        adverse = [row for row in rows if any(g["side"] == "adverse" for g in row["coverage"]["groups"])]
        summary = {"cases": len(rows), "source_passages": sum(row["inventory"]["source_passages"] for row in rows),
            "source_versions": sum(row["inventory"]["source_versions"] for row in rows), "expected_groups": len(groups),
            "available_groups": sum(g["available_in_one_bundle"] for g in groups), "adverse_source_cases": len(adverse),
            "both_sides_available": sum(row["coverage"]["all_groups_available"] for row in adverse),
            "blocked_before_transport": sum(row["selection"]["state"] == "blocked_before_transport" for row in rows),
            "no_candidates_no_call": sum(row["selection"]["state"] == "no_candidates_no_call" for row in rows),
            "unmatched_fallback_bundles": sum(row["coverage"]["unmatched_fallback_bundles"] for row in rows)}
        return {"schema": "disposable-diverse-adapter-evaluation-v1", "suite": SUITE, "suite_sha256": SUITE_SHA256,
                "cases": rows, "summary": summary, "counts": exchange.counts(), "private_documents": 0,
                "production_changes": 0, "review_decisions": 0, "native_or_legal_qualification": False,
                "conclusion": "frozen_synthetic_coverage_and_mock_wire_only_not_native_or_legal_qualification"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = evaluate()
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"summary": report["summary"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
