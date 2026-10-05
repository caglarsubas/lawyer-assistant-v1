"""Synthetic relay boundary tests; never contact a tunnel or use operator keys."""
import hashlib
import importlib.util
import json
import socket
import ssl
import subprocess
import threading
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location("provider_tunnel_relay", ROOT / "deploy/provider/relay.py")
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)
HOST = "fixture.example.com"
PIN = "1.1.1.1"


def env(**changes):
    result = {"PROVIDER_TUNNEL_URL": f"https://{HOST}/v1", "PROVIDER_TUNNEL_APPROVED": "true",
              "PROVIDER_TUNNEL_APPROVED_HOST": HOST}
    result.update(changes)
    return result


def answers(*values):
    return [(socket.AF_INET6 if ":" in value else socket.AF_INET, socket.SOCK_STREAM, 6, "",
             (value, 443)) for value in values]


@pytest.mark.parametrize("url", [
    f"http://{HOST}/v1", f"HTTPS://{HOST}/v1", f"https://{HOST}/v1/", f"https://{HOST}/v1.", f"https://{HOST}/v1?",
    f"https://{HOST}/v1#", f"https://{HOST}/v1?x=1", f"https://{HOST}/v1#x", f"https://{HOST}:444/v1",
    f"https://{HOST}:0443/v1", f"https://{HOST}:/v1", f"https://{HOST}./v1", f"https://{HOST}/v%31",
    f"https://{HOST}/x/../v1", f"https://{HOST}//v1", f"https://{HOST}\\@other.example/v1",
    f"https://user:secret@{HOST}/v1", f"https://{HOST.upper()}/v1", f" https://{HOST}/v1",
    f"https://{HOST}/v1\n", "https://127.0.0.1/v1", "https://[2606:4700:4700::1111]/v1",
    "https://local/v1", "https://a_b.example/v1", "https://*.example.com/v1", "https://é.example/v1",
])
def test_tunnel_url_is_exact_and_canonical(url):
    with pytest.raises(ValueError):
        relay.tunnel_hostname(env(PROVIDER_TUNNEL_URL=url))


@pytest.mark.parametrize("changes", [
    {"PROVIDER_TUNNEL_APPROVED": "false"}, {"PROVIDER_TUNNEL_APPROVED": "True"},
    {"PROVIDER_TUNNEL_APPROVED": "1"}, {"PROVIDER_TUNNEL_APPROVED": ""},
    {"PROVIDER_TUNNEL_APPROVED_HOST": ""}, {"PROVIDER_TUNNEL_APPROVED_HOST": "other.example.com"},
    {"PROVIDER_TUNNEL_APPROVED_HOST": HOST.upper()}, {"PROVIDER_TUNNEL_URL": ""},
])
def test_explicit_host_approval_required_before_dns(monkeypatch, changes):
    monkeypatch.setattr(relay.socket, "getaddrinfo", lambda *args: pytest.fail("DNS before approval"))
    with pytest.raises(ValueError):
        relay.resolve_upstream(env(**changes))


def test_canonical_fingerprint_and_native_metadata():
    assert relay.tunnel_hostname(env(PROVIDER_TUNNEL_URL=f"https://{HOST}:443/v1")) == HOST
    digest = hashlib.sha256(("lawyer-assistant:provider-tunnel:v1\0https://" + HOST + "/v1").encode()).hexdigest()
    assert relay.Upstream(PIN, HOST).metadata == {
        "mode": "approved_laptop_tunnel", "upstream_origin": f"https://{HOST}", "route_sha256": digest,
    }
    assert relay.tunnel_hostname({}) is None
    assert relay.tunnel_hostname({"PROVIDER_TUNNEL_APPROVED": "false", "PROVIDER_TUNNEL_URL": "",
                                  "PROVIDER_TUNNEL_APPROVED_HOST": ""}) is None
    assert relay.Upstream("192.168.1.2").metadata == {"mode": "native_private", "upstream_origin": None}


@pytest.mark.parametrize("values", [
    ("127.0.0.1",), ("169.254.169.254",), ("10.1.2.3",), ("172.16.1.2",), ("192.168.1.2",),
    ("0.0.0.0",), ("100.64.0.1",), ("224.0.0.1",), ("192.0.2.1",), ("240.0.0.1",),
    (PIN, "127.0.0.1"), (PIN, "::1"), (PIN, "fe80::1"), (PIN, "::ffff:1.1.1.1"),
    ("2606:4700:4700::1111",), (),
])
def test_any_nonpublic_dns_answer_or_ipv6_only_is_rejected(monkeypatch, values):
    monkeypatch.setattr(relay.socket, "getaddrinfo", lambda *args: answers(*values))
    with pytest.raises(ValueError):
        relay.resolve_upstream(env())


