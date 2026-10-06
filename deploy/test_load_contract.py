"""Fast load-harness boundaries; no Docker workload runs in routine CI."""

import json
import math
import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from load_fixture import MARKER, ControlledProvider, fixture_settings  # noqa: E402
from load_metrics import cgroup_peaks, distribution, memory_bytes, resource_sample  # noqa: E402
from qualify_load import ResourceSampler, compose_definition  # noqa: E402


class LoadContracts(unittest.TestCase):
    def test_isolated_definition_excludes_live_env_ports_binds_and_driver_secrets(self):
        definition = compose_definition({"api": "sha256:api", "postgres": "sha256:postgres"}, "test-key", "test-password", "t" * 32)
        self.assertEqual(set(definition["services"]), {"api", "postgres", "driver"})
        self.assertEqual(set(definition["volumes"]), {"documents", "postgres"})
        self.assertEqual(definition["networks"], {"isolated": {"internal": True}})
        for service in definition["services"].values():
            self.assertNotIn("ports", service)
            self.assertNotIn("env_file", service)
            self.assertNotIn("network_mode", service)
            self.assertEqual(service["pull_policy"], "never")
            self.assertEqual(service["networks"], ["isolated"])
            self.assertTrue(all(mount.split(":")[0] in definition["volumes"] for mount in service.get("volumes", [])))
        api, driver = (definition["services"][name] for name in ("api", "driver"))
        self.assertNotIn("volumes", driver)
        self.assertNotIn("LA_ENCRYPTION_KEY", driver["environment"])
        self.assertNotIn("LA_RECOVERY_DRILL", api["environment"])
        self.assertIn("load_fixture:create_app", api["command"])
        self.assertEqual(definition["services"]["postgres"]["environment"]["POSTGRES_DB"], "lawyer_load_drill")

    def test_factory_ignores_inherited_provider_secrets_and_requires_disposable_identity(self):
        environment = {"LA_LOAD_DRILL": MARKER, "LA_LOAD_CONTROL_TOKEN": "t" * 32,
                       "LA_DATABASE_URL": "postgresql+psycopg://lawyer:fixture@postgres:5432/lawyer_load_drill",
                       "LA_ENCRYPTION_KEY": "fixture", "LLM_PROVIDER_API_KEY": "must-never-be-loaded",
                       "LLM_PROVIDER_BASE_URL": "https://external.invalid"}
        with patch.dict(os.environ, environment, clear=True):
            settings, token = fixture_settings()
            self.assertEqual(token, "t" * 32)
            self.assertEqual(settings.provider_api_key, "")
            self.assertEqual(settings.provider_base_url, "")
            self.assertTrue(settings.demo_mode)
            self.assertEqual(settings.provider_model, "SYNTHETIC-CONTROLLED-NO-INFERENCE")
            for field, value in (("LA_LOAD_DRILL", ""), ("LA_LOAD_CONTROL_TOKEN", "short"),
                                 ("LA_DATABASE_URL", "postgresql+psycopg://lawyer:fixture@postgres:5432/lawyer"),
                                 ("LA_DATABASE_URL", "postgresql+psycopg://lawyer:fixture@outside:5432/lawyer_load_drill")):
                with self.subTest(field=field, value=value), patch.dict(os.environ, {field: value}), self.assertRaises(ValueError):
                    fixture_settings()

    def test_controlled_provider_holds_five_calls_and_returns_only_exact_quote(self):
        import time

        provider = ControlledProvider(timeout=2)
        provider.control(True)
        passages = [{"id": "synthetic", "text": "SYNTHETIC quoted bytes"}]
        with ThreadPoolExecutor(5) as pool:
            futures = [pool.submit(provider.generate, "SYNTHETIC", passages) for _ in range(5)]
            try:
                deadline = time.monotonic() + 1
                while provider.snapshot()["active"] != 5 and time.monotonic() < deadline:
                    time.sleep(.005)
                self.assertEqual(provider.snapshot()["active"], 5)
                self.assertFalse(any(future.done() for future in futures))
            finally:
                provider.control(False)
            answers = [json.loads(future.result(timeout=1)) for future in futures]
        self.assertEqual(provider.snapshot(), {"active": 0, "peak": 5, "calls": 5, "held": False})
        self.assertTrue(all(answer["claims"] == [{"text": passages[0]["text"], "evidence_ids": ["synthetic"]}] for answer in answers))

    def test_provider_gate_times_out_and_releases_its_counter(self):
        provider = ControlledProvider(timeout=.01)
        provider.control(True)
        with self.assertRaises(ValueError):
            provider.generate("SYNTHETIC", [{"id": "synthetic", "text": "fixture"}])
        self.assertEqual(provider.snapshot()["active"], 0)

    def test_distribution_uses_observed_nearest_rank_and_rejects_bad_samples(self):
        self.assertEqual(distribution([4, 1, 3, 2]), {"samples": 4, "min": 1, "median": 2.5, "p95_nearest_rank": 4, "max": 4})
        self.assertEqual(distribution(list(range(1, 21)))["p95_nearest_rank"], 19)
        for values in ([], [-1], [math.nan], [math.inf]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                distribution(values)

    def test_resource_units_and_missing_or_impossible_samples(self):
        self.assertEqual(memory_bytes("1GiB"), 1024**3)
        self.assertEqual(memory_bytes("1.5MB"), 1500000)
        valid = {"MemUsage": "64MiB / 1GiB", "CPUPerc": "175.2%", "PIDs": "16"}
        self.assertEqual(resource_sample(valid), {"memory_bytes": 64 * 1024**2, "memory_limit_bytes": 1024**3,
                                                "cpu_percent": 175.2, "pids": 16})
        for override in ({"MemUsage": "2GiB / 1GiB"}, {"MemUsage": "0B / 0B"}, {"MemUsage": "missing"},
                         {"CPUPerc": "nan%"}, {"PIDs": "0"}, {"CPUPerc": "-1%"}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                resource_sample({**valid, **override})

    def test_sampler_fails_closed_on_missing_service_or_command_error(self):
        for output in ("", '{"Name":"unexpected"}', 'null'):
            with patch("qualify_load.command", return_value="/fixture-api"):
                sampler = ResourceSampler({"api": "id"})

            def once(*args, **kwargs):
                sampler.stop.set()
                return output

            with patch("qualify_load.command", side_effect=once):
                sampler.thread.start()
                sampler.thread.join(timeout=1)
            result = sampler.finish()
            self.assertFalse(result["valid"])
            self.assertGreater(result["sampling_errors"], 0)

    def test_kernel_peaks_require_real_caps_and_cpu_accounting(self):
        raw = "100\n1024\n16\n256\nusage_usec 1200\nnr_periods 10\nnr_throttled 1\nthrottled_usec 100\n"
        self.assertEqual(cgroup_peaks(raw)["memory_peak_bytes"], 100)
        self.assertEqual(cgroup_peaks(raw)["pids_peak"], 16)
        for bad in ("", raw.replace("1024", "max"), raw.replace("100\n1024", "2048\n1024"),
                    raw.replace("16\n256", "257\n256"), raw.replace("usage_usec 1200\n", "")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cgroup_peaks(bad)

    def test_fixture_control_routes_are_absent_from_production_application(self):
        from app.config import Settings
        from app.main import create_app

        app = create_app(Settings.model_construct())  # No lifespan, database or dotenv.
        self.assertFalse(any(path.startswith("/_load") for path in app.openapi()["paths"]))


if __name__ == "__main__":
    unittest.main()
