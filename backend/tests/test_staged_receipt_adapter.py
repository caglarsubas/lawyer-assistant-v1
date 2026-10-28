"""Disposable stage exports and authenticated adapter calls; no live provisioning."""

import ast
import asyncio
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "deploy")]
import build_receipt_stage as builder  # noqa: E402
import mode_recovery_fixture as fixture  # noqa: E402
import operator_enrollment_evidence as e  # noqa: E402
import receipt_stage_manifest as manifest  # noqa: E402
import test_authenticated_operator_review as retained  # noqa: E402
import test_operator_inventory_handoff as source  # noqa: E402
from campaign_test_assets import share_immutable_assets  # noqa: E402

RECORD, SOURCE, PROFILE = "1" * 32, "2" * 32, "3" * 32
ACTOR, CONTEXT, SCOPE, REQUEST = source.ACTOR, source.CONTEXT, source.SCOPE, source.REQUEST


def load(stage):
    for name in list(sys.modules):
        if name == manifest.PACKAGE or name.startswith(manifest.PACKAGE + "."):
            del sys.modules[name]
    sys.path.insert(0, str(stage))
    return SimpleNamespace(**{n: importlib.import_module(manifest.PACKAGE + "." + n)
                             for n in ("adapter", "readiness", "receipts", "inventory", "evidence")})


def unload(stage):
    sys.path.remove(str(stage))
    for name in list(sys.modules):
        if name == manifest.PACKAGE or name.startswith(manifest.PACKAGE + "."):
            del sys.modules[name]


class StageAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.stage = self.root / "stage"
        self.approved = builder.build(self.stage)["manifest_sha256"]
        self.bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        self.m = load(self.stage)
        store_root, profile_root = self.root / "receipts", self.root / "profile"
        store_root.mkdir(mode=0o700)
        profile_root.mkdir(mode=0o700)
        self.profile = profile_root / "disposable-profile.json"
        e.retain(self.profile, e.encode({"schema": "disposable-operator-review-v1", "profile_id": PROFILE, "production_activation": False}))
        self.store = self.m.receipts.ReceiptStore(root=store_root, context_id=CONTEXT, scope_sha256=SCOPE, key=AESGCM.generate_key(bit_length=256))
        self.pins = self.m.readiness.Pins(context_id=CONTEXT, scope_sha256=SCOPE, key_fingerprint=self.m.readiness.fingerprint(self.store.key),
                                         store_identity=self.store.identity, profile_id=PROFILE, profile_sha256=e.sha(self.profile.read_bytes()))
        self.raw, self.calls, self.resolutions = source.receipt(), [], 0
        self.bound = self.m.adapter.PreparedSource(raw=self.raw, expected_sha256=e.sha(self.raw), selection=REQUEST)
        self.adapter = self.make()

    def tearDown(self):
        unload(self.stage)
        sys.dont_write_bytecode = self.bytecode
        self.temp.cleanup()

    async def authorize(self):
        return ACTOR

    async def read(self, action, body):
        self.calls.append(action)
        return 200, source.source.encoded(source.source.wire(), action)

    async def resolve(self, scope):
        self.resolutions += 1
        return self.m.adapter.Session(actor_sha256=ACTOR, profile_id=PROFILE,
                    reader=self.m.inventory.BoundReader(scope_sha256=SCOPE, authorize=self.authorize, read=self.read))

    def make(self, resolve=None, pins=None, sources=None, readonly=False):
        return self.m.adapter.ReceiptAdapter(self.stage, self.approved, self.store, self.profile, pins or self.pins,
                                             resolve or self.resolve, {SOURCE: self.bound} if sources is None else sources,
                                             require_readonly=readonly)

    async def request(self, action, body, adapter=None, *, raw=None, suffix="", method="POST"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=adapter or self.adapter), base_url="http://stage.invalid") as client:
            return await client.request(method, self.m.adapter.PREFIX + action + suffix,
                                        content=e.encode(body) if raw is None else raw,
                                        headers={"cookie": "la_session=disposable-only", "origin": "http://stage.invalid",
                                                 "x-csrf-token": "disposable-only", "content-type": "application/json"})

    async def capture(self, adapter=None):
        return await self.request("retain", {"source_id": SOURCE, "expected_source_sha256": e.sha(self.raw), "record_id": RECORD}, adapter)

    async def test_deterministic_closed_source_only_stage_preserves_import_only_semantics(self):
        second = self.root / "second"
        built = builder.build(second)
        self.assertEqual(built["manifest_sha256"], self.approved)
        self.assertEqual(len(built["manifest"]["package_sha256"]), 9)
        self.assertFalse(built["manifest"]["private_material_included"])
        for name, output in manifest.SOURCES.items():
            expected = builder.PortableImports().visit(ast.parse((ROOT / "scripts" / (name + ".py")).read_bytes()))
            actual = ast.parse((second / manifest.PACKAGE / (output + ".py")).read_bytes())
            self.assertEqual(ast.dump(expected), ast.dump(actual))
        with self.assertRaises(FileExistsError):
            builder.build(self.stage)

    async def test_isolated_import_loads_no_application_engine_or_host_helpers(self):
        driver = ("import sys;sys.path.insert(0," + repr(str(ROOT / 'scripts')) + ");"
                  "from receipt_stage_manifest import inspect_stage;inspect_stage(" + repr(str(self.stage)) + ',' + repr(self.approved) + ",require_readonly=False);"
                  "sys.path.insert(0," + repr(str(self.stage)) + ");import lawyer_receipt_stage.adapter;"
                  "assert not any(n=='app' or n.startswith(('app.','inference_engine')) for n in sys.modules);")
        result = subprocess.run([sys.executable, "-I", "-B", "-c", driver], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, "Isolated stage import failed")
        self.assertEqual(result.stdout, b"")

    async def test_unknown_private_file_and_wrong_stage_pin_are_rejected_before_import(self):
        with self.assertRaises(ValueError):
            manifest.inspect_stage(self.stage, "0" * 64, require_readonly=False)
        with self.assertRaises(ValueError):
            manifest.inspect_stage(self.stage, self.approved)  # Writable unit stages are not kernel-readonly.
        (self.stage / "invented-private-key").write_bytes(b"private-marker")
        with self.assertRaises(ValueError):
            manifest.inspect_stage(self.stage, self.approved, require_readonly=False)

    async def test_manifest_duplicates_and_forbidden_imports_are_rejected(self):
        path = self.stage / manifest.MANIFEST
        raw = path.read_bytes().replace(b'"version": 1,', b'"version": 1, "version": 1,')
        path.write_bytes(raw)
        with self.assertRaises(ValueError):
            manifest.inspect_stage(self.stage, e.sha(raw), require_readonly=False)
        value = builder.build(self.root / "clean")["manifest"]
        target = self.stage / manifest.PACKAGE / "adapter.py"
        target.write_text(target.read_text() + "\nfrom app import db\n")
        value["package_sha256"]["adapter.py"] = e.sha(target.read_bytes())
        raw = e.encode(value)
        path.write_bytes(raw)
        with self.assertRaises(ValueError):
            manifest.inspect_stage(self.stage, e.sha(raw), require_readonly=False)

    async def test_readiness_matches_independent_pins_without_granting_custody_or_appointments(self):
        value = self.adapter.readiness()
        self.assertEqual(value["state"], "ready_for_disposable_validation")
        self.assertEqual(set(value["checks"].values()), {"verified"})
        self.assertEqual(value["key_custody"], "unassessed")
        self.assertEqual(value["operator_appointments"], "unassessed")
        self.assertFalse(any(value[k] for k in e.FLAGS))
        self.assertEqual(self.calls, [])
        for changes, gate in (({"context_id": "0" * 32}, "store_binding"), ({"scope_sha256": "0" * 64}, "store_binding"),
                              ({"store_identity": (0, 0)}, "store_binding"), ({"key_fingerprint": "0" * 64}, "key_binding"),
                              ({"profile_id": "0" * 32}, "disposable_profile"), ({"profile_sha256": "0" * 64}, "disposable_profile")):
            with self.subTest(gate=gate, changes=changes):
                blocked = self.m.readiness.assess(self.stage, self.approved, self.store, self.profile,
                             replace(self.pins, **changes), require_readonly=False)
                self.assertEqual(blocked["state"], "blocked")
                self.assertEqual(blocked["checks"][gate], "blocked")
        self.assertEqual(self.make(readonly=True).readiness()["state"], "blocked")

    async def test_disposable_profile_schema_rejects_production_and_unknown_fields(self):
        for kind in ("production", "extra", "duplicate"):
            value = {"schema": "disposable-operator-review-v1", "profile_id": PROFILE, "production_activation": kind == "production"}
            if kind == "extra":
                value["private-marker"] = True
            raw = b'{"schema":0,"schema":1}' if kind == "duplicate" else e.encode(value)
            self.profile.write_bytes(raw)
            with self.subTest(kind=kind):
                self.assertEqual(self.make(pins=replace(self.pins, profile_sha256=e.sha(raw))).readiness()["state"], "blocked")

    async def test_authorization_denial_precedes_body_and_private_readiness(self):
        async def denied(scope):
            raise PermissionError("private-marker")
        adapter = self.make(resolve=denied)
        response = await self.capture(adapter)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("private-marker", response.text)
        self.assertEqual(list(self.store.root.iterdir()), [])
        self.assertEqual(self.calls, [])
        async def wrong(scope):
            actor = await self.resolve(scope)
            return replace(actor, profile_id="0" * 32)
        self.assertEqual((await self.capture(self.make(resolve=wrong))).status_code, 403)

    async def test_closed_routes_bodies_and_budgets_never_expand_the_sources(self):
        cases = (("retain", {"source_id": SOURCE, "expected_source_sha256": e.sha(self.raw), "record_id": RECORD, "key": "private-marker"}, None, "", "POST", 400),
                 ("retain", {"source_id": "0" * 32, "expected_source_sha256": e.sha(self.raw), "record_id": RECORD}, None, "", "POST", 404),
                 ("readiness", {}, b"x" * 2049, "", "POST", 400), ("readiness", {}, b'{"a":0,"a":1}', "", "POST", 400),
                 ("readiness", {}, None, "?context=other", "POST", 400), ("install", {}, None, "", "POST", 404),
                 ("readiness", {}, None, "", "GET", 405))
        for action, body, raw, suffix, method, status in cases:
            with self.subTest(action=action, status=status):
                response = await self.request(action, body, raw=raw, suffix=suffix, method=method)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertNotIn("private-marker", response.text)
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.store.root.iterdir()), [])

    async def test_staged_capture_and_reobservation_preserve_exact_ciphertext_and_source(self):
        captured = await self.capture()
        self.assertEqual(captured.status_code, 200)
        path = self.store.root / (RECORD + ".receipt")
        before = path.read_bytes()
        response = await self.request("reobserve", {"record_id": RECORD, "expected_record_sha256": captured.json()["record_sha256"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["retained"]["source"]["receipt_sha256"], e.sha(self.raw))
        self.assertEqual(response.json()["comparison"]["outcome"], "unchanged_metadata")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(self.resolutions, 4)

    async def test_configuration_and_source_selection_are_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            self.adapter.readonly = False
        with self.assertRaises(TypeError):
            self.adapter.sources[SOURCE] = None
        with self.assertRaises(TypeError):
            self.bound.selection["context_id"] = "0" * 32
        self.assertNotIn(repr(self.store.key), repr(self.adapter))

    async def test_admission_guards_release_before_nested_reads_and_on_denial_or_cancellation(self):
        held, released = [], []
        class Guard:
            def __init__(self):
                held.append(self)
            def __exit__(self, *args):
                held.remove(self)
                released.append(self)
        for mode in ("denied", "cancelled", "success"):
            async def resolve(scope):
                scope["state"]["firm_guard"] = Guard()
                if mode == "denied":
                    raise PermissionError
                if mode == "cancelled":
                    raise asyncio.CancelledError
                actor = await self.resolve(scope)
                async def read(action, body):
                    self.assertEqual(held, [])
                    return await self.read(action, body)
                return replace(actor, reader=self.m.inventory.BoundReader(scope_sha256=SCOPE, authorize=self.authorize, read=read))
            with self.subTest(mode=mode):
                if mode == "cancelled":
                    with self.assertRaises(asyncio.CancelledError):
                        await self.capture(self.make(resolve=resolve))
                else:
                    self.assertEqual((await self.capture(self.make(resolve=resolve))).status_code, 403 if mode == "denied" else 200)
            self.assertEqual(held, [])
        self.assertEqual(len(released), 4)

    async def test_ambiguous_or_bearer_session_headers_never_reach_the_resolver(self):
        base = [("cookie", "la_session=disposable-only"), ("origin", "http://stage.invalid"),
                ("x-csrf-token", "disposable-only"), ("content-type", "application/json")]
        cases = [base + [("cookie", "la_session=another-disposable")],
                 [(k, v + "; la_session=another-disposable" if k == "cookie" else v) for k, v in base],
                 [(k, v) for k, v in base if k != "x-csrf-token"], base + [("authorization", "Bearer disposable-only")],
                 [(k, "text/plain" if k == "content-type" else v) for k, v in base]]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.adapter), base_url="http://stage.invalid") as client:
            for headers in cases:
                with self.subTest(headers=headers):
                    response = await client.post(self.m.adapter.PREFIX + "readiness", content=b"{}", headers=headers)
                    self.assertEqual(response.status_code, 400)
        self.assertEqual(self.resolutions, 0)
        self.assertEqual(self.calls, [])

    async def test_lost_response_authorization_preserves_committed_record_without_replay(self):
        count = 0
        async def resolve(scope):
            nonlocal count
            count += 1
            if count == 2:
                raise PermissionError("private-marker")
            return await self.resolve(scope)
        response = await self.capture(self.make(resolve=resolve))
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("record_sha256", response.text)
        path = self.store.root / (RECORD + ".receipt")
        before = path.read_bytes()
        self.assertEqual((await self.capture()).status_code, 409)
        self.assertEqual(path.read_bytes(), before)

    async def test_package_or_profile_changes_during_reads_release_no_history(self):
        captured = await self.capture()
        original = (self.store.root / (RECORD + ".receipt")).read_bytes()
        target = self.stage / manifest.PACKAGE / "adapter.py"
        package_bytes, profile_bytes = target.read_bytes(), self.profile.read_bytes()
        for kind in ("package", "profile"):
            async def resolve(scope):
                actor = await self.resolve(scope)
                async def read(action, body):
                    if action == "joint_finish_observe":
                        changed = target if kind == "package" else self.profile
                        changed.write_bytes(changed.read_bytes() + b"\n")
                    return await self.read(action, body)
                return replace(actor, reader=self.m.inventory.BoundReader(scope_sha256=SCOPE, authorize=self.authorize, read=read))
            with self.subTest(kind=kind):
                response = await self.request("reobserve", {"record_id": RECORD, "expected_record_sha256": captured.json()["record_sha256"]}, self.make(resolve=resolve))
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("retained", response.text)
                self.assertEqual((self.store.root / (RECORD + ".receipt")).read_bytes(), original)
            target.write_bytes(package_bytes)
            self.profile.write_bytes(profile_bytes)

    async def test_cancelled_and_stalled_requests_publish_nothing(self):
        async def cancelled(scope):
            raise asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await self.capture(self.make(resolve=cancelled))
        adapter = self.adapter
        async def receive():
            await asyncio.sleep(1)
            return {"type": "http.request", "body": b"{}"}
        from unittest.mock import patch
        with patch.object(self.m.inventory, "READ_SECONDS", .02), self.assertRaises(TimeoutError):
            await adapter.body(receive)
        self.assertEqual(list(self.store.root.iterdir()), [])