def test_resolves_once_and_serving_config_uses_public_ipv4_pin(monkeypatch):
    calls = []

    def resolve(*args):
        calls.append(args)
        return answers("8.8.8.8", "2606:4700:4700::1111", PIN)

    monkeypatch.setattr(relay.socket, "getaddrinfo", resolve)
    target = relay.resolve_upstream(env())
    assert target == relay.Upstream(PIN, HOST)
    assert calls == [(HOST, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)]
    monkeypatch.setattr(relay.socket, "getaddrinfo", lambda *args: pytest.fail("Serving must not resolve DNS"))
    assert relay.configured_upstream(env(PROVIDER_TUNNEL_IP=PIN)) == target


def test_native_keeps_private_only_endpoint(monkeypatch):
    monkeypatch.setattr(relay.socket, "getaddrinfo", lambda *args: answers("192.168.65.254"))
    assert relay.resolve_upstream({}) == relay.Upstream("192.168.65.254")
    assert relay.configured_upstream({"PROVIDER_NATIVE_IP": "10.1.2.3"}) == relay.Upstream("10.1.2.3")
    with pytest.raises(ValueError):
        relay.resolve_upstream({"PROVIDER_NATIVE_HOST": PIN})
    with pytest.raises(ValueError):
        relay.configured_upstream(env(PROVIDER_TUNNEL_IP="127.0.0.1"))


@pytest.mark.parametrize("certificate_error", [False, True])
def test_tls_connects_pinned_ip_with_original_sni_and_host_without_dns(monkeypatch, certificate_error):
    calls = []
    sent = []

    class Raw:
        def settimeout(self, timeout):
            calls.append(("timeout", timeout))

        def connect(self, endpoint):
            calls.append(("connect", endpoint))

        def close(self):
            calls.append(("close",))

        def sendall(self, data):
            sent.append(bytes(data))

    raw = Raw()

    class Context:
        check_hostname = True
        verify_mode = ssl.CERT_REQUIRED

        def wrap_socket(self, sock, server_hostname):
            calls.append(("tls", sock is raw, server_hostname))
            if certificate_error:
                raise ssl.SSLCertVerificationError("fixture untrusted certificate")
            return raw

    monkeypatch.setattr(relay.socket, "socket", lambda family, kind: raw)
    monkeypatch.setattr(relay.socket, "getaddrinfo", lambda *args: pytest.fail("No serving DNS"))
    monkeypatch.setattr(relay.ssl, "create_default_context", Context)
    connection = relay.PinnedHTTPSConnection(relay.Upstream(PIN, HOST), 5)
    if certificate_error:
        with pytest.raises(ssl.SSLCertVerificationError):
            connection.request("GET", "/v1/models", headers={"Authorization": "Bearer fixture-only"})
        assert not sent
        assert calls[-1] == ("close",)
    else:
        connection.request("GET", "/v1/models", headers={"Authorization": "Bearer fixture-only"})
        assert f"Host: {HOST}\r\n".encode() in b"".join(sent)
        assert PIN.encode() not in b"".join(sent)
    assert calls[:3] == [("timeout", 5), ("connect", (PIN, 443)), ("tls", True, HOST)]


def completion():
    return {"model": "local-model", "messages": [{"role": "user", "content": "synthetic fixture"}],
            "stream": False, "max_completion_tokens": 50, "temperature": 0,
            "response_format": {"type": "json_object"}}


@pytest.fixture
def running_relay(request):
    upstream = relay.Upstream(PIN, HOST) if getattr(request, "param", "tunnel") == "tunnel" else "10.1.2.3"
    server = relay.Server(("127.0.0.1", 0), upstream, "local-model")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False) as client:
            yield client
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def headers():
    return {"Authorization": "Bearer fixture-only", "X-Provider-Route": relay.Upstream(PIN, HOST).route_sha256}


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("routes", [[], [("X-Provider-Route", "0" * 64)],
                                      [("X-Provider-Route", "é")],
                                      [("X-Provider-Route", relay.Upstream(PIN, HOST).route_sha256)] * 2])
def test_route_mismatch_blocks_before_credentials_or_body_can_leave(monkeypatch, running_relay, method, routes):
    monkeypatch.setattr(relay, "PinnedHTTPSConnection", lambda *args: pytest.fail("No upstream connection"))
    path = "/v1/models" if method == "GET" else "/v1/chat/completions"
    request_headers = [(b"Authorization", b"Bearer fixture-only")] + [
        (name.encode(), value.encode("latin1")) for name, value in routes]
    kwargs = {"json": completion()} if method == "POST" else {}
    response = running_relay.request(method, path, headers=request_headers, **kwargs)
    assert response.status_code == 409
    assert "fixture-only" not in response.text


