"""Narrow, memory-only relay to the native local inference engine.

No credentials in its environment/files, no access logging, no redirects,
arbitrary URLs, administration routes, or cloud model names. Network policy is
installed independently by entrypoint.sh before this unprivileged process runs.
"""
import errno
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import NamedTuple
from urllib.parse import urlsplit

from app.analysis_output_contract import admitted_response_format

MAX_REQUEST = 256 * 1024
MAX_RESPONSE = 1024 * 1024
MAX_CONNECTIONS = 12  # Five metadata + five completion lifetimes + health headroom.
MAX_UPSTREAM = 2  # Generation backpressure; never changes shared-engine limits.
LOCAL_BACKENDS = {"ollama_http", "llama_cpp", "mlx"}
LOCAL_FORMATS = {"ollama_http", "gguf", "mlx"}
FAILURE_CODES = frozenset({
    "provider_upstream_http_error", "provider_encoding_rejected", "provider_response_budget_exceeded",
    "provider_model_rejected", "provider_response_invalid", "provider_tls_failed",
    "provider_upstream_timeout", "provider_upstream_transport_failed", "provider_http_protocol_failed",
    "provider_connection_closed", "provider_connection_reset", "provider_connection_refused",
    "provider_network_denied", "provider_network_unreachable", "provider_transport_resource_exhausted",
})


def transport_failure(error):
    if isinstance(error, http.client.RemoteDisconnected):
        return "provider_connection_closed"
    return {
        errno.ECONNRESET: "provider_connection_reset", errno.ECONNREFUSED: "provider_connection_refused",
        errno.EACCES: "provider_network_denied", errno.EPERM: "provider_network_denied",
        errno.ENETUNREACH: "provider_network_unreachable", errno.EHOSTUNREACH: "provider_network_unreachable",
        errno.EMFILE: "provider_transport_resource_exhausted", errno.ENFILE: "provider_transport_resource_exhausted",
        errno.ENOMEM: "provider_transport_resource_exhausted", errno.ENOBUFS: "provider_transport_resource_exhausted",
    }.get(error.errno, "provider_upstream_transport_failed")
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
))
TUNNEL_FIELDS = ("PROVIDER_TUNNEL_URL", "PROVIDER_TUNNEL_APPROVED", "PROVIDER_TUNNEL_APPROVED_HOST")


class Upstream(NamedTuple):
    address: str
    hostname: str | None = None

    @property
    def port(self):
        return 443 if self.hostname else 8080

    @property
    def route_sha256(self):
        if self.hostname is None:
            return None
        value = "lawyer-assistant:provider-tunnel:v1\0" + "https://" + self.hostname + "/v1"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @property
    def metadata(self):
        if self.hostname is None:
            return {"mode": "native_private", "upstream_origin": None}
        return {"mode": "approved_laptop_tunnel", "upstream_origin": "https://" + self.hostname,
                "route_sha256": self.route_sha256}


def tunnel_hostname(environ):
    """Validate the explicit single-host exception before any DNS or traffic."""
    values = [environ.get(field, "") for field in TUNNEL_FIELDS]
    url, approved, approved_host = values
    if not url and not approved_host and approved in {"", "false"}:
        return None
    if (not all(isinstance(value, str) and value for value in values) or approved != "true"
            or not url.isascii() or any(char.isspace() or ord(char) < 33 for char in url)
            or any(char in url for char in "\\?#%")):
        raise ValueError("Invalid approved provider tunnel")
    parsed = urlsplit(url)
    host = parsed.hostname
    if (parsed.scheme != "https" or not host or host != approved_host or host != host.lower()
            or len(host) > 253 or len(host.split(".")) < 2
            or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                   for label in host.split("."))
            or parsed.netloc not in {host, host + ":443"} or parsed.path != "/v1"
            or url not in {f"https://{host}/v1", f"https://{host}:443/v1"}
            or parsed.username is not None or parsed.password is not None or parsed.port not in {None, 443}):
        raise ValueError("Invalid approved provider tunnel")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise ValueError("Invalid approved provider tunnel")


