"""Provider metadata and relay boundaries; never uses operator credentials."""
import importlib.util
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.provider import Provider, ProviderError

spec = importlib.util.spec_from_file_location("local_provider_relay", Path(__file__).parents[2] / "deploy/provider/relay.py")
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


def settings(**changes):
    values = dict(provider_base_url="https://10.20.0.8/v1", provider_api_key="fixture-secret",
                  provider_model="local-model", provider_identity_verified=True,
                  provider_cloud_fallback_disabled=True, provider_allow_plain_http=False,
                  provider_context_limit=8192)
    values.update(changes)
    return SimpleNamespace(**values)


def local_model(**changes):
    model = dict(id="local-model", backend="ollama_http", format="ollama_http",
                 request_key_source="local-inference", max_model_len=32768)
    model.update(changes)
    return model


def transport(monkeypatch, response):
    seen = []
    client_type = httpx.Client

    def serve(request):
        seen.append(request)
        return response

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_type(transport=httpx.MockTransport(serve), **kwargs))
    return seen


def test_metadata_probe_is_authenticated_local_and_context_bounded(monkeypatch):
    seen = transport(monkeypatch, httpx.Response(200, json={"data": [local_model()]}))
    result = Provider(settings()).probe()
    assert result["ready"] and result["checks"] == dict(configuration=True, connection=True, model=True)
    assert result["model"] == dict(id="local-model", backend="ollama_http", context_limit=32768)
    assert len(seen) == 1 and seen[0].method == "GET" and seen[0].url.path == "/v1/models"
    assert seen[0].headers["authorization"] == "Bearer fixture-secret"


@pytest.mark.parametrize("field", ["provider_identity_verified", "provider_cloud_fallback_disabled"])
def test_unattested_metadata_and_generation_make_no_network_call(monkeypatch, field):
    def deny(*args, **kwargs):
        raise AssertionError("No network before deployment attestation")
    monkeypatch.setattr(httpx, "Client", deny)
    provider = Provider(settings(**{field: False}))
    assert provider.probe()["checks"] == dict(configuration=False, connection=False, model=False)
    with pytest.raises(ProviderError):
        provider.generate("private fixture", [])


@pytest.mark.parametrize(("models", "code"), [
    ([], "provider_model_unavailable"),
    ([local_model(), local_model()], "provider_model_unavailable"),
    ([local_model(backend="openrouter", format="openrouter")], "provider_model_not_local"),
    ([local_model(backend="vllm", format="vllm")], "provider_model_not_local"),
    ([local_model(request_key_source="openrouter-api-key")], "provider_model_not_local"),
    ([local_model(max_model_len=None)], "provider_context_unverified"),
    ([local_model(max_model_len=4096)], "provider_context_unverified"),
    ([local_model(max_model_len=True)], "provider_context_unverified"),
])
def test_model_preflight_rejects_remote_ambiguous_and_insufficient_context(monkeypatch, models, code):
    seen = transport(monkeypatch, httpx.Response(200, json={"data": models}))
    provider = Provider(settings())
    assert provider.probe()["issues"][0]["code"] == code
    with pytest.raises(ProviderError):
        provider.generate("private fixture", [])
    assert all(request.method == "GET" for request in seen)


@pytest.mark.parametrize("status", [401, 403, 429, 500, 302])
def test_probe_never_reflects_provider_error_body(monkeypatch, status):
    transport(monkeypatch, httpx.Response(status, json={"error": "secret-prompt-or-key"}))
    result = Provider(settings()).probe()
    assert not result["ready"] and not result["checks"]["connection"]
    assert "secret-prompt-or-key" not in str(result)


def test_probe_rejects_oversized_model_metadata(monkeypatch):
    transport(monkeypatch, httpx.Response(200, content=b' ' * (1024 * 1024 + 1)))
    assert Provider(settings()).probe()["issues"][0]["code"] == "provider_probe_failed"


