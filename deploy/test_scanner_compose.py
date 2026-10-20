"""Exercise Compose interpolation without reading the operator's credential file."""

import json
import os
import subprocess
import unittest
from pathlib import Path


class ScannerComposeTests(unittest.TestCase):
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
