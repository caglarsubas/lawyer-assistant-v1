"""Real parser and adversarial frozen-source qualification checks; no inference."""

import copy
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from provider_job_checks import QUESTION, ProductRejected, verify_product  # noqa: E402
from provider_job_driver import corpus  # noqa: E402
from provider_job_fixture import install_relay_observer, observe_relay_failure  # noqa: E402
from qualify_provider_jobs import definition  # noqa: E402

from app.context_packing import pack_private_context  # noqa: E402
from app.extract import extract  # noqa: E402


def fixture():
    sources, passages = [], []
    with tempfile.TemporaryDirectory() as directory:
        for suffix, content in corpus(0, "mixed-formats-v1"):
            path = Path(directory) / ("synthetic." + suffix)
            path.write_bytes(content)
            result = extract(path, "." + suffix)
            source = {"id": suffix, "revision": 1, "sha256": hashlib.sha256(content).hexdigest(), "passages": []}
            for index, passage in enumerate(result["passages"]):
                value = {**passage, "id": f"{suffix}-{index}",
                         "text_sha256": hashlib.sha256(passage["text"].encode()).hexdigest()}
                source["passages"].append(value)
                passages.append({**value, "document_id": suffix, "document_revision": 1, "document_sha256": source["sha256"]})
            sources.append(source)
    packed = pack_private_context(QUESTION, passages, context_limit=8192)
    evidence, manifest = packed["evidence"], packed["manifest"]
    product = {"status": "needs_review", "snapshots": {"sources": {s["id"]: 1 for s in sources},
               "provider": "local-provider-validated-quotes", "context_pack": {"messages_sha256": manifest["prompt"]["messages_sha256"]}},
               "evidence": evidence, "context_pack": manifest,
               "claims": [{"text": evidence[0]["text"], "evidence_ids": [evidence[0]["id"]], "review_status": "pending"}],
               "critical_gaps": ["legal_corpus_unqualified"], "coverage": {"gaps": ["SYNTHETIC unreviewed corpus"]}}
    return product, sources


class MixedProviderContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.product, cls.sources = fixture()

    def test_real_four_format_parser_context_is_partial_grounded_and_within_budget(self):
        result = verify_product(self.product, self.sources, 8192)
        self.assertEqual(result["selected_documents"], 4)
        self.assertGreater(result["shortened_passages"], 0)
        self.assertGreater(result["omitted_passages"], 0)
        self.assertLessEqual(result["context_units"], 8192)
        self.assertTrue(all(s["passages"] for s in self.sources))

    def test_corrupted_versions_spans_quotes_hashes_and_coverage_cannot_qualify(self):
        mutations = [
            lambda p: p["snapshots"]["sources"].update(txt=2),
            lambda p: p["claims"][0].update(text="Fabricated conclusion"),
            lambda p: p["claims"][0].update(evidence_ids=["unknown"]),
            lambda p: p["context_pack"]["selected"][0].update(excerpt_start=1),
            lambda p: p["context_pack"]["selected"][0].update(original_text_sha256="0" * 64),
            lambda p: p["context_pack"]["prompt"].update(total_upper_bound_units=1),
            lambda p: p["context_pack"]["inventory"].update(omitted_passages=0),
            lambda p: p.update(status="reviewed"),
            lambda p: p.update(critical_gaps=[]),
        ]
        for change in mutations:
            product = copy.deepcopy(self.product)
            change(product)
            with self.subTest(change=mutations.index(change)), self.assertRaises((ValueError, KeyError)):
                verify_product(product, self.sources, 8192)

    def test_insufficient_declared_context_is_not_repaired_by_the_qualifier(self):
        with self.assertRaises(ValueError):
            verify_product(self.product, self.sources, 3072)

    def test_workload_selection_is_explicit_and_only_driver_gets_nonsecret_limits(self):
        args = ({"api": "sha256:api", "postgres": "sha256:pg"}, "key", "pw", "t" * 32, "198.19.0.0/28",
                Path("/protected/profile"), Path("/protected/key"), "provider")
        value = definition(*args, workload="mixed-formats-v1", context_limit=4096)
        self.assertEqual(value["services"]["driver"]["environment"]["LA_REAL_JOB_WORKLOAD"], "mixed-formats-v1")
        self.assertEqual(value["services"]["driver"]["environment"]["LA_REAL_JOB_CONTEXT_UNITS"], "4096")
        self.assertNotIn("LA_REAL_JOB_WORKLOAD", value["services"]["api"]["environment"])
        self.assertNotIn("volumes", value["services"]["driver"])
        for kwargs in ({"workload": "private-case"}, {"context_limit": True}, {"context_limit": 20000}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                definition(*args, **kwargs)

    def test_actual_research_routes_match_the_frozen_source_contract_without_inference(self):
        from fastapi.testclient import TestClient
        from load_driver import Workload
        from load_fixture import ControlledProvider

        from app.config import Settings
        from app.main import create_app

        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(_env_file=None, demo_mode=True, cookie_secure=False, data_dir=Path(folder),
                                LLM_PROVIDER_BASE_URL="", LLM_PROVIDER_API_KEY="", LLM_PROVIDER_MODEL="")
            app = create_app(settings)
            with TestClient(app) as client:
                login = client.post("/api/v1/auth/login", json={"username": "demo", "password": "demo-local-only"})
                client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
                app.state.provider = ControlledProvider()
                app.state.settings.provider_context_limit = 8192
                matter = client.post("/api/v1/matters", json={"title": "SYNTHETIC integration", "domain": "contracts"}).json()["id"]
                workload, sources = Workload(client, {}, {}), []
                for suffix, content in corpus(0, "mixed-formats-v1"):
                    identity = workload.upload(matter, suffix, content, metric="synthetic")
                    sources.append(client.get(f"/api/v1/matters/{matter}/documents/{identity}").json())
                row = workload.terminal(matter, workload.submit(matter))
                self.assertEqual(row["status"], "completed")
                product = client.get(f"/api/v1/matters/{matter}/products/{row['product_id']}").json()
                self.assertEqual(verify_product(product, sources, 8192)["selected_documents"], 4)
                product["claims"] = []
                with self.assertRaises(ProductRejected) as error:
                    verify_product(product, sources, 8192)
                self.assertEqual(error.exception.code, "product_claim_grounding_failed")

    def test_observer_never_records_bodies_headers_or_unknown_error_codes(self):
        notes = []
        for payload in ({"code": "provider_connection_reset", "error": "must never appear"},
                        {"code": "secret-like-unknown", "error": "must never appear"},
                        {"code": ["provider_connection_reset"]}):
            response = httpx.Response(502, json=payload)
            observe_relay_failure(response, notes.append)
        self.assertEqual(notes, ["relay_provider_connection_reset"])
        observe_relay_failure(httpx.Response(200, json={"code": "provider_connection_reset"}), notes.append)
        observe_relay_failure(httpx.Response(502, headers={"content-length": "513"}, content=b"x" * 513), notes.append)
        self.assertEqual(notes, ["relay_provider_connection_reset"])

    def test_observation_cannot_be_installed_without_explicit_fixture_mode(self):
        with patch.dict(os.environ, {"LA_LOAD_REAL_PROVIDER": ""}), self.assertRaises(ValueError):
            install_relay_observer(None)

    def test_original_short_profile_remains_a_single_exact_synthetic_txt(self):
        files = list(corpus(0, "short-txt-v1"))
        self.assertEqual(files, [("txt", b"SYNTHETIC payment odeme evidence: ornek tutar 100 birimdir.\n")])
        with self.assertRaises(ValueError):
            list(corpus(0, "unapproved"))


if __name__ == "__main__":
    unittest.main()
