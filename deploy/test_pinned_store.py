import copy
import errno
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import artifact_store as a  # noqa: E402
import pinned_store_qualification as q  # noqa: E402


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def core(self, root, pin):
        with patch.object(a, "readonly", return_value=True):
            return a.verify_core(root, pin, a.Budget(), time.monotonic() + 20, strategy="windowed-pinned")

    def observe_descriptors(self):
        opened, original = [], os.open

        def tracked(*args, **kwargs):
            fd = original(*args, **kwargs)
            opened.append(fd)
            return fd

        return opened, tracked

    def assert_closed(self, opened):
        for fd in opened:
            with self.assertRaises(OSError) as error:
                os.fstat(fd)
            self.assertEqual(error.exception.errno, errno.EBADF)

    def test_maximum_snapshot_retains_all_eighteen_blob_descriptors(self):
        root = self.root / "maximum"
        info = q.snapshot(root, "P05_maximum_layers")
        opened, tracked = self.observe_descriptors()
        fstats, original = [], os.fstat

        def fstat(fd):
            fstats.append(fd)
            return original(fd)

        with patch.object(a.os, "open", side_effect=tracked), patch.object(a.os, "fstat", side_effect=fstat):
            proof = self.core(root, info["manifest_digest"])
        self.assertEqual(len(opened), 22)  # four directories plus eighteen blobs
        self.assertEqual(proof["retained_blob_descriptors"], 18)
        self.assertTrue(proof["retained_descriptors_rechecked"])
        self.assertTrue(all(fstats.count(fd) >= 3 for fd in opened[4:]))
        self.assert_closed(opened)

    def test_hash_rejection_closes_retained_descriptors(self):
        root = self.root / "corrupt"
        info = q.snapshot(root, "P07_corrupt_config")
        opened, tracked = self.observe_descriptors()
        with patch.object(a.os, "open", side_effect=tracked), self.assertRaises(a.StoreRejected) as error:
            self.core(root, info["manifest_digest"])
        self.assertEqual(error.exception.code, "digest")
        self.assert_closed(opened)

    def test_descriptor_duplication_failure_closes_original_without_fallback(self):
        root = self.root / "limited"
        info = q.snapshot(root)
        opened, tracked = self.observe_descriptors()
        with patch.object(a.os, "open", side_effect=tracked), \
                patch.object(a.os, "dup", side_effect=OSError(errno.EMFILE, "invented descriptor limit")), \
                self.assertRaises(a.StoreRejected) as error:
            self.core(root, info["manifest_digest"])
        self.assertEqual(error.exception.code, "invalid")
        self.assert_closed(opened)

    def test_actual_namespace_replacement_still_rejected(self):
        root = self.root / "replacement"
        info = q.snapshot(root)
        target = root / "blobs" / info["manifest_digest"].replace(":", "-")
        original, moved = a.blocks, [False]

        def replace_after_model(stream, size, strategy, **kwargs):
            yield from original(stream, size, strategy, **kwargs)
            if strategy == "windowed" and not moved[0]:
                moved[0] = True
                old = self.root / "retained-original-manifest"
                target.rename(old)
                shutil.copyfile(old, target)
                target.chmod(0o600)

        with patch.object(a, "blocks", side_effect=replace_after_model), self.assertRaises(a.StoreRejected) as error:
            self.core(root, info["manifest_digest"])
        self.assertTrue(moved[0])
        self.assertEqual(error.exception.code, "changed")

    def test_v3_proof_requires_every_descriptor_and_requested_strategy(self):
        info = q.snapshot(self.root / "proof")
        proof = self.core(self.root / "proof", info["manifest_digest"])
        proof["peak_rss_kib"] = 10000
        a.validate_proof(proof, info["manifest_digest"], a.Budget(), strategy="windowed-pinned")
        self.assertEqual(proof["schema"], "readonly-artifact-proof-v3")
        for strategy in ("stream", "windowed"):
            with self.assertRaises(a.StoreRejected):
                a.validate_proof(proof, info["manifest_digest"], a.Budget(), strategy=strategy)
        for key, value in [("retained_blob_descriptors", 1), ("retained_blob_descriptors", True),
                           ("retained_descriptors_rechecked", False), ("read_strategy", "windowed-v1")]:
            bad = copy.deepcopy(proof)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(a.StoreRejected):
                a.validate_proof(bad, info["manifest_digest"], a.Budget(), strategy="windowed-pinned")

    def test_fresh_pinned_fixture_matrix(self):
        skipped = {"P11_writable", "P12_cancel_after_start", "P13_descriptor_exhaustion"}
        for name, expected in q.CASES:
            if name in skipped:
                continue
            with self.subTest(case=name):
                root = self.root / name
                info = q.snapshot(root, name)
                if expected == "ok":
                    self.core(root, info["manifest_digest"])
                else:
                    with self.assertRaises(a.StoreRejected) as error:
                        self.core(root, info["manifest_digest"])
                    self.assertEqual(error.exception.code, expected)

    def test_kernel_read_only_requirement_is_not_relaxed(self):
        info = q.snapshot(self.root / "writable")
        with patch.object(a, "readonly", return_value=False), self.assertRaises(a.StoreRejected) as error:
            a.verify_core(self.root / "writable", info["manifest_digest"], a.Budget(), time.monotonic() + 20, strategy="windowed-pinned")
        self.assertEqual(error.exception.code, "readonly")

    def test_policy_and_old_negative_inputs_stay_separate(self):
        fixture = Path(__file__).parent / "fixtures"
        self.assertEqual(json.loads((fixture / "pinned_store_policy.json").read_bytes()), q.POLICY)
        self.assertEqual(q.POLICY["pre_post_target_seconds"], 20)
        self.assertEqual(q.POLICY["window_bytes"], 16 * 1024**2)
        self.assertEqual(q.POLICY["cpu_limit"], 2)
        self.assertEqual(q.POLICY["fresh_seed"], 20261027)
        self.assertFalse(q.POLICY["native_inference_qualified"])


if __name__ == "__main__":
    unittest.main()
