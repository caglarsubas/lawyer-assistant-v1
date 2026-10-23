"""Fresh invented path comparisons, frozen before first grading; no legal content."""
import json

CASES = (
    ("P2201", "ok", "ok", True, "both_metadata_accepted"),
    ("P2202", "ok", "preheader_close", True, "origin_only_metadata_accepted"),
    ("P2203", "tcp_timeout", "ok", True, "route_only_metadata_accepted"),
    ("P2204", "headers_timeout", "body_timeout", True, "neither_metadata_accepted"),
    ("P2205", "ok", "ok", False, "origin_unobserved"),
    ("P2206", "redirect", "ok", True, "route_only_metadata_accepted"),
    ("P2207", "ok", "redirect", True, "origin_only_metadata_accepted"),
    ("P2208", "nonfinite", "ok", True, "route_only_metadata_accepted"),
    ("P2209", "ok", "tls_error", True, "origin_only_metadata_accepted"),
    ("P2210", "ok", "refused", True, "origin_only_metadata_accepted"),
)
SUITE_CANONICAL = json.dumps(CASES, separators=(",", ":"))
