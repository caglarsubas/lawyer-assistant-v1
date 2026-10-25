import asyncio
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend"), str(ROOT / "deploy")]
import build_guarded_controller_stage as builder  # noqa: E402
import operator_enrollment_evidence as evidence  # noqa: E402
import operator_review_fixture as fixture  # noqa: E402
import portable_controller_fixture as portable  # noqa: E402
from authenticated_operator_review import PREFIX  # noqa: E402
from campaign_test_assets import share_immutable_assets  # noqa: E402
from ci_case_discovery import declared, install  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from operator_review_auth import SessionAuthority  # noqa: E402
from test_portable_controller import unit_readonly  # noqa: E402


class AuthenticatedOperatorContracts(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.prior_bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.stage = self.root / "stage"
        self.approved = builder.build(self.stage)["manifest_sha256"]
        for name in list(sys.modules):
            if name == "lawyer_provider_stage" or name.startswith("lawyer_provider_stage."):
                del sys.modules[name]
        sys.path.insert(0, str(self.stage))
        self.api = portable.modules()
        self.models, self.work, self.anchors = [self.root / n for n in ("models", "work", "anchors")]
        for path in (self.models, self.work, self.anchors):
            path.mkdir(mode=0o700)
        portable.prepare(self.models, self.stage, self.api)
        for path in (self.models / "model").rglob("*"):
            if path.is_dir():
                path.chmod(0o700)
        (self.models / "model").chmod(0o700)

    def tearDown(self):
        sys.dont_write_bytecode = self.prior_bytecode
        sys.path.remove(str(self.stage))
        for name in list(sys.modules):
            if name == "lawyer_provider_stage" or name.startswith("lawyer_provider_stage."):
                del sys.modules[name]
        self.temp.cleanup()

    def readonly(self):
        from contextlib import ExitStack
        stack = ExitStack()
        inspect = evidence.inspect_stage
        stack.enter_context(unit_readonly(self.api))
        stack.enter_context(patch.object(evidence, "inspect_stage", side_effect=lambda p, h: inspect(p, h, require_readonly=False)))
        stack.enter_context(fixture.forbid_provider_helpers(self.api))
        return stack

    async def qualify_case(self, name, expected):
        with self.readonly():
            f = fixture.Fixture(name, self.models, self.work, self.anchors, self.api)
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.service), base_url="http://operator.invalid") as client:
                    status = await f.run(client)
                self.assertEqual(status, expected)
                self.assertTrue(f.result(status)["credentials_absent_from_responses_and_review_records"])
            finally:
                f.close()

    async def test_cancelled_metadata_write_finishes_before_guard_release_without_replay(self):
        with self.readonly():
            f = fixture.Fixture("unit-cancel", self.models, self.work, self.anchors, self.api)
            entered, release = threading.Event(), threading.Event()
            def pause(stage):
                if stage == "before_commit":
                    entered.set()
                    if not release.wait(3):
                        raise ValueError("Qualification pause exceeded")
            f.service.checkpoint = pause
            body = {"request_id": f.request_id, "packet_sha256": f.packet_sha, "observation_sha256": f.observation_sha}
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.service), base_url="http://operator.invalid") as client:
                    task = asyncio.create_task(client.post(PREFIX + "prepare", content=evidence.encode(body), headers=f.headers("preparer")))
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    task.cancel()
                    release.set()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                    f.service.checkpoint = None
                    self.assertEqual(len(list(f.ledger.iterdir())), 1)
                    response = await client.post(PREFIX + "prepare", content=evidence.encode(body), headers=f.headers("preparer"))
                    self.assertEqual(response.status_code, 409)
                with f.authority.app.state.firm_authorization.guard(fixture.FIRM, exclusive=True):
                    pass
            finally:
                release.set()
                f.close()

    async def test_production_or_arbitrary_store_is_refused_without_connecting(self):
        with self.assertRaises(HTTPException):
            SessionAuthority(SimpleNamespace(engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))), self.root,
                             firm_id="unapproved", bindings={}, origins=(fixture.ORIGIN,))

    async def test_auth_database_replacement_is_rejected(self):
        with self.readonly():
            f = fixture.Fixture("unit-db-swap", self.models, self.work, self.anchors, self.api)
            try:
                path = f.profile / "disposable-identities.sqlite"
                replacement = f.profile / "replacement.sqlite"
                replacement.write_bytes(path.read_bytes())
                replacement.chmod(0o600)
                replacement.replace(path)
                with self.assertRaises(HTTPException):
                    f.authority.validate_profile()
            finally:
                f.close()

    async def test_role_binding_configuration_is_not_mutable_by_requests(self):
        with self.readonly():
            f = fixture.Fixture("unit-policy", self.models, self.work, self.anchors, self.api)
            try:
                with self.assertRaises(TypeError):
                    f.authority.bindings[f.ids["preparer"]] = "reviewer"
            finally:
                f.close()

    async def test_retained_portable_package_policy_and_limits_remain_exact(self):
        previous = json.loads((ROOT / "deploy/fixtures/portable_controller_first_report.json").read_text())
        self.assertEqual(self.approved, previous["package_manifest_sha256"])
        self.assertEqual(json.loads((ROOT / "deploy/fixtures/authenticated_operator_policy.json").read_text()), fixture.POLICY)
        self.assertEqual(self.api.artifact_store.Budget().seconds, 20)
        self.assertEqual(declared(type(self)), {name: (name, status) for name, status in fixture.CASES})


share_immutable_assets(AuthenticatedOperatorContracts)
install(AuthenticatedOperatorContracts, fixture.CASES)

if __name__ == "__main__":
    unittest.main()
