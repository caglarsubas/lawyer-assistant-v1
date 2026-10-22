"""Frozen offline comparison and source integrity; no provider execution."""

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from budgeted_quote_bundles import sha  # noqa: E402
from bundle_adapter_fixture import ControlledExchange  # noqa: E402
from diverse_quote_bundles import MAX_LINES, envelope, plan_diverse, resolve_diverse  # noqa: E402
from evaluate_source_diversity import evaluate  # noqa: E402
from source_diversity_cases import CASES, SUITE_SHA256, originals_for  # noqa: E402

from app.evidence_prompt import canonical  # noqa: E402


class SourceDiversityContracts(unittest.TestCase):
    def context(self, index=3):
        case = CASES[index]
        sources = originals_for(case)
        limit = case.get("context_limit", 8192)
        return case, sources, plan_diverse(case["question"], sources, context_limit=limit)

    def test_frozen_same_suite_comparison_keeps_improvements_and_failures(self):
        report = evaluate()
        self.assertEqual(report["suite_sha256"], SUITE_SHA256)
        self.assertEqual(SUITE_SHA256, "d392cf5a72e166bf5cdbd6d3425d3a55f8e944e5cdec6edf231944c7ab033174")
        self.assertEqual(report["summary"], {"cases": 16, "expected_groups": 31,
            "v1": {"available_groups": 21, "alternate_wording_cases": 3, "alternate_all_groups_available": 0,
                   "adverse_source_cases": 7, "both_sides_available": 4, "prompts_within_budget": 15,
                   "blocked_envelopes": 1, "unmatched_fallback_bundles": 0},
            "v2": {"available_groups": 26, "alternate_wording_cases": 3, "alternate_all_groups_available": 2,
                   "adverse_source_cases": 7, "both_sides_available": 6, "prompts_within_budget": 15,
                   "blocked_envelopes": 1, "unmatched_fallback_bundles": 5}})
        self.assertEqual({c["case"] for c in report["cases"] if c["v2"]["groups"] and not c["v2"]["all_groups_available"]},
                         {"P1203", "P1209", "P1211", "P1212"})
        self.assertEqual(report["inference_calls"], report["http_calls"])
        self.assertEqual(report["inference_calls"], 0)
        self.assertFalse(report["native_or_legal_qualification"])

    def test_source_round_robin_precedes_revisiting_a_source_and_labels_unmatched_evidence(self):
        case, sources, plan = self.context()
        self.assertNotEqual(plan["bundles"][0]["source_version"], plan["bundles"][1]["source_version"])
        self.assertEqual(plan["bundles"][1]["nomination"], "unmatched_source_fallback")
        self.assertEqual(plan["bundles"][0]["nomination"], "query_overlap")
        by_id = {p["id"]: p for p in sources}
        found = {by_id[p["evidence_id"]]["document_id"] for b in plan["bundles"][:2] for p in b["parts"]}
        self.assertEqual(found, {s["document_id"] for s in sources})
        self.assertTrue(any(p["role"] == "companion" for p in plan["bundles"][1]["parts"]))
        self.assertTrue(plan["omitted_candidates"])
        self.assertEqual(plan["measurement"]["context_limit_units"], case["context_limit"])

    def test_revisions_are_separate_sources_and_conflicting_hashes_cannot_alias_a_revision(self):
        case, sources, plan = self.context(5)
        self.assertEqual(len({p["document_id"] for p in sources}), 1)
        self.assertEqual(len({b["source_version"] for b in plan["bundles"]}), 2)
        changed = copy.deepcopy(sources)
        changed[1]["document_revision"] = changed[0]["document_revision"]
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            plan_diverse(case["question"], changed)

    def test_unmatched_fallback_is_not_semantic_relevance_absence_or_abstention(self):
        for index in (0, 1, 2, 7):
            case, sources, plan = self.context(index)
            self.assertTrue(plan["bundles"])
            self.assertEqual(plan["bundles"][0]["nomination"], "unmatched_source_fallback")
            self.assertIn("unmatched_fallback_not_relevance", plan["limitations"])
            self.assertEqual(plan["bundles"][0]["parts"][0]["original_start"], 0)
            self.assertEqual(plan["admission"]["state"], "prepared_only")
            self.assertTrue(plan["admission"]["not_execution_authorization"])
            self.assertEqual(len(sources), 1)
        self.assertFalse(CASES[7]["groups"])

    def test_whole_coarse_fallback_and_unlinked_conditions_never_trim_or_join_sources(self):
        case, sources, plan = self.context(9)
        self.assertEqual(plan["bundles"][0]["fallback"], "whole_passage")
        self.assertEqual(plan["bundles"][0]["parts"][0]["text"], sources[0]["text"])
        self.assertGreater(len(sources[0]["text"].encode()), 768)
        self.assertLessEqual(len(sources[0]["text"].encode()), 1800)
        case, sources, plan = self.context(8)
        self.assertIn("separator_context_not_linked", {f for b in plan["bundles"] for f in b["boundary_flags"]})
        self.assertTrue(all(len({p["evidence_id"] for p in b["parts"]}) == 1 for b in plan["bundles"]))
        text = "\n".join("Zq " + "x" * 900 for _ in range(3))
        source = {**sources[0], "text": text, "text_sha256": sha(text)}
        value = plan_diverse("Zq", [source])
        self.assertFalse(value["bundles"])
        self.assertEqual({o["reason"] for o in value["omitted_candidates"]}, {"no_complete_coarse_fallback"})

    def test_exact_unicode_spans_messages_and_full_inventory_survive_resolution(self):
        case, sources, plan = self.context(12)
        before = canonical(sources)
        messages, measured = envelope(case["question"], plan["bundles"], 8192)
        self.assertEqual(measured, plan["measurement"])
        self.assertEqual(sha(canonical(messages)), measured["messages_sha256"])
        resolved = resolve_diverse([b["id"] for b in plan["bundles"]], plan, case["question"], sources)
        for b in resolved:
            for p in b["parts"]:
                original = next(s for s in sources if s["id"] == p["evidence_id"])
                self.assertEqual(p["text"], original["text"][p["original_start"]:p["original_end"]])
                self.assertEqual(p["text_sha256"], sha(p["text"]))
        self.assertIn("\r\n", sources[0]["text"])
        self.assertEqual(canonical(sources), before)
        self.assertNotIn("document_sha256", messages[1]["content"])

    def test_omitted_source_changes_and_forged_plans_cannot_reuse_selection(self):
        case, sources, plan = self.context(11)
        self.assertTrue(plan["unrepresented_evidence_ids"])
        self.assertEqual(plan["inventory"]["selected_evidence_passages"], 8)
        self.assertEqual(len(plan["unrepresented_source_versions"]), 2)
        changed = copy.deepcopy(sources)
        changed[-1]["document_revision"] += 1
        with self.assertRaises(ValueError):
            resolve_diverse([], plan, case["question"], changed)
        for mutation in (lambda p: p["bundles"][0]["parts"].pop(),
                         lambda p: p["bundles"][0].update(nomination="reviewed_relevant"),
                         lambda p: p.update(source_inventory_sha256="b" * 64),
                         lambda p: p["bundles"][0]["parts"][0].update(original_start=True)):
            altered = copy.deepcopy(plan)
            mutation(altered)
            with self.assertRaises(ValueError):
                resolve_diverse([], altered, case["question"], sources)
        for question, limit in ((case["question"] + " other", 8192), (case["question"], 8191)):
            with self.assertRaises(ValueError):
                resolve_diverse([], plan, question, sources, context_limit=limit)

    def test_blocked_envelope_and_unknown_duplicate_anchor_only_ids_fail_closed(self):
        case, sources, plan = self.context(10)
        self.assertEqual(plan["admission"]["state"], "blocked_envelope")
        with self.assertRaises(ValueError):
            resolve_diverse([], plan, case["question"], sources, context_limit=1536)
        case, sources, plan = self.context(0)
        for ids in (["D999"], ["D1", "D1"], ["D1:anchor"], [True], "D1"):
            with self.assertRaises(ValueError):
                resolve_diverse(ids, plan, case["question"], sources)

    def test_invalid_metadata_duplicate_ids_and_work_limits_block_before_nomination(self):
        case, sources, _ = self.context(0)
        for patch in ({"document_revision": True}, {"document_revision": 0}, {"document_sha256": "bad"},
                      {"text_sha256": "b" * 64}, {"document_id": ""}, {"id": ""}):
            with self.assertRaises(ValueError):
                plan_diverse(case["question"], [{**sources[0], **patch}])
        with self.assertRaises(ValueError):
            plan_diverse(case["question"], sources * 2)
        with self.assertRaises(ValueError):
            plan_diverse(case["question"], sources * 2001)
        for text, reason in (("x" * 2_000_001, "source scan"), ("x\n" * (MAX_LINES + 1), "physical-line work")):
            with self.assertRaisesRegex(ValueError, reason):
                plan_diverse("x", [{**sources[0], "text": text, "text_sha256": sha(text)}])
        for limit in (True, 0, -1, "8192"):
            with self.assertRaises(ValueError):
                plan_diverse(case["question"], sources, context_limit=limit)

    def test_existing_disposable_adapter_cannot_silently_activate_the_new_recipe(self):
        case, sources, plan = self.context(0)
        with ControlledExchange() as exchange:
            with self.assertRaises(ValueError):
                exchange.adapter().select(case["question"], sources, plan)
            self.assertFalse(exchange.requests)
        self.assertFalse(json.loads(envelope(case["question"], plan["bundles"], 8192)[0][1]["content"]).get("expected_groups"))


if __name__ == "__main__":
    unittest.main()
