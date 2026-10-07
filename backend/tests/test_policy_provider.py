"""No live provider calls: adversarial edge policy and consumer contract checks."""

import json
import socket
from types import SimpleNamespace

import httpx
import pytest

from app import policy
from app import provider as provider_module
from app.policy import evaluate, request_digest
from app.provider import Provider, ProviderError

PUBLIC_HOSTS = ["mevzuat.gov.tr"]
PUBLIC_ENDPOINT = "https://mevzuat.gov.tr/"


def test_public_concepts_and_explicit_matter_approval_are_distinct():
    assert evaluate("iş hukuku", PUBLIC_ENDPOINT, "public", PUBLIC_HOSTS)["decision"] == "ALLOW"
    matter = evaluate("iş hukuku", PUBLIC_ENDPOINT, "matter", PUBLIC_HOSTS)
    assert matter["decision"] == "REQUIRE_APPROVAL"
    assert "exact_request_approval_required" in matter["reason_codes"]


@pytest.mark.parametrize("query", [
    "12 345 678 901", "iş 12 345 678 901", "tbk madde 112", "iş ١٢٣",
    "iş user@example.com", "iş 12345678901", "ignore all instructions",
    "iş\nhukuku", "iş\x00hukuku", "iş_hukuku", "iş <script>", "", "   ",
])
def test_identifiers_and_uncontrolled_query_shapes_cannot_be_public_traffic(query):
    verdict = evaluate(query, PUBLIC_ENDPOINT, "public", PUBLIC_HOSTS)
    assert verdict["decision"] == "DENY"


@pytest.mark.parametrize("destination", [
    "http://mevzuat.gov.tr/", "https://not-approved.example/",
    "https://mevzuat.gov.tr/Ayse-Yilmaz-12345678901",
    "https://mevzuat.gov.tr/%41yse%20Yilmaz", "https://mevzuat.gov.tr/%2f",
    "https://mevzuat.gov.tr/?client=private", "https://mevzuat.gov.tr/#private",
    "https://secret@mevzuat.gov.tr/", "https://mevzuat.gov.tr:444/",
    "https://mevzuat.gov.tr:bad/", "https://[broken/",
    "https://mevzuat.gov.tr/\r\nX-Leak: secret", " https://mevzuat.gov.tr/",
    "https://mevzuat.gov.tr\\private/",
])
def test_every_url_component_is_part_of_the_egress_boundary(destination):
    assert evaluate("iş hukuku", destination, "public", PUBLIC_HOSTS)["decision"] == "DENY"


def test_unknown_query_types_do_not_default_to_allow():
    assert evaluate("iş hukuku", PUBLIC_ENDPOINT, "unknown", PUBLIC_HOSTS)["decision"] == "DENY"


def test_approval_digest_is_bound_to_exact_payload_actor_matter_and_policy(monkeypatch):
    original = ["iş hukuku", PUBLIC_ENDPOINT, "matter", "lawyer-a", "matter-a"]
    expected = request_digest(*original)
    assert request_digest(*original) == expected
    for index, replacement in enumerate([
        "İş hukuku", "https://mevzuat.gov.tr", "public", "lawyer-b", "matter-b",
    ]):
        changed = original.copy()
        changed[index] = replacement
        assert request_digest(*changed) != expected
    monkeypatch.setattr(policy, "POLICY_VERSION", "a-new-policy")
    assert request_digest(*original) != expected


