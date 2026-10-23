"""Independent authority, restored-store, runtime-pin and ambiguous-crash guards."""

import copy
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from campaign_authority import CampaignAuthority, validate_pin  # noqa: E402
from campaign_authority_cases import CASES, runtime_pin  # noqa: E402
from durable_packet_campaign import CampaignLedger  # noqa: E402
from evaluate_campaign_authority import evaluate  # noqa: E402
from evaluate_durable_campaign import approve_fixture, fixture  # noqa: E402
from offline_quotation_boundaries import sha  # noqa: E402

CHILD = """
import sys,json,os
from pathlib import Path
sys.path[:0]=[sys.argv[1]+'/scripts',sys.argv[1]+'/backend']
from campaign_authority import CampaignAuthority
from durable_packet_campaign import CampaignLedger
v=json.load(sys.stdin)
a=CampaignAuthority(Path(v['authority_path']),expected_authority_id=v['authority_id'])
l=CampaignLedger(Path(v['ledger_path']),expected_store_id=v['ledger_id'])
if v['crash']=='before_campaign':l.reserve=lambda *args,**kwargs:os._exit(75)
if v['crash']=='after_campaign':a._finish=lambda *args,**kwargs:os._exit(76)
try:a.reserve(l,v['spec'],'P1',authorize=lambda *_:True,observe=lambda:v['pin'])
except ValueError:sys.exit(42)
"""


class CampaignAuthorityContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.ledger = CampaignLedger.create(self.root / "campaign.sqlite")
        self.authority = CampaignAuthority.create(self.root / "authority.sqlite")
        self.sources, self.plan, self.allowance, self.grant = fixture(CASES[1], 2)
        self.pin, self.intent = runtime_pin(), "20000000-0000-4000-8000-000000000001"
        self.ledger.admit(self.grant, authorize=approve_fixture)
        self.spec = self.authority.register(self.intent, self.ledger, self.grant, self.pin, authorize=approve_fixture, observe=self.observe)

    def tearDown(self):
        self.temp.cleanup()

    def observe(self):
        return copy.deepcopy(self.pin)

    def reopen(self):
        return CampaignAuthority(self.authority._store.path, expected_authority_id=self.authority.authority_id)

    def reserve(self, packet="P1", authority=None, observe=None, authorize=approve_fixture):
        return (authority or self.authority).reserve(self.ledger, self.spec, packet, authorize=authorize, observe=observe or self.observe)

    def receipt(self):
        return self.reopen().receipt(self.spec, authorize=approve_fixture)

    def test_frozen_mock_report_and_exact_copies(self):
        r = evaluate()
        self.assertEqual(r, evaluate())
        self.assertEqual(r["summary"], {"cases": 6, "mock_metadata_requests": 6, "mock_completion_requests": 6,
                                      "no_candidate_cases": 2, "all_copies_exact": True})
        self.assertEqual(r["native_inference_calls"], 0)
        self.assertFalse(r["live_identity_or_native_legal_capacity_qualification"])

    def test_complete_immutable_identity_required_and_every_pin_change_blocks(self):
        for field in self.pin:
            altered = copy.deepcopy(self.pin)
            if isinstance(altered[field], bool):
                altered[field] = False
            elif isinstance(altered[field], int):
                altered[field] += 1
            else:
                altered[field] = sha("other") if field.endswith("sha256") else "other"
            with self.assertRaises(ValueError):
                self.reserve(observe=lambda: altered)
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 0)
        for bad in ({}, {**self.pin, "model_digest_sha256": None}, {**self.pin, "format": "gguf"},
                    {**self.pin, "api_key": "MUST-NOT-BE-ACCEPTED"}, {**self.pin, "application_context_units": True}):
            with self.assertRaises(ValueError):
                validate_pin(bad, 8192)

    def test_one_use_intent_cannot_be_replaced_by_another_grant_or_epoch(self):
        _, _, _, other = fixture(CASES[0], 91)
        self.ledger.admit(other, authorize=approve_fixture)
        with self.assertRaises(ValueError):
            self.reopen().register(self.intent, self.ledger, other, self.pin, authorize=approve_fixture, observe=self.observe)
        self.authority.fence_restore(self.ledger.store_id, authorize=approve_fixture)
        with self.assertRaises(ValueError):
            self.reopen().register(self.intent, self.ledger, other, self.pin, authorize=approve_fixture, observe=self.observe)
        with self.assertRaises(ValueError):
            self.reopen().register(str(uuid.uuid4()), self.ledger, self.grant, self.pin, authorize=approve_fixture, observe=self.observe)

    def test_ledger_rollback_detected_even_for_a_different_unspent_packet(self):
        snapshot = self.root / "before.sqlite"
        shutil.copyfile(self.ledger.path, snapshot)
        self.reserve()
        shutil.copyfile(snapshot, self.ledger.path)
        with self.assertRaises(ValueError):
            self.reserve("P2", authority=self.reopen())
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 1)

    def test_restore_epoch_survives_reopen_and_fences_all_old_intents(self):
        fence = self.authority.fence_restore(self.ledger.store_id, authorize=approve_fixture)
        self.assertEqual((fence["previous_epoch"], fence["next_epoch"]), (1, 2))
        with self.assertRaises(ValueError):
            self.reserve(authority=self.reopen())
        self.assertTrue(self.receipt()["fenced"])
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 0)

    def test_fresh_issuer_intent_after_fence_requires_new_grant_and_approval(self):
        self.authority.fence_restore(self.ledger.store_id, authorize=approve_fixture)
        _, _, _, new_grant = fixture(CASES[0], 92)
        self.ledger.admit(new_grant, authorize=approve_fixture)
        intent = str(uuid.uuid4())
        with self.assertRaises(ValueError):
            self.authority.register(intent, self.ledger, new_grant, self.pin, authorize=lambda *_: False, observe=self.observe)
        spec = self.authority.register(intent, self.ledger, new_grant, self.pin, authorize=approve_fixture, observe=self.observe)
        self.assertEqual(spec["epoch"], 2)
        self.authority.reserve(self.ledger, spec, "P1", authorize=approve_fixture, observe=self.observe)
        self.assertEqual(self.authority.receipt(spec, authorize=approve_fixture)["consumed_completion_attempts"], 1)

    def test_permission_denial_and_identity_unavailability_do_not_spend(self):
        for bad in (None, lambda *_: False, lambda *_: 1):
            with self.assertRaises(ValueError):
                self.reserve(authorize=bad)
        for observe in (lambda: None, lambda: {}, lambda: (_ for _ in ()).throw(RuntimeError("synthetic unavailable"))):
            with self.assertRaises(ValueError):
                self.reserve(observe=observe)
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 0)

    def test_permission_change_inside_transaction_rolls_back_before_authority_commit(self):
        checks = [0]
        def once(*_):
            checks[0] += 1
            return checks[0] == 1
        with self.assertRaises(ValueError):
            self.reserve(authorize=once)
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 0)
        self.assertEqual(self.ledger.receipt(self.grant, authorize=approve_fixture)["consumed_completion_attempts"], 0)

    def test_failed_campaign_write_leaves_consumed_pending_intent_without_retry(self):
        with patch.object(self.ledger, "reserve", side_effect=ValueError("synthetic unavailable")), self.assertRaises(ValueError):
            self.reserve()
        r = self.receipt()
        self.assertEqual((r["phase"], r["consumed_completion_attempts"]), ("reserve_pending", 1))
        with self.assertRaises(ValueError):
            self.reserve("P2", authority=self.reopen())

    def child(self, crash):
        v = {"authority_path": str(self.authority._store.path), "authority_id": self.authority.authority_id,
             "ledger_path": str(self.ledger.path), "ledger_id": self.ledger.store_id, "spec": self.spec, "pin": self.pin, "crash": crash}
        p = subprocess.run([sys.executable, "-c", CHILD, str(ROOT)], input=json.dumps(v).encode(), capture_output=True, timeout=20)
        self.assertEqual(p.stdout, b"")
        self.assertEqual(p.stderr, b"")
        return p.returncode

    def test_process_crash_after_authority_commit_never_refunds_or_replays(self):
        self.assertEqual(self.child("before_campaign"), 75)
        self.assertEqual(self.receipt()["phase"], "reserve_pending")
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 1)
        self.assertEqual(self.ledger.receipt(self.grant, authorize=approve_fixture)["consumed_completion_attempts"], 0)
        self.assertEqual(self.child(None), 42)

    def test_process_crash_after_campaign_write_stays_ambiguous_consumed(self):
        self.assertEqual(self.child("after_campaign"), 76)
        self.assertEqual(self.receipt()["phase"], "reserve_pending")
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 1)
        self.assertEqual(self.ledger.receipt(self.grant, authorize=approve_fixture)["consumed_completion_attempts"], 1)
        self.assertEqual(self.child(None), 42)

    def test_concurrent_connections_reserve_one_packet_only_once(self):
        def run(_):
            try:
                self.reserve(authority=self.reopen())
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(run, range(5)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 1)

    def test_unexpected_campaign_write_cannot_be_promoted_as_exact_checkpoint(self):
        finish = self.authority._finish
        def unexpected(*args, **kwargs):
            self.ledger.reserve(self.grant, "P2", authorize=approve_fixture)
            return finish(*args, **kwargs)
        with patch.object(self.authority, "_finish", side_effect=unexpected), self.assertRaises(ValueError):
            self.reserve()
        self.assertEqual(self.receipt()["phase"], "reserve_pending")
        with self.assertRaises(ValueError):
            self.reserve("P3")

    def test_mid_operation_model_change_discards_admission_and_consumes_cost(self):
        reserve = self.ledger.reserve
        def changed(*args, **kwargs):
            result = reserve(*args, **kwargs)
            self.pin["model_digest_sha256"] = sha("changed weights")
            return result
        with patch.object(self.ledger, "reserve", side_effect=changed), self.assertRaises(ValueError):
            self.reserve()
        self.assertEqual(self.receipt()["phase"], "reserve_pending")
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 1)

    def test_terminal_metadata_is_exact_and_one_time_without_budget_refund(self):
        self.reserve()
        self.authority.settle(self.ledger, self.spec, "P1", outcome="failed_consumed", authorize=approve_fixture, observe=self.observe)
        before = self.receipt()
        with self.assertRaises(ValueError):
            self.authority.settle(self.ledger, self.spec, "P1", outcome="returned_unqualified", result_sha256=sha("result"),
                                  authorize=approve_fixture, observe=self.observe)
        self.assertEqual(self.receipt(), before)
        with self.assertRaises(ValueError):
            self.reserve()

    def test_missing_substituted_or_same_authority_store_fails_closed(self):
        with self.assertRaises(FileNotFoundError):
            CampaignAuthority(self.root / "missing.sqlite", expected_authority_id=self.authority.authority_id)
        with self.assertRaises(ValueError):
            CampaignAuthority(self.authority._store.path, expected_authority_id=str(uuid.uuid4()))
        with self.assertRaises(ValueError):
            self.authority.register(str(uuid.uuid4()), self.authority._store, self.grant, self.pin, authorize=approve_fixture, observe=self.observe)
        changed = copy.deepcopy(self.spec)
        changed["ledger_store_id"] = str(uuid.uuid4())
        with self.assertRaises(ValueError):
            self.authority.reserve(self.ledger, changed, "P1", authorize=approve_fixture, observe=self.observe)

    def test_revocation_and_restore_denial_leave_tombstones_and_history(self):
        with self.assertRaises(ValueError):
            self.authority.fence_restore(self.ledger.store_id, authorize=lambda *_: False)
        self.assertFalse(self.receipt()["fenced"])
        self.authority.revoke(self.spec, authorize=approve_fixture)
        with self.assertRaises(ValueError):
            self.reserve(authority=self.reopen())
        self.assertTrue(self.receipt()["revoked"])
        with self.assertRaises(ValueError):
            self.authority.receipt(self.spec, authorize=lambda *_: False)

    def test_full_allowance_totals_remain_exact_across_reopens(self):
        for packet in self.plan["packets"]:
            self.reserve(packet["id"], authority=self.reopen())
            self.authority.settle(self.ledger, self.spec, packet["id"], outcome="returned_unqualified", result_sha256=sha("synthetic result " + packet["id"]),
                                  authorize=approve_fixture, observe=self.observe)
        r = self.receipt()
        self.assertEqual(r["consumed_completion_attempts"], self.allowance.completion_attempts)
        self.assertEqual(r["consumed_upper_bound_units"], self.allowance.context_units)
        self.assertEqual(r["consumed_copied_text_bytes"], self.allowance.copied_text_bytes)
        self.assertEqual(r["phase"], "active")

    def test_authority_persists_only_hashes_labels_limits_and_no_source_or_credentials(self):
        with sqlite3.connect(self.authority._store.path) as db:
            stored = db.execute("SELECT spec_json FROM guard_intents").fetchone()[0]
        self.assertNotIn(CASES[1]["question"], stored)
        for s in self.sources:
            self.assertNotIn(s["text"], stored)
            self.assertNotIn(s["document_id"], stored)
        self.assertNotIn("api_key", stored)
        self.assertTrue(json.loads(stored)["not_native_or_production_authorization"])

    def test_approved_tunnel_is_explicit_and_unknown_public_transport_is_rejected(self):
        approved = {**self.pin, "transport_mode": "approved_laptop_tunnel", "route_sha256": sha("invented approved tunnel")}
        self.assertEqual(validate_pin(approved, 8192), approved)
        with self.assertRaises(ValueError):
            self.reserve(observe=lambda: approved)
        with self.assertRaises(ValueError):
            validate_pin({**approved, "transport_mode": "public_https"}, 8192)
