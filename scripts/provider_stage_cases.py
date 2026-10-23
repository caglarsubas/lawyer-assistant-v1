"""Fresh frozen staged-adapter/trust outcomes. Invented inputs, no native calls."""

import json

CASES = (
    ("P2401", "good", "receipt_consumed"),
    ("P2402", "auth_disabled", "identity_rejected"),
    ("P2403", "key_expired", "identity_rejected"),
    ("P2404", "missing_explicit_key_id", "identity_rejected"),
    ("P2405", "foreign_principal", "identity_rejected"),
    ("P2406", "mutable_tag", "identity_rejected"),
    ("P2407", "digest_changed", "identity_rejected"),
    ("P2408", "external_endpoint", "identity_rejected"),
    ("P2409", "retry_attempt", "receipt_rejected"),
    ("P2410", "wrong_executed_ref", "receipt_rejected"),
    ("P2411", "expired", "receipt_rejected"),
    ("P2412", "not_completed", "receipt_rejected"),
)
SUITE_CANONICAL = json.dumps(CASES, separators=(",", ":"))
