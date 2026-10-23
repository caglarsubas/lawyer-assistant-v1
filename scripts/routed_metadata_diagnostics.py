"""One approved model-list GET with fixed diagnostics, never inference or identity authority."""

import math
import time
from contextlib import contextmanager

import httpx
from provider_identity_binding import collect_identity, decode

from app.provider import Provider, ProviderError, TunnelConfigurationError

RECIPE = "readonly-routed-metadata-diagnostics-v1"
MAX_ERROR_BYTES = 4096
RELAY_CODES = frozenset({
    "provider_upstream_http_error", "provider_encoding_rejected", "provider_response_budget_exceeded",
    "provider_model_rejected", "provider_response_invalid", "provider_tls_failed",
    "provider_upstream_timeout", "provider_upstream_transport_failed", "provider_http_protocol_failed",
    "provider_connection_closed", "provider_connection_reset", "provider_connection_refused",
    "provider_network_denied", "provider_network_unreachable", "provider_transport_resource_exhausted",
})
COLLECTOR_FAILURES = {
    "Explicit provider and bounded identity challenge required": "configuration_rejected",
    "Provider configuration cannot admit read-only metadata": "configuration_rejected",
    "Provider metadata unavailable or compressed": "metadata_headers_rejected",
    "Provider metadata exceeded bounds": "metadata_budget_exceeded",
    "Provider metadata deadline exceeded": "metadata_budget_exceeded",
    "Read-only provider metadata unavailable": "http_transport_rejected",
    "Invalid bounded provider JSON": "metadata_json_rejected",
    "Unbounded provider identity/response body": "metadata_json_rejected",
    "Provider transport metadata is invalid": "transport_metadata_rejected",
    "The response did not use the approved tunnel route": "transport_metadata_rejected",
    "An unapproved provider transport was rejected": "transport_metadata_rejected",
    "Invalid model metadata inventory": "model_inventory_rejected",
    "Missing or ambiguous configured model": "configured_model_unresolved",
    "Model metadata cannot establish local context capability": "local_model_metadata_rejected",
    "Provider configuration changed during identity collection": "configuration_changed",
}


def http_failure(error):
    for cls, label in ((httpx.ConnectTimeout, "connect_timeout"), (httpx.ReadTimeout, "read_timeout"),
                       (httpx.WriteTimeout, "write_timeout"), (httpx.PoolTimeout, "pool_timeout"),
                       (httpx.ConnectError, "connect_error"), (httpx.ReadError, "read_error"),
                       (httpx.RemoteProtocolError, "remote_protocol_error")):
        if isinstance(error, cls):
            return label
    return "http_error"


class Observation:
    def __init__(self, expected_url, client, clock):
        self.expected_url, self.client, self.clock = expected_url, client, clock
        self.attempts, self.status, self.encoding_rejected, self.transport_error = 0, None, False, None
        self.relay_code, self.error_body_state, self.started = None, "not_inspected", clock()

    def inspect_error(self, response):
        # Never retain or reflect the error document, Location header or arbitrary code/message.
        if self.encoding_rejected:
            self.error_body_state = "encoded_body_skipped"
            return
        raw = bytearray()
        try:
            for chunk in response.iter_bytes():
                if len(raw) + len(chunk) > MAX_ERROR_BYTES or self.clock() - self.started >= 10:
                    self.error_body_state = "budget_exceeded"
                    return
                raw.extend(chunk)
            if self.clock() - self.started >= 10:
                self.error_body_state = "budget_exceeded"
                return
            payload = decode(bytes(raw), MAX_ERROR_BYTES)
            pending = [payload]
            while pending:
                item = pending.pop()
                if isinstance(item, float) and not math.isfinite(item):
                    raise ValueError("Nonfinite diagnostic JSON number")
                if isinstance(item, dict):
                    pending.extend(item.values())
                elif isinstance(item, list):
                    pending.extend(item)
            value = payload.get("code") if isinstance(payload, dict) else None
            if isinstance(value, str) and value in RELAY_CODES:
                self.relay_code, self.error_body_state = value, "allowlisted_code"
            else:
                self.error_body_state = "no_allowlisted_code"
        except httpx.HTTPError:
            self.error_body_state = "transport_error"
        except (ValueError, TypeError, RecursionError):
            self.error_body_state = "invalid_json"

    def factory(self, **options):
        if options.get("follow_redirects") is not False or options.get("trust_env") is not False:
            raise ValueError("Diagnostic transport options rejected")
        observer = self

        class Client:
            def __enter__(self):
                self.inner = observer.client(**options)
                self.inner.__enter__()
                return self

            def __exit__(self, *args):
                return self.inner.__exit__(*args)

            @contextmanager
            def stream(self, method, url, **kwargs):
                if method != "GET" or url != observer.expected_url or observer.attempts or set(kwargs) != {"headers"}:
                    raise ValueError("Diagnostic request boundary rejected")
                observer.attempts = 1
                try:
                    with self.inner.stream(method, url, **kwargs) as response:
                        value = response.status_code
                        observer.status = value if type(value) is int and 100 <= value <= 599 else None
                        observer.encoding_rejected = response.headers.get("content-encoding", "identity").lower() != "identity"
                        if value != 200:
                            observer.inspect_error(response)
                        yield response
                except httpx.HTTPError as exc:
                    observer.transport_error = http_failure(exc)
                    raise

        return Client()


def diagnose(provider, *, client=httpx.Client, clock=time.monotonic):
    """One fresh diagnostic observation, no retries, POSTs, raw receipts or trust keys.

    A relay code is a reported condition, not independent proof of ultimate cause.
    Even accepted metadata cannot qualify served identity or authorize execution.
    """
    result = {"recipe": RECIPE, "stage": "configuration_rejected", "http_status": None,
              "client_error": None, "relay_code": None, "error_body_state": "not_inspected",
              "metadata_GET_attempts": 0, "completion_POST_requests": 0, "native_inference_calls": 0,
              "metadata_accepted": False, "identity_issue": None, "qualified_identity": False,
              "native_execution_authorization": False, "production_activation": False}
    if not isinstance(provider, Provider):
        return result
    observer = None
    try:
        observer = Observation(provider._base() + "/models", client, clock)
        record = collect_identity(provider, trusted_key=None, client_factory=observer.factory)
        result.update(stage="metadata_accepted_identity_unqualified", metadata_accepted=True)
        issues = record["issues"]
        if issues == ["signed_provider_identity_unavailable"]:
            result["identity_issue"] = "signed_provider_identity_unavailable"
        elif issues == ["independent_provider_trust_key_unavailable"]:
            result["identity_issue"] = "independent_provider_trust_key_unavailable"
    except Exception as exc:  # noqa: BLE001 - outer diagnostic boundary must not leak arbitrary transport errors
        # Compare only known literal collector errors; never publish exception text/type/traceback.
        result["stage"] = "unclassified_rejection"
        if type(exc) in {ValueError, ProviderError, TunnelConfigurationError}:
            result["stage"] = COLLECTOR_FAILURES.get(str(exc), "unclassified_rejection")
        if observer and observer.transport_error:
            result["stage"] = "http_transport_rejected"
        elif observer and observer.status is not None and observer.status != 200:
            result["stage"] = "http_status_rejected"
        elif observer and observer.encoding_rejected:
            result["stage"] = "encoded_metadata_rejected"
    if observer:
        result.update(http_status=observer.status, client_error=observer.transport_error,
                      relay_code=observer.relay_code, error_body_state=observer.error_body_state,
                      metadata_GET_attempts=observer.attempts)
    return result