class AuthenticatedStageTests(unittest.IsolatedAsyncioTestCase):
    setUp = retained.AuthenticatedOperatorContracts.setUp
    tearDown = retained.AuthenticatedOperatorContracts.tearDown
    readonly = retained.AuthenticatedOperatorContracts.readonly

    async def exercise(self, mode):
        with self.readonly():
            stage = self.root / "receipt-stage"
            approved = builder.build(stage)["manifest_sha256"]
            m = load(stage)
            f = fixture.Fixture("C01_retirement_ordered" if mode == "retirement" else "C09_rollback_ordered",
                                self.models, self.work, self.anchors, self.api)
            clients = [httpx.AsyncClient(transport=httpx.ASGITransport(app=s), base_url="http://operator.invalid") for s in f.services]
            try:
                a, b = clients[:2]
                await f.setup_joint(a, b)
                first = (await f.observe_joint(a)).json()
                calls = []
                async def read(action, body):
                    calls.append(action)
                    response = await fixture.raw.Fixture.request(f, a, action, "preparer", body)
                    return response.status_code, response.content
                actor = f.authority.snapshot(f.session_ids["preparer"], f.ids["preparer"], "preparer", now=f.now)
                actor_hash = e.sha(e.encode(actor))
                async def authorized():
                    try:
                        f.authority.recheck(actor, now=f.now)
                        return actor_hash
                    except Exception:
                        raise PermissionError from None
                reader = m.inventory.BoundReader(scope_sha256=first["scope_sha256"], authorize=authorized, read=read)
                selection = {"context_id": CONTEXT, "change_id": f.change_id, "expected_context_sha256": first["context_sha256"]}
                raw = e.encode(await m.inventory.collect({CONTEXT: reader}, [selection], actor_sha256=actor_hash))
                root = self.root / "stage-receipts"
                root.mkdir(mode=0o700)
                store = m.receipts.ReceiptStore(root=root, context_id=CONTEXT, scope_sha256=first["scope_sha256"], key=AESGCM.generate_key(bit_length=256))
                profile = f.profile / "disposable-profile.json"
                pins = m.readiness.Pins(context_id=CONTEXT, scope_sha256=first["scope_sha256"], key_fingerprint=m.readiness.fingerprint(store.key),
                                        store_identity=store.identity, profile_id=f.authority.profile_id, profile_sha256=e.sha(profile.read_bytes()))
                async def resolve(scope):
                    try:
                        current = f.authority.resolve(scope, "preparer", now=f.now)
                    except Exception:
                        raise PermissionError from None
                    current_hash = e.sha(e.encode(current))
                    async def recheck():
                        try:
                            f.authority.recheck(current, now=f.now)
                            return current_hash
                        except Exception:
                            raise PermissionError from None
                    return m.adapter.Session(actor_sha256=current_hash, profile_id=current["profile_id"],
                        reader=m.inventory.BoundReader(scope_sha256=first["scope_sha256"], authorize=recheck, read=read))
                adapter = m.adapter.ReceiptAdapter(stage, approved, store, profile, pins, resolve,
                          {SOURCE: m.adapter.PreparedSource(raw=raw, expected_sha256=e.sha(raw), selection=selection)}, require_readonly=False)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=adapter), base_url="http://operator.invalid") as client:
                    async def request(action, body, *, headers=None):
                        return await client.post(m.adapter.PREFIX + action, content=e.encode(body), headers=f.headers("preparer") if headers is None else headers)
                    ready = await request("readiness", {})
                    self.assertEqual(ready.status_code, 200)
                    self.assertEqual(ready.json()["key_custody"], "unassessed")
                    before = f.four_histories()
                    captured = await request("retain", {"source_id": SOURCE, "expected_source_sha256": e.sha(raw), "record_id": RECORD})
                    self.assertEqual(captured.status_code, 200)
                    self.assertEqual(f.four_histories(), before)
                    path = root / (RECORD + ".receipt")
                    ciphertext = path.read_bytes()
                    body = {"record_id": RECORD, "expected_record_sha256": captured.json()["record_sha256"]}
                    outcomes = []
                    async def check(state, outcome=None, *, headers=None, status=200):
                        before = f.four_histories()
                        response = await request("reobserve", body, headers=headers)
                        self.assertEqual(response.status_code, status)
                        self.assertEqual(response.json()["state"], state)
                        self.assertEqual(response.headers["cache-control"], "no-store")
                        if outcome:
                            self.assertEqual(response.json()["comparison"]["outcome"], outcome)
                        else:
                            self.assertNotIn("retained", response.json())
                        self.assertEqual(f.four_histories(), before)
                        self.assertEqual(path.read_bytes(), ciphertext)
                        outcomes.append(state)
                    await check("pending_anchors", "unchanged_metadata")
                    f.login("other")
                    await check("denied", headers=f.headers("other"), status=403)
                    wrong = dict(f.headers("preparer"))
                    wrong["origin"] = "https://unapproved.invalid"
                    await check("denied", headers=wrong, status=403)
                    for state in ("pending_anchors", "reconciled_metadata"):
                        view = (await f.observe_joint(a)).json()
                        self.assertEqual((await f.apply_joint(a, view)).status_code, 200)
                        await check(state, "changed_metadata")
                    if mode == "retirement":
                        f.revoke("reviewer")
                        await check("reconciled_metadata", "changed_metadata")
                        f.advance(301)
                    else:
                        await f.withdrawal(a, b)
                    await check("source_changed", "changed_metadata")
                    f.revoke("preparer")
                    count = len(calls)
                    await check("denied", status=403)
                    self.assertEqual(len(calls), count)
                    print("STAGED_RECEIPT_CASE " + json.dumps({"mode": mode, "retentions": 1, "reobservations": len(outcomes),
                          "controller_reads_including_source_collection": len(calls), "outcomes": outcomes,
                          "exact_ciphertext_and_four_histories_preserved": True, "native_or_production_qualification": False}))
            finally:
                await asyncio.gather(*(c.aclose() for c in clients))
                f.close()
                unload(stage)

    async def test_authenticated_stage_retirement_origin_role_expiry_and_revocation(self):
        await self.exercise("retirement")

    async def test_authenticated_stage_rollback_origin_role_withdrawal_and_revocation(self):
        await self.exercise("rollback")


share_immutable_assets(AuthenticatedStageTests)
