"""Exercise fixed invented bundle cases over mock HTTP, never native inference."""

from alternate_adverse_quote_cases import CASES, SUITE_SHA256, originals_for
from budgeted_quote_bundles import plan_bundles, sha
from bundle_adapter_fixture import ControlledExchange

from app.evidence_prompt import canonical


def evaluate():
    rows = []
    with ControlledExchange() as exchange:
        for case in CASES:
            sources = originals_for(case)
            sealed = canonical(sources)
            limit = case.get("context_limit", 8192)
            plan = plan_bundles(case["question"], sources, context_limit=limit)
            result = exchange.adapter(provider_context_limit=limit).select(case["question"], sources, plan, context_limit=limit)
            assert canonical(sources) == sealed
            assert len(result["bundles"]) == len(plan["bundles"])
            rows.append({"case": case["id"], "plan_sha256": plan["plan_sha256"], "result_sha256": sha(canonical(result)),
                "state": result["state"], "all_nominated_bundles_copied": True,
                "source_inventory_unchanged": True, "selection_policy": "controlled_select_all_not_a_model"})
        return {"schema": "disposable-bundle-adapter-mock-evaluation-v1", "suite_sha256": SUITE_SHA256,
                "cases": rows, "counts": exchange.counts(), "production_changes": 0, "private_documents": 0,
                "review_decisions": 0, "native_or_legal_qualification": False}
