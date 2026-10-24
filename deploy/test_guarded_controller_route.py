import asyncio
import json
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import artifact_store as a  # noqa: E402
import guarded_controller_route as guarded  # noqa: E402
import guarded_route_fixture as q  # noqa: E402
from provider_stage_fixture import CREDENTIAL  # noqa: E402
from staged_signed_route import COMPLETION_PATH  # noqa: E402


class Switch:
    def __init__(self, fixture):
        self.fixture = fixture

    async def __call__(self, scope, receive, send):
        await self.fixture.application(scope, receive, send)


@contextmanager
def unit_readonly():
    # Unit-only adapter. Native qualification uses actual read-only ext4 mounts.
    def verify(root, manifest, budget=a.Budget(), **kwargs):
        result = a.verify_core(root, manifest, budget, time.monotonic() + budget.seconds,
                               strategy=kwargs.get("strategy", "stream"))
        result["peak_rss_kib"] = 10000
        return result
    with patch.object(a, "readonly", return_value=True), patch.object(a, "supervised_verify", side_effect=verify):
        yield


class ControllerContracts(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.models, self.work, self.anchors = [self.root / n for n in ("models", "work", "anchors")]
        for p in (self.models, self.work, self.anchors):
            p.mkdir(mode=0o700)
        q.layout(self.models)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, name):
        path = self.models / name
        index = q.decode(q.volume.small(path / "index.json"))
        proof = a.supervised_verify(path / ("snapshot-" + q.operation(name + "-child")) / "store", index["manifest"], strategy="windowed-pinned")
        return q.Fixture(name, self.models, self.work, self.anchors, binding_prefix="unit-fixture", proof=proof)

    async def run_case(self, name):
        f = self.fixture(name)
        try:
            if name == "G16_writable":
                with patch.object(a, "readonly", return_value=False):
                    f.application = f.app()
            else:
                f.application = f.app()
        except (ValueError, OSError):
            return f.result("setup_rejected", "factory")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=Switch(f)), base_url="http://staged.invalid") as client:
            async def post(path, value):
                return await client.post(path, content=q.encode(value), headers={"authorization": "Bearer " + CREDENTIAL, "content-type": "application/json"})
            status = await f.run(post, f.app)
        self.assertIsNone(f.application.controller.context.get())
        return f.result(status, "direct" if name == "G23_direct_hook" else "ASGI")

    async def test_frozen_controller_route_cases(self):
        with unit_readonly():
            for name, status, sends in q.CASES:
                with self.subTest(case=name):
                    result = await self.run_case(name)
                    self.assertEqual((result["status"], result["simulated_backend_sends"]), (status, sends))
                    self.assertTrue(result["privacy_sentinels_absent"])
                    self.assertFalse(result["native_execution_authorized"])

    async def test_factory_requires_explicit_mock_transport(self):
        with unit_readonly():
            f = self.fixture("G01_valid")
            real = httpx.AsyncHTTPTransport(retries=0)
            try:
                for value in (None, real):
                    with self.assertRaises(ValueError):
                        guarded.build(f.root, f.journal, f.binding, key=f.stage.base.key, issuer_key_id=q.ISSUER,
                                      receipts=f.receipts, resolve_identity=f.identity, clock=lambda: f.now, transport=value)
            finally:
                await real.aclose()

    async def test_cancellation_clears_context_and_burns_admission(self):
        with unit_readonly():
            f = self.fixture("G01_valid")
            f.application = f.app()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=Switch(f)), base_url="http://staged.invalid") as client:
                async def post(path, value):
                    return await client.post(path, content=q.encode(value), headers={"authorization": "Bearer " + CREDENTIAL, "content-type": "application/json"})
                await f.prepare(post)
                f.cancel = True
                with self.assertRaises(asyncio.CancelledError):
                    await post(COMPLETION_PATH, f.envelope)
                self.assertIsNone(f.application.controller.context.get())
                self.assertFalse(f.application.route.lock.locked())
                f.cancel = False
                f.application = f.app()
                self.assertEqual((await post(COMPLETION_PATH, f.envelope)).status_code, 400)
                self.assertEqual(len(f.sent), 1)
                self.assertEqual(f.journal.recover(f.child)["nonce_counts"], {"consumed": 1})

    async def test_signed_response_is_withheld_before_release(self):
        with unit_readonly():
            result = await self.run_case("G09_before_release")
        self.assertEqual(result["status"], 400)
        self.assertEqual(result["operation_state"], "revoked")
        self.assertEqual(result["nonce_counts"], {"consumed": 1})

    async def test_rollback_of_old_receipts_cannot_repeat_backend(self):
        with unit_readonly():
            result = await self.run_case("G22_receipt_rollback")
        self.assertEqual((result["status"], result["simulated_backend_sends"]), (400, 1))
        self.assertEqual(result["nonce_counts"], {"consumed": 1})

    async def test_exact_wire_and_public_consumer_stay_bound(self):
        with unit_readonly():
            result = await self.run_case("G29_exact_wire")
        self.assertTrue(q.base64.b64decode(result["frame"]["request_base64"]).endswith(b" \n"))
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["nonce_counts"], {"consumed": 1})

    async def test_pending_anchor_requires_explicit_reconciliation_without_replay(self):
        with unit_readonly():
            result = await self.run_case("G20_commit_gap")
        self.assertEqual(result["status"], 400)
        self.assertEqual(result["simulated_backend_sends"], 0)
        self.assertEqual(result["nonce_counts"], {"reserved": 1})

    async def test_policy_preserves_existing_limits_and_inactive_runtime(self):
        self.assertEqual(json.loads((ROOT / "deploy/fixtures/guarded_route_policy.json").read_text()), q.POLICY)
        self.assertEqual(a.Budget().seconds, 20)
        self.assertFalse(q.POLICY["production_activation"])
        self.assertEqual(q.POLICY["real_provider_requests"], 0)

    async def test_failed_release_never_returns_buffered_signed_bytes(self):
        with unit_readonly():
            f = self.fixture("G09_before_release")
            f.application = f.app()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=Switch(f)), base_url="http://staged.invalid") as client:
                async def post(path, value):
                    return await client.post(path, content=q.encode(value), headers={"authorization": "Bearer " + CREDENTIAL, "content-type": "application/json"})
                await f.prepare(post)
                f.armed = True
                response = await post(COMPLETION_PATH, f.envelope)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.content, q.encode({"error": "staged_request_rejected"}))
                self.assertNotIn(b"response_base64", response.content)
                self.assertNotIn(CREDENTIAL.encode(), response.content)
                self.assertEqual(response.headers["cache-control"], "no-store")


if __name__ == "__main__":
    unittest.main()
