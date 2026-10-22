"""Independent relevance/abstention oracle and exact-source integration; no inference."""

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from provider_job_checks import ProductRejected, verify_product  # noqa: E402
from provider_job_fixture import MeasuredProvider  # noqa: E402
from qualify_provider_jobs import definition  # noqa: E402
from quote_selection_cases import (  # noqa: E402
    CASES,
    PAYMENT,
    POISON,
    SUITE_SHA256,
    documents,
    selection_result,
)

from app.context_packing import pack_private_context  # noqa: E402
from app.evidence_prompt import canonical  # noqa: E402
from app.extract import extract  # noqa: E402


def fixture(case):
    sources, passages = [], []
    with tempfile.TemporaryDirectory() as directory:
        for index, (suffix, content) in enumerate(documents(case)):
            path = Path(directory) / f"synthetic-{index}.{suffix}"
            path.write_bytes(content)
            source = {"id": str(index), "revision": 1, "sha256": hashlib.sha256(content).hexdigest(), "passages": []}
            for n, passage in enumerate(extract(path, "." + suffix)["passages"]):
                value = {**passage, "id": f"{index}-{n}", "text_sha256": hashlib.sha256(passage["text"].encode()).hexdigest()}
                source["passages"].append(value)
                passages.append({**value, "document_id": source["id"], "document_revision": 1, "document_sha256": source["sha256"]})
            sources.append(source)
    packed = pack_private_context(case["question"], passages, context_limit=8192)
    product = {"status": "needs_review", "snapshots": {"sources": {s["id"]: 1 for s in sources},
               "provider": "local-provider-validated-quotes", "context_pack": {
                   "messages_sha256": packed["manifest"]["prompt"]["messages_sha256"]}},
               "evidence": packed["evidence"], "context_pack": packed["manifest"], "claims": [],
               "critical_gaps": ["legal_corpus_unqualified"], "coverage": {"gaps": ["Synthetic corpus only"]}}
    for text in case["expected"]:
        passage = next(p for p in product["evidence"] if text in p["text"])
        product["claims"].append({"text": text, "evidence_ids": [passage["id"]], "review_status": "pending"})
    return product, sources


