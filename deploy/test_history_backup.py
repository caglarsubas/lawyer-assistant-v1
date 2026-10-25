import asyncio
import json
import sys
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend"), str(ROOT / "deploy")]
import history_backup_fixture as fixture  # noqa: E402
import test_authenticated_operator_review as retained  # noqa: E402


class HistoryBackupContracts(unittest.IsolatedAsyncioTestCase):
    setUp = retained.AuthenticatedOperatorContracts.setUp
    tearDown = retained.AuthenticatedOperatorContracts.tearDown
    readonly = retained.AuthenticatedOperatorContracts.readonly

    async def test_frozen_backup_restore_and_shared_instance_cases(self):
        with self.readonly():
            for name, expected in fixture.CASES:
                with self.subTest(case=name):
                    f = fixture.Fixture(name, self.models, self.work, self.anchors, self.api)
                    clients = [httpx.AsyncClient(transport=httpx.ASGITransport(app=s), base_url="http://operator.invalid") for s in f.services]
                    async def open_restored(ident):
                        service = f.service_for(f.services[0].vault.restored(ident))
                        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=service), base_url="http://operator.invalid")
                        clients.append(client)
                        return client
                    f.open_restored = open_restored
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
        self.assertEqual(json.loads((ROOT / "deploy/fixtures/history_backup_policy.json").read_text()), fixture.POLICY)
        self.assertEqual(self.api.artifact_store.Budget().seconds, 20)


if __name__ == "__main__":
    unittest.main()
