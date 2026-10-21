"""Exercise Compose interpolation without reading the operator's credential file."""

import json
import os
import subprocess
import unittest
from pathlib import Path


class ScannerComposeTests(unittest.TestCase):
    def test_compose_secrets_are_file_scoped_without_literal_credential_interpolation(self):
        root = Path(__file__).resolve().parents[1]
        environment = {k: v for k, v in os.environ.items() if not k.startswith(("LA_", "LLM_PROVIDER_"))}
        environment["LA_BOOTSTRAP_USERNAME"] = "synthetic-admin"
        marker = "SYNTHETIC-CREDENTIAL-MUST-NOT-ENTER-COMPOSE"
        for name in ("LA_POSTGRES_PASSWORD", "LA_DATABASE_URL", "LA_ENCRYPTION_KEY",
                     "LA_BOOTSTRAP_PASSWORD", "LA_EXTRACTION_TOKEN", "LA_GATEWAY_TOKEN", "LLM_PROVIDER_API_KEY"):
            environment[name] = marker
        result = subprocess.run(["docker", "compose", "--env-file", "/dev/null", "-f",
                                 str(root / "compose.yaml"), "--profile", "publication", "--profile", "research",
                                 "config", "--format", "json"], env=environment,
                                capture_output=True, text=True, check=True, timeout=20)
        self.assertNotIn(marker, result.stdout)
        model = json.loads(result.stdout)
        grants = {"api": {"database_url", "encryption_key", "bootstrap_password", "extraction_token", "gateway_token", "provider_api_key"},
                  "extractor": {"extraction_token"}, "postgres": {"postgres_password"},
                  "publisher": {"database_url", "encryption_key"}, "gateway": {"gateway_token"}}
        for role, expected in grants.items():
            self.assertEqual({s["source"] for s in model["services"][role]["secrets"]}, expected)
        for role in ("web", "scanner", "opensearch", "fuseki"):
            self.assertFalse(model["services"][role].get("secrets"))

    def test_missing_blank_and_explicit_scanner_addresses(self):
        root = Path(__file__).resolve().parents[1]
        # Never inherit application credentials or provider configuration.
        base = {key: value for key, value in os.environ.items()
                if not key.startswith(("LA_", "LLM_PROVIDER_"))}
        base.update({key: "disposable-compose-contract-only" for key in (
            "LA_POSTGRES_PASSWORD", "LA_ENCRYPTION_KEY", "LA_BOOTSTRAP_USERNAME",
            "LA_BOOTSTRAP_PASSWORD", "LA_EXTRACTION_TOKEN")})
        for configured, expected in ((None, "scanner"), ("", "scanner"),
                                     ("approved-scanner", "approved-scanner")):
            with self.subTest(configured=configured):
                environment = dict(base)
                if configured is not None:
                    environment["LA_CLAMAV_HOST"] = configured
                result = subprocess.run(
                    ["docker", "compose", "--env-file", "/dev/null", "-f",
                     str(root / "compose.yaml"), "config", "--format", "json"],
                    env=environment, capture_output=True, text=True, timeout=20, check=True)
                model = json.loads(result.stdout)
                api, scanner = model["services"]["api"], model["services"]["scanner"]
                self.assertEqual(api["environment"]["LA_CLAMAV_HOST"], expected)
                self.assertEqual(str(api["environment"]["LA_SCANNER_MAX_SIGNATURE_AGE_DAYS"]), "7")
                self.assertEqual(str(scanner["environment"]["LA_SCANNER_MAX_SIGNATURE_AGE_DAYS"]), "7")
                self.assertEqual(set(scanner["networks"]), {"scanning"})
                self.assertNotIn("ports", scanner)
                self.assertTrue(scanner["read_only"])
                databases = next(mount for mount in scanner["volumes"]
                                 if mount["target"] == "/var/lib/clamav")
                self.assertTrue(databases["read_only"])
                self.assertTrue(model["networks"]["scanning"]["internal"])


if __name__ == "__main__":
    unittest.main()
