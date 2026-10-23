"""Offline phase comparison only; never deployed capacity, identity or legal qualification."""
import hashlib
import json

from metadata_phase_cases import CASES, SUITE_CANONICAL
from metadata_phase_fixture import SENTINEL, Fixture


def evaluate():
    rows = []
    for case, mode, phase, outcome in CASES:
        fixture = Fixture(mode)
        result = fixture.run()
        assert SENTINEL not in json.dumps(result)
        rows.append({"case": case, "expected_phase": phase, "expected_outcome": outcome, "diagnostic": result})
    return {"suite_sha256": hashlib.sha256(SUITE_CANONICAL.encode()).hexdigest(), "cases": rows,
            "summary": {"cases": len(rows), "expected_results": sum(r["diagnostic"]["last_phase"] == r["expected_phase"] and r["diagnostic"]["outcome"] == r["expected_outcome"] for r in rows),
                        "mock_connections": sum(r["diagnostic"]["connection_attempts"] for r in rows),
                        "mock_GET_attempts": sum(r["diagnostic"]["metadata_GET_attempts"] for r in rows),
                        "mock_POST_requests": 0, "qualified_identities": 0},
            "real_network_calls": 0, "native_inference_calls": 0, "private_documents": 0,
            "production_activation": False, "historical_timeout_cause_established": False}


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
