"""Fresh private receipt selection and authenticated disposable destination reads."""

import asyncio
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "deploy")]
import mode_recovery_fixture as fixture  # noqa: E402
import operator_enrollment_evidence as e  # noqa: E402
import operator_inventory_handoff as h  # noqa: E402
import operator_recovery_inventory as inventory  # noqa: E402
import test_authenticated_operator_review as retained  # noqa: E402
import test_operator_recovery_inventory as source  # noqa: E402
from campaign_test_assets import share_immutable_assets  # noqa: E402

ACTOR, CONTEXT, SCOPE, REQUEST = source.ACTOR, source.CONTEXT, source.SCOPE, source.REQUEST


def receipt():
    row = {**REQUEST, "state": "reconciled_metadata", "first_read_completed": True,
           "review_validity": "unassessed", "observations": [source.wire(), source.wire()]}
    value = {"schema": "operator-recovery-inventory-v1", "actor_sha256": ACTOR, "metadata_only": True,
             "atomic_snapshot": False, "current_authority_assessed": False,
             "counts": {"reconciled_metadata": 1}, "rows": [row], **dict.fromkeys(inventory.FLAGS, False)}
    return reseal(value)


def reseal(value):
    value["inventory_sha256"] = e.sha(e.encode({k: v for k, v in value.items() if k != "inventory_sha256"}))
    return e.encode(value)


class HandoffInputTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.calls, self.auths = [], 0
        self.raw = receipt()

    async def authorize(self):
        self.auths += 1
        return ACTOR

    async def read(self, action, body):
        self.calls.append((action, body))
        return 200, source.encoded(source.wire(), action)

    def readers(self, *, authorize=None, read=None, scope=SCOPE):
        return {CONTEXT: inventory.BoundReader(scope_sha256=scope, authorize=authorize or self.authorize, read=read or self.read)}

    async def run_handoff(self, *, raw=None, request=None, readers=None, actor=ACTOR, expected=None):
        raw = self.raw if raw is None else raw
        return await h.handoff(raw, e.sha(raw) if expected is None else expected, REQUEST if request is None else request,
                               self.readers() if readers is None else readers, actor_sha256=actor)

    def no_body(self, result, state):
        self.assertEqual(result["state"], state)
        self.assertIsNone(result["source"])
        self.assertIsNone(result["destination"])
        self.assertIsNone(result["comparison"])
        self.assertNotIn("private-marker", str(result))

    async def test_exact_receipt_and_fresh_pinned_reads_do_not_confer_authority(self):
        result = await self.run_handoff()
        self.assertEqual(self.raw, receipt())
        self.assertEqual(result["state"], "reconciled_metadata")
        self.assertEqual(result["source"]["row"], e.decode(self.raw)["rows"][0])
        self.assertEqual(result["source"]["receipt_sha256"], e.sha(self.raw))
        self.assertEqual(result["comparison"], {"outcome": "unchanged_metadata", "changed_fields": []})
        self.assertEqual(self.auths, 5)
        self.assertEqual([a for a, _ in self.calls], ["joint_observe", "joint_finish_observe"])
        self.assertEqual(self.calls[1][1], {"change_id": REQUEST["change_id"], **{"expected_" + k: source.wire()[k] for k in
                                                      ("plan_sha256", "view_sha256", "finish_sha256")}})
        self.assertFalse(result["atomic_snapshot"])
        self.assertFalse(result["current_authority_assessed"])
        self.assertFalse(any(result[k] for k in inventory.FLAGS))
        self.assertEqual(result["review_validity"], "unassessed")

    async def test_selected_entry_only_no_registry_expansion_or_unselected_metadata(self):
        value = e.decode(self.raw)
        other = copy.deepcopy(value["rows"][0])
        other["context_id"] = "0" * 32
        value["rows"].append(other)
        value["counts"]["reconciled_metadata"] = 2
        async def forbidden(*args):
            self.fail("Unselected destination was inspected")
        readers = self.readers()
        readers[other["context_id"]] = inventory.BoundReader(scope_sha256=SCOPE, authorize=forbidden, read=forbidden)
        result = await self.run_handoff(raw=reseal(value), readers=readers)
        self.assertEqual(result["source"]["row"]["context_id"], CONTEXT)
        self.assertNotIn(other["context_id"], e.encode(result).decode())
        self.assertEqual(len(self.calls), 2)

    async def test_request_is_snapshotted_before_authorization_yields(self):
        request = dict(REQUEST)
        async def authorize():
            request["context_id"] = "0" * 32
            request["change_id"] = "0" * 32
            return ACTOR
        result = await self.run_handoff(request=request, readers=self.readers(authorize=authorize))
        self.assertEqual(result["selection"], REQUEST)
        self.assertEqual(result["state"], "reconciled_metadata")
        self.assertEqual(self.calls[0][1], {"change_id": REQUEST["change_id"]})

    async def test_exact_bytes_closed_shapes_and_internal_bindings_fail_before_any_read(self):
        kinds = ("hash", "whitespace", "duplicate", "oversize", "flag", "extra", "inner_hash", "counts", "state",
                 "missing_observation", "scope", "actor", "context", "plan", "view", "observation_flag", "duplicate_row", "failed_row")
        for kind in kinds:
            value = e.decode(self.raw)
            row = value["rows"][0]
            raw, expected = None, None
            if kind == "hash":
                expected = "0" * 64
            elif kind == "whitespace":
                raw, expected = b" " + self.raw, e.sha(self.raw)
            elif kind == "duplicate":
                raw = b'{"schema":0,"schema":1}'
            elif kind == "oversize":
                raw = b"x" * (h.MAX_BYTES + 1)
            elif kind == "flag":
                value["authority_renewed"] = True
            elif kind == "extra":
                value["private-marker"] = "private-marker"
            elif kind == "inner_hash":
                value["inventory_sha256"] = "0" * 64
                raw = e.encode(value)
            elif kind == "counts":
                value["counts"] = {"reconciled_metadata": True}
            elif kind == "state":
                row["state"] = []
            elif kind == "missing_observation":
                row["observations"].pop()
            elif kind in {"scope", "actor", "plan", "view"}:
                row["observations"][0][kind + "_sha256"] = "0" * 64
            elif kind == "context":
                row["expected_context_sha256"] = "0" * 64
            elif kind == "observation_flag":
                row["observations"][0]["production_activation"] = True
            elif kind == "duplicate_row":
                value["rows"].append(copy.deepcopy(row))
                value["counts"]["reconciled_metadata"] = 2
            else:
                row.update(state="denied", observations=[])
                value["counts"] = {"denied": 1}
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                await self.run_handoff(raw=raw if raw is not None else reseal(value), expected=expected)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.auths, 0)

    async def test_explicit_destination_scope_actor_and_context_are_independent(self):
        with self.assertRaises(ValueError):
            await self.run_handoff(readers=self.readers(scope="0" * 64))
        with self.assertRaises(ValueError):
            await self.run_handoff(request={**REQUEST, "path": "/private-marker"})
        result = await self.run_handoff(actor="0" * 64)
        self.no_body(result, "denied")
        result = await self.run_handoff(readers={})
        self.no_body(result, "unavailable")
        self.assertEqual(self.calls, [])

    async def test_authorization_loss_at_each_boundary_returns_no_cached_body(self):
        for fail_at in range(1, 6):
            auths = 0
            async def authorize():
                nonlocal auths
                auths += 1
                if auths == fail_at:
                    raise PermissionError("private-marker")
                return ACTOR
            self.no_body(await self.run_handoff(readers=self.readers(authorize=authorize)), "denied")
        self.assertEqual(self.raw, receipt())

    async def test_denial_conflict_malformed_and_adapter_error_do_not_retry_or_leak(self):
        for kind, state in ((403, "denied"), (409, "conflict"), (502, "unavailable"), ("bad", "unverifiable"), ("error", "unavailable")):
            calls = 0
            async def read(action, body):
                nonlocal calls
                calls += 1
                if kind == "error":
                    raise RuntimeError("private-marker")
                return (200, b'{"private-marker":1}') if kind == "bad" else (kind, b"private-marker")
            self.no_body(await self.run_handoff(readers=self.readers(read=read)), state)
            self.assertEqual(calls, 1)

    async def test_changed_evidence_keeps_both_original_and_fresh_observations(self):
        async def read(action, body):
            return 200, source.encoded(source.wire(changed=True), action)
        result = await self.run_handoff(readers=self.readers(read=read))
        self.assertEqual(result["state"], "source_changed")
        self.assertEqual(result["comparison"]["outcome"], "changed_metadata")
        self.assertIn("revocation_head_sha256", result["comparison"]["changed_fields"])
        self.assertEqual(result["source"]["row"], e.decode(self.raw)["rows"][0])
        self.assertEqual(result["destination"]["row"]["observations"], [source.wire(changed=True)] * 2)

    async def test_changed_destination_context_is_explicit_not_silently_rebound(self):
        view = source.wire()
        view["context_sha256"] = "0" * 64
        plan = {"schema": "joint-recovery-plan-v1", **{k: view[k] for k in inventory.PLAN}}
        view["plan_sha256"] = e.sha(e.encode(plan))
        view["view_sha256"] = e.sha(e.encode({k: v for k, v in view.items() if k != "view_sha256"}))
        async def read(action, body):
            return 200, source.encoded(view, action)
        result = await self.run_handoff(readers=self.readers(read=read))
        self.assertEqual(result["state"], "context_changed")
        self.assertEqual(result["selection"], REQUEST)
        self.assertEqual(result["source"]["row"]["observations"][0]["context_sha256"], REQUEST["expected_context_sha256"])
        self.assertEqual(result["destination"]["row"]["observations"][0]["context_sha256"], "0" * 64)
        self.assertIn("context_sha256", result["comparison"]["changed_fields"])

    async def test_changed_destination_between_reads_keeps_two_distinct_observations(self):
        async def read(action, body):
            return 200, source.encoded(source.wire(changed=action == "joint_finish_observe"), action)
        result = await self.run_handoff(readers=self.readers(read=read))
        self.assertEqual(result["state"], "changed_between_reads")
        views = result["destination"]["row"]["observations"]
        self.assertNotEqual(views[0], views[1])
        self.assertEqual(views[0], source.wire())
        self.assertEqual(views[1], source.wire(changed=True))
        self.assertEqual(result["source"]["row"], e.decode(self.raw)["rows"][0])

    async def test_deadline_and_cancellation_discard_metadata(self):
        async def slow():
            await asyncio.sleep(1)
            return ACTOR
        with patch.object(inventory, "TOTAL_SECONDS", .02):
            self.no_body(await self.run_handoff(readers=self.readers(authorize=slow)), "budget_exhausted")
        async def cancelled():
            raise asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await self.run_handoff(readers=self.readers(authorize=cancelled))


