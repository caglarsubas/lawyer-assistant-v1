import concurrent.futures
import hashlib
import json
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "scripts"), str(Path(__file__).resolve().parents[1] / "backend")]
import artifact_store as a  # noqa: E402
import sealed_handoff_qualification as q  # noqa: E402
import sealed_relay_handoff as relay  # noqa: E402
import sealed_volume as volume  # noqa: E402


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.control = self.folder("control")
        self.journal = volume.Journal.create(self.control / "control.sqlite")

    def tearDown(self):
        self.temp.cleanup()

    def folder(self, name):
        path = self.root / name
        path.mkdir(mode=0o700)
        return path

    @contextmanager
    def emulated_readonly(self):
        # This is a unit filesystem adapter, never a native RO qualification.
        def verify(root, manifest, budget=a.Budget(), **kwargs):
            if kwargs.get("cancelled") is not None and kwargs["cancelled"]():
                raise a.StoreRejected("cancelled")
            proof = a.verify_core(root, manifest, budget, time.monotonic() + budget.seconds,
                                  strategy=kwargs.get("strategy", "stream"))
            proof["peak_rss_kib"] = 10000
            return proof
        with patch.object(a, "readonly", return_value=True), patch.object(a, "supervised_verify", side_effect=verify):
            yield

    def imported(self, name="basic"):
        bundle = self.root / (name + "-bundle")
        info = q.make_bundle(bundle)
        target = self.folder(name + "-target")
        op, binding = q.operation(name), a.digest((name + "-binding").encode())
        result = volume.import_bundle(bundle, target, self.journal, op, info["bundle_index_sha256"], binding)
        return bundle, target, op, binding, info, result

    def test_export_import_preserves_bytes_and_prepared_is_not_sealed(self):
        source = self.root / "source"
        index = q.make_store(source)
        destination = self.folder("export")
        before = {p.name: p.read_bytes() for p in (source / "blobs").iterdir()}
        with self.emulated_readonly():
            exported = volume.export_bundle(source, destination, index["manifest"])
            parsed = volume.parse_index((destination / "bundle/index.json").read_bytes(), exported["bundle_index_sha256"])
            self.assertEqual(parsed, index)
            target = self.folder("import")
            op = q.operation("export-import")
            result = volume.import_bundle(destination / "bundle", target, self.journal, op, exported["bundle_index_sha256"], "a" * 64)
        self.assertEqual(self.journal.get(op)["state"], "prepared")
        self.assertTrue(result["requires_readonly_reverification"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in (source / "blobs").iterdir()})
        self.assertFalse(result["production_activation"])
        self.assertNotIn("credential", json.dumps(result))

    def test_frozen_transfer_matrix_except_explicit_writable_adapter(self):
        bundles, targets = self.folder("bundles"), self.folder("targets")
        approvals = {n: q.make_bundle(bundles / n, n) for n, _ in q.TRANSFER_CASES}
        with self.emulated_readonly():
            rows = q.run_transfer_cases(bundles, targets, self.journal, approvals, "unit-binding-", skip={"T16_writable_bundle"})
        self.assertEqual(len(rows), 15)
        self.assertTrue(all(r["observed"] == r["expected"] and r["original_preserved"] for r in rows))
        self.assertTrue(all(r["control_state"] not in {"prepared", "sealed"} for r in rows if r["expected"] == "rejected"))

    def test_kernel_writable_bundle_rejects_without_control_record(self):
        bundle = self.root / "rw-bundle"
        info = q.make_bundle(bundle)
        target, op = self.folder("rw-target"), q.operation("rw")
        with patch.object(a, "readonly", return_value=False), self.assertRaises(ValueError):
            volume.import_bundle(bundle, target, self.journal, op, info["bundle_index_sha256"], "a" * 64)
        self.assertEqual(list(target.iterdir()), [])
        with self.assertRaises(ValueError):
            self.journal.get(op)

    def test_writable_target_cannot_be_sealed(self):
        with self.emulated_readonly():
            _, target, op, binding, _, _ = self.imported()
        with patch.object(a, "readonly", return_value=False), self.assertRaises(ValueError):
            volume.seal(target, self.journal, op, binding)
        self.assertEqual(self.journal.get(op)["state"], "prepared")

    def test_restored_generation_is_fresh_and_old_handoff_rejects(self):
        with self.emulated_readonly():
            bundle, target, op, binding, info, _ = self.imported()
            volume.seal(target, self.journal, op, binding)
            first = q.SigningFixture(self.journal, op, binding, info["manifest_digest"])
            raw = first.issue(target)
            restored, restore_op, restore_binding = self.folder("restored"), q.operation("restore"), "b" * 64
            result = volume.import_bundle(bundle, restored, self.journal, restore_op, info["bundle_index_sha256"], restore_binding, purpose="restore", parent=op)
            self.assertNotEqual(result["record"]["generation_id"], self.journal.get(op)["generation_id"])
            self.assertEqual(result["record"]["content_sha256"], self.journal.get(op)["record"]["content_sha256"])
            volume.seal(restored, self.journal, restore_op, restore_binding)
            expected = replace(first.expected, operation_id=restore_op, volume_binding_sha256=restore_binding)
            with self.assertRaises(ValueError):
                relay.consume(raw, restored, self.journal, expected, key_for=first.key_for, resolve_pin=lambda: first.runtime, clock=lambda: first.now)
            fresh = q.SigningFixture(self.journal, restore_op, restore_binding, info["manifest_digest"])
            self.assertTrue(fresh.consume(fresh.issue(restored), restored)["metadata_handoff_verified"])

    def test_revocation_preserves_proof_and_blocks_restore(self):
        with self.emulated_readonly():
            bundle, target, op, binding, info, _ = self.imported()
            volume.seal(target, self.journal, op, binding)
            proof = self.journal.get(op)["proof"]
            self.journal.revoke(op)
            restored = self.folder("revoked-restore")
            with self.assertRaises(ValueError):
                volume.import_bundle(bundle, restored, self.journal, q.operation("revoked-restore"), info["bundle_index_sha256"], "b" * 64, purpose="restore", parent=op)
        self.assertEqual(self.journal.get(op)["proof"], proof)
        self.assertEqual(list(restored.iterdir()), [])

    def test_operation_id_cannot_replay_into_fresh_target(self):
        with self.emulated_readonly():
            bundle, _, op, binding, info, _ = self.imported()
            generation = self.journal.get(op)["generation_id"]
            empty = self.folder("replay-target")
            with self.assertRaises(ValueError):
                volume.import_bundle(bundle, empty, self.journal, op, info["bundle_index_sha256"], binding)
        self.assertEqual(list(empty.iterdir()), [])
        self.assertEqual(self.journal.get(op)["generation_id"], generation)

    def test_copy_crash_remains_quarantined_after_reopening(self):
        bundle = self.root / "copy-crash-bundle"
        info = q.make_bundle(bundle)
        target, op = self.folder("copy-crash-target"), q.operation("copy-crash")

        def crash(event):
            if event == "copied_blob":
                raise SystemExit(37)

        with self.emulated_readonly(), self.assertRaises(SystemExit):
            volume.import_bundle(bundle, target, self.journal, op, info["bundle_index_sha256"], "a" * 64, checkpoint=crash)
        reopened = volume.Journal(self.journal.path)
        before = hashlib.sha256(reopened.path.read_bytes()).hexdigest()
        recovered = reopened.recover(op)
        self.assertEqual(before, hashlib.sha256(reopened.path.read_bytes()).hexdigest())
        self.assertEqual(recovered["state"], "copying")
        self.assertFalse(recovered["automatic_repair_or_replay"])
        self.assertFalse(list(target.glob("snapshot-*")))

    def test_rename_crash_does_not_promote_complete_orphan(self):
        bundle = self.root / "rename-crash-bundle"
        info = q.make_bundle(bundle)
        target, op = self.folder("rename-crash-target"), q.operation("rename-crash")

        def crash(event):
            if event == "renamed":
                raise SystemExit(38)

        with self.emulated_readonly(), self.assertRaises(SystemExit):
            volume.import_bundle(bundle, target, self.journal, op, info["bundle_index_sha256"], "a" * 64, checkpoint=crash)
        self.assertEqual(len(list(target.glob("snapshot-*"))), 1)
        with self.emulated_readonly(), self.assertRaises(ValueError):
            volume.seal(target, volume.Journal(self.journal.path), op, "a" * 64)
        self.assertEqual(self.journal.get(op)["state"], "copying")

    def test_late_cancellation_revokes_prepared_operation(self):
        bundle = self.root / "cancel-bundle"
        info = q.make_bundle(bundle)
        target, op = self.folder("cancel-target"), q.operation("late-cancel")
        original, cancelled = self.journal._transition, [False]

        def transition(operation, previous, state, proof=None):
            original(operation, previous, state, proof)
            if state == "prepared":
                cancelled[0] = True

        with self.emulated_readonly(), patch.object(self.journal, "_transition", side_effect=transition), self.assertRaises(ValueError):
            volume.import_bundle(bundle, target, self.journal, op, info["bundle_index_sha256"], "a" * 64, cancelled=lambda: cancelled[0])
        self.assertEqual(self.journal.get(op)["state"], "revoked")

    def test_exclusive_reservation_allows_one_writer_per_destination(self):
        bundle = self.root / "race-bundle"
        info = q.make_bundle(bundle)
        target, barrier, original = self.folder("race-target"), threading.Barrier(2), self.journal.begin

        def begin(*args, **kwargs):
            barrier.wait(timeout=2)
            return original(*args, **kwargs)

        def attempt(number):
            try:
                volume.import_bundle(bundle, target, self.journal, q.operation("race-" + str(number)), info["bundle_index_sha256"], "a" * 64)
                return "prepared"
            except (ValueError, OSError):
                return "rejected"

        with self.emulated_readonly(), patch.object(self.journal, "begin", side_effect=begin), concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertEqual(sorted(results), ["prepared", "rejected"])
        self.assertEqual(len(list(target.glob("snapshot-*"))), 1)

    def test_frozen_signature_and_identity_case_matrix(self):
        with self.emulated_readonly():
            _, target, op, binding, info, _ = self.imported()
            volume.seal(target, self.journal, op, binding)
            report = q.run_handoff_cases(target, self.journal, op, binding, info["manifest_digest"])
        self.assertEqual(len(report["cases"]), 11)
        self.assertTrue(all(r["observed"] == r["expected"] and r["opaque_relay_preserved"] for r in report["cases"]))
        frame = report["valid_frame"]
        self.assertTrue(q.verify_retained(relay.unb64(frame["wire_base64"]), frame["context"], frame["record"], wire_sha256=frame["wire_sha256"])["metadata_replay_only"])
        self.assertEqual(report["execution_resolver_calls"], 0)

    def test_nonce_crash_burns_challenge_durably(self):
        with self.emulated_readonly():
            _, target, op, binding, info, _ = self.imported()
            volume.seal(target, self.journal, op, binding)
            fixture = q.SigningFixture(self.journal, op, binding, info["manifest_digest"])
            raw = fixture.issue(target)

            def crash(_):
                raise SystemExit(39)

            with self.assertRaises(SystemExit):
                fixture.consume(raw, target, checkpoint=crash)
            self.assertEqual(volume.Journal(self.journal.path).recover(op)["nonce_counts"], {"reserved": 1})
            with self.assertRaises(ValueError):
                fixture.consume(raw, target)

    def test_one_concurrent_consumer_wins_same_nonce(self):
        with self.emulated_readonly():
            _, target, op, binding, info, _ = self.imported()
            volume.seal(target, self.journal, op, binding)
            fixture = q.SigningFixture(self.journal, op, binding, info["manifest_digest"])
            raw = fixture.issue(target)

            def consume(_):
                try:
                    fixture.consume(raw, target)
                    return "verified"
                except ValueError:
                    return "rejected"

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(consume, range(2)))
        self.assertEqual(sorted(results), ["rejected", "verified"])
        self.assertEqual(self.journal.recover(op)["nonce_counts"], {"consumed": 1})

    def test_current_identity_change_during_read_burns_nonce(self):
        with self.emulated_readonly():
            _, target, op, binding, info, _ = self.imported()
            volume.seal(target, self.journal, op, binding)
            fixture = q.SigningFixture(self.journal, op, binding, info["manifest_digest"])
            raw, original = fixture.issue(target), volume.seal

            def change(*args, **kwargs):
                result = original(*args, **kwargs)
                fixture.runtime["tenant_id"] = "fixture-revoked-tenant"
                return result

            with patch.object(volume, "seal", side_effect=change), self.assertRaises(ValueError):
                fixture.consume(raw, target)
        self.assertEqual(self.journal.recover(op)["nonce_counts"], {"reserved": 1})

    def test_wrong_bound_volume_cannot_seal(self):
        with self.emulated_readonly():
            _, target, op, _, _, _ = self.imported()
            with self.assertRaises(ValueError):
                volume.seal(target, self.journal, op, "f" * 64)
        self.assertEqual(self.journal.get(op)["state"], "prepared")

    def test_index_has_no_paths_keys_or_state_and_requires_canonical_wire(self):
        bundle = self.root / "strict-bundle"
        info = q.make_bundle(bundle)
        raw = (bundle / "index.json").read_bytes()
        self.assertEqual(set(volume.parse_index(raw, info["bundle_index_sha256"])), {"format", "manifest", "artifacts", "content_sha256", "total_bytes"})
        with self.assertRaises(ValueError):
            volume.parse_index(raw + b" ", a.digest(raw + b" "))
        for raw_value in [True, 0, -1, float("inf")]:
            with self.assertRaises(ValueError):
                volume.TransferBudget(seconds=raw_value).validate()

    def test_journal_cannot_be_overwritten_or_corruption_reset(self):
        before = self.journal.path.read_bytes()
        with self.assertRaises(FileExistsError):
            volume.Journal.create(self.journal.path)
        self.assertEqual(before, self.journal.path.read_bytes())
        bad = self.control / "corrupt.sqlite"
        volume.write_new(bad, b"corrupt-control-not-accepted")
        with self.assertRaises((ValueError, __import__("sqlite3").Error)):
            volume.Journal(bad)
        self.assertEqual(bad.read_bytes(), b"corrupt-control-not-accepted")

    def test_policy_preserves_verification_limits_and_inactive_trust(self):
        policy = Path(__file__).parent / "fixtures/sealed_handoff_policy.json"
        self.assertEqual(json.loads(policy.read_bytes()), q.POLICY)
        self.assertEqual(q.POLICY["verification_seconds"], 20)
        self.assertEqual(q.POLICY["transfer_seconds"], 90)
        self.assertFalse(q.POLICY["real_signers_or_credentials"])
        self.assertFalse(q.POLICY["production_activation"])


if __name__ == "__main__":
    unittest.main()
