"""Fake sockets and TLS; no network, private context or persisted credentials."""
import importlib.util
import io
import json
import socket
import ssl
from pathlib import Path
from types import SimpleNamespace

from metadata_phase_probe import RELAY_BASE, probe

SENTINEL = "SYNTHETIC-PRIVATE-CONTENT-MUST-NOT-ESCAPE"
spec = importlib.util.spec_from_file_location("phase_fixture_relay", Path(__file__).resolve().parents[1] / "deploy/provider/relay.py")
RELAY = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RELAY)


class Fixture:
    def __init__(self, mode="ok"):
        self.mode, self.now, self.operations, self.sent, self.closed, self.timeouts = mode, 1000, [], [], 0, []
        self.environ = {"PROVIDER_TUNNEL_APPROVED": "true", "PROVIDER_TUNNEL_APPROVED_HOST": "synthetic.example",
                        "PROVIDER_TUNNEL_URL": "https://synthetic.example/v1", "PROVIDER_TUNNEL_IP": "8.8.4.4"}
        target = RELAY.configured_upstream(self.environ)
        self.binding = {"api_key": "SYNTHETIC-ONLY-KEY", "model_id": "SYNTHETIC-NO-INFERENCE", "app_context": 8192,
                        "relay_base": RELAY_BASE, "transport_mode": "approved_laptop_tunnel",
                        "approved_hostname": target.hostname, "route_sha256": target.route_sha256}
        self.context = self.Context(self)

    def expire(self, stage):
        self.operations.append(stage)
        if self.mode == stage + "_timeout":
            self.now += 4
            raise socket.timeout(SENTINEL)

    class Context:
        check_hostname = True
        verify_mode = ssl.CERT_REQUIRED

        def __init__(self, owner):
            self.owner = owner

        def wrap_socket(self, raw, server_hostname):
            self.owner.expire("tls")
            self.owner.server_hostname = server_hostname
            if self.owner.mode == "tls_error":
                raise ssl.SSLError(SENTINEL)
            return raw

    class File(io.BytesIO):
        def __init__(self, owner, sock, data):
            super().__init__(data)
            self.owner, self.raw = owner, SimpleNamespace(_sock=sock)

        def readline(self, *args):
            self.owner.expire("headers")
            return super().readline(*args)

        def read1(self, *args):
            self.owner.expire("body")
            return super().read1(*args)

    class Socket:
        def __init__(self, owner):
            self.owner = owner

        def settimeout(self, value):
            self.owner.timeouts.append(value)

        def connect(self, address):
            self.owner.expire("tcp")
            self.owner.address = address

        def sendall(self, data):
            self.owner.expire("send")
            self.owner.sent.append(data)

        def makefile(self, mode):
            model = {"id": self.owner.binding["model_id"], "backend": "ollama_http", "format": "ollama_http",
                     "request_key_source": "local-inference", "max_model_len": 32768}
            body = json.dumps({"data": [model]}).encode()
            if self.owner.mode == "nonfinite":
                body = b'{"data":[],"n":1e999}'
            if self.owner.mode == "oversized":
                body = b"x" * (1024 * 1024 + 1)
            if self.owner.mode == "invalid_json":
                body = SENTINEL.encode()
            status = b"302 Found" if self.owner.mode == "redirect" else b"200 OK"
            headers = b"Content-Encoding: custom\r\n" if self.owner.mode == "encoded" else b""
            wire = b"HTTP/1.1 " + status + b"\r\nConnection: close\r\nContent-Length: " + str(len(body)).encode() + b"\r\n" + headers + b"\r\n" + body
            return Fixture.File(self.owner, self, wire)

        def close(self):
            self.owner.closed += 1

    def socket(self, family, kind):
        self.operations.append("socket_created")
        if family != socket.AF_INET or kind != socket.SOCK_STREAM:
            raise AssertionError("Unexpected socket type")
        return self.Socket(self)

    def run(self):
        return probe(self.binding, RELAY, self.environ, socket_factory=self.socket,
                     context_factory=lambda: self.context, clock=lambda: self.now)
