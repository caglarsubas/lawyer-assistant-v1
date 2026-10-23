"""Offline deterministic comparisons; fake sockets only, no deployment effects."""
import errno
import hashlib
import json

from metadata_phase_fixture import RELAY, SENTINEL, Fixture
from origin_route_cases import CASES, SUITE_CANONICAL
from origin_route_comparison import compare, local_observation


class ComparisonFixture(Fixture):
    class Socket(Fixture.Socket):
        def connect(self, address):
            if self.owner.mode == "refused":
                raise ConnectionRefusedError(errno.ECONNREFUSED, SENTINEL)
            super().connect(address)

        def makefile(self, mode):
            if self.owner.mode == "preheader_close":
                return Fixture.File(self.owner, self, b"")
            return super().makefile(mode)

    def socket(self, family, kind):
        self.operations.append("socket_created")
        return self.Socket(self)


def pair(origin_mode, route_mode, owner=True):
    origin, route = ComparisonFixture(origin_mode), ComparisonFixture(route_mode)
    local = local_observation(origin.binding, RELAY, "synthetic-root", verifier=lambda _: owner,
                              socket_factory=origin.socket, context_factory=lambda: origin.context, clock=lambda: origin.now)
    result = compare(local, route.run())
    assert SENTINEL not in json.dumps(result)
    return result, origin, route


def evaluate():
    rows = [{"case": case, "expected_classification": expected, "comparison": pair(a, b, owner)[0]}
            for case, a, b, owner, expected in CASES]
    return {"suite_sha256": hashlib.sha256(SUITE_CANONICAL.encode()).hexdigest(), "cases": rows,
            "summary": {"cases": len(rows), "expected_results": sum(r["comparison"]["classification"] == r["expected_classification"] for r in rows),
                        "mock_connections": sum(r["comparison"]["aggregate_connection_attempts"] for r in rows),
                        "mock_GET_attempts": sum(r["comparison"]["aggregate_metadata_GET_attempts"] for r in rows)},
            "real_network_calls": 0, "native_inference_calls": 0, "private_documents": 0,
            "qualified_identity": False, "production_activation": False, "historical_timeout_cause_established": False}


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
