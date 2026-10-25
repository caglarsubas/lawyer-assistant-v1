import asyncio
import json
import sys
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend"), str(ROOT / "deploy")]
import test_authenticated_operator_review as retained  # noqa: E402
import withdrawal_backup_fixture as fixture  # noqa: E402


class WithdrawalBackupContracts(unittest.IsolatedAsyncioTestCase):
    setUp = retained.AuthenticatedOperatorContracts.setUp
    tearDown = retained.AuthenticatedOperatorContracts.tearDown
    readonly = retained.AuthenticatedOperatorContracts.readonly

    async def test_frozen_archive_and_fence_cases(self):
        with self.readonly():
            for name, expected in fixture.CASES:
                with self.subTest(case=name):
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
        self.assertEqual(json.loads((ROOT / "deploy/fixtures/withdrawal_backup_policy.json").read_text()), fixture.POLICY)
        self.assertEqual(self.api.artifact_store.Budget().seconds, 20)

    async def test_separate_backup_mount_keeps_case_namespaces_disjoint(self):
        external = self.root / "separate-backup-mount"
        external.mkdir(mode=0o700)
        fixtures = []
        try:
            with self.readonly():
                for name in ("W01_namespace_first", "W02_namespace_second"):
                    fixtures.append(fixture.Fixture(name, self.models, self.work, self.anchors, self.api, backups=external))
                self.assertNotEqual(fixtures[0].archive_bundles, fixtures[1].archive_bundles)
                self.assertTrue(all(f.archive_bundles.parent == external for f in fixtures))
        finally:
            for f in fixtures:
                f.close()


if __name__ == "__main__":
    unittest.main()
