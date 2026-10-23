"""Disposable protocol, authorization, exact-copy and atomic budget falsification."""

import copy
import json
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from bundle_adapter_fixture import ControlledExchange, settings  # noqa: E402
from disposable_packet_selector import MARKER, Allowance, DisposablePacketSelector  # noqa: E402
from evaluate_packet_selector import evaluate  # noqa: E402
from packet_selector_cases import CASES, originals_for  # noqa: E402
from whole_passage_packets import plan_packets  # noqa: E402

from app.evidence_prompt import canonical  # noqa: E402
from app.provider import Provider  # noqa: E402


class DisposablePacketSelectorContracts(unittest.TestCase):
    def prepare(self, index=1, *, case=None, limit=8192):
        case = copy.deepcopy(case or CASES[index])
        sources = originals_for(case)
        plan = plan_packets(case["question"], sources, context_limit=limit)
        b = plan["aggregate_budget"]
        return case["question"], sources, plan, Allowance(len(plan["packets"]), b["planned_upper_bound_units"], b["planned_copied_text_utf8_bytes"])

    def session(self, data, *, authorize=lambda _: True, provider=None, limit=8192, mode=MARKER):
        return DisposablePacketSelector(provider or Provider(settings(provider_context_limit=limit)), *data,
                                        authorize=authorize, mode=mode, context_limit=limit)

    def test_fresh_mock_report_is_reproducible_and_explicitly_unqualified(self):
        report = evaluate()
        self.assertEqual(report, evaluate())
        self.assertEqual(report["summary"], {"cases": 6, "packets": 6, "mock_metadata_requests": 6,
            "mock_completion_requests": 6, "no_candidate_cases": 2, "all_copies_exact": True})
        self.assertEqual(report["network_http_calls"], 0)
        self.assertEqual(report["native_inference_calls"], 0)
        self.assertFalse(report["native_relevance_abstention_legal_or_capacity_qualification"])

    def test_exact_originals_versions_whitespace_and_no_caller_mutation(self):
        for index in (0, 2, 5):
            data = self.prepare(index)
            before = canonical(data[:3])
            with ControlledExchange():
                session = self.session(data)
                result = session.select("P1")
            self.assertEqual(result["bundles"], data[2]["packets"][0]["bundles"])
            self.assertEqual(canonical(data[:3]), before)
            self.assertFalse(result["model_relevance_abstention_or_legal_qualification"])
            self.assertNotIn("text", session.receipt())

    def test_entire_plan_must_fit_each_explicit_aggregate_dimension_before_http(self):
        data = self.prepare()
        for attr in ("completion_attempts", "context_units", "copied_text_bytes"):
            values = data[3].__dict__.copy()
            values[attr] -= 1
            with ControlledExchange() as exchange, self.assertRaises(ValueError):
                self.session((*data[:3], Allowance(**values)))
            self.assertEqual(exchange.counts()["mock_completion_requests"], 0)
            self.assertEqual(exchange.counts()["mock_metadata_requests"], 0)
        for bad in (Allowance(True, 1, 1), Allowance(9, 65536, 32000), Allowance(8, 65537, 32000),
                    Allowance(8, 65536, 32001), Allowance(-1, 0, 0)):
            with self.assertRaises(ValueError):
                self.session((*data[:3], bad))

    def test_no_silent_wider_profile_or_mismatched_provider(self):
        data = self.prepare()
        for limit in (True, 8193, 0, -1, 8192.0):
            with self.assertRaises(ValueError):
                self.session(data, limit=limit)
        for limit in (True, 32768, 4096):
            with self.assertRaises(ValueError):
                self.session(data, provider=Provider(settings(provider_context_limit=limit)))
        with self.assertRaises(ValueError):
            self.session(data, mode="production")

    def test_changed_unused_source_or_wire_is_rejected_without_transport(self):
        for kind in ("unused", "wire", "question", "plan_limit"):
            data = self.prepare()
            session = self.session(data)
            if kind == "unused":
                data[1][-1]["document_revision"] += 1
            elif kind == "wire":
                data[2]["packets"][0]["messages"][0]["content"] += " altered"
            elif kind == "question":
                data = (data[0] + "other", *data[1:])
                with self.assertRaises(ValueError):
                    self.session(data)
                continue
            else:
                data[2]["limits"]["max_packets"] = 7
            with ControlledExchange() as exchange, self.assertRaises(ValueError):
                session.select("P1")
            self.assertEqual(exchange.counts()["mock_metadata_requests"], 0)
            self.assertEqual(session.receipt()["consumed_completion_attempts"], 0)

    def test_snapshot_is_validated_after_copy_not_just_caller_hash(self):
        data = self.prepare()
        data[1][0]["text"] += "tamper"
        with self.assertRaises(ValueError):
            self.session(data)
        data = self.prepare()
        data[2]["packets"][0]["measurement"]["total_upper_bound_units"] = 1
        with self.assertRaises(ValueError):
            self.session(data)

    def test_authorizer_is_required_strict_and_descriptor_contains_no_text(self):
        data = self.prepare()
        for authorize in (None, lambda _: False, lambda _: 1, lambda _: "approved"):
            with self.assertRaises(ValueError):
                self.session(data, authorize=authorize)
        descriptors = []
        session = self.session(data, authorize=lambda d: descriptors.append(d) or True)
        self.assertNotIn(data[0], canonical(descriptors))
        self.assertNotIn(data[1][0]["text"], canonical(descriptors))
        self.assertEqual(descriptors[0]["source_inventory_sha256"], data[2]["source_inventory_sha256"])
        with ControlledExchange():
            session.select("P1")
        self.assertGreaterEqual(len(descriptors), 4)

    def test_revocation_before_call_and_mutation_inside_authorizer_fail_closed(self):
        data = self.prepare()
        permitted = [True]
        session = self.session(data, authorize=lambda _: permitted[0])
        permitted[0] = False
        with ControlledExchange() as exchange, self.assertRaises(ValueError):
            session.select("P1")
        self.assertEqual(exchange.counts()["mock_metadata_requests"], 0)
        data = self.prepare()
        def mutate(_):
            data[1][-1]["document_revision"] += 1
            return True
        with self.assertRaises(ValueError):
            self.session(data, authorize=mutate)

    def test_revocation_or_context_provider_change_in_flight_discards_result_and_consumes_budget(self):
        for change in ("access", "evidence", "model", "key", "limit"):
            data, allowed, provider = self.prepare(), [True], Provider(settings())
            session = self.session(data, authorize=lambda _: allowed[0], provider=provider)
            def select(payload):
                if change == "access":
                    allowed[0] = False
                elif change == "evidence":
                    data[1][-1]["document_revision"] += 1
                else:
                    setattr(provider.settings, {"model": "provider_model", "key": "provider_api_key", "limit": "provider_context_limit"}[change], "changed")
                return json.dumps({"bundle_ids": [b["id"] for b in json.loads(payload["messages"][1]["content"])["bundles"]]})
            with ControlledExchange(select) as exchange, self.assertRaises(ValueError):
                session.select("P1")
            self.assertEqual(exchange.counts()["mock_completion_requests"], 1)
            self.assertEqual(session.receipt()["attempts"]["P1"]["state"], "failed_consumed")

    def test_unknown_cross_packet_legacy_duplicate_and_extra_response_fields_are_rejected(self):
        for content in ('{"bundle_ids":["D1"]}', '{"bundle_ids":["B1"]}', '{"bundle_ids":["W999"]}',
                        '{"bundle_ids":["W1","W1"]}', '{"bundle_ids":[],"text":"invented"}',
                        '{"bundle_ids":[],"bundle_ids":[]}', 'prose {"bundle_ids":[]}', 'x' * 4097):
            data = self.prepare()
            with ControlledExchange(lambda _: content) as exchange, self.assertRaises(ValueError):
                self.session(data).select("P1")
            self.assertEqual(exchange.counts()["mock_completion_requests"], 1)
        data = self.prepare()
        other = data[2]["packets"][-1]["bundles"][0]["id"]
        with ControlledExchange(lambda _: json.dumps({"bundle_ids": [other]})), self.assertRaises(ValueError):
            self.session(data).select("P1")

    def test_failure_never_refunds_or_retries_and_original_provider_checks_remain(self):
        for options in ({"status": 502}, {"metadata": {"backend": "cloud"}}, {"completion": {"model": "other"}}):
            data = self.prepare()
            session = self.session(data)
            with ControlledExchange(**options) as exchange:
                with self.assertRaises(ValueError):
                    session.select("P1")
                counts = exchange.counts().copy()
                with self.assertRaises(ValueError):
                    session.select("P1")
                self.assertEqual(exchange.counts(), counts)
            receipt = session.receipt()
            self.assertEqual(receipt["consumed_completion_attempts"], 1)
            self.assertEqual(receipt["consumed_upper_bound_units"], data[2]["packets"][0]["measurement"]["total_upper_bound_units"])

    def test_reservation_cancelled_before_transport_remains_consumed(self):
        data = self.prepare()
        checks = [0]
        def authorize(_):
            checks[0] += 1
            return checks[0] < 3
        session = self.session(data, authorize=authorize)
        with ControlledExchange() as exchange, self.assertRaises(ValueError):
            session.select("P1")
        self.assertEqual(exchange.counts()["mock_metadata_requests"], 0)
        self.assertEqual(session.receipt()["consumed_completion_attempts"], 1)

    def test_empty_and_blocked_inventory_cannot_trigger_completion(self):
        for index in (3, 4):
            data = self.prepare(index)
            session = self.session(data)
            with ControlledExchange() as exchange, self.assertRaises(ValueError):
                session.select("P1")
            self.assertEqual(session.receipt()["state"], "no_candidates_no_call")
            self.assertEqual(exchange.counts()["mock_completion_requests"], 0)
        data = self.prepare(limit=1536)
        with self.assertRaises(ValueError):
            self.session(data, limit=1536)

    def test_empty_model_choice_is_unqualified_and_not_reinterpreted(self):
        with ControlledExchange(lambda _: '{"bundle_ids":[]}'):
            result = self.session(self.prepare()).select("P1")
        self.assertEqual(result["state"], "empty_selection_unqualified")
        self.assertEqual(result["bundles"], [])

    def test_concurrent_duplicate_reservation_has_one_completion_only(self):
        data = self.prepare()
        session = self.session(data)
        def run(_):
            try:
                return session.select("P1")["state"]
            except ValueError:
                return "rejected"
        with ControlledExchange() as exchange, ThreadPoolExecutor(max_workers=5) as pool:
            result = list(pool.map(run, range(5)))
        self.assertEqual(result.count("exact_selection_unqualified"), 1)
        self.assertEqual(exchange.counts()["mock_completion_requests"], 1)
        self.assertEqual(session.receipt()["consumed_completion_attempts"], 1)

    def test_five_concurrent_mock_packets_reconcile_exact_reserved_totals(self):
        case = {"id": "P1690", "question": "Farklı kaynakları bul.", "texts": [f"Kaynak {i}: bağımsız görüş." for i in range(35)]}
        data = self.prepare(case=case)
        self.assertEqual(len(data[2]["packets"]), 5)
        session, barrier = self.session(data), Barrier(5)
        def select(payload):
            barrier.wait(timeout=10)
            return json.dumps({"bundle_ids": [b["id"] for b in json.loads(payload["messages"][1]["content"])["bundles"]]})
        with ControlledExchange(select) as exchange, ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(session.select, [p["id"] for p in data[2]["packets"]]))
        receipt = session.receipt()
        self.assertEqual(exchange.counts()["mock_completion_requests"], 5)
        self.assertEqual(receipt["consumed_completion_attempts"], 5)
        self.assertEqual(receipt["consumed_upper_bound_units"], data[3].context_units)
        self.assertEqual(receipt["consumed_copied_text_bytes"], data[3].copied_text_bytes)
        self.assertEqual(sum(len(r["bundles"]) for r in results), 35)
        self.assertTrue(all(v["state"] == "returned_unqualified" for v in receipt["attempts"].values()))

    def test_transport_receives_frozen_wire_and_exact_completion_bounds(self):
        data = self.prepare()
        provider = Provider(settings())
        with patch.object(provider, "_complete", return_value='{"bundle_ids":[]}') as complete:
            self.session(data, provider=provider).select("P1")
        packet = data[2]["packets"][0]
        complete.assert_called_once_with(packet["messages"], 1000, packet["measurement"]["total_upper_bound_units"], response_bytes=8192)
