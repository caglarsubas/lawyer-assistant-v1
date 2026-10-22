"""Bounded offline bundle contracts; no inference or private runtime inputs."""

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
from budgeted_quote_bundles import plan_bundles, resolve_bundles  # noqa: E402
from budgeted_quote_cases import CASES, PAIR, suite_sha256  # noqa: E402
from evaluate_budgeted_quotes import evaluate  # noqa: E402
from evaluate_quotation_boundaries import fixture  # noqa: E402

from app.evidence_prompt import canonical  # noqa: E402


class BudgetedQuoteBundles(unittest.TestCase):
    def test_frozen_twelve_case_report_retains_gaps_and_never_claims_model_or_legal_quality(self):
        report = evaluate()
        self.assertEqual(report["suite_sha256"], suite_sha256())
        self.assertEqual(report["summary"], {"cases": 12, "expected_groups": 12, "available_bundle_groups": 9,
            "planned_prompts_within_declared_budget": 11, "blocked_envelopes": 1, "fallback_bundles": 1})
        self.assertEqual(report["inference_calls"], report["http_calls"])
        self.assertEqual(report["inference_calls"], 0)
        self.assertFalse(report["native_or_legal_qualification"])
        self.assertTrue(all(c["source_spans_versions_and_originals_exact"] and
            not c["model_relevance_abstention_instruction_resistance_or_legal_correctness_measured"] for c in report["cases"]))

    def test_late_and_dense_anchors_fit_without_unrelated_passages_or_raised_limits(self):
        for index, units in ((0, 4070), (9, 6298)):
            case = CASES[index]
            originals, _ = fixture(case)
            before = canonical(originals)
            plan = plan_bundles(case["question"], originals)
            self.assertEqual(plan["measurement"]["total_upper_bound_units"], units)
            self.assertTrue(plan["measurement"]["within_budget"])
            self.assertTrue(plan["unused_initial_evidence_ids"])
            self.assertEqual(plan["limits"]["bundles"], 20)
            self.assertEqual(plan["limits"]["parts"], 64)
            self.assertEqual(canonical(originals), before)

    def test_companions_are_atomic_source_spans_in_both_orders_and_across_one_blank(self):
        for index in (1, 2, 3):
            case = CASES[index]
            originals, _ = fixture(case)
            plan = plan_bundles(case["question"], originals)
            bundle = next(b for b in plan["bundles"] if all(any(t in p["text"] for p in b["parts"]) for t in case["groups"][0]))
            resolved = resolve_bundles([bundle["id"]], plan, case["question"], originals)[0]
            self.assertEqual(resolved["parts"], bundle["parts"])
            self.assertTrue(any(p["role"] == "companion" for p in resolved["parts"]))
            for part in resolved["parts"]:
                source = next(p for p in originals if p["id"] == part["evidence_id"])
                self.assertEqual(part["text"], source["text"][part["original_start"]:part["original_end"]])
                self.assertEqual(part["text_sha256"], hashlib.sha256(part["text"].encode()).hexdigest())
            with self.assertRaises(ValueError):
                resolve_bundles([bundle["id"] + ":anchor"], plan, case["question"], originals)
        self.assertIn("blank_separated_companion", bundle["boundary_flags"])
        originals, _ = fixture(CASES[1])
        self.assertIn(PAIR[0] + "\r\n" + PAIR[1], originals[0]["text"])

    def test_coarse_fallback_copies_complete_source_and_clipped_lines_are_omitted(self):
        case = CASES[4]
        originals, _ = fixture(case)
        plan = plan_bundles(case["question"], originals)
        self.assertEqual(plan["bundles"][0]["fallback"], "whole_excerpt")
        self.assertEqual(plan["bundles"][0]["parts"][0]["text"], originals[0]["text"])
        self.assertGreater(len(originals[0]["text"].encode()), 768)
        case = CASES[10]
        originals, _ = fixture(case)
        plan = plan_bundles(case["question"], originals)
        self.assertFalse(plan["bundles"])
        self.assertEqual({o["reason"] for o in plan["omitted_candidates"]}, {"partial_physical_line"})

    def test_unlinked_pages_and_absent_facts_never_become_legal_associations_or_abstention_claims(self):
        for index in (6, 8):
            case = CASES[index]
            originals, _ = fixture(case)
            plan = plan_bundles(case["question"], originals)
            if index == 6:
                self.assertFalse(plan["bundles"])
                self.assertEqual(plan["admission"]["reason"], "no_nominated_bundles")
            else:
                self.assertTrue(plan["bundles"])
                self.assertTrue(all(len({p["evidence_id"] for p in b["parts"]}) == 1 for b in plan["bundles"]))
                self.assertTrue(all("passage_edge_context_not_linked" in b["boundary_flags"] for b in plan["bundles"]))

    def test_budget_pressure_drops_whole_bundles_and_tiny_envelope_blocks_even_empty_resolution(self):
        text = "\n".join(f"SYNTHETIC Z777 ligne {n}: status conservé." for n in range(70))
        originals = [{"id": "one", "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                      "document_id": "d", "document_revision": 1, "document_sha256": "a" * 64}]
        plan = plan_bundles("Z777 status", originals, context_limit=5500)
        self.assertTrue(plan["measurement"]["within_budget"])
        self.assertTrue(plan["bundles"])
        self.assertTrue(any(o["reason"] == "whole_bundle_prompt_budget" for o in plan["omitted_candidates"]))
        self.assertTrue(all(len(b["parts"]) in (2, 3) for b in plan["bundles"]))
        case = CASES[11]
        originals, _ = fixture(case)
        plan = plan_bundles(case["question"], originals, context_limit=1536)
        self.assertEqual(plan["admission"]["state"], "blocked_envelope")
        with self.assertRaises(ValueError):
            resolve_bundles([], plan, case["question"], originals, context_limit=1536)

    def test_version_question_budget_and_part_edits_cannot_reuse_a_plan(self):
        case = CASES[0]
        originals, _ = fixture(case)
        plan = plan_bundles(case["question"], originals)
        ident = plan["bundles"][0]["id"]
        # An unused initial evidence version is still part of the frozen context.
        other = copy.deepcopy(originals)
        other[0]["document_revision"] += 1
        with self.assertRaises(ValueError):
            resolve_bundles([ident], plan, case["question"], other)
        for mutation in (lambda p: p["bundles"][0]["parts"].pop(),
                         lambda p: p["bundles"][0]["parts"][0].update(original_start=True),
                         lambda p: p.update(source_inventory_sha256="b" * 64)):
            value = copy.deepcopy(plan)
            mutation(value)
            with self.assertRaises(ValueError):
                resolve_bundles([ident], value, case["question"], originals)
        for question, limit in (("Other question", 8192), (case["question"], 8191)):
            with self.assertRaises(ValueError):
                resolve_bundles([ident], plan, question, originals, context_limit=limit)

    def test_unknown_duplicate_ids_and_invalid_metadata_fail_closed(self):
        case = CASES[1]
        originals, _ = fixture(case)
        plan = plan_bundles(case["question"], originals)
        ident = plan["bundles"][0]["id"]
        for ids in (["B999"], [ident, ident], [True], ident, [ident] * 21):
            with self.assertRaises(ValueError):
                resolve_bundles(ids, plan, case["question"], originals)
        for field, value in (("document_revision", True), ("document_revision", 0), ("document_sha256", "x")):
            rows = copy.deepcopy(originals)
            rows[0][field] = value
            with self.assertRaises(ValueError):
                plan_bundles(case["question"], rows)
        for limit in (True, 0, "8192"):
            with self.assertRaises(ValueError):
                plan_bundles(case["question"], originals, context_limit=limit)

    def test_fixed_cli_runs_deterministically_without_network_or_overwriting_a_receipt(self):
        import evaluate_budgeted_quotes as driver

        with tempfile.TemporaryDirectory() as directory, patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            target = Path(directory) / "report.json"
            with patch.object(sys, "argv", ["offline", "--output", str(target)]):
                driver.main()
            self.assertEqual(json.loads(target.read_text()), evaluate())
            with patch.object(sys, "argv", ["offline", "--output", str(target)]), self.assertRaises(FileExistsError):
                driver.main()


if __name__ == "__main__":
    unittest.main()
