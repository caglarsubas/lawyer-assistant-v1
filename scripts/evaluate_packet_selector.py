"""Mock protocol evaluation only; no sockets, native inference or quality grading."""

import json

from bundle_adapter_fixture import ControlledExchange, settings
from disposable_packet_selector import MARKER, Allowance, DisposablePacketSelector
from packet_selector_cases import CASES, SUITE_SHA256, originals_for
from whole_passage_packets import plan_packets

from app.provider import Provider


def evaluate():
    rows = []
    for case in CASES:
        sources = originals_for(case)
        plan = plan_packets(case["question"], sources)
        budget = plan["aggregate_budget"]
        allowance = Allowance(len(plan["packets"]), budget["planned_upper_bound_units"], budget["planned_copied_text_utf8_bytes"])
        with ControlledExchange() as exchange:
            session = DisposablePacketSelector(Provider(settings()), case["question"], sources, plan, allowance,
                                               authorize=lambda _: True, mode=MARKER)
            results = [session.select(p["id"]) for p in plan["packets"]]
            expected = {p["id"]: p["text"] for p in sources}
            exact = all(part["text"] == expected[part["evidence_id"]] for r in results for b in r["bundles"] for part in b["parts"])
            rows.append({"case": case["id"], "source_passages": len(sources), "packets": len(results),
                "selected_passages": sum(len(r["bundles"]) for r in results), "exact_copies": exact,
                "unrepresented_evidence_ids": plan["unrepresented_evidence_ids"], "receipt": session.receipt(), **exchange.counts()})
    return {"recipe": MARKER, "suite_sha256": SUITE_SHA256, "cases": rows,
            "summary": {"cases": len(rows), "packets": sum(r["packets"] for r in rows),
                "mock_metadata_requests": sum(r["mock_metadata_requests"] for r in rows),
                "mock_completion_requests": sum(r["mock_completion_requests"] for r in rows),
                "no_candidate_cases": sum(r["packets"] == 0 for r in rows), "all_copies_exact": all(r["exact_copies"] for r in rows)},
            "network_http_calls": 0, "native_inference_calls": 0, "private_documents": 0,
            "production_activation": False, "native_relevance_abstention_legal_or_capacity_qualification": False}


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2, ensure_ascii=False))