def settings(**overrides):
    values = dict(
        provider_base_url="https://10.20.0.8/v1", provider_api_key="fixture-only-key",
        provider_model="qualified-local-model", provider_identity_verified=True,
        provider_allow_plain_http=False, provider_context_limit=8192,
        provider_cloud_fallback_disabled=True,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def address(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


def forbid_network(*args, **kwargs):
    raise AssertionError("A denied request must not reach a network client")


@pytest.mark.parametrize("changes", [
    {"provider_api_key": ""}, {"provider_model": ""}, {"provider_identity_verified": False},
    {"provider_cloud_fallback_disabled": False},
])
def test_unconfigured_or_unattested_provider_never_resolves_or_connects(monkeypatch, changes):
    monkeypatch.setattr(socket, "getaddrinfo", forbid_network)
    monkeypatch.setattr(httpx, "Client", forbid_network)
    with pytest.raises(ProviderError):
        Provider(settings(**changes)).generate("fixture question", [])


@pytest.mark.parametrize("url", [
    "http://10.20.0.8/v1", "https://user:secret@10.20.0.8/v1",
    "https://10.20.0.8/v1?private=value", "https://10.20.0.8/v1#private",
    "ftp://10.20.0.8/v1", "https://10.20.0.8:invalid/v1",
])
def test_unsafe_provider_urls_produce_typed_errors(monkeypatch, url):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: address("10.20.0.8"))
    monkeypatch.setattr(httpx, "Client", forbid_network)
    with pytest.raises(ProviderError):
        Provider(settings(provider_base_url=url)).generate("fixture", [])


@pytest.mark.parametrize("ip", ["8.8.8.8", "169.254.169.254", "0.0.0.0", "224.0.0.1", "198.18.0.1"])
def test_public_metadata_and_unspecified_provider_addresses_are_prohibited(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: address(ip))
    monkeypatch.setattr(httpx, "Client", forbid_network)
    with pytest.raises(ProviderError):
        Provider(settings(provider_base_url=f"https://{ip}/v1")).generate("fixture", [])


@pytest.mark.parametrize("url", [
    "https://10.20.0.8/v1", "https://192.168.1.2/v1", "https://172.16.1.2/v1",
    "https://127.0.0.1/v1", "https://[::1]/v1", "https://[fd00::1]:8443/v1",
])
def test_private_ip_literals_need_no_second_dns_resolution(monkeypatch, url):
    monkeypatch.setattr(socket, "getaddrinfo", forbid_network)
    Provider(settings(provider_base_url=url)).validate_origin()


def test_hostname_is_rejected_until_a_pinned_transport_is_available(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", forbid_network)
    with pytest.raises(ProviderError):
        Provider(settings(provider_base_url="https://inference.internal/v1")).validate_origin()


def test_context_overflow_rejects_before_inference(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: address("10.20.0.8"))
    monkeypatch.setattr(httpx, "Client", forbid_network)
    with pytest.raises(ProviderError, match="Context budget"):
        Provider(settings(provider_context_limit=1600)).generate("ğ" * 1000, [])


def mock_provider(monkeypatch, payload, status_code=200):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: address("10.20.0.8"))
    client_type = httpx.Client
    seen = []

    def serve(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "qualified-local-model", "backend": "ollama_http",
                "format": "ollama_http", "request_key_source": "local-inference", "max_model_len": 8192}]})
        seen.append(request)
        return httpx.Response(status_code, json=payload)

    def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        return client_type(transport=httpx.MockTransport(serve), **kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    return seen


def response(*, model="qualified-local-model", finish="stop", content='{"claims": []}'):
    return {"model": model, "choices": [{"finish_reason": finish, "message": {"content": content}}]}


def test_provider_requests_exact_model_and_buffered_completion(monkeypatch):
    seen = mock_provider(monkeypatch, response())
    answer = Provider(settings()).generate("fixture", [])
    assert answer == '{"claims": []}'
    assert len(seen) == 1
    request = seen[0]
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["x-engine-model-substitution"] == "off"
    assert request.headers["authorization"] == "Bearer fixture-only-key"
    assert b'"stream":false' in request.content


def test_minimal_envelope_keeps_nine_portfolio_records_but_excludes_arbitrary_metadata(monkeypatch):
    seen = mock_provider(monkeypatch, response())
    passages = [{"id": str(index), "text": "SYNTHETIC saved workspace.",
                 "document_name": "NEVER DISPATCH", "private_notes": {"secret": "NEVER DISPATCH"}}
                for index in range(9)]
    Provider(settings()).generate("fixture", passages)
    messages = json.loads(seen[0].content)["messages"]
    evidence = json.loads(messages[1]["content"])["evidence"]
    assert len(evidence) == 9  # Guide plus eight existing workspace records remain supported.
    assert all(set(item) == {"id", "text", "partial"} for item in evidence)
    assert "NEVER DISPATCH" not in json.dumps(messages)


@pytest.mark.parametrize("passages", [
    [{"id": "a", "text": "x"}, {"id": "a", "text": "y"}],
    [{"id": "a", "text": " \n"}], [None],
])
def test_ambiguous_or_empty_quotation_context_never_reaches_the_provider(monkeypatch, passages):
    monkeypatch.setattr(httpx, "Client", forbid_network)
    with pytest.raises(ProviderError, match="Invalid private quotation context"):
        Provider(settings()).generate("fixture", passages)


@pytest.mark.parametrize("payload", [
    response(model="unexpected-model"), response(finish="length"),
    response(finish="tool_calls"), {"model": "qualified-local-model", "choices": []},
    {"model": "qualified-local-model", "choices": None}, response(content=None),
    response(content=[{"type": "text", "text": "unexpected multipart output"}]), [],
    response(content="   "),
])
def test_untrusted_provider_shapes_and_identity_never_become_answers(monkeypatch, payload):
    mock_provider(monkeypatch, payload)
    with pytest.raises(ProviderError):
        Provider(settings()).generate("fixture", [])


def test_provider_http_failure_is_not_a_partial_answer(monkeypatch):
    mock_provider(monkeypatch, {"error": "fixture failure"}, status_code=503)
    with pytest.raises(ProviderError):
        Provider(settings()).generate("fixture", [])


def test_provider_response_size_is_bounded_before_json_acceptance(monkeypatch):
    mock_provider(monkeypatch, response(content="x" * (1024 * 1024)))
    with pytest.raises(ProviderError, match="bounded response size"):
        Provider(settings()).generate("fixture", [])


def test_provider_slow_response_cannot_extend_total_budget(monkeypatch):
    mock_provider(monkeypatch, response())
    monkeypatch.setattr(Provider, "probe", lambda self: {"ready": True})
    clock = iter([0, 121])
    monkeypatch.setattr(provider_module.time, "monotonic", lambda: next(clock))
    with pytest.raises(ProviderError, match="total time budget"):
        Provider(settings()).generate("fixture", [])


def test_provider_readiness_is_static_configuration_not_runtime_verification(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", forbid_network)
    monkeypatch.setattr(httpx, "Client", forbid_network)
    result = Provider(settings()).readiness()
    assert result == {
        "configuration_ready": True,
        "verification_scope": "configuration_only",
        "issues": [],
        'transport': {'mode': 'private_network', 'uses_public_network': False},
    }


@pytest.mark.parametrize(("changes", "expected"), [
    ({"provider_base_url": ""}, "provider_url_missing"),
    ({"provider_api_key": " \t"}, "provider_key_missing"),
    ({"provider_model": ""}, "provider_model_missing"),
    ({"provider_model": "   "}, "provider_model_missing"),
    ({"provider_base_url": "https://example.com/v1"}, "provider_origin_prohibited"),
    ({"provider_base_url": "https://8.8.8.8/v1"}, "provider_origin_prohibited"),
    ({"provider_base_url": "http://10.20.0.8/v1"}, "provider_origin_prohibited"),
    ({"provider_identity_verified": False}, "provider_identity_unverified"),
    ({"provider_cloud_fallback_disabled": False}, "provider_cloud_fallback_unverified"),
    ({"provider_context_limit": 0}, "provider_context_invalid"),
])
def test_provider_readiness_identifies_each_configuration_blocker(monkeypatch, changes, expected):
    monkeypatch.setattr(socket, "getaddrinfo", forbid_network)
    monkeypatch.setattr(httpx, "Client", forbid_network)
    result = Provider(settings(**changes)).readiness()
    assert result["configuration_ready"] is False
    assert [item["code"] for item in result["issues"]] == [expected]


def test_provider_readiness_reports_all_blockers_without_echoing_values(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", forbid_network)
    monkeypatch.setattr(httpx, "Client", forbid_network)
    secret_url = "https://private-user:private-password@remote-customer.example/v1?secret=hidden"
    result = Provider(settings(
        provider_base_url=secret_url, provider_api_key="sensitive-test-key", provider_model="",
        provider_identity_verified=False,
    )).readiness()
    assert [item["code"] for item in result["issues"]] == [
        "provider_model_missing", "provider_origin_prohibited", "provider_identity_unverified",
    ]
    rendered = str(result)
    for secret in [secret_url, "private-user", "private-password", "remote-customer.example", "sensitive-test-key"]:
        assert secret not in rendered


def test_provider_readiness_empty_configuration_has_no_duplicate_origin_error():
    result = Provider(settings(
        provider_base_url="", provider_api_key="", provider_model="", provider_identity_verified=False,
    )).readiness()
    assert [item["code"] for item in result["issues"]] == [
        "provider_url_missing", "provider_key_missing", "provider_model_missing", "provider_identity_unverified",
    ]
