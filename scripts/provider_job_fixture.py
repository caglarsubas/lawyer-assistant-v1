"""Explicit disposable real-provider application factory; never production entrypoint."""

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

import httpx
from load_fixture import fixture_settings

from app.provider import Provider

MARKER = "lawyer-real-provider-jobs-v1"
PROFILE_FIELDS = {"provider_base_url", "provider_model", "provider_context_limit", "provider_allow_plain_http",
                  "provider_identity_verified", "provider_cloud_fallback_disabled", "provider_tenant_id",
                  "provider_org_id", "provider_key_id", "provider_tunnel_url", "provider_tunnel_approved",
                  "provider_tunnel_approved_host"}


# Only this disposable factory installs the observer; production keeps httpx unchanged.
RELAY_FAILURE_CODES = frozenset({
    "provider_upstream_http_error", "provider_encoding_rejected", "provider_response_budget_exceeded",
    "provider_model_rejected", "provider_response_invalid", "provider_tls_failed", "provider_upstream_timeout",
    "provider_upstream_transport_failed", "provider_http_protocol_failed", "provider_connection_closed",
    "provider_connection_reset", "provider_connection_refused", "provider_network_denied",
    "provider_network_unreachable", "provider_transport_resource_exhausted",
})


def observe_relay_failure(response, note):
    """Read only a bounded failed response; export an exact enum, never arbitrary text."""
    if response.status_code == 200:
        return
    try:
        length = response.headers.get("content-length", "")
        if not length.isdigit() or not 0 < int(length) <= 512 or response.headers.get("content-encoding", "identity") != "identity":
            return
        body = bytearray()
        for chunk in response.iter_bytes(512):
            if len(body) + len(chunk) > 512:
                return
            body.extend(chunk)
        value = json.loads(body)
        code = value.get("code") if isinstance(value, dict) else None
        if isinstance(code, str) and code in RELAY_FAILURE_CODES:
            note("relay_" + code)
    except (httpx.HTTPError, ValueError, TypeError, RecursionError):
        pass  # The provider still rejects the original failed HTTP status.


def install_relay_observer(provider):
    import app.provider as module

    if os.environ.get("LA_LOAD_REAL_PROVIDER") != MARKER:
        raise ValueError("Relay observation requires an explicit disposable factory")

    class ObservedHTTPX:
        Timeout, HTTPError = httpx.Timeout, httpx.HTTPError

        @staticmethod
        def Client(*args, **kwargs):
            client = httpx.Client(*args, **kwargs)
            client.event_hooks["response"].append(provider.observe_http)
            client.event_hooks["response"].append(lambda response: observe_relay_failure(response, provider.note))
            return client

    # Replace only the provider module's local namespace in this fixture process.
    # No global httpx patch, accepted-body interception, transport replacement or retry.
    module.httpx = ObservedHTTPX


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
        self.http_observations = {}

    def observe_http(self, response):
        """Finite stage/status counters only; never record a URL or successful body."""
        stage = {"/v1/models": "metadata", "/v1/chat/completions": "completion"}.get(response.request.url.path)
        if stage is None:
            return
        status = response.status_code
        code = str(status) if status in {200, 400, 401, 403, 408, 413, 429, 500, 502, 503, 504} else "other"
        with self.lock:
            name = stage + "_http_" + code
            self.http_observations[name] = self.http_observations.get(name, 0) + 1

    def http_snapshot(self):
        with self.lock:
            return dict(self.http_observations)

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
                if not answer.claims:
                    self.note("empty_quote_selection")
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
    install_relay_observer(provider)

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

    @app.get("/_provider_jobs/http")
    def http_state(x_load_token: str = Header(default="")):
        if not secrets.compare_digest(x_load_token, token):
            raise HTTPException(403, "Synthetic control denied")
        return provider.http_snapshot()

    return app
