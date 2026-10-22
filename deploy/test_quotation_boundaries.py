"""Model-free boundary geometry; none of these tests qualify inference/legal use."""

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from evaluate_quotation_boundaries import availability, evaluate, fixture  # noqa: E402
from offline_quotation_boundaries import candidate_catalog, candidate_prompt, resolve_offline  # noqa: E402
from quotation_boundary_cases import CASES, CONDITION, NEGATIVE, SUITE_SHA256, pdf_bytes  # noqa: E402

from app.context_packing import pack_private_context  # noqa: E402
from app.evidence_prompt import canonical, quote_catalog  # noqa: E402


def setup(case):
    originals, _ = fixture(case)
    pack = pack_private_context(case["question"], originals, context_limit=8192, candidate_profile=True)
    return originals, pack["evidence"], candidate_catalog(pack["evidence"], originals)


class QuotationBoundaries(unittest.TestCase):
    def test_frozen_matrix_geometry_reports_benefits_and_failures_without_quality_claim(self):
        report = evaluate()
        self.assertEqual(report["suite_sha256"], SUITE_SHA256)
        self.assertEqual(report["summary"], {"cases": 10, "expected_groups": 11, "baseline_available_groups": 11,
            "candidate_available_groups": 8, "candidate_geometry_admitted_cases": 6,
            "candidate_budget_exceeded_cases": 2, "candidate_omissions_present_cases": 2})
        self.assertFalse(report["native_or_legal_qualification"])
        self.assertEqual(report["inference_calls"], report["http_calls"])
        self.assertEqual(report["inference_calls"], 0)
        self.assertTrue(all(c["source_spans_and_versions_exact"] and c["originals_unchanged"] for c in report["cases"]))
        self.assertTrue(all(not c["model_selection_relevance_abstention_or_injection_resistance_measured"] for c in report["cases"]))

    def test_adjacent_unicode_negation_and_condition_survive_both_directions_without_rewriting(self):
        for case in CASES[1:3]:
            originals, evidence, plan = setup(case)
            before = copy.deepcopy(originals)
            group = case["groups"][0]
            ident = next(i for i, q in plan["catalog"].items() if all(t in q["text"] for t in group))
            resolved = resolve_offline([ident], plan, evidence, originals)[0]
            self.assertTrue(all(t in resolved["text"] for t in group))
            self.assertLess(len(resolved["text"].encode()), min(len(q["text"].encode()) for q in quote_catalog(evidence).values()
                                                              if all(t in q["text"] for t in group)))
            self.assertEqual(originals, before)
        originals, evidence, plan = setup(CASES[1])
        self.assertTrue(any(NEGATIVE + "\r\n" + CONDITION in q["text"] for q in plan["catalog"].values()))
        for q in plan["catalog"].values():
            p = next(p for p in originals if p["id"] == q["evidence_id"])
            self.assertEqual(q["text"], p["text"][q["original_start"]:q["original_end"]])
            self.assertEqual(hashlib.sha256(q["text"].encode()).hexdigest(), q["text_sha256"])

    def test_page_boundaries_and_blank_separators_never_become_a_synthetic_joint_quote(self):
        case = CASES[7]
        _, _, plan = setup(case)
        self.assertEqual(availability(case["groups"], plan["catalog"])["available_groups"], 0)
        case = CASES[8]
        originals, _, plan = setup(case)
        texts = [g[0] for g in case["groups"]]
        self.assertEqual(availability(case["groups"], plan["catalog"])["available_groups"], 2)
        self.assertFalse(any(all(t in q["text"] for t in texts) for q in plan["catalog"].values()))
        self.assertTrue(all(q["text"] in next(p["text"] for p in originals if p["id"] == q["evidence_id"])
                            for q in plan["catalog"].values()))

    def test_overlong_lines_count_caps_and_prompt_budget_fail_without_clipping_or_expansion(self):
        originals, evidence, plan = setup(CASES[6])
        self.assertFalse(plan["catalog"])
        self.assertEqual({r["reason"] for r in plan["omitted_windows"]}, {"whole_window_byte_limit"})
        self.assertEqual(evidence[0]["text"], originals[0]["text"])
        _, evidence, plan = setup(CASES[-1])
        self.assertEqual(len(plan["catalog"]), 64)
        self.assertTrue(any(r["reason"] == "catalog_count_limit" for r in plan["omitted_windows"]))
        self.assertFalse(candidate_prompt(CASES[-1]["question"], evidence, plan, 8192)["within_budget"])
        for limit in (True, 0, -1, "8192"):
            with self.assertRaises(ValueError):
                candidate_prompt("SYNTHETIC", evidence, plan, limit)

    def test_clipped_physical_lines_are_omitted_and_unicode_offsets_are_code_points(self):
        full = "SYNTHETIC önceki satır\r\nİğne e\u0301 kayıt sonu.\r\nSon satır"
        original = {"id": "x", "text": full, "text_sha256": hashlib.sha256(full.encode()).hexdigest(),
                    "document_id": "d", "document_revision": 7, "document_sha256": "a" * 64}
        start = full.index("İğne") + 1
        evidence = [{**original, "text": full[start:-3], "excerpt_start": start, "excerpt_end": len(full) - 3,
                     "full_passage_length": len(full)}]
        plan = candidate_catalog(evidence, [original])
        self.assertFalse(plan["catalog"])
        self.assertTrue(all(row["reason"] == "partial_physical_line" for row in plan["omitted_windows"]))
        self.assertEqual(plan["source_pins"][0]["excerpt_start"], start)

    def test_stale_versions_altered_offsets_hashes_and_unknown_references_cannot_resolve(self):
        originals, evidence, plan = setup(CASES[1])
        ident = next(iter(plan["catalog"]))
        for ids in (["Q999"], [ident, ident], [True], ident, [ident] * 21):
            with self.assertRaises(ValueError):
                resolve_offline(ids, plan, evidence, originals)
        changed = copy.deepcopy(plan)
        changed["catalog"][ident]["start"] += 1
        with self.assertRaises(ValueError):
            resolve_offline([ident], changed, evidence, originals)
        for field, value in (("document_revision", 2), ("document_sha256", "b" * 64), ("text_sha256", "c" * 64)):
            sources = copy.deepcopy(originals)
            sources[0][field] = value
            with self.assertRaises(ValueError):
                resolve_offline([ident], plan, evidence, sources)
        with self.assertRaises(ValueError):
            candidate_catalog(evidence, [])
        with self.assertRaises(ValueError):
            candidate_catalog(evidence, originals + originals)
        for sources in ([{}], [{"id": "x", "text": "x" * 2_000_001}], originals * 2001):
            with self.assertRaises(ValueError):
                candidate_catalog(evidence, sources)

    def test_unknown_and_duplicate_evidence_and_malformed_utf8_are_rejected(self):
        originals, evidence, _ = setup(CASES[1])
        for values in (evidence * 2, [{**evidence[0], "text": "\ud800"}]):
            with self.assertRaises(ValueError):
                candidate_catalog(values, originals)

    def test_missing_and_hostile_fixtures_do_not_claim_model_abstention_or_injection_success(self):
        report = evaluate()
        missing = next(c for c in report["cases"] if c["case"] == "missing-registration")
        self.assertFalse(missing["candidate"]["oracle_applicable"])
        self.assertGreater(missing["candidate"]["quotes"], 0)
        for case in (CASES[4], CASES[5]):
            originals, evidence, plan = setup(case)
            self.assertEqual(resolve_offline([], plan, evidence, originals), [])
            with self.assertRaises(ValueError):
                resolve_offline(["Q999"], plan, evidence, originals)

    def test_fixed_cli_is_deterministic_and_offline_without_keys_or_mutated_inputs(self):
        import evaluate_quotation_boundaries as driver

        with tempfile.TemporaryDirectory() as folder, patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            output = Path(folder) / "report.json"
            with patch.object(sys, "argv", ["offline", "--output", str(output)]):
                driver.main()
            report = json.loads(output.read_text())
            self.assertEqual(report, evaluate())
            with patch.object(sys, "argv", ["offline", "--output", str(output)]), self.assertRaises(FileExistsError):
                driver.main()
        for case in (CASES[0], CASES[8]):
            self.assertEqual(pdf_bytes(case), pdf_bytes(case))
        self.assertEqual(hashlib.sha256(canonical(CASES).encode()).hexdigest(), SUITE_SHA256)


if __name__ == "__main__":
    unittest.main()
