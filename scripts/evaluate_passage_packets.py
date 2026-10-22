"""Fresh frozen offline availability comparison, never model accuracy or law."""

import argparse
import json
from collections import Counter
from pathlib import Path

from diverse_quote_bundles import plan_diverse
from offline_quotation_boundaries import sha
from passage_packet_cases import CASES, SUITE, SUITE_SHA256, originals_for
from whole_passage_packets import plan_packets, resolve_packet

from app.evidence_prompt import canonical


def groups_for(case, sources, bundles):
    by_id = {p["id"]: p for p in sources}
    result = []
    for key, revision, side, texts in case["groups"]:
        expected = case["id"] + "-doc-" + key
        available = any(all(any(by_id[part["evidence_id"]]["document_id"] == expected
                                and by_id[part["evidence_id"]]["document_revision"] == revision and text in part["text"]
                                for part in b["parts"]) for text in texts) for b in bundles)
        result.append({"document_id": expected, "document_revision": revision, "side": side,
                       "available_in_one_atomic_bundle": available})
    return result


def describe(case, sources, plan):
    for packet in plan["packets"]:
        result = resolve_packet(packet["id"], [b["id"] for b in packet["bundles"]], plan, case["question"], sources,
                                context_limit=case.get("context_limit", 8192), max_packets=plan["limits"]["max_packets"])
        assert result["bundles"] == packet["bundles"]
        for b in result["bundles"]:
            source = next(p for p in sources if p["id"] == b["parts"][0]["evidence_id"])
            assert b["parts"][0]["text"] == source["text"]
            assert b["parts"][0]["text_sha256"] == sha(source["text"])
    bundles = [b for p in plan["packets"] for b in p["bundles"]]
    return {"plan_sha256": plan["plan_sha256"], "inventory": plan["inventory"], "groups": groups_for(case, sources, bundles),
            "aggregate_budget": plan["aggregate_budget"], "admission": plan["admission"],
            "packets": [{"id": p["id"], "measurement": p["measurement"],
                         "bundle_ids": [b["id"] for b in p["bundles"]]} for p in plan["packets"]],
            "omission_counts": dict(sorted(Counter(p["reason"] for p in plan["omitted_passages"]).items())),
            "unrepresented_evidence_ids": plan["unrepresented_evidence_ids"],
            "unrepresented_source_versions": plan["unrepresented_source_versions"],
            "all_available_parts_copy_exact_original_passages": True}


def evaluate():
    rows = []
    for case in CASES:
        sources = originals_for(case)
        sealed = canonical(sources)
        limit = case.get("context_limit", 8192)
        prior = plan_diverse(case["question"], sources, context_limit=limit)
        single = plan_packets(case["question"], sources, context_limit=limit, max_packets=1)
        multiple = plan_packets(case["question"], sources, context_limit=limit)
        assert not single["packets"] or single["packets"][0] == multiple["packets"][0]
        assert canonical(sources) == sealed
        rows.append({"case": case["id"], "kind": case["kind"], "source_inventory_sha256": sha(sealed),
                     "source_pins": multiple["source_pins"], "source_passages": len(sources),
                     "source_versions": multiple["inventory"]["source_versions"],
                     "expected_empty_selection": case.get("expect_empty", False), "abstention_accuracy": "not_measured",
                     "frozen_v2_single_envelope": {"plan_sha256": prior["plan_sha256"],
                         "groups": groups_for(case, sources, prior["bundles"]), "measurement": prior["measurement"],
                         "unmatched_fallback_bundles": sum(b["nomination"] == "unmatched_source_fallback" for b in prior["bundles"])},
                     "whole_single": describe(case, sources, single), "whole_multi": describe(case, sources, multiple),
                     "originals_unchanged": True})
    summary = {"cases": len(rows), "source_passages": sum(r["source_passages"] for r in rows),
               "source_versions": sum(r["source_versions"] for r in rows), "expected_groups": sum(len(c["groups"]) for c in CASES),
               "explicit_empty_cases": sum(c.get("expect_empty", False) for c in CASES)}
    for key in ("frozen_v2_single_envelope", "whole_single", "whole_multi"):
        groups = [g for r in rows for g in r[key]["groups"]]
        values = {"available_groups": sum(g["available_in_one_atomic_bundle"] for g in groups),
                  "unavailable_groups": sum(not g["available_in_one_atomic_bundle"] for g in groups)}
        if key != "frozen_v2_single_envelope":
            values.update(planned_envelopes=sum(r[key]["inventory"]["packets"] for r in rows),
                          planned_upper_bound_units=sum(r[key]["aggregate_budget"]["planned_upper_bound_units"] for r in rows),
                          copied_text_utf8_bytes=sum(r[key]["aggregate_budget"]["planned_copied_text_utf8_bytes"] for r in rows),
                          blocked_envelopes=sum(r[key]["admission"]["state"] == "blocked_envelope" for r in rows),
                          no_candidates=sum(r[key]["admission"]["state"] == "no_candidates_no_call" for r in rows))
        summary[key] = values
    return {"schema": "offline-whole-passage-packet-evaluation-v1", "suite": SUITE, "suite_sha256": SUITE_SHA256,
            "summary": summary, "cases": rows, "counts": {"model_calls": 0, "http_calls": 0, "private_documents": 0,
                "production_changes": 0, "review_decisions": 0},
            "comparison_scope": "whole_single_vs_whole_multi_changes_packet_capacity_only_first_packet_identical",
            "v2_comparison_limit": "whole_passage_nomination_and_aggregate_cost_also_change_no_causal_accuracy_claim",
            "selection_relevance_abstention_native_capacity_and_legal_qualification": False,
            "conclusion": "offline_candidate_availability_only_not_native_acceptance_or_production_activation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate()
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"summary": report["summary"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
