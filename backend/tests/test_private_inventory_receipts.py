"""Encrypted selected metadata and fresh disposable authorization; no live cases."""

import asyncio
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "deploy")]
import mode_recovery_fixture as fixture  # noqa: E402
import operator_enrollment_evidence as e  # noqa: E402
import operator_recovery_inventory as inventory  # noqa: E402
import private_inventory_receipts as p  # noqa: E402
import test_authenticated_operator_review as retained  # noqa: E402
import test_operator_inventory_handoff as handoff  # noqa: E402
import test_operator_recovery_inventory as source  # noqa: E402
from campaign_test_assets import share_immutable_assets  # noqa: E402

ACTOR, CONTEXT, SCOPE, REQUEST = source.ACTOR, source.CONTEXT, source.SCOPE, source.REQUEST
RECORD = "1" * 32


class PrivateReceiptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.key = AESGCM.generate_key(bit_length=256)
        self.store = p.ReceiptStore(root=self.root, key=self.key, context_id=CONTEXT, scope_sha256=SCOPE)
        self.raw, self.calls, self.auths = handoff.receipt(), [], 0

    def tearDown(self):
        self.temp.cleanup()

    async def authorize(self):
        self.auths += 1
        return ACTOR

    async def read(self, action, body):
        self.calls.append((action, body))
        return 200, source.encoded(source.wire(), action)

    def reader(self, authorize=None, read=None):
        return inventory.BoundReader(scope_sha256=SCOPE, authorize=authorize or self.authorize, read=read or self.read)

    async def capture(self, *, reader=None, record=RECORD, raw=None):
        raw = self.raw if raw is None else raw
        return await p.retain(raw, e.sha(raw), REQUEST, self.store, reader or self.reader(), actor_sha256=ACTOR, record_id=record)

    async def observe(self, expected, *, reader=None, record=RECORD, store=None):
        return await p.reobserve(store or self.store, reader or self.reader(), record, expected, actor_sha256=ACTOR)

    def no_body(self, result, state):
        self.assertEqual(result["state"], state)
        self.assertIsNone(result["retained"])
        self.assertIsNone(result["current"])
        self.assertIsNone(result["comparison"])
        self.assertNotIn("private-marker", str(result))

    def decrypt(self, raw, record=RECORD):
        offset = len(p.MAGIC)
        return p.h._decode(AESGCM(self.key).decrypt(raw[offset:offset + 12], raw[offset + 12:], p._aad(self.store, record)))

    async def test_encrypted_roundtrip_exact_source_and_fresh_observation_after_reopen(self):
        captured = await self.capture()
        self.no_body(captured, "retained")
        path = self.root / (RECORD + ".receipt")
        raw = path.read_bytes()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(b"observations", raw)
        self.assertNotIn(b"actor_sha256", raw)
        self.assertEqual(e.sha(raw), captured["record_sha256"])
        record = self.decrypt(raw)
        self.assertEqual(record["handoff"]["source"]["row"], e.decode(self.raw)["rows"][0])
        self.assertEqual(record["handoff"]["source"]["receipt_sha256"], e.sha(self.raw))
        reopened = p.ReceiptStore(root=self.root, key=self.key, context_id=CONTEXT, scope_sha256=SCOPE)
        result = await self.observe(captured["record_sha256"], store=reopened)
        self.assertEqual(result["state"], "reconciled_metadata")
        self.assertEqual(result["retained"], record["handoff"])
        self.assertEqual(result["comparison"], {"outcome": "unchanged_metadata", "changed_fields": []})
        self.assertEqual(self.auths, 13)
        self.assertEqual(len(self.calls), 4)
        self.assertFalse(any(result[k] for k in inventory.FLAGS))
        self.assertFalse(result["atomic_snapshot"])
        self.assertEqual(result["review_validity"], "unassessed")
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(self.raw, handoff.receipt())

    async def test_create_only_publication_never_replaces_an_existing_record(self):
        first = await self.capture()
        path = self.root / (RECORD + ".receipt")
        before = path.read_bytes()
        self.no_body(await self.capture(), "conflict")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(e.sha(before), first["record_sha256"])
        self.assertEqual([x.name for x in self.root.iterdir()], [path.name])
        other = await self.capture(record="2" * 32)
        self.assertNotEqual(first["record_sha256"], other["record_sha256"])

    async def test_independent_hash_key_record_context_and_scope_pins_reject_replay(self):
        captured = await self.capture()
        original = (self.root / (RECORD + ".receipt")).read_bytes()
        cases = ("hash", "key", "record", "context", "scope", "tamper")
        for kind in cases:
            store, record, expected = self.store, RECORD, captured["record_sha256"]
            if kind == "hash":
                expected = "0" * 64
            elif kind == "key":
                store = p.ReceiptStore(root=self.root, key=AESGCM.generate_key(bit_length=256), context_id=CONTEXT, scope_sha256=SCOPE)
            elif kind in {"context", "scope"}:
                store = p.ReceiptStore(root=self.root, key=self.key, context_id="0" * 32 if kind == "context" else CONTEXT,
                                       scope_sha256="0" * 64 if kind == "scope" else SCOPE)
            elif kind == "record":
                record = "2" * 32
                (self.root / (record + ".receipt")).write_bytes(original)
                (self.root / (record + ".receipt")).chmod(0o600)
            else:
                changed = original[:-1] + bytes([original[-1] ^ 1])
                (self.root / (RECORD + ".receipt")).write_bytes(changed)
                expected = e.sha(changed)
            before_calls = len(self.calls)
            with self.subTest(kind=kind):
                if kind == "scope":
                    with self.assertRaises(ValueError):
                        await self.observe(expected, record=record, store=store)
                else:
                    self.no_body(await self.observe(expected, record=record, store=store), "unverifiable")
            self.assertEqual(len(self.calls), before_calls)
            (self.root / (RECORD + ".receipt")).write_bytes(original)

    async def test_filesystem_symlink_hardlink_mode_and_size_are_not_receipt_access(self):
        captured = await self.capture()
        path = self.root / (RECORD + ".receipt")
        original = path.read_bytes()
        for kind in ("symlink", "hardlink", "mode", "oversize"):
            path.unlink()
            target = self.root / "disposable-target"
            target.write_bytes(original)
            target.chmod(0o600)
            if kind == "symlink":
                path.symlink_to(target)
            elif kind == "hardlink":
                os.link(target, path)
            else:
                path.write_bytes(original if kind == "mode" else b"x" * (p.MAX_FILE + 1))
                path.chmod(0o644 if kind == "mode" else 0o600)
            count = len(self.calls)
            with self.subTest(kind=kind):
                result = await self.observe(captured["record_sha256"])
                self.assertIn(result["state"], {"unavailable", "unverifiable"})
                self.assertIsNone(result["retained"])
            self.assertEqual(len(self.calls), count)
            path.unlink()
            target.unlink()
            path.write_bytes(original)
            path.chmod(0o600)

    async def test_store_directory_identity_and_permissions_are_prebound(self):
        captured = await self.capture()
        self.root.chmod(0o755)
        self.no_body(await self.observe(captured["record_sha256"]), "unverifiable")
        self.root.chmod(0o700)
        prior = self.root.with_name(self.root.name + "-disposable-old")
        self.root.rename(prior)
        self.root.mkdir(mode=0o700)
        try:
            self.no_body(await self.observe(captured["record_sha256"]), "unverifiable")
        finally:
            self.root.rmdir()
            prior.rename(self.root)

    async def test_only_selected_metadata_is_retained_from_a_multi_entry_receipt(self):
        value = e.decode(self.raw)
        other = copy.deepcopy(value["rows"][0])
        other["context_id"] = "0" * 32
        value["rows"].append(other)
        value["counts"]["reconciled_metadata"] = 2
        raw = handoff.reseal(value)
        captured = await self.capture(raw=raw)
        self.assertEqual(captured["state"], "retained")
        record = self.decrypt((self.root / (RECORD + ".receipt")).read_bytes())
        self.assertNotIn(other["context_id"], e.encode(record).decode())
        self.assertEqual(record["handoff"]["source"]["receipt_sha256"], e.sha(raw))
        self.assertEqual(record["handoff"]["source"]["row"], value["rows"][0])

    async def test_authorization_loss_at_every_capture_boundary_publishes_nothing(self):
        for fail_at in range(1, 8):
            count = 0
            async def authorize():
                nonlocal count
                count += 1
                if count == fail_at:
                    raise PermissionError("private-marker")
                return ACTOR
            with self.subTest(boundary=fail_at):
                self.no_body(await self.capture(reader=self.reader(authorize)), "denied")
            self.assertEqual(list(self.root.iterdir()), [])

    async def test_authorization_loss_at_every_reobservation_boundary_releases_no_cached_body(self):
        captured = await self.capture()
        path = self.root / (RECORD + ".receipt")
        original = path.read_bytes()
        for fail_at in range(1, 7):
            count = 0
            async def authorize():
                nonlocal count
                count += 1
                if count == fail_at:
                    raise PermissionError("private-marker")
                return ACTOR
            with self.subTest(boundary=fail_at):
                self.no_body(await self.observe(captured["record_sha256"], reader=self.reader(authorize)), "denied")
            self.assertEqual(path.read_bytes(), original)

    async def test_changed_source_context_and_read_pairs_preserve_historical_ciphertext(self):
        captured = await self.capture()
        path = self.root / (RECORD + ".receipt")
        original = path.read_bytes()
        old = self.decrypt(original)["handoff"]
        for kind, state in (("source", "source_changed"), ("context", "context_changed"), ("pair", "changed_between_reads")):
            view = source.wire(changed=kind == "source")
            if kind == "context":
                view["context_sha256"] = "0" * 64
                view["plan_sha256"] = e.sha(e.encode({"schema": "joint-recovery-plan-v1", **{k: view[k] for k in inventory.PLAN}}))
                view["view_sha256"] = e.sha(e.encode({k: v for k, v in view.items() if k != "view_sha256"}))
            async def read(action, body):
                return 200, source.encoded(source.wire(changed=action == "joint_finish_observe") if kind == "pair" else view, action)
            with self.subTest(kind=kind):
                result = await self.observe(captured["record_sha256"], reader=self.reader(read=read))
                self.assertEqual(result["state"], state)
                self.assertEqual(result["retained"], old)
                self.assertEqual(result["comparison"]["outcome"], "changed_metadata")
                self.assertEqual(path.read_bytes(), original)

    async def test_timeout_and_cancellation_leave_retained_records_exact(self):
        async def slow():
            await asyncio.sleep(1)
            return ACTOR
        with patch.object(inventory, "TOTAL_SECONDS", .02):
            self.no_body(await self.capture(reader=self.reader(slow)), "budget_exhausted")
        self.assertEqual(list(self.root.iterdir()), [])
        captured = await self.capture()
        original = (self.root / (RECORD + ".receipt")).read_bytes()
        with patch.object(inventory, "TOTAL_SECONDS", .02):
            self.no_body(await self.observe(captured["record_sha256"], reader=self.reader(slow)), "budget_exhausted")
        async def cancelled():
            raise asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await self.observe(captured["record_sha256"], reader=self.reader(cancelled))
        self.assertEqual((self.root / (RECORD + ".receipt")).read_bytes(), original)

    async def test_destination_errors_discard_history_and_never_retry(self):
        captured = await self.capture()
        for status, state in ((403, "denied"), (409, "conflict"), (502, "unavailable"), (200, "unverifiable")):
            calls = []
            async def read(action, body):
                calls.append(action)
                return status, b'{"private-marker":true}'
            with self.subTest(status=status):
                self.no_body(await self.observe(captured["record_sha256"], reader=self.reader(read=read)), state)
            self.assertEqual(len(calls), 1)

    async def test_uncertain_durability_preserves_published_record_without_retry(self):
        actual, count = os.fsync, 0
        def fail_directory(fd):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("private-marker")
            return actual(fd)
        with patch.object(p.os, "fsync", side_effect=fail_directory):
            self.no_body(await self.capture(), "retention_uncertain")
        path = self.root / (RECORD + ".receipt")
        original = path.read_bytes()
        self.assertEqual([x.name for x in self.root.iterdir()], [path.name])
        self.no_body(await self.capture(), "conflict")
        self.assertEqual(path.read_bytes(), original)
        result = await self.observe(e.sha(original))  # Independently pinned by the disposable operator after inspection.
        self.assertEqual(result["state"], "reconciled_metadata")

    async def test_wrong_actor_is_denied_before_file_access_and_key_repr_is_redacted(self):
        captured = await self.capture()
        async def other():
            return "0" * 64
        with patch.object(p, "_read", side_effect=AssertionError("File access before authorization")):
            self.no_body(await self.observe(captured["record_sha256"], reader=self.reader(other)), "denied")
        self.assertNotIn(repr(self.key), repr(self.store))
        self.assertNotIn(self.key.hex(), repr(self.store))
        with self.assertRaises(ValueError):
            await self.capture(record="../private-marker")

    async def test_decrypted_closed_schema_and_metadata_binding_are_still_verified(self):
        await self.capture()
        path = self.root / (RECORD + ".receipt")
        original = path.read_bytes()
        for kind in ("extra", "flag", "plan", "selection", "comparison", "state"):
            record = self.decrypt(original)
            old = record["handoff"]
            if kind == "extra":
                record["private-marker"] = True
            elif kind == "flag":
                old["authority_renewed"] = True
            elif kind == "plan":
                old["destination"]["row"]["observations"][0]["plan_sha256"] = "0" * 64
            elif kind == "selection":
                old["selection"]["context_id"] = "0" * 32
            elif kind == "comparison":
                old["comparison"]["changed_fields"] = ["private-marker"]
            else:
                old["state"] = "denied"
            record["handoff_sha256"] = e.sha(e.encode(old))
            nonce = os.urandom(12)
            raw = p.MAGIC + nonce + AESGCM(self.key).encrypt(nonce, e.encode(record), p._aad(self.store, RECORD))
            path.write_bytes(raw)
            before = len(self.calls)
            with self.subTest(kind=kind):
                self.no_body(await self.observe(e.sha(raw)), "unverifiable")
            self.assertEqual(len(self.calls), before)
        path.write_bytes(original)

    async def test_record_changed_during_destination_reads_releases_no_cached_history(self):
        captured = await self.capture()
        path = self.root / (RECORD + ".receipt")
        original = path.read_bytes()
        async def read(action, body):
            if action == "joint_observe":
                path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
            return await self.read(action, body)
        self.no_body(await self.observe(captured["record_sha256"], reader=self.reader(read=read)), "unverifiable")
        self.assertNotEqual(path.read_bytes(), original)  # Never silently repair externally altered history.
        path.write_bytes(original)  # Disposable test cleanup, outside the adapter.


