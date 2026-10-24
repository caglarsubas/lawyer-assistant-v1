import copy
import hashlib
import json
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import artifact_store as a  # noqa: E402
import windowed_store_qualification as q  # noqa: E402


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def core(self, root, pin, **kwargs):
        # Native campaign separately requires real Linux ST_RDONLY.
        with patch.object(a, "readonly", return_value=True):
            return a.verify_core(root, pin, a.Budget(), time.monotonic() + 20, **kwargs)

    def proof(self):
        info = q.snapshot(self.root / "valid")
        return info, self.core(self.root / "valid", info["manifest_digest"], strategy="windowed")

    def test_window_boundaries_hash_every_byte_and_close_each_mapping(self):
        granularity = a.mmap.ALLOCATIONGRANULARITY
        for size in (granularity - 1, granularity, granularity + 1, 4 * granularity + 17):
            raw = bytes(v % 251 for v in range(size))
            p = self.root / str(size)
            p.write_bytes(raw)
            seen, h = [], hashlib.sha256()
            with p.open("rb", buffering=0) as stream, patch.object(a, "WINDOW", granularity):
                with closing(a.blocks(stream, size, "windowed")) as chunks:
                    for block in chunks:
                        self.assertTrue(all(v.closed for v in seen))
                        h.update(block)
                        seen.append(block)
                        self.assertLessEqual(len(block), granularity)
            self.assertTrue(all(v.closed for v in seen))
            self.assertEqual(h.digest(), hashlib.sha256(raw).digest())
            self.assertEqual(len(seen), (size + granularity - 1) // granularity)

    def test_mapping_has_read_only_access(self):
        p = self.root / "item"
        p.write_bytes(b"invented mapping data")
        with p.open("rb", buffering=0) as stream, closing(a.blocks(stream, p.stat().st_size, "windowed")) as chunks:
            block = next(chunks)
            with self.assertRaises(TypeError):
                block[0] = 0
        self.assertTrue(block.closed)
        self.assertEqual(p.read_bytes(), b"invented mapping data")

    def test_caller_exception_closes_outstanding_mapping(self):
        p = self.root / "item"
        p.write_bytes(b"invented")
        with p.open("rb", buffering=0) as stream:
            with self.assertRaises(RuntimeError):
                with closing(a.blocks(stream, p.stat().st_size, "windowed")) as chunks:
                    block = next(chunks)
                    raise RuntimeError("invented consumer failure")
        self.assertTrue(block.closed)

    def test_expired_check_prevents_next_mapping(self):
        p = self.root / "item"
        p.write_bytes(b"x" * 8192)
        calls = [0]

        def check():
            calls[0] += 1
            if calls[0] == 2:
                raise a.StoreRejected("deadline")

        with p.open("rb", buffering=0) as stream, patch.object(a, "WINDOW", 4096):
            with closing(a.blocks(stream, 8192, "windowed", check=check)) as chunks:
                block = next(chunks)
                with self.assertRaises(a.StoreRejected):
                    next(chunks)
        self.assertTrue(block.closed)
        self.assertEqual(calls[0], 2)

    def test_default_reader_remains_stream_with_v1_proof(self):
        info = q.snapshot(self.root / "default")
        with patch.object(a.mmap, "mmap", side_effect=AssertionError("Must not map default")):
            proof = self.core(self.root / "default", info["manifest_digest"])
        self.assertEqual(proof["schema"], "readonly-artifact-proof-v1")
        self.assertNotIn("read_strategy", proof)

    def test_model_only_maps_while_text_and_metadata_stream(self):
        info = q.snapshot(self.root / "candidate")
        with patch.object(a, "blocks", wraps=a.blocks) as reader:
            proof = self.core(self.root / "candidate", info["manifest_digest"], strategy="windowed")
        self.assertEqual([c.args[2] for c in reader.call_args_list].count("windowed"), 1)
        self.assertEqual([c.args[2] for c in reader.call_args_list].count("stream"), 4)
        self.assertEqual(proof["mapped_bytes"], info["model_bytes"])
        self.assertEqual(proof["mapped_model_digest"], info["model_digest"])

    def test_mapping_failure_rejects_without_stream_fallback(self):
        info = q.snapshot(self.root / "candidate")
        with patch.object(a.mmap, "mmap", side_effect=OSError("invented unsupported mapping")) as mapping:
            with self.assertRaises(a.StoreRejected) as raised:
                self.core(self.root / "candidate", info["manifest_digest"], strategy="windowed")
        mapping.assert_called_once()
        self.assertEqual(raised.exception.code, "invalid")

    def test_unknown_strategy_rejected_before_worker_or_file_access(self):
        for strategy in ("unknown", None, True, ["windowed"]):
            with patch.object(a.multiprocessing, "get_context", side_effect=AssertionError("No worker")):
                with self.assertRaises(a.StoreRejected) as raised:
                    a.supervised_verify(self.root, "sha256:" + "a" * 64, strategy=strategy)
            self.assertEqual(raised.exception.code, "strategy")

    def test_strategy_and_full_mapped_coverage_bound_into_proof(self):
        info, proof = self.proof()
        proof["peak_rss_kib"] = 10000
        a.validate_proof(proof, info["manifest_digest"], a.Budget(), strategy="windowed")
        with self.assertRaises(a.StoreRejected):
            a.validate_proof(proof, info["manifest_digest"], a.Budget())
        for key, value in [("mapped_bytes", 1), ("mapped_windows", 2), ("mapped_windows", True),
                           ("mapped_model_digest", "sha256:" + "f" * 64), ("read_strategy", "stream"),
                           ("schema", "readonly-artifact-proof-v1")]:
            wrong = copy.deepcopy(proof)
            wrong[key] = value
            with self.subTest(key=key), self.assertRaises(a.StoreRejected):
                a.validate_proof(wrong, info["manifest_digest"], a.Budget(), strategy="windowed")

    def test_cross_window_model_records_tail_and_preserves_original(self):
        root = self.root / "cross"
        info = q.snapshot(root, "W02_window_plus_tail")
        p = root / "blobs" / info["model_digest"].replace(":", "-")
        before = p.read_bytes()
        proof = self.core(root, info["manifest_digest"], strategy="windowed")
        self.assertEqual(proof["mapped_windows"], 2)
        self.assertEqual(proof["mapped_bytes"], a.WINDOW + 73)
        self.assertEqual(before, p.read_bytes())

    def test_fresh_fixture_matrix_through_candidate(self):
        skipped = {"W15_writable", "W16_cancel_after_start", "W17_expired", "W18_aggregate_budget", "W25_unknown_strategy"}
        for name, expected in q.CASES:
            if name in skipped:
                continue
            with self.subTest(case=name):
                root = self.root / name
                info = q.snapshot(root, name)
                if expected == "ok":
                    self.core(root, info["manifest_digest"], strategy="windowed")
                else:
                    with self.assertRaises(a.StoreRejected) as raised:
                        self.core(root, info["manifest_digest"], strategy="windowed")
                    self.assertEqual(raised.exception.code, expected)

    def test_text_cap_stays_one_mebibyte(self):
        self.assertEqual(a.CHUNK, 1024**2)
        self.assertEqual(a.WINDOW, 16 * 1024**2)
        info = q.snapshot(self.root / "text", "W11_oversize_text")
        with self.assertRaises(a.StoreRejected) as raised:
            self.core(self.root / "text", info["manifest_digest"], strategy="windowed")
        self.assertEqual(raised.exception.code, "size")

    def test_kernel_writable_boundary_still_rejected(self):
        info = q.snapshot(self.root / "writable")
        with patch.object(a, "readonly", return_value=False), self.assertRaises(a.StoreRejected) as raised:
            a.verify_core(self.root / "writable", info["manifest_digest"], a.Budget(), time.monotonic() + 20, strategy="windowed")
        self.assertEqual(raised.exception.code, "readonly")

    def test_policy_is_fixed_and_fixture_preparation_is_fresh(self):
        policy = Path(__file__).parent / "fixtures/windowed_store_policy.json"
        self.assertEqual(json.loads(policy.read_bytes()), q.POLICY)
        self.assertEqual(q.POLICY["pre_post_target_seconds"], 20)
        self.assertEqual(q.POLICY["order"], ["candidate", "baseline"])
        self.assertFalse(q.POLICY["native_inference_qualified"])
        info = q.prepare(self.root / "fixtures")
        self.assertEqual(len(info), 25)
        with self.assertRaises(FileExistsError):
            q.prepare(self.root / "fixtures")


if __name__ == "__main__":
    unittest.main()
