"""New invented phase cases, frozen before execution."""
import json

CASES = (
    ("P2101", "ok", "metadata_validation", "metadata_accepted_identity_unqualified"),
    ("P2102", "tcp_timeout", "tcp_connect", "timeout"),
    ("P2103", "tls_timeout", "tls_handshake", "timeout"),
    ("P2104", "send_timeout", "request_send", "timeout"),
    ("P2105", "headers_timeout", "response_headers", "timeout"),
    ("P2106", "body_timeout", "response_body", "timeout"),
    ("P2107", "redirect", "response_headers", "rejected"),
    ("P2108", "nonfinite", "metadata_validation", "rejected"),
)
SUITE_CANONICAL = json.dumps(CASES, separators=(",", ":"))
