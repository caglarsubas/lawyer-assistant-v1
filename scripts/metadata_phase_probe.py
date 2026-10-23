"""Disposable one-connection metadata probe; stdlib only, no serving-process changes."""

import http.client
import json
import math
import re
import socket
import ssl
import time

RECIPE = "readonly-metadata-phase-probe-v1"
RELAY_BASE = "http://172.30.240.2:8083/v1"
MAX_BYTES = 1024 * 1024
FIELDS = {"api_key", "model_id", "app_context", "relay_base", "transport_mode", "approved_hostname", "route_sha256"}


class Rejected(ValueError):
    pass


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Rejected("invalid_metadata")
            result[key] = value
        return result
    payload = json.loads(raw, object_pairs_hook=unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(Rejected("invalid_metadata")))
    pending = [payload]
    while pending:
        value = pending.pop()
        if isinstance(value, float) and not math.isfinite(value):
            raise Rejected("invalid_metadata")
        if isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return payload


def binding_target(binding, relay, environ):
    # This is a private operator context, not an agent tool or permission grant.
    if not isinstance(binding, dict) or set(binding) != FIELDS or binding["relay_base"] != RELAY_BASE:
        raise Rejected("configuration_rejected")
    key, model = binding["api_key"], binding["model_id"]
    if (not isinstance(key, str) or not 8 <= len(key) <= 4096 or any(not 33 <= ord(c) <= 126 for c in key)
            or not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", model)
            or type(binding["app_context"]) is not int or not 0 < binding["app_context"] <= 8192):
        raise Rejected("configuration_rejected")
    target = relay.configured_upstream(environ)
    if target.hostname:
        if (binding["transport_mode"] != "approved_laptop_tunnel" or binding["approved_hostname"] != target.hostname
                or binding["route_sha256"] != target.route_sha256):
            raise Rejected("route_rejected")
    elif (binding["transport_mode"] != "native_private" or binding["approved_hostname"] is not None or binding["route_sha256"] is not None):
        raise Rejected("route_rejected")
    return target