class QuoteSelectionEvaluation(unittest.TestCase):
    def test_frozen_matrix_real_parsers_all_oracles_visible_and_five_answerable_two_abstentions(self):
        self.assertEqual(hashlib.sha256(canonical(CASES).encode()).hexdigest(), SUITE_SHA256)
        self.assertEqual(len(CASES), 7)
        self.assertEqual(sum(not c["expected"] for c in CASES), 2)
        for case in CASES:
            with self.subTest(case=case["id"]):
                product, sources = fixture(case)
                verify_product(product, sources, 8192, question=case["question"], require_claims=bool(case["expected"]))
                self.assertTrue(selection_result(case, product)["selection_passed"])
        self.assertEqual(CASES[1]["documents"], CASES[2]["documents"])
        self.assertNotEqual(CASES[1]["question"], CASES[2]["question"])

    def test_source_matching_does_not_prove_relevance_or_resolve_missing_facts(self):
        missing = CASES[3]
        product, sources = fixture(missing)
        passage = next(p for p in product["evidence"] if PAYMENT in p["text"])
        product["claims"] = [{"text": PAYMENT, "evidence_ids": [passage["id"]], "review_status": "pending"}]
        verify_product(product, sources, 8192, question=missing["question"], require_claims=False)
        self.assertFalse(selection_result(missing, product)["selection_passed"])

    def test_empty_answer_only_passes_declared_negative_task_and_stale_versions_never_pass(self):
        product, sources = fixture(CASES[0])
        product["claims"] = []
        self.assertFalse(selection_result(CASES[0], product)["selection_passed"])
        with self.assertRaises(ProductRejected):
            verify_product(product, sources, 8192, question=CASES[0]["question"])
        product, sources = fixture(CASES[3])
        product["snapshots"]["sources"][sources[0]["id"]] = 2
        with self.assertRaises(ProductRejected):
            verify_product(product, sources, 8192, question=CASES[3]["question"], require_claims=False)

    def test_injection_selection_or_one_sided_conflict_fails_even_when_exactly_grounded(self):
        for index in (4, 5):
            case = CASES[index]
            product, sources = fixture(case)
            if index == 4:
                p = next(p for p in product["evidence"] if POISON in p["text"])
                product["claims"].append({"text": POISON, "evidence_ids": [p["id"]], "review_status": "pending"})
            else:
                product["claims"].pop()
            verify_product(product, sources, 8192, question=case["question"])
            self.assertFalse(selection_result(case, product)["selection_passed"])

    def test_changed_question_cannot_reuse_prompt_seal(self):
        product, sources = fixture(CASES[0])
        with self.assertRaises(ProductRejected):
            verify_product(product, sources, 8192, question=CASES[3]["question"])
        altered = copy.deepcopy(product)
        altered["claims"][0]["text"] = "Invented claim"
        with self.assertRaises(ProductRejected):
            verify_product(altered, sources, 8192, question=CASES[0]["question"])

    def test_http_diagnostics_are_finite_status_stage_counters_without_body_or_identifiers(self):
        provider = MeasuredProvider(None)
        for path, status in [("/v1/models", 200), ("/v1/chat/completions", 502),
                             ("/v1/chat/completions", 599), ("/private/anything", 502)]:
            response = httpx.Response(status, content=b"NEVER RECORD", request=httpx.Request("GET", "http://host" + path))
            provider.observe_http(response)
        self.assertEqual(provider.http_snapshot(), {"metadata_http_200": 1, "completion_http_502": 1, "completion_http_other": 1})
        self.assertNotIn("http_observations", provider.snapshot())  # Existing wave contract stays exact.

    def test_eval_uses_separate_driver_without_private_volumes_or_changed_default_driver(self):
        args = ({"api": "sha256:api", "postgres": "sha256:pg"}, "key", "pw", "t" * 32, "198.19.0.0/28",
                Path("/protected/profile"), Path("/protected/key"), "provider")
        default = definition(*args)
        evaluation = definition(*args, workload="quote-selection-v1")
        self.assertTrue(default["services"]["driver"]["command"][-1].endswith("/provider_job_driver.py"))
        self.assertTrue(evaluation["services"]["driver"]["command"][-1].endswith("/quote_selection_driver.py"))
        self.assertNotIn("volumes", evaluation["services"]["driver"])
        self.assertEqual(default["services"]["api"], evaluation["services"]["api"])

    def test_full_declared_driver_through_authenticated_app_routes_with_controlled_oracle(self):
        import quote_selection_driver as driver
        from fastapi.testclient import TestClient

        from app.config import Settings
        from app.main import create_app

        class Oracle:
            configured, transport_mode = True, "synthetic"

            def __init__(self):
                self.lock, self.calls = Lock(), 0
                self.fail_missing = False

            def generate(self, question, passages):
                with self.lock:
                    self.calls += 1
                case = next(c for c in CASES if c["question"] == question)
                expected = [PAYMENT] if self.fail_missing and case["id"] == "missing-fact" else case["expected"]
                return json.dumps({"summary": "", "claims": [
                    {"text": text, "evidence_ids": [next(p["id"] for p in passages if text in p["text"])]}
                    for text in expected]})

        with tempfile.TemporaryDirectory() as folder:
            app = create_app(Settings(_env_file=None, demo_mode=True, cookie_secure=False, data_dir=Path(folder),
                                      LLM_PROVIDER_BASE_URL="", LLM_PROVIDER_API_KEY="", LLM_PROVIDER_MODEL=""))
            oracle = Oracle()

            @app.get("/_provider_jobs/state")
            def state():
                return {"provider": {"calls": oracle.calls, "active": 0, "failures": 0}, "admitted_jobs": 0}

            @app.get("/_provider_jobs/http")
            def http():
                return {}

            with TestClient(app) as client:
                app.state.provider = oracle
                app.state.settings.provider_context_limit = 8192
                with patch.object(driver, "httpx", SimpleNamespace(Client=lambda **kwargs: nullcontext(client))), patch.dict(
                        os.environ, {"LA_REAL_JOB_WORKLOAD": "quote-selection-v1", "LA_REAL_JOB_CONTEXT_UNITS": "8192",
                                     "LA_LOAD_CONTROL_TOKEN": "synthetic-control-no-real-secret"}):
                    report = driver.run()
                self.assertEqual(report["status"], "passed", report.get("failure_stage"))
                self.assertEqual(report["passed_tasks"], 7)
                self.assertTrue(report["originals_and_versions_unchanged"])
                self.assertEqual(oracle.calls, 7)
                oracle.calls, oracle.fail_missing = 0, True
                with patch.object(driver, "httpx", SimpleNamespace(Client=lambda **kwargs: nullcontext(client))), patch.dict(
                        os.environ, {"LA_REAL_JOB_WORKLOAD": "quote-selection-v1", "LA_REAL_JOB_CONTEXT_UNITS": "8192",
                                     "LA_LOAD_CONTROL_TOKEN": "synthetic-control-no-real-secret"}):
                    failed = driver.run()
                self.assertEqual(failed["status"], "failed")
                self.assertEqual(failed["passed_tasks"], 6)
                self.assertEqual(len(failed["results"]), 7)
                self.assertTrue(failed["originals_and_versions_unchanged"])
                self.assertEqual(oracle.calls, 7)  # No replacement attempt for the failed negative case.


if __name__ == "__main__":
    unittest.main()
