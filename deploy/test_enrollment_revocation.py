import asyncio
import json
import sys
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend"), str(ROOT / "deploy")]
import enrollment_revocation_fixture as fixture  # noqa: E402
import test_authenticated_operator_review as retained  # noqa: E402
from ci_case_discovery import declared, install  # noqa: E402


class EnrollmentRevocationContracts(unittest.IsolatedAsyncioTestCase):
    setUp = retained.AuthenticatedOperatorContracts.setUp
    tearDown = retained.AuthenticatedOperatorContracts.tearDown
    readonly = retained.AuthenticatedOperatorContracts.readonly

    async def qualify_case(self, name, expected):
        with self.readonly():
            f = fixture.Fixture(name, self.models, self.work, self.anchors, self.api)
            clients = [httpx.AsyncClient(transport=httpx.ASGITransport(app=s), base_url="http://operator.invalid") for s in f.services]
            try:
                status = await f.run(clients[:2])
                self.assertEqual(status, expected)
                row = f.result(status)
                self.assertTrue(row["original_history_preserved"])
                self.assertTrue(row["anchor_and_intents_not_restored"])
            finally:
                await asyncio.gather(*(c.aclose() for c in clients))
                f.close()

    async def test_frozen_policy_and_retained_model_budget(self):
        self.assertEqual(json.loads((ROOT / "deploy/fixtures/enrollment_revocation_policy.json").read_text()), fixture.POLICY)
        self.assertEqual(self.api.artifact_store.Budget().seconds, 20)
        self.assertEqual(declared(type(self)), {name: (name, status) for name, status in fixture.CASES})


install(EnrollmentRevocationContracts, fixture.CASES)

if __name__ == "__main__":
    unittest.main()
