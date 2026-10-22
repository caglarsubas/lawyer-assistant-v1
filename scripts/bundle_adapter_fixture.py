"""Fixed invented in-process HTTP transport; no sockets, keys or runtime mounts.

The production Provider handles these mock responses unchanged. Successful mock
selection is protocol evidence only, not native model or legal qualification.
"""

import json
from threading import Lock
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from disposable_bundle_adapter import MARKER, DisposableBundleAdapter

from app.provider import Provider


def settings(**changes):
    values = dict(provider_base_url="https://127.0.0.1/v1", provider_api_key="SYNTHETIC-NOT-A-KEY",
                  provider_model="SYNTHETIC-NO-INFERENCE", provider_identity_verified=True,
                  provider_cloud_fallback_disabled=True, provider_allow_plain_http=False, provider_context_limit=8192)
    values.update(changes)
    return SimpleNamespace(**values)


class ControlledExchange:
    def __init__(self, select=None, *, status=200, metadata=None, completion=None):
        self.select = select or (lambda payload: json.dumps({"bundle_ids": [b["id"] for b in
                                   json.loads(payload["messages"][1]["content"])["bundles"]]}))
        self.status, self.metadata, self.completion = status, metadata or {}, completion or {}
        self.requests = []
        self.lock = Lock()

    def serve(self, request):
        with self.lock:
            self.requests.append(request)
        if request.method == "GET" and request.url.path == "/v1/models":
            model = dict(id="SYNTHETIC-NO-INFERENCE", backend="ollama_http", format="ollama_http",
                         request_key_source="local-inference", max_model_len=32768)
            return httpx.Response(200, json={"data": [{**model, **self.metadata}]})
        if request.method == "POST" and request.url.path == "/v1/chat/completions":
            payload = json.loads(request.content)
            content = self.select(payload)
            return httpx.Response(self.status, json={"model": "SYNTHETIC-NO-INFERENCE",
                "choices": [{"finish_reason": "stop", "message": {"content": content}}], **self.completion})
        raise AssertionError("Unexpected disposable transport route")

    def __enter__(self):
        client = httpx.Client
        self.patch = patch("app.provider.httpx", SimpleNamespace(Timeout=httpx.Timeout, HTTPError=httpx.HTTPError,
            Client=lambda **kwargs: client(transport=httpx.MockTransport(self.serve), **kwargs)))
        self.patch.__enter__()
        return self

    def __exit__(self, *args):
        return self.patch.__exit__(*args)

    def adapter(self, **changes):
        return DisposableBundleAdapter(Provider(settings(**changes)), mode=MARKER)

    def counts(self):
        return {"mock_metadata_requests": sum(r.method == "GET" for r in self.requests),
                "mock_completion_requests": sum(r.method == "POST" for r in self.requests),
                "network_http_calls": 0, "inference_calls": 0}
