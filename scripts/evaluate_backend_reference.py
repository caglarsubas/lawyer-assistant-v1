"""Offline frozen metadata inspection evaluation, never live service collection."""

import json

from backend_reference_cases import CASES, SUITE_CANONICAL
from backend_reference_fixture import Fixture
from backend_reference_inspection import sha


def evaluate():
    rows = []
    for case, mode, classification, requests in CASES:
        report, _ = Fixture(mode).run()
        rows.append(
            {
                "case": case,
                "expected": [classification, requests],
                "actual": [report["classification"], len(report["metadata_requests"])],
            }
        )
    return {
        "suite_sha256": sha(SUITE_CANONICAL.encode()),
        "cases": rows,
        "summary": {
            "cases": len(rows),
            "expected_results": sum(v["expected"] == v["actual"] for v in rows),
        },
        "real_network_calls": 0,
        "native_inference_calls": 0,
        "native_execution_compatibility": "not_tested",
        "production_activation": False,
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
