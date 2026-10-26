import asyncio
import json
import sys
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend"), str(ROOT / "deploy")]
import journal_recovery_fixture as fixture  # noqa: E402
import test_authenticated_operator_review as retained  # noqa: E402
from campaign_test_assets import share_immutable_assets  # noqa: E402
from ci_case_discovery import declared, install  # noqa: E402


class JournalRecoveryContracts(unittest.IsolatedAsyncioTestCase):
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
                self.assertTrue(row["recovery_preserves_all_four_histories"])
            finally:
                await asyncio.gather(*(c.aclose() for c in clients))
                f.close()

    async def test_unassigned_actor_is_denied_before_reader_storage_inspection(self):
        with self.readonly():
            f = fixture.Fixture("G97_unassigned_storage", self.models, self.work, self.anchors, self.api)
            try:
                f.login("other")
                (f.change_controls.root / "metadata.json").write_bytes(b"invented damaged metadata")
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.services[0]), base_url="http://operator.invalid") as client:
                    self.assertEqual((await fixture.raw.Fixture.request(f, client, "recovery_observe", "other", {"change_id": f.change_id, "target": "window"})).status_code, 403)
            finally:
                f.close()

    async def test_frozen_policy_and_retained_model_budget(self):
        self.assertEqual(json.loads((ROOT / "deploy/fixtures/journal_recovery_policy.json").read_text()), fixture.POLICY)
        self.assertEqual(self.api.artifact_store.Budget().seconds, 20)
        self.assertEqual(declared(type(self)), {name: (name, status) for name, status in fixture.CASES})

    async def test_malformed_and_borrowed_repair_views_do_not_append(self):
        with self.readonly():
            f = fixture.Fixture("G98_invalid_view", self.models, self.work, self.anchors, self.api)
            clients = [httpx.AsyncClient(transport=httpx.ASGITransport(app=s), base_url="http://operator.invalid") for s in f.services]
            try:
                a, b = clients[:2]
                await f.setup_window(a, b)
                self.assertEqual((await f.change(a, "change_open", decision_sha256=f.change_decision["decision_sha256"])).status_code, 200)
                f.binding_fault = "selected_retained"
                self.assertEqual((await f.select_child(a, b)).status_code, 400)
                value = (await f.observe_recovery(a, "destination")).json()
                before = f.four_histories()
                bad = await fixture.raw.Fixture.request(f, b, "recovery_apply", "reviewer", {"change_id": f.change_id, "target": "destination", "expected_view_sha256": value["view_sha256"]})
                self.assertEqual(bad.status_code, 409)
                for body in ({"change_id": f.change_id, "target": "other"}, {"change_id": f.change_id, "target": "window", "path": "invented"}):
                    result = await fixture.raw.Fixture.request(f, a, "recovery_observe", "preparer", body)
                    self.assertEqual(result.status_code, 400)
                self.assertEqual(f.four_histories(), before)
            finally:
                await asyncio.gather(*(c.aclose() for c in clients))
                f.close()



share_immutable_assets(JournalRecoveryContracts)
install(JournalRecoveryContracts, fixture.CASES)

if __name__ == "__main__":
    unittest.main()
