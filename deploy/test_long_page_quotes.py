"""Long-page frozen oracles, exact provenance and private-free caller diagnostics."""

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from long_page_cases import (  # noqa: E402
    CASES,
    INJECTION,
    LINES,
    PAGES,
    SUITE_SHA256,
    document,
    selection_result,
)
from provider_call_checks import correlate  # noqa: E402
from provider_job_checks import ProductRejected, verify_product  # noqa: E402
from provider_job_fixture import MeasuredProvider, observe_relay_failure  # noqa: E402
from qualify_provider_jobs import definition  # noqa: E402

from app.context_packing import pack_private_context  # noqa: E402
from app.evidence_prompt import canonical  # noqa: E402
from app.extract import extract  # noqa: E402


def fixture(case):
    content = document(case)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "synthetic.pdf"
        path.write_bytes(content)
        source = {"id": "pdf", "revision": 1, "sha256": hashlib.sha256(content).hexdigest(), "passages": []}
        passages = []
        for index, p in enumerate(extract(path, ".pdf")["passages"]):
            p = {**p, "id": f"page-{index}", "text_sha256": hashlib.sha256(p["text"].encode()).hexdigest()}
            source["passages"].append(p)
            passages.append({**p, "document_id": "pdf", "document_revision": 1, "document_sha256": source["sha256"]})
    pack = pack_private_context(case["question"], passages, context_limit=8192, candidate_profile=True)
    claims = [{"text": text, "evidence_ids": [next(p["id"] for p in pack["evidence"] if text in p["text"])],
               "review_status": "pending"} for text in case["expected"]]
    product = {"status": "needs_review", "snapshots": {"sources": {"pdf": 1}, "provider": "local-provider-validated-quotes",
               "context_pack": {"messages_sha256": pack["manifest"]["prompt"]["messages_sha256"]}},
               "evidence": pack["evidence"], "context_pack": pack["manifest"], "claims": claims,
               "critical_gaps": ["legal_corpus_unqualified"], "coverage": {"gaps": ["Synthetic only"]}}
    return source, product


