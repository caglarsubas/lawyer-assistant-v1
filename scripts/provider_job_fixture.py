"""Explicit disposable real-provider application factory; never production entrypoint."""

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

from load_fixture import fixture_settings

from app.provider import Provider

MARKER = "lawyer-real-provider-jobs-v1"
PROFILE_FIELDS = {"provider_base_url", "provider_model", "provider_context_limit", "provider_allow_plain_http",
                  "provider_identity_verified", "provider_cloud_fallback_disabled", "provider_tenant_id",
                  "provider_org_id", "provider_key_id", "provider_tunnel_url", "provider_tunnel_approved",
                  "provider_tunnel_approved_host"}


def real_settings(profile, key):
    settings, token = fixture_settings()
    if (os.environ.get("LA_LOAD_REAL_PROVIDER") != MARKER or not isinstance(profile, dict)
            or set(profile) != PROFILE_FIELDS or not isinstance(key, str) or not 8 <= len(key) <= 4096
            or any(not 33 <= ord(char) <= 126 for char in key)
            or any(type(profile[k]) is not bool for k in ("provider_allow_plain_http", "provider_identity_verified",
                                                        "provider_cloud_fallback_disabled", "provider_tunnel_approved"))
            or (profile["provider_tenant_id"], profile["provider_org_id"], profile["provider_key_id"]) != (
                "lawyer-assistant-v1", "org-lawyer", "lawyer-assistant-v1-primary")
            or type(profile["provider_context_limit"]) is not int or not 3072 <= profile["provider_context_limit"] <= 16384):
        raise ValueError("Real-provider fixture requires an explicit disposable profile")
    for name, value in profile.items():
        setattr(settings, name, value)
    settings.provider_api_key = key
    if not Provider(settings).readiness()["configuration_ready"]:
        raise ValueError("Real-provider fixture configuration is not admitted")
    return settings, token


class MeasuredProvider(Provider):
    def __init__(self, settings):
        super().__init__(settings)
        self.lock = Lock()
        self.active = self.peak = self.calls = self.failures = 0
        self.diagnostics = {}

    def snapshot(self):
        with self.lock:
            return {**{k: getattr(self, k) for k in ("active", "peak", "calls", "failures")},
                    "diagnostics": dict(self.diagnostics)}

    def note(self, code):
        with self.lock:
            self.diagnostics[code] = self.diagnostics.get(code, 0) + 1

    def generate(self, question, passages):
        with self.lock:
            self.active += 1
            self.calls += 1
            self.peak = max(self.peak, self.active)
        try:
            response = super().generate(question, passages)
            from app.research import GeneratedAnswer
            try:
                answer = GeneratedAnswer.model_validate_json(response)
                evidence = {p["id"]: p["text"] for p in passages}
                for claim in answer.claims:
                    if any(ref not in evidence for ref in claim.evidence_ids):
                        self.note("unknown_reference")
                    elif any(claim.text not in evidence[ref] for ref in claim.evidence_ids):
                        self.note("unmatched_quote")
            except Exception:
                self.note("schema_invalid")
            return response
        except Exception as error:
            self.note({"Provider authentication and local model readiness could not be verified": "readiness_failed",
                       "Provider returned HTTP 502": "upstream_502",
                       "Context budget exceeded; reduce selected evidence": "context_exceeded"}.get(str(error), "adapter_failure"))
            with self.lock:
                self.failures += 1
            raise
        finally:
            with self.lock:
                self.active -= 1


def create_app():
    import secrets

    from fastapi import Header, HTTPException

    from app.main import create_app as application

    if os.environ.get("LA_LOAD_REAL_PROVIDER") != MARKER:
        raise ValueError("Real-provider fixture is not explicitly enabled")
    profile_file = Path("/run/secrets/provider-profile.json")
    key_file = Path("/run/secrets/provider-key")
    if profile_file.stat().st_size > 16384 or key_file.stat().st_size > 4096:
        raise ValueError("Fixture profile exceeded its bound")
    settings, token = real_settings(json.loads(profile_file.read_text()), key_file.read_text().strip())
    app = application(settings)
    original = app.router.lifespan_context
    provider = MeasuredProvider(settings)

    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            app.state.provider = provider
            yield

    app.router.lifespan_context = lifespan

    @app.get("/_provider_jobs/state")
    def state(x_load_token: str = Header(default="")):
        if not secrets.compare_digest(x_load_token, token):
            raise HTTPException(403, "Synthetic control denied")
        jobs = app.state.research_jobs
        with jobs._condition:
            admitted = len(jobs._jobs)
        return {"provider": provider.snapshot(), "admitted_jobs": admitted}

    return app