@pytest.mark.parametrize("running_relay", ["native"], indirect=True)
def test_native_rejects_tunnel_route_before_forwarding(monkeypatch, running_relay):
    monkeypatch.setattr(relay.http.client, "HTTPConnection", lambda *args, **kwargs: pytest.fail("Route mismatch"))
    assert running_relay.get("/v1/models", headers=headers()).status_code == 409


def mock_upstream(monkeypatch, status=200, payload=None):
    calls = []

    class Response:
        sent = False

        def getheader(self, name, default=None):
            return "https://unapproved.example/v1/models" if name == "Location" else default

        def read1(self, size):
            if self.sent:
                return b""
            self.sent = True
            return json.dumps(payload).encode()

    Response.status = status

    class Connection:
        def __init__(self, upstream, timeout):
            calls.append({"upstream": upstream, "timeout": timeout})

        def request(self, method, path, body, headers):
            calls[-1].update(method=method, path=path, body=body, headers=headers)

        def getresponse(self):
            return Response()

        def close(self):
            calls[-1]["closed"] = True

    monkeypatch.setattr(relay, "PinnedHTTPSConnection", Connection)
    return calls


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_exact_tunnel_paths_fixed_headers_and_relay_generated_transport(monkeypatch, running_relay, method):
    payload = ({"object": "list", "data": [{"id": "local-model", "backend": "ollama_http", "format": "ollama_http",
                                           "request_key_source": "local-inference"}]} if method == "GET" else
               {"model": "local-model", "choices": []})
    payload["relay_transport"] = {"mode": "forged-upstream-metadata"}
    calls = mock_upstream(monkeypatch, payload=payload)
    path = "/v1/models" if method == "GET" else "/v1/chat/completions"
    extra = {"json": completion()} if method == "POST" else {}
    response = running_relay.request(method, path, headers={**headers(), "Host": "outside.example",
                                    "Cookie": "private=unrelated", "X-Forwarded-Host": "outside.example"}, **extra)
    assert response.status_code == 200
    assert response.json()["relay_transport"] == relay.Upstream(PIN, HOST).metadata
    assert len(calls) == 1 and calls[0]["upstream"] == relay.Upstream(PIN, HOST)
    assert calls[0]["method"] == method and calls[0]["path"] == path and calls[0]["closed"]
    assert calls[0]["headers"] == {
        "Authorization": "Bearer fixture-only", "Content-Type": "application/json", "Accept-Encoding": "identity",
        "x-engine-model-substitution": "off", "Connection": "close",
    }


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirects_are_not_followed(monkeypatch, running_relay, status):
    calls = mock_upstream(monkeypatch, status=status)
    response = running_relay.get("/v1/models", headers=headers())
    assert response.status_code == 502 and len(calls) == 1 and calls[0]["closed"]
    assert "unapproved" not in response.text


@pytest.mark.parametrize("path", ["/v1/admin/auth-keys", "/v1/models?x=1", "/v1/models/", "/v1/chat/completions/",
                                 "/v1/../admin", "/v1/%6dodels", "/health?tls=check"])
def test_tunnel_does_not_expand_allowed_routes(monkeypatch, running_relay, path):
    monkeypatch.setattr(relay, "PinnedHTTPSConnection", lambda *args: pytest.fail("Unexpected forwarding"))
    assert running_relay.get(path, headers=headers()).status_code == 404
    assert running_relay.post(path, json=completion(), headers=headers()).status_code == 404


def test_entrypoint_firewall_pins_one_ip_and_port_without_shell_evaluation(tmp_path):
    log = tmp_path / "commands"
    for name in ("iptables", "ip6tables", "gosu"):
        command = tmp_path / name
        command.write_text(f"#!/bin/sh\nprintf '%s\\n' '{name}' \"$*\" >> '{log}'\n")
        command.chmod(0o755)
    python = tmp_path / "python"
    python.write_text("#!/bin/sh\ntest \"$*\" = '/app/relay.py --resolve' || exit 1\nprintf '1.1.1.1 443\\n'\n")
    python.chmod(0o755)
    subprocess.run(["/bin/sh", str(ROOT / "deploy/provider/entrypoint.sh")],
                   env={"PATH": str(tmp_path)}, check=True, capture_output=True, timeout=10)
    output = log.read_text()
    assert "-A OUTPUT -d 1.1.1.1 -p tcp --dport 443 -j ACCEPT" in output
    assert "-A INPUT -s 1.1.1.1 -p tcp --sport 443 -m conntrack --ctstate ESTABLISHED -j ACCEPT" in output
    assert "--dport 8080" not in output and "--dport 53" not in output
    assert "ip6tables\n-P OUTPUT DROP" in output
    assert output.index("-D OUTPUT -o lo -j ACCEPT") < output.index("gosu")
    assert "relay:relay python /app/relay.py" in output