@pytest.mark.parametrize("extra", [
    {"fallback_from_model": "local-model"}, {"fallback_reason": "backend_error"},
    {"substitution_reason": "resident_model"}, {"request_key_source": "openrouter-api-key"},
])
def test_generation_never_accepts_substitution_or_cloud_fallback_metadata(monkeypatch, extra):
    monkeypatch.setattr(Provider, "probe", lambda self: {"ready": True})
    payload = {"model": "local-model", "choices": [{"finish_reason": "stop", "message": {"content": '{"claims":[]}'}}], **extra}
    transport(monkeypatch, httpx.Response(200, json=payload))
    with pytest.raises(ProviderError, match="fallback or external"):
        Provider(settings()).generate("synthetic fixture", [])


def completion(**changes):
    payload = dict(model="local-model", messages=[{"role": "user", "content": "synthetic fixture"}],
                   stream=False, max_completion_tokens=50, temperature=0, response_format={"type": "json_object"})
    payload.update(changes)
    return payload


@pytest.mark.parametrize("changes", [
    {"model": "cloud-model"}, {"stream": True}, {"tools": []}, {"extra_body": {"url": "https://external.example"}},
    {"max_completion_tokens": 1001}, {"max_completion_tokens": True}, {"temperature": 1},
    {"messages": [{"role": "tool", "content": "untrusted"}]},
    {"messages": [{"role": "user", "content": [{"image_url": "https://external.example"}]}]},
    {"messages": [{"role": "user", "content": "fixture", "name": "arbitrary"}]},
    {"response_format": {"type": "text"}},
])
def test_relay_admits_only_the_pinned_bounded_text_completion(changes):
    assert relay.valid_completion(completion(), "local-model")
    assert not relay.valid_completion(completion(**changes), "local-model")


def test_relay_metadata_hides_other_models_and_native_paths():
    result = relay.filtered_models({"data": [local_model(model_path="/private/native/path"), local_model(id="other")]}, "local-model")
    assert result["data"] == [local_model()]
    assert relay.filtered_models({"data": [local_model(backend="openrouter")]}, "local-model")["data"] == []


@pytest.fixture
def running_relay():
    server = relay.Server(("127.0.0.1", 0), "192.168.65.254", "local-model")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False) as client:
        yield client
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


@pytest.mark.parametrize("path", [
    "/v1/admin/auth-keys", "/v1/admin/auth-keys:reload", "/v1/models?url=anything", "/v1/models/anything",
    "/v1/chat/completions/", "/v1/../admin", "http://external.example/v1/models",
])
def test_relay_rejects_administration_or_ambiguous_routes(running_relay, path):
    request = running_relay.build_request("POST", "/")
    request.url = httpx.URL(str(running_relay.base_url).rstrip("/") + "/" + path.lstrip("/"))
    response = running_relay.send(request)
    assert response.status_code == 404


def test_relay_requires_auth_even_for_model_discovery(running_relay):
    assert running_relay.get("/v1/models").status_code == 401
    assert running_relay.get("/health").json() == {"status": "ok", "scope": "relay_process_only"}


def test_relay_forwards_only_explicit_headers_to_fixed_upstream(monkeypatch, running_relay):
    calls = []

    class Response:
        status = 200
        sent = False

        def getheader(self, name, default=None):
            return default

        def read1(self, size):
            if self.sent:
                return b""
            self.sent = True
            return json.dumps({"model": "local-model", "choices": []}).encode()

    class Connection:
        def __init__(self, host, port, timeout):
            assert host == "192.168.65.254" and port == 8080

        def request(self, method, path, body, headers):
            calls.append((method, path, body, headers))

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(relay.http.client, "HTTPConnection", Connection)
    response = running_relay.post("/v1/chat/completions", json=completion(), headers={
        "Authorization": "Bearer fixture-secret", "X-Forwarded-Host": "outside.example",
        "x-engine-model-substitution": "on", "Cookie": "private=unrelated",
    })
    assert response.status_code == 200
    assert calls[0][3] == {
        "Authorization": "Bearer fixture-secret", "Content-Type": "application/json", "Accept-Encoding": "identity",
        "x-engine-model-substitution": "off", "Connection": "close",
    }