class HandoffControllerTests(unittest.IsolatedAsyncioTestCase):
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
                readers = {CONTEXT: inventory.BoundReader(scope_sha256=first["scope_sha256"], authorize=authorize, read=read)}
                raw = e.encode(await inventory.collect(readers, [request], actor_sha256=actor))
                source_hash = e.sha(raw)
                outcomes = []
                async def check(state, outcome=None, registry=readers):
                    before = f.four_histories()
                    result = await h.handoff(raw, source_hash, request, registry, actor_sha256=actor)
                    self.assertEqual(result["state"], state)
                    if outcome:
                        self.assertEqual(result["comparison"]["outcome"], outcome)
                        self.assertEqual(result["source"]["row"], e.decode(raw)["rows"][0])
                    else:
                        self.assertIsNone(result["source"])
                        self.assertIsNone(result["destination"])
                    self.assertFalse(any(result[k] for k in inventory.FLAGS))
                    self.assertEqual(result["review_validity"], "unassessed")
                    self.assertEqual(e.sha(raw), source_hash)
                    self.assertEqual(f.four_histories(), before)
                    outcomes.append(state)
                    return result
                await check("pending_anchors", "unchanged_metadata")
                view = (await f.observe_joint(a)).json()
                self.assertEqual((await f.apply_joint(a, view)).status_code, 200)
                await check("pending_anchors", "changed_metadata")
                view = (await f.observe_joint(a)).json()
                self.assertEqual((await f.apply_joint(a, view)).status_code, 200)
                await check("reconciled_metadata", "changed_metadata")
                # Fresh checks remain mandatory even when the source bytes are exact.
                f.login("other")
                async def wrong_read(action, body):
                    calls.append(action)
                    response = await fixture.raw.Fixture.request(f, a, action, "other", body)
                    return response.status_code, response.content
                await check("denied", registry={CONTEXT: inventory.BoundReader(scope_sha256=first["scope_sha256"], authorize=authorize, read=wrong_read)})
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
                print("OPERATOR_HANDOFF_CASE " + json.dumps({"mode": mode, "handoffs": len(outcomes),
                      "HTTP_reads_including_source_collection": len(calls), "outcomes": outcomes,
                      "exact_receipt_and_histories_preserved": True, "review_validity": "unassessed"}))
            finally:
                await asyncio.gather(*(c.aclose() for c in clients))
                f.close()

    async def test_disposable_retirement_destination_freshness_and_revocation(self):
        await self.exercise("retirement")

    async def test_disposable_rollback_destination_freshness_and_withdrawal(self):
        await self.exercise("rollback")


share_immutable_assets(HandoffControllerTests)