def probe(binding, relay, environ, *, socket_factory=socket.socket, context_factory=ssl.create_default_context, clock=time.monotonic):
    """No DNS/retry/redirect/POST. A separate observation, never serving-request proof.

    The operator must verify the deployed relay source and run as its existing
    unprivileged UID within its unchanged firewall. No raw result is returned.
    """
    result = {"recipe": RECIPE, "last_phase": "configuration", "outcome": "rejected", "error": None,
              "completed_phases": [], "connection_attempts": 0, "metadata_GET_attempts": 0,
              "completion_POST_requests": 0, "http_status": None, "tls_required": None, "tls_verified": False,
              "metadata_accepted": False, "budget_seconds": 4, "deadline_reached": False,
              "cleanup_complete": True,
              "qualified_identity": False, "native_execution_authorization": False, "production_activation": False}
    deadline, connection, response = clock() + 4, None, None

    def remaining():
        value = deadline - clock()
        if value <= 0:
            raise socket.timeout()
        return value

    def budget(response=None):
        value = remaining()
        sock = getattr(connection, "sock", None)
        if sock is None and response is not None:
            sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
        if sock is None:
            raise Rejected("response_socket_unavailable")
        sock.settimeout(value)

    def enter(phase):
        result["last_phase"] = phase
        remaining()

    def done(phase):
        remaining()
        result["completed_phases"].append(phase)

    try:
        target = binding_target(binding, relay, environ)
        tls = bool(target.hostname)
        result["tls_required"] = tls
        context = context_factory() if tls else None
        if tls and (not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED):
            raise Rejected("tls_policy_rejected")

        class Connection(http.client.HTTPConnection):
            default_port = 443 if tls else 80

            def connect(self):
                if result["connection_attempts"] or self._tunnel_host:
                    raise Rejected("connection_replay_rejected")
                enter("tcp_connect")
                result["connection_attempts"] = 1
                raw = socket_factory(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    raw.settimeout(remaining())
                    raw.connect((target.address, target.port))
                    done("tcp_connect")
                    if tls:
                        enter("tls_handshake")
                        raw.settimeout(remaining())
                        self.sock = context.wrap_socket(raw, server_hostname=target.hostname)
                        done("tls_handshake")
                        result["tls_verified"] = True
                    else:
                        self.sock = raw
                except BaseException:
                    raw.close()
                    raise

            def send(self, data):
                # HTTPConnection must never silently reconnect after a partial request.
                if self.sock is None:
                    raise Rejected("connection_replay_rejected")
                budget()
                super().send(data)

        connection = Connection(target.hostname or target.address, target.port, timeout=remaining())
        connection.connect()
        enter("request_send")
        result["metadata_GET_attempts"] = 1
        connection.request("GET", "/v1/models", body=None, headers={
            "Authorization": "Bearer " + binding["api_key"], "Content-Type": "application/json",
            "Accept-Encoding": "identity", "x-engine-model-substitution": "off", "Connection": "close"})
        done("request_send")
        enter("response_headers")
        budget()
        response = connection.getresponse()
        status = response.status
        if type(status) is not int or not 100 <= status <= 599:
            raise Rejected("invalid_http_status")
        result["http_status"] = status
        done("response_headers")
        if status != 200:
            raise Rejected("http_status_rejected")
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise Rejected("encoding_rejected")
        enter("response_body")
        raw = bytearray()
        while True:
            if response.isclosed():
                if response.length not in (None, 0):
                    raise Rejected("incomplete_body")
                break
            budget(response)
            chunk = response.read1(65536)
            remaining()
            if len(raw) + len(chunk) > MAX_BYTES:
                raise Rejected("body_budget_exceeded")
            raw.extend(chunk)
            if not chunk:
                if response.length not in (None, 0):
                    raise Rejected("incomplete_body")
                break
        done("response_body")
        enter("metadata_validation")
        payload = strict_json(bytes(raw))
        inventory = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(inventory, list) or len(inventory) > 4096:
            raise Rejected("invalid_metadata")
        selected = [m for m in inventory if isinstance(m, dict) and m.get("id") == binding["model_id"]]
        if len(selected) != 1:
            raise Rejected("model_unresolved")
        model = selected[0]
        if (model.get("request_key_source") != "local-inference"
                or model.get("backend") not in {"ollama_http", "mlx", "llama_cpp"}
                or model.get("format") != {"ollama_http": "ollama_http", "mlx": "mlx", "llama_cpp": "gguf"}.get(model.get("backend"))
                or type(model.get("max_model_len")) is not int or model["max_model_len"] < binding["app_context"]):
            raise Rejected("local_metadata_rejected")
        done("metadata_validation")
        result.update(outcome="metadata_accepted_identity_unqualified", metadata_accepted=True)
    except socket.timeout:
        result.update(outcome="timeout", error="socket_timeout")
    except ssl.SSLError:
        result["error"] = "tls_error"
    except OSError as exc:
        result["error"] = relay.transport_failure(exc)
    except http.client.HTTPException:
        result["error"] = "http_protocol_error"
    except Rejected as exc:
        allowed = {"configuration_rejected", "route_rejected", "tls_policy_rejected", "connection_replay_rejected",
                   "response_socket_unavailable", "invalid_http_status", "http_status_rejected", "encoding_rejected",
                   "body_budget_exceeded", "incomplete_body", "invalid_metadata", "model_unresolved", "local_metadata_rejected"}
        result["error"] = str(exc) if str(exc) in allowed else "unclassified_rejection"
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        result["error"] = "invalid_input_or_metadata"
    except Exception:  # noqa: BLE001 - final diagnostic boundary must never expose arbitrary error text
        result["error"] = "unclassified_rejection"
    finally:
        for resource in (response, connection):
            if resource is not None:
                try:
                    resource.close()
                except Exception:  # noqa: BLE001 - cleanup errors must not expose transport details
                    result.update(cleanup_complete=False, metadata_accepted=False, outcome="rejected")
                    if result["error"] is None:
                        result["error"] = "cleanup_failed"
    result["deadline_reached"] = clock() >= deadline
    return result
