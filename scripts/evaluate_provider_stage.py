"""Offline staged interface/receipt evaluation, no real provider/model execution."""

import json
import tempfile
from pathlib import Path

from provider_stage_cases import CASES, SUITE_CANONICAL
from provider_stage_fixture import StageFixture
from signed_provider_contract import sha


def evaluate():
    rows = []
    for case, mode, expected in CASES:
        with tempfile.TemporaryDirectory() as folder:
            fixture = StageFixture(Path(folder).resolve(), mode)
            try:
                fixture.prepare()
            except ValueError:
                outcome = "identity_rejected"
            else:
                try:
                    fixture.finish()
                    outcome = "receipt_consumed"
                except ValueError:
                    outcome = "receipt_rejected"
        rows.append({"case": case, "expected": expected, "outcome": outcome})
    return {
        "suite_sha256": sha(SUITE_CANONICAL.encode()),
        "cases": rows,
        "summary": {
            "cases": len(rows),
            "expected_results": sum(r["expected"] == r["outcome"] for r in rows),
            "consumed_synthetic_receipts": sum(r["outcome"] == "receipt_consumed" for r in rows),
        },
        "real_network_calls": 0,
        "native_inference_calls": 0,
        "private_documents": 0,
        "live_authentication_qualified": False,
        "live_execution_identity_qualified": False,
        "production_activation": False,
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
