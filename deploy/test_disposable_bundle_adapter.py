"""Disposable exact-source selection and fresh coverage failure boundaries."""

import copy
import json
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from alternate_adverse_quote_cases import CASES, originals_for  # noqa: E402
from budgeted_quote_bundles import plan_bundles, sha  # noqa: E402
from bundle_adapter_fixture import ControlledExchange, settings  # noqa: E402
from disposable_bundle_adapter import MARKER, DisposableBundleAdapter, selection_ids  # noqa: E402
from evaluate_alternate_adverse_quotes import evaluate  # noqa: E402
from evaluate_disposable_bundle_adapter import evaluate as adapter_evaluate  # noqa: E402

from app.evidence_prompt import canonical  # noqa: E402
from app.provider import Provider, ProviderError  # noqa: E402


class DisposableBundleContracts(unittest.TestCase):
    def context(self, index=4):
        case = CASES[index]
        sources = originals_for(case)
        limit = case.get("context_limit", 8192)
        return case["question"], sources, plan_bundles(case["question"], sources, context_limit=limit)

    def test_fresh_evaluation_retains_paraphrase_and_adverse_misses(self):
        report = evaluate()
        self.assertEqual(report["summary"], {"cases": 12, "expected_groups": 18, "available_groups": 13,
            "alternate_wording_cases": 4, "alternate_wording_all_groups_available": 2,
            "adverse_source_cases": 7, "both_sides_available_cases": 4, "within_budget": 12})
        missing = {c["case"] for c in report["cases"] if c["groups"] and not c["all_declared_groups_available"]}
        self.assertEqual(missing, {"P1101", "P1102", "P1108", "P1111", "P1112"})
        self.assertTrue(all(c["adapter_messages_sha256"] == c["measurement"]["messages_sha256"] for c in report["cases"]))
        self.assertEqual(report["inference_calls"], 0)
        self.assertEqual(report["http_calls"], 0)
        self.assertFalse(report["native_or_legal_qualification"])

    def test_mock_adapter_copies_all_parts_with_no_native_quality_claim(self):
        report = adapter_evaluate()
        self.assertEqual(len(report["cases"]), 12)
        self.assertEqual(report["counts"], {"mock_metadata_requests": 9, "mock_completion_requests": 9,
                                         "network_http_calls": 0, "inference_calls": 0})
        question, sources, plan = self.context(2)
        before = canonical(sources)
        with ControlledExchange() as exchange:
            result = exchange.adapter().select(question, sources, plan)
        self.assertEqual(result["bundles"][0]["parts"], plan["bundles"][0]["parts"])
        self.assertEqual(canonical(sources), before)
        for part in result["bundles"][0]["parts"]:
            source = next(s for s in sources if s["id"] == part["evidence_id"])
            self.assertEqual(part["text"], source["text"][part["original_start"]:part["original_end"]])
            self.assertEqual(part["text_sha256"], sha(part["text"]))
        self.assertTrue(any(p["role"] == "companion" for p in result["bundles"][0]["parts"]))
        self.assertFalse(result["production_activation"])

    def test_existing_provider_auth_pin_no_fallback_and_actual_prompt_survive(self):
        question, sources, plan = self.context()
        with ControlledExchange() as exchange:
            exchange.adapter().select(question, sources, plan)
        self.assertEqual(len(exchange.requests), 2)
        for req in exchange.requests:
            self.assertEqual(req.headers["authorization"], "Bearer SYNTHETIC-NOT-A-KEY")
        sent = json.loads(exchange.requests[1].content)
        self.assertEqual(sha(canonical(sent["messages"])), plan["measurement"]["messages_sha256"])
        self.assertEqual(sent["max_completion_tokens"], 1000)
        self.assertEqual(sent["response_format"], {"type": "json_object"})
        self.assertEqual(sent["model"], "SYNTHETIC-NO-INFERENCE")
        self.assertFalse(sent["stream"])
        for field in ("provider_identity_verified", "provider_cloud_fallback_disabled"):
            with ControlledExchange() as exchange:
                with self.assertRaises(ProviderError):
                    exchange.adapter(**{field: False}).select(question, sources, plan)
                self.assertEqual(len(exchange.requests), 0)

    def test_invalid_schema_ids_duplicates_anchor_only_and_prose_fail_without_retry(self):
        question, sources, plan = self.context()
        for content in ['{"bundle_ids":["B999"]}', '{"bundle_ids":["B1","B1"]}',
                        '{"bundle_ids":["B1:anchor"]}', '{"bundle_ids":[true]}', '{"bundle_ids":"B1"}',
                        '{"bundle_ids":[],"claims":[]}', '{"bundle_ids":[],"bundle_ids":["B1"]}',
                        '{"quote_ids":["Q1"]}', '[]', 'null', '```json\n{"bundle_ids":[]}\n```',
                        '{"bundle_ids":[' + '"B1",' * 20 + '"B1"]}']:
            with self.subTest(content=content), ControlledExchange(lambda _: content) as exchange:
                with self.assertRaises((ValueError, RecursionError)):
                    exchange.adapter().select(question, sources, plan)
                self.assertEqual(exchange.counts()["mock_completion_requests"], 1)
        with self.assertRaises(ValueError):
            selection_ids(' ' * 4097)

    def test_no_candidates_is_not_model_abstention_and_empty_selection_is_not_qualified(self):
        question, sources, plan = self.context(0)
        with ControlledExchange() as exchange:
            result = exchange.adapter().select(question, sources, plan)
            self.assertEqual(result["state"], "no_candidates_no_call")
            self.assertFalse(exchange.requests)
        question, sources, plan = self.context()
        with ControlledExchange(lambda _: '{"bundle_ids":[]}') as exchange:
            result = exchange.adapter().select(question, sources, plan)
            self.assertEqual(result["state"], "empty_selection_unqualified")
            self.assertFalse(result["model_relevance_or_legal_qualification"])

    def test_stale_unused_revision_question_budget_and_tampered_companion_block_before_http(self):
        question, sources, plan = self.context()
        for update in (lambda s, p: s[-1].update(document_revision=23),
                       lambda s, p: p["bundles"][0]["parts"].pop(),
                       lambda s, p: p["measurement"].update(within_budget=True, total_upper_bound_units=1)):
            changed, modified = copy.deepcopy(sources), copy.deepcopy(plan)
            update(changed, modified)
            with ControlledExchange() as exchange:
                with self.assertRaises(ValueError):
                    exchange.adapter().select(question, changed, modified)
                self.assertFalse(exchange.requests)
        with ControlledExchange() as exchange:
            for q, limit in ((question + "other", 8192), (question, 8191), (question, True)):
                with self.assertRaises(ValueError):
                    exchange.adapter().select(q, sources, plan, context_limit=limit)
            tiny = plan_bundles(question, sources, context_limit=1024)
            with self.assertRaises(ValueError):
                exchange.adapter(provider_context_limit=1024).select(question, sources, tiny, context_limit=1024)
            self.assertFalse(exchange.requests)

    def test_version_race_during_transport_discards_result_without_overwriting_history(self):
        for change in ("source", "plan"):
            question, sources, plan = self.context()

            def mutate(_):
                if change == "source":
                    sources[-1]["document_revision"] += 1
                else:
                    plan["source_inventory_sha256"] = "b" * 64
                return '{"bundle_ids":["B1"]}'

            with ControlledExchange(mutate) as exchange:
                with self.assertRaisesRegex(ValueError, "changed during"):
                    exchange.adapter().select(question, sources, plan)
                self.assertEqual(exchange.counts()["mock_completion_requests"], 1)

    def test_502_clipped_wrong_model_remote_metadata_and_usage_fail_no_retry(self):
        question, sources, plan = self.context()
        for kwargs in ({"status": 502}, {"completion": {"model": "other-model"}},
                       {"completion": {"fallback_reason": "upstream"}},
                       {"metadata": {"request_key_source": "cloud"}},
                       {"metadata": {"max_model_len": 4096}},
                       {"completion": {"usage": {"completion_tokens": 1001}}},
                       {"completion": {"choices": [{"finish_reason": "length", "message": {"content": '{}'}}]}}):
            with self.subTest(kwargs=kwargs), ControlledExchange(**kwargs) as exchange:
                with self.assertRaises(ProviderError):
                    exchange.adapter().select(question, sources, plan)
                self.assertLessEqual(exchange.counts()["mock_completion_requests"], 1)
        with ControlledExchange(lambda _: 'x' * 9000) as exchange:
            with self.assertRaises(ProviderError):
                exchange.adapter().select(question, sources, plan)

    def test_five_concurrent_mock_selections_have_no_cross_context_sources(self):
        barrier = threading.Barrier(5, timeout=10)

        def select(payload):
            barrier.wait()
            bundles = json.loads(payload["messages"][1]["content"])["bundles"]
            return json.dumps({"bundle_ids": [b["id"] for b in bundles]})

        def task(index):
            question, sources, plan = self.context(index)
            result = exchange.adapter().select(question, sources, plan)
            self.assertEqual(result["plan_sha256"], plan["plan_sha256"])
            ids = {s["id"] for s in sources}
            self.assertTrue(all(p["evidence_id"] in ids for b in result["bundles"] for p in b["parts"]))

        with ControlledExchange(select) as exchange, ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(task, [2, 3, 4, 5, 6]))
        self.assertEqual(exchange.counts()["mock_metadata_requests"], 5)
        self.assertEqual(exchange.counts()["mock_completion_requests"], 5)

    def test_disposable_mode_is_required_and_production_quotation_contract_stays_separate(self):
        with self.assertRaises(ValueError):
            DisposableBundleAdapter(Provider(settings()), mode="production")
        with self.assertRaises(ValueError):
            DisposableBundleAdapter(object(), mode=MARKER)
        with ControlledExchange(lambda _: '{"quote_ids":[]}'):
            result = Provider(settings()).generate("fixture", [])
        self.assertEqual(json.loads(result), {"summary": "", "claims": []})


if __name__ == "__main__":
    unittest.main()
