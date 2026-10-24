import json
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import artifact_store as a  # noqa: E402
import control_journal_qualification as q  # noqa: E402
import sealed_control_journal as c  # noqa: E402
import sealed_handoff_qualification as fixture  # noqa: E402
import sealed_relay_handoff as relay  # noqa: E402
import sealed_volume as v  # noqa: E402


class ControlContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        for name in ("work", "anchors", "backups"):
            (self.root / name).mkdir(mode=0o700)
        self.index = fixture.make_store(self.root / "store")
        # Unit filesystem adapter; actual read-only mount tested separately.
        with patch.object(a, "readonly", return_value=True):
            self.proof = a.verify_core(self.root / "store", self.index["manifest"], a.Budget(), time.monotonic() + 20, strategy="windowed-pinned")
        self.proof["peak_rss_kib"] = 10000
        self.lab = q.Lab(self.root / "work", self.root / "anchors", self.index, self.proof)

    def tearDown(self):
        self.temp.cleanup()

    def family(self, name):
        j = self.lab.journal(name)
        parent = self.lab.add(j, name + "parent")["operation_id"]
        child = self.lab.add(j, name + "child", parent=parent)["operation_id"]
        return j, parent, child

    def test_frozen_control_crash_and_concurrency_matrix(self):
        for name, expected in q.CASES:
            if name not in q.BACKUP_CASES:
                with self.subTest(case=name):
                    self.assertEqual(self.lab.case(name), expected)

    def test_exact_backup_and_stale_foreign_or_bad_hash_matrix(self):
        packet = self.lab.prepare_backups(self.root / "backups")
        with patch.object(a, "readonly", return_value=True):
            for name, expected in q.CASES:
                if name in q.BACKUP_CASES:
                    with self.subTest(case=name):
                        self.assertEqual(self.lab.backup_case(name, self.root / "backups", packet), expected)

    def test_policy_and_existing_reader_budgets_remain_pinned(self):
        self.assertEqual(json.loads((ROOT / "deploy/fixtures/control_journal_policy.json").read_text()), q.POLICY)
        self.assertEqual((c.MAX_OPERATIONS, c.MAX_DEPTH, c.MAX_COMMITS), (512, 32, 8192))
        self.assertEqual(a.Budget().seconds, 20)
        self.assertFalse(q.POLICY["production_activation"])

    def test_ancestor_revocation_during_local_verification_blocks_seal(self):
        j, parent, _ = self.family("seal-race")
        pending = self.lab.add(j, "pending", parent=parent, status="prepared")["operation_id"]
        target = self.root / "target"
        target.mkdir(mode=0o700)
        binding = j.get(pending)["record"]["volume_binding_sha256"]
        def verify(*args, **kwargs):
            j.revoke(parent)
            return self.proof
        with patch.object(a, "readonly", return_value=True), patch.object(a, "supervised_verify", side_effect=verify):
            with self.assertRaises(ValueError):
                v.seal(target, j, pending, binding)
        self.assertEqual(j.get(pending)["state"], "revoked")

    def issue(self, journal, operation):
        record = journal.get(operation)["record"]
        signer = fixture.SigningFixture(journal, operation, record["volume_binding_sha256"], self.index["manifest"])
        def unit_seal(root, j, op, binding):
            row = j.get(op)
            if row["state"] != "sealed" or row["record"]["volume_binding_sha256"] != binding:
                v.reject()
            return {"record": row["record"], "proof": self.proof}
        with patch.object(v, "seal", side_effect=unit_seal):
            wire = signer.issue(self.root)
        return signer, wire

    def test_existing_signed_receiver_rejects_revoked_descendant(self):
        j, parent, child = self.family("signed-revoke")
        signer, wire = self.issue(j, child)
        j.revoke(parent)
        with self.assertRaises(ValueError):
            signer.consume(relay.relay_bytes(wire), self.root)

    def test_existing_receiver_revocation_after_nonce_reservation_burns_it(self):
        j, parent, child = self.family("signed-race")
        signer, wire = self.issue(j, child)
        with self.assertRaises(ValueError):
            signer.consume(wire, self.root, checkpoint=lambda _: j.revoke(parent))
        self.assertEqual(j.recover(child)["nonce_counts"], {"reserved": 1})

    def test_invalid_logical_mutation_rolls_back_without_anchor_advance(self):
        j, parent, _ = self.family("bad-write")
        before = self.lab.hashes(j)
        with self.assertRaises(ValueError), j.connect() as db:
            db.execute("UPDATE operations SET state='sealed' WHERE id=?", (parent,))
            db.execute("DELETE FROM events WHERE operation=?", (parent,))
        self.assertEqual(before, self.lab.hashes(j))

    def test_lost_anchor_ack_requires_explicit_recovery_of_same_commit(self):
        j, _, child = self.family("ack-loss")
        challenge = q.operation("ack-nonce")
        with patch.object(c.Anchor, "append", side_effect=OSError("synthetic-write-failure")):
            with self.assertRaises(OSError):
                j.reserve_nonce(child, challenge, a.digest(b"wire"))
        with self.assertRaises(ValueError):
            self.lab.open(j)
        result = c.Journal.reconcile(j.path, j.anchor.path, j.journal_id)
        self.assertEqual(result["semantic_mutations_replayed"], 0)
        self.assertEqual(self.lab.open(j).recover(child)["nonce_counts"], {"reserved": 1})

    def test_wrong_external_identity_cannot_rebind_a_journal(self):
        j, _, _ = self.family("identity")
        before = self.lab.hashes(j)
        with self.assertRaises(ValueError):
            c.Journal(j.path, j.anchor.path, q.operation("wrong"))
        self.assertEqual(self.lab.hashes(j), before)

    def test_mistyped_metadata_cannot_be_repaired_or_reset(self):
        j, _, child = self.family("mistyped")
        db = sqlite3.connect(j.path)
        db.execute("UPDATE operations SET record=42 WHERE id=?", (child,))
        db.commit()
        db.close()
        before = self.lab.hashes(j)
        with self.assertRaises(ValueError):
            c.Journal.reconcile(j.path, j.anchor.path, j.journal_id)
        self.assertEqual(self.lab.hashes(j), before)

    def test_aligned_explicit_recovery_is_idempotent(self):
        j, _, _ = self.family("aligned")
        before = self.lab.hashes(j)
        for _ in range(2):
            self.assertEqual(c.Journal.reconcile(j.path, j.anchor.path, j.journal_id)["action"], "already_aligned")
        self.assertEqual(self.lab.hashes(j), before)


if __name__ == "__main__":
    unittest.main()
