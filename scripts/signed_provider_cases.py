"""Fresh frozen v2 protocol cases, invented data only, no native generation."""

import json

CASES = (
    ("P2301", "valid", "bound"),
    ("P2302", "foreign_tenant", "identity_rejected"),
    ("P2303", "unknown_trust", "identity_rejected"),
    ("P2304", "identity_nonce", "identity_rejected"),
    ("P2305", "execution_missing", "response_rejected"),
    ("P2306", "execution_digest", "response_rejected"),
    ("P2307", "execution_nonce", "response_rejected"),
    ("P2308", "execution_old", "response_rejected"),
    ("P2309", "wire_tamper", "response_rejected"),
    ("P2310", "request_tamper", "response_rejected"),
    ("P2311", "expired", "identity_rejected"),
    ("P2312", "duplicate_challenge", "handoff_rejected"),
    ("P2313", "fallback", "response_rejected"),
    ("P2314", "nonfinite", "response_rejected"),
)
SUITE_CANONICAL = json.dumps(CASES, separators=(",", ":"))
