#!/usr/bin/env python3
"""Read-only, secret-free check of the native engine tenant and pinned model.

Run with backend/.venv/bin/python; no credentials are accepted as command-line
arguments, written, replaced or printed. This deliberately does not attest that
the engine's cloud fallback is disabled and never performs generation.
"""
import argparse
import hmac
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx

from app.config import Settings
from app.provider import Provider, ProviderError


def active(record):
    now = datetime.now(timezone.utc)
    for field, lower in (("not_before", True), ("expires_at", False)):
        if record.get(field) is not None:
            stamp = datetime.fromisoformat(record[field].replace("Z", "+00:00"))
            if stamp.tzinfo is None or (now < stamp if lower else now >= stamp):
                return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root", required=True, type=Path)
    parser.add_argument("--native-url", default="http://127.0.0.1:8080/v1")
    args = parser.parse_args()
    settings = Settings()
    settings.provider_base_url = args.native_url
    settings.provider_allow_plain_http = True
    # This read-only check targets the native registry/engine, independently of
    # the application's approved tunnel. Never mutate the persisted settings.
    settings.provider_tunnel_url = ""
    settings.provider_tunnel_approved = False
    settings.provider_tunnel_approved_host = ""
    try:
        Provider(settings).validate_origin()
        records = json.loads((args.engine_root / ".auth_keys.json").read_text())
        matches = [row for row in records if isinstance(row, dict) and isinstance(row.get("key"), str)
                   and hmac.compare_digest(row["key"], settings.provider_api_key)]
        expected = {"tenant": settings.provider_tenant_id, "org_id": settings.provider_org_id,
                    "key_id": settings.provider_key_id}
        # The product identity is fixed; changing all configuration fields must
        # not turn a different product's key into a successful attestation.
        product = {"tenant": "lawyer-assistant-v1", "org_id": "org-lawyer", "key_id": "lawyer-assistant-v1-primary"}
        verified = len(matches) == 1 and expected == product and all(matches[0].get(k) == v for k, v in product.items()) and active(matches[0])
        report = {"identity_verified": verified,
                  "actual_identity": [{k: row.get(k) for k in product} for row in matches],
                  "cloud_fallback_verification": "separate_effective_deployment_check_required",
                  "generation_performed": False}
        if not verified:
            print(json.dumps(report))
            return 2
        # Fixed local transport and a bounded model listing; no prompt data.
        with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
            with client.stream("GET", Provider(settings)._base() + "/models", headers={
                "Authorization": f"Bearer {settings.provider_api_key}", "Accept-Encoding": "identity",
            }) as response:
                report["authentication_http_status"] = response.status_code
                if response.status_code != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
                    print(json.dumps(report))
                    return 2
                data = bytearray()
                for chunk in response.iter_bytes():
                    if len(data) + len(chunk) > 1024 * 1024:
                        raise ValueError("bounded metadata exceeded")
                    data.extend(chunk)
        models = json.loads(data).get("data", [])
        report["local_models"] = [{key: item.get(key) for key in ("id", "backend", "format", "max_model_len")}
                                  for item in models if item.get("request_key_source") == "local-inference"
                                  and item.get("backend") in {"ollama_http", "llama_cpp", "mlx"}]
        print(json.dumps(report))
        return 0
    except (OSError, ValueError, TypeError, KeyError, ProviderError, httpx.HTTPError):
        print(json.dumps({"identity_verified": False, "error": "preflight_could_not_be_completed", "generation_performed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
