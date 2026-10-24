"""Frozen invented route evaluation, no native inference or network sockets."""

import asyncio
import json
import tempfile
from pathlib import Path

from immutable_route_cases import CASES, SUITE_CANONICAL
from immutable_route_fixture import RouteFixture
from signed_provider_contract import sha


async def evaluate_async():
    rows = []
    for case, mode, status, calls in CASES:
        with tempfile.TemporaryDirectory() as folder:
            fixture = RouteFixture(Path(folder).resolve(), mode)
            actual = await fixture.run()
        rows.append({"case": case, "expected": [status, calls], "actual": list(actual)})
    return {
        "suite_sha256": sha(SUITE_CANONICAL.encode()),
        "cases": rows,
        "summary": {
            "cases": len(rows),
            "expected_results": sum(v["expected"] == v["actual"] for v in rows),
        },
        "real_network_calls": 0,
        "native_inference_calls": 0,
        "private_documents": 0,
        "production_activation": False,
        "executed_weights_qualified": False,
    }


def evaluate():
    return asyncio.run(evaluate_async())


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
