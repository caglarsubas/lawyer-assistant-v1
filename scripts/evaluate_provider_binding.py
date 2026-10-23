"""Frozen prospective protocol evaluation; no sockets or native generation."""

import json

from provider_binding_cases import CASES, SUITE_CANONICAL
from provider_binding_fixture import SignedFixture
from provider_identity_binding import sha


def evaluate():
    rows = []
    for case in CASES:
        fixture = SignedFixture(case["mode"])
        record = fixture.collect()
        if record["qualified_pin"] is None:
            outcome = "identity_unqualified"
        else:
            pending = fixture.pending(record)
            try:
                pending.consume(fixture.response(pending), now=1800000001)
                outcome = "bound"
            except ValueError:
                outcome = "binding_rejected"
        rows.append({"case": case["id"], "outcome": outcome, "expected": case["expected"], "GET_requests": len(fixture.requests),
                     "POST_requests": sum(r.method == "POST" for r in fixture.requests)})
    return {"suite_sha256": sha(SUITE_CANONICAL), "cases": rows,
        "summary": {"cases": len(rows), "expected_outcomes": sum(r["outcome"] == r["expected"] for r in rows),
            "bound_synthetic_responses": sum(r["outcome"] == "bound" for r in rows),
            "rejected_synthetic_responses": sum(r["outcome"] == "binding_rejected" for r in rows),
            "unqualified_identities": sum(r["outcome"] == "identity_unqualified" for r in rows),
            "mock_GET_requests": sum(r["GET_requests"] for r in rows), "mock_POST_requests": sum(r["POST_requests"] for r in rows)},
        "real_network_calls": 0, "native_inference_calls": 0, "private_documents": 0,
        "production_activation": False, "live_identity_or_legal_capacity_qualification": False}


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
