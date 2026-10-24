"""Fresh invented cases frozen before first grading; no real case material."""

import json

CASES = (
    ("H2401", "good", 200, 1),
    ("H2402", "mutable_tag", 400, 0),
    ("H2403", "foreign_key", 400, 0),
    ("H2404", "tamper_request", 400, 0),
    ("H2405", "remote_manifest", 400, 0),
    ("H2406", "corrupt_blob", 400, 0),
    ("H2407", "redirect", 400, 1),
    ("H2408", "http502", 400, 1),
    ("H2409", "wrong_model", 400, 1),
    ("H2410", "clipped", 400, 1),
    ("H2411", "missing_usage", 400, 1),
    ("H2412", "body_overflow", 400, 1),
    ("H2413", "policy_changed", 400, 0),
    ("H2414", "late_expiry", 400, 1),
    ("H2415", "revoked_during", 400, 1),
    ("H2416", "replay", 400, 1),
)
SUITE_CANONICAL = json.dumps(CASES, separators=(",", ":"))
