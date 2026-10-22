"""Cheap qualifier boundaries; routine CI performs no real provider calls."""

import io
import json
import sys
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from threading import Lock
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from qualify_provider import (  # noqa: E402
    IDENTITY,
    QUESTION,
    TEXT,
    fixture,
    main,
    oversized_guard,
    qualify,
    validate_quote,
)

from app.config import Settings  # noqa: E402
from app.evidence_prompt import measure_prompt  # noqa: E402
from app.provider import ProviderError  # noqa: E402


def settings():
    return Settings.model_construct(provider_base_url="http://127.0.0.1:8080/v1", provider_allow_plain_http=True,
        provider_api_key="synthetic-test-secret", provider_identity_verified=True, provider_cloud_fallback_disabled=True,
        provider_model="synthetic-model", provider_context_limit=8192,
        provider_tenant_id=IDENTITY[0], provider_org_id=IDENTITY[1], provider_key_id=IDENTITY[2])


class FixtureProvider:
    calls = []
    ready = True
    invalid = False

    def __init__(self, settings):
        self.settings = settings

    def readiness(self):
        return {"configuration_ready": True}

    def transport_metadata(self):
        return {"mode": "synthetic"}

    def probe(self):
        return {"ready": self.ready, "model": {"id": "synthetic-model", "backend": "ollama_http", "context_limit": 8192}}

    def generate(self, question, passages):
        self.calls.append(measure_prompt(question, passages)["total_upper_bound_units"])
        time.sleep(.01)  # Ensure concurrent callers overlap; no remote dependency.
        return "private-error-must-not-escape" if self.invalid else json.dumps({
            "summary": "", "claims": [{"text": TEXT, "evidence_ids": [passages[0]["id"]]}]})


class ProviderQualification(unittest.TestCase):
    def setUp(self):
        FixtureProvider.calls = []
        FixtureProvider.ready = True
        FixtureProvider.invalid = False

    def test_boundaries_are_exact_utf8_envelopes_without_oversized_passages(self):
        for units in (3072, 4096, 8192, 8193, 16384, 16385):
            passages = fixture(units)
            self.assertEqual(measure_prompt(QUESTION, passages)["total_upper_bound_units"], units)
            self.assertEqual(passages[0]["text"], TEXT)
            self.assertTrue(all(len(p["text"].encode()) <= 6000 for p in passages))
        for invalid in (True, 2048, 3071, 16386, "8192"):
            with self.assertRaises(ValueError):
                fixture(invalid)

    def test_oversized_context_never_constructs_http_client(self):
        with patch("app.provider.httpx.Client", side_effect=AssertionError("No network allowed")):
            self.assertTrue(oversized_guard(settings()))

    def test_quotes_reject_unknown_ids_paraphrases_extra_claims_and_summary(self):
        valid = {"summary": "", "claims": [{"text": TEXT, "evidence_ids": ["synthetic-first"]}]}
        validate_quote(json.dumps(valid), fixture())
        validate_quote(json.dumps({**valid, "claims": [{"text": "Örnek tutar 100 birimdir.",
                                                       "evidence_ids": ["synthetic-first"]}]}), fixture())
        for invalid in ("null", "[]", '{"summary":"private"}', json.dumps({**valid, "summary": "invented"}),
                        json.dumps({**valid, "claims": valid["claims"] * 2}),
                        json.dumps({**valid, "claims": [{"text": TEXT, "evidence_ids": ["other"]}]}),
                        json.dumps({**valid, "claims": [{"text": TEXT[:-1], "evidence_ids": ["synthetic-first"]}]}),
                        json.dumps({**valid, "claims": [{"text": ".", "evidence_ids": ["synthetic-first"]}]}),
                        json.dumps({**valid, "claims": [{"text": "paraphrase", "evidence_ids": ["synthetic-first"]}]})):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                validate_quote(invalid, fixture())

    def test_six_attempts_and_five_callers_drain_without_changing_settings(self):
        config = settings()
        before = config.model_dump()
        report = qualify(config, "synthetic-model", 8192, provider_type=FixtureProvider)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["generation_attempts"], 6)
        self.assertEqual(report["caller_counters"], {"active": 0, "peak": 5, "attempts": 5})
        self.assertEqual(len(FixtureProvider.calls), 6)
        self.assertEqual(FixtureProvider.calls[0], 8192)
        self.assertEqual(before, config.model_dump())
        self.assertNotIn("synthetic-test-secret", json.dumps(report))
        self.assertNotIn(TEXT, json.dumps(report))

    def test_identity_model_context_and_metadata_fail_before_generation(self):
        for name, value in (("provider_tenant_id", "other"), ("provider_org_id", "other"),
                            ("provider_key_id", "other"), ("provider_model", "other"), ("provider_context_limit", 4096)):
            config = settings()
            setattr(config, name, value)
            report = qualify(config, "synthetic-model", 8192, provider_type=FixtureProvider)
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["generation_attempts"], 0)
        FixtureProvider.ready = False
        report = qualify(settings(), "synthetic-model", 8192, provider_type=FixtureProvider)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(FixtureProvider.calls, [])

    def test_bad_completion_preserves_independent_results_without_exporting_body_or_retry(self):
        FixtureProvider.invalid = True
        report = qualify(settings(), "synthetic-model", 8192, provider_type=FixtureProvider)
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["boundary_exact_quote_verified"])
        self.assertEqual(report["boundary_failure_code"], "invalid_json")
        self.assertEqual(report["generation_attempts"], 6)
        self.assertEqual(len(FixtureProvider.calls), 6)
        self.assertEqual(len(report["five_callers"]), 5)
        self.assertNotIn("private-error-must-not-escape", json.dumps(report))

    def test_single_burst_failure_cannot_be_hidden_by_four_successes(self):
        lock = Lock()
        count = 0
        original = FixtureProvider.generate

        def one_failure(provider, question, passages):
            nonlocal count
            with lock:
                count += 1
                current = count
            if current == 3:
                time.sleep(.01)
                raise ProviderError("sensitive-upstream-error")
            return original(provider, question, passages)

        with patch.object(FixtureProvider, "generate", one_failure):
            report = qualify(settings(), "synthetic-model", 8192, provider_type=FixtureProvider)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(report["boundary_exact_quote_verified"])
        self.assertEqual(report["generation_attempts"], 6)
        self.assertEqual(sum(row["status"] == "passed" for row in report["five_callers"]), 4)
        self.assertEqual(report["caller_counters"], {"active": 0, "peak": 5, "attempts": 5})
        self.assertNotIn("sensitive-upstream-error", json.dumps(report))

    def test_settings_failure_cannot_dump_sensitive_validation_inputs(self):
        output = io.StringIO()
        argv = ["qualify_provider.py", "--expected-model", "synthetic-model", "--expected-context", "8192", "--execute-synthetic"]
        with patch.object(sys, "argv", argv), patch("app.config.load_settings", side_effect=ValueError("sensitive-secret")), redirect_stdout(output):
            self.assertEqual(main(), 1)
        self.assertEqual(json.loads(output.getvalue())["failure_code"], "configuration_or_code_binding_failed")
        self.assertNotIn("sensitive-secret", output.getvalue())


if __name__ == "__main__":
    unittest.main()
