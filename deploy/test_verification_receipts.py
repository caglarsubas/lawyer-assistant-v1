import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pinned_store_qualification as p  # noqa: E402
import volume_store_qualification as v  # noqa: E402
import windowed_store_qualification as w  # noqa: E402


class Contracts(unittest.TestCase):
    def read(self, name):
        return json.loads((Path(__file__).parent / "fixtures" / (name + ".json")).read_bytes())

    def test_first_unpinned_candidate_remains_unqualified(self):
        self.assertEqual(w.grade_cases(self.read("windowed_first_cases"))["passed"], 25)
        info = self.read("windowed_first_info")
        candidate = self.read("windowed_first_candidate")
        result = w.grade_profile(candidate, info)
        self.assertEqual(result["completed_verifications"], 2)
        self.assertFalse(result["hard_budget_pass"])
        self.assertFalse(result["twenty_second_pre_post_target_pass"])
        self.assertEqual([r["error"] for r in candidate["jobs"]], ["changed"] * 5)
        self.assertEqual(w.grade_profile(self.read("windowed_first_baseline"), info)["completed_verifications"], 12)

    def test_pinned_host_bind_miss_is_retained(self):
        self.assertEqual(p.grade_cases(self.read("pinned_first_cases"))["passed"], 13)
        info = self.read("pinned_first_info")
        for name in ("candidate", "baseline"):
            result = p.grade_profile(self.read("pinned_first_" + name), info)
            self.assertEqual(result["completed_verifications"], 12)
            self.assertTrue(result["hard_budget_pass"])
            self.assertTrue(result["memory_target_pass"])
            self.assertFalse(result["twenty_second_pre_post_target_pass"])

    def test_fresh_VM_volume_meets_target_without_promoting_inference(self):
        result = v.grade(self.read("volume_first_report"), self.read("volume_first_info"))
        candidate = result["candidate"]
        self.assertEqual(candidate["completed_verifications"], 12)
        self.assertTrue(candidate["twenty_second_pre_post_target_pass"])
        self.assertTrue(candidate["hard_budget_pass"])
        self.assertTrue(candidate["memory_target_pass"])
        self.assertFalse(candidate["native_inference_qualified"])
        self.assertFalse(candidate["research_jobs_qualified"])
        self.assertFalse(result["baseline"]["twenty_second_pre_post_target_pass"])
        self.assertEqual(self.read("volume_store_policy"), v.POLICY)

    def test_skipped_bytes_or_descriptors_cannot_be_promoted(self):
        info = self.read("volume_first_info")
        for field, value in [("mapped_bytes", 1), ("retained_blob_descriptors", 0), ("retained_descriptors_rechecked", False)]:
            report = self.read("volume_first_report")
            report["candidate"]["jobs"][0]["proofs"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                v.grade(report, info)

    def test_partial_or_slow_jobs_do_not_meet_target(self):
        info, report = self.read("volume_first_info"), self.read("volume_first_report")
        report["candidate"]["jobs"][0]["proofs"].pop()
        result = v.grade(report, info)["candidate"]
        self.assertEqual(result["completed_verifications"], 11)
        self.assertFalse(result["twenty_second_pre_post_target_pass"])
        report = self.read("volume_first_report")
        report["candidate"]["jobs"][0]["elapsed_seconds"] = 20.0001
        self.assertFalse(v.grade(report, info)["candidate"]["twenty_second_pre_post_target_pass"])

    def test_profile_filesystem_and_read_only_envelope_are_required(self):
        info, original = self.read("volume_first_info"), self.read("volume_first_report")
        for key, value in [("filesystem", "virtiofs"), ("kernel_readonly", False), ("order", ["baseline", "candidate"])]:
            report = copy.deepcopy(original)
            report[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                v.grade(report, info)

    def test_volume_preparer_needs_marker_and_nonroot_final_owner(self):
        with patch.object(v.Path, "is_file", return_value=False), self.assertRaises(ValueError):
            v.prepare_volume(501, 20)
        with patch.object(v, "require_marker", return_value=None):
            for uid, gid in [(0, 20), (True, 20), (501, -1), (501, False)]:
                with self.subTest(uid=uid, gid=gid), self.assertRaises(ValueError):
                    v.prepare_volume(uid, gid)
        self.assertEqual(v.POLICY["preparation_flush_bytes"], 64 * 1024**2)
        self.assertEqual(v.POLICY["preparation_model_copies"], 0)


if __name__ == "__main__":
    unittest.main()
