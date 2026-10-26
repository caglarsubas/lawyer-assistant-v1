import asyncio
import json
import shutil
import sys
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend"), str(ROOT / "deploy")]
import destination_change_fixture as fixture  # noqa: E402
import test_authenticated_operator_review as retained  # noqa: E402
from campaign_test_assets import share_immutable_assets  # noqa: E402
from ci_case_discovery import declared, install  # noqa: E402


class DestinationChangeContracts(unittest.IsolatedAsyncioTestCase):
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
                self.assertTrue(row["legacy_history_immutable"])
                self.assertTrue(row["destination_and_transition_prefixes_preserved"])
            finally:
                await asyncio.gather(*(c.aclose() for c in clients))
                f.close()

    async def test_unassigned_actor_is_denied_before_reader_storage_inspection(self):
        with self.readonly():
            f = fixture.Fixture("D97_unassigned_storage", self.models, self.work, self.anchors, self.api)
            try:
                f.login("other")
                (f.change_controls.root / "metadata.json").write_bytes(b"invented damaged metadata")
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.services[0]), base_url="http://operator.invalid") as client:
                    self.assertEqual((await f.change(client, "change_status", role="other")).status_code, 403)
            finally:
                f.close()

    async def test_frozen_policy_and_retained_model_budget(self):
        self.assertEqual(json.loads((ROOT / "deploy/fixtures/destination_change_policy.json").read_text()), fixture.POLICY)
        self.assertEqual(self.api.artifact_store.Budget().seconds, 20)
        self.assertEqual(declared(type(self)), {name: (name, status) for name, status in fixture.CASES})

    async def test_copied_legacy_namespace_is_rejected_before_change_preparation(self):
        with self.readonly():
            f = fixture.Fixture("D98_copied_namespace", self.models, self.work, self.anchors, self.api)
            clients = [httpx.AsyncClient(transport=httpx.ASGITransport(app=s), base_url="http://operator.invalid") for s in f.services]
            try:
                await f.initialize(*clients[:2])
                root = f.legacy_controls.root
                held = root.with_name(root.name + "-original")
                root.rename(held)
                shutil.copytree(held, root)
                response = await f.change(clients[0], "change_status")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(len(list(f.change_controls.root.glob("[0-9a-f]*.json"))), 0)
            finally:
                await asyncio.gather(*(c.aclose() for c in clients))
                f.close()

    async def test_unknown_decisions_steps_and_clock_rollback_do_not_append(self):
        with self.readonly():
            f = fixture.Fixture("D07_invalid_values", self.models, self.work, self.anchors, self.api)
            clients = [httpx.AsyncClient(transport=httpx.ASGITransport(app=s), base_url="http://operator.invalid") for s in f.services]
            try:
                a, b = clients[:2]
                self.assertEqual(await f.run((a, b)), 409)
                before = f.retained_files(f.change_controls)
                result = await f.change(b, "change_decide", role="reviewer", proposal_sha256=f.change_proposal["proposal_sha256"], decision="unknown", reason_code=None)
                self.assertEqual(result.status_code, 400)
                self.assertEqual(f.retained_files(f.change_controls), before)
                f.advance(1)
                result = await f.change(b, "change_decide", role="reviewer", proposal_sha256=f.change_proposal["proposal_sha256"], decision="approve", reason_code="exact_destination_change_checked")
                self.assertEqual(result.status_code, 200)
                decision = result.json()["decision_sha256"]
                f.advance(1)
                self.assertEqual((await f.change(a, "change_open", decision_sha256=decision)).status_code, 200)
                before = f.retained_files(f.reader_controls)
                self.assertEqual((await f.change(a, "change_step", step=None, decision=None)).status_code, 400)
                self.assertEqual(f.retained_files(f.reader_controls), before)
                self.assertEqual((await f.change(a, "change_step", step="prepare", decision=None)).status_code, 200)
                before = f.retained_files(f.reader_controls)
                self.assertEqual((await f.change(b, "change_step", role="reviewer", step="decide", decision="unknown")).status_code, 400)
                self.assertEqual(f.retained_files(f.reader_controls), before)
                f.advance(-1)
                self.assertEqual((await f.change(a, "change_status")).status_code, 400)
                self.assertEqual(f.retained_files(f.reader_controls), before)
            finally:
                await asyncio.gather(*(c.aclose() for c in clients))
                f.close()



share_immutable_assets(DestinationChangeContracts)
install(DestinationChangeContracts, fixture.CASES)

if __name__ == "__main__":
    unittest.main()
