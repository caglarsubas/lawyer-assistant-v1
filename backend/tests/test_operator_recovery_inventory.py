"""Fresh disposable selections; the original deployment inventory stays exact."""

import asyncio
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
import operator_recovery_inventory as inventory  # noqa: E402
import test_authenticated_operator_review as retained  # noqa: E402
from campaign_test_assets import share_immutable_assets  # noqa: E402

ACTOR, CONTEXT, SCOPE, CHANGE = "a" * 64, "b" * 32, "c" * 64, "d" * 32
REQUEST = {"context_id": CONTEXT, "change_id": CHANGE, "expected_context_sha256": "e" * 64}


def wire(*, changed=False):
    value = {k + "_sha256": "f" * 64 for k in ("window_head", "window_tip", "destination_head", "destination_tip",
             "namespace_head", "legacy_head", "revocation_head", "history", "finish")}
    value.update(target="window", change_id=CHANGE, scope_sha256=SCOPE, actor_sha256=ACTOR,
                 context_sha256="e" * 64, phase="finished", finish_state="anchored", pending={},
                 current_source_matches=True, next_target=None, progress="reconciled")
    if changed:
        value["revocation_head_sha256"] = "0" * 64
        value["current_source_matches"] = False
    plan_keys = ("change_id", "window_tip_sha256", "destination_tip_sha256", "namespace_head_sha256",
                 "legacy_head_sha256", "revocation_head_sha256", "context_sha256", "history_sha256",
                 "scope_sha256", "actor_sha256", "finish_sha256")
    value["plan_sha256"] = e.sha(e.encode({"schema": "joint-recovery-plan-v1", **{k: value[k] for k in plan_keys}}))
    value["view_sha256"] = e.sha(e.encode(value))
    return value


def encoded(view, action):
    return e.encode({**view, "status": "joint_context_observed" if action == "joint_observe" else
                     "joint_finish_reconciled_readonly", **dict.fromkeys(e.FLAGS | {"authority_renewed", "atomic_joint_write"}, False)})


class InventoryInputTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.calls, self.authorizations = [], 0

    async def authorize(self):
        self.authorizations += 1
        return ACTOR

    def reader(self, read):
        return inventory.BoundReader(scope_sha256=SCOPE, authorize=self.authorize, read=read)

    async def stable(self, action, body):
        self.calls.append((action, body))
        return 200, encoded(wire(), action)

    async def test_explicit_order_exact_finish_pins_and_no_registry_enumeration(self):
        async def forbidden(*args):
            self.fail("Unselected context was inspected")
        result = await inventory.collect({CONTEXT: self.reader(self.stable), "0" * 32: self.reader(forbidden)},
                                         [REQUEST], actor_sha256=ACTOR)
        self.assertEqual(result["counts"], {"reconciled_metadata": 1})
        self.assertFalse(result["atomic_snapshot"])
        self.assertFalse(result["current_authority_assessed"])
        self.assertEqual(result["rows"][0]["review_validity"], "unassessed")
        self.assertEqual(self.authorizations, 3)
        self.assertEqual([a for a, _ in self.calls], ["joint_observe", "joint_finish_observe"])
        self.assertEqual(self.calls[1][1], {"change_id": CHANGE, **{"expected_" + k: wire()[k] for k in
                                                            ("plan_sha256", "view_sha256", "finish_sha256")}})
        self.assertEqual(result["inventory_sha256"], e.sha(e.encode({k: v for k, v in result.items() if k != "inventory_sha256"})))

    async def test_closed_unique_bounded_selections_fail_before_any_read(self):
        for requests in ([], [REQUEST] * 2, [REQUEST] * 9, [{**REQUEST, "path": "/private"}],
                         [{**REQUEST, "context_id": "other"}], [{**REQUEST, "expected_context_sha256": True}]):
            with self.subTest(requests=requests), self.assertRaises(ValueError):
                await inventory.collect({CONTEXT: self.reader(self.stable)}, requests, actor_sha256=ACTOR)
        self.assertEqual(self.calls, [])

    async def test_unknown_context_does_not_probe_registered_context(self):
        result = await inventory.collect({CONTEXT: self.reader(self.stable)},
                                         [{**REQUEST, "context_id": "0" * 32}], actor_sha256=ACTOR)
        self.assertEqual(result["counts"], {"unavailable": 1})
        self.assertEqual(self.calls, [])
        self.assertEqual(self.authorizations, 0)

    async def test_malformed_foreign_or_unverifiable_responses_never_publish_metadata(self):
        for kind in ("actor", "scope", "change", "extra", "flag", "plan", "view", "pending", "bool", "oversize", "duplicate"):
            async def bad(action, body):
                value = e.decode(encoded(wire(), action))
                if kind in {"actor", "scope", "change"}:
                    key = {"actor": "actor_sha256", "scope": "scope_sha256", "change": "change_id"}[kind]
                    value[key] = "0" * (32 if kind == "change" else 64)
                elif kind == "extra":
                    value["credential"] = "invented-private-marker"
                elif kind == "flag":
                    value["production_activation"] = True
                elif kind in {"plan", "view"}:
                    value[kind + "_sha256"] = "0" * 64
                elif kind == "pending":
                    value["pending"] = {"window": {"kind": "finished", "event_sha256": "0" * 64}}
                elif kind == "bool":
                    value["current_source_matches"] = 1
                return 200, b"x" * 32769 if kind == "oversize" else b'{"status":0,"status":1}' if kind == "duplicate" else e.encode(value)
            with self.subTest(kind=kind):
                result = await inventory.collect({CONTEXT: self.reader(bad)}, [REQUEST], actor_sha256=ACTOR)
                self.assertEqual(result["counts"], {"unverifiable": 1})
                self.assertEqual(result["rows"][0]["observations"], [])
                self.assertNotIn("invented-private-marker", str(result))

    async def test_denial_conflict_and_errors_discard_prior_body_without_retry(self):
        for status, expected in ((403, "denied"), (409, "conflict"), (502, "unavailable")):
            calls = []
            async def read(action, body):
                calls.append(action)
                return (200, encoded(wire(), action)) if len(calls) == 1 else (status, b"invented-private-error")
            result = await inventory.collect({CONTEXT: self.reader(read)}, [REQUEST], actor_sha256=ACTOR)
            self.assertEqual(result["counts"], {expected: 1})
            self.assertEqual(result["rows"][0]["observations"], [])
            self.assertEqual(len(calls), 2)

    async def test_changed_heads_are_two_observations_not_a_merged_snapshot(self):
        async def read(action, body):
            return 200, encoded(wire(changed=action == "joint_finish_observe"), action)
        result = await inventory.collect({CONTEXT: self.reader(read)}, [REQUEST], actor_sha256=ACTOR)
        self.assertEqual(result["counts"], {"changed_between_reads": 1})
        self.assertEqual(len(result["rows"][0]["observations"]), 2)

    async def test_fresh_final_authorization_and_cancellation(self):
        async def authority():
            self.authorizations += 1
            return ACTOR if self.authorizations < 3 else "0" * 64
        reader = inventory.BoundReader(scope_sha256=SCOPE, authorize=authority, read=self.stable)
        result = await inventory.collect({CONTEXT: reader}, [REQUEST], actor_sha256=ACTOR)
        self.assertEqual(result["counts"], {"denied": 1})
        self.assertEqual(result["rows"][0]["observations"], [])
        async def cancelled(action, body):
            raise asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await inventory.collect({CONTEXT: self.reader(cancelled)}, [REQUEST], actor_sha256=ACTOR)

    async def test_aggregate_deadline_stops_remaining_contexts(self):
        async def slow(action, body):
            self.calls.append(action)
            if action == "joint_finish_observe":
                await asyncio.sleep(1)
            return 200, encoded(wire(), action)
        with patch.object(inventory, "TOTAL_SECONDS", .03):
            result = await inventory.collect({CONTEXT: self.reader(slow)},
                                             [REQUEST, {**REQUEST, "change_id": "0" * 32}], actor_sha256=ACTOR)
        self.assertEqual(result["counts"], {"partial": 1, "budget_exhausted": 1})
        self.assertEqual(self.calls, ["joint_observe", "joint_finish_observe"])


