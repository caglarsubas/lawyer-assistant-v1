"""v2 wire identity, bounded transport and exact-source result contracts."""

import copy
import json
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from bundle_adapter_fixture import ControlledExchange, settings  # noqa: E402
from disposable_bundle_adapter import MARKER as OLD_MARKER  # noqa: E402
from disposable_diverse_adapter import (  # noqa: E402
    MARKER,
    NEW_EXAMPLE,
    OLD_EXAMPLE,
    DisposableDiverseAdapter,
    prepare_diverse_selection,
    prepared_context,
)
from diverse_adapter_cases import CASES, SUITE_SHA256, originals_for  # noqa: E402
from diverse_quote_bundles import envelope, plan_diverse, sha  # noqa: E402
from evaluate_diverse_adapter import evaluate  # noqa: E402

from app.evidence_prompt import canonical  # noqa: E402
from app.provider import Provider, ProviderError  # noqa: E402


class DisposableDiverseContracts(unittest.TestCase):
    def context(self, index=1):
        case = CASES[index]
        sources = originals_for(case)
        limit = case.get("context_limit", 8192)
        plan = plan_diverse(case["question"], sources, context_limit=limit)
        wire = prepare_diverse_selection(case["question"], sources, plan, context_limit=limit)
        return case, sources, plan, wire, limit

    def adapter(self, limit=8192, **changes):
        return DisposableDiverseAdapter(Provider(settings(provider_context_limit=limit, **changes)), mode=MARKER)

    def test_first_frozen_report_retains_gaps_and_mock_only_scope(self):
        report = evaluate()
        self.assertEqual(report["suite_sha256"], SUITE_SHA256)
        self.assertEqual(SUITE_SHA256, "3f753ee96f34dbad30a12f67632dcd98f1e212b4024c40ad2bd9f4c0d29445de")
        self.assertEqual(report["summary"], {"cases": 14, "source_passages": 215, "source_versions": 55,
            "expected_groups": 20, "available_groups": 13, "adverse_source_cases": 3, "both_sides_available": 3,
            "blocked_before_transport": 1, "no_candidates_no_call": 2, "unmatched_fallback_bundles": 4})
        self.assertEqual(report["counts"], {"mock_metadata_requests": 11, "mock_completion_requests": 11,
            "network_http_calls": 0, "inference_calls": 0})
        self.assertEqual({c["case"] for c in report["cases"] if c["coverage"]["groups"] and not c["coverage"]["all_groups_available"]},
                         {"P1304", "P1306", "P1307", "P1312", "P1313"})
        self.assertFalse(report["native_or_legal_qualification"])

    def test_wire_example_changes_only_system_example_with_distinct_digest_and_equal_budget(self):
        case, sources, plan, wire, limit = self.context(9)
        old, measured = envelope(case["question"], plan["bundles"], limit)
        rebuilt, messages = prepared_context(case["question"], sources, plan, limit)
        self.assertEqual(rebuilt, wire)
        self.assertIn(OLD_EXAMPLE, old[0]["content"])
        self.assertNotIn(OLD_EXAMPLE, messages[0]["content"])
        self.assertIn(NEW_EXAMPLE, messages[0]["content"])
        self.assertEqual(messages[0]["content"], old[0]["content"].replace(OLD_EXAMPLE, NEW_EXAMPLE))
        self.assertEqual(messages[1], old[1])
        self.assertIn("B1", messages[1]["content"])  # Hostile source bytes stay data, not instructions to rewrite.
        self.assertNotEqual(wire["measurement"]["messages_sha256"], wire["planner_messages_sha256"])
        for key in ("utf8_bytes", "total_upper_bound_units", "context_limit_units", "within_budget"):
            self.assertEqual(wire["measurement"][key], measured[key])
        self.assertEqual(wire["measurement"]["messages_sha256"], sha(canonical(messages)))
        self.assertTrue(wire["not_execution_authorization"])

    def test_full_selection_preserves_versions_companions_and_exact_unicode_source_spans(self):
        for index in (1, 4, 10):
            case, sources, plan, wire, limit = self.context(index)
            before = canonical(sources)
            with ControlledExchange():
                result = self.adapter(limit).select(case["question"], sources, plan, wire, context_limit=limit)
            self.assertEqual(result["wire_sha256"], wire["wire_sha256"])
            self.assertTrue(result["selection_coverage"]["all_nominated_bundles_selected"])
            self.assertEqual(result["bundles"][0]["parts"], plan["bundles"][0]["parts"])
            for bundle in result["bundles"]:
                for part in bundle["parts"]:
                    source = next(p for p in sources if p["id"] == part["evidence_id"])
                    self.assertEqual(part["text"], source["text"][part["original_start"]:part["original_end"]])
                    self.assertEqual(part["text_sha256"], sha(part["text"]))
            self.assertEqual(canonical(sources), before)
            self.assertFalse(result["production_activation"])
        self.assertIn("\r\n", sources[0]["text"])

    def test_subset_and_empty_selection_expose_omitted_nominated_sources_without_quality_claims(self):
        case, sources, plan, wire, limit = self.context()
        for selected, state in (([plan["bundles"][0]["id"]], "selection_returned"), ([], "empty_selection_unqualified")):
            with ControlledExchange(lambda _: json.dumps({"bundle_ids": selected})):
                result = self.adapter(limit).select(case["question"], sources, plan, wire)
            coverage = result["selection_coverage"]
            self.assertEqual(result["state"], state)
            self.assertFalse(coverage["all_nominated_bundles_selected"])
            self.assertTrue(coverage["omitted_nominated_bundle_ids"])
            self.assertLess(len(coverage["selected_source_versions"]), len(coverage["available_source_versions"]))
            self.assertFalse(result["model_relevance_abstention_or_legal_qualification"])

    def test_schema_errors_unknown_legacy_anchor_only_and_duplicate_ids_fail_without_retry(self):
        case, sources, plan, wire, limit = self.context()
        responses = ['{"bundle_ids":["B1"]}', '{"bundle_ids":["D999"]}', '{"bundle_ids":["D1:anchor"]}',
            '{"bundle_ids":["D1","D1"]}', '{"bundle_ids":[true]}', '{"bundle_ids":"D1"}',
            '{"bundle_ids":[],"claims":[]}', '{"bundle_ids":[],"bundle_ids":["D1"]}', '[]', 'null',
            '```json\n{"bundle_ids":[]}\n```', '{"bundle_ids":[]}' + ' ' * 4097]
        for content in responses:
            with self.subTest(content=content), ControlledExchange(lambda _: content) as exchange:
                with self.assertRaises(ValueError):
                    self.adapter(limit).select(case["question"], sources, plan, wire)
                self.assertEqual(exchange.counts()["mock_completion_requests"], 1)

    def test_stale_context_manifest_and_unrepresented_source_changes_block_before_http(self):
        case, sources, plan, wire, limit = self.context(12)
        self.assertTrue(plan["unrepresented_evidence_ids"])
        for target, update in (("sources", lambda s: s[-1].update(document_revision=99)),
                               ("plan", lambda p: p["bundles"][0]["parts"].pop()),
                               ("wire", lambda w: w["measurement"].update(messages_sha256="b" * 64)),
                               ("wire", lambda w: w.update(bundle_ids=[]))):
            values = {"sources": copy.deepcopy(sources), "plan": copy.deepcopy(plan), "wire": copy.deepcopy(wire)}
            update(values[target])
            with ControlledExchange() as exchange:
                with self.assertRaises(ValueError):
                    self.adapter(limit).select(case["question"], values["sources"], values["plan"], values["wire"])
                self.assertFalse(exchange.requests)
        with ControlledExchange() as exchange:
            for question, changed_limit in ((case["question"] + " other", limit), (case["question"], limit - 1)):
                with self.assertRaises(ValueError):
                    self.adapter(changed_limit).select(question, sources, plan, wire, context_limit=changed_limit)
            self.assertFalse(exchange.requests)

    def test_context_changes_during_preparation_are_rejected_before_http(self):
        case, sources, plan, wire, limit = self.context()

        def changed(*args):
            value = prepared_context(*args)
            sources[-1]["document_revision"] += 1
            return value

        with ControlledExchange() as exchange, patch("disposable_diverse_adapter.prepared_context", changed):
            with self.assertRaisesRegex(ValueError, "context changed"):
                self.adapter(limit).select(case["question"], sources, plan, wire)
            self.assertFalse(exchange.requests)

    def test_sources_wire_and_provider_limit_changes_during_transport_discard_result(self):
        for target in ("sources", "wire", "limit"):
            case, sources, plan, wire, limit = self.context()
            adapter = self.adapter(limit)

            def changed(_):
                if target == "sources":
                    sources[-1]["document_revision"] += 1
                elif target == "wire":
                    wire["bundle_ids"] = []
                else:
                    adapter.provider.settings.provider_context_limit -= 1
                return '{"bundle_ids":["D1"]}'

            with ControlledExchange(changed) as exchange:
                with self.assertRaisesRegex(ValueError, "context changed"):
                    adapter.select(case["question"], sources, plan, wire)
                self.assertEqual(exchange.counts()["mock_completion_requests"], 1)

    def test_blocked_preview_and_no_candidates_remain_non_authorizing(self):
        case, sources, plan, wire, limit = self.context(11)
        self.assertEqual(wire["admission"], "blocked_envelope")
        with ControlledExchange() as exchange:
            with self.assertRaises(ValueError):
                self.adapter(limit).select(case["question"], sources, plan, wire, context_limit=limit)
            self.assertFalse(exchange.requests)
        for index in (5, 8):
            case, sources, plan, wire, limit = self.context(index)
            with ControlledExchange() as exchange:
                result = self.adapter(limit).select(case["question"], sources, plan, wire)
                self.assertEqual(result["state"], "no_candidates_no_call")
                self.assertFalse(exchange.requests)
        self.assertFalse(result["model_relevance_abstention_or_legal_qualification"])

    def test_existing_provider_auth_model_route_limits_no_fallback_and_502_guards_remain(self):
        case, sources, plan, wire, limit = self.context()
        for field in ("provider_identity_verified", "provider_cloud_fallback_disabled"):
            with ControlledExchange() as exchange:
                with self.assertRaises(ProviderError):
                    self.adapter(limit, **{field: False}).select(case["question"], sources, plan, wire)
                self.assertFalse(exchange.requests)
        with ControlledExchange() as exchange:
            with self.assertRaises(ProviderError):
                self.adapter(limit, provider_base_url="https://8.8.8.8/v1").select(case["question"], sources, plan, wire)
            self.assertFalse(exchange.requests)
        for changes in ({"status": 502}, {"metadata": {"request_key_source": "cloud"}},
                        {"metadata": {"max_model_len": 4096}}, {"completion": {"model": "other"}},
                        {"completion": {"fallback_reason": "upstream"}},
                        {"completion": {"usage": {"completion_tokens": 1001}}},
                        {"completion": {"choices": [{"finish_reason": "length", "message": {"content": '{}'}}]}}):
            with self.subTest(changes=changes), ControlledExchange(**changes) as exchange:
                with self.assertRaises(ProviderError):
                    self.adapter(limit).select(case["question"], sources, plan, wire)
                self.assertLessEqual(exchange.counts()["mock_completion_requests"], 1)
        with ControlledExchange(lambda _: '{"bundle_ids":[]}' + ' ' * 9000) as exchange:
            with self.assertRaises(ProviderError):
                self.adapter(limit).select(case["question"], sources, plan, wire)
            self.assertEqual(exchange.counts()["mock_completion_requests"], 1)
        with ControlledExchange() as exchange:
            self.adapter(limit).select(case["question"], sources, plan, wire)
        sent = json.loads(exchange.requests[1].content)
        self.assertEqual(sha(canonical(sent["messages"])), wire["measurement"]["messages_sha256"])
        self.assertEqual(exchange.requests[1].headers["authorization"], "Bearer SYNTHETIC-NOT-A-KEY")
        self.assertEqual(sent["max_completion_tokens"], 1000)
        self.assertEqual(sent["response_format"], {"type": "json_object"})

    def test_five_concurrent_mock_selections_are_bound_to_separate_sources_and_wire_manifests(self):
        barrier = threading.Barrier(5, timeout=10)

        def select(payload):
            barrier.wait()
            return json.dumps({"bundle_ids": [b["id"] for b in json.loads(payload["messages"][1]["content"])["bundles"]]})

        def task(index):
            case, sources, plan, wire, limit = self.context(index)
            result = self.adapter(limit).select(case["question"], sources, plan, wire, context_limit=limit)
            self.assertEqual(result["source_inventory_sha256"], plan["source_inventory_sha256"])
            self.assertEqual(result["wire_sha256"], wire["wire_sha256"])
            ids = {p["id"] for p in sources}
            self.assertTrue(all(p["evidence_id"] in ids for b in result["bundles"] for p in b["parts"]))

        with ControlledExchange(select) as exchange, ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(task, [1, 2, 9, 10, 13]))
        self.assertEqual(exchange.counts()["mock_metadata_requests"], 5)
        self.assertEqual(exchange.counts()["mock_completion_requests"], 5)

    def test_old_mode_cannot_activate_v2_and_missing_or_other_context_wire_is_rejected(self):
        with self.assertRaises(ValueError):
            DisposableDiverseAdapter(Provider(settings()), mode=OLD_MARKER)
        case, sources, plan, wire, limit = self.context()
        other = self.context(2)[3]
        with ControlledExchange() as exchange:
            for supplied in (None, {}, other):
                with self.assertRaises(ValueError):
                    self.adapter(limit).select(case["question"], sources, plan, supplied)
            self.assertFalse(exchange.requests)


if __name__ == "__main__":
    unittest.main()
