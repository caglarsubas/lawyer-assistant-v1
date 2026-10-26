import asyncio
import json
import sys
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend"), str(ROOT / "deploy")]
import staged_reader_fixture as fixture  # noqa: E402
import test_authenticated_operator_review as retained  # noqa: E402
from campaign_test_assets import share_immutable_assets  # noqa: E402
from ci_case_discovery import declared, install  # noqa: E402


class StagedReaderContracts(unittest.IsolatedAsyncioTestCase):
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

    async def test_unassigned_actor_is_denied_before_reader_storage_inspection(self):
        with self.readonly():
            f = fixture.Fixture("B97_unassigned_storage", self.models, self.work, self.anchors, self.api)
            try:
                f.login("other")
                (f.reader_controls.root / "metadata.json").write_bytes(b"invented damaged metadata")
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.services[0]), base_url="http://operator.invalid") as client:
                    self.assertEqual((await f.request(client, "reader_observe", "other", {})).status_code, 403)
            finally:
                f.close()

    async def test_frozen_policy_and_retained_model_budget(self):
        self.assertEqual(json.loads((ROOT / "deploy/fixtures/staged_reader_policy.json").read_text()), fixture.POLICY)
        self.assertEqual(self.api.artifact_store.Budget().seconds, 20)
        self.assertEqual(declared(type(self)), {name: (name, status) for name, status in fixture.CASES})



share_immutable_assets(StagedReaderContracts)
install(StagedReaderContracts, fixture.CASES)

if __name__ == "__main__":
    unittest.main()