def private_address(value):
    address = ipaddress.ip_address(value)
    if address.version != 4 or not any(address in network for network in PRIVATE_NETWORKS):
        raise ValueError("Invalid native provider endpoint")
    return str(address)


def public_address(value):
    address = ipaddress.ip_address(value)
    if (not address.is_global or address.is_multicast or address.is_reserved
            or getattr(address, "ipv4_mapped", None) is not None or "%" in value):
        raise ValueError("Invalid provider tunnel address")
    return address


def resolve_upstream(environ):
    """Bootstrap only: inspect every answer, then select one IPv4 firewall target."""
    hostname = tunnel_hostname(environ)
    if hostname is not None:
        answers = socket.getaddrinfo(hostname, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
        addresses = {public_address(row[4][0]) for row in answers}
        candidates = sorted((address for address in addresses if address.version == 4), key=int)
        if not candidates:
            raise ValueError("Provider tunnel requires a public IPv4 endpoint")
        return Upstream(str(candidates[0]), hostname)
    host = environ.get("PROVIDER_NATIVE_HOST", "host.docker.internal")
    if host == "host.docker.internal":
        addresses = {row[4][0] for row in socket.getaddrinfo(host, 8080, socket.AF_INET, socket.SOCK_STREAM)}
        if len(addresses) != 1:
            raise ValueError("Provider host must resolve to one private IPv4")
        host = addresses.pop()
    return Upstream(private_address(host))


def configured_upstream(environ):
    """Read the bootstrap pin; never resolve DNS in the serving process."""
    hostname = tunnel_hostname(environ)
    if hostname is None:
        return Upstream(private_address(environ["PROVIDER_NATIVE_IP"]))
    address = public_address(environ["PROVIDER_TUNNEL_IP"])
    if address.version != 4:
        raise ValueError("Provider tunnel requires a public IPv4 endpoint")
    return Upstream(str(address), hostname)


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to the bootstrap IP, retaining the approved TLS/HTTP authority."""
    def __init__(self, upstream, timeout):
        self.pinned_address = str(public_address(upstream.address))
        if ipaddress.ip_address(self.pinned_address).version != 4 or not upstream.hostname:
            raise ValueError("Invalid provider tunnel address")
        context = ssl.create_default_context()
        if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError("Provider TLS verification is required")
        super().__init__(upstream.hostname, 443, timeout=timeout, context=context)

    def connect(self):
        if self._tunnel_host:
            raise ValueError("Provider proxy tunnels are prohibited")
        # socket.create_connection also resolves numeric addresses. Use a socket
        # directly so this request cannot trigger DNS or follow a changed answer.
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            raw.settimeout(self.remaining())
            raw.connect((self.pinned_address, 443))
            if getattr(self, "deadline", None) is not None:
                raw.settimeout(self.remaining())
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise

    def remaining(self):
        deadline = getattr(self, "deadline", None)
        if deadline is None:
            return self.timeout
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise socket.timeout()
        return min(self.timeout, remaining)

    def send(self, data):
        if self.sock is None:
            self.connect()
        if getattr(self, "deadline", None) is not None:
            self.sock.settimeout(self.remaining())
        super().send(data)


def valid_completion(payload, model):
    if not isinstance(payload, dict) or not model or payload.get("model") != model:
        return False
    allowed = {"model", "messages", "temperature", "max_completion_tokens", "stream", "response_format"}
    if set(payload) - allowed or payload.get("stream") is not False:
        return False
    tokens = payload.get("max_completion_tokens")
    if type(tokens) is not int or not 1 <= tokens <= 1000:
        return False
    if (payload.get("temperature") != 0 or (payload.get("response_format") != {"type": "json_object"}
                                          and not admitted_response_format(payload.get("response_format")))):
        return False
    messages = payload.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 8:
        return False
    return all(isinstance(message, dict) and set(message) == {"role", "content"}
               and message.get("role") in {"system", "user", "assistant"}
               and isinstance(message.get("content"), str) for message in messages)


def filtered_models(payload, model):
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("invalid model metadata")
    fields = {"id", "backend", "format", "request_key_source", "max_model_len", "context_length"}
    matches = [item for item in payload["data"] if isinstance(item, dict) and item.get("id") == model]
    if len(matches) > 1:
        raise ValueError("ambiguous model metadata")
    return {"object": "list", "data": [
        {key: value for key, value in item.items() if key in fields}
        for item in matches if item.get("backend") in LOCAL_BACKENDS
        and item.get("format") in LOCAL_FORMATS and item.get("request_key_source") == "local-inference"
    ]}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, address, upstream, model):
        self.upstream = upstream if isinstance(upstream, Upstream) else Upstream(private_address(upstream))
        self.model = model
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self.upstream_slots = threading.BoundedSemaphore(MAX_UPSTREAM)
        self.metadata_slots = threading.BoundedSemaphore(2)
        self.metadata_lock = threading.Lock()
        self.metadata_flights = {}
        super().__init__(address, Handler)

    def join_metadata(self, auth):
        # No bearer or matter data is retained. Only overlapping requests with
        # the same credential, route and model share this read-only operation.
        key = hashlib.sha256((auth + "\0" + self.model + "\0" + str(self.upstream.route_sha256)).encode()).digest()
        with self.metadata_lock:
            flight = self.metadata_flights.get(key)
            leader = flight is None
            if leader:
                flight = {"ready": threading.Event(), "result": None}
                self.metadata_flights[key] = flight
            return key, flight, leader

    def publish_metadata(self, key, flight, result):
        with self.metadata_lock:
            if flight["result"] is None:
                flight["result"] = result
                # Remove before waking participants: later requests must probe
                # afresh, even if an earlier client is still receiving its reply.
                if self.metadata_flights.get(key) is flight:
                    del self.metadata_flights[key]
                flight["ready"].set()

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # HTTP library failures must not log requests, authorization or content.
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalProviderRelay"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass

    def send_json(self, status, payload):
        flight = getattr(self, "metadata_flight", None)
        if flight is not None:
            self.server.publish_metadata(self.metadata_key, flight, (status, payload))
        encoded = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)

    def fail(self, status, code=None):
        payload = {"error": "Local provider request could not be admitted"}
        if code in FAILURE_CODES:
            payload["code"] = code
        self.send_json(status, payload)

    def do_GET(self):
        if self.path == "/health":
            return self.send_json(200, {"status": "ok", "scope": "relay_process_only"})
        if self.path != "/v1/models":
            return self.fail(404)
        if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length", "0") != "0":
            return self.fail(400)
        self.forward(None)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            return self.fail(404)
        if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
            return self.fail(400)
        try:
            size = int(self.headers["Content-Length"])
            if size < 1 or size > MAX_REQUEST or self.headers.get_content_type() != "application/json":
                return self.fail(413)
            body = self.rfile.read(size)
            if len(body) != size or not valid_completion(json.loads(body), self.server.model):
                return self.fail(400)
        except (ValueError, TypeError, socket.timeout, RecursionError):
            return self.fail(400)
        self.forward(body)

    def forward(self, body):
        routes = self.headers.get_all("X-Provider-Route", [])
        expected_route = self.server.upstream.route_sha256
        if ((expected_route is None and routes) or (expected_route is not None and (
                len(routes) != 1 or not re.fullmatch(r"[0-9a-f]{64}", routes[0])
                or not hmac.compare_digest(routes[0], expected_route)))):
            return self.fail(409)
        auth = self.headers.get("Authorization", "")
        if (len(self.headers.get_all("Authorization", [])) != 1 or not auth.startswith("Bearer ")
                or not 8 < len(auth) <= 4096 or any(ord(char) < 33 or ord(char) > 126 for char in auth[7:])):
            return self.fail(401)
        connection = None
        acquired = False
        slots = self.server.metadata_slots if body is None else self.server.upstream_slots
        # Leave response-delivery headroom inside the API's existing 5s/90s
        # socket budgets. Queue wait, TLS and body reads share one deadline.
        deadline = time.monotonic() + (4 if body is None else 85)
        if body is None:
            key, flight, leader = self.server.join_metadata(auth)
            if not leader:
                if not flight["ready"].wait(timeout=max(0, deadline - time.monotonic())):
                    return self.fail(503, "provider_upstream_timeout")
                return self.send_json(*flight["result"])
            self.metadata_key, self.metadata_flight = key, flight
        try:
            acquired = slots.acquire(timeout=max(0, deadline - time.monotonic()))
            if not acquired:
                return self.fail(503, "provider_upstream_timeout")
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                return self.fail(503, "provider_upstream_timeout")
            upstream = self.server.upstream
            connection = (PinnedHTTPSConnection(upstream, timeout) if upstream.hostname else
                          http.client.HTTPConnection(upstream.address, 8080, timeout=timeout))
            connection.deadline = deadline
            connection.request(self.command, self.path, body=body, headers={
                "Authorization": auth, "Content-Type": "application/json", "Accept-Encoding": "identity",
                "x-engine-model-substitution": "off", "Connection": "close",
            })
            self.remaining_timeout(connection, deadline)
            response = connection.getresponse()
            if response.status != 200:
                return self.fail(response.status if response.status in {400, 401, 403, 404, 429, 503} else 502,
                                 "provider_upstream_http_error")
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                return self.fail(502, "provider_encoding_rejected")
            payload = bytearray()
            while True:
                self.remaining_timeout(connection, deadline, response)
                chunk = response.read1(65536)
                if len(payload) + len(chunk) > MAX_RESPONSE or time.monotonic() >= deadline:
                    return self.fail(502, "provider_response_budget_exceeded")
                payload.extend(chunk)
                if not chunk:
                    break
            result = json.loads(payload)
            if body is None:
                result = filtered_models(result, self.server.model)
            elif (not isinstance(result, dict) or result.get("model") != self.server.model
                  or result.get("request_key_source", "local-inference") != "local-inference"
                  or any(result.get(key) for key in ("fallback_from_model", "fallback_reason", "substitution_reason"))):
                return self.fail(502, "provider_model_rejected")
            result["relay_transport"] = self.server.upstream.metadata
            return self.send_json(200, result)
        except ssl.SSLError:
            return self.fail(502, "provider_tls_failed")
        except socket.timeout:
            return self.fail(502, "provider_upstream_timeout")
        except OSError as error:
            return self.fail(502, transport_failure(error))
        except http.client.HTTPException:
            return self.fail(502, "provider_http_protocol_failed")
        except (ValueError, TypeError, RecursionError):
            return self.fail(502, "provider_response_invalid")
        finally:
            try:
                if connection is not None:
                    connection.close()
            finally:
                if acquired:
                    slots.release()
                flight = getattr(self, "metadata_flight", None)
                if flight is not None:
                    self.server.publish_metadata(self.metadata_key, flight, (502, {
                        "error": "Local provider request could not be admitted", "code": "provider_upstream_transport_failed"}))

    @staticmethod
    def remaining_timeout(connection, deadline, response=None):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise socket.timeout()
        # HTTPConnection may transfer ownership to a Connection: close response.
        # Its retained file/socket still needs the shrinking absolute deadline.
        sock = getattr(connection, "sock", None)
        if sock is None and response is not None and getattr(response, "fp", None) is not None:
            raw = getattr(response.fp, "raw", None)
            sock = getattr(raw, "_sock", None)
        if sock is not None:
            sock.settimeout(remaining)


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--resolve"]:
            target = resolve_upstream(os.environ)
            # Only validated IPv4/port values; entrypoint never evals this output.
            print(target.address, target.port)
            raise SystemExit(0)
        if sys.argv[1:]:
            raise ValueError("Unsupported relay arguments")
        target = configured_upstream(os.environ)
    except (KeyError, ValueError, OSError):
        raise SystemExit("Invalid provider endpoint")
    Server(("0.0.0.0", 8083), target, os.environ.get("PROVIDER_PINNED_MODEL", "")).serve_forever()