class LongPageQuotes(unittest.TestCase):
    def test_independent_frozen_cases_have_long_pages_late_facts_and_all_oracles_visible(self):
        self.assertEqual(SUITE_SHA256, hashlib.sha256(canonical({"cases": CASES, "pages": PAGES, "lines": LINES}).encode()).hexdigest())
        self.assertEqual(len(CASES), 5)
        self.assertEqual(sum(not c["expected"] for c in CASES), 1)
        for case in CASES:
            with self.subTest(case=case["id"]):
                self.assertEqual(document(case), document(case))
                source, product = fixture(case)
                self.assertEqual(len(source["passages"]), 3)
                self.assertTrue(all(len(p["text"]) > 2000 for p in source["passages"]))
                self.assertTrue(selection_result(case, product)["selection_passed"])
                result = verify_product(product, [source], 8192, question=case["question"], require_claims=bool(case["expected"]))
                self.assertGreater(result["shortened_passages"], 0)
                self.assertLessEqual(result["context_units"], 8192)

    def test_one_sided_conflict_missing_condition_and_false_abstention_fail(self):
        for index in (0, 1, 4):
            case = CASES[index]
            _, product = fixture(case)
            product["claims"].pop()
            self.assertFalse(selection_result(case, product)["selection_passed"])
        _, product = fixture(CASES[2])
        product["claims"] = [{"text": "SYNTHETIC irrelevant"}]
        self.assertFalse(selection_result(CASES[2], product)["selection_passed"])

    def test_document_instruction_never_qualifies_even_with_correct_fact(self):
        _, product = fixture(CASES[3])
        product["claims"].append({"text": INJECTION})
        self.assertFalse(selection_result(CASES[3], product)["selection_passed"])

    def test_revisions_spans_prompt_and_reference_mutations_fail(self):
        case = CASES[0]
        source, product = fixture(case)
        for mutation in (lambda p: p["snapshots"]["sources"].update(pdf=2),
                         lambda p: p["evidence"][0].update(text="changed"),
                         lambda p: p["snapshots"]["context_pack"].update(messages_sha256="0" * 64),
                         lambda p: p["claims"][0].update(evidence_ids=["Q777"])):
            value = copy.deepcopy(product)
            mutation(value)
            with self.assertRaises(ProductRejected):
                verify_product(value, [source], 8192, question=case["question"])

    def test_correlation_rejects_duplicate_unknown_extra_unbounded_and_nonfinite_events(self):
        events = [{"sequence": n + 1, "started": 1, "finished": 3, "question_sha256": hashlib.sha256(c["question"].encode()).hexdigest(),
                   "http": [{"stage": "completion", "status": 502, "elapsed_seconds": 1}],
                   "diagnostics": {"relay_provider_connection_closed": 1}, "outcome": "failed"} for n, c in enumerate(CASES)]
        self.assertTrue(all(r["completion_502_with_relay_connection_closure"] for r in correlate(CASES, events).values()))
        for mutation in (lambda e: e.pop(), lambda e: e.__setitem__(1, e[0]),
                         lambda e: e[0].update(secret="never"), lambda e: e[0].update(finished=float("nan")),
                         lambda e: e[0]["diagnostics"].update(arbitrary_secret=1),
                         lambda e: e[0]["http"][0].update(status=599),
                         lambda e: e[0]["http"][0].update(elapsed_seconds=9)):
            value = copy.deepcopy(events)
            mutation(value)
            with self.assertRaises(ValueError):
                correlate(CASES, value)

    def test_profile_is_disposable_only_and_keeps_existing_budgets(self):
        args = ({"api": "sha256:api", "postgres": "sha256:pg"}, "key", "pw", "t" * 32, "198.19.0.0/28",
                Path("/protected/profile"), Path("/protected/key"), "provider")
        profile, baseline = definition(*args, workload="long-page-quotes-v1"), definition(*args)
        self.assertTrue(profile["services"]["driver"]["command"][-1].endswith("/long_page_driver.py"))
        self.assertNotIn("volumes", profile["services"]["driver"])
        self.assertEqual(profile["services"]["api"]["environment"].pop("LA_QUOTE_VOLUME_CANDIDATE"), "lawyer-real-provider-jobs-v1")
        self.assertEqual(profile["services"]["api"], baseline["services"]["api"])

    def test_authenticated_driver_correlates_concurrent_outcomes_and_keeps_failed_product_seals(self):
        import long_page_driver as driver
        from fastapi.testclient import TestClient

        import app.research as research
        from app.config import Settings
        from app.main import create_app

        class Oracle(MeasuredProvider):
            def __init__(self, settings, failure):
                super().__init__(settings)
                self.barrier, self.failure = Barrier(5), failure

            def _complete(self, messages, *args, **kwargs):
                payload = json.loads(messages[-1]["content"])
                case = next(c for c in CASES if c["question"] == payload["question"])
                self.barrier.wait(timeout=10)
                self.observe_http(httpx.Response(200, request=httpx.Request("GET", "http://fixture/v1/models")))
                fail = self.failure == "transport" and case["id"] == CASES[2]["id"]
                response = httpx.Response(502 if fail else 200, json={"code": "provider_connection_closed", "secret": "never-retain"},
                                          request=httpx.Request("POST", "http://fixture/v1/chat/completions"))
                self.observe_http(response)
                self.note("never-retain")
                if fail:
                    observe_relay_failure(response, self.note)
                    raise ValueError("Provider returned HTTP 502")
                expected = [] if self.failure == "empty" and case["id"] == CASES[0]["id"] else case["expected"]
                ids = [next(q["id"] for p in payload["evidence"] if text in p["text"] for q in p["quotes"]) for text in expected]
                return json.dumps({"quote_ids": list(dict.fromkeys(ids))})

        for failure in (None, "empty", "transport"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                settings = Settings(_env_file=None, demo_mode=True, cookie_secure=False, data_dir=Path(folder),
                    LLM_PROVIDER_BASE_URL="http://127.0.0.1/v1", LLM_PROVIDER_API_KEY="synthetic-only", LLM_PROVIDER_MODEL="synthetic")
                app, oracle = create_app(settings), Oracle(settings, failure)

                @app.get("/_provider_jobs/state")
                def state():
                    return {"provider": oracle.snapshot(), "admitted_jobs": 0}

                @app.get("/_provider_jobs/http")
                def http():
                    return oracle.http_snapshot()

                @app.get("/_provider_jobs/events")
                def events():
                    return oracle.event_snapshot()

                with TestClient(app) as client:
                    app.state.provider, app.state.settings.provider_context_limit = oracle, 8192
                    with patch.object(driver, "httpx", SimpleNamespace(Client=lambda **kwargs: nullcontext(client))), patch.dict(
                            os.environ, {"LA_REAL_JOB_WORKLOAD": "long-page-quotes-v1", "LA_REAL_JOB_CONTEXT_UNITS": "8192",
                                         "LA_LOAD_CONTROL_TOKEN": "synthetic-control-no-real-secret"}), patch.object(
                            research, "pack_private_context", side_effect=lambda *a, **k: pack_private_context(*a, **k, candidate_profile=True)):
                        report = driver.run()
                    self.assertEqual(report["status"], "passed" if failure is None else "failed", report.get("failure_stage"))
                    self.assertEqual(report["passed_tasks"], 5 if failure is None else 4)
                    self.assertEqual(report["peak_application_calls"], 5)
                    self.assertTrue(report["caller_events_verified"])
                    self.assertTrue(report["originals_and_versions_unchanged"])
                    self.assertEqual(oracle.calls, 5)
                    self.assertNotIn("never-retain", json.dumps(report))
                    if failure == "empty":
                        self.assertEqual(report["results"][0]["failure_code"], "product_claim_grounding_failed")
                        self.assertEqual(len(report["results"][0]["product_sha256"]), 64)
                    if failure == "transport":
                        self.assertTrue(report["call_observations"][CASES[2]["id"]]["completion_502_with_relay_connection_closure"])
                        self.assertTrue(all(not v["completion_502_with_relay_connection_closure"] for k, v in report["call_observations"].items()
                                            if k != CASES[2]["id"]))


if __name__ == "__main__":
    unittest.main()
