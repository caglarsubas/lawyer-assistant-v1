"""Whole-source atomicity, packet cost, caps and immutable evidence contracts."""

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import whole_passage_packets as packets  # noqa: E402
from disposable_diverse_adapter import MARKER, DisposableDiverseAdapter  # noqa: E402
from evaluate_passage_packets import evaluate, groups_for  # noqa: E402
from native_acceptance_plan import validate_plan  # noqa: E402
from offline_quotation_boundaries import sha  # noqa: E402
from passage_packet_cases import CASES, SUITE_SHA256, originals_for  # noqa: E402

from app.evidence_prompt import canonical  # noqa: E402
from app.provider import Provider  # noqa: E402


class WholePassagePacketContracts(unittest.TestCase):
    def prepare(self, index=8, max_packets=8):
        case = CASES[index]
        sources = originals_for(case)
        limit = case.get("context_limit", 8192)
        return case, sources, packets.plan_packets(case["question"], sources, context_limit=limit, max_packets=max_packets)

    def resolve(self, case, sources, plan, packet_index=0, ids=None):
        packet = plan["packets"][packet_index]
        return packets.resolve_packet(packet["id"], ids if ids is not None else [b["id"] for b in packet["bundles"]],
                                      plan, case["question"], sources, context_limit=case.get("context_limit", 8192),
                                      max_packets=plan["limits"]["max_packets"])

    def test_frozen_fresh_comparison_retains_gaps_and_aggregate_cost(self):
        report = evaluate()
        self.assertEqual(SUITE_SHA256, "aedb0ac14eb2ba9a6ef5c6df0c23c85a07148875efe9cc87fc8ef9c7bae4199e")
        self.assertEqual(report["summary"], {"cases": 16, "source_passages": 294, "source_versions": 117,
            "expected_groups": 23, "explicit_empty_cases": 3,
            "frozen_v2_single_envelope": {"available_groups": 9, "unavailable_groups": 14},
            "whole_single": {"available_groups": 13, "unavailable_groups": 10, "planned_envelopes": 12,
                "planned_upper_bound_units": 42018, "copied_text_utf8_bytes": 5776, "blocked_envelopes": 1, "no_candidates": 3},
            "whole_multi": {"available_groups": 18, "unavailable_groups": 5, "planned_envelopes": 32,
                "planned_upper_bound_units": 144178, "copied_text_utf8_bytes": 15794, "blocked_envelopes": 1, "no_candidates": 3}})
        missing = [r["case"] for r in report["cases"] if any(not g["available_in_one_atomic_bundle"] for g in r["whole_multi"]["groups"])]
        self.assertEqual(missing, ["P1504", "P1507", "P1510", "P1511", "P1514"])

    def test_complete_unicode_spaces_separators_and_long_line_never_clipped(self):
        for index in (0, 1, 2, 5):
            case, sources, plan = self.prepare(index)
            before = canonical(sources)
            result = self.resolve(case, sources, plan)
            self.assertEqual(result["bundles"][0]["parts"][0]["text"], sources[0]["text"])
            self.assertEqual(result["bundles"][0]["parts"][0]["original_end"], len(sources[0]["text"]))
            self.assertEqual(result["bundles"][0]["parts"][0]["text_sha256"], sha(sources[0]["text"]))
            self.assertTrue(result["bundles"][0]["document_completeness_unknown"])
            self.assertEqual(canonical(sources), before)

    def test_separate_passages_do_not_become_one_complete_condition(self):
        case, sources, plan = self.prepare(6)
        result = self.resolve(case, sources, plan)
        self.assertEqual(len(result["bundles"]), 2)
        self.assertFalse(groups_for(case, sources, result["bundles"])[0]["available_in_one_atomic_bundle"])
        self.assertEqual([b["parts"][0]["text"] for b in result["bundles"]], [p["text"] for p in sources])

    def test_packets_obey_existing_per_call_budgets_and_global_eight_packet_cap(self):
        for index in (8, 9, 10):
            case, sources, plan = self.prepare(index)
            seen = []
            for packet in plan["packets"]:
                self.assertLessEqual(len(packet["bundles"]), 8)
                self.assertLessEqual(packet["copied_text_utf8_bytes"], 4000)
                self.assertLessEqual(packet["measurement"]["total_upper_bound_units"], 8192)
                self.assertTrue(packet["not_execution_authorization"])
                seen += [b["id"] for b in packet["bundles"]]
            self.assertLessEqual(len(plan["packets"]), 8)
            self.assertEqual(len(seen), len(set(seen)))
            self.assertLessEqual(plan["aggregate_budget"]["planned_copied_text_utf8_bytes"], 32000)
            self.assertLessEqual(plan["aggregate_budget"]["planned_upper_bound_units"], 65536)
            self.assertTrue(plan["unrepresented_evidence_ids"] or len(seen) == len(sources))

    def test_one_vs_eight_capacity_ablation_keeps_first_packet_bytes_identical(self):
        case, sources, multiple = self.prepare(8)
        single = packets.plan_packets(case["question"], sources, max_packets=1)
        self.assertEqual(single["packets"][0], multiple["packets"][0])
        self.assertGreater(multiple["aggregate_budget"]["future_completion_request_upper_bound"], 1)
        self.assertGreater(multiple["aggregate_budget"]["planned_upper_bound_units"], single["aggregate_budget"]["planned_upper_bound_units"])
        self.assertNotEqual(single["plan_sha256"], multiple["plan_sha256"])

    def test_cross_packet_unknown_legacy_and_duplicate_ids_fail(self):
        case, sources, plan = self.prepare()
        foreign = plan["packets"][1]["bundles"][0]["id"]
        first = plan["packets"][0]["bundles"][0]["id"]
        for ids in [[foreign], ["D1"], ["B1"], ["W999"], [first, first], [True], None, first]:
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                packets.resolve_packet("P1", ids, plan, case["question"], sources)
        with self.assertRaises(ValueError):
            packets.resolve_packet("P999", [], plan, case["question"], sources)

    def test_changed_unused_source_or_manifest_cannot_resolve_old_selection(self):
        case, sources, plan = self.prepare(9)
        unused = next(p for p in sources if p["id"] in plan["unrepresented_evidence_ids"])
        unused["text"] += " Yeni kayıt."
        unused["text_sha256"] = sha(unused["text"])
        with self.assertRaises(ValueError):
            self.resolve(case, sources, plan)
        case, sources, plan = self.prepare()
        for mutate in [lambda p: p["packets"][0]["messages"][0].update(content="changed"),
                       lambda p: p["packets"][0]["bundles"][0]["parts"][0].update(original_end=1),
                       lambda p: p["limits"].update(max_packets=1), lambda p: p.update(plan_sha256="0" * 64)]:
            altered = copy.deepcopy(plan)
            mutate(altered)
            with self.assertRaises(ValueError):
                self.resolve(case, sources, altered)
        with self.assertRaises(ValueError):
            packets.resolve_packet("P1", [], plan, case["question"] + " değişti", sources)

    def test_bad_metadata_ambiguous_versions_and_forged_hashes_rejected(self):
        case, sources, _ = self.prepare(4)
        for mutate in [lambda p: p.update(secret="unexpected"), lambda p: p.update(document_revision=True),
                       lambda p: p.update(text_sha256="0" * 64), lambda p: p.update(id=""),
                       lambda p: p.update(document_sha256="bad")]:
            changed = copy.deepcopy(sources)
            mutate(changed[0])
            with self.assertRaises(ValueError):
                packets.plan_packets(case["question"], changed)
        changed = copy.deepcopy(sources)
        changed[1]["document_revision"] = changed[0]["document_revision"]
        with self.assertRaises(ValueError):
            packets.plan_packets(case["question"], changed)

    def test_scan_and_packet_parameter_work_bounds_fail_closed(self):
        case, sources, _ = self.prepare(0)
        for cap in [0, 9, True, "8"]:
            with self.assertRaises(ValueError):
                packets.plan_packets(case["question"], sources, max_packets=cap)
        with self.assertRaises(ValueError):
            packets.plan_packets(case["question"], sources * 2001)
        changed = copy.deepcopy(sources)
        changed[0]["text"] = "A\n" * 20001
        changed[0]["text_sha256"] = sha(changed[0]["text"])
        with self.assertRaises(ValueError):
            packets.plan_packets(case["question"], changed)

    def test_empty_oversize_and_blocked_sources_remain_explicit_no_call_gaps(self):
        for index, state, reason in [(3, "no_candidates_no_call", "whole_passage_text_byte_limit"),
                                     (13, "blocked_envelope", "empty_envelope_budget"),
                                     (14, "no_candidates_no_call", None),
                                     (15, "no_candidates_no_call", "empty_source_passage")]:
            case, sources, plan = self.prepare(index)
            self.assertEqual(plan["admission"]["state"], state)
            self.assertEqual(plan["packets"], [])
            if reason:
                self.assertEqual(plan["omitted_passages"][0]["reason"], reason)
            with self.assertRaises(ValueError):
                packets.resolve_packet("P1", [], plan, case["question"], sources, context_limit=case.get("context_limit", 8192))

    def test_versions_are_separate_and_wire_excludes_grading_fields(self):
        case, sources, plan = self.prepare(4)
        result = self.resolve(case, sources, plan)
        self.assertEqual({b["source_version"] for b in result["bundles"]}, {"S1", "S2"})
        for packet in plan["packets"]:
            payload = json.loads(packet["messages"][1]["content"])
            self.assertEqual(set(payload), {"question", "packet_id", "bundles"})
            self.assertNotIn("groups", canonical(payload))
            self.assertNotIn("expected", canonical(payload))

    def test_changed_caller_context_during_preparation_is_discarded(self):
        case, sources, _ = self.prepare(0)
        envelope = packets.envelope

        def racing(*args):
            result = envelope(*args)
            if args[2]:
                sources[0]["text"] += " Değişiklik."
                sources[0]["text_sha256"] = sha(sources[0]["text"])
            return result

        with patch.object(packets, "envelope", racing), self.assertRaises(ValueError):
            packets.plan_packets(case["question"], sources)

    def test_recipe_cannot_activate_existing_native_adapter_or_certify_abstention(self):
        case, sources, plan = self.prepare(11)
        adapter = DisposableDiverseAdapter(Provider(SimpleNamespace(provider_context_limit=8192)), mode=MARKER)
        with patch.object(Provider, "_complete", side_effect=AssertionError("no inference")):
            with self.assertRaises(ValueError):
                adapter.select(case["question"], sources, plan, {})
            result = self.resolve(case, sources, plan, ids=[])
        self.assertEqual(result["state"], "empty_selection_unqualified")
        self.assertFalse(result["native_or_legal_qualification"])
        self.assertFalse(result["production_activation"])
        self.assertEqual(plan["packets"][0]["bundles"][0]["nomination"], "whole_passage_inventory_not_relevance")

    def test_previous_frozen_acceptance_declaration_still_exactly_validates(self):
        path = ROOT / "docs/evidence/frozen-native-acceptance-plan-v1.json"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), "c3a38ac99547ed84bbfa2ae6dd06b9d92aae63a26dff06117c397e4de2856ed2")
        validate_plan(json.loads(path.read_text()))


if __name__ == "__main__":
    unittest.main()
