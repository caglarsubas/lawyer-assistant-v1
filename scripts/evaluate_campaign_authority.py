"""Mock-only boundary bridge; no live identity collector or native executor."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from bundle_adapter_fixture import ControlledExchange, settings
from campaign_authority import RECIPE, CampaignAuthority
from campaign_authority_cases import CASES, SUITE_SHA256, runtime_pin
from disposable_packet_selector import MARKER, DisposablePacketSelector
from durable_packet_campaign import CampaignLedger
from evaluate_durable_campaign import approve_fixture, fixture
from offline_quotation_boundaries import sha

from app.evidence_prompt import canonical
from app.provider import Provider


def evaluate():
    rows = []
    for n, case in enumerate(CASES, 1):
        sources, plan, allowance, grant = fixture(case, n)
        pin = runtime_pin()
        with TemporaryDirectory() as tmp, ControlledExchange() as exchange:
            root = Path(tmp).resolve()
            ledger, authority = CampaignLedger.create(root / "campaign.sqlite"), CampaignAuthority.create(root / "authority.sqlite")
            ledger.admit(grant, authorize=approve_fixture)
            spec = authority.register("10000000-0000-4000-8000-" + str(n).zfill(12), ledger, grant, pin,
                                      authorize=approve_fixture, observe=lambda: pin)
            results = []
            for packet in plan["packets"]:
                authority = CampaignAuthority(authority._store.path, expected_authority_id=authority.authority_id)
                ledger = CampaignLedger(ledger.path, expected_store_id=ledger.store_id)
                session = DisposablePacketSelector(Provider(settings()), case["question"], sources, plan, allowance,
                                                   authorize=lambda _: True, mode=MARKER)
                reserved = authority.reserve(ledger, spec, packet["id"], authorize=approve_fixture, observe=lambda: pin)
                assert reserved["selector_context_sha256"] == session.receipt()["context_sha256"]
                result = session.select(packet["id"])
                authority.settle(ledger, spec, packet["id"], outcome="returned_unqualified", result_sha256=sha(canonical(result)),
                                 authorize=approve_fixture, observe=lambda: pin)
                results.append(result)
            receipt = authority.receipt(spec, authorize=approve_fixture)
            exact = all(part["text"] == next(s["text"] for s in sources if s["id"] == part["evidence_id"])
                        for r in results for b in r["bundles"] for part in b["parts"])
            rows.append({"case": case["id"], "packets": len(results), "exact_copies": exact,
                         "authority_receipt": receipt, **exchange.counts()})
    return {"recipe": RECIPE, "suite_sha256": SUITE_SHA256, "cases": rows,
        "summary": {"cases": len(rows), "mock_metadata_requests": sum(r["mock_metadata_requests"] for r in rows),
            "mock_completion_requests": sum(r["mock_completion_requests"] for r in rows),
            "no_candidate_cases": sum(r["packets"] == 0 for r in rows), "all_copies_exact": all(r["exact_copies"] for r in rows)},
        "network_http_calls": 0, "native_inference_calls": 0, "private_documents": 0,
        "production_activation": False, "live_identity_or_native_legal_capacity_qualification": False}


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2, ensure_ascii=False))
