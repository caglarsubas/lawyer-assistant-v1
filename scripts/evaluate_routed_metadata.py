"""Frozen offline diagnostic stage comparison, never live qualification."""
import hashlib
import json

from routed_metadata_cases import CASES, SUITE_CANONICAL
from routed_metadata_fixture import SENTINEL, Fixture


def evaluate():
    rows = []
    for case, mode, expected in CASES:
        fixture = Fixture(mode)
        result = fixture.run()
        assert SENTINEL not in json.dumps(result)
        rows.append({"case": case, "expected_stage": expected, "diagnostic": result,
                     "mock_GET_requests": sum(r.method == "GET" for r in fixture.requests),
                     "mock_POST_requests": sum(r.method == "POST" for r in fixture.requests)})
    return {"suite_sha256": hashlib.sha256(SUITE_CANONICAL.encode()).hexdigest(), "cases": rows,
            "summary": {"cases": len(rows), "expected_stages": sum(r["expected_stage"] == r["diagnostic"]["stage"] for r in rows),
                        "mock_GET_requests": sum(r["mock_GET_requests"] for r in rows),
                        "mock_POST_requests": sum(r["mock_POST_requests"] for r in rows),
                        "qualified_identities": sum(r["diagnostic"]["qualified_identity"] for r in rows)},
            "real_network_calls": 0, "native_inference_calls": 0, "private_documents": 0,
            "production_activation": False, "ultimate_network_or_legal_cause_established": False}


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
