"""Disposable synthetic bridge only; not a durable native inference executor.

Fresh mock-only sessions intentionally reset their local ledgers, while a separate
protected store rejects replay and retains totals across reopens. No matter data,
credentials, native model, production store or external permission is used.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from bundle_adapter_fixture import ControlledExchange, settings
from disposable_packet_selector import MARKER, Allowance, DisposablePacketSelector
from durable_campaign_cases import CASES, SUITE_SHA256, originals_for
from durable_packet_campaign import RECIPE, CampaignLedger, prepare_grant
from offline_quotation_boundaries import sha
from whole_passage_packets import plan_packets

from app.evidence_prompt import canonical
from app.provider import Provider


def fixture(case, n):
    sources = originals_for(case)
    plan = plan_packets(case["question"], sources)
    b = plan["aggregate_budget"]
    allowance = Allowance(len(plan["packets"]), b["planned_upper_bound_units"], b["planned_copied_text_utf8_bytes"])
    grant = prepare_grant("00000000-0000-4000-8000-" + str(n).zfill(12), case["question"], sources, plan, allowance)
    return sources, plan, allowance, grant


def approve_fixture(_grant, _action):
    return True  # Invented fixtures only. Never wire this into private-matter/native workflows.


def evaluate():
    rows = []
    for n, case in enumerate(CASES, 1):
        sources, plan, allowance, grant = fixture(case, n)
        with TemporaryDirectory() as tmp, ControlledExchange() as exchange:
            path = Path(tmp).resolve() / "synthetic.sqlite"
            ledger = CampaignLedger.create(path)
            store_id = ledger.store_id
            ledger.admit(grant, authorize=approve_fixture)
            results = []
            for packet in plan["packets"]:
                ledger = CampaignLedger(path, expected_store_id=store_id)
                session = DisposablePacketSelector(Provider(settings()), case["question"], sources, plan, allowance,
                                                   authorize=lambda _: True, mode=MARKER)
                reserved = ledger.reserve(grant, packet["id"], authorize=approve_fixture)
                assert reserved["selector_context_sha256"] == session.receipt()["context_sha256"]
                result = session.select(packet["id"])
                ledger.settle(grant, packet["id"], outcome="returned_unqualified", result_sha256=sha(canonical(result)), authorize=approve_fixture)
                results.append(result)
            rejected = 0
            if plan["packets"]:
                ledger = CampaignLedger(path, expected_store_id=store_id)
                try:
                    ledger.reserve(grant, "P1", authorize=approve_fixture)
                except ValueError:
                    rejected = 1
                assert rejected == 1
            receipt = ledger.receipt(grant, authorize=approve_fixture)
            expected = {p["id"]: p["text"] for p in sources}
            rows.append({"case": case["id"], "recreated_sessions": len(results), "duplicate_reservations_rejected": rejected,
                "exact_copies": all(part["text"] == expected[part["evidence_id"]] for r in results for b in r["bundles"] for part in b["parts"]),
                "receipt": receipt, **exchange.counts()})
    return {"recipe": RECIPE, "suite_sha256": SUITE_SHA256, "cases": rows,
        "summary": {"cases": len(rows), "recreated_sessions": sum(r["recreated_sessions"] for r in rows),
            "mock_completion_requests": sum(r["mock_completion_requests"] for r in rows),
            "mock_metadata_requests": sum(r["mock_metadata_requests"] for r in rows),
            "duplicate_reservations_rejected": sum(r["duplicate_reservations_rejected"] for r in rows),
            "no_candidate_cases": sum(r["recreated_sessions"] == 0 for r in rows), "all_copies_exact": all(r["exact_copies"] for r in rows)},
        "network_http_calls": 0, "native_inference_calls": 0, "private_documents": 0,
        "production_activation": False, "native_or_legal_or_capacity_qualification": False}


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2, ensure_ascii=False))