class ReceiptControllerTests(unittest.IsolatedAsyncioTestCase):
    setUp = retained.AuthenticatedOperatorContracts.setUp
    tearDown = retained.AuthenticatedOperatorContracts.tearDown
    readonly = retained.AuthenticatedOperatorContracts.readonly

    async def exercise(self, mode):
        with self.readonly():
            f = fixture.Fixture("C01_retirement_ordered" if mode == "retirement" else "C09_rollback_ordered",
                                self.models, self.work, self.anchors, self.api)
            clients = [httpx.AsyncClient(transport=httpx.ASGITransport(app=s), base_url="http://operator.invalid") for s in f.services]
            try:
                a, b = clients[:2]
                await f.setup_joint(a, b)
                first = (await f.observe_joint(a)).json()
                actor = e.sha(e.encode(f.authority.snapshot(f.session_ids["preparer"], f.ids["preparer"], "preparer", now=f.now)))
                request = {"context_id": CONTEXT, "change_id": f.change_id, "expected_context_sha256": first["context_sha256"]}
                async def authorize():
                    try:
                        return e.sha(e.encode(f.authority.snapshot(f.session_ids["preparer"], f.ids["preparer"], "preparer", now=f.now)))
                    except Exception:
                        raise PermissionError from None
                calls = []
                async def read(action, body):
                    calls.append(action)
                    response = await fixture.raw.Fixture.request(f, a, action, "preparer", body)
                    return response.status_code, response.content
                reader = inventory.BoundReader(scope_sha256=first["scope_sha256"], authorize=authorize, read=read)
                raw = e.encode(await inventory.collect({CONTEXT: reader}, [request], actor_sha256=actor))
                store_root = self.root / "receipts"
                store_root.mkdir(mode=0o700)
                store = p.ReceiptStore(root=store_root, context_id=CONTEXT, scope_sha256=first["scope_sha256"], key=AESGCM.generate_key(bit_length=256))
                before = f.four_histories()
                ack = await p.retain(raw, e.sha(raw), request, store, reader, actor_sha256=actor, record_id=RECORD)
                self.assertEqual(ack["state"], "retained")
                self.assertEqual(f.four_histories(), before)
                path = store_root / (RECORD + ".receipt")
                ciphertext = path.read_bytes()
                outcomes = []
                async def check(state, outcome=None, bound=reader):
                    before = f.four_histories()
                    result = await p.reobserve(store, bound, RECORD, ack["record_sha256"], actor_sha256=actor)
                    self.assertEqual(result["state"], state)
                    if outcome:
                        self.assertEqual(result["comparison"]["outcome"], outcome)
                        self.assertEqual(result["retained"]["source"]["receipt_sha256"], e.sha(raw))
                    else:
                        self.assertIsNone(result["retained"])
                        self.assertIsNone(result["current"])
                    self.assertFalse(any(result[k] for k in inventory.FLAGS))
                    self.assertEqual(result["review_validity"], "unassessed")
                    self.assertEqual(f.four_histories(), before)
                    self.assertEqual(path.read_bytes(), ciphertext)
                    outcomes.append(state)
                await check("pending_anchors", "unchanged_metadata")
                await check("pending_anchors", "unchanged_metadata")
                for state in ("pending_anchors", "reconciled_metadata"):
                    view = (await f.observe_joint(a)).json()
                    self.assertEqual((await f.apply_joint(a, view)).status_code, 200)
                    await check(state, "changed_metadata")
                f.login("other")
                async def wrong_read(action, body):
                    calls.append(action)
                    response = await fixture.raw.Fixture.request(f, a, action, "other", body)
                    return response.status_code, response.content
                await check("denied", bound=inventory.BoundReader(scope_sha256=first["scope_sha256"], authorize=authorize, read=wrong_read))
                if mode == "retirement":
                    f.revoke("reviewer")
                    await check("reconciled_metadata", "changed_metadata")
                    self.assertEqual((await f.inventory(a)).status_code, 409)
                    f.advance(301)
                else:
                    await f.withdrawal(a, b)
                await check("source_changed", "changed_metadata")
                f.revoke("preparer")
                count = len(calls)
                await check("denied")
                self.assertEqual(len(calls), count)
                self.assertTrue(set(calls) <= {"joint_observe", "joint_finish_observe"})
                print("PRIVATE_RECEIPT_CASE " + json.dumps({"mode": mode, "retentions": 1, "reobservations": len(outcomes),
                      "HTTP_reads_including_source_collection": len(calls), "outcomes": outcomes,
                      "exact_ciphertext_source_and_four_histories_preserved": True, "review_validity": "unassessed"}))
            finally:
                await asyncio.gather(*(c.aclose() for c in clients))
                f.close()

    async def test_disposable_retirement_retention_reopen_expiry_and_revocation(self):
        await self.exercise("retirement")

    async def test_disposable_rollback_retention_reopen_withdrawal_and_revocation(self):
        await self.exercise("rollback")


share_immutable_assets(ReceiptControllerTests)