class InventoryControllerTests(unittest.IsolatedAsyncioTestCase):
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
                actor = e.sha(e.encode(f.authority.snapshot(f.session_ids["preparer"], f.ids["preparer"], "preparer", now=f.now)))
                first = (await f.observe_joint(a)).json()
                request = {"context_id": CONTEXT, "change_id": f.change_id, "expected_context_sha256": first["context_sha256"]}
                async def authorize():
                    try:
                        return e.sha(e.encode(f.authority.snapshot(f.session_ids["preparer"], f.ids["preparer"], "preparer", now=f.now)))
                    except Exception:
                        raise PermissionError("Disposable session unavailable") from None
                calls = []
                async def read(action, body):
                    calls.append(action)
                    response = await fixture.raw.Fixture.request(f, a, action, "preparer", body)
                    return response.status_code, response.content
                readers = {CONTEXT: inventory.BoundReader(scope_sha256=first["scope_sha256"], authorize=authorize, read=read)}
                outcomes = []
                async def collect_for(registry, selected_actor, selection=request):
                    result = await inventory.collect(registry, [selection], actor_sha256=selected_actor)
                    outcomes.append(next(iter(result["counts"])))
                    return result
                async def check(expected, selection=request):
                    before = f.four_histories()
                    result = await collect_for(readers, actor, selection)
                    self.assertEqual(result["counts"], {expected: 1})
                    self.assertEqual(before, f.four_histories())
                    self.assertFalse(any(result[k] for k in inventory.FLAGS))
                    self.assertEqual(result["rows"][0]["review_validity"], "unassessed")
                    return result
                await check("pending_anchors")
                f.login("other")
                other = e.sha(e.encode(f.authority.snapshot(f.session_ids["other"], f.ids["other"], "reviewer", now=f.now)))
                async def other_authorize():
                    return e.sha(e.encode(f.authority.snapshot(f.session_ids["other"], f.ids["other"], "reviewer", now=f.now)))
                async def other_read(action, body):
                    calls.append(action)
                    response = await fixture.raw.Fixture.request(f, a, action, "other", body)
                    return response.status_code, response.content
                other_reader = inventory.BoundReader(scope_sha256=first["scope_sha256"], authorize=other_authorize, read=other_read)
                before = f.four_histories()
                unrelated = await collect_for({CONTEXT: other_reader}, other)
                self.assertEqual(unrelated["counts"], {"denied": 1})  # Controller assignment rejects unrelated users first.
                self.assertEqual(unrelated["rows"][0]["observations"], [])
                self.assertEqual(f.four_histories(), before)
                # An external actor advances one admitted anchor between the two
                # reads; the collector itself may send only the read operations.
                external = []
                async def raced_read(action, body):
                    response = await read(action, body)
                    if action == "joint_observe":
                        view = e.decode(response[1])
                        self.assertEqual((await f.apply_joint(a, view)).status_code, 200)
                        external.append(f.four_histories())
                    return response
                raced_reader = inventory.BoundReader(scope_sha256=first["scope_sha256"], authorize=authorize, read=raced_read)
                race = await collect_for({CONTEXT: raced_reader}, actor)
                self.assertEqual(race["counts"], {"conflict": 1})
                self.assertEqual(race["rows"][0]["observations"], [])
                self.assertEqual(len(external), 1)
                self.assertEqual(f.four_histories(), external[0])
                await check("pending_anchors")
                view = (await f.observe_joint(a)).json()
                self.assertEqual((await f.apply_joint(a, view)).status_code, 200)
                await check("reconciled_metadata")
                await check("context_changed", {**request, "expected_context_sha256": "0" * 64})
                if mode == "retirement":
                    f.revoke("reviewer")
                    await check("reconciled_metadata")  # Retained metadata does not validate current independent review.
                    self.assertEqual((await f.inventory(a)).status_code, 409)  # The retired-reader fence remains in force.
                    f.advance(301)
                    await check("source_changed")  # Expiry changes the current basis without rewriting retained history.
                    count = len(calls)
                    f.revoke("preparer")
                    await check("denied")
                    self.assertEqual(len(calls), count)
                else:
                    await f.withdrawal(a, b)
                    await check("source_changed")
                self.assertTrue(set(calls) <= {"joint_observe", "joint_finish_observe"})
                print("OPERATOR_INVENTORY_CASE " + json.dumps({"mode": mode, "collections": len(outcomes),
                    "collection_HTTP_reads": len(calls), "outcomes": outcomes, "history_preserved": True,
                    "external_race_repairs": len(external), "current_authority_assessed": False}))
            finally:
                await asyncio.gather(*(c.aclose() for c in clients))
                f.close()

    async def test_disposable_retirement_and_revoked_review_preserve_histories(self):
        await self.exercise("retirement")

    async def test_disposable_rollback_successor_and_withdrawal_preserve_histories(self):
        await self.exercise("rollback")


share_immutable_assets(InventoryControllerTests)
