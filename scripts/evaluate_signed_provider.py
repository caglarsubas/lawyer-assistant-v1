"""Frozen offline producer/relay/consumer outcomes; no sockets or native inference."""

import json

from signed_provider_cases import CASES, SUITE_CANONICAL
from signed_provider_contract import sha
from signed_provider_fixture import SENTINEL, Fixture


def evaluate():
    rows = []
    for case, mode, expected in CASES:
        fixture = Fixture(mode)
        try:
            proof = fixture.identity()
        except ValueError:
            outcome = "handoff_rejected" if mode == "duplicate_challenge" else "identity_rejected"
        else:
            try:
                fixture.bind(proof)
                outcome = "bound"
            except ValueError:
                outcome = "response_rejected"
        rows.append({"case": case, "expected": expected, "outcome": outcome})
    result = {
        "suite_sha256": sha(SUITE_CANONICAL.encode()),
        "cases": rows,
        "summary": {
            "cases": len(rows),
            "expected_results": sum(r["expected"] == r["outcome"] for r in rows),
            "bound_synthetic_responses": sum(r["outcome"] == "bound" for r in rows),
        },
        "real_network_calls": 0,
        "native_inference_calls": 0,
        "private_documents": 0,
        "persisted_or_provisioned_keys": 0,
        "live_identity_qualified": False,
        "production_activation": False,
    }
    assert SENTINEL not in json.dumps(result)
    return result


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
