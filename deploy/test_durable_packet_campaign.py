"""Private durable admission, crash, replay, tampering and process-race contracts."""

import copy
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from durable_campaign_cases import CASES  # noqa: E402
from durable_packet_campaign import CampaignLedger, prepare_grant, validate_grant  # noqa: E402
from evaluate_durable_campaign import approve_fixture, evaluate, fixture  # noqa: E402
from offline_quotation_boundaries import sha  # noqa: E402

from app.evidence_prompt import canonical  # noqa: E402

CHILD = """
import sys,json,os
from pathlib import Path
sys.path[:0]=[sys.argv[1]+'/scripts',sys.argv[1]+'/backend']
from durable_packet_campaign import CampaignLedger
value=json.load(sys.stdin)
ledger=CampaignLedger(Path(value['path']),expected_store_id=value['store_id'])
try:ledger.reserve(value['grant'],value['packet'],authorize=lambda *_:True)
except ValueError:sys.exit(42)
if value.get('dispatch_marker'):Path(value['dispatch_marker']).write_text('synthetic_dispatch_only')
if value.get('crash'):os._exit(73)
"""


class DurablePacketCampaignContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "ledger.sqlite"
        self.ledger = CampaignLedger.create(self.path)
        self.store_id = self.ledger.store_id
        self.sources, self.plan, self.allowance, self.grant = fixture(CASES[1], 2)

    def tearDown(self):
        self.temp.cleanup()

    def admit(self):
        self.ledger.admit(self.grant, authorize=approve_fixture)

    def reopen(self):
        return CampaignLedger(self.path, expected_store_id=self.store_id)

    def receipt(self, ledger=None):
        return (ledger or self.ledger).receipt(self.grant, authorize=approve_fixture)

    def launch(self, packet, *, crash=False, marker=None):
        value = {"path": str(self.path), "store_id": self.store_id, "grant": self.grant,
                 "packet": packet, "crash": crash, "dispatch_marker": str(marker) if marker else None}
        p = subprocess.Popen([sys.executable, "-c", CHILD, str(ROOT)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.stdin.write(json.dumps(value).encode())
        p.stdin.close()
        return p

    def joined(self, p):
        code = p.wait(timeout=20)
        out, err = p.stdout.read(), p.stderr.read()
        p.stdout.close()
        p.stderr.close()
        self.assertEqual(out, b"")
        self.assertEqual(err, b"")
        return code

    def test_fresh_report_preserves_exact_copies_across_recreated_sessions(self):
        report = evaluate()
        self.assertEqual(report, evaluate())
        self.assertEqual(report["summary"], {"cases": 6, "recreated_sessions": 7, "mock_completion_requests": 7,
            "mock_metadata_requests": 7, "duplicate_reservations_rejected": 4, "no_candidate_cases": 2, "all_copies_exact": True})
        self.assertEqual(report["native_inference_calls"], 0)
        self.assertFalse(report["production_activation"])

    def test_private_create_is_exclusive_and_store_identity_is_required(self):
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            CampaignLedger.create(self.path)
        with self.assertRaises(ValueError):
            CampaignLedger(self.path, expected_store_id=str(uuid.uuid4()))
        with self.assertRaises(ValueError):
            CampaignLedger(self.path, expected_store_id=True)

    def test_missing_truncated_symlink_hardlink_and_permissive_store_fail_closed(self):
        missing = self.root / "missing.sqlite"
        with self.assertRaises(FileNotFoundError):
            CampaignLedger(missing, expected_store_id=self.store_id)
        self.assertFalse(missing.exists())
        alias = self.root / "alias.sqlite"
        alias.symlink_to(self.path)
        with self.assertRaises(ValueError):
            CampaignLedger(alias, expected_store_id=self.store_id)
        alias.unlink()
        os.link(self.path, alias)
        with self.assertRaises(ValueError):
            self.reopen()
        alias.unlink()
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.reopen()
        self.path.chmod(0o600)
        self.path.write_bytes(b"truncated")
        with self.assertRaises(ValueError):
            self.reopen()

    def test_parent_scope_and_authority_substitution_fail_closed(self):
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):
            self.reopen()
        self.root.chmod(0o700)
        other = CampaignLedger.create(self.root / "other.sqlite")
        with self.assertRaises(ValueError):
            CampaignLedger(self.path, expected_store_id=other.store_id)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE store_meta SET store_id=?", (other.store_id,))
        with self.assertRaises(ValueError):
            self.reopen()

    def test_grant_is_admitted_once_and_cannot_be_reissued_after_restart(self):
        self.admit()
        with self.assertRaises(ValueError):
            self.reopen().admit(self.grant, authorize=approve_fixture)
        changed = copy.deepcopy(self.grant)
        changed["selector_context"]["question_sha256"] = sha("different")
        changed["selector_context_sha256"] = sha(canonical(changed["selector_context"]))
        changed["grant_sha256"] = sha(canonical({k: v for k, v in changed.items() if k != "grant_sha256"}))
        with self.assertRaises(ValueError):
            self.reopen().admit(changed, authorize=approve_fixture)
        with self.assertRaises(ValueError):
            self.reopen().reserve(changed, "P1", authorize=approve_fixture)
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 0)

    def test_authorizer_is_current_strict_and_receives_only_metadata_actions(self):
        for bad in (None, lambda *_: False, lambda *_: 1):
            with self.assertRaises(ValueError):
                self.ledger.admit(self.grant, authorize=bad)
        actions = []
        self.ledger.admit(self.grant, authorize=lambda g, action: actions.append(action) or True)
        self.assertEqual(actions, ["admit", "admit"])
        for text in (CASES[1]["question"], self.sources[0]["text"]):
            self.assertNotIn(text, canonical(self.grant))
        with self.assertRaises(ValueError):
            self.ledger.reserve(self.grant, "P1", authorize=lambda *_: False)
        with self.assertRaises(ValueError):
            self.ledger.receipt(self.grant, authorize=lambda *_: False)
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 0)

    def test_denial_after_insert_rolls_back_admission_and_reservation(self):
        count = [0]
        def once(*_):
            count[0] += 1
            return count[0] == 1
        with self.assertRaises(ValueError):
            self.ledger.admit(self.grant, authorize=once)
        self.admit()
        count[0] = 0
        with self.assertRaises(ValueError):
            self.ledger.reserve(self.grant, "P1", authorize=once)
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 0)
        self.reopen().reserve(self.grant, "P1", authorize=approve_fixture)
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 1)

    def test_crash_after_committed_reservation_consumes_budget_and_never_replays(self):
        self.admit()
        self.assertEqual(self.joined(self.launch("P1", crash=True)), 73)
        self.assertEqual(self.receipt(self.reopen())["attempts"][0]["state"], "reserved")
        self.assertEqual(self.joined(self.launch("P1")), 42)
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 1)

    def test_crash_after_synthetic_dispatch_never_repeats_effect(self):
        self.admit()
        marker = self.root / "synthetic-effect"
        self.assertEqual(self.joined(self.launch("P1", crash=True, marker=marker)), 73)
        self.assertEqual(marker.read_text(), "synthetic_dispatch_only")
        marker.unlink()
        self.assertEqual(self.joined(self.launch("P1", marker=marker)), 42)
        self.assertFalse(marker.exists())
        self.assertEqual(self.receipt()["attempts"][0]["state"], "reserved")

    def test_duplicate_process_race_commits_exactly_one_reservation(self):
        self.admit()
        processes = [self.launch("P1") for _ in range(5)]
        codes = [self.joined(p) for p in processes]
        self.assertEqual(sorted(codes), [0, 42, 42, 42, 42])
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 1)

    def test_distinct_process_reservations_reconcile_all_cost_dimensions(self):
        self.admit()
        processes = [self.launch(p["id"]) for p in self.grant["packets"]]
        self.assertTrue(all(self.joined(p) == 0 for p in processes))
        r = self.receipt(self.reopen())
        self.assertEqual(r["consumed_completion_attempts"], self.allowance.completion_attempts)
        self.assertEqual(r["consumed_upper_bound_units"], self.allowance.context_units)
        self.assertEqual(r["consumed_copied_text_bytes"], self.allowance.copied_text_bytes)
        for p in self.grant["packets"]:
            with self.assertRaises(ValueError):
                self.reopen().reserve(self.grant, p["id"], authorize=approve_fixture)

    def test_terminal_metadata_is_one_time_and_no_refund_or_result_replay_exists(self):
        self.admit()
        self.ledger.reserve(self.grant, "P1", authorize=approve_fixture)
        self.reopen().settle(self.grant, "P1", outcome="failed_consumed", authorize=approve_fixture)
        before = self.receipt()
        with self.assertRaises(ValueError):
            self.ledger.settle(self.grant, "P1", outcome="returned_unqualified", result_sha256=sha("result"), authorize=approve_fixture)
        with self.assertRaises(ValueError):
            self.reopen().reserve(self.grant, "P1", authorize=approve_fixture)
        self.assertEqual(self.receipt(), before)
        self.assertFalse(any(hasattr(self.ledger, k) for k in ("reset", "refund", "delete", "replay")))

    def test_revocation_survives_restart_and_blocks_new_reservations_and_result_publication(self):
        self.admit()
        self.ledger.reserve(self.grant, "P1", authorize=approve_fixture)
        self.reopen().revoke(self.grant, authorize=approve_fixture)
        with self.assertRaises(ValueError):
            self.reopen().reserve(self.grant, "P2", authorize=approve_fixture)
        with self.assertRaises(ValueError):
            self.reopen().settle(self.grant, "P1", outcome="returned_unqualified", result_sha256=sha("result"), authorize=approve_fixture)
        self.reopen().settle(self.grant, "P1", outcome="failed_consumed", authorize=approve_fixture)
        self.assertTrue(self.receipt()["revoked"])
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 1)
        with self.assertRaises(ValueError):
            self.reopen().admit(self.grant, authorize=approve_fixture)

    def test_changed_wire_cost_allowance_and_grant_fields_rejected_before_admission(self):
        for field in ("messages_sha256", "units", "copied_bytes"):
            altered = copy.deepcopy(self.grant)
            altered["packets"][0][field] = sha("other") if field.endswith("sha256") else 999999
            with self.assertRaises(ValueError):
                self.ledger.admit(altered, authorize=approve_fixture)
        for field in ("completion_attempts", "context_units", "copied_text_bytes"):
            altered = copy.deepcopy(self.grant)
            altered["selector_context"]["allowance"][field] = 0
            altered["selector_context_sha256"] = sha(canonical(altered["selector_context"]))
            altered["grant_sha256"] = sha(canonical({k: v for k, v in altered.items() if k != "grant_sha256"}))
            with self.assertRaises(ValueError):
                validate_grant(altered)
        altered = copy.deepcopy(self.grant)
        altered["native_authorization"] = True
        with self.assertRaises(ValueError):
            validate_grant(altered)

    def test_prepare_rejects_stale_unused_evidence_and_unevaluated_limits(self):
        self.sources[-1]["document_revision"] += 1
        with self.assertRaises(ValueError):
            prepare_grant(self.grant["grant_id"], CASES[1]["question"], self.sources, self.plan, self.allowance)
        for limit in (True, 8193, 0):
            with self.assertRaises(ValueError):
                prepare_grant(self.grant["grant_id"], CASES[1]["question"], self.sources, self.plan, self.allowance, context_limit=limit)

    def test_cost_tampering_and_unsupported_journal_mode_fail_closed(self):
        self.admit()
        self.ledger.reserve(self.grant, "P1", authorize=approve_fixture)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE attempts SET units=1")
        with self.assertRaises(ValueError):
            self.receipt()
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA journal_mode=WAL")
        with self.assertRaises(ValueError):
            self.reopen()

    def test_busy_authority_fails_bounded_without_creating_a_reservation(self):
        self.admit()
        db = sqlite3.connect(self.path)
        try:
            db.execute("BEGIN IMMEDIATE")
            with self.assertRaises(ValueError):
                self.ledger.reserve(self.grant, "P1", authorize=approve_fixture)
        finally:
            db.rollback()
            db.close()
        self.assertEqual(self.receipt()["consumed_completion_attempts"], 0)

    def test_no_source_text_or_runtime_credentials_are_persisted_in_ledger(self):
        self.admit()
        self.ledger.reserve(self.grant, "P1", authorize=approve_fixture)
        with sqlite3.connect(self.path) as db:
            text = db.execute("SELECT grant_json FROM campaigns").fetchone()[0]
        self.assertEqual(json.loads(text), self.grant)
        self.assertNotIn(CASES[1]["question"], text)
        for s in self.sources:
            self.assertNotIn(s["text"], text)
            self.assertNotIn(s["document_id"], text)
        self.assertNotIn("api_key", text)

    def test_empty_inventory_has_no_dispatch_and_zero_allowance(self):
        _, _, _, grant = fixture(CASES[4], 5)
        self.ledger.admit(grant, authorize=approve_fixture)
        with self.assertRaises(ValueError):
            self.ledger.reserve(grant, "P1", authorize=approve_fixture)
        self.assertEqual(self.ledger.receipt(grant, authorize=approve_fixture)["consumed_completion_attempts"], 0)

    def test_success_stores_only_caller_digest_not_replayable_result_content(self):
        self.admit()
        self.ledger.reserve(self.grant, "P1", authorize=approve_fixture)
        self.ledger.settle(self.grant, "P1", outcome="returned_unqualified", result_sha256=sha("synthetic result"), authorize=approve_fixture)
        r = self.receipt(self.reopen())
        self.assertEqual(r["attempts"], [{"packet_id": "P1", "state": "returned_unqualified", "result_sha256": sha("synthetic result")}])
        self.assertNotIn("synthetic result", canonical(r))
        self.assertFalse(r["native_or_legal_qualification"])
