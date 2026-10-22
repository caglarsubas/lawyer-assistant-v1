"""Frozen volume, exact spans, independent relevance and guarded real-route driver."""

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

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from provider_job_checks import ProductRejected, verify_product  # noqa: E402
from provider_job_fixture import MARKER, MeasuredProvider, install_volume_packing  # noqa: E402
from qualify_provider_jobs import definition  # noqa: E402
from quote_volume_cases import (  # noqa: E402
    CASES,
    POISON,
    SUITE_SHA256,
    WORKSPACES,
    documents,
    selection_result,
)
from quote_volume_driver import digest, peak_overlap  # noqa: E402

from app.context_packing import pack_private_context  # noqa: E402
from app.evidence_prompt import canonical  # noqa: E402
from app.extract import extract  # noqa: E402


def fixture(value):
    sources, passages = [], []
    with tempfile.TemporaryDirectory() as directory:
        for suffix, content in documents(value):
            path = Path(directory) / ("synthetic." + suffix)
            path.write_bytes(content)
            source = {"id": suffix, "revision": 1, "sha256": hashlib.sha256(content).hexdigest(), "passages": []}
            for index, p in enumerate(extract(path, "." + suffix)["passages"]):
                p = {**p, "id": f"{suffix}-{index}", "text_sha256": hashlib.sha256(p["text"].encode()).hexdigest()}
                source["passages"].append(p)
                passages.append({**p, "document_id": suffix, "document_revision": 1, "document_sha256": source["sha256"]})
            sources.append(source)
    return sources, passages


def product(case, sources, passages):
    pack = pack_private_context(case["question"], passages, context_limit=8192, candidate_profile=True)
    claims = [{"text": text, "evidence_ids": [next(p["id"] for p in pack["evidence"] if text in p["text"])],
               "review_status": "pending"} for text in case["expected"]]
    return {"status": "needs_review", "snapshots": {"sources": {s["id"]: 1 for s in sources},
            "provider": "local-provider-validated-quotes", "context_pack": {"messages_sha256": pack["manifest"]["prompt"]["messages_sha256"]}},
            "evidence": pack["evidence"], "context_pack": pack["manifest"], "claims": claims,
            "critical_gaps": ["legal_corpus_unqualified"], "coverage": {"gaps": ["Synthetic only"]}}


class QuoteVolumeEvaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = [fixture(w) for w in WORKSPACES]

    def test_unchanged_frozen_matrix_covers_fifteen_distinct_tasks_and_twenty_deterministic_files(self):
        self.assertEqual(hashlib.sha256(canonical(WORKSPACES).encode()).hexdigest(), SUITE_SHA256)
        self.assertEqual(len({c["id"] for c in CASES}), 15)
        self.assertEqual(sum(not c["expected"] for c in CASES), 5)
        self.assertEqual(sum(len(p) for _, p in self.fixtures), 975)
        for w in WORKSPACES:
            self.assertEqual(list(documents(w)), list(documents(w)))
            self.assertEqual([len(rows) for suffix, rows in w["documents"]], [65, 64, 64, 64])

    def test_all_oracles_survive_large_partial_context_with_exact_hashes_and_unchanged_budget(self):
        for case in CASES:
            sources, passages = self.fixtures[case["workspace"]]
            before = copy.deepcopy(passages)
            p = product(case, sources, passages)
            result = verify_product(p, sources, 8192, question=case["question"], require_claims=bool(case["expected"]))
            with self.subTest(case=case["id"]):
                self.assertTrue(selection_result(case, p)["selection_passed"])
                self.assertEqual(result["selected_documents"], 4)
                self.assertGreater(result["omitted_passages"], 0)
                self.assertGreater(result["shortened_passages"], 0)
                self.assertLessEqual(result["context_units"], 8192)
                self.assertEqual(passages, before)

    def test_one_sided_contradiction_empty_positive_and_wrong_versions_never_qualify(self):
        case = CASES[5]
        sources, passages = self.fixtures[case["workspace"]]
        p = product(case, sources, passages)
        p["claims"].pop()
        self.assertFalse(selection_result(case, p)["selection_passed"])
        p["claims"] = []
        with self.assertRaises(ProductRejected):
            verify_product(p, sources, 8192, question=case["question"])
        p = product(CASES[10], sources, passages)
        p["snapshots"]["sources"][sources[0]["id"]] = 2
        with self.assertRaises(ProductRejected):
            verify_product(p, sources, 8192, question=CASES[10]["question"], require_claims=False)

    def test_negative_irrelevant_exact_quote_and_document_instruction_fail_relevance(self):
        case = CASES[10]
        sources, passages = self.fixtures[0]
        p = product(case, sources, passages)
        for text in (CASES[0]["expected"][0], POISON):
            p["claims"] = [{"text": text, "evidence_ids": ["synthetic-only"], "review_status": "pending"}]
            self.assertFalse(selection_result(case, p)["selection_passed"])

    def test_caller_interval_qualification_rejects_missing_duplicate_and_nonfinite_records(self):
        events = [{"sequence": n, "started": n, "finished": 10} for n in range(1, 6)]
        self.assertEqual(peak_overlap(events, range(1, 6)), 5)
        serial = [{"sequence": n, "started": n * 2, "finished": n * 2 + 1} for n in range(1, 6)]
        self.assertEqual(peak_overlap(serial, range(1, 6)), 1)
        for invalid in (events[:-1], [events[0]] * 5, [{**e, "finished": float("nan")} for e in events]):
            with self.assertRaises(ValueError):
                peak_overlap(invalid, range(1, 6))

    def test_volume_driver_is_explicit_without_private_mounts_or_production_factory(self):
        args = ({"api": "sha256:api", "postgres": "sha256:pg"}, "key", "pw", "t" * 32, "198.19.0.0/28",
                Path("/protected/profile"), Path("/protected/key"), "provider")
        volume, short = definition(*args, workload="quote-volume-v1"), definition(*args)
        self.assertTrue(volume["services"]["driver"]["command"][-1].endswith("/quote_volume_driver.py"))
        self.assertNotIn("volumes", volume["services"]["driver"])
        self.assertEqual(volume["services"]["api"]["environment"].pop("LA_QUOTE_VOLUME_CANDIDATE"), "lawyer-real-provider-jobs-v1")
        self.assertEqual(volume["services"]["api"], short["services"]["api"])

    def test_default_and_candidate_match_independent_retained_pretrial_code_references(self):
        reference = json.loads((ROOT / "deploy/fixtures/quote-volume-packing-references.json").read_text())
        self.assertEqual(reference["suite_sha256"], SUITE_SHA256)
        for case, row in zip(CASES, reference["cases"], strict=True):
            _, passages = self.fixtures[case["workspace"]]
            self.assertEqual(row["case"], case["id"])
            self.assertEqual(digest(pack_private_context(case["question"], passages, context_limit=8192)), row["literal_sha256"])
            self.assertEqual(digest(pack_private_context(case["question"], passages, context_limit=8192, candidate_profile=True)),
                             row["candidate_sha256"])

    def test_candidate_cannot_install_without_both_explicit_disposable_markers(self):
        for values in ({"LA_LOAD_REAL_PROVIDER": "", "LA_QUOTE_VOLUME_CANDIDATE": MARKER},
                       {"LA_LOAD_REAL_PROVIDER": MARKER, "LA_QUOTE_VOLUME_CANDIDATE": ""}):
            with patch.dict(os.environ, values), self.assertRaises(ValueError):
                install_volume_packing()

    def test_complete_authenticated_volume_driver_preserves_failed_case_without_retry_or_lost_original_checks(self):
        import quote_volume_driver as driver
        from fastapi.testclient import TestClient

        import app.research as research
        from app.config import Settings
        from app.main import create_app

        class Oracle(MeasuredProvider):
            def __init__(self, settings):
                super().__init__(settings)
                self.barrier = Barrier(5)
                self.wrong_negative = False

            def _complete(self, messages, *args, **kwargs):
                payload = json.loads(messages[-1]["content"])
                case = next(c for c in CASES if c["question"] == payload["question"])
                self.barrier.wait(timeout=10)
                expected = CASES[0]["expected"] if self.wrong_negative and case["id"] == CASES[10]["id"] else case["expected"]
                ids = [next(q["id"] for p in payload["evidence"] if text in p["text"] for q in p["quotes"]) for text in expected]
                return json.dumps({"quote_ids": list(dict.fromkeys(ids))})

        for wrong in (False, True):
            with self.subTest(wrong=wrong), tempfile.TemporaryDirectory() as folder:
                settings = Settings(_env_file=None, demo_mode=True, cookie_secure=False, data_dir=Path(folder),
                    LLM_PROVIDER_BASE_URL="http://127.0.0.1/v1", LLM_PROVIDER_API_KEY="synthetic-only", LLM_PROVIDER_MODEL="synthetic")
                app, oracle = create_app(settings), Oracle(settings)
                oracle.wrong_negative = wrong

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
                    app.state.provider = oracle
                    app.state.settings.provider_context_limit = 8192
                    with patch.object(driver, "httpx", SimpleNamespace(Client=lambda **kwargs: nullcontext(client))), patch.dict(
                            os.environ, {"LA_REAL_JOB_WORKLOAD": "quote-volume-v1", "LA_REAL_JOB_CONTEXT_UNITS": "8192",
                                         "LA_LOAD_CONTROL_TOKEN": "synthetic-control-no-real-secret"}), patch.object(
                            research, "pack_private_context", side_effect=lambda *a, **k: pack_private_context(*a, **k, candidate_profile=True)):
                        report = driver.run()
                    self.assertEqual(report["status"], "failed" if wrong else "passed", report.get("failure_stage"))
                    self.assertEqual(report["passed_tasks"], 14 if wrong else 15)
                    self.assertEqual([w["peak_application_calls"] for w in report["waves"]], [5, 5, 5])
                    self.assertEqual(oracle.calls, 15)
                    self.assertTrue(report["originals_and_versions_unchanged"])
                    self.assertEqual(len(report["corpus"]), 20)


if __name__ == "__main__":
    unittest.main()
